"""
D006 — Um time se desvia da vantagem de casa que o RESTO DA LIGA tem,
pra mais ou pra menos.

Mudança de design (motivada por feedback real, ver histórico): a
primeira versão comparava cada time contra zero — "esse time joga
melhor em casa do que fora?". Isso é uma pergunta ruim, porque a
resposta é "sim" pra quase todo time do futebol; vantagem de casa é
um efeito real, forte e quase universal no esporte. Perguntar isso
não gera descoberta, gera confirmações do óbvio repetidas N vezes.

A pergunta certa é relativa: "esse time se desvia do padrão que os
OUTROS times da mesma liga, no mesmo período, também têm?". Só um
time que foge da norma — vantagem de casa muito mais forte que a
média, ou quase inexistente, ou até invertida — é uma descoberta de
verdade.

Limitação documentada, não escondida: o p-valor calculado aqui ainda
testa "o gap casa/fora DESTE time é diferente de zero", não "o gap
deste time é diferente da média da liga" (esse segundo teste exigiria
uma modelagem mais elaborada, tipo ANOVA ou teste de outlier baseado
em desvio padrão entre times). Por isso um time com gap perto de zero
— que seria um desvio da norma se a liga é +25pp em média — pode
aparecer como Discovery sem um p-valor "significativo" nesse teste
específico. Isso é aceitável aqui porque o efeito prático (a
comparação com a média da liga) já é o filtro central; o p-valor
entra só na correção de múltiplas comparações do lote inteiro, não
como único árbitro.
"""

from __future__ import annotations

import statistics
from collections import defaultdict

from ..capabilities import Capability
from ..models import Match
from ..tools.stats_utils import two_proportion_p_value
from .base import Discovery, Hypothesis

# Desvio mínimo (em pontos percentuais) em relação à MÉDIA DA LIGA
# pra considerar um time atípico — não é mais "diferença de zero".
MIN_DEVIATION_FROM_LEAGUE_PP = 15.0


class HomeAwayPerformance(Hypothesis):
    code = "D006"
    title = "Desvio da vantagem de casa em relação à liga"
    required_capabilities = {Capability.BASIC_RESULTS}
    min_sample_size = 5  # mínimo de jogos EM CADA lado (casa e fora), não total

    def evaluate(self, matches: list[Match], context: dict | None = None) -> list[Discovery]:
        home_points: dict[str, list[int]] = defaultdict(list)
        away_points: dict[str, list[int]] = defaultdict(list)
        home_wins: dict[str, int] = defaultdict(int)
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

        # --- Primeira passada: calcula o gap casa/fora de cada time
        # elegível, e a média da liga a partir só desses gaps válidos.
        team_diffs: dict[str, tuple[float, float, float]] = {}  # team_id -> (home_pct, away_pct, diff)
        all_team_ids = set(home_points) | set(away_points)

        for team_id in all_team_ids:
            home_games = home_points.get(team_id, [])
            away_games = away_points.get(team_id, [])

            if len(home_games) < self.min_sample_size or len(away_games) < self.min_sample_size:
                continue  # sem amostra dos dois lados, nem entra no cálculo da média da liga

            home_pct = 100 * sum(home_games) / (3 * len(home_games))
            away_pct = 100 * sum(away_games) / (3 * len(away_games))
            team_diffs[team_id] = (home_pct, away_pct, home_pct - away_pct)

        if len(team_diffs) < 3:
            return []  # liga com poucos times elegíveis — "referência da liga" não seria confiável

        # MEDIANA, não média: a média simples é arrastada por um único
        # outlier extremo (achado real ao testar — um time muito fora
        # do padrão fazia os times NORMAIS parecerem atípicos, porque
        # puxava a média inteira pra baixo). A mediana ignora isso.
        league_reference_diff = statistics.median(diff for _, _, diff in team_diffs.values())

        # --- Segunda passada: só reporta quem se desvia da referência da liga.
        discoveries = []
        for team_id, (home_pct, away_pct, diff) in team_diffs.items():
            deviation = diff - league_reference_diff
            if abs(deviation) < MIN_DEVIATION_FROM_LEAGUE_PP:
                continue  # está dentro do padrão da liga — não é descoberta

            home_games = home_points[team_id]
            away_games = away_points[team_id]
            p_value = two_proportion_p_value(
                home_wins.get(team_id, 0), len(home_games), away_wins.get(team_id, 0), len(away_games)
            )

            if deviation > 0:
                title = f"{team_names[team_id]} tem vantagem de casa muito acima da média da liga"
            else:
                title = f"{team_names[team_id]} tem vantagem de casa muito abaixo da média da liga (ou nenhuma)"

            discoveries.append(
                Discovery(
                    code=self.code,
                    title=title,
                    detail=(
                        f"Gap casa-fora deste time: {diff:+.0f} pontos percentuais "
                        f"(casa {home_pct:.0f}%, fora {away_pct:.0f}%, {len(home_games)}+{len(away_games)} jogos). "
                        f"Referência da liga (mediana) no mesmo período: {league_reference_diff:+.0f} pontos percentuais. "
                        f"Desvio: {deviation:+.0f} pontos percentuais."
                    ),
                    sample_size=len(home_games) + len(away_games),
                    subject=team_names[team_id],
                    p_value=p_value,
                )
            )

        return discoveries
