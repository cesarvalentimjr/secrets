"""
D010 — Um time está numa sequência estatisticamente anormal
(positiva ou negativa) comparado ao seu próprio desempenho médio
na temporada.

Métrica: aproveitamento de pontos nos últimos N jogos vs aproveitamento
na temporada inteira. Só vira Discovery se:
  1. O time já tiver jogado o suficiente pra ter uma "média da
     temporada" confiável (não adianta comparar 3 jogos recentes
     contra uma média de 4 jogos totais — quase a mesma coisa).
  2. A janela recente realmente tiver o tamanho pedido (não uma
     janela incompleta de time que acabou de estrear).
  3. A diferença for grande o suficiente pra não ser oscilação normal.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from ..capabilities import Capability
from ..models import Match
from ..tools.stats_utils import two_proportion_p_value
from .base import Discovery, Hypothesis

RECENT_WINDOW = 5           # últimos N jogos considerados "forma recente"
MIN_SEASON_GAMES = 10        # mínimo de jogos na temporada pra ter uma "média" confiável
MIN_DIFFERENCE_PP = 20.0     # diferença mínima (pontos percentuais) pra não ser ruído


class HotColdStreak(Hypothesis):
    code = "D010"
    title = "Sequência estatisticamente anormal (time quente ou frio)"
    required_capabilities = {Capability.BASIC_RESULTS}
    min_sample_size = MIN_SEASON_GAMES

    def evaluate(self, matches: list[Match], context: dict | None = None) -> list[Discovery]:
        by_team: dict[str, list[tuple[datetime, int, bool]]] = defaultdict(list)  # (data, pontos, foi_vitoria)
        team_names: dict[str, str] = {}

        for m in matches:
            if m.home_score is None or m.away_score is None:
                continue

            team_names[m.home_team.id] = m.home_team.name
            team_names[m.away_team.id] = m.away_team.name

            if m.home_score > m.away_score:
                home_pts, away_pts = 3, 0
            elif m.home_score < m.away_score:
                home_pts, away_pts = 0, 3
            else:
                home_pts, away_pts = 1, 1

            by_team[m.home_team.id].append((m.date, home_pts, home_pts == 3))
            by_team[m.away_team.id].append((m.date, away_pts, away_pts == 3))

        discoveries = []
        for team_id, games in by_team.items():
            games.sort(key=lambda g: g[0])  # ordem cronológica

            if len(games) < self.min_sample_size:
                continue  # não há jogos suficientes pra confiar numa "média da temporada"

            recent = games[-RECENT_WINDOW:]
            if len(recent) < RECENT_WINDOW:
                continue  # janela recente incompleta — não compara

            season_pct = 100 * sum(p for _, p, _ in games) / (3 * len(games))
            recent_pct = 100 * sum(p for _, p, _ in recent) / (3 * len(recent))
            diff = recent_pct - season_pct

            if abs(diff) < MIN_DIFFERENCE_PP:
                continue

            season_wins = sum(1 for _, _, w in games if w)
            recent_wins = sum(1 for _, _, w in recent if w)
            p_value = two_proportion_p_value(recent_wins, len(recent), season_wins, len(games))

            status = "quente" if diff > 0 else "fria"
            discoveries.append(
                Discovery(
                    code=self.code,
                    title=f"{team_names[team_id]} está numa sequência {status}",
                    detail=(
                        f"Aproveitamento na temporada: {season_pct:.0f}% ({len(games)} jogos). "
                        f"Nos últimos {RECENT_WINDOW} jogos: {recent_pct:.0f}%. "
                        f"Diferença de {abs(diff):.0f} pontos percentuais."
                    ),
                    sample_size=len(games),
                    subject=team_names[team_id],
                    p_value=p_value,
                )
            )

        return discoveries
