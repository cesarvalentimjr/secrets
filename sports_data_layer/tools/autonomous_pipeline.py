"""
Pipeline 100% autônomo: da URL bruta a dados normalizados, sem nenhum
ponto de espera humana. Pensado pra rodar num cron/agendador todo dia,
sozinho.

O que ele faz sozinho, sem perguntar nada:
  1. Busca a resposta bruta da API.
  2. Descobre o schema e propõe mapeamento (nome de campo).
  3. Filtra por sanidade de valor (segunda camada de defesa).
  4. Resolve conflitos e aplica o mapeamento de alta confiança.
  5. Deriva as capacidades disponíveis automaticamente.
  6. Registra tudo isso na CapabilityMatrix.
  7. Já devolve os Match/StandingRow normalizados, prontos pro motor
     de hipóteses consumir.

Nada aqui bloqueia esperando aprovação. Campos incertos ficam de fora
silenciosamente (registrados em quarantine/<provider>.json só como
log de auditoria) e o motor de hipóteses recebe menos capacidades —
nunca dado errado.
"""

from __future__ import annotations

import logging
from datetime import date

import requests

from ..capabilities import CapabilityMatrix
from .auto_mapper import build_and_save_mapping
from .generic_mapping_adapter import GenericMappingAdapter, register_autonomous_provider

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pipeline_autonomo")


def run_autonomous_ingestion(
    provider: str,
    url: str,
    competition: str,
    capability_matrix: CapabilityMatrix,
    headers: dict | None = None,
) -> GenericMappingAdapter:
    """Roda a cadeia inteira para um provedor e devolve um adaptador
    já pronto pra uso pelo motor de hipóteses. Chame isso num loop,
    um por provedor/competição, no seu job agendado diário."""

    logger.info("Buscando resposta bruta de %s (%s)", provider, url)
    resp = requests.get(url, headers=headers or {}, timeout=15)
    resp.raise_for_status()
    raw = resp.json()

    result = build_and_save_mapping(provider, raw)
    logger.info(
        "Mapeamento de %s: %d campos aplicados, %d em quarentena. Mudanças: %s",
        provider,
        result["mapeados_automaticamente"],
        result["em_quarentena"],
        result["mudou_desde_ultima_vez"] or "nenhuma",
    )

    register_autonomous_provider(provider, competition, capability_matrix)

    return GenericMappingAdapter(provider, url, capability_matrix, headers)


if __name__ == "__main__":
    # Exemplo de execução diária autônoma — sem nenhum input humano.
    capability_matrix = CapabilityMatrix()

    providers_config = [
        {
            "provider": "api_futebol",
            "url": "https://api.api-futebol.com.br/v1/campeonatos/10/partidas",
            "competition": "brasileirao_a",
            "headers": {"Authorization": "Bearer SEU_TOKEN"},
        },
    ]

    for cfg in providers_config:
        try:
            adapter = run_autonomous_ingestion(
                cfg["provider"], cfg["url"], cfg["competition"], capability_matrix, cfg.get("headers")
            )
            matches = adapter.get_matches(cfg["competition"], date(2026, 1, 1), date.today())
            logger.info("%s: %d partidas normalizadas e prontas para o motor de hipóteses", cfg["provider"], len(matches))
        except Exception as exc:
            # Um provedor falhando não derruba os outros — autonomia
            # inclui tolerância a falha, não só ausência de perguntas.
            logger.error("Falha ao processar %s: %s", cfg["provider"], exc)
