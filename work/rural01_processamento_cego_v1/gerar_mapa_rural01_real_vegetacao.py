#!/usr/bin/env python3
"""Gera figura multipainel local do cenário RURAL-01, sem ground truth.

O produto combina uma fotografia aérea DJI apenas como contexto visual e,
nos painéis cartográficos, exclusivamente camadas públicas já armazenadas no
projeto (ESA WorldCover 2021, SRTM e OpenStreetMap). Nenhuma consulta externa
é executada e nenhuma posição verdadeira é lida, derivada ou representada.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "outputs/campo_rural01/processamento_cego_v1"
GEO = ROOT / "outputs/sprint2_s2_06_geo05_v33"
PHOTO = ROOT / "outputs/campo_rural01/reservado_originais/ParicasDrone0858.JPG"
OUT = ROOT / "outputs/campo_rural01/mapa_real_vegetacao_v1"
FONTES = OUT / "fontes"

SECTORS_PATH = SOURCE / "setores_rural01.geojson"
BUFFER_PATH = SOURCE / "entrada_raio_fonte.geojson"
TOP3_PATH = SOURCE / "top3_rural01.json"
WORLDCOVER_PATH = GEO / "worldcover_tiles/ESA_WorldCover_10m_2021_v200_N00W054_Map.tif"
SRTM_PATH = GEO / "N00W052.hgt.gz"
ROADS_PATH = GEO / "osm_highways_raw.json"
HYDRO_PATH = GEO / "osm_hydrography_raw.json"
T2_MANIFEST_PATH = ROOT / "outputs/campo_rural01/t2_congelado_final/manifesto_t2_rural01.json"
EXPECTED_T2_MANIFEST_SHA256 = "15e9961bc585b5a585eae4d48af9a3f5bfc829ca54e42d7c79bdb3e4db6994cf"

PNG_PATH = OUT / "Mapa_RURAL01_Contexto_Real_Vegetacao_Priorizacao_v1.png"
PDF_PATH = OUT / "Mapa_RURAL01_Contexto_Real_Vegetacao_Priorizacao_v1.pdf"
README_PATH = OUT / "README_MAPA_RURAL01_REAL_VEGETACAO_v1.md"
MANIFEST_PATH = OUT / "manifesto_mapa_rural01_real_vegetacao_v1.json"

CANVAS_W = 4961
CANVAS_H = 3508
MARGIN_X = 90
PANEL_GAP_X = 70
PANEL_GAP_Y = 55
PANEL_W = (CANVAS_W - 2 * MARGIN_X - PANEL_GAP_X) // 2
PANEL_H = 1430
TOP_Y = 270
BOTTOM_Y = TOP_Y + PANEL_H + PANEL_GAP_Y
MAP_SIZE = 1100
R_EARTH = 6_371_008.8

LON0 = -51.155556
LAT0 = 0.188611
RADIUS_M = 1500.0
EXTENT_M = 1750.0

FONT_REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_ITALIC = "/System/Library/Fonts/Supplemental/Arial Italic.ttf"

PAPER = "#f7f5ef"
INK = "#263238"
MUTED = "#5f6b70"
BORDER = "#c7c2b8"
ORIGIN = "#8a1c1c"
AP_COLORS = ["#1f5f8b", "#c58a00", "#d56a32"]
ROAD_MAJOR = "#f2d17d"
ROAD_MINOR = "#ddd2ba"
HYDRO = "#3e97bb"

WC_COLORS: dict[int, tuple[int, int, int]] = {
    10: (0, 100, 0),
    20: (255, 187, 34),
    30: (255, 255, 76),
    40: (240, 150, 255),
    50: (250, 0, 0),
    60: (180, 180, 180),
    70: (240, 240, 240),
    80: (0, 100, 200),
    90: (0, 150, 160),
    95: (0, 207, 117),
    100: (250, 230, 160),
}
WC_LABELS = {
    10: "Cobertura arbórea",
    20: "Arbustos",
    30: "Vegetação herbácea",
    40: "Área agrícola",
    50: "Área construída",
    60: "Solo exposto/vegetação esparsa",
    70: "Neve/gelo",
    80: "Água permanente",
    90: "Área úmida herbácea",
    95: "Manguezal",
    100: "Musgos/líquens",
}


def font(size: int, *, bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_ITALIC if italic else FONT_REGULAR
    return ImageFont.truetype(path, size=size)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wrap_lines(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if draw.textbbox((0, 0), trial, font=fnt)[2] <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    fnt: ImageFont.FreeTypeFont,
    fill: str,
    width: int,
    spacing: int = 8,
) -> int:
    x, y = xy
    line_h = draw.textbbox((0, 0), "Ag", font=fnt)[3]
    for line in wrap_lines(draw, text, fnt, width):
        draw.text((x, y), line, font=fnt, fill=fill)
        y += line_h + spacing
    return y


def hex_rgba(color: str, alpha: int) -> tuple[int, int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16), alpha


def lonlat_bounds() -> tuple[float, float, float, float]:
    lat_delta = math.degrees(EXTENT_M / R_EARTH)
    lon_delta = math.degrees(EXTENT_M / (R_EARTH * math.cos(math.radians(LAT0))))
    return LON0 - lon_delta, LAT0 - lat_delta, LON0 + lon_delta, LAT0 + lat_delta


def lonlat_to_px(lon: float, lat: float, bounds: tuple[float, float, float, float], size: int) -> tuple[int, int]:
    min_lon, min_lat, max_lon, max_lat = bounds
    x = (lon - min_lon) / (max_lon - min_lon) * (size - 1)
    y = (max_lat - lat) / (max_lat - min_lat) * (size - 1)
    return int(round(x)), int(round(y))


def iter_lonlat(coords: Any) -> Iterable[tuple[float, float]]:
    if not coords:
        return
    if isinstance(coords[0], (float, int)):
        yield float(coords[0]), float(coords[1])
    else:
        for child in coords:
            yield from iter_lonlat(child)


def crop_worldcover(bounds: tuple[float, float, float, float]) -> np.ndarray:
    """Recorta o tile WorldCover N00W054 (3 x 3 graus) sem GIS externo."""
    Image.MAX_IMAGE_PIXELS = None
    min_lon, min_lat, max_lon, max_lat = bounds
    image = Image.open(WORLDCOVER_PATH)
    width, height = image.size
    left = int(round((min_lon + 54.0) / 3.0 * width))
    right = int(round((max_lon + 54.0) / 3.0 * width))
    upper = int(round((3.0 - max_lat) / 3.0 * height))
    lower = int(round((3.0 - min_lat) / 3.0 * height))
    crop = image.crop((left, upper, right, lower))
    return np.asarray(crop, dtype=np.uint8)


def crop_srtm(bounds: tuple[float, float, float, float]) -> np.ndarray:
    """Recorta SRTM N00W052; grade 3601 x 3601, norte para sul."""
    min_lon, min_lat, max_lon, max_lat = bounds
    with gzip.open(SRTM_PATH, "rb") as handle:
        grid = np.frombuffer(handle.read(), dtype=">i2").reshape((3601, 3601)).astype(np.float32)
    left = max(0, int(math.floor((min_lon + 52.0) * 3600)))
    right = min(3601, int(math.ceil((max_lon + 52.0) * 3600)) + 1)
    upper = max(0, int(math.floor((1.0 - max_lat) * 3600)))
    lower = min(3601, int(math.ceil((1.0 - min_lat) * 3600)) + 1)
    crop = grid[upper:lower, left:right]
    crop[crop <= -32768] = np.nan
    if np.isnan(crop).any():
        fill = float(np.nanmedian(crop)) if not np.isnan(crop).all() else 0.0
        crop = np.nan_to_num(crop, nan=fill)
    return crop


def hillshade(elevation: np.ndarray) -> np.ndarray:
    dy, dx = np.gradient(elevation)
    slope = np.pi / 2.0 - np.arctan(np.hypot(dx, dy))
    aspect = np.arctan2(-dx, dy)
    azimuth = math.radians(315.0)
    altitude = math.radians(45.0)
    shade = np.sin(altitude) * np.sin(slope) + np.cos(altitude) * np.cos(slope) * np.cos(azimuth - aspect)
    shade = (shade - float(shade.min())) / max(float(np.ptp(shade)), 1e-9)
    return np.asarray(np.clip(shade * 255.0, 0, 255), dtype=np.uint8)


def landcover_base(bounds: tuple[float, float, float, float]) -> tuple[Image.Image, dict[int, float], tuple[float, float, float]]:
    codes = crop_worldcover(bounds)
    rgb = np.zeros((*codes.shape, 3), dtype=np.uint8)
    for code, color in WC_COLORS.items():
        rgb[codes == code] = color
    unknown = np.all(rgb == 0, axis=2) & (codes != 10)
    rgb[unknown] = (210, 210, 210)

    elevation = crop_srtm(bounds)
    shade = hillshade(elevation)
    shade_img = Image.fromarray(shade, mode="L").resize((codes.shape[1], codes.shape[0]), Image.Resampling.BILINEAR)
    shade_arr = np.asarray(shade_img, dtype=np.float32) / 255.0
    factor = 0.76 + 0.40 * shade_arr
    shaded = np.clip(rgb.astype(np.float32) * factor[..., None], 0, 255).astype(np.uint8)

    base = Image.fromarray(shaded, mode="RGB").resize((MAP_SIZE, MAP_SIZE), Image.Resampling.NEAREST).convert("RGBA")

    # Estatísticas apenas dentro do círculo de 1.500 m.
    h, w = codes.shape
    yy, xx = np.mgrid[0:h, 0:w]
    cx = (w - 1) / 2.0
    cy = (h - 1) / 2.0
    radius_px = (RADIUS_M / EXTENT_M) * min(w, h) / 2.0
    mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= radius_px**2
    count = Counter(int(value) for value in codes[mask].ravel())
    total = sum(count.values()) or 1
    percentages = {code: number * 100.0 / total for code, number in count.items()}
    elev_stats = (float(np.min(elevation)), float(np.mean(elevation)), float(np.max(elevation)))
    return base, percentages, elev_stats


def osm_lines(path: Path, bounds: tuple[float, float, float, float]) -> list[tuple[list[tuple[float, float]], dict[str, str]]]:
    min_lon, min_lat, max_lon, max_lat = bounds
    doc = load_json(path)
    result: list[tuple[list[tuple[float, float]], dict[str, str]]] = []
    for element in doc.get("elements", []):
        points = [
            (float(p["lon"]), float(p["lat"]))
            for p in (element.get("geometry") or [])
            if "lon" in p and "lat" in p
        ]
        if len(points) < 2:
            continue
        lons = [p[0] for p in points]
        lats = [p[1] for p in points]
        if max(lons) < min_lon or min(lons) > max_lon or max(lats) < min_lat or min(lats) > max_lat:
            continue
        tags = {str(k): str(v) for k, v in (element.get("tags") or {}).items()}
        result.append((points, tags))
    return result


def add_osm(base: Image.Image, bounds: tuple[float, float, float, float]) -> tuple[int, int]:
    draw = ImageDraw.Draw(base, "RGBA")
    roads = osm_lines(ROADS_PATH, bounds)
    hydro = osm_lines(HYDRO_PATH, bounds)
    for points, tags in roads:
        highway = tags.get("highway", "")
        width = 7 if highway in {"motorway", "trunk", "primary"} else 5 if highway in {"secondary", "tertiary"} else 3
        color = ROAD_MAJOR if width >= 5 else ROAD_MINOR
        pixels = [lonlat_to_px(lon, lat, bounds, MAP_SIZE) for lon, lat in points]
        draw.line(pixels, fill=hex_rgba(color, 215), width=width, joint="curve")
    for points, _tags in hydro:
        pixels = [lonlat_to_px(lon, lat, bounds, MAP_SIZE) for lon, lat in points]
        draw.line(pixels, fill=hex_rgba(HYDRO, 230), width=6, joint="curve")
    return len(roads), len(hydro)


def draw_common_map_elements(image: Image.Image, bounds: tuple[float, float, float, float]) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    buffer_doc = load_json(BUFFER_PATH)
    ring = buffer_doc["features"][0]["geometry"]["coordinates"][0]
    polygon = [lonlat_to_px(float(lon), float(lat), bounds, MAP_SIZE) for lon, lat in ring]
    draw.line(polygon + [polygon[0]], fill=hex_rgba(ORIGIN, 230), width=5, joint="curve")

    ox, oy = lonlat_to_px(LON0, LAT0, bounds, MAP_SIZE)
    draw.ellipse((ox - 13, oy - 13, ox + 13, oy + 13), fill="white", outline=ORIGIN, width=5)
    draw.line((ox - 20, oy, ox + 20, oy), fill=ORIGIN, width=4)
    draw.line((ox, oy - 20, ox, oy + 20), fill=ORIGIN, width=4)

    # Norte e escala gráfica de 500 m.
    draw.polygon([(MAP_SIZE - 62, 34), (MAP_SIZE - 82, 84), (MAP_SIZE - 62, 72), (MAP_SIZE - 42, 84)], fill=(255, 255, 255, 235), outline=INK)
    draw.text((MAP_SIZE - 77, 88), "N", font=font(27, bold=True), fill=INK)
    scale_px = int(round(500.0 / (2.0 * EXTENT_M) * MAP_SIZE))
    sx, sy = 45, MAP_SIZE - 48
    draw.rectangle((sx - 12, sy - 42, sx + scale_px + 42, sy + 20), fill=(255, 255, 255, 205))
    draw.line((sx, sy, sx + scale_px, sy), fill=INK, width=6)
    draw.line((sx, sy - 10, sx, sy + 10), fill=INK, width=4)
    draw.line((sx + scale_px, sy - 10, sx + scale_px, sy + 10), fill=INK, width=4)
    draw.text((sx + 5, sy - 38), "500 m", font=font(24, bold=True), fill=INK)


def add_sectors(image: Image.Image, bounds: tuple[float, float, float, float], highlight_top3: bool) -> None:
    sectors = load_json(SECTORS_PATH)["features"]
    top3 = load_json(TOP3_PATH)["areas"]
    top_lookup = {row["sector_id"]: (index, row) for index, row in enumerate(top3)}

    sector_overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    sector_draw = ImageDraw.Draw(sector_overlay)
    polygons: dict[str, list[tuple[int, int]]] = {}
    for feature in sectors:
        sid = feature["properties"]["sector_id"]
        ring = feature["geometry"]["coordinates"][0]
        polygon = [lonlat_to_px(float(lon), float(lat), bounds, MAP_SIZE) for lon, lat in ring]
        polygons[sid] = polygon
        fill = (255, 255, 255, 18) if not highlight_top3 else (255, 255, 255, 8)
        sector_draw.polygon(polygon, fill=fill, outline=(38, 50, 56, 165), width=2)
    image.alpha_composite(sector_overlay)
    draw = ImageDraw.Draw(image)

    if highlight_top3:
        highlight_overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        highlight_draw = ImageDraw.Draw(highlight_overlay)
        for sid, (index, _row) in top_lookup.items():
            polygon = polygons[sid]
            color = AP_COLORS[index]
            highlight_draw.polygon(polygon, fill=hex_rgba(color, 112), outline=hex_rgba(color, 255), width=8)
        image.alpha_composite(highlight_overlay)
        draw = ImageDraw.Draw(image)
        for sid, (index, _row) in top_lookup.items():
            polygon = polygons[sid]
            color = AP_COLORS[index]
            # Padrões redundantes para leitura em escala de cinza.
            min_x = min(x for x, _y in polygon)
            max_x = max(x for x, _y in polygon)
            min_y = min(y for _x, y in polygon)
            max_y = max(y for _x, y in polygon)
            mask = Image.new("L", (MAP_SIZE, MAP_SIZE), 0)
            ImageDraw.Draw(mask).polygon(polygon, fill=255)
            pattern = Image.new("RGBA", (MAP_SIZE, MAP_SIZE), (0, 0, 0, 0))
            pd = ImageDraw.Draw(pattern)
            if index in (0, 2):
                for k in range(min_x - (max_y - min_y), max_x + (max_y - min_y), 25):
                    pd.line((k, max_y, k + (max_y - min_y), min_y), fill=hex_rgba(color, 210), width=3)
            if index == 1:
                for yy in range(min_y, max_y + 1, 25):
                    for xx in range(min_x, max_x + 1, 25):
                        pd.ellipse((xx - 3, yy - 3, xx + 3, yy + 3), fill=hex_rgba(color, 220))
            if index == 2:
                for k in range(min_x, max_x + (max_y - min_y), 25):
                    pd.line((k, min_y, k - (max_y - min_y), max_y), fill=hex_rgba(color, 210), width=3)
            image.alpha_composite(Image.composite(pattern, Image.new("RGBA", image.size, (0, 0, 0, 0)), mask))
            draw = ImageDraw.Draw(image)
            draw.line(polygon + [polygon[0]], fill=color, width=8, joint="curve")

        for index, row in enumerate(top3):
            x, y = lonlat_to_px(float(row["representative_lon"]), float(row["representative_lat"]), bounds, MAP_SIZE)
            color = AP_COLORS[index]
            draw.ellipse((x - 21, y - 21, x + 21, y + 21), fill=color, outline="white", width=4)
            draw.text((x - 10, y - 17), str(index + 1), font=font(28, bold=True), fill="white")
            label = f"AP{index + 1}  {row['ring_id']}-{row['direction']}"
            tx = x - 155 if index in (0, 2) else x + 30
            ty = y - 58 if index == 0 else y + 20 if index == 2 else y - 16
            box = draw.textbbox((tx, ty), label, font=font(24, bold=True))
            draw.rounded_rectangle((box[0] - 8, box[1] - 5, box[2] + 8, box[3] + 7), 7, fill=(255, 255, 255, 228), outline=color, width=2)
            draw.text((tx, ty), label, font=font(24, bold=True), fill=INK)
    else:
        # Rótulos direcionais externos e anéis.
        for label, azimuth in [("N", 0), ("NE", 45), ("E", 90), ("SE", 135), ("S", 180), ("SW", 225), ("W", 270), ("NW", 315)]:
            angle = math.radians(azimuth)
            dist = 1510.0
            lon = LON0 + math.degrees((dist * math.sin(angle)) / (R_EARTH * math.cos(math.radians(LAT0))))
            lat = LAT0 + math.degrees((dist * math.cos(angle)) / R_EARTH)
            x, y = lonlat_to_px(lon, lat, bounds, MAP_SIZE)
            draw.text((x - 14, y - 15), label, font=font(23, bold=True), fill=INK, stroke_width=3, stroke_fill="white")
        for ring, distance in [("R01", 430), ("R02", 1040), ("R03", 1380)]:
            lon = LON0 - math.degrees(distance / (R_EARTH * math.cos(math.radians(LAT0))))
            x, y = lonlat_to_px(lon, LAT0, bounds, MAP_SIZE)
            draw.text((x - 18, y + 12), ring, font=font(22, bold=True), fill=INK, stroke_width=3, stroke_fill="white")


def panel_shell(image: Image.Image, x: int, y: int, title: str, subtitle: str) -> tuple[int, int]:
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((x, y, x + PANEL_W, y + PANEL_H), 24, fill="#ffffff", outline=BORDER, width=3)
    draw.text((x + 34, y + 24), title, font=font(43, bold=True), fill=INK)
    draw.text((x + 36, y + 82), subtitle, font=font(25), fill=MUTED)
    return x + 35, y + 145


def paste_map(image: Image.Image, map_image: Image.Image, x: int, y: int) -> None:
    draw = ImageDraw.Draw(image)
    image.alpha_composite(map_image, (x, y))
    draw.rectangle((x, y, x + MAP_SIZE, y + MAP_SIZE), outline="#616b6f", width=3)


def crop_photo_square(path: Path) -> Image.Image:
    photo = Image.open(path).convert("RGB")
    # Recorte central preserva clareira, estrada e borda de mata; não é ortomosaico.
    side = min(photo.size)
    left = (photo.width - side) // 2
    upper = (photo.height - side) // 2
    crop = photo.crop((left, upper, left + side, upper + side))
    crop = ImageEnhance.Contrast(crop).enhance(1.04)
    return ImageOps.fit(crop, (MAP_SIZE, MAP_SIZE), method=Image.Resampling.LANCZOS)


def draw_panel_a(image: Image.Image, x: int, y: int) -> None:
    map_x, map_y = panel_shell(
        image,
        x,
        y,
        "A. Contexto aéreo local",
        "Fotografia DJI do entorno do ponto inicial; registro visual, não base cartográfica.",
    )
    photo = crop_photo_square(PHOTO).convert("RGBA")
    paste_map(image, photo, map_x, map_y)
    draw = ImageDraw.Draw(image)
    info_x = map_x + MAP_SIZE + 55
    draw.text((info_x, map_y + 4), "Como ler", font=font(31, bold=True), fill=INK)
    y0 = draw_wrapped(
        draw,
        (info_x, map_y + 55),
        "A imagem documenta a clareira, a estrada de terra e a borda de vegetação observadas no campo.",
        font(25),
        INK,
        PANEL_W - MAP_SIZE - 135,
        10,
    )
    y0 += 25
    draw.text((info_x, y0), "Limite de uso", font=font(31, bold=True), fill=INK)
    y0 = draw_wrapped(
        draw,
        (info_x, y0 + 52),
        "Não é ortofoto nem ortomosaico. Não possui escala cartográfica uniforme e não foi usada para medir distâncias ou posicionar candidatos.",
        font(25),
        ORIGIN,
        PANEL_W - MAP_SIZE - 135,
        10,
    )
    draw.rounded_rectangle((info_x, y0 + 35, x + PANEL_W - 35, y0 + 190), 16, fill="#f5eee4", outline="#cfb68d", width=2)
    draw.text((info_x + 22, y0 + 53), "Registro utilizado", font=font(26, bold=True), fill=INK)
    draw.text((info_x + 22, y0 + 96), "ParicasDrone0858.JPG", font=font(24), fill=INK)
    draw.text((info_x + 22, y0 + 133), "DJI FC3682 | 4.000 × 2.250 px", font=font(22), fill=MUTED)


def draw_panel_b(
    image: Image.Image,
    x: int,
    y: int,
    base_map: Image.Image,
    bounds: tuple[float, float, float, float],
    percentages: dict[int, float],
    elev_stats: tuple[float, float, float],
) -> tuple[int, int]:
    map_x, map_y = panel_shell(
        image,
        x,
        y,
        "B. Cobertura, relevo e acessos",
        "WorldCover 2021 + relevo sombreado SRTM + vias e hidrografia OSM.",
    )
    panel_map = base_map.copy()
    counts = add_osm(panel_map, bounds)
    draw_common_map_elements(panel_map, bounds)
    paste_map(image, panel_map, map_x, map_y)
    draw = ImageDraw.Draw(image)
    info_x = map_x + MAP_SIZE + 55
    draw.text((info_x, map_y + 4), "Cobertura no raio", font=font(31, bold=True), fill=INK)
    legend_y = map_y + 58
    for code, percentage in sorted(percentages.items(), key=lambda item: item[1], reverse=True):
        if percentage < 0.05:
            continue
        color = WC_COLORS.get(code, (200, 200, 200))
        draw.rectangle((info_x, legend_y + 4, info_x + 30, legend_y + 34), fill=color, outline="#4f585c", width=1)
        label = WC_LABELS.get(code, f"Classe {code}")
        draw.text((info_x + 44, legend_y), f"{label}", font=font(22), fill=INK)
        draw.text((x + PANEL_W - 42, legend_y), f"{percentage:.1f}%", font=font(22, bold=True), fill=INK, anchor="ra")
        legend_y += 48
    legend_y += 18
    draw.text((info_x, legend_y), "Relevo SRTM", font=font(29, bold=True), fill=INK)
    draw.text((info_x, legend_y + 45), f"mín. {elev_stats[0]:.0f} m | média {elev_stats[1]:.0f} m | máx. {elev_stats[2]:.0f} m", font=font(22), fill=INK)
    legend_y += 105
    draw.text((info_x, legend_y), "Contexto OSM", font=font(29, bold=True), fill=INK)
    draw.line((info_x, legend_y + 54, info_x + 62, legend_y + 54), fill=ROAD_MAJOR, width=7)
    draw.text((info_x + 78, legend_y + 37), f"{counts[0]} feições viárias", font=font(22), fill=INK)
    draw.line((info_x, legend_y + 99, info_x + 62, legend_y + 99), fill=HYDRO, width=7)
    draw.text((info_x + 78, legend_y + 82), f"{counts[1]} feições hidrográficas", font=font(22), fill=INK)
    legend_y += 155
    draw_wrapped(
        draw,
        (info_x, legend_y),
        "As classes ambientais qualificam deslocamento, visibilidade e acesso; não indicam, isoladamente, onde a vítima está.",
        font(24),
        MUTED,
        PANEL_W - MAP_SIZE - 135,
        10,
    )
    return counts


def draw_panel_c(image: Image.Image, x: int, y: int, base_map: Image.Image, bounds: tuple[float, float, float, float]) -> None:
    map_x, map_y = panel_shell(
        image,
        x,
        y,
        "C. Setorização do espaço de busca",
        "O buffer de 1.500 m é dividido em 3 anéis e 8 direções, totalizando 24 setores.",
    )
    panel_map = base_map.copy()
    add_sectors(panel_map, bounds, highlight_top3=False)
    draw_common_map_elements(panel_map, bounds)
    paste_map(image, panel_map, map_x, map_y)
    draw = ImageDraw.Draw(image)
    info_x = map_x + MAP_SIZE + 55
    draw.text((info_x, map_y + 4), "Estrutura", font=font(31, bold=True), fill=INK)
    items = [
        ("R01", "anel interno"),
        ("R02", "anel intermediário"),
        ("R03", "anel externo"),
        ("N a NW", "oito direções"),
    ]
    yy = map_y + 60
    for code, label in items:
        draw.rounded_rectangle((info_x, yy, info_x + 105, yy + 47), 9, fill="#e7ecef", outline="#9aa5aa", width=2)
        draw.text((info_x + 52, yy + 8), code, font=font(23, bold=True), fill=INK, anchor="ma")
        draw.text((info_x + 127, yy + 8), label, font=font(23), fill=INK)
        yy += 67
    yy += 30
    draw.text((info_x, yy), "Função", font=font(31, bold=True), fill=INK)
    yy = draw_wrapped(
        draw,
        (info_x, yy + 52),
        "Converter uma área contínua em unidades comparáveis e auditáveis, sem afirmar uma posição exata.",
        font(25),
        INK,
        PANEL_W - MAP_SIZE - 135,
        10,
    )
    yy += 30
    draw.text((info_x, yy), "Leitura", font=font(31, bold=True), fill=INK)
    draw_wrapped(
        draw,
        (info_x, yy + 52),
        "E0 é o ponto inicial recebido. O contorno vinho é o raio informado pela fonte. As linhas internas são unidades analíticas, não rotas prescritas.",
        font(24),
        MUTED,
        PANEL_W - MAP_SIZE - 135,
        10,
    )


def draw_panel_d(image: Image.Image, x: int, y: int, base_map: Image.Image, bounds: tuple[float, float, float, float]) -> None:
    map_x, map_y = panel_shell(
        image,
        x,
        y,
        "D. Priorização analítica",
        "Top-3 produzido sem acesso à posição real; escores não representam probabilidade de presença.",
    )
    panel_map = base_map.copy()
    add_sectors(panel_map, bounds, highlight_top3=True)
    draw_common_map_elements(panel_map, bounds)
    paste_map(image, panel_map, map_x, map_y)
    draw = ImageDraw.Draw(image)
    info_x = map_x + MAP_SIZE + 48
    top3 = load_json(TOP3_PATH)["areas"]
    draw.rounded_rectangle((info_x, map_y, x + PANEL_W - 35, map_y + 116), 14, fill="#f2e9d2", outline="#b9994d", width=3)
    draw.text((info_x + 18, map_y + 18), "STATUS", font=font(24, bold=True), fill="#725711")
    draw.text((info_x + 18, map_y + 55), "REVISAR", font=font(37, bold=True), fill="#725711")
    draw.text((info_x + 235, map_y + 51), "margem AP1-AP2 = 0,0137", font=font(21), fill="#725711")

    yy = map_y + 145
    draw.text((info_x, yy), "Ordem de análise", font=font(31, bold=True), fill=INK)
    yy += 58
    for index, row in enumerate(top3):
        color = AP_COLORS[index]
        draw.rounded_rectangle((info_x, yy, x + PANEL_W - 35, yy + 135), 14, fill="#fafafa", outline=color, width=4)
        draw.ellipse((info_x + 16, yy + 25, info_x + 72, yy + 81), fill=color)
        draw.text((info_x + 44, yy + 34), str(index + 1), font=font(28, bold=True), fill="white", anchor="ma")
        draw.text((info_x + 92, yy + 17), f"AP{index + 1}  {row['ring_id']}-{row['direction']}", font=font(28, bold=True), fill=INK)
        draw.text((info_x + 92, yy + 58), f"escore {float(row['score']):.3f}", font=font(23), fill=INK)
        draw.text((info_x + 92, yy + 92), f"GEO-02 {float(row['geo02_score']):.2f}  |  GEO-03 {float(row['geo03_score']):.2f}", font=font(20), fill=MUTED)
        yy += 157

    yy += 18
    draw.text((info_x, yy), "Interpretação", font=font(30, bold=True), fill=INK)
    yy = draw_wrapped(
        draw,
        (info_x, yy + 50),
        "AP1 inicia a revisão, seguida por AP2 e AP3. A margem estreita e a instabilidade entre ponderações exigem supervisão humana.",
        font(24),
        INK,
        PANEL_W - MAP_SIZE - 125,
        9,
    )
    draw.rounded_rectangle((info_x, yy + 28, x + PANEL_W - 35, yy + 144), 12, fill="#eef4f5", outline="#9ab0b7", width=2)
    draw.text((info_x + 17, yy + 44), "Ground truth", font=font(23, bold=True), fill=INK)
    draw.text((info_x + 17, yy + 80), "oculto e não utilizado", font=font(25, bold=True), fill=ORIGIN)


def create_figure() -> dict[str, Any]:
    required = [SECTORS_PATH, BUFFER_PATH, TOP3_PATH, WORLDCOVER_PATH, SRTM_PATH, ROADS_PATH, HYDRO_PATH, PHOTO, T2_MANIFEST_PATH]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Fontes ausentes: {missing}")
    t2_hash = sha256(T2_MANIFEST_PATH)
    if t2_hash != EXPECTED_T2_MANIFEST_SHA256:
        raise RuntimeError("O manifesto T2 congelado diverge do hash esperado; geração interrompida.")

    OUT.mkdir(parents=True, exist_ok=True)
    FONTES.mkdir(parents=True, exist_ok=True)
    bounds = lonlat_bounds()
    base_map, percentages, elev_stats = landcover_base(bounds)

    image = Image.new("RGBA", (CANVAS_W, CANVAS_H), PAPER)
    draw = ImageDraw.Draw(image)
    draw.text((MARGIN_X, 48), "RURAL-01: do contexto real à priorização espacial", font=font(62, bold=True), fill=INK)
    draw.text(
        (MARGIN_X + 2, 132),
        "Figura pré-revelação: fotografia de campo, cobertura do solo, setorização e Top-3 no mesmo protocolo visual.",
        font=font(31),
        fill=MUTED,
    )
    draw.rounded_rectangle((CANVAS_W - 1140, 45, CANVAS_W - 90, 195), 20, fill="#eef3f5", outline="#9aadb4", width=3)
    draw.text((CANVAS_W - 1105, 69), "PONTO INICIAL", font=font(23, bold=True), fill=MUTED)
    draw.text((CANVAS_W - 1105, 108), "0,188611; -51,155556", font=font(31, bold=True), fill=INK)
    draw.text((CANVAS_W - 1105, 151), "raio informado pela fonte: 1.500 m", font=font(22), fill=MUTED)

    left_x = MARGIN_X
    right_x = MARGIN_X + PANEL_W + PANEL_GAP_X
    draw_panel_a(image, left_x, TOP_Y)
    osm_counts = draw_panel_b(image, right_x, TOP_Y, base_map, bounds, percentages, elev_stats)
    draw_panel_c(image, left_x, BOTTOM_Y, base_map, bounds)
    draw_panel_d(image, right_x, BOTTOM_Y, base_map, bounds)

    footer_y = BOTTOM_Y + PANEL_H + 32
    draw.line((MARGIN_X, footer_y, CANVAS_W - MARGIN_X, footer_y), fill=BORDER, width=3)
    note = (
        "Nota. Composição pré-revelação sem uso da posição verdadeira. Painel A: fotografia aérea DJI, não ortorretificada e sem uso métrico. "
        "Painéis B-D: ESA WorldCover 2021 v200 e SRTM, com vias e hidrografia do OpenStreetMap (base local de 17/08/2026). "
        "Fontes públicas e registros de campo, não levantamento GNSS de precisão. AP1-AP3 indicam prioridade analítica para revisão humana, não probabilidade de presença. "
        "WorldCover: © ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium. "
        "OpenStreetMap: © OpenStreetMap contributors, ODbL."
    )
    draw_wrapped(draw, (MARGIN_X + 4, footer_y + 18), note, font(26), MUTED, CANVAS_W - 2 * MARGIN_X - 8, 6)

    rgb = image.convert("RGB")
    rgb.save(PNG_PATH, format="PNG", dpi=(300, 300), optimize=True)

    page_w, page_h = landscape(A3)
    pdf = canvas.Canvas(str(PDF_PATH), pagesize=(page_w, page_h))
    margin_pt = 15
    available_w = page_w - 2 * margin_pt
    available_h = page_h - 2 * margin_pt
    ratio = CANVAS_W / CANVAS_H
    draw_w = available_w
    draw_h = draw_w / ratio
    if draw_h > available_h:
        draw_h = available_h
        draw_w = draw_h * ratio
    pdf.drawImage(str(PNG_PATH), (page_w - draw_w) / 2, (page_h - draw_h) / 2, width=draw_w, height=draw_h, preserveAspectRatio=True)
    pdf.showPage()
    pdf.save()

    # Pacote mínimo de fontes: metadados e um recorte visual derivado, sem duplicar os originais reservados.
    photo_crop_path = FONTES / "ParicasDrone0858_recorte_contexto_nao_metrico.jpg"
    crop_photo_square(PHOTO).save(photo_crop_path, format="JPEG", quality=94, optimize=True)
    optional_wms = FONTES / "WMS_RGB_ESA_OPCIONAL_NAO_EXECUTADO.md"
    optional_wms.write_text(
        "# Aprimoramento opcional não executado\n\n"
        "O RGB anual 2021 do ESA WorldCover/Terrascope pode substituir o painel A em uma futura versão. "
        "Nesta geração nenhuma requisição externa foi realizada, pois a consulta enviaria a caixa geográfica "
        "do cenário a um serviço remoto. A camada prevista seria "
        "`esa-worldcover-s2rgbnir-10m-2021-v2_tcc`.\n",
        encoding="utf-8",
    )

    top3 = load_json(TOP3_PATH)["areas"]
    readme = f"""# Mapa RURAL-01 - contexto real, vegetação e priorização v1

## Produto

- `{PNG_PATH.name}`: figura multipainel em {CANVAS_W} x {CANVAS_H} px, 300 dpi;
- `{PDF_PATH.name}`: exportação A3 horizontal;
- `{Path(__file__).name}`: script reprodutível e autocontido;
- `{MANIFEST_PATH.name}`: proveniência, hashes e QA básico.

## Leitura dos painéis

1. **A - Contexto aéreo local:** fotografia DJI do entorno do ponto inicial. É um registro visual, não ortofoto, ortomosaico ou base métrica.
2. **B - Cobertura, relevo e acessos:** ESA WorldCover 2021, relevo sombreado SRTM e feições locais do OpenStreetMap.
3. **C - Setorização:** buffer informado de 1.500 m dividido em 3 anéis e 8 direções, totalizando 24 setores comparáveis.
4. **D - Priorização:** AP1 `{top3[0]['ring_id']}-{top3[0]['direction']}`, AP2 `{top3[1]['ring_id']}-{top3[1]['direction']}` e AP3 `{top3[2]['ring_id']}-{top3[2]['direction']}`. Os escores são prioridade analítica, não probabilidade.

## Salvaguarda pré-revelação

A posição verdadeira não foi consultada, utilizada nem representada. O mapa reproduz apenas a entrada E0, o raio informado pela fonte, as camadas públicas locais e as saídas já registradas pelo processamento cego.

## Fontes e atribuição

- ESA WorldCover 2021 v200, 10 m, CC BY 4.0. Atribuição: © ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium.
- SRTM N00W052, modelo digital de elevação usado somente para relevo sombreado e síntese altimétrica.
- OpenStreetMap, base local de 17/08/2026, © OpenStreetMap contributors, ODbL.
- `ParicasDrone0858.JPG`, fotografia aérea DJI fornecida pelo pesquisador; o recorte exibido não foi usado como base cartográfica.

## Consulta RGB externa

O WMS RGB anual 2021 do ESA/Terrascope não foi consultado. A consulta exigiria enviar a caixa geográfica do cenário a um serviço remoto. O aprimoramento permanece documentado em `fontes/WMS_RGB_ESA_OPCIONAL_NAO_EXECUTADO.md`.
"""
    README_PATH.write_text(readme, encoding="utf-8")

    generated_at = datetime.now(timezone.utc).isoformat()
    manifest: dict[str, Any] = {
        "artifact": "Mapa_RURAL01_Contexto_Real_Vegetacao_Priorizacao_v1",
        "generated_at_utc": generated_at,
        "ground_truth_used": False,
        "external_requests_executed": False,
        "crs": "EPSG:4326",
        "bounds": {"min_lon": bounds[0], "min_lat": bounds[1], "max_lon": bounds[2], "max_lat": bounds[3]},
        "scenario": {"id": "RURAL-01", "e0_lon": LON0, "e0_lat": LAT0, "source_radius_m": RADIUS_M, "sector_count": 24},
        "top3": [
            {"rank": row["analytical_rank"], "area": row["area_label"], "sector": f"{row['ring_id']}-{row['direction']}", "score": row["score"]}
            for row in top3
        ],
        "worldcover_percent_within_buffer": {WC_LABELS.get(code, str(code)): round(value, 4) for code, value in percentages.items()},
        "srtm_elevation_m": {"min": round(elev_stats[0], 3), "mean": round(elev_stats[1], 3), "max": round(elev_stats[2], 3)},
        "osm_context_features": {"roads": osm_counts[0], "hydrography": osm_counts[1], "snapshot": "2026-08-17T17:01:35Z"},
        "sources": [],
        "outputs": [],
        "qa": {
            "png_dimensions": [CANVAS_W, CANVAS_H],
            "pdf_expected_pages": 1,
            "panels": 4,
            "ground_truth_coordinates_absent": True,
            "top3_count": len(top3),
            "wms_rgb_optional_not_executed": True,
            "frozen_t2_manifest_sha256_unchanged": t2_hash,
        },
    }
    for path, role in [
        (SECTORS_PATH, "24 setores"),
        (BUFFER_PATH, "buffer de entrada"),
        (TOP3_PATH, "ranking Top-3"),
        (WORLDCOVER_PATH, "cobertura do solo"),
        (SRTM_PATH, "elevação"),
        (ROADS_PATH, "vias OSM"),
        (HYDRO_PATH, "hidrografia OSM"),
        (PHOTO, "fotografia aérea de contexto"),
    ]:
        manifest["sources"].append({"role": role, "path": str(path.relative_to(ROOT)), "sha256": sha256(path)})

    # Gravação inicial para que o manifesto possa listar os demais artefatos sem autorreferência circular.
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for path in [PNG_PATH, PDF_PATH, README_PATH, photo_crop_path, optional_wms]:
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
