"""
Testes de D006 (desempenho em casa vs fora).

O teste mais importante aqui não é "a conta está certa" — é
"o sistema se recusa a opinar sem amostra suficiente". Isso existe
porque vimos, rodando contra dado real, que com 1 jogo de cada lado
9 de 15 times pareciam ter um padrão "forte" que era só ruído.
"""

from ..models import Match, Team


def _match(home_name, away_name, home_score, away_score, day=1):
    from datetime import datetime

    return Match(
        id=f"{home_name}-{away_name}-{day}",
        competition="teste",
        season="2026",
        date=datetime(2026, 1, day),
        home_team=Team(id=home_name, name=home_name),
        away_team=Team(id=away_name, name=away_name),
        home_score=home_score,
        away_score=away_score,
        status="finished",
    )


def test_nao_publica_descoberta_com_amostra_pequena():
    """Regressão do achado real: 1 jogo em casa + 1 fora nunca deve
    gerar Discovery, mesmo que a diferença pareça grande (100%)."""
    from .home_advantage import HomeAwayPerformance

    matches = [
        _match("Flamengo", "Vitória", 3, 0, day=1),   # Flamengo vence em casa
        _match("Botafogo", "Flamengo", 2, 0, day=2),  # Flamengo perde fora
    ]
    discoveries = HomeAwayPerformance().evaluate(matches)
    assert discoveries == []  # amostra de 1 jogo de cada lado — não é suficiente


def test_publica_descoberta_com_amostra_suficiente_e_diferenca_real():
    """Com amostra suficiente (5+ de cada lado) e diferença grande,
    a Discovery deve aparecer com o sample_size correto e visível."""
    from .home_advantage import HomeAwayPerformance

    matches = []
    for i in range(6):
        matches.append(_match("Time Forte", f"Adv{i}", 2, 0, day=i + 1))       # sempre vence em casa
        matches.append(_match(f"Adv{i}", "Time Forte", 1, 1, day=15 + i))      # sempre empata fora

    discoveries = HomeAwayPerformance().evaluate(matches)
    assert len(discoveries) == 1
    assert discoveries[0].subject == "Time Forte"
    assert discoveries[0].sample_size == 12  # 6 em casa + 6 fora, nunca escondido


def test_diferenca_pequena_nao_e_publicada_mesmo_com_amostra_grande():
    """Amostra grande não basta — a diferença em si precisa ser
    grande o bastante pra não ser variação normal de futebol."""
    from .home_advantage import HomeAwayPerformance

    matches = []
    for i in range(6):
        # Aproveitamento parecido em casa e fora (sem padrão real)
        matches.append(_match("Time Equilibrado", f"Adv{i}", 1, 1, day=i + 1))
        matches.append(_match(f"Adv{i}", "Time Equilibrado", 1, 1, day=15 + i))

    discoveries = HomeAwayPerformance().evaluate(matches)
    assert discoveries == []
