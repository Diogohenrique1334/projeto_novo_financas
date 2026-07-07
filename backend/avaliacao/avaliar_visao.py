"""Harness de avaliação da extração por visão (spec §6).

Roda o extrator sobre cada fatura sintética do golden set e reporta:
  * recall (quantas transações esperadas foram encontradas);
  * falsos positivos (extraídas que não casam com nenhuma esperada);
  * acurácia POR CAMPO (date, descricao, amount, parcelas, cidade) sobre os pares
    casados.

Casamento: cada esperada casa com a extraída de mesmo ``amount`` (tolerância de
1 centavo) e data mais próxima. Determinístico e simples — golden set é controlado.

Uso:  cd backend && python avaliacao/avaliar_visao.py
      (chama a OpenAI de verdade; custo de centavos)
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from services.upload_service import extrair_transacoes

GOLDEN = Path(__file__).resolve().parent / "golden_set"
CAMPOS = ["date", "descricao", "amount", "parcelas", "cidade"]


def _norm_texto(v) -> str:
    return " ".join(str(v).split()).casefold() if v not in (None, "") else ""


def _norm_data(v) -> str:
    try:
        return date.fromisoformat(str(v)[:10]).isoformat()
    except Exception:  # noqa: BLE001
        return str(v)


def _igual(campo: str, esperado, obtido) -> bool:
    if campo == "amount":
        try:
            return abs(float(esperado) - float(obtido)) < 0.01
        except (TypeError, ValueError):
            return False
    if campo == "date":
        return _norm_data(esperado) == _norm_data(obtido)
    # descricao / parcelas / cidade — comparação textual normalizada (null == null)
    return _norm_texto(esperado) == _norm_texto(obtido)


def _casar(esperadas: list[dict], obtidas: list[dict]) -> list[tuple[dict, dict | None]]:
    """Casa cada esperada com uma obtida (mesmo amount, data mais próxima)."""
    livres = list(obtidas)
    pares: list[tuple[dict, dict | None]] = []
    for esp in esperadas:
        candidatos = [
            o for o in livres
            if o.get("amount") is not None
            and abs(float(o["amount"]) - float(esp["amount"])) < 0.01
        ]
        if not candidatos:
            pares.append((esp, None))
            continue

        def _dist(o):
            try:
                return abs(
                    date.fromisoformat(_norm_data(o["date"])).toordinal()
                    - date.fromisoformat(_norm_data(esp["date"])).toordinal()
                )
            except Exception:  # noqa: BLE001
                return 10_000

        melhor = min(candidatos, key=_dist)
        livres.remove(melhor)
        pares.append((esp, melhor))
    return pares, livres


def avaliar_fatura(pasta: Path) -> dict:
    esperadas = json.loads((pasta / "esperado.json").read_text(encoding="utf-8"))
    conteudo = (pasta / "fatura.pdf").read_bytes()
    obtidas = extrair_transacoes(conteudo)

    pares, sobras = _casar(esperadas, obtidas)
    encontrados = sum(1 for _, o in pares if o is not None)

    acertos = {c: 0 for c in CAMPOS}
    for esp, obt in pares:
        if obt is None:
            continue
        for c in CAMPOS:
            if _igual(c, esp.get(c), obt.get(c)):
                acertos[c] += 1

    return {
        "banco": pasta.name,
        "esperadas": len(esperadas),
        "extraidas": len(obtidas),
        "encontradas": encontrados,
        "falsos_positivos": len(sobras),
        "acertos": acertos,
    }


def main() -> None:
    pastas = sorted(p for p in GOLDEN.iterdir() if (p / "fatura.pdf").exists())
    if not pastas:
        print("Nenhuma fatura no golden set. Rode os geradores (gerar.py) primeiro.")
        sys.exit(1)

    for pasta in pastas:
        r = avaliar_fatura(pasta)
        print(f"\n=== {r['banco']} ===")
        print(f"  esperadas={r['esperadas']}  extraídas={r['extraidas']}  "
              f"encontradas={r['encontradas']}  falsos_positivos={r['falsos_positivos']}")
        base = max(r["encontradas"], 1)
        print("  acurácia por campo (sobre as casadas):")
        for c in CAMPOS:
            pct = 100 * r["acertos"][c] / base
            print(f"    {c:10} {r['acertos'][c]}/{r['encontradas']}  ({pct:5.1f}%)")


if __name__ == "__main__":
    main()
