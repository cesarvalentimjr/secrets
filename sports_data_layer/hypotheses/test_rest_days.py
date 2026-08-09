from datetime import datetime, timedelta

from ..models import Match, Team
from .rest_days import RestDaysImpact


def _match(home, away, hs, as_, date):
    return Match(
        id=f"{home}-{away}-{date}",
        competition="teste",
        season="2026",
        date=date,
        home_team=Team(id=home, name=home),
        away_team=Team(id=away, name=away),
        home_score=hs,
        away_score=as_,
        status="finished",
    )


def test_nao_publica_sem_amostra_nas_duas_categorias():
    """Só jogos com descanso normal, nenhum com pouco descanso —
    não há base de comparação."""
    base = datetime(2026, 1, 1)
    matches = [_match("Time", f"Adv{i}", 2, 0, base + timedelta(days=i * 7)) for i in range(6)]
    assert RestDaysImpact().evaluate(matches) == []


def test_publica_quando_ha_diferenca_real_entre_categorias():
    base = datetime(2026, 1, 1)
    matches = []
    day = 0
    # 6 jogos com pouco descanso (a cada 2 dias), sempre perdendo
    for i in range(6):
        matches.append(_match("Time Cansado", f"AdvA{i}", 0, 2, base + timedelta(days=day)))
        day += 2
    # 6 jogos com descanso normal (a cada 7 dias), sempre vencendo
    for i in range(6):
        matches.append(_match("Time Cansado", f"AdvB{i}", 2, 0, base + timedelta(days=day)))
        day += 7

    discoveries = RestDaysImpact().evaluate(matches)
    assert len(discoveries) == 1
    assert discoveries[0].subject == "Time Cansado"
