"""Ponto de entrada da API FastAPI do SaaS de análise de faturas.

Executar a partir do diretório ``backend/``:

    uvicorn app.main_api:app --port 8001 --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import models  # noqa: F401 — registra Usuario/Transacao em Base.metadata p/ create_tables
from app.routers import faturas, gastos, usuarios
from config import settings
from database import create_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cria as tabelas (idempotente) no startup — beta de instância única."""
    await create_tables()
    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origem.strip() for origem in settings.ALLOWED_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(usuarios.router)
app.include_router(gastos.router)
app.include_router(faturas.router)


@app.get("/health", tags=["infra"])
def health() -> dict:
    """Healthcheck simples para orquestração/monitoramento."""
    return {"status": "ok"}
