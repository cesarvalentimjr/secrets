"""
Aproveitamento contra adversários do G6, meio de tabela e Z4 (item 9
do seu MVP original). Precisa de duas capacidades ao mesmo tempo:
BASIC_RESULTS (pra saber quem jogou contra quem) e STANDINGS (pra
saber em que faixa da tabela cada adversário está).

Limitação conhecida, deliberadamente exposta: usa a classificação
FINAL da temporada pra definir quem é G6/meio/Z4, não a classificação
no momento exato de cada jogo. Isso é "olhar pra trás" (look-ahead) —
um time pode ter jogado contra um adversário que só terminou no Z4
DEPOIS de uma reta final ruim. O jeito estatisticamente correto seria
usar a tabela como estava no dia de cada partida, o que exige guardar
um histórico de tabela por rodada — não implementado ainda. Pra uso
em produção isto precisa ser corrigido antes de virar uma "descoberta"
publicada com confiança.
"""

from __future__ import annotations

from collections import defaultdict

from ..capabilities import Capability
from ..models import Match, StandingRow
from ..tools.stats_utils import two_proportion_p_value
from .base import Discovery, Hypothesis

MIN_DIFFERENCE_PP = 20.0


def _classify_tiers(standings: list[StandingRow]) -> dict[str, str]:
    """team_id -> 'G6' | 'meio' | 'Z4', a partir da posição final."""
    n = len(standings)
    tiers = {}
    for row in standings:
        if row.position <= 6:
            tiers[row.team_id] = "G6"
        elif row.position > n - 4:
            tiers[row.team_id] = "Z4"
        else:
            tiers[row.team_id] = "meio"
    return tiers


class OpponentTierPerformance(Hypothesis):
    code = "D101"  # não está no catálogo original D001-D030 — item novo, adicionado a partir do MVP
    title = "Aproveitamento por faixa de tabela do adversário"
    required_capabilities = {Capability.BASIC_RESULTS, Capability.STANDINGS}
    min_sample_size = 4  # mínimo de jogos contra a MESMA faixa (G6 só tem 6 times, então poucos jogos por faixa)

    def evaluate(self, matches: list[Match], context: dict | None = None) -> list[Discovery]:
        standings = (context or {}).get("standings")
        if not standings:
            return []  # sem tabela, não dá pra classificar adversário — pula, não força

        tiers = _classify_tiers(standings)

        # pontos e vitórias por (time, faixa_do_adversário)
        points_by_tier: dict[tuple[str, str], list[int]] = defaultdict(list)
        wins_by_tier: dict[tuple[str, str], int] = defaultdict(int)
        team_names: dict[str, str] = {}

        for m in matches:
            if m.home_score is None or m.away_score is None:
                continue
            team_names[m.home_team.id] = m.home_team.name
            team_names[m.away_team.id] = m.away_team.name

            away_tier = tiers.get(m.away_team.id)
            home_tier = tiers.get(m.home_team.id)
            if away_tier is None or home_tier is None:
                continue  # time sem classificação na tabela fornecida (dado incompleto) — pula esta partida

            if m.home_score > m.away_score:
                home_pts, away_pts = 3, 0
            elif m.home_score < m.away_score:
                home_pts, away_pts = 0, 3
            else:
                home_pts, away_pts = 1, 1

            points_by_tier[(m.home_team.id, away_tier)].append(home_pts)
            points_by_tier[(m.away_team.id, home_tier)].append(away_pts)
            if home_pts == 3:
                wins_by_tier[(m.home_team.id, away_tier)] += 1
            if away_pts == 3:
                wins_by_tier[(m.away_team.id, home_tier)] += 1

        discoveries = []
        teams_with_data = {team_id for team_id, _ in points_by_tier}

        for team_id in teams_with_data:
            overall_games = [g for (t, _), games in points_by_tier.items() if t == team_id for g in games]
            if not overall_games:
                continue
            overall_pct = 100 * sum(overall_games) / (3 * len(overall_games))

            for tier in ("G6", "meio", "Z4"):
                tier_games = points_by_tier.get((team_id, tier), [])
                if len(tier_games) < self.min_sample_size:
                    continue

                tier_pct = 100 * sum(tier_games) / (3 * len(tier_games))
                diff = tier_pct - overall_pct
                if abs(diff) < MIN_DIFFERENCE_PP:
                    continue

                tier_wins = wins_by_tier.get((team_id, tier), 0)
                overall_wins = sum(1 for (t, _), games in points_by_tier.items() if t == team_id for pts in games if pts == 3)
                p_value = two_proportion_p_value(tier_wins, len(tier_games), overall_wins, len(overall_games))

                melhor_pior = "melhor" if diff > 0 else "pior"
                discoveries.append(
                    Discovery(
                        code=self.code,
                        title=f"{team_names[team_id]} joga {melhor_pior} contra times do {tier}",
                        detail=(
                            f"Aproveitamento contra {tier}: {tier_pct:.0f}% ({len(tier_games)} jogos). "
                            f"Aproveitamento geral: {overall_pct:.0f}% ({len(overall_games)} jogos)."
                        ),
                        sample_size=len(tier_games),
                        subject=team_names[team_id],
                        p_value=p_value,
                    )
                )

        return discoveries
