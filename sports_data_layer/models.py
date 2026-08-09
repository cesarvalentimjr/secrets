"""
Modelo de dados normalizado.

Todo adaptador de provedor (API Futebol, Dados Futebol, TheSportsDB, etc.)
deve traduzir a resposta bruta da API dele para estas classes. O motor de
hipóteses (D001-D1500) NUNCA importa nada dos adaptadores — só importa
daqui. Isso é o que permite trocar de provedor sem tocar no motor.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class EventType(str, Enum):
    GOAL = "goal"
    YELLOW_CARD = "yellow_card"
    RED_CARD = "red_card"
    SUBSTITUTION = "substitution"
    PENALTY_MISSED = "penalty_missed"
    PENALTY_SCORED = "penalty_scored"


@dataclass
class Team:
    id: str  # id normalizado interno, não o id da API de origem
    name: str
    country: str = "BR"


@dataclass
class Player:
    id: str
    name: str
    team_id: str
    position: str | None = None


@dataclass
class MatchEvent:
    """Um evento dentro da partida. Se o provedor não fornece isso
    (ex: football-data.org no plano free), o adaptador simplesmente
    retorna uma lista vazia — o motor de hipóteses decide o que fazer."""
    minute: int
    type: EventType
    team_id: str
    player_id: str | None = None
    detail: str | None = None  # ex: "assistência de X", "pênalti"


@dataclass
class Lineup:
    team_id: str
    starters: list[str] = field(default_factory=list)  # player ids
    bench: list[str] = field(default_factory=list)
    formation: str | None = None  # ex: "4-3-3"


@dataclass
class Match:
    id: str
    competition: str  # ex: "brasileirao_a", "baiano"
    season: str
    date: datetime
    home_team: Team
    away_team: Team
    home_score: int | None = None
    away_score: int | None = None
    status: str = "scheduled"  # scheduled | live | finished
    events: list[MatchEvent] = field(default_factory=list)
    lineups: list[Lineup] = field(default_factory=list)

    @property
    def is_finished(self) -> bool:
        return self.status == "finished"


@dataclass
class StandingRow:
    team_id: str
    position: int
    played: int
    points: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
