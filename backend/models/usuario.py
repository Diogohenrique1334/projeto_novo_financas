"""Modelo de usuário (conta + autorização por admin).

Autenticação ≠ autorização (spec §3): qualquer conta Google autentica, mas só
quem o admin aprova (``status='approved'``) é autorizado a usar o app.
"""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String

from database import Base

# Domínios permitidos (validados também no banco via CheckConstraint).
ROLES = ("user", "admin")
STATUSES = ("pending", "approved", "blocked")


class Usuario(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False, unique=True, index=True)
    nome = Column(String, nullable=True)
    role = Column(String, nullable=False, default="user")
    # Novo usuário nasce 'pending' — precisa de aprovação do admin (spec §3).
    status = Column(String, nullable=False, default="pending")
    # Consentimento LGPD (spec §9): carimbado no cadastro.
    consent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        CheckConstraint("role in ('user','admin')", name="ck_users_role"),
        CheckConstraint("status in ('pending','approved','blocked')", name="ck_users_status"),
    )

    def __repr__(self) -> str:  # pragma: no cover - conveniência de debug
        return f"<Usuario id={self.id} email={self.email!r} role={self.role} status={self.status}>"
