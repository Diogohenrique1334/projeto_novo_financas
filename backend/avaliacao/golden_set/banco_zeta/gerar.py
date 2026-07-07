"""Gera uma fatura SINTÉTICA (banco fictício, zero PII) + o ground truth.

Layout deliberadamente diferente do Bradesco: colunas próprias, valores em
formato brasileiro (vírgula decimal, separador de milhar), datas só dia/mês com
o ano vindo do vencimento no cabeçalho. Serve para medir a acurácia da extração
genérica sem usar nenhum dado real.

Uso:  cd backend && python avaliacao/golden_set/banco_zeta/gerar.py
Gera, ao lado deste arquivo: ``fatura.pdf`` e ``esperado.json``.
"""

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

AQUI = Path(__file__).resolve().parent
ANO = 2026  # inferível do "Vencimento: 10/03/2026"

# Ground truth — (dia/mês, descrição, cidade|None, parcela|None, valor_float)
TRANSACOES = [
    ("15/02", "SUPERMERCADO OK", "SAO PAULO", None, 245.90),
    ("16/02", "POSTO SHELL", "CAMPINAS", None, 180.00),
    ("18/02", "MAGAZINE LUIZA", None, "01/10", 1299.99),
    ("20/02", "NETFLIX.COM", None, None, 55.90),
    ("22/02", "DROGARIA SP", "SAO PAULO", None, 34.50),
    ("25/02", "UBER *TRIP", "RIO DE JANEIRO", None, 23.45),
    ("01/03", "AMAZON BR", None, "02/03", 89.90),
]


def _brl(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def gerar_pdf(caminho: Path) -> None:
    estilos = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(caminho), pagesize=A4,
                            topMargin=20 * mm, bottomMargin=20 * mm)
    elems = [
        Paragraph("<b>Banco Zeta — Cartão Platinum</b>", estilos["Title"]),
        Paragraph("Fatura mensal · Vencimento: 10/03/2026 · Total: R$ 1.929,64",
                  estilos["Normal"]),
        Spacer(1, 8 * mm),
    ]
    linhas = [["Data", "Descrição", "Cidade", "Parcela", "Valor (R$)"]]
    for dia, desc, cidade, parc, valor in TRANSACOES:
        linhas.append([dia, desc, cidade or "", parc or "", _brl(valor)])

    tabela = Table(linhas, colWidths=[18 * mm, 55 * mm, 40 * mm, 20 * mm, 30 * mm])
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222222")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("ALIGN", (4, 1), (4, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]))
    elems.append(tabela)
    doc.build(elems)


def gerar_esperado(caminho: Path) -> None:
    esperado = []
    for dia, desc, cidade, parc, valor in TRANSACOES:
        d, m = dia.split("/")
        esperado.append({
            "date": f"{ANO}-{m}-{d}",
            "descricao": desc,
            "cidade": cidade,
            "parcelas": parc,
            "amount": valor,
        })
    caminho.write_text(json.dumps(esperado, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    gerar_pdf(AQUI / "fatura.pdf")
    gerar_esperado(AQUI / "esperado.json")
    print(f"Gerado: {AQUI/'fatura.pdf'}")
    print(f"Gerado: {AQUI/'esperado.json'}")
