"""
Ponto de entrada único do motor de descobertas. Roda todas as
hipóteses disponíveis contra os dados de uma competição, aplica a
correção de múltiplas comparações sobre o lote inteiro, e devolve só
o que sobreviveu tanto ao efeito prático (definido em cada hipótese)
quanto à significância estatística ajustada.

Uso (depois de plugar as APIs em bootstrap.py):

    from sports_data_layer.tools.bootstrap import bootstrap_registry, ProviderSpec
    from sports_data_layer.tools.run_all_hypotheses import run_daily_discoveries

    registry = bootstrap_registry([...])
    matches = registry.get_matches("brasileirao_a", date(2026,1,1), date.today())
    standings = registry.get_standings("brasileirao_a", "2026")
    discoveries = run_daily_discoveries(matches, standings)
"""

from __future__ import annotations

from ..models import Match, StandingRow
from .base import Discovery, apply_multiple_comparisons_correction
from .home_advantage import HomeAwayPerformance
from .hot_cold_streak import HotColdStreak
from .opponent_tier import OpponentTierPerformance
from .publisher import format_batch
from .rest_days import RestDaysImpact

ALL_HYPOTHESES = [
    HomeAwayPerformance(),
    HotColdStreak(),
    RestDaysImpact(),
    OpponentTierPerformance(),
]


def run_daily_discoveries(
    matches: list[Match], standings: list[StandingRow] | None = None, alpha: float = 0.05
) -> list[Discovery]:
    """Roda todas as hipóteses disponíveis, junta os candidatos que já
    passaram no efeito prático de cada uma, e aplica Benjamini-Hochberg
    sobre o LOTE INTEIRO (todas as hipóteses juntas, não uma de cada
    vez) — é isso que corrige pelo fato de estarmos testando várias
    coisas ao mesmo tempo."""

    finished = [m for m in matches if m.is_finished]
    context = {"standings": standings or []}

    candidates: list[Discovery] = []
    for hypothesis in ALL_HYPOTHESES:
        candidates.extend(hypothesis.evaluate(finished, context))

    apply_multiple_comparisons_correction(candidates, alpha=alpha)
    return [d for d in candidates if d.adjusted_significant]


if __name__ == "__main__":
    import json
    import sys

    from ..adapters.generic_mapping_adapter import GenericMappingAdapter
    from ..capabilities import CapabilityMatrix

    if len(sys.argv) < 2:
        print("Uso: python -m sports_data_layer.hypotheses.run_all_hypotheses <arquivo_matches.json> [tabela.json]")
        sys.exit(1)

    matrix = CapabilityMatrix()
    adapter = GenericMappingAdapter("cli_run", "http://fake", matrix)

    raw = json.load(open(sys.argv[1]))
    list_path = adapter._mapping["list_path"]
    from ..tools.path_utils import get_by_path

    records = raw if list_path == "$root" else get_by_path(raw, list_path)
    matches = [adapter._record_to_match(r, "competicao") for r in records]
    matches = [m for m in matches if m]

    standings = []
    if len(sys.argv) > 2:
        raw_standings = json.load(open(sys.argv[2]))
        standings_records = get_by_path(raw_standings, adapter._mapping["list_path"]) or []
        for r in standings_records:
            team_id = adapter._extract(r, "team_id")
            points = adapter._extract(r, "points")
            if team_id and points is not None:
                standings.append(
                    StandingRow(
                        team_id=str(team_id),
                        position=len(standings) + 1,
                        played=0,
                        points=int(points),
                        wins=int(adapter._extract(r, "wins") or 0),
                        draws=int(adapter._extract(r, "draws") or 0),
                        losses=int(adapter._extract(r, "losses") or 0),
                        goals_for=int(adapter._extract(r, "goals_for") or 0),
                        goals_against=int(adapter._extract(r, "goals_against") or 0),
                    )
                )

    discoveries = run_daily_discoveries(matches, standings)
    print(format_batch(discoveries))
