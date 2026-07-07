"""Schema canônico de transação (spec §6) — saída estruturada do modelo de visão.

Campos obrigatórios: ``date``, ``descricao``, ``amount``.
Opcionais (muitas faturas não têm): ``parcelas``, ``categoria``, ``cidade``.

``date`` sai do modelo como string ISO (``YYYY-MM-DD``) — a conversão para
``datetime.date`` e o descarte de datas inválidas ficam na camada de serviço,
para tolerar formatos distintos sem quebrar a chamada estruturada.
"""

from typing import Optional

from pydantic import BaseModel, Field


class TransacaoCanonica(BaseModel):
    """Uma transação lida da fatura, em formato neutro de banco."""

    date: str = Field(
        description=(
            "Data da transação em ISO 8601 (YYYY-MM-DD). Se a linha só tiver dia/mês, "
            "use o ANO do período/vencimento da fatura. Nunca invente datas."
        )
    )
    descricao: str = Field(
        description="Descrição/estabelecimento exatamente como aparece na fatura."
    )
    amount: float = Field(
        description=(
            "Valor da transação como número decimal com ponto (ex.: 1234.56). "
            "Converta vírgula decimal e separador de milhar. Despesa é positiva."
        )
    )
    parcelas: Optional[str] = Field(
        default=None,
        description=(
            "Se for compra parcelada, a parcela no formato NN/NN (ex.: 01/03). "
            "Null quando não houver parcelamento."
        ),
    )
    categoria: Optional[str] = Field(
        default=None,
        description=(
            "Categoria da despesa se claramente inferível (ex.: Alimentação, "
            "Transporte, Moradia, Saúde, Lazer, Compras, Serviços, Educação). "
            "Null se incerto."
        ),
    )
    cidade: Optional[str] = Field(
        default=None,
        description="Cidade da compra se aparecer na fatura. Null quando não houver.",
    )


class FaturaExtraida(BaseModel):
    """Todas as transações extraídas de uma fatura (possivelmente multipágina)."""

    transacoes: list[TransacaoCanonica]
