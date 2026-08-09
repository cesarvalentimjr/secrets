"""
Testes de regressão do pipeline autônomo.

Os dois primeiros testes existem porque bugs reais já aconteceram
durante o desenvolvimento:
  - test_home_score_nao_e_confundido_com_nome_do_time: a primeira
    versão da heurística confundia "placar_mandante" com o conceito
    de nome do time, por causa do substring "mandante" compartilhado.
  - test_campo_aninhado_legitimo_nao_cai_em_quarentena: o limiar de
    confiança 0.7 rejeitava injustamente "time_mandante.nome_popular"
    por ter tokens estruturais extras.

Rodar com: pytest tests/ -v
"""

import shutil
from pathlib import Path

import pytest

from ..tools.auto_mapper import apply_sanity_gate, build_and_save_mapping, propose_mapping, split_by_confidence
from ..tools.path_utils import find_record_list, get_by_path
from ..tools.schema_discovery import inspect_json
from ..tools.validators import passes_sanity_check

SAMPLE_MATCH_PT = {
    "partida_id": 1001,
    "data_realizacao_iso": "2026-08-01T20:00:00",
    "status": "encerrada",
    "placar_mandante": 2,
    "placar_visitante": 1,
    "time_mandante": {"id": 10, "nome_popular": "Bahia"},
    "time_visitante": {"id": 20, "nome_popular": "Vitoria"},
}

SAMPLE_MATCH_EN = {
    "idEvent": "600001",
    "dateEvent": "2026-08-01",
    "strHomeTeam": "Bahia",
    "strAwayTeam": "Vitoria",
    "intHomeScore": "2",
    "intAwayScore": "1",
}


@pytest.fixture(autouse=True)
def _clean_generated_dirs():
    """Cada teste começa sem mappings/quarentena de execuções anteriores."""
    for d in ("mappings", "quarantine", "schema_snapshots"):
        shutil.rmtree(d, ignore_errors=True)
    yield
    for d in ("mappings", "quarantine", "schema_snapshots"):
        shutil.rmtree(d, ignore_errors=True)


def _mapping_of(raw_record: dict) -> dict[str, str]:
    fields = inspect_json(raw_record)
    proposals = propose_mapping(fields)
    sane, _ = apply_sanity_gate(proposals)
    auto_applied, _ = split_by_confidence(sane)
    return {concept: c.path for concept, c in auto_applied.items()}


def test_home_score_nao_e_confundido_com_nome_do_time():
    """Regressão: 'placar_mandante' não deve virar home_team_name só
    por compartilhar o token 'mandante' com 'time_mandante.nome_popular'."""
    mapping = _mapping_of(SAMPLE_MATCH_PT)
    assert mapping["home_score"] == "placar_mandante"
    assert mapping["home_team_name"] == "time_mandante.nome_popular"
    assert mapping["home_score"] != mapping["home_team_name"]


def test_campo_aninhado_legitimo_nao_cai_em_quarentena():
    """Regressão: nomes aninhados normais (2 níveis) devem ser aplicados,
    não descartados por confiança calculada sobre o caminho inteiro."""
    mapping = _mapping_of(SAMPLE_MATCH_PT)
    assert "home_team_name" in mapping
    assert "away_team_name" in mapping


def test_heuristica_generaliza_para_formato_em_ingles():
    """O mesmo motor de assinaturas deve funcionar tanto pro formato em
    português (API Futebol) quanto no formato em inglês (TheSportsDB),
    sem nenhum código específico de idioma."""
    mapping = _mapping_of(SAMPLE_MATCH_EN)
    assert mapping["home_team_name"] == "strHomeTeam"
    assert mapping["away_team_name"] == "strAwayTeam"
    assert mapping["home_score"] == "intHomeScore"


def test_valor_implausivel_e_colocado_em_quarentena_mesmo_com_nome_perfeito():
    """Segunda camada de defesa: mesmo que o NOME do campo bata
    perfeitamente com a assinatura, um valor implausível deve
    impedir a aplicação automática."""
    fake_record = {**SAMPLE_MATCH_PT, "placar_mandante": "Bahia"}  # nome bate, valor não faz sentido
    fields = inspect_json(fake_record)
    proposals = propose_mapping(fields)
    sane, quarantined = apply_sanity_gate(proposals)
    quarantined_paths = {c.path for c in quarantined}
    assert "placar_mandante" in quarantined_paths


def test_pipeline_completo_nunca_lanca_excecao_por_ambiguidade(tmp_path, monkeypatch):
    """Garantia central da autonomia: rodar o pipeline completo sobre
    dados reais nunca deve exigir intervenção — na pior hipótese,
    campos ficam de fora do mapping, mas a função sempre retorna."""
    monkeypatch.chdir(tmp_path)
    raw_response = {"resultados": [SAMPLE_MATCH_PT]}
    result = build_and_save_mapping("teste_ci", raw_response)
    assert result["mapeados_automaticamente"] > 0
    assert Path(result["mapping_path"]).exists()


def test_capacidades_refletem_apenas_o_que_foi_validado(tmp_path, monkeypatch):
    """A CapabilityMatrix não deve declarar uma capacidade se os
    conceitos que ela exige não sobreviveram à confiança + sanidade."""
    from ..adapters.generic_mapping_adapter import capabilities_from_mapping
    from ..capabilities import Capability

    monkeypatch.chdir(tmp_path)
    # Resposta deliberadamente sem dados de tabela/classificação (só partidas)
    build_and_save_mapping("teste_capacidades", {"resultados": [SAMPLE_MATCH_PT]})
    caps = capabilities_from_mapping("teste_capacidades")
    assert Capability.BASIC_RESULTS in caps
    assert Capability.STANDINGS not in caps  # não há pontos/vitórias/empates nesta amostra


def test_singular_e_plural_ambos_reconhecidos(tmp_path, monkeypatch):
    """Regressão real: TheSportsDB usa 'intWin'/'intDraw'/'intLoss' (singular),
    não 'wins'/'draws'/'losses' (plural). A primeira versão das assinaturas só
    reconhecia o plural e isso zerava a capacidade de STANDINGS silenciosamente
    — só foi descoberto testando contra a tabela real do Brasileirão."""
    from ..adapters.generic_mapping_adapter import capabilities_from_mapping
    from ..capabilities import Capability

    monkeypatch.chdir(tmp_path)
    standings_singular = {
        "table": [
            {
                "idTeam": "134287",
                "idLeague": "4351",
                "intWin": "23",
                "intDraw": "10",
                "intLoss": "5",
                "intGoalsFor": "78",
                "intGoalsAgainst": "27",
                "intPoints": "79",
            }
        ]
    }
    build_and_save_mapping("teste_singular", standings_singular)
    caps = capabilities_from_mapping("teste_singular")
    assert Capability.STANDINGS in caps


def test_get_by_path_nao_lanca_excecao_para_caminho_ausente():
    """A extração de dado nunca deve quebrar o lote por causa de um
    campo ausente em um registro específico — deve retornar None."""
    assert get_by_path(SAMPLE_MATCH_PT, "time_mandante.nome_popular") == "Bahia"
    assert get_by_path(SAMPLE_MATCH_PT, "campo_que_nao_existe.sub_campo") is None
    assert get_by_path({}, "qualquer.coisa") is None


def test_find_record_list_acha_lista_aninhada():
    raw = {"meta": {"pagina": 1}, "resultados": [SAMPLE_MATCH_PT]}
    path, records = find_record_list(raw)
    assert path == "resultados"
    assert records == [SAMPLE_MATCH_PT]


@pytest.mark.parametrize(
    "concept,value,esperado",
    [
        ("home_score", "2", True),
        ("home_score", "99", False),       # placar impossível
        ("home_score", "Bahia", False),    # nem é número
        ("match_date", "2026-08-01", True),
        ("match_date", "não é uma data", False),
        ("home_team_name", "Bahia", True),
        ("home_team_name", "12345", False),  # nome não pode ser só número
    ],
)
def test_validadores_de_sanidade(concept, value, esperado):
    assert passes_sanity_check(concept, value) is esperado
