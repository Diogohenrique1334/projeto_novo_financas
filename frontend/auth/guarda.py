"""Guard de acesso das páginas: login → autorização → renderização.

Chame :func:`exigir_acesso` no topo de cada página. Ele:
  1. exige login OIDC (senão mostra a tela de login e para);
  2. consulta ``/usuarios/me`` no backend;
  3. barra ``blocked`` e ``pending`` com telas próprias (spec §3);
  4. devolve o dict do usuário aprovado (``email``, ``nome``, ``role``, ``status``).
"""

import httpx
import streamlit as st

from api.client import buscar_me, dar_consentimento, registrar_login
from auth.sessao import esta_logado

_PROVIDER = "google"


def _tela_login() -> None:
    st.title("💳 Análise de Faturas")
    st.caption("Beta por convite — acesso liberado pelo administrador.")
    st.write("")
    st.info("Entre com sua conta Google para continuar.")
    if st.button("Entrar com Google", type="primary", use_container_width=False):
        st.login(_PROVIDER)
    st.stop()


def _tela_pendente(me: dict) -> None:
    st.title("⏳ Aguardando aprovação")
    st.warning(
        f"Sua conta (**{me.get('email','')}**) foi criada e está **pendente**. "
        "Um administrador precisa aprovar seu acesso antes de você usar o app."
    )
    st.caption("Autenticação ≠ autorização: você está autenticado, mas ainda não autorizado.")
    if st.button("Sair"):
        st.logout()
    st.stop()


def _tela_bloqueado(me: dict) -> None:
    st.title("🚫 Acesso bloqueado")
    st.error(f"A conta **{me.get('email','')}** está bloqueada. Fale com o administrador.")
    if st.button("Sair"):
        st.logout()
    st.stop()


def _tela_sessao_invalida() -> None:
    st.title("Sessão inválida")
    st.error("Não foi possível validar sua sessão com o servidor. Entre novamente.")
    if st.button("Sair"):
        st.logout()
    st.stop()


def _tela_consentimento(me: dict) -> None:
    st.title("📄 Consentimento (LGPD)")
    st.write(
        "Para usar o app, você precisa concordar com o tratamento dos seus dados "
        "financeiros: os PDFs enviados são processados para extrair as transações, "
        "que ficam **isoladas na sua conta**. Você pode **excluir sua conta e todos "
        "os dados** a qualquer momento em *Minha conta*."
    )
    aceito = st.checkbox("Li e concordo com o tratamento dos meus dados.")
    if st.button("Continuar", type="primary", disabled=not aceito):
        dar_consentimento()
        st.rerun()
    if st.button("Sair"):
        st.logout()
    st.stop()


def _auditar_login_uma_vez() -> None:
    """Registra o login no audit log uma única vez por sessão do Streamlit."""
    if not st.session_state.get("_login_auditado"):
        try:
            registrar_login()
        except Exception:  # noqa: BLE001 — auditoria não deve travar o acesso
            pass
        st.session_state["_login_auditado"] = True


def exigir_acesso() -> dict:
    """Garante logado + consentido + aprovado; devolve o dict de ``/me``. Para se não."""
    if not esta_logado():
        _tela_login()

    try:
        me = buscar_me()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            _tela_sessao_invalida()
        raise

    _auditar_login_uma_vez()

    # Consentimento LGPD antes de qualquer uso (mesmo pending precisa consentir).
    if not me.get("consent_at"):
        _tela_consentimento(me)

    status = me.get("status")
    if status == "blocked":
        _tela_bloqueado(me)
    if status != "approved":
        _tela_pendente(me)

    return me
