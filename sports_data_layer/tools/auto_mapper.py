"""
Automação ponta a ponta: descobre schema -> calcula confiança -> aplica
automaticamente o que é seguro -> só enfileira para revisão humana o
que é ambíguo, sem travar o pipeline.

Regra de confiança: quanto mais tokens da assinatura de um conceito
batem EXATAMENTE com os tokens do campo (sem sobra), maior a confiança.
Um campo "placar_mandante" com assinatura {"placar","mandante"} tem
confiança 1.0 (bate 100%). Um campo "resultado_mandante_final" com a
mesma assinatura tem confiança menor (2 de 3 tokens) — sobra "final"
sem explicação, o que é sinal de que pode ser outra coisa.

Limiar padrão: >= 0.7 aplica automaticamente. Abaixo disso, vai para
pending_review.json — visível, mas não bloqueia a extração de dados
(o campo simplesmente fica None até alguém confirmar o mapeamento).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .path_utils import find_record_list
from .schema_discovery import CONCEPT_SIGNATURES, FieldInfo, _tokenize, inspect_json
from .validators import passes_sanity_check

MAPPING_DIR = Path("mappings")
QUARANTINE_DIR = Path("quarantine")

# 0.4, não 0.7: caminhos aninhados legítimos (ex: "time_mandante.nome_popular")
# têm tokens estruturais extras que não indicam ambiguidade — a proteção real
# contra falso-positivo já vem do containment de assinatura (subset match) e
# do apply_sanity_gate (valor precisa ser plausível). A razão de confiança
# aqui serve para desempatar entre candidatos concorrentes ao mesmo conceito,
# não para rejeitar campos corretos só porque o caminho tem mais de 2 tokens.
AUTO_APPLY_THRESHOLD = 0.4


@dataclass
class MappingCandidate:
    concept: str
    path: str
    confidence: float
    sample_value: str = ""


def _score(field_tokens: set[str], signature: set[str]) -> float:
    if not signature.issubset(field_tokens):
        return 0.0
    return len(signature) / len(field_tokens)


def propose_mapping(fields: list[FieldInfo]) -> list[MappingCandidate]:
    """Para cada campo, acha o conceito de maior confiança. Retorna
    UMA proposta por campo (a melhor), independente do limiar —
    a decisão de aplicar ou revisar acontece depois, em split_by_confidence."""

    proposals: list[MappingCandidate] = []
    for field in fields:
        field_tokens = _tokenize(field.path)
        best_concept, best_score = None, 0.0

        for concept, signatures in CONCEPT_SIGNATURES.items():
            for signature in signatures:
                score = _score(field_tokens, signature)
                if score > best_score:
                    best_score, best_concept = score, concept

        if best_concept:
            proposals.append(MappingCandidate(best_concept, field.path, round(best_score, 2), field.sample_value))

    return proposals


def apply_sanity_gate(proposals: list[MappingCandidate]) -> tuple[list[MappingCandidate], list[MappingCandidate]]:
    """Segunda camada de defesa, totalmente automática: mesmo um
    candidato com nome de campo perfeito é descartado se o VALOR de
    exemplo não for plausível para aquele conceito (ex: 'home_score'
    apontando pra um campo cujo valor é 'Bahia' — nome bate por
    coincidência, valor não faz sentido nenhum).

    Retorna (aprovados, quarentena). Nada aqui espera humano."""

    approved, quarantined = [], []
    for p in proposals:
        if passes_sanity_check(p.concept, p.sample_value):
            approved.append(p)
        else:
            quarantined.append(p)
    return approved, quarantined


def split_by_confidence(
    proposals: list[MappingCandidate], threshold: float = AUTO_APPLY_THRESHOLD
) -> tuple[dict[str, MappingCandidate], list[MappingCandidate]]:
    """Separa em (mapeamento automático, fila de revisão).

    Quando dois campos disputam o mesmo conceito, o de maior confiança
    vence automaticamente e o perdedor vai pra revisão (pode ser um
    campo duplicado legítimo, ou sinal de que a assinatura do conceito
    precisa ficar mais específica)."""

    by_concept: dict[str, list[MappingCandidate]] = {}
    for p in proposals:
        by_concept.setdefault(p.concept, []).append(p)

    auto_applied: dict[str, MappingCandidate] = {}
    needs_review: list[MappingCandidate] = []

    for concept, candidates in by_concept.items():
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        winner = candidates[0]
        if winner.confidence >= threshold:
            auto_applied[concept] = winner
            needs_review.extend(candidates[1:])  # concorrentes descartados, visíveis pra auditoria
        else:
            needs_review.extend(candidates)

    return auto_applied, needs_review


def build_and_save_mapping(provider: str, raw_response: dict) -> dict:
    """Função principal do pipeline autônomo. Roda tudo sem parar em
    nenhum ponto para esperar decisão humana:

      1. Descobre schema.
      2. Propõe mapeamento por nome de campo (confiança).
      3. Filtra por valor plausível (sanidade) — segunda camada,
         independente da confiança do nome.
      4. Resolve empates (dois campos querendo o mesmo conceito):
         vence o de maior confiança; o perdedor vai pra quarentena.
      5. Salva o mapeamento aplicado E o log de quarentena (auditoria
         que você pode olhar quando quiser, mas que nunca bloqueia
         nada).

    Um campo em quarentena não impede o pipeline de rodar — ele
    simplesmente fica ausente do mapeamento, e a camada de
    capacidades (ver capabilities_from_mapping) automaticamente marca
    aquela informação como indisponível para este provedor. O motor
    de hipóteses pula sozinho o que depender dela."""

    MAPPING_DIR.mkdir(exist_ok=True)
    QUARANTINE_DIR.mkdir(exist_ok=True)

    list_info = find_record_list(raw_response)
    if list_info is None:
        raise ValueError(
            f"[{provider}] não encontrei nenhuma lista de registros na resposta bruta."
        )
    list_path, records = list_info
    sample_fields = inspect_json(records[0])

    proposals = propose_mapping(sample_fields)
    sane_proposals, sanity_quarantined = apply_sanity_gate(proposals)
    auto_applied, confidence_quarantined = split_by_confidence(sane_proposals)
    all_quarantined = sanity_quarantined + confidence_quarantined

    mapping_path = MAPPING_DIR / f"{provider}.json"
    previous = json.loads(mapping_path.read_text()) if mapping_path.exists() else {}
    previous_fields = previous.get("fields", {})

    changed = {
        concept: {"antes": previous_fields.get(concept, {}).get("path"), "agora": c.path}
        for concept, c in auto_applied.items()
        if previous_fields.get(concept, {}).get("path") != c.path
    }

    mapping_payload = {
        "provider": provider,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "list_path": list_path,
        "fields": {concept: {"path": c.path, "confidence": c.confidence} for concept, c in auto_applied.items()},
    }
    mapping_path.write_text(json.dumps(mapping_payload, indent=2, ensure_ascii=False))

    if all_quarantined:
        quarantine_path = QUARANTINE_DIR / f"{provider}.json"
        quarantine_path.write_text(
            json.dumps(
                {
                    "provider": provider,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "nota": "Estes campos NÃO estão em uso. O pipeline segue rodando sem eles.",
                    "descartados": [
                        {"conceito": c.concept, "campo": c.path, "confianca": c.confidence, "valor_amostra": c.sample_value}
                        for c in all_quarantined
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )

    return {
        "mapeados_automaticamente": len(auto_applied),
        "em_quarentena": len(all_quarantined),
        "mudou_desde_ultima_vez": changed,
        "mapping_path": str(mapping_path),
    }
