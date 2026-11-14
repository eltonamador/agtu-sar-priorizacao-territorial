#!/usr/bin/env python3
"""Gera o mapa comparativo pré-revelação do cenário RURAL-01.

A figura usa somente saídas espaciais já congeladas e camadas públicas locais.
Ela não lê, deriva nem representa a posição verdadeira da vítima.
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
URBE_SCRIPT = ROOT / "work/urbe01_processamento_cego_v1/gerar_mapa_urbe01_cego.py"

spec = importlib.util.spec_from_file_location("mapa_urbe_base", URBE_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Não foi possível carregar o módulo-base: {URBE_SCRIPT}")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

OUT = ROOT / "outputs/campo_rural01/processamento_cego_v1"
PROFILE = ROOT / "outputs/campo_rural01/perfil_v2_v3"
GEO = ROOT / "outputs/sprint2_s2_06_geo05_v33"

SECTORS_PATH = OUT / "setores_rural01.geojson"
BASE_TOP3_PATH = OUT / "top3_rural01.csv"
PROFILE_TOP3_PATH = PROFILE / "top3_perfil_v3_rural01.json"
ROADS_PATH = GEO / "osm_highways_raw.json"
HYDRO_PATH = GEO / "osm_hydrography_raw.json"

PNG_PATH = OUT / "Mapa_RURAL01_Previsao_Cega_BASE_PERFIL_v1.png"
PDF_PATH = OUT / "Mapa_RURAL01_Previsao_Cega_BASE_PERFIL_v1.pdf"
README_PATH = OUT / "README_MAPA_RURAL01_PREVISAO_CEGA_v1.md"

LON0 = -51.155556
LAT0 = 0.188611
RADIUS_M = 1500.0
EXTENT_M = 1725.0


def load_profile_top3(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        rows = json.load(handle)
    if not isinstance(rows, list) or len(rows) != 3:
        raise ValueError("Top-3 do perfil deve conter exatamente três áreas.")
    return rows


def create_figure() -> None:
    sectors_doc = base.load_json(SECTORS_PATH)
    features = sectors_doc["features"]
    territorial = base.load_top3(BASE_TOP3_PATH)
    profile = load_profile_top3(PROFILE_TOP3_PATH)

    # Os três setores prioritários ficam próximos no quadrante leste;
    # posicionar os rótulos acima evita sobreposição entre AP1 e AP3.
    for row in territorial + profile:
        row["_map_label_position"] = "ABOVE"

    territorial_ids = [row["sector_id"] for row in territorial]
    profile_ids = [row["sector_id"] for row in profile]
    if territorial_ids != profile_ids:
        raise RuntimeError("O mapa exige conferência: o perfil alterou o Top-3 territorial.")

    lon_delta = math.degrees(EXTENT_M / (base.R_EARTH * math.cos(math.radians(LAT0))))
    lat_delta = math.degrees(EXTENT_M / base.R_EARTH)
    bounds = (LON0 - lon_delta, LAT0 - lat_delta, LON0 + lon_delta, LAT0 + lat_delta)
    roads = base.osm_lines(ROADS_PATH, bounds)
    hydro = base.osm_lines(HYDRO_PATH, bounds)

    image = base.Image.new("RGBA", (base.CANVAS_W, base.CANVAS_H), base.COLORS["paper"])
    draw = base.ImageDraw.Draw(image)

    draw.text(
        (130, 70),
        "RURAL-01: priorização espacial antes da abertura da posição real",
        font=base.font(67, bold=True),
        fill=base.COLORS["ink"],
    )
    draw.text(
        (132, 160),
        "Top-3 territorial preservado; intervalo entre desaparecimento e fotografias corrigido para 14 h",
        font=base.font(34),
        fill=base.COLORS["muted"],
    )
    draw.rounded_rectangle((3320, 70, 3865, 205), 22, fill="#f2e9d2", outline="#b9994d", width=3)
    draw.text((3457, 88), "STATUS", font=base.font(26, bold=True), fill="#725711")
    draw.text((3378, 131), "REVISAR", font=base.font(40, bold=True), fill="#725711")

    base.draw_panel(
        image,
        base.LEFT_X,
        "A. Ranking BASE territorial",
        "GEO-02 a GEO-05; raio final informado pela fonte: 1.500 m.",
        features,
        territorial,
        roads,
        hydro,
        LON0,
        LAT0,
        EXTENT_M,
    )
    base.draw_panel(
        image,
        base.RIGHT_X,
        "B. Saída final PERFIL RURAL-01",
        "Perfil espacial absteve-se; sem pista quantitativa elegível, o Top-3 foi mantido.",
        features,
        profile,
        roads,
        hydro,
        LON0,
        LAT0,
        EXTENT_M,
    )

    legend_y = 2140
    draw.text((145, legend_y), "Legenda", font=base.font(35, bold=True), fill=base.COLORS["ink"])
    x = 350
    for label, color, pattern in [
        ("AP1 — 1ª prioridade", base.COLORS["ap1"], "diagonal"),
        ("AP2 — 2ª prioridade", base.COLORS["ap2"], "pontos"),
        ("AP3 — 3ª prioridade", base.COLORS["ap3"], "cruzado"),
    ]:
        draw.rectangle((x, legend_y - 2, x + 60, legend_y + 48), fill=color, outline=base.COLORS["ink"], width=2)
        if pattern == "diagonal":
            for k in range(-10, 70, 16):
                draw.line((x + k, legend_y + 48, x + k + 50, legend_y - 2), fill="white", width=3)
        elif pattern == "pontos":
            for yy in (legend_y + 12, legend_y + 34):
                for xx in (x + 15, x + 35, x + 55):
                    draw.ellipse((xx - 3, yy - 3, xx + 3, yy + 3), fill="white")
        else:
            for k in range(-10, 70, 16):
                draw.line((x + k, legend_y + 48, x + k + 50, legend_y - 2), fill="white", width=3)
                draw.line((x + k, legend_y - 2, x + k + 50, legend_y + 48), fill="white", width=3)
        draw.text((x + 78, legend_y + 2), label, font=base.font(28), fill=base.COLORS["ink"])
        x += 600

    y2 = 2215
    draw.line((350, y2 + 19, 415, y2 + 19), fill=base.COLORS["road_major"], width=6)
    draw.text((435, y2), "vias OSM", font=base.font(26), fill=base.COLORS["ink"])
    draw.line((650, y2 + 19, 715, y2 + 19), fill=base.COLORS["hydro"], width=6)
    draw.text((735, y2), "hidrografia OSM", font=base.font(26), fill=base.COLORS["ink"])
    draw.ellipse((1065, y2 - 1, 1109, y2 + 43), fill="white", outline=base.COLORS["origin"], width=6)
    draw.line((1057, y2 + 21, 1117, y2 + 21), fill=base.COLORS["origin"], width=5)
    draw.text((1134, y2), "E0 = ponto inicial recebido", font=base.font(26), fill=base.COLORS["ink"])
    draw.text((1680, y2), "Raio: 1.500 m  |  24 setores de área equivalente", font=base.font(26), fill=base.COLORS["ink"])

    note = (
        "Nota. Composição cartográfica do processamento cego RURAL-01. As vias e a hidrografia provêm do "
        "OpenStreetMap (© OpenStreetMap contributors, ODbL); o ranking utiliza também SRTMGL1/Mapzen e ESA "
        "WorldCover 2021 v200. São fontes públicas, "
        "não levantamento de campo. O intervalo de 14 h foi informado pelo operador, mas não foi reaplicado ao "
        "buffer porque o raio de 1.500 m foi recebido como raio final ajustado pela fonte. A posição real não foi "
        "utilizada nem representada. A pista Norte, o perfil e as fotografias não alteraram quantitativamente este "
        "ranking. AP1–AP3 indicam prioridade analítica, não probabilidade de presença ou localização determinada. "
        "O status REVISAR decorre da margem baixa e da instabilidade entre ponderações."
    )
    draw.line((130, 2310, 3870, 2310), fill="#cbc6bc", width=3)
    base.multiline(
        draw,
        (145, 2340),
        note,
        fnt=base.font(23),
        fill=base.COLORS["muted"],
        max_width=3700,
        line_spacing=6,
    )

    rgb = image.convert("RGB")
    rgb.save(PNG_PATH, format="PNG", dpi=(300, 300), optimize=True)

    page_w, page_h = base.landscape(base.A3)
    pdf = base.canvas.Canvas(str(PDF_PATH), pagesize=(page_w, page_h))
    margin = 18
    available_w = page_w - 2 * margin
    available_h = page_h - 2 * margin
    ratio = base.CANVAS_W / base.CANVAS_H
    draw_w = available_w
    draw_h = draw_w / ratio
    if draw_h > available_h:
        draw_h = available_h
        draw_w = draw_h * ratio
    pdf.drawImage(
        str(PNG_PATH),
        (page_w - draw_w) / 2,
        (page_h - draw_h) / 2,
        width=draw_w,
        height=draw_h,
        preserveAspectRatio=True,
        mask="auto",
    )
    pdf.showPage()
    pdf.save()

    readme = f"""# Mapa RURAL-01 — previsão/priorização cega v1

Arquivos:

- `{PNG_PATH.name}`: figura em 4.000 × 2.550 px, 300 dpi;
- `{PDF_PATH.name}`: exportação A3 horizontal;
- script reprodutível: `{Path(__file__).name}`.

## Leitura

- E0: ponto inicial recebido pelo sistema;
- AP1, AP2 e AP3: áreas priorizadas, na ordem do ranking;
- R01, R02 e R03: anéis interno, intermediário e externo;
- N, NE, E, SE, S, SW, W e NW: direções dos setores;
- o painel B repete o Top-3 porque o módulo de perfil se absteve de alterar o ranking sem pista espacial quantitativamente elegível;
- a posição verdadeira não foi lida nem representada.

## Correção temporal

O intervalo entre desaparecimento e fotografias foi corrigido para 14 h. Essa correção não altera o Top-3 porque o raio de 1.500 m foi recebido como raio final ajustado pela fonte e o tempo não participou numericamente do ranking espacial congelado.

## Contexto cartográfico

A figura usa camadas públicas do OpenStreetMap (© OpenStreetMap contributors, ODbL), SRTMGL1/Mapzen e ESA WorldCover 2021 v200. Não representa levantamento de campo. A pista Norte, o perfil e as fotografias não alteraram quantitativamente o ranking congelado. AP1–AP3 expressam prioridade analítica para revisão humana, não probabilidade de presença.
"""
    README_PATH.write_text(readme, encoding="utf-8")

    print(PNG_PATH)
    print(PDF_PATH)
    print(README_PATH)
    print(f"contexto: {len(roads)} vias, {len(hydro)} feições hidrográficas")


if __name__ == "__main__":
    create_figure()
