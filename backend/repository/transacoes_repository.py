"""Repositório de transações — TODA operação é escopada por ``user_id`` (spec §7).

Isolamento multi-tenant row-level: nenhuma função aqui aceita ler ou escrever
sem o ``user_id`` do dono. Nos updates/deletes, o ``user_id`` entra no ``WHERE``
junto do ``id`` — assim, mesmo forjando um ``id`` alheio, um usuário não toca o
dado de outro (critério de aceite dos testes de isolamento, spec §4).
"""

import pandas as pd
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert

from database import async_session
from models.transacao import Transacao

# Colunas de dado (sem id/user_id) na ordem do schema canônico.
_COLUNAS = ("date", "descricao", "parcelas", "categoria", "cidade", "amount")
# Campos que o usuário pode editar (tudo menos as chaves id/user_id).
_CAMPOS_EDITAVEIS = _COLUNAS


async def salvar_transacoes(user_id: int, df: pd.DataFrame) -> int:
    """Insere as transações do lote como pertencentes a ``user_id``, ignorando duplicatas.

    Duplicatas são barradas pela constraint ``uq_transacao_user``
    ``(user_id, date, descricao, parcelas, amount)`` via ``ON CONFLICT DO NOTHING``.
    Retorna quantas linhas foram efetivamente inseridas.
    """
    if df.empty:
        return 0

    registros = [
        {"user_id": user_id, **{col: row.get(col) for col in _COLUNAS}}
        for _, row in df.iterrows()
    ]

    async with async_session() as session:
        stmt = insert(Transacao).values(registros).on_conflict_do_nothing(
            constraint="uq_transacao_user"
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount


async def listar_transacoes(user_id: int) -> pd.DataFrame:
    """DataFrame das transações do usuário (sem id/user_id), para o pipeline de tratamento."""
    async with async_session() as session:
        result = await session.execute(
            select(Transacao).where(Transacao.user_id == user_id)
        )
        linhas = result.scalars().all()

    dados = [{col: getattr(t, col) for col in _COLUNAS} for t in linhas]
    return pd.DataFrame(dados, columns=list(_COLUNAS))


async def listar_crus(user_id: int) -> list[dict]:
    """Transações cruas (com ``id``) do usuário, sem tratamento, para edição."""
    async with async_session() as session:
        result = await session.execute(
            select(Transacao)
            .where(Transacao.user_id == user_id)
            .order_by(Transacao.date.desc(), Transacao.id.desc())
        )
        linhas = result.scalars().all()

    return [
        {"id": t.id, **{col: getattr(t, col) for col in _COLUNAS}} for t in linhas
    ]


async def atualizar_e_excluir(
    user_id: int, alteracoes: list[dict], exclusoes: list[int]
) -> dict:
    """Aplica updates e deletes por ``id``, SEMPRE restritos ao ``user_id`` do dono.

    O filtro por ``user_id`` no ``WHERE`` é a barreira de isolamento: um id que
    não pertença ao usuário simplesmente não casa e nada é alterado/removido.
    """
    atualizados = 0
    excluidos = 0
    async with async_session() as session:
        for linha in alteracoes:
            valores = {c: linha[c] for c in _CAMPOS_EDITAVEIS if c in linha}
            if not valores:
                continue
            res = await session.execute(
                update(Transacao)
                .where(Transacao.id == linha["id"], Transacao.user_id == user_id)
                .values(**valores)
            )
            atualizados += res.rowcount

        if exclusoes:
            res = await session.execute(
                delete(Transacao).where(
                    Transacao.id.in_(exclusoes), Transacao.user_id == user_id
                )
            )
            excluidos += res.rowcount

        await session.commit()

    return {"atualizados": atualizados, "excluidos": excluidos}
