"""
Base do motor de descobertas.

Isto implementa a proteção contra o problema que discutimos no início
de tudo: rodar centenas de hipóteses sem controle garante "descobertas"
que são só ruído estatístico. Duas regras não-negociáveis aqui:

  1. TAMANHO MÍNIMO DE AMOSTRA — uma hipótese não pode virar
     "descoberta" com poucos jogos. Cada Hypothesis declara seu
     próprio mínimo; abaixo disso, o motor descarta silenciosamente
     (não é erro, é o sistema recusando publicar algo frágil).
  2. TAMANHO DE AMOSTRA SEMPRE VISÍVEL — toda Discovery carrega
     quantos jogos sustentam o número. Nunca aparece "time X vence
     80%" sem dizer se isso é sobre 5 jogos ou 200.

Isto NÃO é correção de Benjamini-Hochberg/FDR completa (isso exige
rodar todas as ~1500 hipóteses de uma vez e ajustar o limiar em
conjunto) — é a primeira camada, mais simples, que já impede o caso
mais óbvio de "descoberta" vazia por amostra pequena. A correção
estatística completa por lote é o próximo passo natural quando houver
mais de uma hipótese rodando simultaneamente.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..capabilities import Capability
from ..models import Match
from ..registry import SportsDataRegistry
from ..tools.stats_utils import benjamini_hochberg


@dataclass
class Discovery:
    """Uma descoberta publicável — só existe se passou pelo tamanho
    mínimo de amostra da hipótese que a gerou."""

    code: str                 # ex: "D006"
    title: str                # frase curta, pronta pra virar manchete
    detail: str                # explicação em uma frase, com os números
    sample_size: int           # sempre visível — nunca escondido atrás do título
    subject: str                # sobre quem/o que é a descoberta (ex: nome do time)
    p_value: float = 1.0       # significância estatística ANTES da correção por lote
    adjusted_significant: bool = False  # preenchido só depois de apply_multiple_comparisons_correction


class Hypothesis(ABC):
    """Toda hipótese (D001, D002, ...) implementa isto."""

    code: str
    title: str
    required_capabilities: set[Capability]
    min_sample_size: int = 10  # padrão conservador — cada hipótese pode sobrescrever

    @abstractmethod
    def evaluate(self, matches: list[Match], context: dict | None = None) -> list[Discovery]:
        """Recebe as partidas já normalizadas (e, opcionalmente, um
        contexto extra — ex: tabela de classificação, pra hipóteses
        que precisam saber a posição dos times) e devolve só as
        descobertas que passaram no tamanho mínimo de amostra e no
        efeito prático mínimo. NUNCA deve lançar exceção por falta de
        dado — retorna lista vazia se não houver dado suficiente."""
        ...


def apply_multiple_comparisons_correction(discoveries: list[Discovery], alpha: float = 0.05) -> list[Discovery]:
    """Roda Benjamini-Hochberg sobre TODAS as descobertas de um lote
    (de uma ou várias hipóteses, rodadas juntas no mesmo dia) e marca
    quais continuam de pé depois da correção.

    IMPORTANTE: isto opera só sobre descobertas que JÁ passaram pelo
    filtro de efeito prático de cada hipótese (a diferença mínima em
    pontos percentuais, por exemplo) — não sobre todo candidato
    testado. Isso é uma simplificação deliberada: o ideal
    estatisticamente mais rigoroso seria corrigir sobre TODOS os
    testes feitos (incluindo os que nem pareciam interessantes), o
    que tornaria a correção mais conservadora ainda. A abordagem aqui
    já resolve o caso mais comum (vários times/hipóteses "parecendo"
    interessantes ao mesmo tempo por acaso), mas é menos rigorosa que
    o ideal — documentado aqui de propósito, não escondido."""

    if not discoveries:
        return []

    p_values = [d.p_value for d in discoveries]
    flags = benjamini_hochberg(p_values, alpha)

    for discovery, is_significant in zip(discoveries, flags):
        discovery.adjusted_significant = is_significant

    return discoveries


class HypothesisEngine:
    """Roda hipóteses contra a Registry, checando capacidade antes
    de tentar — o mesmo princípio de autonomia conservadora do
    resto do pipeline: se o provedor não tem o dado necessário, a
    hipótese é pulada, não forçada."""

    def __init__(self, registry: SportsDataRegistry):
        self._registry = registry

    def run(
        self, hypothesis: Hypothesis, competition: str, matches: list[Match], context: dict | None = None
    ) -> list[Discovery]:
        if not self._registry.supports(competition, next(iter(hypothesis.required_capabilities))):
            return []  # dado necessário indisponível — pula em silêncio, não quebra

        finished = [m for m in matches if m.is_finished]
        return hypothesis.evaluate(finished, context)
