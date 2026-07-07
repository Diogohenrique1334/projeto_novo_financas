"""Audit log de ações relevantes: login e uploads (spec §9).

Registra "quem fez o quê, quando". Também é a fonte de verdade do **teto de
upload por usuário** (conta os eventos de extração do dia). ``ON DELETE CASCADE``
garante que, ao excluir a conta (LGPD), os registros de auditoria do usuário
saem junto.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from database import Base

# Tipos de evento auditados.
EVENTO_LOGIN = "login"
EVENTO_UPLOAD_EXTRACT = "upload_extract"
EVENTO_UPLOAD_SAVE = "upload_save"


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evento = Column(String, nullable=False, index=True)
    meta = Column(Text, nullable=True)  # detalhe livre (ex.: nome do arquivo, contagens)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
