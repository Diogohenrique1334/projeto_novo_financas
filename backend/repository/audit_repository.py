"""Repositório do audit log: registrar eventos e contar uso do dia por usuário."""

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select

from database import async_session
from models.audit import AuditLog


async def registrar_evento(user_id: int, evento: str, meta: Optional[dict] = None) -> None:
    """Grava um evento de auditoria (login/upload/…) para o usuário."""
    async with async_session() as session:
        session.add(
            AuditLog(
                user_id=user_id,
                evento=evento,
                meta=json.dumps(meta, ensure_ascii=False) if meta else None,
            )
        )
        await session.commit()


async def contar_eventos_hoje(user_id: int, evento: str) -> int:
    """Conta quantos eventos de um tipo o usuário gerou hoje (UTC).

    Base do teto de upload por usuário (spec §9): cada extração é um evento.
    """
    inicio_dia = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    async with async_session() as session:
        return await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.user_id == user_id,
                AuditLog.evento == evento,
                AuditLog.created_at >= inicio_dia,
            )
        )
