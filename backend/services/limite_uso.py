"""Teto de extrações POR USUÁRIO (spec §9), com o audit log como contador.

Substitui o contador global em memória do projeto de referência: num SaaS
multi-tenant o custo tem que ser limitado por dono. Cada extração é um evento
``upload_extract`` no audit; o teto conta os eventos do dia do usuário.
"""

from config import settings
from models.audit import EVENTO_UPLOAD_EXTRACT
from repository.audit_repository import contar_eventos_hoje, registrar_evento


class LimiteExcedido(Exception):
    """Sinaliza que o teto diário de extrações do usuário foi atingido."""

    def __init__(self, limite: int):
        self.limite = limite
        super().__init__(f"Limite diário de {limite} extrações atingido.")


async def reservar_extracao(user_id: int, nome_arquivo: str) -> None:
    """Reserva uma extração para o usuário: valida o teto e já audita o uso.

    Registrar ANTES da chamada de LLM "reserva" a cota — protege o custo mesmo
    que a extração falhe depois. Chamar só após validar tipo/tamanho do arquivo,
    para não gastar cota com um upload obviamente inválido.

    Raises:
        LimiteExcedido: se o usuário já bateu o teto diário.
    """
    usados = await contar_eventos_hoje(user_id, EVENTO_UPLOAD_EXTRACT)
    if usados >= settings.LIMITE_DIARIO_UPLOAD:
        raise LimiteExcedido(settings.LIMITE_DIARIO_UPLOAD)
    await registrar_evento(user_id, EVENTO_UPLOAD_EXTRACT, {"arquivo": nome_arquivo})
