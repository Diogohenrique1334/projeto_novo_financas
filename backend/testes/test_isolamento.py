"""Teste de isolamento multi-tenant (critério de aceite — spec §4).

Roda contra o banco real (Neon). Cria dois usuários sintéticos, popula
transações para cada e verifica que:

  1. leitura de A nunca retorna dado de B (e vice-versa);
  2. A não consegue editar nem excluir uma transação de B forjando o ``id``;
  3. duplicatas do MESMO usuário são ignoradas (ON CONFLICT), inclusive com
     ``parcelas IS NULL`` (unicidade NULLS NOT DISTINCT);
  4. excluir o usuário apaga suas transações por CASCADE (LGPD, spec §9).

Uso:
    cd backend && python testes/test_isolamento.py

Limpa os usuários sintéticos ao final (mesmo em falha).
"""

import asyncio
import sys
from datetime import date

import pandas as pd
from sqlalchemy import func, select

from database import async_session, create_tables, engine
from models.transacao import Transacao
from repository.transacoes_repository import (
    atualizar_e_excluir,
    listar_crus,
    listar_transacoes,
    salvar_transacoes,
)
from repository.usuarios_repository import get_or_create_por_email, remover_usuario

EMAIL_A = "iso_test_a@example.com"
EMAIL_B = "iso_test_b@example.com"

_falhas: list[str] = []


def checar(cond: bool, descricao: str) -> None:
    marca = "OK  " if cond else "FALHOU"
    print(f"  [{marca}] {descricao}")
    if not cond:
        _falhas.append(descricao)


def _df(rows: list[dict]) -> pd.DataFrame:
    cols = ["date", "descricao", "parcelas", "categoria", "cidade", "amount"]
    return pd.DataFrame(rows, columns=cols)


async def _contar_transacoes(user_id: int) -> int:
    async with async_session() as s:
        return await s.scalar(
            select(func.count()).select_from(Transacao).where(Transacao.user_id == user_id)
        )


async def main() -> None:
    await create_tables()

    a = await get_or_create_por_email(EMAIL_A, nome="Iso A")
    b = await get_or_create_por_email(EMAIL_B, nome="Iso B")
    # começa limpo (caso um run anterior tenha abortado antes da limpeza)
    await remover_usuario(a.id)
    await remover_usuario(b.id)
    a = await get_or_create_por_email(EMAIL_A, nome="Iso A")
    b = await get_or_create_por_email(EMAIL_B, nome="Iso B")

    try:
        # --- popula A e B -----------------------------------------------------
        linhas_a = _df([
            {"date": date(2026, 1, 5), "descricao": "MERCADO A1", "parcelas": "01/03",
             "categoria": "Alimentação", "cidade": "SAO PAULO", "amount": 100.0},
            {"date": date(2026, 1, 6), "descricao": "POSTO A2", "parcelas": None,
             "categoria": "Transporte", "cidade": None, "amount": 50.0},
        ])
        linhas_b = _df([
            {"date": date(2026, 1, 7), "descricao": "LOJA B1", "parcelas": None,
             "categoria": "Compras", "cidade": "RIO DE JANEIRO", "amount": 999.0},
        ])
        salvos_a = await salvar_transacoes(a.id, linhas_a)
        salvos_b = await salvar_transacoes(b.id, linhas_b)
        checar(salvos_a == 2, f"A inseriu 2 transações (inseriu {salvos_a})")
        checar(salvos_b == 1, f"B inseriu 1 transação (inseriu {salvos_b})")

        # --- 3. dedup do mesmo usuário (inclusive parcelas NULL) --------------
        redun = await salvar_transacoes(a.id, linhas_a)
        checar(redun == 0, f"Reenvio das mesmas linhas de A é ignorado (inseriu {redun})")

        # --- 1. leitura isolada ----------------------------------------------
        df_a = await listar_transacoes(a.id)
        df_b = await listar_transacoes(b.id)
        checar(len(df_a) == 2, f"listar_transacoes(A) traz só as 2 de A (trouxe {len(df_a)})")
        checar(len(df_b) == 1, f"listar_transacoes(B) traz só a de B (trouxe {len(df_b)})")
        checar("LOJA B1" not in set(df_a["descricao"]), "Dado de B NÃO aparece na leitura de A")
        checar("MERCADO A1" not in set(df_b["descricao"]), "Dado de A NÃO aparece na leitura de B")

        crus_b = await listar_crus(b.id)
        id_b = crus_b[0]["id"]

        # --- 2. A não edita nem exclui dado de B forjando o id ----------------
        forjado = {"id": id_b, "descricao": "HACKEADO POR A", "amount": 0.0}
        res_edit = await atualizar_e_excluir(a.id, [forjado], [id_b])
        checar(res_edit["atualizados"] == 0, "A NÃO atualiza transação de B (0 updates)")
        checar(res_edit["excluidos"] == 0, "A NÃO exclui transação de B (0 deletes)")

        crus_b_depois = await listar_crus(b.id)
        intacto = (
            len(crus_b_depois) == 1
            and crus_b_depois[0]["descricao"] == "LOJA B1"
            and crus_b_depois[0]["amount"] == 999.0
        )
        checar(intacto, "Transação de B permanece intacta após o ataque de A")

        # dono legítimo consegue editar a própria
        res_dono = await atualizar_e_excluir(
            b.id, [{"id": id_b, "descricao": "LOJA B1 EDITADA", "amount": 999.0}], []
        )
        checar(res_dono["atualizados"] == 1, "B edita a própria transação (1 update)")

        # --- 4. CASCADE ao excluir usuário (LGPD) -----------------------------
        await remover_usuario(a.id)
        restantes_a = await _contar_transacoes(a.id)
        checar(restantes_a == 0, f"Excluir A apaga as transações de A por CASCADE (restaram {restantes_a})")
        # B não foi afetado
        restantes_b = await _contar_transacoes(b.id)
        checar(restantes_b == 1, f"Excluir A não toca em B (B tem {restantes_b})")

    finally:
        await remover_usuario(a.id)
        await remover_usuario(b.id)
        await engine.dispose()

    print()
    if _falhas:
        print(f"RESULTADO: {len(_falhas)} FALHA(S) DE ISOLAMENTO [FAIL]")
        for f in _falhas:
            print(f"   - {f}")
        sys.exit(1)
    print("RESULTADO: TODOS OS TESTES DE ISOLAMENTO PASSARAM [PASS]")


if __name__ == "__main__":
    asyncio.run(main())
