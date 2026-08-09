"""
Frontend Streamlit do motor de descobertas.

Roda no Streamlit Cloud, onde o servidor tem acesso de rede livre —
diferente do ambiente de chat, aqui não existe a restrição de "só
acesso URLs que já vi antes". Isso resolve o problema real: buscar
qualquer temporada, de qualquer ano, direto pelo botão.
"""

from __future__ import annotations

import time

import requests
import streamlit as st

from sports_data_layer.adapters.generic_mapping_adapter import (
    GenericMappingAdapter,
    capabilities_from_mapping,
)
from sports_data_layer.capabilities import CapabilityMatrix
from sports_data_layer.hypotheses.run_all_hypotheses import run_daily_discoveries
from sports_data_layer.models import StandingRow
from sports_data_layer.tools.auto_mapper import build_and_save_mapping
from sports_data_layer.tools.multi_season import summarize_by_season

st.set_page_config(page_title="Motor de Descobertas — Brasileirão", layout="wide")

LEAGUE_ID = "4351"
API_KEY = "123"
EVENTS_URL = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/eventsseason.php"
ROUND_URL = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/eventsround.php"
TABLE_URL = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/lookuptable.php"
PROVIDER_NAME = "thesportsdb_streamlit"
COMPETITION = "brasileirao_a"
MAX_ROUNDS = 42  # Brasileirão tem 38, +margem para copas/reagendamentos


# ---------------------------------------------------------------------------
# Busca de dados (roda no servidor do Streamlit Cloud — sem a trava do chat)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def fetch_season(year: int) -> dict | None:
    """Chamada única pra temporada inteira. O plano gratuito da
    TheSportsDB trunca essa resposta (documentado: 'Free Limit: 1'
    contra 'Premium Limit: 500' nesse endpoint) — por isso isto é só
    o caminho rápido; fetch_season_complete() abaixo é quem garante
    a temporada inteira, buscando rodada por rodada."""

    for season_param in (str(year), f"{year}-{year + 1}"):
        try:
            resp = requests.get(EVENTS_URL, params={"id": LEAGUE_ID, "s": season_param}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            continue
        if data.get("events"):
            return data
    return None


@st.cache_data(show_spinner=False)
def fetch_season_complete(year: int, progress_callback=None) -> dict | None:
    """Contorna o truncamento do plano gratuito buscando rodada por
    rodada (eventsround.php?id=...&r=N&s=...) — cada chamada devolve
    só ~10 jogos, abaixo do limite que trunca a chamada de temporada
    inteira. Deduplica por idEvent (algumas rodadas reagendadas
    aparecem repetidas com IDs diferentes de partida, então a
    deduplicação é por ID, não por rodada)."""

    all_events: dict[str, dict] = {}  # idEvent -> registro, pra deduplicar

    for season_param in (str(year), f"{year}-{year + 1}"):
        got_any = False
        for round_num in range(1, MAX_ROUNDS + 1):
            try:
                resp = requests.get(
                    ROUND_URL, params={"id": LEAGUE_ID, "r": round_num, "s": season_param}, timeout=15
                )
                resp.raise_for_status()
                data = resp.json()
            except (requests.RequestException, ValueError):
                continue

            events = data.get("events") or []
            if events:
                got_any = True
                for e in events:
                    all_events[e["idEvent"]] = e

            if progress_callback:
                progress_callback(round_num, MAX_ROUNDS)
            time.sleep(0.25)  # gentil com o limite de 30 req/min do plano gratuito

        if got_any:
            break  # esse formato de temporada (ano único vs ano-ano) funcionou, não tenta o outro

    if not all_events:
        return None
    return {"events": list(all_events.values())}


@st.cache_data(show_spinner=False)
def fetch_standings(year: int) -> dict | None:
    try:
        resp = requests.get(TABLE_URL, params={"l": LEAGUE_ID, "s": str(year)}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return None
    return data if data.get("table") else None


def load_matches(raw_payloads: dict[int, dict]) -> list:
    """Usa o mapping já validado (gerado contra a primeira temporada
    disponível) pra extrair Match de todas as temporadas buscadas."""

    first_year = min(raw_payloads)
    build_and_save_mapping(PROVIDER_NAME, raw_payloads[first_year])

    matrix = CapabilityMatrix()
    adapter = GenericMappingAdapter(PROVIDER_NAME, EVENTS_URL, matrix)

    all_matches = []
    for year, raw in raw_payloads.items():
        for record in raw["events"]:
            match = adapter._record_to_match(record, COMPETITION)
            if match:
                match.season = str(year)
                all_matches.append(match)
    return all_matches


def load_standings(raw_table: dict) -> list[StandingRow]:
    """A tabela de classificação tem um formato de resposta diferente
    das partidas (lista de times, não de jogos) — por isso precisa
    do seu próprio mapeamento, gerado a partir do JSON da tabela em
    si, não reaproveitado do mapeamento de partidas."""

    table_provider = f"{PROVIDER_NAME}_table"
    build_and_save_mapping(table_provider, raw_table)

    matrix = CapabilityMatrix()
    adapter = GenericMappingAdapter(table_provider, TABLE_URL, matrix)
    rows = []
    for i, record in enumerate(raw_table["table"], start=1):
        team_id = adapter._extract(record, "team_id")
        points = adapter._extract(record, "points")
        if team_id is None or points is None:
            continue
        wins = int(adapter._extract(record, "wins") or 0)
        draws = int(adapter._extract(record, "draws") or 0)
        losses = int(adapter._extract(record, "losses") or 0)
        rows.append(
            StandingRow(
                team_id=str(team_id),
                position=i,
                played=wins + draws + losses,  # calculado, não depende de um campo "played" mapeado
                points=int(points),
                wins=wins,
                draws=draws,
                losses=losses,
                goals_for=int(adapter._extract(record, "goals_for") or 0),
                goals_against=int(adapter._extract(record, "goals_against") or 0),
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

st.title("⚽ Motor de Descobertas — Brasileirão Série A")
st.caption(
    "Busca dados reais da TheSportsDB, mapeia os campos automaticamente, "
    "e roda o motor de hipóteses com correção estatística por lote."
)

with st.sidebar:
    st.header("Configuração")
    start_year, end_year = st.slider("Intervalo de temporadas", 2014, 2026, (2021, 2026))
    fetch_table = st.checkbox("Buscar tabela de classificação da última temporada", value=True)
    st.caption(
        "A busca é feita rodada por rodada (não temporada inteira de uma vez), "
        "porque o plano gratuito trunca a resposta da temporada completa. "
        "Isso significa ~40 chamadas por temporada — pode levar 1-2 minutos "
        "pra um intervalo grande, especialmente na primeira vez (depois fica em cache)."
    )
    run_button = st.button("🔄 Buscar dados e rodar o motor", type="primary")

if "raw_payloads" not in st.session_state:
    st.session_state.raw_payloads = {}

if run_button:
    years = list(range(start_year, end_year + 1))
    raw_payloads = {}
    season_progress = st.progress(0.0, text="Iniciando busca...")
    round_progress = st.empty()

    for i, year in enumerate(years):
        season_progress.progress(i / len(years), text=f"Temporada {year} ({i + 1}/{len(years)})...")

        def _report_round(round_num: int, max_rounds: int, _year=year):
            round_progress.progress(
                round_num / max_rounds, text=f"  Temporada {_year}: rodada {round_num}/{max_rounds}"
            )

        data = fetch_season_complete(year, progress_callback=_report_round)
        if data:
            raw_payloads[year] = data

    season_progress.empty()
    round_progress.empty()
    st.session_state.raw_payloads = raw_payloads

    if not raw_payloads:
        st.error("Nenhuma temporada retornou dados. Verifique o intervalo escolhido.")
    else:
        found = sorted(raw_payloads.keys())
        missing = sorted(set(years) - set(found))
        counts = {y: len(raw_payloads[y]["events"]) for y in found}
        st.success(f"{len(found)} de {len(years)} temporadas encontradas: {counts}")
        if missing:
            st.warning(f"Sem dados para: {missing}")

raw_payloads = st.session_state.raw_payloads

if raw_payloads:
    matches = load_matches(raw_payloads)
    per_season = summarize_by_season(matches)

    col1, col2, col3 = st.columns(3)
    col1.metric("Partidas carregadas", len(matches))
    col2.metric("Temporadas", len(raw_payloads))
    col3.metric("Times distintos", len({m.home_team.id for m in matches} | {m.away_team.id for m in matches}))

    st.subheader("Partidas por temporada")
    st.bar_chart(per_season)

    standings = []
    if fetch_table:
        latest_year = max(raw_payloads)
        raw_table = fetch_standings(latest_year)
        if raw_table:
            standings = load_standings(raw_table)
            st.caption(f"Tabela de classificação de {latest_year}: {len(standings)} times carregados.")
        else:
            st.caption(f"Não consegui buscar a tabela de {latest_year} — hipóteses de faixa de tabela ficarão sem dado.")

    st.subheader("🔍 Descobertas")
    with st.spinner("Rodando as 4 hipóteses + correção estatística..."):
        discoveries = run_daily_discoveries(matches, standings)

    if not discoveries:
        st.info(
            "Nenhuma descoberta passou nos dois filtros (efeito prático + significância "
            "estatística ajustada) com os dados atuais. Isso é esperado se o intervalo "
            "de temporadas for pequeno — aumente o intervalo na barra lateral."
        )
    else:
        for d in discoveries:
            with st.container(border=True):
                st.markdown(f"**{d.title}**")
                st.write(d.detail)
                st.caption(f"Amostra: {d.sample_size} jogos · código interno: {d.code}")

    with st.expander("Diagnóstico técnico (mapeamento automático de campos)"):
        st.json(capabilities_from_mapping(PROVIDER_NAME))
else:
    st.info("Configure o intervalo de temporadas na barra lateral e clique em buscar.")
