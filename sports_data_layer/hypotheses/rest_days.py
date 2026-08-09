"""
D022 — Poucos dias de descanso alteram o desempenho da equipe.

Métrica: compara o aproveitamento de pontos em jogos com pouco
descanso (≤ 3 dias desde o jogo anterior do mesmo time) contra jogos
com descanso normal (≥ 6 dias). Só usa BASIC_RESULTS — nenhum dado
de calendário além da data de cada partida, que já validamos vir
correto de verdade (TheSportsDB).

Limitação conhecida, não escondida: isto não diferencia viagem longa
de descanso curto por outros motivos (jogo de copa no meio da semana,
por exemplo). É "dias entre jogos", não "cansaço real por viagem" —
esse último exigiria dado de geolocalização de estádio, que não
temos hoje.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from ..capabilities import Capability
from ..models import Match
from ..tools.stats_utils import two_proportion_p_value
from .base import Discovery, Hypothesis

SHORT_REST_MAX_DAYS = 3
NORMAL_REST_MIN_DAYS = 6
MIN_DIFFERENCE_PP = 15.0


class RestDaysImpact(Hypothesis):
    code = "D022"
    title = "Impacto dos dias de descanso"
    required_capabilities = {Capability.BASIC_RESULTS}
    min_sample_size = 5  # mínimo de jogos EM CADA categoria (pouco descanso / descanso normal)

    def evaluate(self, matches: list[Match], context: dict | None = None) -> list[Discovery]:
        games_by_team: dict[str, list[tuple[datetime, int, bool]]] = defaultdict(list)
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

            games_by_team[m.home_team.id].append((m.date, home_pts, home_pts == 3))
            games_by_team[m.away_team.id].append((m.date, away_pts, away_pts == 3))

        discoveries = []
        for team_id, games in games_by_team.items():
            games.sort(key=lambda g: g[0])

            short_rest = []  # (pontos, foi_vitoria)
            normal_rest = []

            for i in range(1, len(games)):
                gap_days = (games[i][0] - games[i - 1][0]).days
                _, pts, won = games[i]
                if gap_days <= SHORT_REST_MAX_DAYS:
                    short_rest.append((pts, won))
                elif gap_days >= NORMAL_REST_MIN_DAYS:
                    normal_rest.append((pts, won))
                # gaps intermediários (4-5 dias) não entram em nenhuma categoria —
                # não são nem "pouco descanso" nem "descanso normal" com clareza

            if len(short_rest) < self.min_sample_size or len(normal_rest) < self.min_sample_size:
                continue

            short_pct = 100 * sum(p for p, _ in short_rest) / (3 * len(short_rest))
            normal_pct = 100 * sum(p for p, _ in normal_rest) / (3 * len(normal_rest))
            diff = normal_pct - short_pct

            if abs(diff) < MIN_DIFFERENCE_PP:
                continue

            short_wins = sum(1 for _, w in short_rest if w)
            normal_wins = sum(1 for _, w in normal_rest if w)
            p_value = two_proportion_p_value(normal_wins, len(normal_rest), short_wins, len(short_rest))

            discoveries.append(
                Discovery(
                    code=self.code,
                    title=f"{team_names[team_id]} rende {'pior' if diff > 0 else 'melhor'} com pouco descanso",
                    detail=(
                        f"Aproveitamento com ≤{SHORT_REST_MAX_DAYS} dias de descanso: {short_pct:.0f}% "
                        f"({len(short_rest)} jogos). Com ≥{NORMAL_REST_MIN_DAYS} dias: {normal_pct:.0f}% "
                        f"({len(normal_rest)} jogos)."
                    ),
                    sample_size=len(short_rest) + len(normal_rest),
                    subject=team_names[team_id],
                    p_value=p_value,
                )
            )

        return discoveries
