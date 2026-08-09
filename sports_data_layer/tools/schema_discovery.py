"""
Descoberta automática de schema de APIs de dados esportivos.

Problema que isso resolve: em vez de adivinhar nomes de campo (o que
fiz nos adaptadores iniciais como "time_mandante", "gols_mandante"),
esta ferramenta chama o endpoint real, lista TODOS os campos que
vieram na resposta, e sugere automaticamente a qual conceito do seu
modelo normalizado (models.py) cada campo bruto provavelmente
corresponde — usando pistas no próprio nome do campo.

Uso típico:
    python -m sports_data_layer.tools.schema_discovery \\
        --url "https://api.api-futebol.com.br/v1/campeonatos/10/partidas" \\
        --headers "Authorization=Bearer SEU_TOKEN" \\
        --provider api_futebol

Isso imprime um relatório e salva um "retrato" do schema em
schema_snapshots/api_futebol.json. Rodar de novo mais tarde e comparar
os dois é como você detecta que o provedor mudou algo sem avisar.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

SNAPSHOT_DIR = Path("schema_snapshots")

# Cada conceito do modelo normalizado tem uma ou mais "assinaturas":
# conjuntos de tokens que, se TODOS estiverem presentes no caminho do
# campo, indicam esse conceito. Usar conjuntos (em vez de substring
# simples) evita que "placar_mandante" seja capturado por "mandante"
# sozinho — ele só bate com a assinatura de home_score, que exige
# "placar" E "mandante" ao mesmo tempo.
CONCEPT_SIGNATURES: dict[str, list[set[str]]] = {
    "match_id": [{"partida", "id"}, {"match", "id"}, {"fixture", "id"}, {"id", "event"}],
    "competition_id": [{"campeonato", "id"}, {"competition", "id"}, {"league", "id"}, {"id", "league"}],
    "match_date": [{"data", "realizacao"}, {"date"}, {"date", "event"}, {"data", "jogo"}],
    "status": [{"status"}, {"situacao"}],
    "home_team_id": [{"time", "mandante", "id"}, {"home", "team", "id"}],
    "away_team_id": [{"time", "visitante", "id"}, {"away", "team", "id"}],
    "home_team_name": [{"mandante", "nome"}, {"home", "team"}, {"str", "home", "team"}],
    "away_team_name": [{"visitante", "nome"}, {"away", "team"}, {"str", "away", "team"}],
    "home_score": [{"placar", "mandante"}, {"gols", "mandante"}, {"home", "score"}],
    "away_score": [{"placar", "visitante"}, {"gols", "visitante"}, {"away", "score"}],
    "event_minute": [{"minuto"}, {"minute"}, {"elapsed"}],
    "event_type": [{"tipo", "evento"}, {"tipo"}, {"event", "type"}],
    "player_id": [{"jogador", "id"}, {"player", "id"}],
    "player_name": [{"jogador", "nome"}, {"player", "name"}, {"str", "player"}],
    "team_id": [{"time", "id"}, {"team", "id"}, {"id", "team"}],
    "points": [{"pontos"}, {"points"}],
    "wins": [{"vitorias"}, {"wins"}, {"win"}],
    "draws": [{"empates"}, {"draws"}, {"draw"}],
    "losses": [{"derrotas"}, {"losses"}, {"loss"}],
    "goals_for": [{"gols", "pro"}, {"goals", "for"}],
    "goals_against": [{"gols", "contra"}, {"goals", "against"}],
    "lineup": [{"escalacao"}, {"lineup"}, {"titulares"}, {"starters"}],
    "substitution": [{"substituicao"}, {"substitution"}],
}


def _tokenize(path: str) -> set[str]:
    """Converte um caminho tipo 'eventos[0].time_mandante.nome_popular'
    num conjunto de tokens: {'eventos', 'time', 'mandante', 'nome', 'popular'}.
    Remove índices de lista, separa por pontuação e por camelCase."""

    no_indices = re.sub(r"\[\d+\]", "", path)
    spaced = re.sub(r"[._]", " ", no_indices)
    camel_split = re.sub(r"(?<!^)(?<![A-Z])(?=[A-Z])", " ", spaced)
    return {t for t in re.findall(r"[a-zA-Z]+", camel_split.lower())}


@dataclass
class FieldInfo:
    path: str          # ex: "resultados[0].time_mandante.nome_popular"
    json_type: str      # str, int, float, bool, list, dict, null
    sample_value: str   # representação curta do valor encontrado


def inspect_json(obj: Any, prefix: str = "", max_list_items: int = 1) -> list[FieldInfo]:
    """Percorre um JSON recursivamente e retorna todos os campos-folha
    encontrados, com caminho, tipo e um exemplo de valor.

    max_list_items limita quantos itens de uma lista são expandidos
    (listas de partidas podem ter centenas de itens idênticos em
    estrutura — expandir 1 já mostra o schema completo)."""

    fields: list[FieldInfo] = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            fields.extend(inspect_json(value, path, max_list_items))

    elif isinstance(obj, list):
        if not obj:
            fields.append(FieldInfo(path=f"{prefix}[]", json_type="list(vazia)", sample_value=""))
        else:
            for i, item in enumerate(obj[:max_list_items]):
                fields.extend(inspect_json(item, f"{prefix}[{i}]", max_list_items))

    else:
        fields.append(
            FieldInfo(
                path=prefix,
                json_type=type(obj).__name__ if obj is not None else "null",
                sample_value=str(obj)[:60],
            )
        )

    return fields


def suggest_mapping(fields: list[FieldInfo]) -> dict[str, list[str]]:
    """Para cada campo descoberto, testa a assinatura de todos os
    conceitos e atribui o campo ao conceito de assinatura mais
    específica (mais tokens) que ele contém por inteiro. Cada campo
    recebe no máximo UM conceito sugerido — isso evita que um campo
    apareça espalhado em vários conceitos incompatíveis, como
    acontecia na versão por substring.

    Isso é uma sugestão, não uma verdade — sempre confira o
    sample_value antes de fechar o mapeamento no adaptador."""

    suggestions: dict[str, list[str]] = {}

    for field in fields:
        field_tokens = _tokenize(field.path)
        best_concept: str | None = None
        best_score = 0

        for concept, signatures in CONCEPT_SIGNATURES.items():
            for signature in signatures:
                if signature.issubset(field_tokens) and len(signature) > best_score:
                    best_score = len(signature)
                    best_concept = concept

        if best_concept:
            suggestions.setdefault(best_concept, []).append(field.path)

    return suggestions


def fetch_and_inspect(url: str, headers: dict[str, str] | None = None) -> tuple[list[FieldInfo], dict]:
    resp = requests.get(url, headers=headers or {}, timeout=15)
    resp.raise_for_status()
    raw = resp.json()
    return inspect_json(raw), raw


def save_snapshot(provider_name: str, fields: list[FieldInfo]) -> Path:
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    path = SNAPSHOT_DIR / f"{provider_name}.json"
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "fields": [asdict(f) for f in fields],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def diff_against_snapshot(provider_name: str, current_fields: list[FieldInfo]) -> dict[str, list[str]]:
    """Compara os campos atuais com o último retrato salvo.
    Retorna {"novos": [...], "sumidos": [...]} — é isso que te avisa
    que a API mudou algo antes de quebrar seu pipeline em produção."""

    path = SNAPSHOT_DIR / f"{provider_name}.json"
    if not path.exists():
        return {"novos": [], "sumidos": [], "aviso": ["nenhum retrato anterior encontrado — este é o primeiro"]}

    previous = json.loads(path.read_text())
    previous_paths = {f["path"] for f in previous["fields"]}
    current_paths = {f.path for f in current_fields}

    return {
        "novos": sorted(current_paths - previous_paths),
        "sumidos": sorted(previous_paths - current_paths),
    }


def print_report(provider_name: str, fields: list[FieldInfo]) -> None:
    print(f"\n=== Schema descoberto: {provider_name} ({len(fields)} campos) ===")
    for f in fields:
        print(f"  {f.path:<50} {f.json_type:<10} ex: {f.sample_value}")

    print("\n=== Sugestão de mapeamento para o modelo normalizado ===")
    suggestions = suggest_mapping(fields)
    if not suggestions:
        print("  Nenhuma correspondência automática encontrada — mapeie manualmente.")
    for concept, paths in suggestions.items():
        print(f"  {concept:<20} <- {paths}")

    diff = diff_against_snapshot(provider_name, fields)
    print("\n=== Comparação com retrato anterior ===")
    print(f"  Campos novos:  {diff.get('novos', [])}")
    print(f"  Campos sumidos: {diff.get('sumidos', [])}")
    if diff.get("aviso"):
        print(f"  Aviso: {diff['aviso']}")

    saved_path = save_snapshot(provider_name, fields)
    print(f"\nRetrato salvo em: {saved_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Descobre e mapeia o schema de uma API de dados esportivos.")
    parser.add_argument("--url", required=True, help="URL do endpoint a inspecionar")
    parser.add_argument("--provider", required=True, help="Nome curto do provedor (ex: api_futebol)")
    parser.add_argument(
        "--headers",
        nargs="*",
        default=[],
        help="Headers no formato Chave=Valor, ex: Authorization='Bearer TOKEN'",
    )
    args = parser.parse_args()

    headers = dict(h.split("=", 1) for h in args.headers)
    discovered_fields, _raw = fetch_and_inspect(args.url, headers)
    print_report(args.provider, discovered_fields)
