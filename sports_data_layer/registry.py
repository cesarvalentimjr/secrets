"""
Registry / Facade da camada de dados.

Este é o único objeto que o motor de hipóteses deve importar. Ele:
  1. Sabe qual provedor usar para cada competição (via config).
  2. Cacheia respostas para não estourar rate limit dos free tiers.
  3. Faz fallback para um segundo provedor se o primeiro falhar ou
     não tiver a capacidade necessária.
  4. Expõe get_matches/get_standings com a MESMA assinatura não importa
     o provedor por trás — trocar provedor não muda uma linha do motor.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from .capabilities import Capability
from .interfaces import SportsDataProvider
from .models import Match, StandingRow


@dataclass
class ProviderConfig:
    """Define, por competição, qual provedor é o principal e qual é
    o fallback. Isso vem de um arquivo de config (yaml/json/env), não
    fica hardcoded no código — é a peça que te dá liberdade de trocar
    de provedor sem deploy de código novo."""

    primary_by_competition: dict[str, str]           # ex: {"brasileirao_a": "api_futebol"}
    fallback_by_competition: dict[str, str] = field(default_factory=dict)


class SimpleTTLCache:
    """Cache em memória bem simples. Trocar por Redis é trivial —
    a interface (get/set) é o que importa, não a implementação."""

    def __init__(self, ttl_seconds: int = 3600):
        self._ttl = timedelta(seconds=ttl_seconds)
        self._store: dict[str, tuple[object, date]] = {}

    def get(self, key: str):
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if date.today() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value) -> None:
        self._store[key] = (value, date.today() + self._ttl)


class SportsDataRegistry:
    """Facade única usada pelo motor de hipóteses."""

    def __init__(
        self,
        providers: dict[str, SportsDataProvider],
        config: ProviderConfig,
        cache: SimpleTTLCache | None = None,
    ):
        self._providers = providers
        self._config = config
        self._cache = cache or SimpleTTLCache()

    def get_matches(self, competition: str, date_from: date, date_to: date) -> list[Match]:
        cache_key = f"matches:{competition}:{date_from}:{date_to}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        for provider in self._providers_for(competition):
            try:
                matches = provider.get_matches(competition, date_from, date_to)
                if matches:
                    self._cache.set(cache_key, matches)
                    return matches
            except Exception:
                continue  # tenta o próximo provedor da lista de fallback

        return []

    def get_standings(self, competition: str, season: str) -> list[StandingRow]:
        cache_key = f"standings:{competition}:{season}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        for provider in self._providers_for(competition):
            try:
                standings = provider.get_standings(competition, season)
                if standings:
                    self._cache.set(cache_key, standings)
                    return standings
            except Exception:
                continue

        return []

    def supports(self, competition: str, capability: Capability) -> bool:
        """O motor de hipóteses chama isto ANTES de tentar uma hipótese
        que dependa de dado raro (lineups, eventos por minuto)."""
        for provider in self._providers_for(competition):
            if provider.supports(capability, competition):
                return True
        return False

    def _providers_for(self, competition: str) -> list[SportsDataProvider]:
        """Retorna [principal, fallback] na ordem de tentativa."""
        names = [self._config.primary_by_competition.get(competition)]
        fallback = self._config.fallback_by_competition.get(competition)
        if fallback:
            names.append(fallback)
        return [self._providers[n] for n in names if n and n in self._providers]
