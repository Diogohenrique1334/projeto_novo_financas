"""Dependencies de identidade e autorização.

Fluxo (padrão BFF — ver ``auth/tokens.py``):
  1. o frontend envia ``Authorization: Bearer <asserção>``;
  2. :func:`get_identidade` verifica a asserção e deriva o e-mail do token
     VERIFICADO (nunca de body/header cru — spec §4), faz ``get_or_create`` e
     devolve o ``Usuario`` seja qual for o status;
  3. :func:`get_current_user` acrescenta o guard de autorização (só ``approved``).

Rotas de dado dependem de :func:`get_current_user`. A ``/me`` usa
:func:`get_identidade` para poder reportar status ``pending``/``blocked``.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.tokens import AssercaoInvalida, verificar_assertion
from models.usuario import Usuario
from repository.usuarios_repository import get_or_create_por_email

_bearer = HTTPBearer(auto_error=True)


async def get_identidade(
    credencial: HTTPAuthorizationCredentials = Depends(_bearer),
) -> Usuario:
    """Verifica a asserção e devolve o ``Usuario`` (qualquer status). 401 se inválida."""
    try:
        claims = verificar_assertion(credencial.credentials)
    except AssercaoInvalida as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Autenticação inválida: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return await get_or_create_por_email(claims["email"], nome=claims.get("nome"))


async def get_current_user(usuario: Usuario = Depends(get_identidade)) -> Usuario:
    """Exige usuário AUTORIZADO (``status='approved'``) — guard de acesso (spec §3)."""
    if usuario.status == "blocked":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Conta bloqueada.")
    if usuario.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conta aguardando aprovação do admin.",
        )
    return usuario


async def require_admin(usuario: Usuario = Depends(get_current_user)) -> Usuario:
    """Exige um admin aprovado (para a página de administração — Fase 4)."""
    if usuario.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito a admin.")
    return usuario
