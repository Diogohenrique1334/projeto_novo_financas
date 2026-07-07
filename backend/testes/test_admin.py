"""Teste dos endpoints de admin (spec §3, §4).

Verifica que:
  1. admin lista usuários; não-admin recebe 403;
  2. admin aprova um pending (que passa a acessar /gastos);
  3. admin bloqueia e o usuário volta a ser barrado;
  4. guards: status inválido → 422; auto-bloqueio → 400; auto-remoção → 400;
     usuário inexistente → 404;
  5. admin remove o usuário de teste (cleanup).

Uso:  cd backend && python testes/test_admin.py
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

EMAIL_USER = "admin_test_user@example.com"
_falhas: list[str] = []


def checar(cond: bool, descricao: str) -> None:
    print(f"  [{'OK  ' if cond else 'FALHOU'}] {descricao}")
    if not cond:
        _falhas.append(descricao)


def cunhar(email: str, ttl: int = 300) -> str:
    agora = int(time.time())
    return jwt.encode(
        {"email": email, "nome": "T", "iss": EMISSOR, "iat": agora, "exp": agora + ttl},
        settings.INTERNAL_AUTH_SECRET,
        algorithm=ALGORITMO,
    )


def hdr(email: str) -> dict:
    return {"Authorization": f"Bearer {cunhar(email)}"}


def main() -> None:
    admin_email = sorted(settings.admin_emails)[0]

    with TestClient(app) as client:
        # cria o usuário de teste (nasce pending) tocando /me
        r = client.get("/usuarios/me", headers=hdr(EMAIL_USER))
        user_id = r.json()["id"]
        checar(r.json()["status"] == "pending", "usuário de teste nasce pending")

        # 1. admin lista; não-admin 403
        r = client.get("/usuarios", headers=hdr(admin_email))
        checar(r.status_code == 200, f"admin lista usuários → 200 (foi {r.status_code})")
        checar(any(u["email"] == EMAIL_USER for u in r.json()), "lista contém o usuário de teste")
        r = client.get("/usuarios", headers=hdr(EMAIL_USER))
        checar(r.status_code == 403, f"não-admin NÃO lista → 403 (foi {r.status_code})")

        # 2. aprovar
        r = client.patch(f"/usuarios/{user_id}/status", json={"status": "approved"}, headers=hdr(admin_email))
        checar(r.status_code == 200 and r.json()["afetados"] == 1, "admin aprova o usuário")
        r = client.get("/gastos", headers=hdr(EMAIL_USER))
        checar(r.status_code == 200, f"usuário aprovado acessa /gastos → 200 (foi {r.status_code})")

        # 3. bloquear
        r = client.patch(f"/usuarios/{user_id}/status", json={"status": "blocked"}, headers=hdr(admin_email))
        checar(r.status_code == 200, "admin bloqueia o usuário")
        r = client.get("/gastos", headers=hdr(EMAIL_USER))
        checar(r.status_code == 403, f"usuário bloqueado é barrado → 403 (foi {r.status_code})")

        # 4. guards
        r = client.patch(f"/usuarios/{user_id}/status", json={"status": "xpto"}, headers=hdr(admin_email))
        checar(r.status_code == 422, f"status inválido → 422 (foi {r.status_code})")

        admin_id = client.get("/usuarios/me", headers=hdr(admin_email)).json()["id"]
        r = client.patch(f"/usuarios/{admin_id}/status", json={"status": "blocked"}, headers=hdr(admin_email))
        checar(r.status_code == 400, f"admin não se auto-bloqueia → 400 (foi {r.status_code})")
        r = client.delete(f"/usuarios/{admin_id}", headers=hdr(admin_email))
        checar(r.status_code == 400, f"admin não se auto-remove → 400 (foi {r.status_code})")

        r = client.patch("/usuarios/99999999/status", json={"status": "approved"}, headers=hdr(admin_email))
        checar(r.status_code == 404, f"usuário inexistente → 404 (foi {r.status_code})")

        # 5. remover o usuário de teste
        r = client.delete(f"/usuarios/{user_id}", headers=hdr(admin_email))
        checar(r.status_code == 200 and r.json()["afetados"] == 1, "admin remove o usuário de teste")

    # cleanup defensivo (engine próprio — não reusar o global)
    async def _limpar():
        eng = create_async_engine(DATABASE_URL, connect_args={"ssl": True, "statement_cache_size": 0})
        async with eng.begin() as conn:
            await conn.execute(text("delete from users where email = :e"), {"e": EMAIL_USER})
        await eng.dispose()

    asyncio.run(_limpar())

    print()
    if _falhas:
        print(f"RESULTADO: {len(_falhas)} FALHA(S) [FAIL]")
        for f in _falhas:
            print(f"   - {f}")
        sys.exit(1)
    print("RESULTADO: TODOS OS TESTES DE ADMIN PASSARAM [PASS]")


if __name__ == "__main__":
    main()
