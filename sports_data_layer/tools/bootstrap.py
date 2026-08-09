"""
Bootstrap: monta a SportsDataRegistry inteira a partir de uma lista de
provedores autônomos, sem nenhum passo manual. É este objeto que o
motor de hipóteses (D001-D1500) importa — ele nunca vê schema
discovery, mapping, nem adaptadores concretos.

Rodar isto uma vez por dia (cron) atualiza os mappings de todos os
provedores, deriva capacidades de novo, e devolve uma Registry fresca.
Se um provedor mudar de schema entre uma execução e outra, o log em
INFO mostra exatamente o que mudou (ver 'mudou_desde_ultima_vez' em
auto_mapper.build_and_save_mapping) — não precisa monitorar nada
manualmente, mas fica registrado pra auditoria se você quiser olhar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..capabilities import CapabilityMatrix
from ..registry import ProviderConfig, SimpleTTLCache, SportsDataRegistry
from .autonomous_pipeline import run_autonomous_ingestion

logger = logging.getLogger("bootstrap")


@dataclass
class ProviderSpec:
    provider: str
    url: str
    competition: str
    headers: dict | None = None
    is_fallback_for: str | None = None  # nome do provedor principal, se este for o fallback


def bootstrap_registry(specs: list[ProviderSpec], cache_ttl_seconds: int = 3600) -> SportsDataRegistry:
    """Ponto de entrada único do pipeline autônomo. Processa cada
    provedor (descoberta + mapeamento + capacidades), monta os
    adaptadores, e devolve a Registry pronta. Provedores que falharem
    são logados e simplesmente excluídos da Registry — não derrubam
    os outros nem travam a inicialização."""

    capability_matrix = CapabilityMatrix()
    providers = {}
    primary_by_competition: dict[str, str] = {}
    fallback_by_competition: dict[str, str] = {}

    for spec in specs:
        try:
            adapter = run_autonomous_ingestion(
                spec.provider, spec.url, spec.competition, capability_matrix, spec.headers
            )
            providers[spec.provider] = adapter

            if spec.is_fallback_for:
                fallback_by_competition[spec.competition] = spec.provider
            else:
                primary_by_competition[spec.competition] = spec.provider

        except Exception:
            logger.exception("Provedor '%s' falhou na inicialização autônoma — excluído desta rodada.", spec.provider)

    config = ProviderConfig(
        primary_by_competition=primary_by_competition,
        fallback_by_competition=fallback_by_competition,
    )
    return SportsDataRegistry(providers=providers, config=config, cache=SimpleTTLCache(cache_ttl_seconds))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    specs = [
        ProviderSpec(
            provider="thesportsdb",
            url="https://www.thesportsdb.com/api/v1/json/123/eventsseason.php?id=4351&s=2025",
            competition="brasileirao_a",
        ),
        # Descomente quando tiver o token da API Futebol (cadastro em
        # https://ct.api-futebol.com.br/cadastrar). Ela vira o provedor
        # PRINCIPAL, e a TheSportsDB acima passa a ser o fallback —
        # troque o "is_fallback_for" de lugar quando isso acontecer.
        #
        # ProviderSpec(
        #     provider="api_futebol",
        #     url="https://api.api-futebol.com.br/v1/campeonatos/10/partidas",
        #     competition="brasileirao_a",
        #     headers={"Authorization": "Bearer SEU_TOKEN_AQUI"},
        # ),
    ]

    registry = bootstrap_registry(specs)
    print("Registry pronta. Provedores ativos:", list(registry._providers.keys()))
