"""Componente de envio de fatura (camada de apresentação).

Fluxo em duas etapas, espelhando a separação do backend:
  1. **Ler fatura** → ``api.client.extrair_fatura`` devolve as transações lidas
     pelo LLM (preview), sem salvar nada.
  2. **Conferir e salvar** → o usuário revisa/edita num ``st.data_editor`` e só
     então ``api.client.salvar_fatura`` persiste o lote, invalidando o cache do
     painel para que os novos gastos apareçam de imediato.

Toda extração/persistência mora no backend; aqui só orquestramos UI + HTTP.
"""

import datetime
from typing import Optional

import httpx
import pandas as pd
import streamlit as st

from api.client import extrair_fatura, get_gastos, salvar_fatura

_CHAVE_EXTRAIDAS = "fatura_transacoes_extraidas"
_CHAVE_ARQUIVO = "fatura_nome_arquivo"

# Mesmas categorias do prompt de extração (mantém o editor alinhado ao LLM).
_CATEGORIAS = [
    "Alimentação", "Transporte", "Moradia", "Saúde", "Lazer",
    "Compras", "Serviços", "Educação", "Outros",
]


def _detalhe_erro(exc: httpx.HTTPStatusError) -> str:
    """Extrai a mensagem ``detail`` do corpo de erro da API, com fallback."""
    try:
        return exc.response.json().get("detail", str(exc))
    except Exception:  # noqa: BLE001 — corpo não-JSON
        return str(exc)


def _ler_fatura(arquivo, senha: Optional[str]) -> None:
    """Chama a extração no backend e guarda o resultado na sessão."""
    try:
        with st.spinner("Lendo a fatura com IA… (pode levar alguns segundos)"):
            transacoes = extrair_fatura(arquivo.getvalue(), arquivo.name, senha or None)
    except httpx.HTTPStatusError as exc:
        st.error(f"Não consegui ler a fatura: {_detalhe_erro(exc)}")
        return
    except httpx.HTTPError as exc:
        st.error(f"Erro de conexão com o backend: {exc}")
        return

    if not transacoes:
        st.warning("Nenhuma transação foi reconhecida nesta fatura. Confira o arquivo.")
        st.session_state.pop(_CHAVE_EXTRAIDAS, None)
        return

    st.session_state[_CHAVE_EXTRAIDAS] = transacoes
    st.session_state[_CHAVE_ARQUIVO] = arquivo.name


def _editor_transacoes(transacoes: list[dict]) -> pd.DataFrame:
    """Renderiza o editor de conferência e devolve o DataFrame editado."""
    df = pd.DataFrame(transacoes)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="editor_fatura",
        column_config={
            "date": st.column_config.DateColumn("Data", required=True),
            "descricao": st.column_config.TextColumn("Descrição", required=True),
            "parcelas": st.column_config.TextColumn("Parcelas"),
            "categoria": st.column_config.SelectboxColumn("Categoria", options=_CATEGORIAS),
            "cidade": st.column_config.TextColumn("Cidade"),
            "amount": st.column_config.NumberColumn("Valor", format="R$ %.2f", required=True),
        },
    )


def _salvar(editado: pd.DataFrame) -> None:
    """Serializa, valida o mínimo e persiste o lote conferido."""
    validos = editado.dropna(subset=["date", "descricao", "amount"])
    if validos.empty:
        st.warning("Nenhuma linha completa para salvar (precisa de data, descrição e valor).")
        return

    registros = validos.to_dict("records")
    for r in registros:
        data = r.get("date")
        r["date"] = data.isoformat() if isinstance(data, datetime.date) else data

    try:
        with st.spinner("Salvando no painel…"):
            resumo = salvar_fatura(registros)
    except httpx.HTTPStatusError as exc:
        st.error(f"Falha ao salvar: {_detalhe_erro(exc)}")
        return
    except httpx.HTTPError as exc:
        st.error(f"Erro de conexão com o backend: {exc}")
        return

    get_gastos.clear()  # invalida o cache para o painel refletir os novos gastos
    st.session_state.pop(_CHAVE_EXTRAIDAS, None)
    st.success(
        f"✅ {resumo['salvos']} transação(ões) salva(s) · "
        f"{resumo['ignorados']} já existiam ({resumo['recebidos']} enviadas)."
    )
    st.balloons()


def render() -> None:
    """Renderiza a página de envio de fatura."""
    st.set_page_config(layout="wide", page_title="Enviar fatura")
    st.title("📤 Enviar fatura")
    st.caption(
        "Suba o PDF da fatura do cartão. A leitura é feita por IA — você **confere "
        "e corrige** as transações antes de salvar no painel."
    )

    arquivo = st.file_uploader("Fatura em PDF", type="pdf")
    senha = st.text_input(
        "Senha do PDF (se for protegido)", type="password", placeholder="opcional"
    )

    if st.button("Ler fatura", type="primary", disabled=arquivo is None):
        _ler_fatura(arquivo, senha)

    if _CHAVE_EXTRAIDAS in st.session_state:
        st.divider()
        st.subheader(f"Confira as transações · {st.session_state.get(_CHAVE_ARQUIVO, '')}")
        st.caption("Edite o que estiver errado, adicione ou remova linhas, depois confirme.")

        editado = _editor_transacoes(st.session_state[_CHAVE_EXTRAIDAS])

        coluna_salvar, coluna_cancelar = st.columns([1, 1])
        if coluna_salvar.button("Confirmar e salvar", type="primary", use_container_width=True):
            _salvar(editado)
        if coluna_cancelar.button("Cancelar", use_container_width=True):
            st.session_state.pop(_CHAVE_EXTRAIDAS, None)
            st.rerun()
