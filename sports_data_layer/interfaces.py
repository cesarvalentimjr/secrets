"""
Interface abstrata do provedor de dados.

Todo adaptador (API Futebol, Dados Futebol, TheSportsDB, football-data.org...)
implementa esta classe. O motor de hipóteses e a camada de abstração só
conversam com este contrato — nunca com uma classe concreta.
"""

from abc import ABC, abstractmethod
from datetime import date

from .capabilities import Capability
from .models import Match, StandingRow


class SportsDataProvider(ABC):
    """Contrato que qualquer fonte de dados esportivos deve cumprir."""

    #: Nome curto usado como chave na CapabilityMatrix e nos logs/config.
    name: str

    @abstractmethod
    def get_matches(self, competition: str, date_from: date, date_to: date) -> list[Match]:
        """Retorna partidas de uma competição num intervalo de datas,
        já traduzidas para o modelo normalizado (models.Match)."""
        ...

    @abstractmethod
    def get_match_detail(self, match_id: str) -> Match:
        """Retorna uma partida específica com o máximo de detalhe que
        o provedor conseguir (eventos, lineups) — pode vir incompleto,
        é responsabilidade do chamador checar capabilities antes."""
        ...

    @abstractmethod
    def get_standings(self, competition: str, season: str) -> list[StandingRow]:
        ...

    @abstractmethod
    def supports(self, capability: Capability, competition: str) -> bool:
        """Delega para a CapabilityMatrix interna do adaptador."""
        ...
