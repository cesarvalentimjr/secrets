"""
Exemplo de uso ponta a ponta, com o pipeline atual.

Isto substitui a versão antiga deste arquivo, que usava adaptadores
escritos à mão (ApiFutebolAdapter, TheSportsDBAdapter) — removidos
porque o GenericMappingAdapter faz o trabalho deles automaticamente
a partir de qualquer API, sem código específico por provedor.

Rode isto depois de preencher bootstrap.py com suas APIs (tokens
inclusos, quando a API exigir).
"""

from datetime import date

from .hypotheses.publisher import format_batch
from .hypotheses.run_all_hypotheses import run_daily_discoveries
from .tools.bootstrap import ProviderSpec, bootstrap_registry

# 1. Descreva os provedores — sem escrever nenhuma classe de adaptador.
specs = [
    ProviderSpec(
        provider="thesportsdb",
        url="https://www.thesportsdb.com/api/v1/json/123/eventsseason.php?id=4351&s=2025",
        competition="brasileirao_a",
    ),
    # Descomente e preencha o token quando cadastrar na API Futebol:
    # ProviderSpec(
    #     provider="api_futebol",
    #     url="https://api.api-futebol.com.br/v1/campeonatos/10/partidas",
    #     competition="brasileirao_a",
    #     headers={"Authorization": "Bearer SEU_TOKEN_AQUI"},
    # ),
]

# 2. Monta a Registry — descobre schema, mapeia, valida e deriva
#    capacidades automaticamente pra cada provedor.
registry = bootstrap_registry(specs)

# 3. Busca dados normalizados — o motor de hipóteses nunca sabe de
#    qual API isso veio.
matches = registry.get_matches("brasileirao_a", date(2025, 1, 1), date.today())
standings = registry.get_standings("brasileirao_a", "2025")

# 4. Roda as 4 hipóteses disponíveis + correção estatística em lote,
#    e mostra só o que sobrou depois dos dois filtros (efeito prático
#    e significância ajustada).
discoveries = run_daily_discoveries(matches, standings)
print(format_batch(discoveries))
