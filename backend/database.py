"""Engine assíncrona, sessão e base declarativa.

A `DATABASE_URL` chega no formato libpq (o mesmo que o `psql`/Neon entregam):
``postgresql://user:pass@host/db?sslmode=require&channel_binding=require``.
O driver assíncrono (asyncpg) não entende ``sslmode``/``channel_binding`` e o
endpoint ``-pooler`` do Neon é um PgBouncer em modo transação, que quebra com o
cache de prepared statements do asyncpg. A normalização abaixo resolve os dois:

  * troca o esquema para ``postgresql+asyncpg``;
  * remove os parâmetros específicos do libpq da query string;
  * injeta ``ssl`` (Neon exige TLS) e ``statement_cache_size=0`` (pooler-safe).
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

# Parâmetros de conexão que só o libpq entende — o asyncpg os rejeitaria.
_PARAMS_LIBPQ = {"sslmode", "channel_binding"}


def _normalizar_url_async(url: str) -> str:
    """Converte uma URL de Postgres libpq para o dialeto SQLAlchemy+asyncpg.

    Idempotente para URLs já em ``postgresql+asyncpg`` e transparente para SQLite
    (usado em testes). Só mexe no esquema e limpa a query dos params do libpq.
    """
    partes = urlsplit(url)
    esquema = partes.scheme
    if esquema in ("postgres", "postgresql"):
        esquema = "postgresql+asyncpg"

    query = [(k, v) for k, v in parse_qsl(partes.query) if k not in _PARAMS_LIBPQ]
    return urlunsplit((esquema, partes.netloc, partes.path, urlencode(query), partes.fragment))


DATABASE_URL = _normalizar_url_async(settings.DATABASE_URL)
_e_postgres = "postgresql" in DATABASE_URL

_engine_kwargs: dict = {"echo": settings.DEBUG}
if _e_postgres:
    _engine_kwargs.update(
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        # ssl: Neon exige TLS. statement_cache_size=0: obrigatório sob PgBouncer
        # (endpoint -pooler), senão prepared statements colidem entre conexões.
        connect_args={"ssl": True, "statement_cache_size": 0},
    )

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base declarativa para todos os modelos."""

    pass


async def get_db():
    """Dependency que fornece uma sessão de banco de dados."""
    async with async_session() as session:
        yield session


async def create_tables():
    """Cria todas as tabelas no banco de dados (idempotente)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
