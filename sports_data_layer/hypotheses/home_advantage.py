"""
D006 — Um time joga significativamente melhor em casa do que fora
(ou vice-versa), com diferença grande o suficiente pra não ser
coincidência de amostra pequena.

Métrica: aproveitamento de pontos (%) em casa vs fora, por time.
Só vira Discovery se o time tiver jogado o mínimo de partidas EM CASA
e o mínimo FORA — não adianta ter 20 jogos totais se 18 foram em casa
e 2 fora; a comparação em si precisa de amostra dos dois lados.
"""

from __future__ import annotations

from collections import defaultdict

from ..capabilities import Capability
from ..models import Match
from ..tools.stats_utils import two_proportion_p_value
from .base import Discovery, Hypothesis

# Diferença mínima de aproveitamento (em pontos percentuais) para
# considerar "significativamente melhor" — abaixo disso é variação
# normal de futebol, não padrão. Isto é o filtro de EFEITO PRÁTICO;
# o p-valor calculado abaixo é o filtro de SIGNIFICÂNCIA ESTATÍSTICA
# (usado depois, em lote, por apply_multiple_comparisons_correction).
MIN_DIFFERENCE_PP = 15.0


class HomeAwayPerformance(Hypothesis):
    code = "D006"
    title = "Desempenho em casa vs fora"
    required_capabilities = {Capability.BASIC_RESULTS}
    min_sample_size = 5  # mínimo de jogos EM CADA lado (casa e fora), não total

    def evaluate(self, matches: list[Match], context: dict | None = None) -> list[Discovery]:
        home_points: dict[str, list[int]] = defaultdict(list)   # team_id -> [pontos por jogo em casa]
        away_points: dict[str, list[int]] = defaultdict(list)
        home_wins: dict[str, int] = defaultdict(int)             # pra teste de proporção (vitória binária)
        away_wins: dict[str, int] = defaultdict(int)
        team_names: dict[str, str] = {}

        for m in matches:
            if m.home_score is None or m.away_score is None:
                continue

            team_names[m.home_team.id] = m.home_team.name
            team_names[m.away_team.id] = m.away_team.name

            if m.home_score > m.away_score:
                home_points[m.home_team.id].append(3)
                away_points[m.away_team.id].append(0)
                home_wins[m.home_team.id] += 1
            elif m.home_score < m.away_score:
                home_points[m.home_team.id].append(0)
                away_points[m.away_team.id].append(3)
                away_wins[m.away_team.id] += 1
            else:
                home_points[m.home_team.id].append(1)
                away_points[m.away_team.id].append(1)

        discoveries = []
        all_team_ids = set(home_points) | set(away_points)

        for team_id in all_team_ids:
            home_games = home_points.get(team_id, [])
            away_games = away_points.get(team_id, [])

            # Proteção central: sem amostra dos dois lados, não opina.
            if len(home_games) < self.min_sample_size or len(away_games) < self.min_sample_size:
                continue

            home_pct = 100 * sum(home_games) / (3 * len(home_games))
            away_pct = 100 * sum(away_games) / (3 * len(away_games))
            diff = home_pct - away_pct

            if abs(diff) < MIN_DIFFERENCE_PP:
                continue  # diferença pequena demais para ser um padrão, não só sorte

            p_value = two_proportion_p_value(
                home_wins.get(team_id, 0), len(home_games), away_wins.get(team_id, 0), len(away_games)
            )

            lado = "em casa" if diff > 0 else "fora"
            discoveries.append(
                Discovery(
                    code=self.code,
                    title=f"{team_names[team_id]} rende muito mais {lado}",
                    detail=(
                        f"Aproveitamento em casa: {home_pct:.0f}% ({len(home_games)} jogos). "
                        f"Fora: {away_pct:.0f}% ({len(away_games)} jogos). "
                        f"Diferença de {abs(diff):.0f} pontos percentuais."
                    ),
                    sample_size=len(home_games) + len(away_games),
                    subject=team_names[team_id],
                    p_value=p_value,
                )
            )

        return discoveries
