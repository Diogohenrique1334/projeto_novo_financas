"""Repositório de usuários: cadastro, bootstrap de admin e gestão de status.

O ``get_or_create_por_email`` é o ponto onde a política de autorização nasce:
e-mails em ``ADMIN_EMAILS`` viram admin aprovado; os demais nascem ``pending``
até o admin aprovar (spec §3).
"""

from typing import Optional

from sqlalchemy import delete, select, update

from config import settings
from database import async_session
from models.usuario import Usuario


async def get_or_create_por_email(email: str, nome: Optional[str] = None) -> Usuario:
    """Busca o usuário pelo e-mail; cria se não existir. Aplica bootstrap de admin.

    - E-mail em ``ADMIN_EMAILS`` → nasce (ou é promovido a) ``role='admin'`` e
      ``status='approved'``. Idempotente: se o e-mail for adicionado à lista
      depois, o próximo login promove.
    - Demais e-mails → nascem ``role='user'``, ``status='pending'``.
    """
    email_norm = email.strip().lower()
    e_admin = email_norm in settings.admin_emails

    async with async_session() as session:
        result = await session.execute(select(Usuario).where(Usuario.email == email_norm))
        usuario = result.scalar_one_or_none()

        if usuario is None:
            usuario = Usuario(
                email=email_norm,
                nome=nome,
                role="admin" if e_admin else "user",
                status="approved" if e_admin else "pending",
            )
            session.add(usuario)
        elif e_admin and (usuario.role != "admin" or usuario.status != "approved"):
            # Promoção idempotente de um admin adicionado à lista posteriormente.
            usuario.role = "admin"
            usuario.status = "approved"

        await session.commit()
        await session.refresh(usuario)
        return usuario


async def buscar_por_id(user_id: int) -> Optional[Usuario]:
    async with async_session() as session:
        return await session.get(Usuario, user_id)


async def definir_consentimento(user_id: int) -> Optional[Usuario]:
    """Carimba o consentimento LGPD (``consent_at = agora``) do usuário."""
    from datetime import datetime, timezone

    async with async_session() as session:
        usuario = await session.get(Usuario, user_id)
        if usuario is None:
            return None
        usuario.consent_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(usuario)
        return usuario


async def listar_usuarios() -> list[Usuario]:
    """Lista todos os usuários, mais recentes primeiro (para a página de admin)."""
    async with async_session() as session:
        result = await session.execute(select(Usuario).order_by(Usuario.created_at.desc()))
        return list(result.scalars().all())


async def definir_status(user_id: int, status: str) -> int:
    """Aprova/bloqueia/reverte um usuário. Retorna linhas afetadas (0 se inexistente)."""
    async with async_session() as session:
        res = await session.execute(
            update(Usuario).where(Usuario.id == user_id).values(status=status)
        )
        await session.commit()
        return res.rowcount


async def remover_usuario(user_id: int) -> int:
    """Remove o usuário (e, por CASCADE, todas as suas transações — LGPD, spec §9)."""
    async with async_session() as session:
        res = await session.execute(delete(Usuario).where(Usuario.id == user_id))
        await session.commit()
        return res.rowcount
