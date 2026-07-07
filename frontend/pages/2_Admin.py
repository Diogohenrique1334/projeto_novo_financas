"""Página de administração (entrada fina — guard + role admin + delega)."""

import streamlit as st

from admin.painel import render
from auth.guarda import exigir_acesso

st.set_page_config(layout="wide", page_title="Administração")

me = exigir_acesso()  # login + aprovado

if me.get("role") != "admin":
    st.title("🔒 Acesso restrito")
    st.error("Esta página é exclusiva para administradores.")
    st.stop()

render(me)
