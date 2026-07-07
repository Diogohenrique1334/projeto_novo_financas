"""Testes de LGPD + custo (spec §9), contra o Neon real.

  1. consentimento: consent_at começa nulo e é carimbado por definir_consentimento;
  2. audit log: login e uploads são registrados e contáveis por dia;
  3. teto de upload POR usuário: reservar_extracao barra ao atingir o limite;
  4. exclusão de conta: remove usuário + transações + audit por CASCADE.

Uso:  cd backend && python testes/test_lgpd.py
"""

import asyncio
import sys
from datetime import date

import pandas as pd
from sqlalchemy import func, select

from config import settings
from database import async_session, create_tables, engine
from models.audit import EVENTO_LOGIN, EVENTO_UPLOAD_EXTRACT, AuditLog
from models.transacao import Transacao
from repository.audit_repository import contar_eventos_hoje, registrar_evento
from repository.transacoes_repository import salvar_transacoes
from repository.usuarios_repository import (
    buscar_por_id,
    definir_consentimento,
    get_or_create_por_email,
    remover_usuario,
)
from services.limite_uso import LimiteExcedido, reservar_extracao

EMAIL = "lgpd_test@example.com"
_falhas: list[str] = []


def checar(cond: bool, descricao: str) -> None:
    print(f"  [{'OK  ' if cond else 'FALHOU'}] {descricao}")
    if not cond:
        _falhas.append(descricao)


async def _contar(modelo, user_id) -> int:
    async with async_session() as s:
        return await s.scalar(
            select(func.count()).select_from(modelo).where(modelo.user_id == user_id)
        )


async def main() -> None:
    await create_tables()
    u = await get_or_create_por_email(EMAIL, nome="LGPD")
    await remover_usuario(u.id)  # começa limpo
    u = await get_or_create_por_email(EMAIL, nome="LGPD")

    try:
        # 1. consentimento
        checar(u.consent_at is None, "consent_at começa nulo")
        u2 = await definir_consentimento(u.id)
        checar(u2.consent_at is not None, "definir_consentimento carimba consent_at")

        # 2. audit de login
        await registrar_evento(u.id, EVENTO_LOGIN)
        checar(await contar_eventos_hoje(u.id, EVENTO_LOGIN) == 1, "login é auditado (1 hoje)")

        # 3. teto de upload por usuário
        settings.LIMITE_DIARIO_UPLOAD = 3
        for i in range(3):
            await reservar_extracao(u.id, f"f{i}.pdf")
        checar(await contar_eventos_hoje(u.id, EVENTO_UPLOAD_EXTRACT) == 3, "3 extrações reservadas")
        estourou = False
        try:
            await reservar_extracao(u.id, "excedente.pdf")
        except LimiteExcedido:
            estourou = True
        checar(estourou, "4ª extração barra no teto (LimiteExcedido)")

        # 4. exclusão de conta (CASCADE)
        df = pd.DataFrame([{
            "date": date(2026, 1, 1), "descricao": "X", "parcelas": None,
            "categoria": None, "cidade": None, "amount": 10.0,
        }])
        await salvar_transacoes(u.id, df)
        checar(await _contar(Transacao, u.id) == 1, "usuário tem 1 transação antes de excluir")
        checar(await _contar(AuditLog, u.id) >= 4, "usuário tem eventos de audit antes de excluir")

        await remover_usuario(u.id)
        checar(await buscar_por_id(u.id) is None, "usuário removido")
        checar(await _contar(Transacao, u.id) == 0, "transações removidas por CASCADE")
        checar(await _contar(AuditLog, u.id) == 0, "audit log removido por CASCADE")

    finally:
        await remover_usuario(u.id)
        await engine.dispose()

    print()
    if _falhas:
        print(f"RESULTADO: {len(_falhas)} FALHA(S) [FAIL]")
        for f in _falhas:
            print(f"   - {f}")
        sys.exit(1)
    print("RESULTADO: TODOS OS TESTES DE LGPD/CUSTO PASSARAM [PASS]")


if __name__ == "__main__":
    asyncio.run(main())
