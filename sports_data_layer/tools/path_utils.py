"""
Resolução de caminho tipo 'time_mandante.nome_popular' ou 'eventos[0].minuto'
contra um dicionário Python já carregado do JSON. É o que permite o
adaptador genérico usar os caminhos descobertos automaticamente sem
nenhum código específico de provedor.
"""

from __future__ import annotations

import re
from typing import Any

_PATH_SEGMENT = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def get_by_path(obj: Any, path: str) -> Any:
    """Retorna None se qualquer parte do caminho não existir, em vez
    de lançar exceção — dado ausente é normal (nem todo provedor tem
    todo campo) e não deve derrubar o pipeline."""

    current = obj
    for key, index in _PATH_SEGMENT.findall(path):
        if current is None:
            return None
        if key:
            current = current.get(key) if isinstance(current, dict) else None
        elif index:
            i = int(index)
            current = current[i] if isinstance(current, list) and i < len(current) else None
    return current


def find_record_list(raw: Any, _prefix: str = "") -> tuple[str, list] | None:
    """Heurística para achar automaticamente ONDE, dentro da resposta,
    está a lista de registros (partidas, times da tabela, etc).
    Procura recursivamente o primeiro array cujo primeiro item seja
    um dicionário. Retorna (caminho_ate_a_lista, a_lista) ou None se
    a própria raiz já for a lista."""

    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        return _prefix or "$root", raw

    if isinstance(raw, dict):
        for key, value in raw.items():
            path = f"{_prefix}.{key}" if _prefix else key
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return path, value
            if isinstance(value, dict):
                found = find_record_list(value, path)
                if found:
                    return found
    return None
