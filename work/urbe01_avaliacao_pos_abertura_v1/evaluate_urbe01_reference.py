#!/usr/bin/env python3
"""Avalia a referência revelada do URBE-01 contra saídas previamente congeladas.

Este programa NÃO recalcula setores, atributos GEO, escores ou rankings. Ele lê o
pacote cego v1, registra a referência declarada pelo usuário em etapa posterior e
mede cobertura/rank. A pertença espacial é verificada por dois métodos
independentes: ponto-no-polígono e distância/azimute geodésicos.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "outputs/campo_urbe01/processamento_cego_v1"
DEFAULT_OUT = ROOT / "outputs/campo_urbe01/avaliacao_pos_abertura_v1"
FROZEN_RESULT = FROZEN / "resultado_urbe01_cego.json"
FROZEN_SECTORS = FROZEN / "setores_urbe01.geojson"
FROZEN_MANIFEST = FROZEN / "manifesto_processamento_cego.json"
FROZEN_MAP = FROZEN / "Mapa_URBE01_Processamento_Cego_BASE_PERFIL_v1.png"

REFERENCE_LAT_TEXT = "0.0024809355844815323"
REFERENCE_LON_TEXT = "-51.07092698392779"
REFERENCE_LAT = float(REFERENCE_LAT_TEXT)
REFERENCE_LON = float(REFERENCE_LON_TEXT)
LOCAL_TZ = ZoneInfo("America/Belem")
EARTH_RADIUS_M = 6_371_008.8

SCIENTIFIC_FILES = (
    "registro_abertura_referencia.json",
    "resultado_avaliacao_pos_abertura.json",
    "avaliacao_rankings.csv",
    "distancias_top3.csv",
    "referencia_setores_e_top3.geojson",
    "verificacao_independente.json",
    "relatorio_avaliacao_pos_abertura.md",
    "Mapa_URBE01_Avaliacao_Pos_Abertura_v1.png",
    "Mapa_URBE01_Avaliacao_Pos_Abertura_v1.pdf",
)

FONT_REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def frozen_tree_snapshot(directory: Path) -> dict[str, Any]:
    files = []
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.name != ".DS_Store":
            files.append(
                {
                    "path": str(path.relative_to(directory)),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    return {
        "root": str(directory.relative_to(ROOT)),
        "file_count": len(files),
        "files": files,
        "tree_sha256": _canonical_hash(files),
    }


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def lonlat_to_local_m(lon: float, lat: float, lon0: float, lat0: float) -> tuple[float, float]:
    x = EARTH_RADIUS_M * math.cos(math.radians(lat0)) * math.radians(lon - lon0)
    y = EARTH_RADIUS_M * math.radians(lat - lat0)
    return x, y


def point_segment_distance_m(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    px, py = point
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def polygon_relation(
    lon: float,
    lat: float,
    ring_lonlat: Sequence[Sequence[float]],
    lon0: float,
    lat0: float,
    boundary_tolerance_m: float = 0.05,
) -> str:
    """Retorna INSIDE, BOUNDARY ou OUTSIDE em projeção local apropriada ao raio de 2,5 km."""
    point = lonlat_to_local_m(lon, lat, lon0, lat0)
    ring = [lonlat_to_local_m(float(x), float(y), lon0, lat0) for x, y in ring_lonlat]
    for a, b in zip(ring, ring[1:]):
        if point_segment_distance_m(point, a, b) <= boundary_tolerance_m:
            return "BOUNDARY"
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y):
            crossing_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing_x:
                inside = not inside
    return "INSIDE" if inside else "OUTSIDE"


def minimum_distance_to_polygon_m(
    lon: float, lat: float, ring_lonlat: Sequence[Sequence[float]], lon0: float, lat0: float
) -> float:
    relation = polygon_relation(lon, lat, ring_lonlat, lon0, lat0)
    if relation in {"INSIDE", "BOUNDARY"}:
        return 0.0
    point = lonlat_to_local_m(lon, lat, lon0, lat0)
    ring = [lonlat_to_local_m(float(x), float(y), lon0, lat0) for x, y in ring_lonlat]
    return min(point_segment_distance_m(point, a, b) for a, b in zip(ring, ring[1:]))


def minimum_distance_to_polygon_boundary_m(
    lon: float, lat: float, ring_lonlat: Sequence[Sequence[float]], lon0: float, lat0: float
) -> float:
    """Distância local mínima até a borda, inclusive quando o ponto está dentro."""
    point = lonlat_to_local_m(lon, lat, lon0, lat0)
    ring = [lonlat_to_local_m(float(x), float(y), lon0, lat0) for x, y in ring_lonlat]
    return min(point_segment_distance_m(point, a, b) for a, b in zip(ring, ring[1:]))


def analytic_sector(distance_m: float, bearing_deg: float, sector_features: Sequence[Mapping[str, Any]]) -> str | None:
    ring_id = None
    for feature in sector_features:
        props = feature["properties"]
        inner = float(props["inner_radius_m"])
        outer = float(props["outer_radius_m"])
        if inner - 0.05 <= distance_m <= outer + 0.05:
            ring_id = str(props["ring_id"])
            break
    if ring_id is None:
        return None
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    direction_index = int(((bearing_deg + 22.5) % 360.0) // 45.0)
    direction = directions[direction_index]
    for feature in sector_features:
        props = feature["properties"]
        if str(props["ring_id"]) == ring_id and str(props["direction"]) == direction:
            return str(props["sector_id"])
    return None


def _features_by_id(doc: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(f["properties"]["sector_id"]): f for f in doc["features"]}


def _rank_row(rows: Sequence[Mapping[str, Any]], sector_id: str) -> Mapping[str, Any]:
    for row in rows:
        if str(row["sector_id"]) == sector_id:
            return row
    raise KeyError(sector_id)


def build_evaluation(opened_at_local: str) -> dict[str, Any]:
    result_doc = _load_json(FROZEN_RESULT)
    sectors_doc = _load_json(FROZEN_SECTORS)
    manifest_doc = _load_json(FROZEN_MANIFEST)
    features = sectors_doc["features"]
    by_id = _features_by_id(sectors_doc)
    e0 = result_doc["buffer_results"][0] if "buffer_results" in result_doc else result_doc.get("buffer_rows", [None])[0]
    if e0 is None:
        # Estrutura publicada do pacote v1.
        input_doc = _load_json(FROZEN / "entrada_raio_fonte.json")
        e0 = input_doc["results"][0]
    lat0 = float(e0["estimated_lat"])
    lon0 = float(e0["estimated_lon"])
    radius_m = float(e0["adaptive_radius_m"])

    relations = []
    for feature in features:
        ring = feature["geometry"]["coordinates"][0]
        relation = polygon_relation(REFERENCE_LON, REFERENCE_LAT, ring, lon0, lat0)
        if relation != "OUTSIDE":
            relations.append({"sector_id": str(feature["properties"]["sector_id"]), "relation": relation})

    distance_e0 = haversine_m(lat0, lon0, REFERENCE_LAT, REFERENCE_LON)
    bearing_e0 = initial_bearing_deg(lat0, lon0, REFERENCE_LAT, REFERENCE_LON)
    analytic_id = analytic_sector(distance_e0, bearing_e0, features)
    matched_ids = sorted(item["sector_id"] for item in relations)
    if not matched_ids:
        primary_sector_id = None
    elif len(matched_ids) == 1:
        primary_sector_id = matched_ids[0]
    else:
        # Critério conservador: setor com a pior posição combinada; desempate por ID.
        base_rows = result_doc["base_results"]
        profile_rows = result_doc["profile_results"]
        primary_sector_id = max(
            matched_ids,
            key=lambda sid: (
                max(
                    int(_rank_row(base_rows, sid)["rank_base_within_buffer"]),
                    int(_rank_row(profile_rows, sid)["profile_rank_within_buffer"]),
                ),
                sid,
            ),
        )

    geometry_check = {
        "method": "LOCAL_EQUIRECTANGULAR_POINT_IN_POLYGON_WITH_0_05_M_BOUNDARY_TOLERANCE",
        "matched_sectors": relations,
        "primary_sector_conservative": primary_sector_id,
    }
    if primary_sector_id:
        primary_ring = by_id[primary_sector_id]["geometry"]["coordinates"][0]
        geometry_check["distance_to_nearest_sector_boundary_m"] = round(
            minimum_distance_to_polygon_boundary_m(
                REFERENCE_LON, REFERENCE_LAT, primary_ring, lon0, lat0
            ),
            3,
        )
    analytic_check = {
        "method": "HAVERSINE_DISTANCE_PLUS_INITIAL_BEARING_AND_FROZEN_RING_LIMITS",
        "distance_e0_reference_m": round(distance_e0, 3),
        "bearing_e0_reference_deg": round(bearing_e0, 6),
        "sector_id": analytic_id,
    }
    checks_agree = primary_sector_id == analytic_id and len(matched_ids) == 1

    modes = []
    distance_rows = []
    for mode, rows_key, top_key, rank_field, score_field in (
        ("BASE", "base_results", "top3_base", "rank_base_within_buffer", "score_base"),
        ("PERFIL", "profile_results", "top3_profile", "profile_rank_within_buffer", "profile_final_score"),
    ):
        rows = result_doc[rows_key]
        top3 = result_doc[top_key]
        matched_rank_rows = [_rank_row(rows, sid) for sid in matched_ids]
        ranks = [int(row[rank_field]) for row in matched_rank_rows]
        conservative_rank = max(ranks) if ranks else None
        best_rank = min(ranks) if ranks else None
        coverage_top1 = any(rank <= 1 for rank in ranks)
        coverage_top3 = any(rank <= 3 for rank in ranks)
        true_score = float(_rank_row(rows, primary_sector_id)[score_field]) if primary_sector_id else None
        top3_area_m2 = sum(float(by_id[str(row["sector_id"])]["properties"]["sector_area_m2"]) for row in top3)
        total_area_m2 = sum(float(f["properties"]["sector_area_m2"]) for f in features)
        modes.append(
            {
                "ranking_mode": mode,
                "reference_sector_ids": matched_ids,
                "primary_reference_sector_id": primary_sector_id,
                "reference_rank_best": best_rank,
                "reference_rank_conservative": conservative_rank,
                "reference_score": round(true_score, 9) if true_score is not None else None,
                "top1_covered": coverage_top1,
                "top3_covered": coverage_top3,
                "top3_area_m2": round(top3_area_m2, 3),
                "top3_area_km2": round(top3_area_m2 / 1_000_000.0, 6),
                "total_sectorized_area_m2": round(total_area_m2, 3),
                "top3_area_fraction": round(top3_area_m2 / total_area_m2, 9),
                "outcome": "COBERTO_TOP3" if coverage_top3 else "NAO_COBERTO_TOP3",
            }
        )
        for top in top3:
            sid = str(top["sector_id"])
            feature = by_id[sid]
            distance_rows.append(
                {
                    "ranking_mode": mode,
                    "area_label": top["area_label"],
                    "sector_id": sid,
                    "analytical_rank": int(top["analytical_rank"]),
                    "representative_lat": float(top["representative_lat"]),
                    "representative_lon": float(top["representative_lon"]),
                    "reference_to_representative_m": round(
                        haversine_m(
                            REFERENCE_LAT,
                            REFERENCE_LON,
                            float(top["representative_lat"]),
                            float(top["representative_lon"]),
                        ),
                        3,
                    ),
                    "reference_to_sector_polygon_m": round(
                        minimum_distance_to_polygon_m(
                            REFERENCE_LON,
                            REFERENCE_LAT,
                            feature["geometry"]["coordinates"][0],
                            lon0,
                            lat0,
                        ),
                        3,
                    ),
                    "contains_reference": sid in matched_ids,
                }
            )

    base_mode = modes[0]
    profile_mode = modes[1]
    primary_profile_row = _rank_row(result_doc["profile_results"], primary_sector_id) if primary_sector_id else None
    true_sector_diagnostics = None
    if primary_profile_row:
        true_sector_diagnostics = {
            "sector_id": primary_sector_id,
            "geo02_road_trail_access_score": float(primary_profile_row["geo02_score"]),
            "geo03_hydro_access_score": float(primary_profile_row["geo03_score"]),
            "geo04_terrain_access_score": float(primary_profile_row["geo04_score"]),
            "geo05_landcover_access_score": float(primary_profile_row["geo05_score"]),
            "barrier_flags": str(primary_profile_row["barrier_flags"]),
            "profile_awater": float(primary_profile_row["profile_awater"]),
            "interpretation": (
                "A boa acessibilidade viária coexistiu com forte penalização hidrográfica; "
                "o perfil comportamental não compensou essa combinação no ranking congelado."
            ),
        }
    result = {
        "protocol_id": "URBE-POSTOPEN-EVAL-v1.0",
        "scenario_id": "URBE-01",
        "phase": "T3_T4_POS_ABERTURA",
        "opened_at_local": opened_at_local,
        "timezone": "America/Belem",
        "reference": {
            "latitude_text_as_received": REFERENCE_LAT_TEXT,
            "longitude_text_as_received": REFERENCE_LON_TEXT,
            "latitude": REFERENCE_LAT,
            "longitude": REFERENCE_LON,
            "source": "DECLARADA_PELO_USUARIO_APOS_CONGELAMENTO_DAS_SAIDAS",
            "independent_gnss_or_exif_verification": False,
            "horizontal_precision_m": None,
            "horizontal_precision_status": "NAO_INFORMADA",
            "verification_status": "DECLARADA_NAO_VERIFICADA_INDEPENDENTEMENTE",
            "coordinate_sha256": _canonical_hash(
                {
                    "scenario_id": "URBE-01",
                    "latitude": REFERENCE_LAT_TEXT,
                    "longitude": REFERENCE_LON_TEXT,
                }
            ),
        },
        "frozen_inputs": {
            "package_path": str(FROZEN.relative_to(ROOT)),
            "frozen_manifest_sha256": _sha256(FROZEN_MANIFEST),
            "scientific_projection_sha256": manifest_doc.get("scientific_projection_sha256"),
            "ground_truth_used_in_frozen_processing": manifest_doc.get("ground_truth_used"),
            "rankings_recomputed": False,
            "weights_recomputed": False,
            "sectors_recomputed": False,
        },
        "initial_point": {
            "latitude": lat0,
            "longitude": lon0,
            "source_radius_m": radius_m,
            "reference_inside_source_radius": distance_e0 <= radius_m + 0.05,
            "distance_to_reference_m": round(distance_e0, 3),
            "bearing_to_reference_deg": round(bearing_e0, 6),
        },
        "sector_identification": {
            "geometry_check": geometry_check,
            "analytic_check": analytic_check,
            "checks_agree": checks_agree,
            "boundary_case": any(item["relation"] == "BOUNDARY" for item in relations),
            "boundary_rule": "Todos os setores tocados contam para cobertura; o rank principal usa o pior posto (critério conservador).",
            "precision_sensitivity_status": "NAO_AVALIAVEL_SEM_PRECISAO_HORIZONTAL_DA_REFERENCIA",
            "precision_sensitivity_note": (
                "A pertença vale para a coordenada declarada. Sem precisão horizontal, não se pode excluir "
                "mudança de setor caso o erro real exceda a distância registrada até a borda mais próxima."
            ),
        },
        "ranking_evaluation": modes,
        "true_sector_diagnostics_from_frozen_outputs": true_sector_diagnostics,
        "profile_incremental_comparison": {
            "base_reference_rank": base_mode["reference_rank_conservative"],
            "profile_reference_rank": profile_mode["reference_rank_conservative"],
            "rank_change_profile_minus_base": (
                profile_mode["reference_rank_conservative"] - base_mode["reference_rank_conservative"]
                if base_mode["reference_rank_conservative"] is not None
                and profile_mode["reference_rank_conservative"] is not None
                else None
            ),
            "interpretation": "O ranking PERFIL não melhorou a posição da referência neste caso.",
        },
        "distances_to_top3": distance_rows,
        "case_conclusion": {
            "top1_any_mode": any(item["top1_covered"] for item in modes),
            "top3_any_mode": any(item["top3_covered"] for item in modes),
            "classification": "NAO_COBERTO_NO_TOP3_BASE_NEM_PERFIL",
            "scope": "RESULTADO_DE_UM_CASO_UNICO_DIAGNOSTICO",
            "general_efficiency_claim_allowed": False,
        },
    }
    if not checks_agree:
        raise RuntimeError("Os métodos independentes de identificação do setor não concordaram")
    return result


def build_geojson(result: Mapping[str, Any]) -> dict[str, Any]:
    sectors_doc = _load_json(FROZEN_SECTORS)
    by_id = _features_by_id(sectors_doc)
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "id": "URBE-01::E0",
            "properties": {"role": "PONTO_INICIAL_RECEBIDO", "label": "E0"},
            "geometry": {
                "type": "Point",
                "coordinates": [result["initial_point"]["longitude"], result["initial_point"]["latitude"]],
            },
        },
        {
            "type": "Feature",
            "id": "URBE-01::REFERENCIA_REVELADA",
            "properties": {
                "role": "REFERENCIA_REVELADA_POS_CONGELAMENTO",
                "verification_status": result["reference"]["verification_status"],
            },
            "geometry": {
                "type": "Point",
                "coordinates": [result["reference"]["longitude"], result["reference"]["latitude"]],
            },
        },
    ]
    true_ids = set(item["sector_id"] for item in result["sector_identification"]["geometry_check"]["matched_sectors"])
    top_by_mode = {
        "BASE": set(row["sector_id"] for row in _load_json(FROZEN / "top3_base_original.json")["areas"]),
        "PERFIL": set(row["sector_id"] for row in _load_json(FROZEN / "top3_perfil_urbe01.json")["areas"]),
    }
    all_ids = true_ids | top_by_mode["BASE"] | top_by_mode["PERFIL"]
    for sid in sorted(all_ids):
        source = by_id[sid]
        roles = []
        if sid in true_ids:
            roles.append("SETOR_DA_REFERENCIA")
        if sid in top_by_mode["BASE"]:
            roles.append("TOP3_BASE")
        if sid in top_by_mode["PERFIL"]:
            roles.append("TOP3_PERFIL")
        features.append(
            {
                "type": "Feature",
                "id": sid,
                "properties": {"sector_id": sid, "roles": roles},
                "geometry": source["geometry"],
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "URBE01_AVALIACAO_POS_ABERTURA_v1",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": features,
    }


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size=size)


def build_map(output_dir: Path, result: Mapping[str, Any]) -> None:
    image = Image.open(FROZEN_MAP).convert("RGBA")
    draw = ImageDraw.Draw(image)
    paper = "#fbfaf7"
    ink = "#263238"
    muted = "#5f6b70"
    truth = "#7b1fa2"

    # Substitui título e nota do mapa cego para impedir interpretação incorreta.
    draw.rectangle((0, 0, image.width, 285), fill=paper)
    draw.text((130, 62), "URBE-01: avaliação após a abertura da posição de referência", font=_font(63, True), fill=ink)
    draw.text(
        (132, 150),
        "A referência caiu em R02-S: 18º no BASE e 19º no PERFIL; fora do Top-3 em ambos.",
        font=_font(35),
        fill=muted,
    )
    draw.rounded_rectangle((3190, 55, 3865, 205), 22, fill="#f5dede", outline="#9d3737", width=3)
    draw.text((3340, 75), "RESULTADO", font=_font(25, True), fill="#7b1f1f")
    draw.text((3280, 124), "NÃO TOP-3", font=_font(39, True), fill="#7b1f1f")

    sectors_doc = _load_json(FROZEN_SECTORS)
    by_id = _features_by_id(sectors_doc)
    true_id = result["sector_identification"]["geometry_check"]["primary_sector_conservative"]
    true_ring = by_id[true_id]["geometry"]["coordinates"][0]
    lon0 = result["initial_point"]["longitude"]
    lat0 = result["initial_point"]["latitude"]
    extent_m = 2850.0
    map_size = 1500
    map_top = 485
    scale = map_size / (2 * extent_m)
    panel_lefts = [130, 2050]

    def panel_px(panel_x: int, lon: float, lat: float) -> tuple[int, int]:
        map_left = panel_x + (1820 - map_size) // 2
        xm, ym = lonlat_to_local_m(lon, lat, lon0, lat0)
        return int(map_left + map_size / 2 + xm * scale), int(map_top + map_size / 2 - ym * scale)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for panel_x, rank in zip(panel_lefts, (18, 19)):
        polygon = [panel_px(panel_x, float(lon), float(lat)) for lon, lat in true_ring]
        od.polygon(polygon, fill=(123, 31, 162, 45), outline=(123, 31, 162, 255), width=10)
        tx, ty = panel_px(panel_x, result["reference"]["longitude"], result["reference"]["latitude"])
        od.ellipse((tx - 25, ty - 25, tx + 25, ty + 25), fill=(255, 255, 255, 255), outline=(123, 31, 162, 255), width=8)
        od.line((tx - 34, ty, tx + 34, ty), fill=(123, 31, 162, 255), width=7)
        od.line((tx, ty - 34, tx, ty + 34), fill=(123, 31, 162, 255), width=7)
        label = f"Referência  R02-S  ({rank}º)"
        box = od.textbbox((0, 0), label, font=_font(27, True))
        lx, ly = tx + 42, ty - 26
        od.rounded_rectangle((lx - 10, ly - 6, lx + box[2] + 10, ly + box[3] + 8), 8, fill=(255, 255, 255, 235), outline=(123, 31, 162, 255), width=3)
        od.text((lx, ly), label, font=_font(27, True), fill=truth)
    image.alpha_composite(overlay)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 2290, image.width, image.height), fill=paper)
    draw.line((130, 2310, 3870, 2310), fill="#cbc6bc", width=3)
    note = (
        "Nota. Mapa produzido após a abertura da referência declarada pelo usuário. O fundo e os rankings provêm do pacote "
        "cego previamente congelado; nenhum escore, peso ou setor foi recalculado. O contorno roxo indica o setor R02-S, "
        "que contém a referência. A referência não ficou no Top-3 BASE nem no Top-3 PERFIL. Resultado de caso único, sem "
        "alegação de eficácia geral. Fontes territoriais: OpenStreetMap, SRTMGL1/Mapzen e ESA WorldCover 2021 v200."
    )
    # Quebra simples de linha.
    words = note.split()
    line = ""
    lines = []
    for word in words:
        candidate = word if not line else f"{line} {word}"
        if draw.textbbox((0, 0), candidate, font=_font(24))[2] <= 3700:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    y = 2340
    for line in lines:
        draw.text((145, y), line, font=_font(24), fill=muted)
        y += 36

    png = output_dir / "Mapa_URBE01_Avaliacao_Pos_Abertura_v1.png"
    pdf = output_dir / "Mapa_URBE01_Avaliacao_Pos_Abertura_v1.pdf"
    image.convert("RGB").save(png, "PNG", dpi=(300, 300), optimize=True)
    page_w, page_h = landscape(A3)
    pdf_canvas = canvas.Canvas(str(pdf), pagesize=(page_w, page_h), invariant=1)
    margin = 18
    draw_w = page_w - 2 * margin
    draw_h = draw_w / (image.width / image.height)
    if draw_h > page_h - 2 * margin:
        draw_h = page_h - 2 * margin
        draw_w = draw_h * (image.width / image.height)
    pdf_canvas.drawImage(
        ImageReader(image.convert("RGB")),
        (page_w - draw_w) / 2,
        (page_h - draw_h) / 2,
        draw_w,
        draw_h,
    )
    pdf_canvas.showPage()
    pdf_canvas.save()


def build_report(result: Mapping[str, Any]) -> str:
    modes = {item["ranking_mode"]: item for item in result["ranking_evaluation"]}
    distances = result["distances_to_top3"]
    profile_dist = [row for row in distances if row["ranking_mode"] == "PERFIL"]
    nearest = min(profile_dist, key=lambda row: row["reference_to_sector_polygon_m"])
    diagnostic = result["true_sector_diagnostics_from_frozen_outputs"]
    return f"""# Avaliação pós-abertura — URBE-01

## Controle temporal e metodológico

- referência registrada em: `{result['opened_at_local']}` (`America/Belem`);
- origem: coordenada declarada pelo usuário após o congelamento;
- verificação GNSS/EXIF independente: não disponível;
- precisão horizontal da referência: não informada;
- rankings, pesos e setores recalculados: não;
- métodos independentes de identificação do setor: concordantes.

## Posição da referência

- latitude: `{result['reference']['latitude_text_as_received']}`;
- longitude: `{result['reference']['longitude_text_as_received']}`;
- distância ao ponto inicial E0: **{result['initial_point']['distance_to_reference_m']:.3f} m**;
- azimute a partir de E0: **{result['initial_point']['bearing_to_reference_deg']:.3f}°**;
- setor: **{result['sector_identification']['geometry_check']['primary_sector_conservative']}**.
- distância à borda setorial mais próxima: **{result['sector_identification']['geometry_check']['distance_to_nearest_sector_boundary_m']:.1f} m**.

A pertença a R02-S é válida para a coordenada declarada. Como a precisão horizontal não foi informada, não é possível excluir mudança de setor caso o erro real da referência exceda 75,4 m.

## Resultado contra os rankings congelados

| Ranking | Posto do setor verdadeiro | Top-1 | Top-3 | Resultado |
|---|---:|---|---|---|
| BASE | {modes['BASE']['reference_rank_conservative']}º | não | não | não coberto |
| PERFIL | {modes['PERFIL']['reference_rank_conservative']}º | não | não | não coberto |

O ranking PERFIL deslocou o setor verdadeiro do 18º para o 19º posto. Portanto, neste caso, a inclusão do perfil tal como congelada não produziu ganho de ranking.

No setor real, os escores territoriais congelados foram: vias/trilhas **{diagnostic['geo02_road_trail_access_score']:.3f}**, hidrografia **{diagnostic['geo03_hydro_access_score']:.3f}**, terreno **{diagnostic['geo04_terrain_access_score']:.3f}** e cobertura do solo **{diagnostic['geo05_landcover_access_score']:.3f}**. O setor recebeu o alerta `{diagnostic['barrier_flags']}` e contribuição comportamental ligada à água `Awater = {diagnostic['profile_awater']:.3f}`. Assim, a boa acessibilidade viária coexistiu com forte penalização hidrográfica, e o perfil congelado não compensou essa combinação.

As três áreas do Top-3 abrangem aproximadamente **{modes['PERFIL']['top3_area_km2']:.3f} km²**, equivalentes a **{100*modes['PERFIL']['top3_area_fraction']:.1f}%** da área setorizada, mas não contiveram a referência. O setor priorizado mais próximo foi `{nearest['sector_id']}`, a aproximadamente **{nearest['reference_to_sector_polygon_m']:.1f} m** da referência; proximidade não é contabilizada como acerto Top-3.

## Interpretação

O resultado é negativo para Top-1 e Top-3 nos dois rankings. Ele deve ser preservado integralmente, pois informa que as regras territoriais e o componente comportamental atuais não distinguiram adequadamente o setor real neste cenário urbano. Um caso não permite estimar eficácia geral, mas fornece evidência útil para revisar prospectivamente o módulo comportamental em versões futuras, sem modificar esta rodada.
"""


def build_scientific_outputs(output_dir: Path, opened_at_local: str) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    result = build_evaluation(opened_at_local)
    event = {
        "protocol_id": "URBE-POSTOPEN-EVAL-v1.0",
        "scenario_id": "URBE-01",
        "event": "ABERTURA_DA_REFERENCIA",
        "opened_at_local": opened_at_local,
        "timezone": "America/Belem",
        "coordinate": {
            "latitude_text_as_received": REFERENCE_LAT_TEXT,
            "longitude_text_as_received": REFERENCE_LON_TEXT,
            "sha256": result["reference"]["coordinate_sha256"],
        },
        "source": "DECLARADA_PELO_USUARIO_APOS_CONGELAMENTO",
        "verification_status": "DECLARADA_NAO_VERIFICADA_INDEPENDENTEMENTE",
        "frozen_manifest_sha256": result["frozen_inputs"]["frozen_manifest_sha256"],
    }
    _write_json(output_dir / "registro_abertura_referencia.json", event)
    _write_json(output_dir / "resultado_avaliacao_pos_abertura.json", result)
    _write_csv(output_dir / "avaliacao_rankings.csv", result["ranking_evaluation"])
    _write_csv(output_dir / "distancias_top3.csv", result["distances_to_top3"])
    _write_json(output_dir / "referencia_setores_e_top3.geojson", build_geojson(result))
    verification = {
        "protocol_id": "URBE-POSTOPEN-EVAL-v1.0",
        "geometry_method": result["sector_identification"]["geometry_check"],
        "analytic_method": result["sector_identification"]["analytic_check"],
        "methods_agree": result["sector_identification"]["checks_agree"],
        "reference_inside_source_radius": result["initial_point"]["reference_inside_source_radius"],
        "frozen_outputs_modified": False,
    }
    _write_json(output_dir / "verificacao_independente.json", verification)
    (output_dir / "relatorio_avaliacao_pos_abertura.md").write_text(build_report(result), encoding="utf-8")
    build_map(output_dir, result)
    return result


def _compare_dirs(first: Path, second: Path) -> dict[str, Any]:
    rows = []
    for name in SCIENTIFIC_FILES:
        h1 = _sha256(first / name)
        h2 = _sha256(second / name)
        rows.append({"file": name, "run1_sha256": h1, "run2_sha256": h2, "equal": h1 == h2})
    return {
        "status": "PASS" if all(row["equal"] for row in rows) else "FAIL",
        "file_count": len(rows),
        "all_equal": all(row["equal"] for row in rows),
        "files": rows,
    }


def _existing_or_new_opened_at(output_dir: Path) -> str:
    existing = output_dir / "registro_abertura_referencia.json"
    if existing.exists():
        event = _load_json(existing)
        coordinate = event.get("coordinate", {})
        if coordinate.get("latitude_text_as_received") != REFERENCE_LAT_TEXT or coordinate.get("longitude_text_as_received") != REFERENCE_LON_TEXT:
            raise RuntimeError("A referência existente difere; crie nova versão em vez de sobrescrever")
        return str(event["opened_at_local"])
    return datetime.now(LOCAL_TZ).isoformat(timespec="seconds")


def run_and_publish(output_dir: Path) -> dict[str, Any]:
    for required in (FROZEN_RESULT, FROZEN_SECTORS, FROZEN_MANIFEST, FROZEN_MAP):
        if not required.exists():
            raise FileNotFoundError(required)
    output_dir.mkdir(parents=True, exist_ok=True)
    opened_at = _existing_or_new_opened_at(output_dir)
    frozen_before = frozen_tree_snapshot(FROZEN)
    owned = set(SCIENTIFIC_FILES) | {"relatorio_determinismo.json", "manifesto_avaliacao_pos_abertura.json"}
    for name in owned:
        path = output_dir / name
        if path.exists():
            path.unlink()
    build_scientific_outputs(output_dir, opened_at)
    with tempfile.TemporaryDirectory(prefix="urbe01_postopen_repeat_") as temp:
        temp_dir = Path(temp)
        build_scientific_outputs(temp_dir, opened_at)
        determinism = _compare_dirs(output_dir, temp_dir)
    if determinism["status"] != "PASS":
        raise RuntimeError("A avaliação pós-abertura não foi determinística")
    _write_json(output_dir / "relatorio_determinismo.json", determinism)
    frozen_after = frozen_tree_snapshot(FROZEN)
    if frozen_before["tree_sha256"] != frozen_after["tree_sha256"]:
        raise RuntimeError("O pacote congelado foi modificado durante a avaliação")
    output_files = []
    for path in sorted(output_dir.iterdir()):
        if path.is_file() and path.name != "manifesto_avaliacao_pos_abertura.json":
            output_files.append(
                {"path": path.name, "bytes": path.stat().st_size, "sha256": _sha256(path), "role": "output"}
            )
    manifest = {
        "protocol_id": "URBE-POSTOPEN-EVAL-v1.0",
        "scenario_id": "URBE-01",
        "opened_at_local": opened_at,
        "timezone": "America/Belem",
        "reference_coordinate_sha256": _load_json(output_dir / "registro_abertura_referencia.json")["coordinate"]["sha256"],
        "frozen_package_before": frozen_before,
        "frozen_package_after_tree_sha256": frozen_after["tree_sha256"],
        "frozen_package_unchanged": True,
        "rankings_recomputed": False,
        "weights_recomputed": False,
        "sectors_recomputed": False,
        "determinism": determinism,
        "output_files": output_files,
    }
    _write_json(output_dir / "manifesto_avaliacao_pos_abertura.json", manifest)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    manifest = run_and_publish(Path(args.output_dir).resolve())
    result = _load_json(Path(args.output_dir) / "resultado_avaliacao_pos_abertura.json")
    print(json.dumps({
        "status": "PASS",
        "output_dir": str(Path(args.output_dir).resolve()),
        "frozen_package_unchanged": manifest["frozen_package_unchanged"],
        "determinism": manifest["determinism"]["status"],
        "true_sector": result["sector_identification"]["geometry_check"]["primary_sector_conservative"],
        "base_rank": result["ranking_evaluation"][0]["reference_rank_conservative"],
        "profile_rank": result["ranking_evaluation"][1]["reference_rank_conservative"],
        "top3_any": result["case_conclusion"]["top3_any_mode"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
