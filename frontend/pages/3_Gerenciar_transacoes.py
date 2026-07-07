"""Página de gerenciamento de transações (entrada fina — guard + delega)."""

import streamlit as st

from auth.guarda import exigir_acesso
from gerenciar.transacoes import render

st.set_page_config(layout="wide", page_title="Gerenciar transações")
exigir_acesso()
render()
