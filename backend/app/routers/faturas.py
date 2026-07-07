"""Rotas de upload de fatura: extração (preview) e salvamento (confirmação)."""

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError

from app.dependencies.auth import get_current_user
from app.schemas_api import (
    EditarFaturasIn,
    EditarFaturasOut,
    GastoCru,
    SalvarFaturasIn,
    SalvarFaturasOut,
    TransacaoExtraida,
)
from config import settings
from models.audit import EVENTO_UPLOAD_SAVE
from models.usuario import Usuario
from repository.audit_repository import registrar_evento
from repository.transacoes_repository import atualizar_e_excluir, listar_crus as _repo_listar_crus
from services.limite_uso import LimiteExcedido, reservar_extracao
from services.upload_service import extrair_transacoes, salvar_transacoes

router = APIRouter(prefix="/faturas", tags=["faturas"])


@router.post("/extrair", response_model=list[TransacaoExtraida])
async def extrair(
    arquivo: UploadFile = File(...),
    senha: Optional[str] = Form(default=None),
    usuario: Usuario = Depends(get_current_user),
) -> list[TransacaoExtraida]:
    """Lê uma fatura PDF e devolve as transações para conferência (NÃO salva).

    A extração roda em threadpool (operação síncrona e lenta por causa do LLM).
    Falhas de PDF inválido/protegido viram 400; estouro do teto diário vira 429.
    Exige usuário aprovado (a extração custa uma chamada de LLM).
    """
    if not (arquivo.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Envie um arquivo PDF.")

    conteudo = await arquivo.read()
    limite_bytes = settings.UPLOAD_MAX_MB * 1024 * 1024
    if len(conteudo) > limite_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"Arquivo acima do limite de {settings.UPLOAD_MAX_MB} MB.",
        )

    # Teto POR USUÁRIO + auditoria da extração (reserva a cota antes do LLM).
    try:
        await reservar_extracao(usuario.id, arquivo.filename or "sem-nome.pdf")
    except LimiteExcedido as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    try:
        return await run_in_threadpool(extrair_transacoes, conteudo, senha)
    except ValueError as exc:  # PDF protegido / senha incorreta
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — superfície única de erro p/ o cliente
        raise HTTPException(status_code=502, detail=f"Falha ao ler a fatura: {exc}") from exc


@router.post("/salvar", response_model=SalvarFaturasOut)
async def salvar(
    payload: SalvarFaturasIn,
    usuario: Usuario = Depends(get_current_user),
) -> SalvarFaturasOut:
    """Persiste o lote conferido COMO DO USUÁRIO corrente, ignorando duplicatas."""
    try:
        transacoes = [t.model_dump() for t in payload.transacoes]
        resumo = await salvar_transacoes(usuario.id, transacoes)
        await registrar_evento(usuario.id, EVENTO_UPLOAD_SAVE, resumo)
        return SalvarFaturasOut(**resumo)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha ao salvar: {exc}") from exc


@router.get("", response_model=list[GastoCru])
async def listar_crus(usuario: Usuario = Depends(get_current_user)) -> list[GastoCru]:
    """Lista as transações cruas (com ``id``) DO USUÁRIO, sem tratamento, para edição."""
    return await _repo_listar_crus(usuario.id)


@router.post("/editar", response_model=EditarFaturasOut)
async def editar(
    payload: EditarFaturasIn,
    usuario: Usuario = Depends(get_current_user),
) -> EditarFaturasOut:
    """Aplica alterações/exclusões por ``id``, restritas ao dono, numa transação só.

    O ``user_id`` entra no ``WHERE`` do update/delete (spec §4): id alheio não casa.
    Uma edição que faça duas transações do usuário ficarem idênticas em
    (data, descrição, valor) viola o índice único e retorna 409.
    """
    try:
        alteracoes = [a.model_dump() for a in payload.alteracoes]
        resumo = await atualizar_e_excluir(usuario.id, alteracoes, payload.exclusoes)
        return EditarFaturasOut(**resumo)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="A edição deixaria duas transações idênticas (data, descrição e valor).",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha ao editar: {exc}") from exc
