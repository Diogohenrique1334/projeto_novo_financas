"""Schemas de resposta da API."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class UsuarioOut(BaseModel):
    """Identidade + autorização do usuário (para ``/me`` e página de admin)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    nome: Optional[str] = None
    role: str
    status: str
    consent_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class StatusUpdateIn(BaseModel):
    """Novo status de um usuário (aprovar/bloquear/reverter) — ação de admin."""

    status: str = Field(..., description="pending | approved | blocked")


class AcaoOut(BaseModel):
    """Resultado de uma ação de admin sobre um usuário."""

    afetados: int


class GastoOut(BaseModel):
    """Um lançamento de fatura já tratado, pronto para o frontend."""

    date: date
    descricao: str
    parcelas: Optional[str] = None
    categoria: Optional[str] = None
    cidade: Optional[str] = None
    amount: float
    Parcelas_pagas: Optional[int] = None
    total_parcelas: Optional[int] = None
    Cidade_sem_tratamento: Optional[str] = None


class TransacaoExtraida(BaseModel):
    """Uma transação lida de uma fatura, ainda não persistida (preview editável)."""

    date: date
    descricao: str
    parcelas: Optional[str] = None
    categoria: Optional[str] = None
    cidade: Optional[str] = None
    amount: float


class SalvarFaturasIn(BaseModel):
    """Lote de transações (possivelmente editadas pelo usuário) para persistir."""

    transacoes: list[TransacaoExtraida] = Field(min_length=1)


class SalvarFaturasOut(BaseModel):
    """Resumo do salvamento de um lote de transações."""

    recebidos: int
    salvos: int
    ignorados: int


class GastoCru(BaseModel):
    """Uma transação como está no banco (com ``id``), sem tratamento — para edição."""

    id: int
    date: date
    descricao: str
    parcelas: Optional[str] = None
    categoria: Optional[str] = None
    cidade: Optional[str] = None
    amount: float


class EditarFaturasIn(BaseModel):
    """Lote de alterações: linhas a atualizar (por ``id``) e ids a excluir."""

    alteracoes: list[GastoCru] = Field(default_factory=list)
    exclusoes: list[int] = Field(default_factory=list)


class EditarFaturasOut(BaseModel):
    """Resumo das alterações aplicadas."""

    atualizados: int
    excluidos: int
