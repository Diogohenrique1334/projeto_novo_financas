"""Extração de transações de fatura via modelo com visão + saída estruturada.

Fluxo (spec §6): PDF (bytes) → imagens PNG → chamada ao modelo com as imagens e
o schema canônico como ``response_format`` → lista de transações estruturadas.
Robusto a layouts/bancos distintos; a conferência humana antes de salvar é a
rede de segurança contra extração imperfeita.
"""

import logging
from typing import Optional

from openai import OpenAI

from config import settings
from services.extracao.prompt import SISTEMA, USUARIO
from services.extracao.render_pdf import pdf_para_imagens
from services.extracao.schema_canonico import FaturaExtraida

logger = logging.getLogger(__name__)


def _client() -> OpenAI:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY não configurado.")
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def _bloco_imagens(imagens_b64: list[str]) -> list[dict]:
    conteudo: list[dict] = [{"type": "text", "text": USUARIO}]
    for b64 in imagens_b64:
        conteudo.append(
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
        )
    return conteudo


def extrair_de_pdf(conteudo: bytes, senha: Optional[str] = None) -> list[dict]:
    """Extrai as transações de um PDF de fatura como dicts do schema canônico.

    Levanta ``ValueError`` para PDF inválido/protegido (vira 400 na API). Demais
    falhas (modelo, rede) propagam para o router tratar como 502.
    """
    imagens = pdf_para_imagens(
        conteudo,
        senha=senha,
        dpi=settings.EXTRACT_DPI,
        max_paginas=settings.EXTRACT_MAX_PAGINAS,
    )
    if not imagens:
        return []

    logger.info("Extraindo fatura com %s (%d página[s]).", settings.EXTRACT_MODEL, len(imagens))
    resposta = _client().chat.completions.parse(
        model=settings.EXTRACT_MODEL,
        messages=[
            {"role": "system", "content": SISTEMA},
            {"role": "user", "content": _bloco_imagens(imagens)},
        ],
        response_format=FaturaExtraida,
    )

    mensagem = resposta.choices[0].message
    if getattr(mensagem, "refusal", None):
        raise RuntimeError(f"Modelo recusou a extração: {mensagem.refusal}")

    fatura = mensagem.parsed
    if fatura is None:
        return []
    return [t.model_dump() for t in fatura.transacoes]
