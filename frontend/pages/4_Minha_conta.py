"""Página 'Minha conta' (entrada fina — guard + delega)."""

import streamlit as st

from auth.guarda import exigir_acesso
from conta.painel import render

st.set_page_config(layout="wide", page_title="Minha conta")

me = exigir_acesso()
render(me)
