"""
Utilitários estatísticos pro motor de descobertas.

Isto implementa a segunda camada de proteção contra "descoberta" falsa
que prometemos lá no início: mesmo depois do filtro de amostra mínima
e do filtro de efeito prático (diferença grande o suficiente pra
importar), ainda existe o problema de rodar VÁRIAS hipóteses/times ao
mesmo tempo — mesmo com amostra decente, testar 20 times aumenta a
chance de pelo menos um parecer "significativo" só por acaso.

Benjamini-Hochberg controla isso: em vez de aceitar qualquer p-valor
< 0.05 isoladamente, ele ajusta o limiar de acordo com QUANTOS testes
foram feitos no mesmo lote.
"""

from __future__ import annotations

import math


def two_proportion_p_value(successes_a: int, n_a: int, successes_b: int, n_b: int) -> float:
    """Teste de duas proporções (aproximação normal). Usado pra
    comparar, por exemplo, taxa de vitória em casa vs fora, ou taxa
    de vitória recente vs na temporada inteira.

    Simplificação assumida: trata resultado como binário (vitória ou
    não), não usa os 3 resultados possíveis (vitória/empate/derrota)
    — é uma aproximação razoável pra decidir significância, não uma
    modelagem completa do resultado do jogo."""

    if n_a == 0 or n_b == 0:
        return 1.0

    p_a = successes_a / n_a
    p_b = successes_b / n_b
    p_pool = (successes_a + successes_b) / (n_a + n_b)
    variance = p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b)

    if variance == 0:
        return 1.0

    z = (p_a - p_b) / math.sqrt(variance)
    p_value = 2 * (1 - _standard_normal_cdf(abs(z)))
    return max(0.0, min(1.0, p_value))


def _standard_normal_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def benjamini_hochberg(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    """Retorna uma lista de bool, na MESMA ordem de entrada, indicando
    quais p-valores continuam significativos depois da correção.

    Procedimento padrão: ordena os p-valores, acha o maior rank k tal
    que p_(k) <= (k/m) * alpha, e considera significativos todos os
    p-valores até esse rank (não só os que passariam isoladamente)."""

    m = len(p_values)
    if m == 0:
        return []

    order = sorted(range(m), key=lambda i: p_values[i])
    max_significant_rank = 0

    for rank, idx in enumerate(order, start=1):
        threshold = (rank / m) * alpha
        if p_values[idx] <= threshold:
            max_significant_rank = rank

    significant = [False] * m
    for rank, idx in enumerate(order, start=1):
        significant[idx] = rank <= max_significant_rank

    return significant
