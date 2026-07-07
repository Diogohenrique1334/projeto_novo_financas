"""Verificação da asserção interna (padrão BFF).

O `st.login` nativo do Streamlit NÃO expõe o id_token cru do Google (só as
claims decodificadas num cookie assinado por ele). Então o backend não tem como
reverificar a assinatura do Google. Em vez disso, o frontend — que já fez o OIDC
real — cunha um JWT curto (HS256) assinado com um segredo compartilhado só entre
os dois serviços, e o backend verifica ESSE token aqui.

Tradeoff conhecido (spec §4): confia-se na asserção do frontend em vez do token
do Google. Mitigação: segredo só em env, TTL curto, ``iss`` fixo, serviços nossos.
"""

from typing import Any

import jwt

from config import settings

ALGORITMO = "HS256"
EMISSOR = "saas-faturas-frontend"


class AssercaoInvalida(Exception):
    """Asserção ausente, malformada, expirada ou com assinatura inválida."""


def _segredo() -> str:
    segredo = settings.INTERNAL_AUTH_SECRET
    if not segredo:
        # Falha explícita: sem segredo, a auth não pode operar com segurança.
        raise AssercaoInvalida("INTERNAL_AUTH_SECRET não configurado no backend.")
    return segredo


def verificar_assertion(token: str) -> dict[str, Any]:
    """Valida a asserção e devolve as claims verificadas (``email``, ``nome``).

    Levanta :class:`AssercaoInvalida` para qualquer falha (assinatura, ``exp``,
    ``iss`` ou e-mail ausente) — o chamador traduz para HTTP 401.
    """
    try:
        claims = jwt.decode(
            token,
            _segredo(),
            algorithms=[ALGORITMO],
            issuer=EMISSOR,
            options={"require": ["exp", "iss", "email"]},
        )
    except jwt.InvalidTokenError as exc:
        raise AssercaoInvalida(str(exc)) from exc

    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise AssercaoInvalida("Asserção sem e-mail.")
    claims["email"] = email
    return claims
