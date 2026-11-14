#!/usr/bin/env python3
"""Gera a figura realista v2 do cenário RURAL-01, sem ground truth.

O fundo cartográfico é a composição anual Sentinel-2 em cores naturais do
ESA WorldCover/Terrascope para 2021. Trata-se de contexto cartográfico
histórico, não de uma cena observada em 2026. A figura reutiliza somente
entradas e resultados já existentes no projeto e não executa novas consultas
externas.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageOps
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[2]
V1_SCRIPT = ROOT / "work/rural01_processamento_cego_v1/gerar_mapa_rural01_real_vegetacao.py"
spec = importlib.util.spec_from_file_location("rural01_v1_base", V1_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Não foi possível carregar o módulo-base: {V1_SCRIPT}")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

OUT = ROOT / "outputs/campo_rural01/mapa_real_vegetacao_v2"
FONTES = OUT / "fontes"
RGB_PATH = FONTES / "ESA_WorldCover_S2_TCC_2021_RURAL01.png"
RGB_META_PATH = FONTES / "ESA_WorldCover_S2_TCC_2021_RURAL01.metadata.json"

PNG_PATH = OUT / "Mapa_RURAL01_Base_Realista_Sentinel_Vegetacao_Priorizacao_v2.png"
PDF_PATH = OUT / "Mapa_RURAL01_Base_Realista_Sentinel_Vegetacao_Priorizacao_v2.pdf"
README_PATH = OUT / "README_MAPA_RURAL01_REALISTA_v2.md"
MANIFEST_PATH = OUT / "manifesto_mapa_rural01_realista_v2.json"

V1_OUT = ROOT / "outputs/campo_rural01/mapa_real_vegetacao_v1"
V1_ARTIFACTS = [
    V1_OUT / "Mapa_RURAL01_Contexto_Real_Vegetacao_Priorizacao_v1.png",
    V1_OUT / "Mapa_RURAL01_Contexto_Real_Vegetacao_Priorizacao_v1.pdf",
    V1_OUT / "README_MAPA_RURAL01_REAL_VEGETACAO_v1.md",
    V1_OUT / "manifesto_mapa_rural01_real_vegetacao_v1.json",
]

LANDCOVER_ALPHA = 87  # 34,1%; faixa solicitada: 30-38%.
TOP3_ALPHAS = [82, 78, 74]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rgba(color: str, alpha: int) -> tuple[int, int, int, int]:
    return base.hex_rgba(color, alpha)


def load_metadata() -> dict[str, Any]:
    with RGB_META_PATH.open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)
    actual_hash = sha256(RGB_PATH)
    declared_hash = metadata["file"]["sha256"]
    if actual_hash != declared_hash:
        raise RuntimeError("O hash da composição RGB não corresponde aos metadados de aquisição.")
    if metadata["privacy_and_method"].get("ground_truth_used") is not False:
        raise RuntimeError("Metadados RGB incompatíveis com o protocolo cego.")
    return metadata


def metadata_bounds(metadata: dict[str, Any]) -> tuple[float, float, float, float]:
    item = metadata["request"]["bounds_lon_lat"]
    return float(item["min_lon"]), float(item["min_lat"]), float(item["max_lon"]), float(item["max_lat"])


def load_rgb_base() -> Image.Image:
    rgb = Image.open(RGB_PATH).convert("RGB")
    # Ajuste uniforme apenas de apresentação; preserva a geometria e não cria informação.
    rgb = ImageEnhance.Brightness(rgb).enhance(1.05)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.08)
    rgb = ImageEnhance.Color(rgb).enhance(1.07)
    return rgb.resize((base.MAP_SIZE, base.MAP_SIZE), Image.Resampling.LANCZOS).convert("RGBA")


def build_environment_map(
    rgb_base: Image.Image, bounds: tuple[float, float, float, float]
) -> tuple[Image.Image, dict[int, float], tuple[float, float, float]]:
    codes = base.crop_worldcover(bounds)
    wc_rgb = np.zeros((*codes.shape, 3), dtype=np.uint8)
    for code, color in base.WC_COLORS.items():
        wc_rgb[codes == code] = color
    unknown = np.all(wc_rgb == 0, axis=2) & (codes != 10)
    wc_rgb[unknown] = (210, 210, 210)
    wc_image = Image.fromarray(wc_rgb, mode="RGB").resize(
        (base.MAP_SIZE, base.MAP_SIZE), Image.Resampling.NEAREST
    ).convert("RGBA")
    wc_image.putalpha(LANDCOVER_ALPHA)

    elevation = base.crop_srtm(bounds)
    shade = base.hillshade(elevation)
    shade_image = Image.fromarray(shade, mode="L").resize(
        (base.MAP_SIZE, base.MAP_SIZE), Image.Resampling.BILINEAR
    )
    shade_arr = np.asarray(shade_image, dtype=np.float32) / 255.0
    rgb_arr = np.asarray(rgb_base.convert("RGB"), dtype=np.float32)
    factor = 0.91 + 0.17 * shade_arr
    shaded = np.clip(rgb_arr * factor[..., None], 0, 255).astype(np.uint8)
    result = Image.fromarray(shaded, mode="RGB").convert("RGBA")
    result.alpha_composite(wc_image)

    height, width = codes.shape
    yy, xx = np.mgrid[0:height, 0:width]
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    radius_px = (base.RADIUS_M / base.EXTENT_M) * min(width, height) / 2.0
    mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= radius_px**2
    values, counts = np.unique(codes[mask], return_counts=True)
    total = int(counts.sum()) or 1
    percentages = {int(value): float(count) * 100.0 / total for value, count in zip(values, counts)}
    elev_stats = (float(np.min(elevation)), float(np.mean(elevation)), float(np.max(elevation)))
    return result, percentages, elev_stats


def add_osm_halo(image: Image.Image, bounds: tuple[float, float, float, float]) -> tuple[int, int]:
    roads = base.osm_lines(base.ROADS_PATH, bounds)
    hydro = base.osm_lines(base.HYDRO_PATH, bounds)
    draw = ImageDraw.Draw(image, "RGBA")
    for points, tags in roads:
        highway = tags.get("highway", "")
        width = 7 if highway in {"motorway", "trunk", "primary"} else 5 if highway in {"secondary", "tertiary"} else 3
        pixels = [base.lonlat_to_px(lon, lat, bounds, base.MAP_SIZE) for lon, lat in points]
        draw.line(pixels, fill=(255, 255, 255, 220), width=width + 6, joint="curve")
        color = base.ROAD_MAJOR if width >= 5 else base.ROAD_MINOR
        draw.line(pixels, fill=rgba(color, 245), width=width, joint="curve")
    for points, _tags in hydro:
        pixels = [base.lonlat_to_px(lon, lat, bounds, base.MAP_SIZE) for lon, lat in points]
        draw.line(pixels, fill=(255, 255, 255, 220), width=11, joint="curve")
        draw.line(pixels, fill=rgba(base.HYDRO, 250), width=6, joint="curve")
    return len(roads), len(hydro)


def sector_polygons(bounds: tuple[float, float, float, float]) -> dict[str, list[tuple[int, int]]]:
    features = base.load_json(base.SECTORS_PATH)["features"]
    result: dict[str, list[tuple[int, int]]] = {}
    for feature in features:
        sid = feature["properties"]["sector_id"]
        ring = feature["geometry"]["coordinates"][0]
        result[sid] = [base.lonlat_to_px(float(lon), float(lat), bounds, base.MAP_SIZE) for lon, lat in ring]
    return result


def add_sector_grid(image: Image.Image, bounds: tuple[float, float, float, float], *, labels: bool) -> dict[str, list[tuple[int, int]]]:
    polygons = sector_polygons(bounds)
    halo = Image.new("RGBA", image.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    for polygon in polygons.values():
        hd.line(polygon + [polygon[0]], fill=(255, 255, 255, 210), width=6, joint="curve")
        hd.line(polygon + [polygon[0]], fill=(22, 35, 40, 205), width=2, joint="curve")
    image.alpha_composite(halo)

    if labels:
        draw = ImageDraw.Draw(image)
        for label, azimuth in [("N", 0), ("NE", 45), ("E", 90), ("SE", 135), ("S", 180), ("SW", 225), ("W", 270), ("NW", 315)]:
            angle = math.radians(azimuth)
            distance = 1510.0
            lon = base.LON0 + math.degrees((distance * math.sin(angle)) / (base.R_EARTH * math.cos(math.radians(base.LAT0))))
            lat = base.LAT0 + math.degrees((distance * math.cos(angle)) / base.R_EARTH)
            x, y = base.lonlat_to_px(lon, lat, bounds, base.MAP_SIZE)
            draw.text((x - 14, y - 15), label, font=base.font(23, bold=True), fill=base.INK, stroke_width=4, stroke_fill="white")
        for ring, distance in [("R01", 430), ("R02", 1040), ("R03", 1380)]:
            lon = base.LON0 - math.degrees(distance / (base.R_EARTH * math.cos(math.radians(base.LAT0))))
            x, y = base.lonlat_to_px(lon, base.LAT0, bounds, base.MAP_SIZE)
            draw.text((x - 18, y + 12), ring, font=base.font(22, bold=True), fill=base.INK, stroke_width=4, stroke_fill="white")
    return polygons


def add_top3(image: Image.Image, bounds: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    polygons = add_sector_grid(image, bounds, labels=False)
    top3 = base.load_json(base.TOP3_PATH)["areas"]

    fill_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    fd = ImageDraw.Draw(fill_layer)
    for index, row in enumerate(top3):
        polygon = polygons[row["sector_id"]]
        fd.polygon(polygon, fill=rgba(base.AP_COLORS[index], TOP3_ALPHAS[index]))
    image.alpha_composite(fill_layer)

    draw = ImageDraw.Draw(image)
    for index, row in enumerate(top3):
        polygon = polygons[row["sector_id"]]
        color = base.AP_COLORS[index]
        mask = Image.new("L", image.size, 0)
        ImageDraw.Draw(mask).polygon(polygon, fill=255)
        pattern = Image.new("RGBA", image.size, (0, 0, 0, 0))
        pd = ImageDraw.Draw(pattern)
        min_x, max_x = min(x for x, _ in polygon), max(x for x, _ in polygon)
        min_y, max_y = min(y for _, y in polygon), max(y for _, y in polygon)
        if index in (0, 2):
            for k in range(min_x - (max_y - min_y), max_x + (max_y - min_y), 28):
                pd.line((k, max_y, k + (max_y - min_y), min_y), fill=rgba(color, 215), width=3)
        if index == 1:
            for yy in range(min_y, max_y + 1, 28):
                for xx in range(min_x, max_x + 1, 28):
                    pd.ellipse((xx - 3, yy - 3, xx + 3, yy + 3), fill=rgba(color, 225))
        if index == 2:
            for k in range(min_x, max_x + (max_y - min_y), 28):
                pd.line((k, min_y, k - (max_y - min_y), max_y), fill=rgba(color, 215), width=3)
        image.alpha_composite(Image.composite(pattern, Image.new("RGBA", image.size, (0, 0, 0, 0)), mask))
        draw = ImageDraw.Draw(image)
        draw.line(polygon + [polygon[0]], fill="white", width=11, joint="curve")
        draw.line(polygon + [polygon[0]], fill=color, width=7, joint="curve")

        x, y = base.lonlat_to_px(float(row["representative_lon"]), float(row["representative_lat"]), bounds, base.MAP_SIZE)
        draw.ellipse((x - 21, y - 21, x + 21, y + 21), fill=color, outline="white", width=4)
        draw.text((x, y - 1), str(index + 1), font=base.font(27, bold=True), fill="white", anchor="mm")
        label = f"AP{index + 1}  {row['ring_id']}-{row['direction']}"
        tx = x - 155 if index in (0, 2) else x + 30
        ty = y - 58 if index == 0 else y + 20 if index == 2 else y - 16
        box = draw.textbbox((tx, ty), label, font=base.font(24, bold=True))
        draw.rounded_rectangle((box[0] - 8, box[1] - 5, box[2] + 8, box[3] + 7), 7, fill=(255, 255, 255, 232), outline=color, width=2)
        draw.text((tx, ty), label, font=base.font(24, bold=True), fill=base.INK)
    return top3


def panel_shell(image: Image.Image, x: int, y: int, title: str, subtitle: str) -> tuple[int, int]:
    return base.panel_shell(image, x, y, title, subtitle)


def paste_map(image: Image.Image, map_image: Image.Image, x: int, y: int) -> None:
    base.paste_map(image, map_image, x, y)


def photo_inset() -> Image.Image:
    photo = Image.open(base.PHOTO).convert("RGB")
    return ImageOps.fit(photo, (540, 304), method=Image.Resampling.LANCZOS, centering=(0.5, 0.52))


def draw_panel_a(image: Image.Image, x: int, y: int, rgb: Image.Image, bounds: tuple[float, float, float, float]) -> None:
    map_x, map_y = panel_shell(
        image,
        x,
        y,
        "A. Contexto orbital em cores naturais",
        "Composição anual Sentinel-2/ESA WorldCover de 2021; não é cena adquirida em 2026.",
    )
    panel_map = rgb.copy()
    base.draw_common_map_elements(panel_map, bounds)
    paste_map(image, panel_map, map_x, map_y)
    draw = ImageDraw.Draw(image)
    info_x = map_x + base.MAP_SIZE + 55
    width = base.PANEL_W - base.MAP_SIZE - 135
    draw.text((info_x, map_y + 4), "Fonte cartográfica", font=base.font(31, bold=True), fill=base.INK)
    yy = base.draw_wrapped(
        draw,
        (info_x, map_y + 56),
        "Mosaico anual 2021 em cores naturais, produzido a partir do arquivo Sentinel-2 L2A e disponibilizado pelo ESA WorldCover/Terrascope.",
        base.font(24),
        base.INK,
        width,
        9,
    )
    yy += 22
    draw.rounded_rectangle((info_x, yy, x + base.PANEL_W - 35, yy + 105), 13, fill="#f6eadf", outline="#c49a72", width=2)
    draw.text((info_x + 18, yy + 16), "Referência temporal", font=base.font(23, bold=True), fill=base.ORIGIN)
    draw.text((info_x + 18, yy + 54), "2021 ≠ condições observadas em 2026", font=base.font(24, bold=True), fill=base.ORIGIN)
    yy += 137
    draw.text((info_x, yy), "Registro local complementar", font=base.font(28, bold=True), fill=base.INK)
    inset = photo_inset().convert("RGBA")
    image.alpha_composite(inset, (info_x, yy + 48))
    draw.rectangle((info_x, yy + 48, info_x + 540, yy + 352), outline="#667176", width=2)
    yy += 370
    yy = base.draw_wrapped(
        draw,
        (info_x, yy),
        "Fotografia DJI 0858: detalhe aéreo de campo, não ortorretificado e sem uso métrico.",
        base.font(22),
        base.MUTED,
        width,
        8,
    )
    yy += 22
    draw.text((info_x, yy), "Uso neste painel", font=base.font(28, bold=True), fill=base.INK)
    base.draw_wrapped(
        draw,
        (info_x, yy + 48),
        "A composição orbital fornece o enquadramento espacial contínuo; a fotografia apenas confirma visualmente elementos observados no entorno de E0.",
        base.font(23),
        base.INK,
        width,
        9,
    )


def draw_panel_b(
    image: Image.Image,
    x: int,
    y: int,
    environment: Image.Image,
    bounds: tuple[float, float, float, float],
    percentages: dict[int, float],
    elev_stats: tuple[float, float, float],
) -> tuple[int, int]:
    map_x, map_y = panel_shell(
        image,
        x,
        y,
        "B. Leitura ambiental integrada",
        "RGB 2021 + relevo sombreado + WorldCover a 34% + vias e hidrografia OSM com halo.",
    )
    panel_map = environment.copy()
    osm_counts = add_osm_halo(panel_map, bounds)
    base.draw_common_map_elements(panel_map, bounds)
    paste_map(image, panel_map, map_x, map_y)
    draw = ImageDraw.Draw(image)
    info_x = map_x + base.MAP_SIZE + 55
    width = base.PANEL_W - base.MAP_SIZE - 135
    draw.text((info_x, map_y + 4), "Cobertura no raio", font=base.font(31, bold=True), fill=base.INK)
    yy = map_y + 58
    for code, percentage in sorted(percentages.items(), key=lambda item: item[1], reverse=True):
        if percentage < 0.05:
            continue
        color = base.WC_COLORS.get(code, (200, 200, 200))
        draw.rectangle((info_x, yy + 4, info_x + 30, yy + 34), fill=color, outline="#4f585c", width=1)
        draw.text((info_x + 44, yy), base.WC_LABELS.get(code, f"Classe {code}"), font=base.font(22), fill=base.INK)
        draw.text((x + base.PANEL_W - 42, yy), f"{percentage:.1f}%", font=base.font(22, bold=True), fill=base.INK, anchor="ra")
        yy += 48
    yy += 18
    draw.text((info_x, yy), "Relevo SRTM", font=base.font(29, bold=True), fill=base.INK)
    draw.text((info_x, yy + 44), f"mín. {elev_stats[0]:.0f} m | média {elev_stats[1]:.0f} m | máx. {elev_stats[2]:.0f} m", font=base.font(22), fill=base.INK)
    yy += 105
    draw.text((info_x, yy), "Contexto OSM", font=base.font(29, bold=True), fill=base.INK)
    draw.line((info_x, yy + 54, info_x + 62, yy + 54), fill="white", width=12)
    draw.line((info_x, yy + 54, info_x + 62, yy + 54), fill=base.ROAD_MAJOR, width=6)
    draw.text((info_x + 78, yy + 37), f"{osm_counts[0]} feições viárias", font=base.font(22), fill=base.INK)
    draw.line((info_x, yy + 99, info_x + 62, yy + 99), fill="white", width=12)
    draw.line((info_x, yy + 99, info_x + 62, yy + 99), fill=base.HYDRO, width=6)
    draw.text((info_x + 78, yy + 82), f"{osm_counts[1]} feições hidrográficas", font=base.font(22), fill=base.INK)
    yy += 155
    base.draw_wrapped(
        draw,
        (info_x, yy),
        "A transparência mantém visível o mosaico orbital e torna explícita a classe ambiental usada pelo modelo. As camadas apoiam a priorização, mas não determinam sozinhas a localização.",
        base.font(23),
        base.MUTED,
        width,
        9,
    )
    return osm_counts


def draw_panel_c(image: Image.Image, x: int, y: int, rgb: Image.Image, bounds: tuple[float, float, float, float]) -> None:
    map_x, map_y = panel_shell(
        image,
        x,
        y,
        "C. Setorização sobre a imagem orbital",
        "A mesma extensão é dividida em 3 anéis e 8 direções: 24 unidades analíticas.",
    )
    panel_map = rgb.copy()
    add_sector_grid(panel_map, bounds, labels=True)
    base.draw_common_map_elements(panel_map, bounds)
    paste_map(image, panel_map, map_x, map_y)
    draw = ImageDraw.Draw(image)
    info_x = map_x + base.MAP_SIZE + 55
    width = base.PANEL_W - base.MAP_SIZE - 135
    draw.text((info_x, map_y + 4), "Estrutura", font=base.font(31, bold=True), fill=base.INK)
    yy = map_y + 58
    for code, label in [("R01", "anel interno"), ("R02", "anel intermediário"), ("R03", "anel externo"), ("N a NW", "oito direções")]:
        draw.rounded_rectangle((info_x, yy, info_x + 105, yy + 47), 9, fill="#e7ecef", outline="#9aa5aa", width=2)
        draw.text((info_x + 52, yy + 8), code, font=base.font(23, bold=True), fill=base.INK, anchor="ma")
        draw.text((info_x + 127, yy + 8), label, font=base.font(23), fill=base.INK)
        yy += 67
    yy += 30
    draw.text((info_x, yy), "Vantagem visual", font=base.font(31, bold=True), fill=base.INK)
    yy = base.draw_wrapped(
        draw,
        (info_x, yy + 52),
        "A grade permanece auditável sem esconder rios, clareiras, estradas e continuidade da vegetação.",
        base.font(25),
        base.INK,
        width,
        10,
    )
    yy += 30
    draw.text((info_x, yy), "Cautela", font=base.font(31, bold=True), fill=base.INK)
    base.draw_wrapped(
        draw,
        (info_x, yy + 52),
        "As linhas representam unidades de comparação. Não são trajetórias previstas e não substituem a leitura operacional do terreno.",
        base.font(24),
        base.MUTED,
        width,
        10,
    )


def draw_panel_d(image: Image.Image, x: int, y: int, rgb: Image.Image, bounds: tuple[float, float, float, float]) -> None:
    map_x, map_y = panel_shell(
        image,
        x,
        y,
        "D. Top-3 sobre o contexto real",
        "Áreas priorizadas pelo processamento cego; preenchimento translúcido preserva a leitura do terreno.",
    )
    panel_map = rgb.copy()
    top3 = add_top3(panel_map, bounds)
    base.draw_common_map_elements(panel_map, bounds)
    paste_map(image, panel_map, map_x, map_y)
    draw = ImageDraw.Draw(image)
    info_x = map_x + base.MAP_SIZE + 48
    width = base.PANEL_W - base.MAP_SIZE - 125
    draw.rounded_rectangle((info_x, map_y, x + base.PANEL_W - 35, map_y + 116), 14, fill="#f2e9d2", outline="#b9994d", width=3)
    draw.text((info_x + 18, map_y + 18), "STATUS", font=base.font(24, bold=True), fill="#725711")
    draw.text((info_x + 18, map_y + 55), "REVISAR", font=base.font(37, bold=True), fill="#725711")
    draw.text((info_x + 235, map_y + 51), "margem AP1-AP2 = 0,0137", font=base.font(21), fill="#725711")
    yy = map_y + 145
    draw.text((info_x, yy), "Ordem de análise", font=base.font(31, bold=True), fill=base.INK)
    yy += 58
    for index, row in enumerate(top3):
        color = base.AP_COLORS[index]
        draw.rounded_rectangle((info_x, yy, x + base.PANEL_W - 35, yy + 135), 14, fill="#fafafa", outline=color, width=4)
        draw.ellipse((info_x + 16, yy + 25, info_x + 72, yy + 81), fill=color)
        draw.text((info_x + 44, yy + 53), str(index + 1), font=base.font(28, bold=True), fill="white", anchor="mm")
        draw.text((info_x + 92, yy + 17), f"AP{index + 1}  {row['ring_id']}-{row['direction']}", font=base.font(28, bold=True), fill=base.INK)
        draw.text((info_x + 92, yy + 58), f"escore {float(row['score']):.3f}", font=base.font(23), fill=base.INK)
        draw.text((info_x + 92, yy + 92), f"GEO-02 {float(row['geo02_score']):.2f}  |  GEO-03 {float(row['geo03_score']):.2f}", font=base.font(20), fill=base.MUTED)
        yy += 157
    yy += 18
    draw.text((info_x, yy), "Interpretação", font=base.font(30, bold=True), fill=base.INK)
    yy = base.draw_wrapped(
        draw,
        (info_x, yy + 50),
        "AP1 inicia a revisão, seguida por AP2 e AP3. A margem estreita e a instabilidade entre ponderações exigem supervisão humana.",
        base.font(24),
        base.INK,
        width,
        9,
    )
    draw.rounded_rectangle((info_x, yy + 28, x + base.PANEL_W - 35, yy + 144), 12, fill="#eef4f5", outline="#9ab0b7", width=2)
    draw.text((info_x + 17, yy + 44), "Ground truth", font=base.font(23, bold=True), fill=base.INK)
    draw.text((info_x + 17, yy + 80), "oculto e não utilizado", font=base.font(25, bold=True), fill=base.ORIGIN)


def create_figure() -> dict[str, Any]:
    required = [
        RGB_PATH,
        RGB_META_PATH,
        base.SECTORS_PATH,
        base.BUFFER_PATH,
        base.TOP3_PATH,
        base.WORLDCOVER_PATH,
        base.SRTM_PATH,
        base.ROADS_PATH,
        base.HYDRO_PATH,
        base.PHOTO,
        base.T2_MANIFEST_PATH,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Fontes ausentes: {missing}")
    t2_hash = sha256(base.T2_MANIFEST_PATH)
    if t2_hash != base.EXPECTED_T2_MANIFEST_SHA256:
        raise RuntimeError("O manifesto T2 congelado diverge do hash esperado; geração interrompida.")

    metadata = load_metadata()
    bounds = metadata_bounds(metadata)
    expected_bounds = base.lonlat_bounds()
    if max(abs(a - b) for a, b in zip(bounds, expected_bounds)) > 1e-10:
        raise RuntimeError("A extensão do RGB não coincide com a extensão cartográfica congelada.")

    OUT.mkdir(parents=True, exist_ok=True)
    rgb = load_rgb_base()
    environment, percentages, elev_stats = build_environment_map(rgb, bounds)

    image = Image.new("RGBA", (base.CANVAS_W, base.CANVAS_H), base.PAPER)
    draw = ImageDraw.Draw(image)
    draw.text((base.MARGIN_X, 48), "RURAL-01: processamento espacial sobre contexto orbital", font=base.font(60, bold=True), fill=base.INK)
    draw.text(
        (base.MARGIN_X + 2, 132),
        "Composição anual Sentinel-2 de 2021, leitura ambiental, setorização e Top-3 no mesmo enquadramento.",
        font=base.font(30),
        fill=base.MUTED,
    )
    draw.rounded_rectangle((base.CANVAS_W - 1280, 45, base.CANVAS_W - 90, 195), 20, fill="#eef3f5", outline="#9aadb4", width=3)
    draw.text((base.CANVAS_W - 1245, 65), "BASE ORBITAL", font=base.font(23, bold=True), fill=base.MUTED)
    draw.text((base.CANVAS_W - 1245, 103), "mosaico anual 2021", font=base.font(31, bold=True), fill=base.INK)
    draw.text((base.CANVAS_W - 1245, 148), "contexto histórico; não cena de 2026", font=base.font(22), fill=base.ORIGIN)

    left_x = base.MARGIN_X
    right_x = base.MARGIN_X + base.PANEL_W + base.PANEL_GAP_X
    draw_panel_a(image, left_x, base.TOP_Y, rgb, bounds)
    osm_counts = draw_panel_b(image, right_x, base.TOP_Y, environment, bounds, percentages, elev_stats)
    draw_panel_c(image, left_x, base.BOTTOM_Y, rgb, bounds)
    draw_panel_d(image, right_x, base.BOTTOM_Y, rgb, bounds)

    footer_y = base.BOTTOM_Y + base.PANEL_H + 32
    draw.line((base.MARGIN_X, footer_y, base.CANVAS_W - base.MARGIN_X, footer_y), fill=base.BORDER, width=3)
    note = (
        "Nota. Figura pré-revelação: a posição verdadeira não foi consultada nem representada. A base RGB é a composição anual Sentinel-2/ESA WorldCover 2021, "
        "não uma cena contemporânea ao campo de 2026. Painel B combina, com transparência, ESA WorldCover 2021 v200, SRTM e OpenStreetMap (base local de 17/08/2026). "
        "AP1-AP3 indicam prioridade analítica para revisão humana, não probabilidade de presença. "
        "© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium. "
        "© OpenStreetMap contributors, ODbL."
    )
    base.draw_wrapped(draw, (base.MARGIN_X + 4, footer_y + 18), note, base.font(26), base.MUTED, base.CANVAS_W - 2 * base.MARGIN_X - 8, 6)

    image.convert("RGB").save(PNG_PATH, format="PNG", dpi=(300, 300), optimize=True)
    page_w, page_h = landscape(A3)
    pdf = canvas.Canvas(str(PDF_PATH), pagesize=(page_w, page_h))
    margin_pt = 15
    available_w = page_w - 2 * margin_pt
    available_h = page_h - 2 * margin_pt
    ratio = base.CANVAS_W / base.CANVAS_H
    draw_w = available_w
    draw_h = draw_w / ratio
    if draw_h > available_h:
        draw_h = available_h
        draw_w = draw_h * ratio
    pdf.drawImage(str(PNG_PATH), (page_w - draw_w) / 2, (page_h - draw_h) / 2, width=draw_w, height=draw_h, preserveAspectRatio=True)
    pdf.showPage()
    pdf.save()

    top3 = base.load_json(base.TOP3_PATH)["areas"]
    readme = f"""# Mapa RURAL-01 - base orbital realista v2

## Produto

- `{PNG_PATH.name}`: figura multipainel em {base.CANVAS_W} x {base.CANVAS_H} px, 300 dpi;
- `{PDF_PATH.name}`: exportação A3 horizontal;
- `{Path(__file__).name}`: script reprodutível;
- `{MANIFEST_PATH.name}`: proveniência, hashes e QA.

## Leitura

1. **A - Contexto orbital:** composição anual Sentinel-2 em cores naturais do ESA WorldCover/Terrascope para 2021; não é uma cena observada em 2026. A fotografia DJI aparece apenas como registro local complementar.
2. **B - Leitura ambiental:** RGB com relevo sombreado discreto, WorldCover a {LANDCOVER_ALPHA / 255 * 100:.1f}% e feições OSM com halo.
3. **C - Setorização:** 24 setores sobre a mesma extensão e escala da imagem orbital.
4. **D - Top-3:** AP1 `{top3[0]['ring_id']}-{top3[0]['direction']}`, AP2 `{top3[1]['ring_id']}-{top3[1]['direction']}` e AP3 `{top3[2]['ring_id']}-{top3[2]['direction']}`, com preenchimentos de {TOP3_ALPHAS[0] / 255 * 100:.1f}%, {TOP3_ALPHAS[1] / 255 * 100:.1f}% e {TOP3_ALPHAS[2] / 255 * 100:.1f}%.

## Salvaguardas

- Ground truth não consultado, não utilizado e não representado.
- O RGB é um mosaico anual de 2021, útil para contexto cartográfico, e não comprova as condições observadas em 2026.
- A v1 permanece preservada; esta versão grava somente em `mapa_real_vegetacao_v2`.
- O T2 congelado foi conferido pelo hash original antes da geração.

## Fontes

- ESA WorldCover annual Sentinel-2 RGBNIR composite 2021 v2, TCC, 10 m, CC BY 4.0.
- ESA WorldCover 2021 v200, SRTM N00W052 e OpenStreetMap (snapshot local de 17/08/2026).
- Fotografia DJI 0858 fornecida pelo pesquisador, usada apenas em pequeno inset não métrico.
"""
    README_PATH.write_text(readme, encoding="utf-8")

    source_paths = [
        (RGB_PATH, "composição RGB Sentinel-2 2021"),
        (RGB_META_PATH, "metadados e URL WMS"),
        (base.SECTORS_PATH, "24 setores"),
        (base.BUFFER_PATH, "buffer de entrada"),
        (base.TOP3_PATH, "ranking Top-3"),
        (base.WORLDCOVER_PATH, "cobertura do solo"),
        (base.SRTM_PATH, "elevação"),
        (base.ROADS_PATH, "vias OSM"),
        (base.HYDRO_PATH, "hidrografia OSM"),
        (base.PHOTO, "fotografia aérea de contexto"),
    ]
    manifest: dict[str, Any] = {
        "artifact": "Mapa_RURAL01_Base_Realista_Sentinel_Vegetacao_Priorizacao_v2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ground_truth_used": False,
        "external_requests_executed": True,
        "external_request": {
            "provider": metadata["provider"],
            "service": metadata["service"],
            "request_url": metadata["request_url"],
            "retrieved_at_utc": metadata["retrieved_at_utc"],
            "http_status": metadata["http_response"]["status"],
            "rgb_sha256": sha256(RGB_PATH),
            "metadata_sha256": sha256(RGB_META_PATH),
            "ground_truth_included_in_request": False,
        },
        "crs": "EPSG:4326",
        "bounds": {"min_lon": bounds[0], "min_lat": bounds[1], "max_lon": bounds[2], "max_lat": bounds[3]},
        "scenario": {"id": "RURAL-01", "e0_lon": base.LON0, "e0_lat": base.LAT0, "source_radius_m": base.RADIUS_M, "sector_count": 24},
        "display": {
            "rgb_period": 2021,
            "rgb_is_2026_scene": False,
            "landcover_alpha": LANDCOVER_ALPHA,
            "landcover_alpha_percent": round(LANDCOVER_ALPHA / 255 * 100, 2),
            "top3_alpha": TOP3_ALPHAS,
            "uniform_rgb_adjustments": {"brightness": 1.05, "contrast": 1.08, "color": 1.07},
        },
        "top3": [
            {"rank": row["analytical_rank"], "area": row["area_label"], "sector": f"{row['ring_id']}-{row['direction']}", "score": row["score"]}
            for row in top3
        ],
        "worldcover_percent_within_buffer": {base.WC_LABELS.get(code, str(code)): round(value, 4) for code, value in percentages.items()},
        "srtm_elevation_m": {"min": round(elev_stats[0], 3), "mean": round(elev_stats[1], 3), "max": round(elev_stats[2], 3)},
        "osm_context_features": {"roads": osm_counts[0], "hydrography": osm_counts[1], "snapshot": "2026-08-17T17:01:35Z"},
        "sources": [{"role": role, "path": str(path.relative_to(ROOT)), "sha256": sha256(path)} for path, role in source_paths],
        "preserved_v1_artifacts": [
            {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)} for path in V1_ARTIFACTS if path.exists()
        ],
        "outputs": [],
        "qa": {
            "png_dimensions": [base.CANVAS_W, base.CANVAS_H],
            "pdf_expected_pages": 1,
            "panels": 4,
            "same_extent_all_map_panels": True,
            "ground_truth_coordinates_absent": True,
            "top3_count": len(top3),
            "rgb_hash_matches_acquisition_metadata": True,
            "frozen_t2_manifest_sha256_unchanged": t2_hash,
            "v1_not_written": True,
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for path in [PNG_PATH, PDF_PATH, README_PATH]:
        manifest["outputs"].append({"path": str(path.relative_to(ROOT)), "sha256": sha256(path), "bytes": path.stat().st_size})
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    result = create_figure()
    print(PNG_PATH)
    print(PDF_PATH)
    print(README_PATH)
    print(MANIFEST_PATH)
    print(json.dumps(result["qa"], ensure_ascii=False))
