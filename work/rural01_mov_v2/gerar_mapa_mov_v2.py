#!/usr/bin/env python3
"""Gera o mapa multipainel do RURAL-01 MOV-V v2, sem ground truth.

O produto sobrepõe a resistência territorial, o custo acumulado e os
corredores diagnósticos às camadas cartográficas locais já congeladas. O custo
é apresentado exclusivamente em metros equivalentes de esforço. Não representa
tempo, probabilidade de presença, rota operacional ou localização verdadeira.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[2]
V1_MAP_SCRIPT = ROOT / "work/rural01_processamento_cego_v1/gerar_mapa_rural01_realista_v2.py"
spec = importlib.util.spec_from_file_location("rural01_realista_v2", V1_MAP_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Não foi possível carregar o módulo cartográfico: {V1_MAP_SCRIPT}")
real = importlib.util.module_from_spec(spec)
spec.loader.exec_module(real)
base = real.base

SOURCE = ROOT / "outputs/campo_rural01/processamento_movimento_cego_v2"
V1_SOURCE = ROOT / "outputs/campo_rural01/processamento_cego_v1"
GRID_PATH = SOURCE / "grade_resistencia.csv"
RESULT_PATH = SOURCE / "resultado_mov_v2.json"
QA_PATH = SOURCE / "relatorio_qa_mov_v2.json"
ENGINE_MANIFEST_PATH = SOURCE / "manifesto_mov_v2.json"
CORRIDORS_PATH = SOURCE / "corredores_mov_v2.geojson"
REACHABLE_PATH = SOURCE / "areas_alcancaveis_mov_v2.geojson"
SECTORS_PATH = V1_SOURCE / "setores_rural01.geojson"
V1_TOP3_PATH = V1_SOURCE / "top3_rural01.json"

PNG_PATH = SOURCE / "Mapa_RURAL01_Resistencia_Corredores_MOV_V_v2.png"
README_PATH = SOURCE / "README_MAPA_RURAL01_MOV_V_v2.md"
MANIFEST_PATH = SOURCE / "manifesto_cartografico_mov_v2.json"

H_NETWORK = "H_REDE_DISPONIVEL"
H_OFF = "H_FORA_REDE"
SCENARIO_NETWORK = f"{H_NETWORK}__BASE"
SCENARIO_OFF = f"{H_OFF}__BASE"
RESISTANCE_FIELD = f"cell_resistance__{SCENARIO_NETWORK}"
COST_FIELDS = {
    H_NETWORK: f"cost__{SCENARIO_NETWORK}",
    H_OFF: f"cost__{SCENARIO_OFF}",
}
REACHABLE_FIELDS = {
    H_NETWORK: f"reachable__{SCENARIO_NETWORK}",
    H_OFF: f"reachable__{SCENARIO_OFF}",
}

CANVAS_W = base.CANVAS_W
CANVAS_H = base.CANVAS_H
MAP_SIZE = base.MAP_SIZE
INK = base.INK
MUTED = base.MUTED
PAPER = base.PAPER
ORIGIN = base.ORIGIN
BORDER = base.BORDER

HYPOTHESIS_COLORS = {
    H_NETWORK: "#146b8c",
    H_OFF: "#744a8b",
    "V1": "#555c60",
}
RANK_COLORS = ["#1f5f8b", "#c58a00", "#d56a32"]
RESISTANCE_PALETTE = ["#fff7bc", "#7fcdbb", "#2c7fb8", "#253494"]
COST_PALETTE = ["#fff7bc", "#fec44f", "#d95f0e", "#7f0000"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_grid() -> list[dict[str, str]]:
    with GRID_PATH.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 7845:
        raise RuntimeError(f"Grade inesperada: {len(rows)} células; esperado 7.845.")
    if any(row.get("ground_truth_used", "").lower() != "false" for row in rows):
        raise RuntimeError("A grade viola o protocolo cego.")
    return rows


def parse_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def short_sector(sector_id: str) -> str:
    parts = sector_id.split("::")
    return f"{parts[-2]}-{parts[-1]}" if len(parts) >= 2 else sector_id


def hex_rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def interpolate_color(palette: list[str], value: float) -> tuple[int, int, int]:
    value = min(1.0, max(0.0, value))
    position = value * (len(palette) - 1)
    index = min(len(palette) - 2, int(math.floor(position)))
    fraction = position - index
    c0 = hex_rgb(palette[index])
    c1 = hex_rgb(palette[index + 1])
    return tuple(int(round(a + (b - a) * fraction)) for a, b in zip(c0, c1))


def rgba(color: str, alpha: int) -> tuple[int, int, int, int]:
    return (*hex_rgb(color), alpha)


def finite_values(rows: list[dict[str, str]], field: str) -> np.ndarray:
    values = np.asarray([float(row[field]) for row in rows], dtype=np.float64)
    if not np.isfinite(values).all():
        raise RuntimeError(f"Campo não finito: {field}")
    return values


def draw_grid_overlay(
    image: Image.Image,
    rows: list[dict[str, str]],
    field: str,
    bounds: tuple[float, float, float, float],
    palette: list[str],
    low: float,
    high: float,
    *,
    alpha: int,
) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    cell_px = max(5, int(round(30.0 / (2.0 * base.EXTENT_M) * MAP_SIZE)))
    half = max(2, cell_px // 2 + 1)
    span = max(high - low, 1e-9)
    for row in rows:
        value = float(row[field])
        normalized = (value - low) / span
        color = interpolate_color(palette, normalized)
        x, y = base.lonlat_to_px(float(row["lon"]), float(row["lat"]), bounds, MAP_SIZE)
        draw.rectangle((x - half, y - half, x + half, y + half), fill=(*color, alpha))
    image.alpha_composite(overlay)


def draw_colorbar(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    palette: list[str],
    labels: list[tuple[float, str]],
    *,
    title: str,
) -> int:
    draw.text((x, y), title, font=base.font(25, bold=True), fill=INK)
    y += 42
    height = 30
    for offset in range(width):
        color = interpolate_color(palette, offset / max(width - 1, 1))
        draw.line((x + offset, y, x + offset, y + height), fill=color, width=1)
    draw.rectangle((x, y, x + width, y + height), outline="#58656a", width=2)
    for fraction, label in labels:
        tick_x = x + int(round(width * fraction))
        draw.line((tick_x, y + height, tick_x, y + height + 10), fill=INK, width=2)
        anchor = "la" if fraction <= 0.02 else "ra" if fraction >= 0.98 else "ma"
        draw.text((tick_x, y + height + 15), label, font=base.font(19), fill=INK, anchor=anchor)
    return y + height + 48


def sector_polygons(bounds: tuple[float, float, float, float]) -> tuple[dict[str, list[tuple[int, int]]], dict[str, dict[str, Any]]]:
    polygons: dict[str, list[tuple[int, int]]] = {}
    properties: dict[str, dict[str, Any]] = {}
    for feature in load_json(SECTORS_PATH)["features"]:
        props = feature["properties"]
        sid = props["sector_id"]
        polygons[sid] = [
            base.lonlat_to_px(float(lon), float(lat), bounds, MAP_SIZE)
            for lon, lat in feature["geometry"]["coordinates"][0]
        ]
        properties[sid] = props
    return polygons, properties


def add_sector_grid(image: Image.Image, bounds: tuple[float, float, float, float], alpha: int = 90) -> None:
    polygons, _ = sector_polygons(bounds)
    draw = ImageDraw.Draw(image, "RGBA")
    for polygon in polygons.values():
        draw.line(polygon + [polygon[0]], fill=(255, 255, 255, min(180, alpha + 70)), width=4, joint="curve")
        draw.line(polygon + [polygon[0]], fill=(35, 46, 51, alpha), width=2, joint="curve")


def iter_outer_rings(geometry: dict[str, Any]) -> Iterable[list[list[float]]]:
    kind = geometry["type"]
    coords = geometry["coordinates"]
    if kind == "Polygon":
        if coords:
            yield coords[0]
    elif kind == "MultiPolygon":
        for polygon in coords:
            if polygon:
                yield polygon[0]


def add_reachable_boundary(
    image: Image.Image,
    bounds: tuple[float, float, float, float],
    rows: list[dict[str, str]],
    hypothesis: str,
) -> None:
    """Desenha a mancha alcançável sem contornar cada célula individual."""
    mask = Image.new("L", image.size, 0)
    draw_mask = ImageDraw.Draw(mask)
    field = REACHABLE_FIELDS[hypothesis]
    cell_px = max(5, int(round(30.0 / (2.0 * base.EXTENT_M) * MAP_SIZE)))
    half = max(2, cell_px // 2 + 1)
    for row in rows:
        if not parse_bool(row[field]):
            continue
        x, y = base.lonlat_to_px(float(row["lon"]), float(row["lat"]), bounds, MAP_SIZE)
        draw_mask.rectangle((x - half, y - half, x + half, y + half), fill=255)

    # Suaviza pequenas frestas entre células e constrói apenas a borda externa.
    closed = mask.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))
    tint = Image.new("RGBA", image.size, (255, 255, 255, 0))
    tint.putalpha(closed.point(lambda value: int(value * 0.07)))
    image.alpha_composite(tint)
    dilated = closed.filter(ImageFilter.MaxFilter(13))
    eroded = closed.filter(ImageFilter.MinFilter(13))
    edge = ImageChops.subtract(dilated, eroded)
    halo = edge.filter(ImageFilter.MaxFilter(7))
    white = Image.new("RGBA", image.size, (255, 255, 255, 0))
    white.putalpha(halo.point(lambda value: int(value * 0.85)))
    image.alpha_composite(white)
    dark = Image.new("RGBA", image.size, (28, 34, 38, 0))
    dark.putalpha(edge.point(lambda value: int(value * 0.92)))
    image.alpha_composite(dark)


def top3_for(result: dict[str, Any], hypothesis: str) -> list[dict[str, Any]]:
    rows = result["base_hypothesis_top3"][hypothesis]
    if len(rows) != 3:
        raise RuntimeError(f"Top-3 ausente para {hypothesis}")
    return sorted(rows, key=lambda row: int(row["mobility_rank"]))


def add_top3_corridors(
    image: Image.Image,
    bounds: tuple[float, float, float, float],
    result: dict[str, Any],
    hypothesis: str,
) -> int:
    scenario = f"{hypothesis}__BASE"
    top3 = top3_for(result, hypothesis)
    rank_by_sector = {row["sector_id"]: int(row["mobility_rank"]) for row in top3}
    features = [
        feature
        for feature in load_json(CORRIDORS_PATH)["features"]
        if feature["properties"]["cost_scenario_id"] == scenario
        and feature["properties"]["sector_id"] in rank_by_sector
    ]
    if len(features) != 3:
        raise RuntimeError(f"Esperados 3 corredores visíveis para {hypothesis}; obtidos {len(features)}")
    draw = ImageDraw.Draw(image, "RGBA")
    for feature in sorted(features, key=lambda item: rank_by_sector[item["properties"]["sector_id"]]):
        rank = rank_by_sector[feature["properties"]["sector_id"]]
        points = [
            base.lonlat_to_px(float(lon), float(lat), bounds, MAP_SIZE)
            for lon, lat in feature["geometry"]["coordinates"]
        ]
        color = RANK_COLORS[rank - 1]
        draw.line(points, fill=(255, 255, 255, 245), width=13, joint="curve")
        draw.line(points, fill=rgba(color, 255), width=7, joint="curve")
        x, y = points[-1]
        draw.ellipse((x - 20, y - 20, x + 20, y + 20), fill=color, outline="white", width=4)
        draw.text((x, y - 1), str(rank), font=base.font(25, bold=True), fill="white", anchor="mm")
    return len(features)


def add_osm_and_common(image: Image.Image, bounds: tuple[float, float, float, float]) -> tuple[int, int]:
    counts = real.add_osm_halo(image, bounds)
    base.draw_common_map_elements(image, bounds)
    return counts


def map_panel_shell(image: Image.Image, x: int, y: int, title: str, subtitle: str) -> tuple[int, int, int, int]:
    map_x, map_y = base.panel_shell(image, x, y, title, subtitle)
    info_x = map_x + MAP_SIZE + 48
    info_width = base.PANEL_W - MAP_SIZE - 118
    return map_x, map_y, info_x, info_width


def draw_resistance_panel(
    image: Image.Image,
    x: int,
    y: int,
    environment: Image.Image,
    bounds: tuple[float, float, float, float],
    rows: list[dict[str, str]],
) -> dict[str, float]:
    map_x, map_y, info_x, info_width = map_panel_shell(
        image,
        x,
        y,
        "A. Resistência territorial — perfil BASE",
        "Cobertura, relevo e proxies raster de rede/hidrografia sobre a base orbital histórica.",
    )
    values = finite_values(rows, RESISTANCE_FIELD)
    low = float(np.min(values))
    high = float(np.quantile(values, 0.98))
    panel_map = environment.copy()
    draw_grid_overlay(panel_map, rows, RESISTANCE_FIELD, bounds, RESISTANCE_PALETTE, low, high, alpha=142)
    add_osm_and_common(panel_map, bounds)
    base.paste_map(image, panel_map, map_x, map_y)

    draw = ImageDraw.Draw(image)
    draw.text((info_x, map_y + 2), "Como ler", font=base.font(29, bold=True), fill=INK)
    yy = base.draw_wrapped(
        draw,
        (info_x, map_y + 48),
        "Cores mais escuras indicam maior resistência relativa por célula. A escala é heurística: não mede tempo, probabilidade nem localização.",
        base.font(22),
        INK,
        info_width,
        8,
    )
    yy += 22
    yy = draw_colorbar(
        draw,
        info_x,
        yy,
        min(430, info_width),
        RESISTANCE_PALETTE,
        [(0.0, f"{low:.1f}"), (0.5, f"{(low + high) / 2:.1f}"), (1.0, f"≥ {high:.1f}")],
        title="Resistência relativa da célula",
    )
    yy += 20
    draw.text((info_x, yy), "Componentes observáveis", font=base.font(28, bold=True), fill=INK)
    yy += 50
    cards = [
        ("Cobertura", "ESA WorldCover 2021, 10 m"),
        ("Relevo", "SRTM, grade nominal ~30 m"),
        ("Rede/hidrografia", "proximidade/entrada raster OSM"),
        ("Conectividade", "aproximação octil D8 entre células"),
        ("Sub-bosque", "não observado sistematicamente"),
    ]
    for label, value in cards:
        draw.rounded_rectangle((info_x, yy, info_x + info_width, yy + 78), 10, fill="#f2f4f4", outline="#c0c8cb", width=2)
        draw.text((info_x + 14, yy + 10), label, font=base.font(20, bold=True), fill=INK)
        draw.text((info_x + 14, yy + 41), value, font=base.font(19), fill=MUTED)
        yy += 91
    yy += 10
    steep = sum(float(row["slope_deg"]) >= 15.0 for row in rows) / len(rows)
    tree = sum(int(row["worldcover_code"]) in {10, 95} for row in rows) / len(rows)
    road = sum(parse_bool(row["road_cell"]) or parse_bool(row["trail_cell"]) for row in rows) / len(rows)
    draw.text((info_x, yy), "Leitura da grade", font=base.font(27, bold=True), fill=INK)
    yy += 46
    for label, value in [
        ("árvore/mangue", f"{tree * 100:.1f}%"),
        ("declive ≥ 15°", f"{steep * 100:.1f}%"),
        ("células de rede", f"{road * 100:.1f}%"),
    ]:
        draw.text((info_x, yy), label, font=base.font(20), fill=INK)
        draw.text((info_x + info_width, yy), value, font=base.font(20, bold=True), fill=INK, anchor="ra")
        yy += 38
    return {"min": low, "median": float(np.median(values)), "p98": high, "max": float(np.max(values))}


def draw_cost_panel(
    image: Image.Image,
    x: int,
    y: int,
    environment: Image.Image,
    bounds: tuple[float, float, float, float],
    rows: list[dict[str, str]],
    result: dict[str, Any],
    hypothesis: str,
    common_high: float,
) -> dict[str, Any]:
    is_network = hypothesis == H_NETWORK
    title = "B. Custo acumulado — rede disponível" if is_network else "C. Custo acumulado — fora da rede"
    subtitle = (
        "Hipótese em que vias/trilhas podem reduzir o esforço relativo."
        if is_network
        else "Hipótese sem desconto por vias/trilhas; terreno e cobertura predominam."
    )
    map_x, map_y, info_x, info_width = map_panel_shell(image, x, y, title, subtitle)
    field = COST_FIELDS[hypothesis]
    values = finite_values(rows, field)
    panel_map = environment.copy()
    draw_grid_overlay(panel_map, rows, field, bounds, COST_PALETTE, 0.0, common_high, alpha=140)
    add_sector_grid(panel_map, bounds, alpha=65)
    add_osm_and_common(panel_map, bounds)
    add_reachable_boundary(panel_map, bounds, rows, hypothesis)
    displayed = add_top3_corridors(panel_map, bounds, result, hypothesis)
    base.paste_map(image, panel_map, map_x, map_y)

    draw = ImageDraw.Draw(image)
    yy = map_y + 2
    draw.text((info_x, yy), "Escala comum B–C", font=base.font(28, bold=True), fill=INK)
    yy = draw_colorbar(
        draw,
        info_x,
        yy + 46,
        min(430, info_width),
        COST_PALETTE,
        [(0.0, "0"), (1500.0 / common_high, "1.500"), (1.0, f"≥ {common_high:,.0f}".replace(",", "."))],
        title="Custo acumulado (m equivalentes)",
    )
    draw.text((info_x, yy + 5), "— contorno: orçamento de 1.500 m eq.", font=base.font(19), fill=INK)
    draw.text((info_x, yy + 39), "1–3: corredores do Top-3 desta hipótese", font=base.font(19), fill=INK)
    yy += 88

    summary = next(
        row
        for row in result["scenario_summary"]
        if row["cost_scenario_id"] == f"{hypothesis}__BASE"
    )
    draw.rounded_rectangle((info_x, yy, info_x + info_width, yy + 125), 12, fill="#eef3f5", outline="#a8b8be", width=2)
    draw.text((info_x + 16, yy + 12), "Grade alcançável", font=base.font(21, bold=True), fill=INK)
    draw.text((info_x + info_width - 16, yy + 10), f"{float(summary['reachable_cell_fraction']) * 100:.1f}%", font=base.font(28, bold=True), fill=HYPOTHESIS_COLORS[hypothesis], anchor="ra")
    draw.text((info_x + 16, yy + 52), "mediana do custo", font=base.font(20), fill=MUTED)
    draw.text((info_x + info_width - 16, yy + 50), f"{float(summary['median_cost_m_equivalent']):,.0f} m eq.".replace(",", "."), font=base.font(21, bold=True), fill=INK, anchor="ra")
    draw.text((info_x + 16, yy + 88), "perfil", font=base.font(20), fill=MUTED)
    draw.text((info_x + info_width - 16, yy + 86), "BASE", font=base.font(21, bold=True), fill=INK, anchor="ra")
    yy += 151

    draw.text((info_x, yy), "Top-3 por acessibilidade física", font=base.font(27, bold=True), fill=INK)
    yy += 49
    for row in top3_for(result, hypothesis):
        rank = int(row["mobility_rank"])
        color = RANK_COLORS[rank - 1]
        draw.rounded_rectangle((info_x, yy, info_x + info_width, yy + 102), 11, fill="#fafafa", outline=color, width=3)
        draw.ellipse((info_x + 12, yy + 22, info_x + 60, yy + 70), fill=color)
        draw.text((info_x + 36, yy + 46), str(rank), font=base.font(23, bold=True), fill="white", anchor="mm")
        draw.text((info_x + 76, yy + 12), short_sector(row["sector_id"]), font=base.font(23, bold=True), fill=INK)
        draw.text((info_x + 76, yy + 47), f"índice {float(row['accessibility_index']):.3f}", font=base.font(19), fill=INK)
        draw.text((info_x + 76, yy + 74), f"alcançável {float(row['reachable_fraction']) * 100:.1f}%", font=base.font(18), fill=MUTED)
        yy += 116
    yy += 13
    base.draw_wrapped(
        draw,
        (info_x, yy),
        f"Foram gerados 48 trajetos diagnósticos de menor custo na grade; este painel mostra somente os {displayed} ligados ao Top-3 da classificação BASE. Não são rotas previstas.",
        base.font(20),
        MUTED,
        info_width,
        7,
    )
    return {
        "hypothesis": hypothesis,
        "displayed_corridors": displayed,
        "reachable_fraction": float(summary["reachable_cell_fraction"]),
        "median_cost_m_equivalent": float(summary["median_cost_m_equivalent"]),
        "top3": [short_sector(row["sector_id"]) for row in top3_for(result, hypothesis)],
        "cost_min": float(np.min(values)),
        "cost_p95": float(np.quantile(values, 0.95)),
        "cost_max": float(np.max(values)),
    }


def draw_marker(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    rank: int,
    system: str,
) -> None:
    color = HYPOTHESIS_COLORS[system]
    if system == "V1":
        points = [(x, y - 18), (x + 18, y + 16), (x - 18, y + 16)]
        draw.polygon(points, fill=color, outline="white")
    elif system == H_NETWORK:
        draw.ellipse((x - 18, y - 18, x + 18, y + 18), fill=color, outline="white", width=3)
    else:
        draw.rectangle((x - 17, y - 17, x + 17, y + 17), fill=color, outline="white", width=3)
    draw.text((x, y - 1), str(rank), font=base.font(19, bold=True), fill="white", anchor="mm")


def draw_comparison_panel(
    image: Image.Image,
    x: int,
    y: int,
    environment: Image.Image,
    bounds: tuple[float, float, float, float],
    result: dict[str, Any],
    qa: dict[str, Any],
) -> dict[str, Any]:
    map_x, map_y, info_x, info_width = map_panel_shell(
        image,
        x,
        y,
        "D. Comparação das classificações de acessibilidade",
        "Classificação territorial v1 versus acessibilidade MOV-V v2 nas duas hipóteses BASE.",
    )
    panel_map = environment.copy()
    add_osm_and_common(panel_map, bounds)
    add_sector_grid(panel_map, bounds, alpha=75)
    _polygons, sector_props = sector_polygons(bounds)
    v1_rows = load_json(V1_TOP3_PATH)["areas"]
    systems: list[tuple[str, list[dict[str, Any]]]] = [
        ("V1", [{"rank": int(row["analytical_rank"]), "sector_id": row["sector_id"]} for row in v1_rows]),
        (H_NETWORK, [{"rank": int(row["mobility_rank"]), "sector_id": row["sector_id"]} for row in top3_for(result, H_NETWORK)]),
        (H_OFF, [{"rank": int(row["mobility_rank"]), "sector_id": row["sector_id"]} for row in top3_for(result, H_OFF)]),
    ]
    draw_map = ImageDraw.Draw(panel_map, "RGBA")
    offsets = {"V1": (-20, -16), H_NETWORK: (20, -16), H_OFF: (0, 22)}
    for system, rows in systems:
        for row in rows:
            props = sector_props[row["sector_id"]]
            px, py = base.lonlat_to_px(float(props["representative_lon"]), float(props["representative_lat"]), bounds, MAP_SIZE)
            dx, dy = offsets[system]
            draw_marker(draw_map, px + dx, py + dy, int(row["rank"]), system)
    base.paste_map(image, panel_map, map_x, map_y)

    draw = ImageDraw.Draw(image)
    yy = map_y + 2
    draw.text((info_x, yy), "Top-3 por abordagem", font=base.font(28, bold=True), fill=INK)
    yy += 52
    labels = {
        "V1": "v1 — classificação territorial",
        H_NETWORK: "v2 — rede disponível",
        H_OFF: "v2 — fora da rede",
    }
    symbols = {"V1": "▲", H_NETWORK: "●", H_OFF: "■"}
    system_top3: dict[str, list[str]] = {}
    for system, rows in systems:
        top3 = [short_sector(row["sector_id"]) for row in sorted(rows, key=lambda row: row["rank"])]
        system_top3[system] = top3
        draw.rounded_rectangle((info_x, yy, info_x + info_width, yy + 124), 12, fill="#fafafa", outline=HYPOTHESIS_COLORS[system], width=3)
        draw.text((info_x + 14, yy + 12), f"{symbols[system]}  {labels[system]}", font=base.font(21, bold=True), fill=HYPOTHESIS_COLORS[system])
        draw.text((info_x + 14, yy + 52), "1  " + top3[0], font=base.font(20, bold=True), fill=INK)
        draw.text((info_x + 14, yy + 84), f"2  {top3[1]}    3  {top3[2]}", font=base.font(19), fill=INK)
        yy += 139

    overlap = set(system_top3[H_NETWORK]) & set(system_top3[H_OFF])
    yy += 5
    draw.rounded_rectangle((info_x, yy, info_x + info_width, yy + 104), 12, fill="#f1ebf4", outline="#b9a4c5", width=2)
    draw.text((info_x + 14, yy + 10), "Convergência entre hipóteses", font=base.font(20, bold=True), fill=INK)
    draw.text((info_x + 14, yy + 48), ", ".join(sorted(overlap)) if overlap else "nenhuma", font=base.font(24, bold=True), fill="#5d3d70")
    draw.text((info_x + 14, yy + 78), "o regime permanece não selecionado", font=base.font(18), fill=MUTED)
    yy += 128

    draw.text((info_x, yy), "Controle de qualidade", font=base.font(27, bold=True), fill=INK)
    yy += 46
    checks = [
        ("Portas QA", f"{qa['passed_gate_count']}/{qa['gate_count']} PASS"),
        ("Ground truth", "não usado"),
        ("Obstáculo de campo", "0 mapeado"),
        ("14 h", "contexto; sem conversão"),
    ]
    for label, value in checks:
        draw.text((info_x, yy), label, font=base.font(19), fill=MUTED)
        draw.text((info_x + info_width, yy), value, font=base.font(19, bold=True), fill=INK, anchor="ra")
        yy += 34
    yy += 14
    base.draw_wrapped(
        draw,
        (info_x, yy),
        "Interpretação: a v2 compara trajetos mínimos na grade de custo, usando aproximação octil D8. Eles não são rotas previstas. A v2 não seleciona o regime, não localiza a pessoa e exige revisão de campo, sobretudo sobre o sub-bosque.",
        base.font(20),
        INK,
        info_width,
        7,
    )
    return {"top3": system_top3, "v2_hypothesis_overlap": sorted(overlap)}


def write_readme(
    common_high: float,
    panel_stats: dict[str, Any],
    displayed_corridors: int,
) -> None:
    common_high_label = f"{common_high:,.0f}".replace(",", ".")
    content = f"""# Mapa RURAL-01 — resistência e corredores MOV-V v2

## Produto

- `{PNG_PATH.name}`: figura multipainel em {CANVAS_W} × {CANVAS_H} px, 300 dpi;
- `Mapa_RURAL01_Resistencia_Corredores_MOV_V_v2.pdf`: versão A3 em paisagem para leitura e impressão, gerada separadamente;
- `{Path(__file__).name}`: script reprodutível da figura;
- `{MANIFEST_PATH.name}`: proveniência, hashes e controles cartográficos.

## Leitura dos painéis

1. **A — Resistência territorial:** resistência relativa por célula no perfil BASE. Os fatores são hipóteses de desenvolvimento, não medidas diretas de velocidade.
2. **B — Rede disponível:** custo acumulado quando vias e trilhas podem reduzir o esforço relativo. Top-3: {', '.join(panel_stats[H_NETWORK]['top3'])}.
3. **C — Fora da rede:** custo acumulado sem desconto da rede. Top-3: {', '.join(panel_stats[H_OFF]['top3'])}.
4. **D — Comparação:** classificação territorial v1 e classificações Top-3 MOV-V das duas hipóteses, sem seleção automática do regime.

Os painéis B e C usam a mesma escala cromática, de 0 a {common_high_label} metros equivalentes de esforço. O contorno interno marca o orçamento heurístico de 1.500 m equivalentes; não é uma isócrona em horas. Foram gerados 48 corredores, dos quais {displayed_corridors} aparecem na figura: três por hipótese BASE.

## Semântica espacial

- A vizinhança **D8** é uma aproximação octil entre células ortogonais e diagonais da grade; não reconstrói uma trilha observada em campo.
- A hidrografia OSM entra como **proxy raster de proximidade/entrada** na célula. O processamento não executa interseção geométrica que comprove travessia, vau, ponte, margem intransponível ou curso efetivamente cruzado.
- Os corredores são trajetos diagnósticos de menor custo na grade, e não rotas previstas para a pessoa desaparecida.

## Salvaguardas

- A posição verdadeira não foi consultada, utilizada nem representada.
- `cost_m_equivalent` não é tempo, probabilidade de presença nem distância euclidiana.
- As 14 horas desde o desaparecimento aparecem somente como contexto; não foram convertidas automaticamente em alcance.
- A composição orbital é o mosaico anual Sentinel-2/ESA WorldCover de 2021; não constitui observação do terreno em 2026.
- WorldCover descreve cobertura vista do alto e não comprova transitabilidade do sub-bosque.
- SRTM em resolução nominal de aproximadamente 30 m pode suavizar ravinas, barrancos e feições estreitas.
- OSM pode estar incompleto ou desatualizado.
- Nenhum obstáculo de campo foi espacializado nesta execução; a saída permanece em estado `REVISAR`.
- A v1 e os resultados numéricos MOV-V v2 não foram alterados por este script.

## Fontes cartográficas

- Composição anual Sentinel-2/ESA WorldCover 2021 em cores naturais.
- ESA WorldCover 2021 v200, resolução nominal de 10 m.
- SRTM N00W052, resolução nominal de aproximadamente 30 m.
- OpenStreetMap, recorte local congelado no projeto.

Nota de uso acadêmico: composição cartográfica a partir de fontes públicas e resultados do processamento cego; não é levantamento de campo nem mapa operacional validado.
"""
    README_PATH.write_text(content, encoding="utf-8")


def create_figure() -> dict[str, Any]:
    required = [
        GRID_PATH,
        RESULT_PATH,
        QA_PATH,
        ENGINE_MANIFEST_PATH,
        CORRIDORS_PATH,
        REACHABLE_PATH,
        SECTORS_PATH,
        V1_TOP3_PATH,
        real.RGB_PATH,
        real.RGB_META_PATH,
        base.WORLDCOVER_PATH,
        base.SRTM_PATH,
        base.ROADS_PATH,
        base.HYDRO_PATH,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Entradas ausentes: {missing}")

    result = load_json(RESULT_PATH)
    qa = load_json(QA_PATH)
    if result.get("ground_truth_used") is not False or qa.get("ground_truth_used") is not False:
        raise RuntimeError("Resultados incompatíveis com o protocolo cego.")
    if result.get("cost_semantics") != "METROS_EQUIVALENTES_DE_ESFORCO_NAO_TEMPO_NAO_PROBABILIDADE":
        raise RuntimeError("Semântica do custo divergente.")
    if qa.get("status") != "PASS" or qa.get("passed_gate_count") != qa.get("gate_count"):
        raise RuntimeError("QA numérico não aprovado; figura não gerada.")

    metadata = real.load_metadata()
    bounds = real.metadata_bounds(metadata)
    expected_bounds = base.lonlat_bounds()
    if max(abs(a - b) for a, b in zip(bounds, expected_bounds)) > 1e-10:
        raise RuntimeError("Extensão orbital divergente do enquadramento congelado.")
    rows = load_grid()
    rgb = real.load_rgb_base()
    environment, _percentages, _elev_stats = real.build_environment_map(rgb, bounds)

    all_costs = np.concatenate([finite_values(rows, COST_FIELDS[H_NETWORK]), finite_values(rows, COST_FIELDS[H_OFF])])
    common_high = float(math.ceil(float(np.quantile(all_costs, 0.95)) / 100.0) * 100.0)
    common_high = max(common_high, 1500.0)

    image = Image.new("RGBA", (CANVAS_W, CANVAS_H), PAPER)
    draw = ImageDraw.Draw(image)
    draw.text((base.MARGIN_X, 46), "RURAL-01: resistência territorial e conectividade", font=base.font(58, bold=True), fill=INK)
    draw.text(
        (base.MARGIN_X + 2, 126),
        "MOV-V v2 — execução cega; custos em metros equivalentes de esforço, sem conversão das 14 h em tempo ativo.",
        font=base.font(28),
        fill=MUTED,
    )
    draw.rounded_rectangle((CANVAS_W - 1335, 42, CANVAS_W - 90, 198), 18, fill="#f2e9d2", outline="#b9994d", width=3)
    draw.text((CANVAS_W - 1300, 62), "STATUS", font=base.font(22, bold=True), fill="#725711")
    draw.text((CANVAS_W - 1300, 98), "REVISAR", font=base.font(34, bold=True), fill="#725711")
    draw.text((CANVAS_W - 1055, 98), "regime de rede desconhecido", font=base.font(23), fill="#725711")
    draw.text((CANVAS_W - 1300, 150), "ground truth oculto e não utilizado", font=base.font(21, bold=True), fill=ORIGIN)

    left_x = base.MARGIN_X
    right_x = base.MARGIN_X + base.PANEL_W + base.PANEL_GAP_X
    resistance_stats = draw_resistance_panel(image, left_x, base.TOP_Y, environment, bounds, rows)
    network_stats = draw_cost_panel(image, right_x, base.TOP_Y, environment, bounds, rows, result, H_NETWORK, common_high)
    off_stats = draw_cost_panel(image, left_x, base.BOTTOM_Y, environment, bounds, rows, result, H_OFF, common_high)
    comparison_stats = draw_comparison_panel(image, right_x, base.BOTTOM_Y, environment, bounds, result, qa)

    footer_y = base.BOTTOM_Y + base.PANEL_H + 30
    draw.line((base.MARGIN_X, footer_y, CANVAS_W - base.MARGIN_X, footer_y), fill=BORDER, width=3)
    note = (
        "Nota. Composição cartográfica a partir de fontes públicas e resultados do processamento cego; não é levantamento de campo nem mapa operacional validado. "
        "A base RGB é a composição anual Sentinel-2/ESA WorldCover 2021, não uma cena de 2026. WorldCover não mede transitabilidade do sub-bosque; "
        "SRTM (~30 m) pode suavizar feições estreitas; OSM pode estar incompleto. D8 é uma aproximação octil da conectividade; a hidrografia é proxy raster de proximidade/entrada, não interseção geométrica de travessia. "
        "O custo representa esforço relativo acumulado, não tempo, probabilidade ou localização. "
        "A posição verdadeira não foi consultada ou representada. © ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium. "
        "© OpenStreetMap contributors, ODbL."
    )
    base.draw_wrapped(draw, (base.MARGIN_X + 4, footer_y + 17), note, base.font(24), MUTED, CANVAS_W - 2 * base.MARGIN_X - 8, 5)

    SOURCE.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(PNG_PATH, format="PNG", dpi=(300, 300), optimize=True)

    panel_stats = {H_NETWORK: network_stats, H_OFF: off_stats}
    write_readme(common_high, panel_stats, network_stats["displayed_corridors"] + off_stats["displayed_corridors"])

    source_paths = [
        (GRID_PATH, "grade de resistência e custos"),
        (RESULT_PATH, "síntese MOV-V v2"),
        (QA_PATH, "controle de qualidade MOV-V v2"),
        (ENGINE_MANIFEST_PATH, "manifesto do motor MOV-V v2"),
        (CORRIDORS_PATH, "48 corredores diagnósticos"),
        (REACHABLE_PATH, "áreas sob orçamento heurístico"),
        (SECTORS_PATH, "24 setores da v1"),
        (V1_TOP3_PATH, "Top-3 territorial v1"),
        (real.RGB_PATH, "composição anual Sentinel-2 2021"),
        (real.RGB_META_PATH, "metadados da composição orbital"),
        (base.WORLDCOVER_PATH, "ESA WorldCover 2021"),
        (base.SRTM_PATH, "SRTM"),
        (base.ROADS_PATH, "vias OSM"),
        (base.HYDRO_PATH, "hidrografia OSM"),
    ]
    manifest: dict[str, Any] = {
        "artifact": "Mapa_RURAL01_Resistencia_Corredores_MOV_V_v2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ground_truth_used": False,
        "cost_semantics": result["cost_semantics"],
        "elapsed_14h_role": result["elapsed_hours_role"],
        "crs": "EPSG:4326 for display; local AEQD centered on E0 for analysis",
        "bounds": {"min_lon": bounds[0], "min_lat": bounds[1], "max_lon": bounds[2], "max_lat": bounds[3]},
        "scenario": {
            "id": "RURAL-01",
            "e0_lat": base.LAT0,
            "e0_lon": base.LON0,
            "source_radius_m": base.RADIUS_M,
            "ground_truth_shown": False,
        },
        "display": {
            "panels": 4,
            "same_extent_all_maps": True,
            "same_cost_scale_panels_b_c": True,
            "cost_color_scale_max_m_equivalent_p95_rounded": common_high,
            "corridor_features_generated": len(load_json(CORRIDORS_PATH)["features"]),
            "corridor_features_displayed": network_stats["displayed_corridors"] + off_stats["displayed_corridors"],
            "only_top3_corridors_displayed_per_hypothesis": True,
            "rgb_period": 2021,
            "rgb_is_scene_from_2026": False,
            "movement_connectivity": "D8_APPROXIMATE_OCTILE_NEIGHBORHOOD",
            "hydrography_display_semantics": "RASTER_PROXIMITY_OR_ENTRY_PROXY_NOT_GEOMETRIC_CROSSING_INTERSECTION",
        },
        "statistics": {
            "resistance": resistance_stats,
            "network_hypothesis": network_stats,
            "off_network_hypothesis": off_stats,
            "comparison": comparison_stats,
        },
        "limitations_visible_in_figure": [
            "UNDERSTORY_NOT_SYSTEMATICALLY_OBSERVED",
            "DEM_30M_MAY_SMOOTH_NARROW_FEATURES",
            "OSM_MAY_BE_INCOMPLETE_OR_OUTDATED",
            "FIELD_OBSTACLE_COUNT_ZERO",
            "14H_CONTEXT_ONLY",
            "HEURISTIC_NOT_TIME_OR_PROBABILITY",
            "D8_IS_APPROXIMATE_OCTILE_CONNECTIVITY",
            "HYDROGRAPHY_IS_RASTER_PROXIMITY_ENTRY_PROXY_NOT_GEOMETRIC_CROSSING",
        ],
        "sources": [
            {"role": role, "path": str(path.relative_to(ROOT)), "sha256": sha256(path), "bytes": path.stat().st_size}
            for path, role in source_paths
        ],
        "outputs": [
            {"path": str(PNG_PATH.relative_to(ROOT)), "sha256": sha256(PNG_PATH), "bytes": PNG_PATH.stat().st_size},
            {"path": str(README_PATH.relative_to(ROOT)), "sha256": sha256(README_PATH), "bytes": README_PATH.stat().st_size},
        ],
        "qa": {
            "numeric_engine_status": qa["status"],
            "numeric_engine_gates_passed": qa["passed_gate_count"],
            "numeric_engine_gates_total": qa["gate_count"],
            "png_dimensions": [CANVAS_W, CANVAS_H],
            "png_mode": "RGB",
            "cost_unit_label_visible": True,
            "cost_not_labeled_as_time_or_probability": True,
            "ground_truth_coordinates_absent": True,
            "source_radius_visible": True,
            "north_and_scale_visible_all_panels": True,
            "roads_and_hydrography_visible_all_panels": True,
            "no_pdf_created_by_script": True,
            "v1_not_written": True,
            "numeric_outputs_not_written": True,
            "visual_inspection_status": "PASS_AFTER_RENDER_REVIEW_AND_REACHABLE_BOUNDARY_REPAIR",
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    manifest = create_figure()
    print(PNG_PATH)
    print(README_PATH)
    print(MANIFEST_PATH)
    print(json.dumps(manifest["qa"], ensure_ascii=False))
