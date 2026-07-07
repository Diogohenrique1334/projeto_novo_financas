"""Componente de gerenciamento de transações (editar/excluir o dado cru).

Diferente do painel (que mostra dado **tratado** e re-derivado a cada leitura),
aqui editamos a **fonte da verdade**: as linhas cruas do banco, identificadas
pela PK ``id``. O usuário altera células e remove linhas num ``st.data_editor``;
ao salvar, calculamos o *diff* contra o estado original e enviamos só o que mudou
(updates) e o que sumiu (deletes) ao backend, numa transação só.

Toda a persistência mora no backend; aqui só orquestramos UI + diff + HTTP.
"""

import datetime

import httpx
import pandas as pd
import streamlit as st

from api.client import editar_gastos, get_gastos, listar_gastos_crus

# Mesmas categorias do prompt de extração (mantém o editor alinhado).
_CATEGORIAS = [
    "Alimentação", "Transporte", "Moradia", "Saúde", "Lazer",
    "Compras", "Serviços", "Educação", "Outros",
]
_COLUNAS = ["date", "descricao", "parcelas", "categoria", "cidade", "amount"]


@st.cache_data(ttl=60)
def _carregar() -> pd.DataFrame:
    """Busca as transações cruas e indexa por ``id`` (snapshot estável p/ o diff)."""
    df = pd.DataFrame(listar_gastos_crus(), columns=["id"] + _COLUNAS)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.set_index("id")


def _detalhe_erro(exc: httpx.HTTPStatusError) -> str:
    """Extrai a mensagem ``detail`` do corpo de erro da API, com fallback."""
    try:
        return exc.response.json().get("detail", str(exc))
    except Exception:  # noqa: BLE001 — corpo não-JSON
        return str(exc)


def _normalizar(valor):
    """Normaliza para comparação: NaN/None → '' e tudo o mais para str canônica."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    return str(valor)


def _linha_para_payload(id_: int, linha: pd.Series) -> dict:
    """Monta o dict de update para uma linha editada (date → ISO)."""
    data = linha["date"]
    return {
        "id": int(id_),
        "date": data.isoformat() if isinstance(data, datetime.date) else data,
        "descricao": linha["descricao"],
        "parcelas": linha.get("parcelas"),
        "categoria": linha.get("categoria"),
        "cidade": linha.get("cidade"),
        "amount": float(linha["amount"]),
    }


def _calcular_diff(original: pd.DataFrame, editado: pd.DataFrame):
    """Compara original × editado e devolve (alteracoes, exclusoes, n_novas)."""
    ids_orig = set(original.index)
    ids_edit = {i for i in editado.index if pd.notna(i)}

    exclusoes = [int(i) for i in (ids_orig - ids_edit)]
    n_novas = int(sum(1 for i in editado.index if pd.isna(i)))  # linhas adicionadas (ignoradas)

    alteracoes = []
    for id_ in (ids_orig & ids_edit):
        antes, depois = original.loc[id_], editado.loc[id_]
        if any(_normalizar(antes[c]) != _normalizar(depois[c]) for c in _COLUNAS):
            alteracoes.append(_linha_para_payload(id_, depois))

    return alteracoes, exclusoes, n_novas


def _aplicar(alteracoes: list[dict], exclusoes: list[int]) -> None:
    """Envia o diff ao backend, trata erros e atualiza os caches."""
    try:
        with st.spinner("Aplicando alterações…"):
            resumo = editar_gastos(alteracoes, exclusoes)
    except httpx.HTTPStatusError as exc:
        st.error(f"Não consegui salvar: {_detalhe_erro(exc)}")
        return
    except httpx.HTTPError as exc:
        st.error(f"Erro de conexão com o backend: {exc}")
        return

    _carregar.clear()  # recarrega o editor com o estado novo
    get_gastos.clear()  # invalida o painel tratado
    st.success(
        f"✅ {resumo['atualizados']} atualizada(s) · {resumo['excluidos']} excluída(s)."
    )
    st.rerun()


def render() -> None:
    """Renderiza a página de gerenciamento de transações."""
    st.set_page_config(layout="wide", page_title="Gerenciar transações")
    st.title("🛠️ Gerenciar transações")
    st.caption(
        "Edite as células e remova linhas direto na tabela. Aqui você mexe no "
        "**dado cru** do banco — o painel já reflete as mudanças após salvar."
    )

    original = _carregar()
    if original.empty:
        st.info("Nenhuma transação no banco ainda. Use **Enviar fatura** para incluir.")
        return

    editado = st.data_editor(
        original,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="editor_gerenciar",
        column_config={
            "date": st.column_config.DateColumn("Data", required=True),
            "descricao": st.column_config.TextColumn("Descrição", required=True),
            "parcelas": st.column_config.TextColumn("Parcelas"),
            "categoria": st.column_config.SelectboxColumn("Categoria", options=_CATEGORIAS),
            "cidade": st.column_config.TextColumn("Cidade"),
            "amount": st.column_config.NumberColumn("Valor", format="R$ %.2f", required=True),
        },
    )

    alteracoes, exclusoes, n_novas = _calcular_diff(original, editado)

    if n_novas:
        st.caption(
            "ℹ️ Linhas novas adicionadas aqui são ignoradas — use **Enviar fatura** para incluir."
        )

    coluna_alt, coluna_exc = st.columns(2)
    coluna_alt.metric("Alterações", len(alteracoes))
    coluna_exc.metric("Exclusões", len(exclusoes))

    nada_a_fazer = not alteracoes and not exclusoes
    confirmado = True
    if exclusoes:
        confirmado = st.checkbox(
            f"Confirmo a exclusão de {len(exclusoes)} transação(ões) — ação irreversível."
        )

    if st.button(
        "Salvar alterações",
        type="primary",
        disabled=nada_a_fazer or not confirmado,
    ):
        _aplicar(alteracoes, exclusoes)
