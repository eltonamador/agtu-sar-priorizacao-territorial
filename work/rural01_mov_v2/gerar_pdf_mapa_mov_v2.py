#!/usr/bin/env python3
"""Converte o mapa MOV-V v2 em PDF A3 paisagem para leitura e impressão."""

from pathlib import Path

from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "outputs/campo_rural01/processamento_movimento_cego_v2"
PNG = OUTPUT_DIR / "Mapa_RURAL01_Resistencia_Corredores_MOV_V_v2.png"
PDF = OUTPUT_DIR / "Mapa_RURAL01_Resistencia_Corredores_MOV_V_v2.pdf"


def main() -> int:
    width, height = landscape(A3)
    document = canvas.Canvas(str(PDF), pagesize=(width, height), pageCompression=1)
    document.setTitle("RURAL-01 — resistência territorial e conectividade MOV-V v2")
    document.setAuthor("Francielton Amador")
    document.setSubject("Mapa cego de acessibilidade física relativa; posição verdadeira não utilizada")
    document.drawImage(ImageReader(str(PNG)), 0, 0, width=width, height=height, preserveAspectRatio=True)
    document.showPage()
    document.save()
    print(PDF)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
