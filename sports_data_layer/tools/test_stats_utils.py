from ..tools.stats_utils import benjamini_hochberg, two_proportion_p_value


def test_proporcoes_iguais_tem_p_valor_alto():
    """Times com a mesma taxa de vitória não devem parecer diferentes."""
    p = two_proportion_p_value(5, 10, 5, 10)
    assert p > 0.9


def test_proporcoes_muito_diferentes_com_amostra_grande_tem_p_valor_baixo():
    p = two_proportion_p_value(90, 100, 10, 100)
    assert p < 0.01


def test_amostra_zero_nao_lanca_excecao():
    assert two_proportion_p_value(0, 0, 5, 10) == 1.0


def test_benjamini_hochberg_rejeita_menos_que_o_limiar_ingenuo():
    """Exemplo clássico: com 10 testes, um p-valor de 0.04 passaria no
    limiar ingênuo (< 0.05) mas NÃO deve passar depois da correção,
    porque estamos testando 10 coisas ao mesmo tempo."""
    p_values = [0.001, 0.04, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    significant = benjamini_hochberg(p_values, alpha=0.05)

    assert significant[0] is True   # 0.001 é claramente significativo mesmo após correção
    assert significant[1] is False  # 0.04 sozinho passaria, mas não no lote de 10


def test_benjamini_hochberg_lista_vazia_nao_lanca_excecao():
    assert benjamini_hochberg([]) == []


def test_benjamini_hochberg_mantem_ordem_de_entrada():
    """O resultado deve corresponder índice a índice com a entrada,
    não vir reordenado por p-valor."""
    p_values = [0.5, 0.001, 0.9]
    significant = benjamini_hochberg(p_values, alpha=0.05)
    assert significant[1] is True   # o menor p-valor, na posição 1
    assert significant[0] is False
    assert significant[2] is False
