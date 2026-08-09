"""
Combina partidas de várias temporadas da mesma competição/provedor
num único conjunto de Match, reaproveitando o mapping já descoberto
e validado — não precisa rodar a descoberta de schema de novo pra
cada temporada, já que é a mesma API com a mesma estrutura.

Isso é o que permite hipóteses como D010 (sequências "quentes/frias")
ou o próprio D006 (casa vs fora) atingirem o tamanho mínimo de
amostra: 2 rodadas de 1 temporada não bastam, mas 3-4 temporadas
inteiras da mesma competição já dão volume suficiente.

Ponto de atenção (não resolvido aqui, documentado): misturar
temporadas dilui a força do padrão se o time mudou muito de elenco
entre uma temporada e outra (rebaixamento, contratações grandes).
Para D006 especificamente isso é aceitável — mando de campo tende a
ser um efeito estrutural (torcida, viagem, familiaridade com o
gramado), não dependente de elenco específico.
"""

from __future__ import annotations

from ..adapters.generic_mapping_adapter import GenericMappingAdapter
from ..capabilities import CapabilityMatrix
from ..models import Match


def combine_seasons(provider: str, competition: str, raw_payloads_by_season: dict[str, dict]) -> list[Match]:
    """raw_payloads_by_season: {"2025": {...json...}, "2024": {...json...}, ...}

    Usa o mapping já salvo em mappings/<provider>.json (gerado antes,
    contra uma das temporadas) para traduzir os registros de TODAS as
    temporadas fornecidas. Não redescobre nada — assume que a mesma
    API mantém a mesma estrutura de campo entre temporadas (checagem
    de sanidade continua rodando por registro, então um registro
    estranho de uma temporada específica ainda seria descartado)."""

    matrix = CapabilityMatrix()
    adapter = GenericMappingAdapter(provider, "http://fake", matrix)

    all_matches: list[Match] = []
    for season, raw in raw_payloads_by_season.items():
        list_path = adapter._mapping["list_path"]
        from ..tools.path_utils import get_by_path

        records = raw if list_path == "$root" else get_by_path(raw, list_path)
        if not records:
            continue

        for record in records:
            match = adapter._record_to_match(record, competition)
            if match is not None:
                match.season = season
                all_matches.append(match)

    return all_matches


def summarize_by_season(matches: list[Match]) -> dict[str, int]:
    """Contagem simples de quantas partidas vieram de cada temporada
    — útil pra checar rapidamente se alguma temporada veio incompleta
    antes de rodar hipóteses em cima do conjunto combinado."""

    counts: dict[str, int] = {}
    for m in matches:
        counts[m.season] = counts.get(m.season, 0) + 1
    return counts
