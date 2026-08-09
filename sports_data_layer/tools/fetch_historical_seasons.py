"""
Busca automática de todas as temporadas históricas do Brasileirão
(2014-2026) na TheSportsDB, usando a chave pública gratuita.

Por que isso roda na SUA máquina, não aqui no chat: a ferramenta de
navegação que a Claude usa em chat só acessa URLs que já apareceram
antes numa busca — ela não deixa montar uma URL nova com parâmetro
diferente (ex: trocar o ano). Rodando localmente, esse limite não
existe: você tem acesso de rede livre.

Uso:
    pip install requests
    python fetch_historical_seasons.py

Isso cria um arquivo JSON por temporada em ./dados_historicos/, e um
arquivo consolidado com tudo junto, pronto para o pipeline (auto_mapper,
run_daily_discoveries) processar.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

LEAGUE_ID = "4351"  # Brazilian Serie A na TheSportsDB
API_KEY = "123"  # chave pública gratuita, sem cadastro
BASE_URL = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/eventsseason.php"
OUTPUT_DIR = Path("dados_historicos")
SEASONS = range(2014, 2027)  # 2014 até 2026 inclusive
DELAY_BETWEEN_REQUESTS_SECONDS = 1.2  # respeita o limite de taxa do plano gratuito


def fetch_season(year: int) -> dict | None:
    """Busca uma temporada. A TheSportsDB usa formatos diferentes de
    ano dependendo da liga — pro Brasileirão é ano único ("2024"),
    mas tentamos o formato "2024-2025" como plano B caso a API mude
    de convenção no futuro."""

    for season_param in (str(year), f"{year}-{year + 1}"):
        try:
            resp = requests.get(BASE_URL, params={"id": LEAGUE_ID, "s": season_param}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"  [{year}] erro na chamada ({season_param}): {exc}")
            continue

        events = data.get("events")
        if events:
            print(f"  [{year}] OK — {len(events)} partidas (parâmetro s={season_param})")
            return data

    print(f"  [{year}] nenhuma partida encontrada em nenhum formato de temporada")
    return None


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    consolidated_events = []
    summary = {}

    for year in SEASONS:
        print(f"Buscando temporada {year}...")
        data = fetch_season(year)

        if data:
            season_path = OUTPUT_DIR / f"{year}.json"
            season_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            consolidated_events.extend(data["events"])
            summary[year] = len(data["events"])
        else:
            summary[year] = 0

        time.sleep(DELAY_BETWEEN_REQUESTS_SECONDS)

    consolidated_path = OUTPUT_DIR / "todas_temporadas.json"
    consolidated_path.write_text(
        json.dumps({"events": consolidated_events}, indent=2, ensure_ascii=False)
    )

    print("\n=== Resumo ===")
    for year, count in summary.items():
        status = f"{count} partidas" if count else "FALHOU — confira manualmente"
        print(f"  {year}: {status}")
    print(f"\nTotal consolidado: {len(consolidated_events)} partidas em {consolidated_path}")
    print("\nPróximo passo: aponte o pipeline (auto_mapper / run_daily_discoveries) para este arquivo.")


if __name__ == "__main__":
    main()
