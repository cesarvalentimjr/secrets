"""
Publicador de descobertas.

Implementa a ideia central da sua primeira mensagem: o usuário nunca
vê "hipótese D006 com p-valor tal" — ele vê uma frase pronta, com o
tamanho de amostra sempre visível (mas discreto, não como aviso
técnico assustador).
"""

from __future__ import annotations

from .base import Discovery


def format_for_display(discovery: Discovery) -> str:
    """Formato pronto pra tela do produto. O código (D006, D010...)
    fica de fora do texto principal — é metadado interno, não algo
    que o usuário final precisa ver."""

    return f"{discovery.title}\n{discovery.detail}\n(baseado em {discovery.sample_size} jogos)"


def format_batch(discoveries: list[Discovery]) -> str:
    """Várias descobertas juntas, como apareceriam numa tela de
    'descobertas de hoje'. Vazio vira uma frase honesta, não um
    espaço em branco confuso."""

    if not discoveries:
        return "Nenhuma descoberta com confiança suficiente hoje — o motor está sendo conservador de propósito."

    return "\n\n".join(format_for_display(d) for d in discoveries)
