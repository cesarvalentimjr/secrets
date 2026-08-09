"""
Validação de sanidade automática.

Mesmo um mapeamento com confiança alta (nome do campo bate perfeito
com a assinatura) pode estar errado — nomes de campo mentem às vezes.
Esta camada checa o VALOR de exemplo contra o que é fisicamente
plausível para aquele conceito. É o que permite o pipeline rodar sem
nenhuma revisão humana: se o valor não faz sentido, o campo é
descartado automaticamente, sem perguntar pra ninguém.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime

DATE_FORMATS = ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"]


def _is_int_in_range(value: str, low: int, high: int) -> bool:
    try:
        n = int(float(value))
    except (ValueError, TypeError):
        return False
    return low <= n <= high


def _is_parseable_date(value: str) -> bool:
    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(value, fmt)
            return True
        except (ValueError, TypeError):
            continue
    return False


def _is_plausible_name(value: str, min_len: int = 2, max_len: int = 60) -> bool:
    if not isinstance(value, str):
        return False
    if not (min_len <= len(value) <= max_len):
        return False
    return not value.strip().isdigit()  # nome não deve ser só número


def _is_short_code(value: str, max_len: int = 20) -> bool:
    return isinstance(value, str) and 0 < len(value) <= max_len


# Um validador por conceito. Se o conceito não tiver validador aqui,
# ele passa sem checagem extra (conta só a confiança do nome do campo).
CONCEPT_VALIDATORS: dict[str, Callable[[str], bool]] = {
    "home_score": lambda v: _is_int_in_range(v, 0, 20),
    "away_score": lambda v: _is_int_in_range(v, 0, 20),
    "points": lambda v: _is_int_in_range(v, 0, 200),
    "wins": lambda v: _is_int_in_range(v, 0, 60),
    "draws": lambda v: _is_int_in_range(v, 0, 60),
    "losses": lambda v: _is_int_in_range(v, 0, 60),
    "goals_for": lambda v: _is_int_in_range(v, 0, 250),
    "goals_against": lambda v: _is_int_in_range(v, 0, 250),
    "event_minute": lambda v: _is_int_in_range(v, 0, 130),
    "match_date": _is_parseable_date,
    "home_team_name": _is_plausible_name,
    "away_team_name": _is_plausible_name,
    "player_name": _is_plausible_name,
    "status": _is_short_code,
    "event_type": _is_short_code,
}


def passes_sanity_check(concept: str, sample_value: str) -> bool:
    """True se não houver validador (sem opinião) ou se o valor passar.
    False só quando existe um validador E o valor falha nele."""

    validator = CONCEPT_VALIDATORS.get(concept)
    if validator is None:
        return True
    if sample_value in ("", "None", "null"):
        return False  # valor vazio nunca é uma amostra confiável pra validar
    try:
        return validator(sample_value)
    except Exception:
        return False
