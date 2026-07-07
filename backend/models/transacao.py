"""Modelo de transação de fatura, isolada por usuário (multi-tenant row-level).

Toda linha carrega o ``user_id`` do dono (spec §7): leitura e escrita SEMPRE
filtram por ele. A FK usa ``ON DELETE CASCADE`` para o "excluir minha conta e
meus dados" da LGPD (spec §9) apagar as transações junto com o usuário.
"""

from sqlalchemy import Column, Date, Float, ForeignKey, Integer, String, UniqueConstraint

from database import Base


class Transacao(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # FK não é indexada automaticamente no Postgres; filtramos sempre por ela.
    )
    date = Column(Date, nullable=False)
    descricao = Column(String, nullable=False)
    # Opcionais no schema canônico (spec §6): faturas de bancos distintos variam.
    parcelas = Column(String, nullable=True)
    categoria = Column(String, nullable=True)
    cidade = Column(String, nullable=True)  # muitas faturas não têm cidade.
    amount = Column(Float, nullable=False)

    __table_args__ = (
        # Unicidade por DONO (spec §7): o user_id na chave impede que a fatura de
        # um usuário deduplique contra a de outro; `parcelas` na chave impede que
        # parcelas distintas da mesma compra (01/10, 02/10, …) colidam.
        # NULLS NOT DISTINCT (Postgres 15+): trata `parcelas IS NULL` como igual,
        # senão o ON CONFLICT nunca dispararia para transações sem parcelamento.
        UniqueConstraint(
            "user_id",
            "date",
            "descricao",
            "parcelas",
            "amount",
            name="uq_transacao_user",
            postgresql_nulls_not_distinct=True,
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - conveniência de debug
        return (
            f"<Transacao id={self.id} user_id={self.user_id} "
            f"date={self.date} amount={self.amount}>"
        )
