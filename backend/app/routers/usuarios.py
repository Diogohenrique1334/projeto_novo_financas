"""Rotas de usuário: identidade do usuário corrente (``/me``) e admin.

- ``GET /usuarios/me``           → qualquer usuário autenticado (inclusive pending).
- ``GET /usuarios``              → admin: lista todos.
- ``PATCH /usuarios/{id}/status``→ admin: aprova/bloqueia/reverte.
- ``DELETE /usuarios/{id}``      → admin: remove (cascade nas transações).
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status as http_status

from app.dependencies.auth import get_identidade, require_admin
from app.schemas_api import AcaoOut, StatusUpdateIn, UsuarioOut
from models.audit import EVENTO_LOGIN
from models.usuario import STATUSES, Usuario
from repository.audit_repository import registrar_evento
from repository.usuarios_repository import (
    definir_consentimento,
    definir_status,
    listar_usuarios,
    remover_usuario,
)

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.get("/me", response_model=UsuarioOut)
async def me(usuario: Usuario = Depends(get_identidade)) -> Usuario:
    """Devolve a identidade + status do usuário corrente (inclusive ``pending``).

    Usa ``get_identidade`` (não ``get_current_user``) de propósito: o frontend
    precisa saber que a conta está ``pending``/``blocked`` para mostrar a tela
    certa — por isso esta rota não aplica o guard de aprovação.
    """
    return usuario


@router.post("/me/consent", response_model=UsuarioOut)
async def consentir(usuario: Usuario = Depends(get_identidade)) -> Usuario:
    """Registra o consentimento LGPD do usuário corrente (spec §9)."""
    atualizado = await definir_consentimento(usuario.id)
    return atualizado or usuario


@router.delete("/me", response_model=AcaoOut)
async def excluir_minha_conta(usuario: Usuario = Depends(get_identidade)) -> AcaoOut:
    """Exclui a conta do usuário e TODOS os seus dados por CASCADE (LGPD, spec §9).

    Remove transações e audit log junto (FKs ON DELETE CASCADE). Ação do próprio
    dono — não exige aprovação (um pending também pode desistir e apagar tudo).
    """
    afetados = await remover_usuario(usuario.id)
    return AcaoOut(afetados=afetados)


@router.post("/eventos/login", status_code=http_status.HTTP_204_NO_CONTENT)
async def registrar_login(usuario: Usuario = Depends(get_identidade)) -> Response:
    """Audita um login (chamado uma vez por sessão pelo frontend)."""
    await registrar_evento(usuario.id, EVENTO_LOGIN)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@router.get("", response_model=list[UsuarioOut])
async def listar(_: Usuario = Depends(require_admin)) -> list[Usuario]:
    """Lista todos os usuários (admin). Mais recentes primeiro."""
    return await listar_usuarios()


@router.patch("/{user_id}/status", response_model=AcaoOut)
async def mudar_status(
    user_id: int,
    payload: StatusUpdateIn,
    admin: Usuario = Depends(require_admin),
) -> AcaoOut:
    """Aprova/bloqueia/reverte um usuário (admin)."""
    if payload.status not in STATUSES:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status inválido; use um de {STATUSES}.",
        )
    if user_id == admin.id and payload.status != "approved":
        # Evita o admin se auto-bloquear e perder o acesso pela própria tela.
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Você não pode alterar o próprio status para não-aprovado.",
        )
    afetados = await definir_status(user_id, payload.status)
    if afetados == 0:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    return AcaoOut(afetados=afetados)


@router.delete("/{user_id}", response_model=AcaoOut)
async def remover(user_id: int, admin: Usuario = Depends(require_admin)) -> AcaoOut:
    """Remove um usuário e, por CASCADE, todas as suas transações (admin)."""
    if user_id == admin.id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Você não pode remover a própria conta pela tela de admin.",
        )
    afetados = await remover_usuario(user_id)
    if afetados == 0:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    return AcaoOut(afetados=afetados)
