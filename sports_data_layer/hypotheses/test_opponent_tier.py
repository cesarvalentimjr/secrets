from datetime import datetime, timedelta

from ..models import Match, StandingRow, Team
from .opponent_tier import OpponentTierPerformance


def _match(home, away, hs, as_, day):
    return Match(
        id=f"{home}-{away}-{day}",
        competition="teste",
        season="2026",
        date=datetime(2026, 1, 1) + timedelta(days=day),
        home_team=Team(id=home, name=home),
        away_team=Team(id=away, name=away),
        home_score=hs,
        away_score=as_,
        status="finished",
    )


def _standings(n_teams: int) -> list[StandingRow]:
    return [
        StandingRow(
            team_id=f"T{i}", position=i, played=38, points=0, wins=0, draws=0, losses=0, goals_for=0, goals_against=0
        )
        for i in range(1, n_teams + 1)
    ]


def test_sem_tabela_nao_gera_descoberta():
    matches = [_match("T20", "T1", 1, 0, day=0)]
    assert OpponentTierPerformance().evaluate(matches, context=None) == []
    assert OpponentTierPerformance().evaluate(matches, context={"standings": []}) == []


def test_time_z4_que_surpreende_contra_g6_e_detectado():
    """T20 (último colocado, Z4) vence times do G6 (posições 1-6)
    consistentemente, mas perde contra o meio de tabela — um padrão
    grande o suficiente pra passar no filtro de efeito prático."""
    standings = _standings(20)  # T1..T6 = G6, T7..T16 = meio, T17..T20 = Z4

    matches = []
    day = 0
    # T20 vence times do G6 (4 jogos, sample mínimo)
    for i in range(1, 5):
        matches.append(_match("T20", f"T{i}", 2, 0, day=day))
        day += 3
    # T20 perde contra o meio de tabela (4 jogos)
    for i in range(7, 11):
        matches.append(_match("T20", f"T{i}", 0, 2, day=day))
        day += 3

    discoveries = OpponentTierPerformance().evaluate(matches, context={"standings": standings})
    subjects_and_tiers = [(d.subject, "G6" in d.title) for d in discoveries]
    assert any(subj == "T20" for subj, _ in subjects_and_tiers)
