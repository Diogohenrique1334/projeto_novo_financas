"""Sessão do usuário: login OIDC (Google) + cunhagem da asserção interna.

Autenticação ≠ autorização (spec §3):
  * o ``st.login`` nativo autentica qualquer conta Google;
  * a autorização (``approved``) é decidida pelo backend, que este módulo
    consulta em ``/usuarios/me`` para decidir qual tela mostrar.

A asserção interna (JWT HS256) é cunhada a partir do e-mail VERIFICADO pelo
Google (``st.user.email``) e enviada ao backend como ``Authorization: Bearer``.
O segredo é o mesmo ``INTERNAL_AUTH_SECRET`` dos dois lados (padrão BFF).
"""

import time
from typing import Optional

import jwt
import streamlit as st

from config import settings

# Deve casar com EMISSOR do backend (auth/tokens.py).
EMISSOR = "saas-faturas-frontend"
_ALGORITMO = "HS256"
_PROVIDER = "google"


def esta_logado() -> bool:
    """True se há sessão OIDC válida do Streamlit."""
    return bool(getattr(st.user, "is_logged_in", False))


def email_logado() -> Optional[str]:
    """E-mail verificado pelo Google (normalizado), ou None se deslogado."""
    if not esta_logado():
        return None
    email = getattr(st.user, "email", None)
    return email.strip().lower() if email else None


def cunhar_assertion() -> str:
    """Cunha a asserção interna (JWT curto) para o e-mail logado.

    Levanta ``RuntimeError`` se não houver login ou segredo — o guard de acesso
    já impede que isso aconteça em fluxo normal.
    """
    email = email_logado()
    if not email:
        raise RuntimeError("Sem usuário logado para cunhar a asserção.")
    if not settings.INTERNAL_AUTH_SECRET:
        raise RuntimeError("INTERNAL_AUTH_SECRET não configurado no frontend.")

    agora = int(time.time())
    payload = {
        "email": email,
        "nome": getattr(st.user, "name", None),
        "iss": EMISSOR,
        "iat": agora,
        "exp": agora + settings.AUTH_ASSERTION_TTL,
    }
    return jwt.encode(payload, settings.INTERNAL_AUTH_SECRET, algorithm=_ALGORITMO)


def headers_auth() -> dict:
    """Header ``Authorization: Bearer`` com a asserção interna atual."""
    return {"Authorization": f"Bearer {cunhar_assertion()}"}
