"""
Adaptador genérico: uma única classe que serve qualquer provedor,
desde que exista um mapping/<provider>.json gerado pelo auto_mapper.

Isso elimina a necessidade de escrever ApiFutebolAdapter,
TheSportsDBAdapter, etc. na mão. Descobriu uma API nova? Roda o
schema_discovery + auto_mapper nela, e o GenericMappingAdapter já
sabe extrair dados — usando só os caminhos salvos no JSON de mapping.

Conceitos ausentes do mapping (por baixa confiança ou reprovados na
sanidade) simplesmente resultam em campos None no Match — nunca em
exceção. A camada de capacidades (capabilities_from_mapping) é quem
informa ao motor de hipóteses o que está e o que não está disponível.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import requests

from ..capabilities import Capability, CapabilityMatrix
from ..interfaces import SportsDataProvider
from ..models import Match, StandingRow, Team
from ..tools.path_utils import get_by_path

MAPPING_DIR = Path("mappings")

# Quais conceitos, se presentes no mapping, habilitam qual capacidade.
CAPABILITY_REQUIREMENTS: dict[Capability, set[str]] = {
    Capability.BASIC_RESULTS: {"match_id", "home_team_name", "away_team_name", "match_date"},
    Capability.STANDINGS: {"points", "wins", "draws", "losses"},
    Capability.MATCH_EVENTS: {"event_minute", "event_type"},
}


def capabilities_from_mapping(provider: str) -> set[Capability]:
    """Deriva automaticamente quais capacidades este provedor tem,
    olhando só pro que sobreviveu à confiança + sanidade no mapping
    salvo. Zero decisão humana — é 100% função do que foi validado
    automaticamente."""

    mapping_path = MAPPING_DIR / f"{provider}.json"
    if not mapping_path.exists():
        return set()

    mapped_concepts = set(json.loads(mapping_path.read_text())["fields"].keys())
    return {
        capability
        for capability, required in CAPABILITY_REQUIREMENTS.items()
        if required.issubset(mapped_concepts)
    }


def register_autonomous_provider(
    provider: str, competition: str, capability_matrix: CapabilityMatrix
) -> None:
    """Chamado pelo pipeline autônomo depois de gerar/atualizar o
    mapping. Preenche a CapabilityMatrix automaticamente — nenhuma
    linha de config escrita à mão."""

    capability_matrix.declare(provider, competition, capabilities_from_mapping(provider))


class GenericMappingAdapter(SportsDataProvider):
    """Um único adaptador para todos os provedores autônomos."""

    def __init__(self, provider_name: str, base_url: str, capability_matrix: CapabilityMatrix, headers: dict | None = None):
        self.name = provider_name
        self._base_url = base_url
        self._headers = headers or {}
        self._capabilities = capability_matrix
        self._mapping = self._load_mapping()

    def _load_mapping(self) -> dict:
        path = MAPPING_DIR / f"{self.name}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Nenhum mapping encontrado para '{self.name}'. "
                "Rode o pipeline autônomo (autonomous_pipeline.py) primeiro."
            )
        return json.loads(path.read_text())

    def _field_path(self, concept: str) -> str | None:
        return self._mapping["fields"].get(concept, {}).get("path")

    def _extract(self, record: dict, concept: str):
        path = self._field_path(concept)
        return get_by_path(record, path) if path else None

    def get_matches(self, competition: str, date_from: date, date_to: date) -> list[Match]:
        resp = requests.get(f"{self._base_url}", headers=self._headers, timeout=15)
        resp.raise_for_status()
        raw = resp.json()

        list_path = self._mapping["list_path"]
        records = raw if list_path == "$root" else get_by_path(raw, list_path)
        if not records:
            return []

        matches = []
        for record in records:
            match = self._record_to_match(record, competition)
            if match is None:
                continue
            if match.date and date_from <= match.date.date() <= date_to:
                matches.append(match)
        return matches

    def get_match_detail(self, match_id: str) -> Match:
        raise NotImplementedError("Endpoint de detalhe precisa de mapping próprio — não coberto no MVP autônomo.")

    def get_standings(self, competition: str, season: str) -> list[StandingRow]:
        resp = requests.get(f"{self._base_url}", headers=self._headers, timeout=15)
        resp.raise_for_status()
        raw = resp.json()

        list_path = self._mapping["list_path"]
        records = raw if list_path == "$root" else get_by_path(raw, list_path)
        if not records:
            return []

        rows = []
        for record in records:
            team_id = self._extract(record, "team_id")
            points = self._extract(record, "points")
            if team_id is None or points is None:
                continue  # campo em quarentena ou ausente — pula o registro, não quebra o lote
            rows.append(
                StandingRow(
                    team_id=str(team_id),
                    position=len(rows) + 1,
                    played=0,
                    points=int(points),
                    wins=int(self._extract(record, "wins") or 0),
                    draws=int(self._extract(record, "draws") or 0),
                    losses=int(self._extract(record, "losses") or 0),
                    goals_for=int(self._extract(record, "goals_for") or 0),
                    goals_against=int(self._extract(record, "goals_against") or 0),
                )
            )
        return rows

    def supports(self, capability: Capability, competition: str) -> bool:
        return self._capabilities.supports(self.name, competition, capability)

    def _record_to_match(self, record: dict, competition: str) -> Match | None:
        home_name = self._extract(record, "home_team_name")
        away_name = self._extract(record, "away_team_name")
        match_id = self._extract(record, "match_id")
        raw_date = self._extract(record, "match_date")

        if not (home_name and away_name and match_id):
            return None  # dados essenciais em quarentena/ausentes — registro descartado, não quebra o lote

        parsed_date = self._parse_date(raw_date) if raw_date else None
        home_id = str(self._extract(record, "home_team_id") or f"unk_{home_name}")
        away_id = str(self._extract(record, "away_team_id") or f"unk_{away_name}")

        return Match(
            id=str(match_id),
            competition=competition,
            season="",
            date=parsed_date,
            home_team=Team(id=home_id, name=str(home_name)),
            away_team=Team(id=away_id, name=str(away_name)),
            home_score=self._safe_int(self._extract(record, "home_score")),
            away_score=self._safe_int(self._extract(record, "away_score")),
            status=str(self._extract(record, "status") or "scheduled"),
        )

    @staticmethod
    def _safe_int(value) -> int | None:
        try:
            return int(value) if value is not None else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_date(raw: str) -> datetime | None:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(raw[: len(fmt) + 2], fmt)
            except (ValueError, TypeError):
                continue
        return None
