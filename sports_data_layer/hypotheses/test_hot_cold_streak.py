from datetime import datetime, timedelta

from ..models import Match, Team
from .hot_cold_streak import HotColdStreak


def _match(home_name, away_name, home_score, away_score, day):
    return Match(
        id=f"{home_name}-{away_name}-{day}",
        competition="teste",
        season="2026",
        date=datetime(2026, 1, 1) + timedelta(days=day),
        home_team=Team(id=home_name, name=home_name),
        away_team=Team(id=away_name, name=away_name),
        home_score=home_score,
        away_score=away_score,
        status="finished",
    )


def test_nao_publica_sem_jogos_suficientes_na_temporada():
    """Com poucos jogos totais, não há 'média da temporada' confiável
    pra comparar contra a forma recente."""
    matches = [_match("Time", f"Adv{i}", 3, 0, day=i) for i in range(6)]  # só 6 jogos, mínimo é 10
    assert HotColdStreak().evaluate(matches) == []


def test_publica_sequencia_quente_com_amostra_suficiente():
    """Time com desempenho mediano na temporada mas ótimo nos últimos
    5 jogos deve aparecer como 'quente', com o sample_size visível."""
    matches = []
    # 5 primeiros jogos: resultados mistos (aproveitamento baixo)
    for i in range(5):
        matches.append(_match("Time", f"Adv{i}", 0, 1, day=i))  # perde tudo no início
    # últimos 5 jogos: sequência vitoriosa
    for i in range(5, 10):
        matches.append(_match("Time", f"Adv{i}", 3, 0, day=i))  # vence tudo recentemente

    discoveries = HotColdStreak().evaluate(matches)
    assert len(discoveries) == 1
    assert "quente" in discoveries[0].title
    assert discoveries[0].sample_size == 10


def test_nao_publica_diferenca_pequena_mesmo_com_amostra_grande():
    """Desempenho recente parecido com a média da temporada não deve
    virar 'descoberta' só porque há muitos jogos disponíveis."""
    matches = [_match("Time Estável", f"Adv{i}", 1, 1, day=i) for i in range(12)]  # sempre empata
    assert HotColdStreak().evaluate(matches) == []
