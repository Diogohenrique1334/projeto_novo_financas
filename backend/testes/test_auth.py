"""Teste da auth do backend (asserção interna + gate de autorização).

Roda contra o Neon real via ``TestClient`` (dispara o lifespan → create_tables).
Verifica que o backend:

  1. aceita uma asserção válida e responde /me + /gastos para um admin aprovado;
  2. reporta ``pending`` no /me e BARRA /gastos (403) de um usuário não aprovado;
  3. rejeita (401) asserção com assinatura errada e asserção expirada;
  4. rejeita (401/403) requisição SEM Authorization.

Uso:  cd backend && python testes/test_auth.py
"""

from __future__ import annotations

import asyncio
import sys
import time

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.main_api import app
from auth.tokens import ALGORITMO, EMISSOR
from config import settings
from database import DATABASE_URL

EMAIL_PENDING = "pending_auth_test@example.com"
_falhas: list[str] = []


def checar(cond: bool, descricao: str) -> None:
    print(f"  [{'OK  ' if cond else 'FALHOU'}] {descricao}")
    if not cond:
        _falhas.append(descricao)


def cunhar(email: str, ttl: int = 300, segredo: str | None = None, iss: str = EMISSOR) -> str:
    agora = int(time.time())
    return jwt.encode(
        {"email": email, "nome": "Teste", "iss": iss, "iat": agora, "exp": agora + ttl},
        segredo or settings.INTERNAL_AUTH_SECRET,
        algorithm=ALGORITMO,
    )


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    admin_email = sorted(settings.admin_emails)[0]

    with TestClient(app) as client:
        # 1. admin aprovado
        r = client.get("/usuarios/me", headers=bearer(cunhar(admin_email)))
        checar(r.status_code == 200, f"/me com asserção válida → 200 (foi {r.status_code})")
        if r.status_code == 200:
            checar(r.json()["status"] == "approved", "admin do ADMIN_EMAILS vem approved")
            checar(r.json()["role"] == "admin", "admin do ADMIN_EMAILS vem role=admin")
        r = client.get("/gastos", headers=bearer(cunhar(admin_email)))
        checar(r.status_code == 200, f"/gastos do admin → 200 (foi {r.status_code})")

        # 2. usuário pending
        r = client.get("/usuarios/me", headers=bearer(cunhar(EMAIL_PENDING)))
        checar(r.status_code == 200, f"/me de novo usuário → 200 (foi {r.status_code})")
        if r.status_code == 200:
            checar(r.json()["status"] == "pending", "novo usuário nasce pending")
        r = client.get("/gastos", headers=bearer(cunhar(EMAIL_PENDING)))
        checar(r.status_code == 403, f"/gastos de pending é BARRADO → 403 (foi {r.status_code})")

        # 3. assinatura errada
        r = client.get("/gastos", headers=bearer(cunhar(admin_email, segredo="segredo_errado")))
        checar(r.status_code == 401, f"assinatura inválida → 401 (foi {r.status_code})")

        # 3b. expirada
        r = client.get("/gastos", headers=bearer(cunhar(admin_email, ttl=-10)))
        checar(r.status_code == 401, f"asserção expirada → 401 (foi {r.status_code})")

        # 3c. emissor errado
        r = client.get("/gastos", headers=bearer(cunhar(admin_email, iss="outro")))
        checar(r.status_code == 401, f"emissor errado → 401 (foi {r.status_code})")

        # 4. sem Authorization
        r = client.get("/gastos")
        checar(r.status_code in (401, 403), f"sem Bearer é barrado → 401/403 (foi {r.status_code})")

    # Limpeza do usuário sintético com um engine PRÓPRIO — reusar o engine global
    # (já usado pelo loop do TestClient) num novo asyncio.run quebra o asyncpg.
    async def _limpar():
        eng = create_async_engine(
            DATABASE_URL, connect_args={"ssl": True, "statement_cache_size": 0}
        )
        async with eng.begin() as conn:
            await conn.execute(
                text("delete from users where email = :e"), {"e": EMAIL_PENDING}
            )
        await eng.dispose()

    asyncio.run(_limpar())

    print()
    if _falhas:
        print(f"RESULTADO: {len(_falhas)} FALHA(S) [FAIL]")
        for f in _falhas:
            print(f"   - {f}")
        sys.exit(1)
    print("RESULTADO: TODOS OS TESTES DE AUTH PASSARAM [PASS]")


if __name__ == "__main__":
    main()
