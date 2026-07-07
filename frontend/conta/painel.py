"""Página 'Minha conta': dados do usuário + exclusão LGPD (spec §9)."""

import streamlit as st

from api.client import excluir_minha_conta


def render(me: dict) -> None:
    st.title("👤 Minha conta")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**E-mail:** {me.get('email','—')}")
        st.markdown(f"**Nome:** {me.get('nome') or '—'}")
    with c2:
        st.markdown(f"**Status:** {me.get('status','—')}")
        st.markdown(f"**Perfil:** {me.get('role','—')}")
    consent = me.get("consent_at")
    st.caption(f"Consentimento registrado em: {consent[:19].replace('T',' ') if consent else '—'}")

    st.markdown("---")
    st.subheader("⚠️ Zona de perigo")
    st.write(
        "Excluir sua conta remove **permanentemente** todos os seus dados: transações, "
        "auditoria e o cadastro. Esta ação **não pode ser desfeita**."
    )
    with st.popover("Excluir minha conta e meus dados", use_container_width=False):
        st.warning("Tem certeza? Todos os seus dados serão apagados imediatamente.")
        confirma = st.text_input("Digite EXCLUIR para confirmar", key="confirma_exclusao")
        if st.button("Excluir definitivamente", type="primary", disabled=confirma != "EXCLUIR"):
            excluir_minha_conta()
            st.session_state.clear()
            st.success("Conta e dados excluídos. Você será desconectado.")
            st.logout()
