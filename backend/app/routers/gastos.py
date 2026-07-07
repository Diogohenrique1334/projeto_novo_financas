"""Rotas de gastos (escopadas ao usuário corrente)."""

from fastapi import APIRouter, Depends

from app.dependencies.auth import get_current_user
from app.schemas_api import GastoOut
from models.usuario import Usuario
from services.gastos_service import listar_gastos_tratados

router = APIRouter(prefix="/gastos", tags=["gastos"])


@router.get("", response_model=list[GastoOut])
async def get_gastos(usuario: Usuario = Depends(get_current_user)) -> list[GastoOut]:
    """Retorna os gastos tratados DO USUÁRIO corrente (nunca de outro — spec §4)."""
    return await listar_gastos_tratados(usuario.id)
