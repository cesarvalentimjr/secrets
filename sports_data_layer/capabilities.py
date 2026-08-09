"""
Capacidades por provedor.

Este é o pedaço mais importante pro seu caso de uso: nem todo provedor
gratuito entrega a mesma profundidade de dado (lineups, eventos por
minuto, estatísticas de partida). Em vez de o motor de hipóteses
descobrir isso na marra (erro em runtime, dado ausente silencioso),
cada adaptador declara o que sabe fazer. O motor consulta isso ANTES
de tentar rodar uma hipótese que dependa de dado que o provedor atual
não tem para aquela competição.

Exemplo de uso no motor de hipóteses:

    if provider.supports(Capability.LINEUPS, competition="baiano"):
        run_hypothesis_d008(...)  # reserva vs titular
    else:
        skip_with_reason("D008 requer lineups, indisponível no Baiano via este provedor")
"""

from enum import Enum, auto


class Capability(Enum):
    BASIC_RESULTS = auto()       # placar, data, mando de campo
    STANDINGS = auto()           # tabela de classificação
    MATCH_EVENTS = auto()        # gols/cartões com minuto
    LINEUPS = auto()             # escalação titular/reserva
    SUBSTITUTIONS = auto()       # trocas com minuto
    PLAYER_SEASON_STATS = auto() # estatísticas agregadas de jogador na temporada
    ODDS = auto()                # odds de mercado
    LIVE_UPDATES = auto()        # dados em tempo real (não delayed)


class CapabilityMatrix:
    """Mapa provedor -> competição -> capacidades disponíveis.

    Isso é intencionalmente granular por competição, porque na prática
    a mesma API costuma ter dado bom pra Série A e dado pobre pra
    Série C ou pra um estadual. Você vai precisar popular isso na mão
    testando as chamadas reais (ver plano de validação que já discutimos).
    """

    def __init__(self):
        self._matrix: dict[str, dict[str, set[Capability]]] = {}

    def declare(self, provider_name: str, competition: str, capabilities: set[Capability]) -> None:
        self._matrix.setdefault(provider_name, {})[competition] = capabilities

    def supports(self, provider_name: str, competition: str, capability: Capability) -> bool:
        return capability in self._matrix.get(provider_name, {}).get(competition, set())

    def capabilities_for(self, provider_name: str, competition: str) -> set[Capability]:
        return self._matrix.get(provider_name, {}).get(competition, set())
