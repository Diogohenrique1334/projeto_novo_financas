"""Client HTTP para o serviço backend (FastAPI).

TODA chamada leva a asserção interna (``Authorization: Bearer``) cunhada em
``auth.sessao`` — sem ela o backend responde 401. O backend deriva o ``user_id``
do token verificado, então este client nunca envia ``user_id`` (spec §4).
"""

import time
from typing import Optional

import httpx
import pandas as pd
import streamlit as st

from auth.sessao import headers_auth
from config import settings

# No free tier do Render o serviço HIBERNA após ~15 min ocioso. A primeira chamada
# acorda o backend e pode levar ~30-60s, com o proxy devolvendo 502/503/504 no
# meio do boot. Sem retry, todo primeiro acesso do dia quebra na cara do usuário.
_STATUS_ACORDANDO = {502, 503, 504}
_TENTATIVAS = 5
_TIMEOUT_PADRAO = 90.0


def _base_url() -> str:
    """URL do backend garantindo o esquema http(s).

    O Render injeta o endereço interno como ``host:port`` (sem esquema); aqui
    normalizamos para uma URL válida sem quebrar o default local já completo.
    """
    url = settings.BACKEND_URL
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"
    return url.rstrip("/")


def _requisitar(
    metodo: str,
    caminho: str,
    *,
    timeout: float = _TIMEOUT_PADRAO,
    retry_5xx: bool = True,
    **kwargs,
) -> httpx.Response:
    """Chama o backend tolerando o cold start do free tier.

    Reententa com backoff exponencial em falha de conexão/timeout (não chegou ao
    servidor) e, se ``retry_5xx``, também em 502/503/504 (serviço acordando).
    Erros de aplicação (401, 403, 404, 409, 422…) sobem NA HORA, sem retry, para
    o chamador tratar — o guard depende disso para detectar 401.

    ``retry_5xx=False`` é usado na extração: um 5xx pode ter vindo DEPOIS de o
    LLM já ter rodado, e reententar cobraria a chamada de novo.
    """
    url = f"{_base_url()}{caminho}"
    espera = 2.0
    ultima = _TENTATIVAS - 1

    for tentativa in range(_TENTATIVAS):
        try:
            resposta = httpx.request(metodo, url, timeout=timeout, **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
            if tentativa == ultima:
                raise
        else:
            acordando = retry_5xx and resposta.status_code in _STATUS_ACORDANDO
            if not acordando or tentativa == ultima:
                resposta.raise_for_status()
                return resposta
        time.sleep(espera)
        espera *= 2

    raise RuntimeError("inalcançável")  # pragma: no cover


def buscar_me() -> dict:
    """Identidade + status do usuário corrente (``/usuarios/me``). Não cacheado."""
    return _requisitar("GET", "/usuarios/me", headers=headers_auth()).json()


def dar_consentimento() -> dict:
    """Registra o consentimento LGPD do usuário corrente."""
    return _requisitar("POST", "/usuarios/me/consent", headers=headers_auth()).json()


def registrar_login() -> None:
    """Audita um login (uma vez por sessão)."""
    _requisitar("POST", "/usuarios/eventos/login", headers=headers_auth())


def excluir_minha_conta() -> dict:
    """Exclui a conta do usuário corrente e todos os seus dados (cascade)."""
    return _requisitar("DELETE", "/usuarios/me", headers=headers_auth()).json()


def listar_usuarios() -> list[dict]:
    """Lista todos os usuários (admin). Não cacheado."""
    return _requisitar("GET", "/usuarios", headers=headers_auth()).json()


def mudar_status_usuario(user_id: int, status: str) -> dict:
    """Aprova/bloqueia/reverte um usuário (admin)."""
    return _requisitar(
        "PATCH",
        f"/usuarios/{user_id}/status",
        json={"status": status},
        headers=headers_auth(),
    ).json()


def remover_usuario(user_id: int) -> dict:
    """Remove um usuário e suas transações (admin)."""
    return _requisitar("DELETE", f"/usuarios/{user_id}", headers=headers_auth()).json()


@st.cache_data(ttl=settings.CACHE_TTL)
def get_gastos(user_email: str) -> pd.DataFrame:
    """Busca os gastos tratados DO USUÁRIO e devolve um DataFrame pronto p/ análise.

    ``user_email`` é a CHAVE DE CACHE por usuário: sem ele, ``st.cache_data`` seria
    global entre sessões e um usuário veria o cache de outro (vazamento tenant).
    O e-mail não vai no request — a identidade é a asserção; ele só isola o cache.
    """
    resposta = _requisitar("GET", "/gastos", headers=headers_auth())

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
    # retry_5xx=False: um 5xx pode vir depois de o LLM já ter rodado — reententar
    # cobraria a extração de novo. Só falhas de conexão (não chegou) reententam.
    resposta = _requisitar(
        "POST",
        "/faturas/extrair",
        files=files,
        data=data,
        headers=headers_auth(),
        timeout=180,
        retry_5xx=False,
    )
    return resposta.json()


def salvar_fatura(transacoes: list[dict]) -> dict:
    """Persiste o lote de transações já conferido e devolve o resumo do salvamento.

    Returns:
        dict ``SalvarFaturasOut`` (``recebidos``, ``salvos``, ``ignorados``).
    """
    resposta = _requisitar(
        "POST",
        "/faturas/salvar",
        json={"transacoes": transacoes},
        headers=headers_auth(),
    )
    return resposta.json()


def listar_gastos_crus() -> list[dict]:
    """Busca as transações cruas (com ``id``) do usuário para o editor de gerenciamento.

    Diferente de :func:`get_gastos`, traz o dado SEM tratamento e com a PK, pois
    a edição precisa operar sobre a fonte da verdade. Não é cacheado.
    """
    return _requisitar("GET", "/faturas", headers=headers_auth()).json()


def editar_gastos(alteracoes: list[dict], exclusoes: list[int]) -> dict:
    """Aplica alterações e exclusões de transações e devolve o resumo.

    Returns:
        dict ``EditarFaturasOut`` (``atualizados``, ``excluidos``).
    """
    resposta = _requisitar(
        "POST",
        "/faturas/editar",
        json={"alteracoes": alteracoes, "exclusoes": exclusoes},
        headers=headers_auth(),
    )
    return resposta.json()
