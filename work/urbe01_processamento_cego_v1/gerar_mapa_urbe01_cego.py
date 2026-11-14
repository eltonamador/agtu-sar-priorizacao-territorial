#!/usr/bin/env python3
"""Gera mapa comparativo BASE x PERFIL para o processamento cego URBE-01.

A figura usa apenas as saídas previamente congeladas e as camadas públicas
locais usadas pelo motor. Não lê nem representa posição verdadeira.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/campo_urbe01/processamento_cego_v1"
GEO = ROOT / "outputs/sprint2_s2_06_geo05_v33"

SECTORS_PATH = OUT / "setores_urbe01.geojson"
BASE_PATH = OUT / "top3_base_original.csv"
PROFILE_PATH = OUT / "top3_perfil_urbe01.csv"
ROADS_PATH = GEO / "osm_highways_raw.json"
HYDRO_PATH = GEO / "osm_hydrography_raw.json"

PNG_PATH = OUT / "Mapa_URBE01_Processamento_Cego_BASE_PERFIL_v1.png"
PDF_PATH = OUT / "Mapa_URBE01_Processamento_Cego_BASE_PERFIL_v1.pdf"
README_PATH = OUT / "README_MAPA_URBE01_CEGO_v1.md"

CANVAS_W = 4000
CANVAS_H = 2550
MAP_TOP = 330
PANEL_W = 1820
PANEL_H = 1740
LEFT_X = 130
RIGHT_X = 2050
R_EARTH = 6_371_008.8

FONT_REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_ITALIC = "/System/Library/Fonts/Supplemental/Arial Italic.ttf"

COLORS = {
    "ink": "#263238",
    "muted": "#5f6b70",
    "paper": "#fbfaf7",
    "map": "#f0eee8",
    "grid": "#9aa2a5",
    "road_major": "#9a9084",
    "road_minor": "#c0b9af",
    "hydro": "#4f93ad",
    "ap1": "#1f5f8b",
    "ap2": "#c58a00",
    "ap3": "#d56a32",
    "origin": "#8a1c1c",
}


def font(size: int, bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_ITALIC if italic else FONT_REGULAR
    return ImageFont.truetype(path, size=size)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_top3(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def lonlat_to_m(lon: float, lat: float, lon0: float, lat0: float) -> tuple[float, float]:
    x = R_EARTH * math.cos(math.radians(lat0)) * math.radians(lon - lon0)
    y = R_EARTH * math.radians(lat - lat0)
    return x, y


def iter_lonlat(coords: Any) -> Iterable[tuple[float, float]]:
    if not coords:
        return
    if isinstance(coords[0], (int, float)):
        yield float(coords[0]), float(coords[1])
        return
    for child in coords:
        yield from iter_lonlat(child)


def osm_lines(path: Path, bounds: tuple[float, float, float, float]) -> list[tuple[list[tuple[float, float]], dict[str, str]]]:
    """Lê somente feições lineares que intersectam a caixa do mapa."""
    min_lon, min_lat, max_lon, max_lat = bounds
    doc = load_json(path)
    selected: list[tuple[list[tuple[float, float]], dict[str, str]]] = []
    for element in doc.get("elements", []):
        geometry = element.get("geometry") or []
        points = [(float(p["lon"]), float(p["lat"])) for p in geometry if "lon" in p and "lat" in p]
        if len(points) < 2:
            continue
        lons = [p[0] for p in points]
        lats = [p[1] for p in points]
        if max(lons) < min_lon or min(lons) > max_lon or max(lats) < min_lat or min(lats) > max_lat:
            continue
        selected.append((points, {str(k): str(v) for k, v in (element.get("tags") or {}).items()}))
    return selected


def hex_rgba(value: str, alpha: int) -> tuple[int, int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha


def multiline(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, *, fnt: ImageFont.FreeTypeFont,
              fill: str, max_width: int, line_spacing: int = 8) -> int:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if draw.textbbox((0, 0), trial, font=fnt)[2] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    x, y = xy
    line_h = draw.textbbox((0, 0), "Ag", font=fnt)[3]
    for line in lines:
        draw.text((x, y), line, font=fnt, fill=fill)
        y += line_h + line_spacing
    return y


def hatch_polygon(overlay: Image.Image, polygon: list[tuple[int, int]], color: str, style: int) -> None:
    """Aplica padrão redundante dentro do polígono: diagonal, pontos ou cruzado."""
    mask = Image.new("L", overlay.size, 0)
    md = ImageDraw.Draw(mask)
    md.polygon(polygon, fill=255)
    pattern = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
    pd = ImageDraw.Draw(pattern)
    min_x = min(x for x, _ in polygon)
    max_x = max(x for x, _ in polygon)
    min_y = min(y for _, y in polygon)
    max_y = max(y for _, y in polygon)
    stroke = hex_rgba(color, 175)
    if style in (1, 3):
        for k in range(min_x - (max_y - min_y), max_x + (max_y - min_y), 34):
            pd.line([(k, max_y), (k + (max_y - min_y), min_y)], fill=stroke, width=4)
    if style == 2:
        for yy in range(min_y, max_y + 1, 32):
            for xx in range(min_x, max_x + 1, 32):
                pd.ellipse((xx - 4, yy - 4, xx + 4, yy + 4), fill=stroke)
    if style == 3:
        for k in range(min_x, max_x + (max_y - min_y), 34):
            pd.line([(k, min_y), (k - (max_y - min_y), max_y)], fill=stroke, width=4)
    overlay.alpha_composite(Image.composite(pattern, Image.new("RGBA", overlay.size, (0, 0, 0, 0)), mask))


def draw_panel(
    image: Image.Image,
    panel_x: int,
    title: str,
    subtitle: str,
    features: list[dict[str, Any]],
    top3: list[dict[str, str]],
    roads: list[tuple[list[tuple[float, float]], dict[str, str]]],
    hydro: list[tuple[list[tuple[float, float]], dict[str, str]]],
    lon0: float,
    lat0: float,
    extent_m: float,
) -> None:
    draw = ImageDraw.Draw(image)
    panel_y = MAP_TOP
    draw.rounded_rectangle((panel_x, panel_y, panel_x + PANEL_W, panel_y + PANEL_H), 26,
                           fill=COLORS["map"], outline="#d4d0c8", width=4)
    draw.text((panel_x + 38, panel_y + 28), title, font=font(50, bold=True), fill=COLORS["ink"])
    draw.text((panel_x + 40, panel_y + 91), subtitle, font=font(29), fill=COLORS["muted"])

    map_size = 1500
    map_left = panel_x + (PANEL_W - map_size) // 2
    map_top = panel_y + 155
    map_bottom = map_top + map_size
    scale = map_size / (2 * extent_m)

    def px(lon: float, lat: float) -> tuple[int, int]:
        xm, ym = lonlat_to_m(lon, lat, lon0, lat0)
        return int(map_left + map_size / 2 + xm * scale), int(map_top + map_size / 2 - ym * scale)

    draw.rectangle((map_left, map_top, map_left + map_size, map_bottom), fill="#f6f4ef", outline="#7d8588", width=3)

    # Camadas de contexto sob os setores, recortadas no quadro cartográfico.
    context_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    context_draw = ImageDraw.Draw(context_layer)
    for points, tags in roads:
        highway = tags.get("highway", "")
        width = 6 if highway in {"motorway", "trunk", "primary"} else 4 if highway in {"secondary", "tertiary"} else 2
        color = COLORS["road_major"] if width >= 4 else COLORS["road_minor"]
        context_draw.line([px(lon, lat) for lon, lat in points], fill=color, width=width, joint="curve")
    for points, _tags in hydro:
        context_draw.line([px(lon, lat) for lon, lat in points], fill=COLORS["hydro"], width=5, joint="curve")
    clip_mask = Image.new("L", image.size, 0)
    clip_draw = ImageDraw.Draw(clip_mask)
    clip_draw.rectangle((map_left, map_top, map_left + map_size, map_bottom), fill=255)
    clipped_context = Image.composite(context_layer, Image.new("RGBA", image.size, (0, 0, 0, 0)), clip_mask)
    image.alpha_composite(clipped_context)
    draw = ImageDraw.Draw(image)

    top_lookup = {row["sector_id"]: (idx + 1, row) for idx, row in enumerate(top3)}
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    # Preenchimento neutro e divisões dos 24 setores.
    polygons: dict[str, list[tuple[int, int]]] = {}
    for feature in features:
        sid = feature["properties"]["sector_id"]
        ring = feature["geometry"]["coordinates"][0]
        polygon = [px(float(lon), float(lat)) for lon, lat in ring]
        polygons[sid] = polygon
        od.polygon(polygon, fill=(255, 255, 255, 16), outline=(95, 105, 108, 125), width=2)

    # Destaques: cor + padrão + contorno, de modo que a leitura não dependa de cor.
    ap_colors = [COLORS["ap1"], COLORS["ap2"], COLORS["ap3"]]
    for sid, (pos, _row) in top_lookup.items():
        polygon = polygons[sid]
        color = ap_colors[pos - 1]
        od.polygon(polygon, fill=hex_rgba(color, 105), outline=hex_rgba(color, 255), width=12)
        hatch_polygon(overlay, polygon, color, pos)
        od.line(polygon + [polygon[0]], fill=hex_rgba(color, 255), width=12, joint="curve")
    image.alpha_composite(overlay)
    draw = ImageDraw.Draw(image)

    # Rótulos AP no ponto representativo de cada setor.
    for idx, row in enumerate(top3, start=1):
        x, y = px(float(row["representative_lon"]), float(row["representative_lat"]))
        color = ap_colors[idx - 1]
        radius = 33
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color, outline="white", width=6)
        label = f"{idx}"
        box = draw.textbbox((0, 0), label, font=font(34, bold=True))
        draw.text((x - (box[2] - box[0]) / 2, y - (box[3] - box[1]) / 2 - 4), label,
                  font=font(34, bold=True), fill="white")
        ring_dir = f"AP{idx}  {row['ring_id']}-{row['direction']}"
        label_font = font(27, bold=True)
        label_box = draw.textbbox((0, 0), ring_dir, font=label_font)
        label_width = label_box[2] - label_box[0]
        label_position = row.get("_map_label_position", "AUTO")
        if label_position == "ABOVE":
            tx = x - label_width / 2
            ty = y - 82
        else:
            # Mantém rótulos próximos ao marcador, mas os ancora à esquerda
            # quando o setor está junto à borda direita do quadro cartográfico.
            tx = x - 43 - label_width if x > map_left + map_size * 0.72 else x + 43
            ty = y - 25
        tbox = draw.textbbox((tx, ty), ring_dir, font=label_font)
        draw.rounded_rectangle((tbox[0] - 12, tbox[1] - 7, tbox[2] + 12, tbox[3] + 9), 9,
                               fill=(255, 255, 255, 232), outline=color, width=3)
        draw.text((tx, ty), ring_dir, font=label_font, fill=COLORS["ink"])

    # Ponto inicial, explicitamente distinto das áreas priorizadas.
    ox, oy = px(lon0, lat0)
    draw.ellipse((ox - 23, oy - 23, ox + 23, oy + 23), fill="white", outline=COLORS["origin"], width=7)
    draw.line((ox - 33, oy, ox + 33, oy), fill=COLORS["origin"], width=6)
    draw.line((ox, oy - 33, ox, oy + 33), fill=COLORS["origin"], width=6)
    draw.text((ox + 40, oy + 20), "E0  ponto inicial", font=font(27, bold=True), fill=COLORS["origin"])

    # Direções cardeais/intercardeais no limite externo.
    for label, azimuth in [("N", 0), ("NE", 45), ("E", 90), ("SE", 135), ("S", 180), ("SW", 225), ("W", 270), ("NW", 315)]:
        # Mantém os rótulos proporcionais ao enquadramento. Para o URBE-01,
        # 0,937 × 2.850 m reproduz os 2.670 m usados na versão publicada;
        # a parametrização também permite reutilizar o painel em outros raios.
        r = extent_m * 0.937
        ang = math.radians(azimuth)
        x = int(map_left + map_size / 2 + math.sin(ang) * r * scale)
        y = int(map_top + map_size / 2 - math.cos(ang) * r * scale)
        bbox = draw.textbbox((0, 0), label, font=font(25, bold=True))
        draw.rounded_rectangle((x - (bbox[2]-bbox[0])/2 - 7, y - 17, x + (bbox[2]-bbox[0])/2 + 7, y + 18),
                               6, fill=(255, 255, 255, 218))
        draw.text((x - (bbox[2]-bbox[0])/2, y - 16), label, font=font(25, bold=True), fill=COLORS["muted"])

    # Norte e escala gráfica de 1 km.
    nx = map_left + map_size - 92
    ny = map_top + 95
    draw.polygon([(nx, ny - 52), (nx - 22, ny + 15), (nx, ny + 2), (nx + 22, ny + 15)], fill=COLORS["ink"])
    draw.text((nx - 14, ny + 23), "N", font=font(30, bold=True), fill=COLORS["ink"])
    bar_px = int(1000 * scale)
    bx = map_left + 55
    by = map_bottom - 55
    draw.line((bx, by, bx + bar_px, by), fill=COLORS["ink"], width=10)
    draw.line((bx, by - 15, bx, by + 15), fill=COLORS["ink"], width=5)
    draw.line((bx + bar_px, by - 15, bx + bar_px, by + 15), fill=COLORS["ink"], width=5)
    draw.text((bx + bar_px / 2 - 32, by - 52), "1 km", font=font(27, bold=True), fill=COLORS["ink"])


def create_figure() -> None:
    sectors_doc = load_json(SECTORS_PATH)
    features = sectors_doc["features"]
    base = load_top3(BASE_PATH)
    profile = load_top3(PROFILE_PATH)

    # Centro recebido; não é posição verdadeira.
    lon0 = -51.068056
    lat0 = 0.015833
    extent_m = 2850.0
    lon_delta = math.degrees(extent_m / (R_EARTH * math.cos(math.radians(lat0))))
    lat_delta = math.degrees(extent_m / R_EARTH)
    bounds = (lon0 - lon_delta, lat0 - lat_delta, lon0 + lon_delta, lat0 + lat_delta)
    roads = osm_lines(ROADS_PATH, bounds)
    hydro = osm_lines(HYDRO_PATH, bounds)

    image = Image.new("RGBA", (CANVAS_W, CANVAS_H), COLORS["paper"])
    draw = ImageDraw.Draw(image)
    draw.text((130, 70), "URBE-01: priorização espacial antes da abertura da posição real",
              font=font(67, bold=True), fill=COLORS["ink"])
    draw.text((132, 160), "Comparação das três áreas prioritárias entre o ranking territorial e o ranking com perfil limitado",
              font=font(36), fill=COLORS["muted"])
    draw.rounded_rectangle((3320, 70, 3865, 205), 22, fill="#f2e9d2", outline="#b9994d", width=3)
    draw.text((3457, 88), "STATUS", font=font(26, bold=True), fill="#725711")
    draw.text((3378, 131), "REVISAR", font=font(40, bold=True), fill="#725711")

    draw_panel(
        image, LEFT_X, "A. Ranking BASE territorial",
        "Sem pistas comportamentais; pesos gerais GEO-02 a GEO-05.",
        features, base, roads, hydro, lon0, lat0, extent_m,
    )
    draw_panel(
        image, RIGHT_X, "B. Ranking PERFIL URBE-01",
        "90% territorial + 10% contextual; sem direção ou anel preferencial.",
        features, profile, roads, hydro, lon0, lat0, extent_m,
    )

    # Legenda comum.
    legend_y = 2140
    draw.text((145, legend_y), "Legenda", font=font(35, bold=True), fill=COLORS["ink"])
    x = 350
    for idx, (label, color, pattern) in enumerate([
        ("AP1 — 1ª prioridade", COLORS["ap1"], "diagonal"),
        ("AP2 — 2ª prioridade", COLORS["ap2"], "pontos"),
        ("AP3 — 3ª prioridade", COLORS["ap3"], "cruzado"),
    ], start=1):
        draw.rectangle((x, legend_y - 2, x + 60, legend_y + 48), fill=color, outline=COLORS["ink"], width=2)
        if pattern == "diagonal":
            for k in range(-10, 70, 16):
                draw.line((x+k, legend_y+48, x+k+50, legend_y-2), fill="white", width=3)
        elif pattern == "pontos":
            for yy in (legend_y+12, legend_y+34):
                for xx in (x+15, x+35, x+55):
                    draw.ellipse((xx-3, yy-3, xx+3, yy+3), fill="white")
        else:
            for k in range(-10, 70, 16):
                draw.line((x+k, legend_y+48, x+k+50, legend_y-2), fill="white", width=3)
                draw.line((x+k, legend_y-2, x+k+50, legend_y+48), fill="white", width=3)
        draw.text((x + 78, legend_y + 2), label, font=font(28), fill=COLORS["ink"])
        x += 600

    # Segunda linha da legenda/contexto.
    y2 = 2215
    draw.line((350, y2 + 19, 415, y2 + 19), fill=COLORS["road_major"], width=6)
    draw.text((435, y2), "vias OSM", font=font(26), fill=COLORS["ink"])
    draw.line((650, y2 + 19, 715, y2 + 19), fill=COLORS["hydro"], width=6)
    draw.text((735, y2), "hidrografia OSM", font=font(26), fill=COLORS["ink"])
    draw.ellipse((1065, y2 - 1, 1109, y2 + 43), fill="white", outline=COLORS["origin"], width=6)
    draw.line((1057, y2 + 21, 1117, y2 + 21), fill=COLORS["origin"], width=5)
    draw.text((1134, y2), "E0 = ponto inicial recebido", font=font(26), fill=COLORS["ink"])
    draw.text((1680, y2), "Raio: 2.500 m  |  24 setores de área equivalente", font=font(26), fill=COLORS["ink"])

    note = (
        "Nota. Composição cartográfica do processamento cego URBE-01. As vias e a hidrografia exibidas provêm do "
        "OpenStreetMap; os rankings também utilizam SRTMGL1/Mapzen e ESA WorldCover 2021 v200. São fontes públicas, "
        "não levantamento de campo. A posição real não foi utilizada nem representada. AP1–AP3 indicam prioridade "
        "analítica, não probabilidade de presença ou localização determinada. O status REVISAR decorre da baixa margem "
        "entre as primeiras alternativas e da natureza diagnóstica do ensaio."
    )
    draw.line((130, 2310, 3870, 2310), fill="#cbc6bc", width=3)
    multiline(draw, (145, 2340), note, fnt=font(24), fill=COLORS["muted"], max_width=3700, line_spacing=7)

    rgb = image.convert("RGB")
    rgb.save(PNG_PATH, format="PNG", dpi=(300, 300), optimize=True)

    page_w, page_h = landscape(A3)
    pdf = canvas.Canvas(str(PDF_PATH), pagesize=(page_w, page_h))
    margin = 18
    available_w = page_w - 2 * margin
    available_h = page_h - 2 * margin
    ratio = CANVAS_W / CANVAS_H
    draw_w = available_w
    draw_h = draw_w / ratio
    if draw_h > available_h:
        draw_h = available_h
        draw_w = draw_h * ratio
    pdf.drawImage(str(PNG_PATH), (page_w - draw_w) / 2, (page_h - draw_h) / 2,
                  width=draw_w, height=draw_h, preserveAspectRatio=True, mask="auto")
    pdf.showPage()
    pdf.save()

    readme = f"""# Mapa URBE-01 — processamento cego v1

Arquivos:

- `{PNG_PATH.name}`: figura em 4.000 × 2.550 px, metadado de 300 dpi;
- `{PDF_PATH.name}`: exportação A3 horizontal;
- script reprodutível: `{Path(__file__).name}`.

## Finalidade

A figura compara o Top-3 do ranking BASE territorial e o Top-3 do ranking PERFIL URBE-01. Ela foi gerada depois do congelamento das saídas científicas, sem leitura ou representação da posição verdadeira.

## Nota sugerida para a dissertação

> Nota. Composição cartográfica do processamento cego URBE-01. As vias e a hidrografia exibidas provêm do OpenStreetMap; os rankings também utilizam SRTMGL1/Mapzen e ESA WorldCover 2021 v200. São fontes públicas, não levantamento de campo. A posição real não foi utilizada nem representada. AP1–AP3 indicam prioridade analítica, não probabilidade de presença ou localização determinada.

## Leitura

- E0: ponto inicial recebido pelo sistema;
- AP1, AP2 e AP3: três áreas priorizadas, na ordem do ranking;
- R01, R02 e R03: anéis interno, intermediário e externo;
- N, NE, E, SE, S, SW, W e NW: direções dos setores;
- a cor é redundante com padrão e número, para preservar legibilidade.
"""
    README_PATH.write_text(readme, encoding="utf-8")
    print(PNG_PATH)
    print(PDF_PATH)
    print(README_PATH)
    print(f"contexto: {len(roads)} vias, {len(hydro)} feições hidrográficas")


if __name__ == "__main__":
    create_figure()
