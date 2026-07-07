"""Página de envio de fatura (entrada fina — guard + delega ao componente)."""

import streamlit as st

from auth.guarda import exigir_acesso
from upload.enviar_fatura import render

st.set_page_config(layout="wide", page_title="Enviar fatura")
exigir_acesso()
render()
