"""Painel de administração: aprovar / bloquear / remover usuários (spec §3).

Renderizado só para ``role='admin'`` (o guard fica na página que chama). Toda
ação chama o backend, que revalida ``require_admin`` — a UI é conveniência, não
a fronteira de segurança.
"""

import httpx
import streamlit as st

from api.client import listar_usuarios, mudar_status_usuario, remover_usuario

# Rótulo + cor por status, para o "badge".
_BADGE = {
    "approved": ("✅ aprovado", "#10b981"),
    "pending": ("⏳ pendente", "#d4a017"),
    "blocked": ("🚫 bloqueado", "#e5534b"),
}


def _kpi(col, rotulo: str, valor: int, cor: str) -> None:
    col.markdown(
        f"""
        <div style="border:1px solid #2a2f3a;border-radius:10px;padding:14px 16px;
                    background:#161b22;">
          <div style="font-size:12px;color:#9aa4b2;text-transform:uppercase;
                      letter-spacing:.5px;">{rotulo}</div>
          <div style="font-size:28px;font-weight:700;color:{cor};">{valor}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _acao(user_id: int, funcao, *args, sucesso: str) -> None:
    """Executa uma ação de admin, trata erro de forma amigável e recarrega."""
    try:
        funcao(*args)
        st.toast(sucesso)
        st.rerun()
    except httpx.HTTPStatusError as exc:
        detalhe = ""
        try:
            detalhe = exc.response.json().get("detail", "")
        except Exception:  # noqa: BLE001
            detalhe = exc.response.text
        st.error(f"Falhou: {detalhe or exc}")


def render(me: dict) -> None:
    st.title("🛠️ Administração de usuários")
    st.caption("Autenticação ≠ autorização: aqui você autoriza quem pode usar o app.")

    usuarios = listar_usuarios()

    total = len(usuarios)
    pendentes = sum(1 for u in usuarios if u["status"] == "pending")
    aprovados = sum(1 for u in usuarios if u["status"] == "approved")
    bloqueados = sum(1 for u in usuarios if u["status"] == "blocked")

    c1, c2, c3, c4 = st.columns(4)
    _kpi(c1, "Total", total, "#e6edf3")
    _kpi(c2, "Pendentes", pendentes, "#d4a017")
    _kpi(c3, "Aprovados", aprovados, "#10b981")
    _kpi(c4, "Bloqueados", bloqueados, "#e5534b")

    st.markdown("---")

    if pendentes:
        st.info(f"**{pendentes}** usuário(s) aguardando aprovação.")

    for u in usuarios:
        rotulo, cor = _BADGE.get(u["status"], (u["status"], "#9aa4b2"))
        eu = u["id"] == me["id"]
        with st.container(border=True):
            info, badge, acoes = st.columns([5, 2, 3])
            with info:
                nome = u.get("nome") or "—"
                marca_admin = " · 👑 admin" if u["role"] == "admin" else ""
                marca_eu = " · (você)" if eu else ""
                st.markdown(f"**{u['email']}**{marca_admin}{marca_eu}")
                st.caption(f"#{u['id']} · {nome}")
            badge.markdown(
                f"<span style='color:{cor};font-weight:600'>{rotulo}</span>",
                unsafe_allow_html=True,
            )
            with acoes:
                b1, b2, b3 = st.columns(3)
                # Aprovar (para pending/blocked)
                if u["status"] != "approved":
                    if b1.button("Aprovar", key=f"apr_{u['id']}", use_container_width=True):
                        _acao(u["id"], mudar_status_usuario, u["id"], "approved",
                              sucesso=f"{u['email']} aprovado.")
                # Bloquear (para não-bloqueado e não-eu)
                if u["status"] != "blocked" and not eu:
                    if b2.button("Bloquear", key=f"blq_{u['id']}", use_container_width=True):
                        _acao(u["id"], mudar_status_usuario, u["id"], "blocked",
                              sucesso=f"{u['email']} bloqueado.")
                # Remover (não-eu), com confirmação
                if not eu:
                    with b3.popover("Remover", use_container_width=True):
                        st.warning(f"Remover **{u['email']}** e TODOS os seus dados?")
                        if st.button("Confirmar remoção", key=f"rem_{u['id']}", type="primary"):
                            _acao(u["id"], remover_usuario, u["id"],
                                  sucesso=f"{u['email']} removido.")
