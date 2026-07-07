"""Render de PDF de fatura em imagens PNG (base64), para o modelo de visão.

Usa PyMuPDF (``fitz``) — sem dependência de sistema (não precisa de poppler),
então roda igual no Windows e no container de deploy. Decripta PDFs protegidos
por senha e limita o número de páginas (proteção de custo/token).
"""

import base64
from typing import Optional

import fitz  # PyMuPDF


def pdf_para_imagens(
    conteudo: bytes,
    senha: Optional[str] = None,
    dpi: int = 150,
    max_paginas: int = 12,
) -> list[str]:
    """Converte os bytes de um PDF numa lista de PNGs base64 (uma por página).

    Args:
        conteudo: bytes do PDF.
        senha: senha, se o PDF for protegido.
        dpi: resolução do render (maior = mais nítido e mais tokens).
        max_paginas: teto de páginas processadas.

    Raises:
        ValueError: PDF protegido sem senha correta, ou arquivo inválido.
    """
    try:
        doc = fitz.open(stream=conteudo, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 — arquivo inválido → 400 na API
        raise ValueError(f"PDF inválido: {exc}") from exc

    try:
        if doc.needs_pass:
            if not senha or not doc.authenticate(senha):
                raise ValueError("PDF protegido ou senha incorreta.")

        imagens: list[str] = []
        for indice in range(min(doc.page_count, max_paginas)):
            pagina = doc.load_page(indice)
            pix = pagina.get_pixmap(dpi=dpi)
            imagens.append(base64.b64encode(pix.tobytes("png")).decode("ascii"))
        return imagens
    finally:
        doc.close()
