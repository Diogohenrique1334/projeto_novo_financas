"""Client HTTP para o serviço backend (FastAPI).

TODA chamada leva a asserção interna (``Authorization: Bearer``) cunhada em
``auth.sessao`` — sem ela o backend responde 401. O backend deriva o ``user_id``
do token verificado, então este client nunca envia ``user_id`` (spec §4).
"""

from typing import Optional

import httpx
import pandas as pd
import streamlit as st

from auth.sessao import headers_auth
from config import settings


def _base_url() -> str:
    """URL do backend garantindo o esquema http(s).

    O Render injeta o endereço interno como ``host:port`` (sem esquema); aqui
    normalizamos para uma URL válida sem quebrar o default local já completo.
    """
    url = settings.BACKEND_URL
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"
    return url.rstrip("/")


def buscar_me() -> dict:
    """Identidade + status do usuário corrente (``/usuarios/me``). Não cacheado."""
    resposta = httpx.get(f"{_base_url()}/usuarios/me", headers=headers_auth(), timeout=30)
    resposta.raise_for_status()
    return resposta.json()


def dar_consentimento() -> dict:
    """Registra o consentimento LGPD do usuário corrente."""
    resposta = httpx.post(f"{_base_url()}/usuarios/me/consent", headers=headers_auth(), timeout=30)
    resposta.raise_for_status()
    return resposta.json()


def registrar_login() -> None:
    """Audita um login (uma vez por sessão)."""
    resposta = httpx.post(f"{_base_url()}/usuarios/eventos/login", headers=headers_auth(), timeout=30)
    resposta.raise_for_status()


def excluir_minha_conta() -> dict:
    """Exclui a conta do usuário corrente e todos os seus dados (cascade)."""
    resposta = httpx.delete(f"{_base_url()}/usuarios/me", headers=headers_auth(), timeout=30)
    resposta.raise_for_status()
    return resposta.json()


def listar_usuarios() -> list[dict]:
    """Lista todos os usuários (admin). Não cacheado."""
    resposta = httpx.get(f"{_base_url()}/usuarios", headers=headers_auth(), timeout=30)
    resposta.raise_for_status()
    return resposta.json()


def mudar_status_usuario(user_id: int, status: str) -> dict:
    """Aprova/bloqueia/reverte um usuário (admin)."""
    resposta = httpx.patch(
        f"{_base_url()}/usuarios/{user_id}/status",
        json={"status": status},
        headers=headers_auth(),
        timeout=30,
    )
    resposta.raise_for_status()
    return resposta.json()


def remover_usuario(user_id: int) -> dict:
    """Remove um usuário e suas transações (admin)."""
    resposta = httpx.delete(
        f"{_base_url()}/usuarios/{user_id}", headers=headers_auth(), timeout=30
    )
    resposta.raise_for_status()
    return resposta.json()


@st.cache_data(ttl=settings.CACHE_TTL)
def get_gastos(user_email: str) -> pd.DataFrame:
    """Busca os gastos tratados DO USUÁRIO e devolve um DataFrame pronto p/ análise.

    ``user_email`` é a CHAVE DE CACHE por usuário: sem ele, ``st.cache_data`` seria
    global entre sessões e um usuário veria o cache de outro (vazamento tenant).
    O e-mail não vai no request — a identidade é a asserção; ele só isola o cache.
    """
    resposta = httpx.get(f"{_base_url()}/gastos", headers=headers_auth(), timeout=60)
    resposta.raise_for_status()

    df = pd.DataFrame(resposta.json())
    if df.empty:
        return df

    df["date"] = pd.to_datetime(df["date"])
    for coluna in ("categoria", "cidade"):
        df[coluna] = df[coluna].astype("category")

    return df


def extrair_fatura(arquivo_bytes: bytes, nome_arquivo: str, senha: Optional[str] = None) -> list[dict]:
    """Envia um PDF de fatura ao backend e devolve as transações extraídas (preview).

    Não persiste nada: o usuário ainda vai conferir/editar antes de salvar. O
    timeout é generoso porque a extração depende de uma chamada de LLM com retries.

    Args:
        arquivo_bytes: conteúdo binário do PDF.
        nome_arquivo: nome original (usado para validar a extensão no backend).
        senha: senha do PDF, se protegido.

    Returns:
        Lista de dicts com ``date``, ``descricao``, ``parcelas``, ``categoria``,
        ``cidade``, ``amount``.
    """
    files = {"arquivo": (nome_arquivo, arquivo_bytes, "application/pdf")}
    data = {"senha": senha} if senha else None
    resposta = httpx.post(
        f"{_base_url()}/faturas/extrair",
        files=files,
        data=data,
        headers=headers_auth(),
        timeout=180,
    )
    resposta.raise_for_status()
    return resposta.json()


def salvar_fatura(transacoes: list[dict]) -> dict:
    """Persiste o lote de transações já conferido e devolve o resumo do salvamento.

    Returns:
        dict ``SalvarFaturasOut`` (``recebidos``, ``salvos``, ``ignorados``).
    """
    resposta = httpx.post(
        f"{_base_url()}/faturas/salvar",
        json={"transacoes": transacoes},
        headers=headers_auth(),
        timeout=60,
    )
    resposta.raise_for_status()
    return resposta.json()


def listar_gastos_crus() -> list[dict]:
    """Busca as transações cruas (com ``id``) do usuário para o editor de gerenciamento.

    Diferente de :func:`get_gastos`, traz o dado SEM tratamento e com a PK, pois
    a edição precisa operar sobre a fonte da verdade. Não é cacheado.
    """
    resposta = httpx.get(f"{_base_url()}/faturas", headers=headers_auth(), timeout=60)
    resposta.raise_for_status()
    return resposta.json()


def editar_gastos(alteracoes: list[dict], exclusoes: list[int]) -> dict:
    """Aplica alterações e exclusões de transações e devolve o resumo.

    Returns:
        dict ``EditarFaturasOut`` (``atualizados``, ``excluidos``).
    """
    resposta = httpx.post(
        f"{_base_url()}/faturas/editar",
        json={"alteracoes": alteracoes, "exclusoes": exclusoes},
        headers=headers_auth(),
        timeout=60,
    )
    resposta.raise_for_status()
    return resposta.json()
