"""Serviço de upload de faturas: extração (preview) e persistência (confirmação).

Separa as duas etapas do fluxo do dashboard:
  1. ``extrair_transacoes``  → lê o PDF com o LLM e devolve as transações SEM salvar.
  2. ``salvar_transacoes``   → persiste o lote (já conferido/editado pelo usuário).
"""

from typing import Any, Optional

import pandas as pd

from repository.transacoes_repository import salvar_transacoes as _repo_salvar_transacoes
from services.extracao.extrator import extrair_de_pdf

# Colunas esperadas pelo repositório, na ordem do schema da fatura.
_COLUNAS = ["date", "descricao", "parcelas", "categoria", "cidade", "amount"]


def _normalizar_data(valor: Any) -> Optional[str]:
    """Normaliza a data do modelo (ISO) para 'YYYY-MM-DD'; None se irreconhecível."""
    if not valor:
        return None
    texto = str(valor).strip()
    try:  # caminho feliz: já veio ISO do modelo
        return pd.Timestamp(texto[:10]).date().isoformat()
    except (ValueError, TypeError):
        pass
    try:  # tolera formatos não-ISO (dd/mm/aaaa etc.)
        return pd.to_datetime(texto, dayfirst=True).date().isoformat()
    except (ValueError, TypeError):
        return None


def _limpar(texto: Any) -> Optional[str]:
    if texto is None:
        return None
    limpo = str(texto).strip()
    return limpo or None


def extrair_transacoes(conteudo: bytes, senha: Optional[str] = None) -> list[dict[str, Any]]:
    """Lê uma fatura (PDF) com o modelo de visão e devolve as transações p/ conferência.

    Operação síncrona e lenta (chamada de LLM): deve ser chamada via threadpool a
    partir da rota async. Não toca no banco. Descarta linhas sem os campos
    obrigatórios (``date``, ``descricao``, ``amount``) — a conferência humana
    ainda revisa o resto.
    """
    brutas = extrair_de_pdf(conteudo, senha)

    registros: list[dict[str, Any]] = []
    for t in brutas:
        data = _normalizar_data(t.get("date"))
        descricao = _limpar(t.get("descricao"))
        amount = t.get("amount")
        if data is None or descricao is None or amount is None:
            continue  # sem obrigatório: descarta
        registros.append(
            {
                "date": data,
                "descricao": descricao,
                "parcelas": _limpar(t.get("parcelas")),
                "categoria": _limpar(t.get("categoria")),
                "cidade": _limpar(t.get("cidade")),
                "amount": float(amount),
            }
        )
    return registros


async def salvar_transacoes(user_id: int, transacoes: list[dict[str, Any]]) -> dict[str, int]:
    """Persiste um lote de transações já conferidas do usuário, ignorando duplicatas.

    Args:
        user_id: dono das transações (derivado do token, nunca do cliente — spec §4).
        transacoes: lista de dicts com as chaves de ``_COLUNAS`` (date já como
            ``datetime.date``). Tipicamente vinda de ``SalvarFaturasIn``.

    Returns:
        dict com ``recebidos``, ``salvos`` (inseridos de fato) e ``ignorados``
        (duplicatas barradas pelo índice único).
    """
    df = pd.DataFrame(transacoes)
    df = df.reindex(columns=_COLUNAS)
    df["date"] = pd.to_datetime(df["date"])

    salvos = await _repo_salvar_transacoes(user_id, df)
    recebidos = len(df)
    return {"recebidos": recebidos, "salvos": salvos, "ignorados": recebidos - salvos}
