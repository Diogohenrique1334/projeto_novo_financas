from services.upload_service import extrair_transacoes, salvar_transacoes
from repository.usuarios_repository import get_or_create_por_email
from config import settings
from utils.mover_arquivos import mover_arquivo
from database import create_tables, engine

import os
import asyncio
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent


async def alimentar_banco():

    await create_tables()

    # Ingestão batch é offline e secundária: atrela as faturas ao admin de
    # bootstrap (multi-tenant exige um dono; spec §7). Rode só com faturas suas.
    emails = sorted(settings.admin_emails)
    if not emails:
        raise SystemExit("Defina ADMIN_EMAILS no .env para rodar a ingestão batch.")
    admin = await get_or_create_por_email(emails[0], nome="Admin (bootstrap)")

    caminho = BASE_DIR / "data" / "Faturas_bradesco"
    caminho_bkp = caminho / "bkp"

    pdfs = [x for x in os.listdir(caminho) if x.endswith(".pdf")]

    for pdf in pdfs:
        try:
            logger.info(f"Processando fatura: {pdf}")

            caminho_pdf = caminho / pdf

            # 1️⃣ extrai com o modelo de visão (mesmo núcleo do upload)
            registros = extrair_transacoes(caminho_pdf.read_bytes())

            if not registros:
                logger.warning(f"Fatura {pdf} não gerou dados. Pulando...")
                continue

            # 2️⃣ salva no banco (como do admin)
            resumo = await salvar_transacoes(admin.id, registros)
            logger.info(f"Fatura {pdf} salva ({resumo['salvos']} novas) ✅")

            # 3️⃣ move para backup
            mover_arquivo(
                caminho_origem=str(caminho_pdf),
                caminho_destino=str(caminho_bkp / pdf)
            )

            logger.info(f"Fatura {pdf} movida para bkp 📦")

        except Exception as e:
            logger.error(f"Erro ao processar {pdf}: {e}", exc_info=True)
            # não para o processo — continua nas próximas
            continue

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(alimentar_banco())