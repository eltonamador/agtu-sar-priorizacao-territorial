#!/usr/bin/env python3
"""Motor auditável de setorização e priorização territorial (EXT-ESP-SET-v1.1).

O módulo opera exclusivamente sobre buffers já produzidos sem ground truth. Ele:
1. valida a cadeia de custódia do motor de buffers;
2. cria 24 setores por buffer (3 anéis de mesma área x 8 direções);
3. extrai quatro atributos GEO a partir de bases públicas locais;
4. calcula cinco especificações de sensibilidade e ranking intra-buffer;
5. grava saídas, alertas e manifesto SHA-256.

O escore representa favorabilidade/prioridade operacional territorial. Não é
probabilidade de presença da vítima e não substitui decisão humana.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import hashlib
import json
import math
import platform
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


EARTH_RADIUS_M = 6_371_008.8
MINIMUM_FORBIDDEN_GT_FRAGMENTS = {
    "ground_truth",
    "truth_lat",
    "truth_lon",
    "reference_lat",
    "reference_lon",
    "real_lat",
    "real_lon",
    "true_lat",
    "true_lon",
    "victim_lat",
    "victim_lon",
    "target_lat",
    "target_lon",
    "base_lat",
    "base_lon",
    "distance_to_truth",
    "distance_to_ground_truth",
    "distance_to_reference",
    "generator_distance",
    "inside_buffer",
    "sector_contains_truth",
    "reference_sector",
    "correct_sector",
    "relevant_candidate",
}


class ContractError(ValueError):
    """Falha de contrato, integridade ou firewall metodológico."""


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _walk(value: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield f"{path}.{key}", item
            yield from _walk(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}]")


def canonical_firewall_fragments(config: Mapping[str, Any] | None = None) -> set[str]:
    """Retorna o vocabulário mínimo unido aos fragmentos da configuração."""
    fragments = set(MINIMUM_FORBIDDEN_GT_FRAGMENTS)
    if config is not None:
        configured = config.get("ground_truth_firewall", {}).get("forbidden_columns_or_fragments", [])
        if not isinstance(configured, list) or not all(isinstance(item, str) and item.strip() for item in configured):
            raise ContractError("Lista de fragmentos do firewall é inválida")
        fragments.update(item.strip().lower() for item in configured)
    return fragments


def validate_firewall_config(config: Mapping[str, Any]) -> None:
    firewall = config.get("ground_truth_firewall")
    if not isinstance(firewall, Mapping) or firewall.get("enabled") is not True:
        raise ContractError("Firewall de ground truth deve estar habilitado")
    allowed = firewall.get("allowed_control_field")
    if not isinstance(allowed, Mapping) or allowed.get("field") != "ground_truth_used" or allowed.get("required_value") is not False:
        raise ContractError("Única exceção do firewall deve ser ground_truth_used=false")
    if firewall.get("match_mode") != "NORMALIZED_KEY_SUBSTRING":
        raise ContractError("Firewall v1.1 exige correspondência por substring normalizada")
    canonical_firewall_fragments(config)


def enforce_ground_truth_firewall(value: Any, config: Mapping[str, Any] | None = None) -> None:
    """Bloqueia recursivamente nomes de campos de referência protegida."""
    fragments = canonical_firewall_fragments(config)
    normalized_fragments = {
        "".join(character if character.isalnum() else "_" for character in fragment.lower()).strip("_")
        for fragment in fragments
    }
    for path, item in _walk(value):
        raw_key = path.rsplit(".", 1)[-1].lower()
        key = "".join(character if character.isalnum() else "_" for character in raw_key).strip("_")
        compact_key = key.replace("_", "")
        if key == "ground_truth_used" and item is not False:
            raise ContractError(f"ground_truth_used deve ser booleano false: {path}")
        if key != "ground_truth_used" and any(
            fragment in key or fragment.replace("_", "") in compact_key
            for fragment in normalized_fragments
        ):
            raise ContractError(f"Campo proibido pelo firewall: {path}")


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{name} deve ser numérico")
    result = float(value)
    if not math.isfinite(result):
        raise ContractError(f"{name} deve ser finito")
    return result


def _manifest_hash(manifest: Mapping[str, Any], path: Path, role: str = "output") -> str:
    matches = [
        item
        for item in manifest.get("files", [])
        if item.get("role") == role
        and (Path(str(item.get("path", ""))).name == path.name or str(item.get("path", "")).endswith(str(path)))
    ]
    if len(matches) != 1:
        raise ContractError(f"Manifesto não identifica univocamente {role}: {path.name}")
    return str(matches[0].get("sha256", ""))


def validate_buffer_contract(
    buffer_doc: Mapping[str, Any],
    buffer_geojson: Mapping[str, Any] | None = None,
    buffer_manifest: Mapping[str, Any] | None = None,
    buffer_json_path: Path | None = None,
    buffer_geojson_path: Path | None = None,
    config: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    enforce_ground_truth_firewall(buffer_doc, config)
    if buffer_geojson is not None:
        enforce_ground_truth_firewall(buffer_geojson, config)
    if buffer_manifest is not None:
        enforce_ground_truth_firewall(buffer_manifest, config)
    expected_protocol = (
        config.get("dependencies", {}).get("upstream_buffer_protocol")
        if config is not None
        else None
    )
    if expected_protocol and buffer_doc.get("protocol_id") != expected_protocol:
        raise ContractError("Protocolo do JSON de buffers diverge da dependência congelada")
    if buffer_doc.get("ground_truth_used") is not False:
        raise ContractError("Raiz do buffer deve declarar ground_truth_used=false")
    results = buffer_doc.get("results")
    if not isinstance(results, list) or not results:
        raise ContractError("results deve ser lista não vazia")
    if buffer_doc.get("record_count") != len(results):
        raise ContractError("record_count diverge de len(results)")

    required = {
        "scenario_id",
        "candidate_id",
        "estimated_lat",
        "estimated_lon",
        "adaptive_radius_m",
        "buffer_area_m2",
        "review_status",
        "execution_classification",
        "confirmatory_eligible",
        "ground_truth_used",
        "source_row_hash",
    }
    keys: set[tuple[str, str]] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(results):
        if not isinstance(raw, dict):
            raise ContractError(f"Registro {index} não é objeto")
        missing = sorted(required.difference(raw))
        if missing:
            raise ContractError(f"Registro {index} sem campos: {', '.join(missing)}")
        if raw["ground_truth_used"] is not False:
            raise ContractError(f"Registro {index} viola firewall")
        scenario_id = str(raw["scenario_id"]).strip()
        candidate_id = str(raw["candidate_id"]).strip()
        if not scenario_id or not candidate_id or "::" in scenario_id or "::" in candidate_id:
            raise ContractError("scenario_id/candidate_id vazios")
        if expected_protocol and raw.get("protocol_id") != expected_protocol:
            raise ContractError(f"Protocolo divergente no registro {index}")
        if not isinstance(raw.get("confirmatory_eligible"), bool):
            raise ContractError(f"confirmatory_eligible deve ser booleano: {index}")
        key = (scenario_id, candidate_id)
        if key in keys:
            raise ContractError(f"Chave duplicada: {key}")
        keys.add(key)
        lat = _finite_number(raw["estimated_lat"], "estimated_lat")
        lon = _finite_number(raw["estimated_lon"], "estimated_lon")
        radius = _finite_number(raw["adaptive_radius_m"], "adaptive_radius_m")
        area = _finite_number(raw["buffer_area_m2"], "buffer_area_m2")
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ContractError(f"Coordenada fora do domínio: {key}")
        if not 250 <= radius <= 7500:
            raise ContractError(f"Raio fora do protocolo: {key}")
        expected_area = math.pi * radius * radius
        if not math.isclose(area, expected_area, rel_tol=2e-6, abs_tol=1.0):
            raise ContractError(f"Área incompatível com raio: {key}")
        if raw.get("r0_semantics") == "diagnostic_legacy" and raw.get("confirmatory_eligible") is not False:
            raise ContractError(f"Legado diagnóstico marcado como confirmatório: {key}")
        source_hash = str(raw.get("source_row_hash", ""))
        if len(source_hash) != 64 or any(char not in "0123456789abcdefABCDEF" for char in source_hash):
            raise ContractError(f"source_row_hash inválido: {key}")
        normalized.append(dict(raw))

    if buffer_geojson is not None:
        if buffer_geojson.get("type") != "FeatureCollection":
            raise ContractError("GeoJSON deve ser FeatureCollection")
        features = buffer_geojson.get("features")
        if not isinstance(features, list) or len(features) != len(results):
            raise ContractError("Cardinalidade do GeoJSON diverge do JSON")
        geo_keys: set[tuple[str, str]] = set()
        geometry_by_key: dict[tuple[str, str], list[list[float]]] = {}
        for feature in features:
            props = feature.get("properties", {})
            key = (str(props.get("scenario_id", "")), str(props.get("candidate_id", "")))
            if key in geo_keys:
                raise ContractError(f"Feição duplicada: {key}")
            geo_keys.add(key)
            if feature.get("id") != f"{key[0]}::{key[1]}":
                raise ContractError(f"ID de feição divergente: {key}")
            if expected_protocol and props.get("protocol_id") not in (None, expected_protocol):
                raise ContractError(f"Protocolo divergente na feição: {key}")
            geometry = feature.get("geometry", {})
            coordinates = geometry.get("coordinates", [])
            if geometry.get("type") != "Polygon" or len(coordinates) != 1 or len(coordinates[0]) < 4:
                raise ContractError(f"Geometria inválida: {key}")
            if coordinates[0][0] != coordinates[0][-1]:
                raise ContractError(f"Anel não fechado: {key}")
            ring: list[list[float]] = []
            for position, pair in enumerate(coordinates[0]):
                if not isinstance(pair, list) or len(pair) < 2:
                    raise ContractError(f"Coordenada inválida em {key}, posição {position}")
                lon = _finite_number(pair[0], "buffer_geometry_lon")
                lat = _finite_number(pair[1], "buffer_geometry_lat")
                if not -180 <= lon <= 180 or not -90 <= lat <= 90:
                    raise ContractError(f"Coordenada fora do domínio em {key}")
                ring.append([lon, lat])
            minimum_unique = int(
                config.get("geometry", {}).get("minimum_unique_vertices", 4)
                if config is not None
                else 4
            )
            if len({(pair[0], pair[1]) for pair in ring[:-1]}) < minimum_unique:
                raise ContractError(f"Vértices únicos insuficientes: {key}")
            geometry_by_key[key] = ring
        if geo_keys != keys:
            raise ContractError("Conjunto de candidatos difere entre JSON e GeoJSON")
        for row in normalized:
            key = (str(row["scenario_id"]), str(row["candidate_id"]))
            ring = geometry_by_key[key]
            parent_xy = [
                aeqd_forward(float(lat), float(lon), float(row["estimated_lat"]), float(row["estimated_lon"]))
                for lon, lat in ring[:-1]
            ]
            if len(parent_xy) < 3 or abs(_signed_area_xy(parent_xy)) <= 1e-6:
                raise ContractError(f"Área autoritativa inválida: {key}")
            if not _point_in_polygon_or_boundary((0.0, 0.0), parent_xy):
                raise ContractError(f"Centro do candidato fora do buffer autoritativo: {key}")
            if not _is_convex_polygon(parent_xy):
                raise ContractError(f"Buffer autoritativo não convexo/estrelar suportado: {key}")
            row["_authoritative_buffer_ring"] = ring
            row["_authoritative_buffer_geometry_sha256"] = canonical_hash(ring)
            row["_authoritative_buffer_area_m2"] = abs(_signed_area_xy(parent_xy))

    if buffer_manifest is not None:
        if expected_protocol and buffer_manifest.get("protocol_id") != expected_protocol:
            raise ContractError("Protocolo do manifesto de buffers diverge da dependência congelada")
        if buffer_manifest.get("ground_truth_used") is not False:
            raise ContractError("Manifesto de buffer viola firewall")
        if buffer_manifest.get("record_count") != len(results):
            raise ContractError("Manifesto de buffer tem cardinalidade divergente")
        if buffer_json_path is not None:
            expected = _manifest_hash(buffer_manifest, buffer_json_path)
            if sha256_file(buffer_json_path) != expected:
                raise ContractError("SHA-256 do JSON de buffers diverge do manifesto")
        if buffer_geojson_path is not None:
            expected = _manifest_hash(buffer_manifest, buffer_geojson_path)
            if sha256_file(buffer_geojson_path) != expected:
                raise ContractError("SHA-256 do GeoJSON de buffers diverge do manifesto")
    return sorted(normalized, key=lambda row: (str(row["scenario_id"]), str(row["candidate_id"])))


def destination(lat_deg: float, lon_deg: float, distance_m: float, bearing_deg: float) -> tuple[float, float]:
    lat1 = math.radians(lat_deg)
    lon1 = math.radians(lon_deg)
    theta = math.radians(bearing_deg)
    delta = distance_m / EARTH_RADIUS_M
    lat2 = math.asin(
        math.sin(lat1) * math.cos(delta)
        + math.cos(lat1) * math.sin(delta) * math.cos(theta)
    )
    lon2 = lon1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(lat1),
        math.cos(delta) - math.sin(lat1) * math.sin(lat2),
    )
    lon2 = (lon2 + math.pi) % (2 * math.pi) - math.pi
    return round(math.degrees(lat2), 9), round(math.degrees(lon2), 9)


def local_xy(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    return (
        (lon - lon0) * 111_320.0 * math.cos(math.radians(lat0)),
        (lat - lat0) * 110_574.0,
    )


def aeqd_forward(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    """Projeção azimutal equidistante esférica local; retorna leste/norte em metros."""
    phi = math.radians(lat)
    lam = math.radians(lon)
    phi0 = math.radians(lat0)
    lam0 = math.radians(lon0)
    delta = (lam - lam0 + math.pi) % (2.0 * math.pi) - math.pi
    cos_c = max(-1.0, min(1.0, math.sin(phi0) * math.sin(phi) + math.cos(phi0) * math.cos(phi) * math.cos(delta)))
    c = math.acos(cos_c)
    k = 1.0 if c <= 1e-15 else c / math.sin(c)
    x = EARTH_RADIUS_M * k * math.cos(phi) * math.sin(delta)
    y = EARTH_RADIUS_M * k * (
        math.cos(phi0) * math.sin(phi) - math.sin(phi0) * math.cos(phi) * math.cos(delta)
    )
    return x, y


def aeqd_inverse(x: float, y: float, lat0: float, lon0: float) -> tuple[float, float]:
    """Inversa da AEQD esférica local; retorna latitude/longitude em graus."""
    phi0 = math.radians(lat0)
    lam0 = math.radians(lon0)
    rho = math.hypot(x, y)
    if rho <= 1e-12:
        return lat0, lon0
    c = rho / EARTH_RADIUS_M
    sin_c, cos_c = math.sin(c), math.cos(c)
    phi = math.asin(cos_c * math.sin(phi0) + (y * sin_c * math.cos(phi0) / rho))
    lam = lam0 + math.atan2(
        x * sin_c,
        rho * math.cos(phi0) * cos_c - y * math.sin(phi0) * sin_c,
    )
    lon = (math.degrees(lam) + 180.0) % 360.0 - 180.0
    return math.degrees(phi), lon


def _signed_area_xy(points: Sequence[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    closed = list(points) + [points[0]]
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(closed, closed[1:])) / 2.0


def _point_on_segment(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float], tolerance: float = 1e-6) -> bool:
    px, py = point
    ax, ay = a
    bx, by = b
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > tolerance * max(1.0, math.hypot(bx - ax, by - ay)):
        return False
    return min(ax, bx) - tolerance <= px <= max(ax, bx) + tolerance and min(ay, by) - tolerance <= py <= max(ay, by) + tolerance


def _point_in_polygon_or_boundary(point: tuple[float, float], polygon: Sequence[tuple[float, float]]) -> bool:
    if len(polygon) < 3:
        return False
    for a, b in zip(polygon, list(polygon[1:]) + [polygon[0]]):
        if _point_on_segment(point, a, b):
            return True
    px, py = point
    inside = False
    for (ax, ay), (bx, by) in zip(polygon, list(polygon[1:]) + [polygon[0]]):
        if (ay > py) != (by > py):
            x_at_y = ax + (py - ay) * (bx - ax) / (by - ay)
            if px < x_at_y:
                inside = not inside
    return inside


def _is_convex_polygon(polygon: Sequence[tuple[float, float]]) -> bool:
    signs: list[bool] = []
    n = len(polygon)
    for i in range(n):
        ax, ay = polygon[i]
        bx, by = polygon[(i + 1) % n]
        cx, cy = polygon[(i + 2) % n]
        cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        if abs(cross) > 1e-7:
            signs.append(cross > 0)
    return bool(signs) and all(value == signs[0] for value in signs)


def _shoelace_area(coords: Sequence[Sequence[float]], lat0: float, lon0: float) -> float:
    points = [aeqd_forward(float(lat), float(lon), lat0, lon0) for lon, lat in coords]
    if points and points[0] == points[-1]:
        points = points[:-1]
    return abs(_signed_area_xy(points))


def _bearing_xy(point: tuple[float, float]) -> float:
    return math.degrees(math.atan2(point[0], point[1])) % 360.0


def _ray_polygon_intersection(polygon: Sequence[tuple[float, float]], bearing_deg: float) -> tuple[float, float]:
    theta = math.radians(bearing_deg)
    dx, dy = math.sin(theta), math.cos(theta)
    best_t: float | None = None
    for (ax, ay), (bx, by) in zip(polygon, list(polygon[1:]) + [polygon[0]]):
        ex, ey = bx - ax, by - ay
        denominator = dx * ey - dy * ex
        if abs(denominator) <= 1e-12:
            continue
        t = (ax * ey - ay * ex) / denominator
        u = (ax * dy - ay * dx) / denominator
        if t >= -1e-8 and -1e-8 <= u <= 1.0 + 1e-8:
            if best_t is None or t < best_t:
                best_t = max(0.0, t)
    if best_t is None:
        raise ContractError(f"Raio sem interseção com o buffer no azimute {bearing_deg}")
    return best_t * dx, best_t * dy


def _boundary_arc(
    polygon: Sequence[tuple[float, float]], start_deg: float, end_deg: float
) -> list[tuple[float, float]]:
    width = end_deg - start_deg
    if not 0.0 < width <= 180.0:
        raise ContractError("Cunha angular inválida")
    start = _ray_polygon_intersection(polygon, start_deg)
    end = _ray_polygon_intersection(polygon, end_deg)
    intermediate: list[tuple[float, tuple[float, float]]] = []
    for vertex in polygon:
        offset = (_bearing_xy(vertex) - start_deg) % 360.0
        if 1e-9 < offset < width - 1e-9:
            intermediate.append((offset, vertex))
    return [start, *(point for _, point in sorted(intermediate, key=lambda item: item[0])), end]


def _scaled(points: Sequence[tuple[float, float]], factor: float) -> list[tuple[float, float]]:
    return [(factor * x, factor * y) for x, y in points]


def _dedupe_close(points: Sequence[tuple[float, float]], tolerance: float = 1e-8) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    for point in points:
        if not result or math.hypot(point[0] - result[-1][0], point[1] - result[-1][1]) > tolerance:
            result.append(point)
    if len(result) >= 2 and math.hypot(result[0][0] - result[-1][0], result[0][1] - result[-1][1]) <= tolerance:
        result.pop()
    return result


def _authoritative_sector_xy(
    parent_xy: Sequence[tuple[float, float]],
    inner_fraction: float,
    outer_fraction: float,
    start_deg: float,
    end_deg: float,
) -> list[tuple[float, float]]:
    parent_arc = _boundary_arc(parent_xy, start_deg, end_deg)
    outer_arc = _scaled(parent_arc, outer_fraction)
    if inner_fraction <= 1e-15:
        polygon = [*outer_arc, (0.0, 0.0)]
    else:
        inner_arc = _scaled(parent_arc, inner_fraction)
        polygon = [*outer_arc, *reversed(inner_arc)]
    polygon = _dedupe_close(polygon)
    if len(polygon) < 3 or abs(_signed_area_xy(polygon)) <= 1e-6:
        raise ContractError("Setor autoritativo degenerado")
    return polygon


def _xy_ring_to_geojson(points: Sequence[tuple[float, float]], lat0: float, lon0: float) -> list[list[float]]:
    coords: list[list[float]] = []
    for x, y in points:
        lat, lon = aeqd_inverse(x, y, lat0, lon0)
        coords.append([round(lon, 10), round(lat, 10)])
    coords.append(list(coords[0]))
    return coords


def _authoritative_sample_points(
    parent_xy: Sequence[tuple[float, float]],
    ring_index: int,
    ring_count: int,
    start_deg: float,
    end_deg: float,
    radial_samples: int,
    angular_samples: int,
    lat0: float,
    lon0: float,
) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    for radial_index in range(radial_samples):
        q_r = (radial_index + 0.5) / radial_samples
        scale = math.sqrt((ring_index + q_r) / ring_count)
        for angular_index in range(angular_samples):
            q_a = (angular_index + 0.5) / angular_samples
            boundary = _ray_polygon_intersection(parent_xy, start_deg + q_a * (end_deg - start_deg))
            lat, lon = aeqd_inverse(scale * boundary[0], scale * boundary[1], lat0, lon0)
            result.append((lat, lon))
    return result


def make_sector_records(buffer_rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]) -> list[dict[str, Any]]:
    geometry = config["geometry"]
    ring_count = int(geometry.get("ring_count", geometry.get("rings", 0)))
    direction_centers = geometry.get("direction_centers_deg")
    directions = list(direction_centers.keys()) if isinstance(direction_centers, dict) else list(geometry.get("direction_labels", []))
    if ring_count != 3 or len(directions) != 8:
        raise ContractError("SETOR-v1 exige 3 anéis e 8 direções")
    raster_sampling = config.get("feature_extraction", {}).get("raster_sampling", {})
    radial_samples = int(geometry.get("radial_samples", raster_sampling.get("radial_samples", 3)))
    angular_samples = int(geometry.get("angular_samples", raster_sampling.get("angular_samples", 3)))
    partition_tolerance = float(geometry.get("partition_area_conservation_relative_tolerance", 1e-6))
    output: list[dict[str, Any]] = []
    for source in sorted(buffer_rows, key=lambda r: (str(r["scenario_id"]), str(r["candidate_id"]))):
        lat = float(source["estimated_lat"])
        lon = float(source["estimated_lon"])
        radius = float(source["adaptive_radius_m"])
        radial_bounds = [radius * math.sqrt(i / ring_count) for i in range(ring_count + 1)]
        source_ring = source.get("_authoritative_buffer_ring")
        if not isinstance(source_ring, list):
            raise ContractError("Geometria autoritativa não foi incorporada ao contrato do buffer")
        parent_xy = [aeqd_forward(float(pair[1]), float(pair[0]), lat, lon) for pair in source_ring[:-1]]
        parent_area = abs(_signed_area_xy(parent_xy))
        expected_area = parent_area / (ring_count * len(directions))
        circular_theoretical_area = math.pi * radius * radius / (ring_count * len(directions))
        buffer_start = len(output)
        for ring_index in range(ring_count):
            inner_m = radial_bounds[ring_index]
            outer_m = radial_bounds[ring_index + 1]
            for direction_index, label in enumerate(directions):
                center = float(direction_centers[label]) if isinstance(direction_centers, dict) else direction_index * 360.0 / len(directions)
                half = 180.0 / len(directions)
                start = center - half
                end = center + half
                ring_id = f"R{ring_index + 1:02d}"
                sector_id = f"{source['scenario_id']}::{source['candidate_id']}::{ring_id}::{label}"
                inner_fraction = math.sqrt(ring_index / ring_count)
                outer_fraction = math.sqrt((ring_index + 1) / ring_count)
                sector_xy = _authoritative_sector_xy(
                    parent_xy, inner_fraction, outer_fraction, start, end
                )
                coords = _xy_ring_to_geojson(sector_xy, lat, lon)
                representative_scale = math.sqrt((ring_index + 0.5) / ring_count)
                boundary_at_center = _ray_polygon_intersection(parent_xy, center)
                rep_lat, rep_lon = aeqd_inverse(
                    representative_scale * boundary_at_center[0],
                    representative_scale * boundary_at_center[1],
                    lat,
                    lon,
                )
                samples = _authoritative_sample_points(
                    parent_xy,
                    ring_index,
                    ring_count,
                    start,
                    end,
                    radial_samples,
                    angular_samples,
                    lat,
                    lon,
                )
                planar_area = _shoelace_area(coords, lat, lon)
                output.append(
                    {
                        "protocol_id": config["protocol_id"],
                        "engine_version": config.get("engine_version", str(config.get("version", "1.0"))),
                        "scenario_id": source["scenario_id"],
                        "candidate_id": source["candidate_id"],
                        "sector_id": sector_id,
                        "ring_id": ring_id,
                        "ring_index": ring_index + 1,
                        "direction": label,
                        "direction_label": label,
                        "direction_index": direction_index + 1,
                        "sector_index": ring_index * len(directions) + direction_index + 1,
                        "azimuth_center_deg": round(center % 360.0, 6),
                        "azimuth_start_deg": round(start % 360.0, 6),
                        "azimuth_end_deg": round(end % 360.0, 6),
                        "inner_radius_m": round(inner_m, 6),
                        "outer_radius_m": round(outer_m, 6),
                        "sector_area_m2": round(planar_area, 6),
                        "polygon_planar_area_m2": round(planar_area, 6),
                        "expected_authoritative_sector_area_m2": round(expected_area, 6),
                        "theoretical_circular_sector_area_m2": round(circular_theoretical_area, 6),
                        "authoritative_buffer_planar_area_m2": round(parent_area, 6),
                        "area_relative_error": round(abs(planar_area - expected_area) / expected_area, 12),
                        "representative_lat": round(rep_lat, 10),
                        "representative_lon": round(rep_lon, 10),
                        "sample_points": [[p[0], p[1]] for p in samples],
                        "geometry_coordinates": coords,
                        "geometry": {"type": "Polygon", "coordinates": [coords]},
                        "_geometry_xy": sector_xy,
                        "geometry_source": "INPUT_BUFFER_GEOJSON",
                        "geometry_method": "LOCAL_AEQD_HOMOTHETIC_PARTITION",
                        "source_buffer_geometry_sha256": source["_authoritative_buffer_geometry_sha256"],
                        "source_buffer_review_status": source["review_status"],
                        "source_execution_classification": source["execution_classification"],
                        "source_confirmatory_eligible": bool(source["confirmatory_eligible"]),
                        "source_row_hash": source["source_row_hash"],
                        "ground_truth_used": False,
                    }
                )
        generated = output[buffer_start:]
        area_sum = sum(float(item["sector_area_m2"]) for item in generated)
        relative_difference = abs(area_sum - parent_area) / parent_area
        if relative_difference > partition_tolerance:
            raise ContractError(
                f"Partição não conserva a área autoritativa de {source['scenario_id']}::{source['candidate_id']}: "
                f"{relative_difference:.3e}"
            )
    return output


@dataclass(frozen=True)
class Segment:
    cls: str
    subtype: str
    name: str | None
    severity: float
    a_lat: float
    a_lon: float
    b_lat: float
    b_lon: float


class SpatialSegmentIndex:
    def __init__(self, segments: Sequence[Segment], cell_deg: float = 0.02):
        self.segments = list(segments)
        self.cell_deg = cell_deg
        self.cells: dict[tuple[int, int], list[int]] = defaultdict(list)
        for index, seg in enumerate(self.segments):
            x0 = math.floor(min(seg.a_lon, seg.b_lon) / cell_deg)
            x1 = math.floor(max(seg.a_lon, seg.b_lon) / cell_deg)
            y0 = math.floor(min(seg.a_lat, seg.b_lat) / cell_deg)
            y1 = math.floor(max(seg.a_lat, seg.b_lat) / cell_deg)
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    self.cells[(x, y)].append(index)

    def query_bbox(self, min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> list[Segment]:
        x0 = math.floor(min_lon / self.cell_deg)
        x1 = math.floor(max_lon / self.cell_deg)
        y0 = math.floor(min_lat / self.cell_deg)
        y1 = math.floor(max_lat / self.cell_deg)
        found: set[int] = set()
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                found.update(self.cells.get((x, y), ()))
        return [self.segments[i] for i in sorted(found)]


TRAIL_TYPES = {"path", "footway", "bridleway", "steps", "pedestrian", "cycleway", "track"}
IGNORED_HIGHWAYS = {"proposed", "construction", "raceway", "platform", "corridor", "bus_stop", "elevator", "rest_area"}


def load_road_segments(path: str | Path, config: Mapping[str, Any] | None = None) -> tuple[list[Segment], str | None]:
    doc = load_json(path)
    enforce_ground_truth_firewall(doc, config)
    segments: list[Segment] = []
    for way in doc.get("elements", []):
        tags = way.get("tags") or {}
        highway = tags.get("highway")
        geometry = way.get("geometry")
        if not highway or highway in IGNORED_HIGHWAYS or not isinstance(geometry, list):
            continue
        cls = "trail" if highway in TRAIL_TYPES else "road"
        name = tags.get("name") or tags.get("ref") or highway
        for a, b in zip(geometry, geometry[1:]):
            vals = [a.get("lat"), a.get("lon"), b.get("lat"), b.get("lon")]
            if all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals):
                segments.append(Segment(cls, str(highway), str(name) if name else None, 0.0, *map(float, vals)))
    return segments, (doc.get("osm3s") or {}).get("timestamp_osm_base")


def _hydro_class(tags: Mapping[str, Any]) -> tuple[str, float, str | None] | None:
    waterway = tags.get("waterway")
    name = tags.get("name") or tags.get("name:pt") or tags.get("ref")
    if waterway == "river":
        return "Rio", 1.0, name
    if waterway == "stream":
        return "Igarapé/córrego", 0.65, name
    if waterway in {"canal", "tidal_channel", "riverbank"}:
        label = "Canal de maré" if waterway == "tidal_channel" else "Área fluvial" if waterway == "riverbank" else "Canal"
        return label, 1.0, name
    if waterway in {"ditch", "drain"}:
        return "Vala/drenagem", 0.35, name
    if tags.get("natural") == "wetland":
        return "Área úmida", 1.0, name
    if tags.get("natural") == "water" or tags.get("landuse") in {"reservoir", "basin"}:
        water = tags.get("water")
        label = "Área fluvial" if water == "river" else "Lago" if water == "lake" else "Lagoa" if water == "lagoon" else "Corpo d'água"
        severity = 0.65 if (water in {"pond", "basin"} or tags.get("landuse") == "basin") else 1.0
        return label, severity, name
    return None


def load_hydro_segments(path: str | Path, config: Mapping[str, Any] | None = None) -> tuple[list[Segment], str | None]:
    doc = load_json(path)
    enforce_ground_truth_firewall(doc, config)
    segments: list[Segment] = []
    for element in doc.get("elements", []):
        classification = _hydro_class(element.get("tags") or {})
        if classification is None:
            continue
        category, severity, name = classification
        geometries = [element.get("geometry")] if element.get("type") == "way" else [m.get("geometry") for m in element.get("members", [])]
        for geometry in geometries:
            if not isinstance(geometry, list):
                continue
            for a, b in zip(geometry, geometry[1:]):
                vals = [a.get("lat"), a.get("lon"), b.get("lat"), b.get("lon")]
                if all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals):
                    segments.append(Segment("hydro", category, str(name) if name else None, float(severity), *map(float, vals)))
    return segments, (doc.get("osm3s") or {}).get("timestamp_osm_base")


def _point_segment_distance(seg: Segment, lat: float, lon: float) -> float:
    ax, ay = local_xy(seg.a_lat, seg.a_lon, lat, lon)
    bx, by = local_xy(seg.b_lat, seg.b_lon, lat, lon)
    dx, dy = bx - ax, by - ay
    norm = dx * dx + dy * dy
    t = 0.0 if norm == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / norm))
    return math.hypot(ax + t * dx, ay + t * dy)


def _clip_segment_circle(
    seg: Segment, lat0: float, lon0: float, radius_m: float
) -> tuple[float, float, float, float] | None:
    ax, ay = local_xy(seg.a_lat, seg.a_lon, lat0, lon0)
    bx, by = local_xy(seg.b_lat, seg.b_lon, lat0, lon0)
    dx, dy = bx - ax, by - ay
    a = dx * dx + dy * dy
    if a == 0:
        return None
    b = 2.0 * (ax * dx + ay * dy)
    c = ax * ax + ay * ay - radius_m * radius_m
    roots: list[float] = [0.0, 1.0]
    disc = b * b - 4.0 * a * c
    if disc >= 0:
        root = math.sqrt(disc)
        roots.extend([(-b - root) / (2.0 * a), (-b + root) / (2.0 * a)])
    roots = sorted(max(0.0, min(1.0, t)) for t in roots if -1e-12 <= t <= 1 + 1e-12)
    intervals = []
    for lo, hi in zip(roots, roots[1:]):
        mid = (lo + hi) / 2.0
        x, y = ax + mid * dx, ay + mid * dy
        if x * x + y * y <= radius_m * radius_m + 1e-6 and hi > lo:
            intervals.append((lo, hi))
    if not intervals:
        return None
    lo = min(pair[0] for pair in intervals)
    hi = max(pair[1] for pair in intervals)
    return ax + lo * dx, ay + lo * dy, ax + hi * dx, ay + hi * dy


def _sector_index_for_xy(x: float, y: float, radius_m: float, rotation_deg: float = 0.0) -> int | None:
    distance = math.hypot(x, y)
    if distance > radius_m + 1e-6:
        return None
    radial_bounds = [radius_m * math.sqrt(i / 3.0) for i in range(4)]
    ring = min(2, max(0, bisect.bisect_left(radial_bounds[1:], distance)))
    bearing = math.degrees(math.atan2(x, y)) % 360.0
    direction = int(math.floor(((bearing - rotation_deg + 22.5) % 360.0) / 45.0)) % 8
    return ring * 8 + direction


def _locate_sector_xy(
    point: tuple[float, float], sector_polygons_xy: Sequence[Sequence[tuple[float, float]]]
) -> int | None:
    """Localiza o ponto; em fronteira compartilhada vence o menor índice técnico."""
    for index, polygon in enumerate(sector_polygons_xy):
        if _point_in_polygon_or_boundary(point, polygon):
            return index
    return None


def _allocate_lengths(
    segments: Sequence[Segment],
    lat0: float,
    lon0: float,
    sector_polygons_xy: Sequence[Sequence[tuple[float, float]]],
    chunk_m: float,
    cls_filter: str | None = None,
) -> tuple[list[float], list[float]]:
    lengths = [0.0] * len(sector_polygons_xy)
    severity_lengths = [0.0] * len(sector_polygons_xy)
    for seg in segments:
        if cls_filter is not None and seg.cls != cls_filter:
            continue
        ax, ay = aeqd_forward(seg.a_lat, seg.a_lon, lat0, lon0)
        bx, by = aeqd_forward(seg.b_lat, seg.b_lon, lat0, lon0)
        length = math.hypot(bx - ax, by - ay)
        if length <= 1e-9:
            continue
        steps = max(1, int(math.ceil(length / chunk_m)))
        for i in range(steps):
            t0, t1 = i / steps, (i + 1) / steps
            mx = ax + ((t0 + t1) / 2.0) * (bx - ax)
            my = ay + ((t0 + t1) / 2.0) * (by - ay)
            index = _locate_sector_xy((mx, my), sector_polygons_xy)
            if index is not None:
                part = length / steps
                lengths[index] += part
                severity_lengths[index] += part * seg.severity
    return lengths, severity_lengths


class HGTSampler:
    def __init__(self, directory: str | Path):
        self.tiles: dict[str, bytes] = {}
        for path in sorted(Path(directory).glob("[NS][0-9][0-9][EW][0-9][0-9][0-9].hgt.gz")):
            with gzip.open(path, "rb") as handle:
                self.tiles[path.name[:7]] = handle.read()

    @staticmethod
    def key(lat: float, lon: float) -> str:
        lat_floor = math.floor(lat)
        lon_floor = math.floor(lon)
        return f"{'N' if lat_floor >= 0 else 'S'}{abs(lat_floor):02d}{'E' if lon_floor >= 0 else 'W'}{abs(lon_floor):03d}"

    def sample(self, lat: float, lon: float) -> float | None:
        data = self.tiles.get(self.key(lat, lon))
        if data is None:
            return None
        lat0, lon0 = math.floor(lat), math.floor(lon)
        rowf = (lat0 + 1 - lat) * 3600
        colf = (lon - lon0) * 3600
        row = max(0, min(3599, math.floor(rowf)))
        col = max(0, min(3599, math.floor(colf)))
        dr, dc = rowf - row, colf - col

        def z(r: int, c: int) -> int:
            offset = (r * 3601 + c) * 2
            return int.from_bytes(data[offset : offset + 2], "big", signed=True)

        vals = [z(row, col), z(row, col + 1), z(row + 1, col), z(row + 1, col + 1)]
        if -32768 in vals:
            return None
        return (
            vals[0] * (1 - dr) * (1 - dc)
            + vals[1] * (1 - dr) * dc
            + vals[2] * dr * (1 - dc)
            + vals[3] * dr * dc
        )

    def metrics(self, lat: float, lon: float) -> tuple[float, float, float, float] | None:
        spacing = 30.0
        d_lat = spacing / 110_574.0
        d_lon = spacing / (111_320.0 * math.cos(math.radians(lat)))
        samples: list[float] = []
        for y in (1, 0, -1):
            for x in (-1, 0, 1):
                value = self.sample(lat + y * d_lat, lon + x * d_lon)
                if value is None:
                    return None
                samples.append(value)
        nw, n, ne, w, center, e, sw, s, se = samples
        dzdx = (ne + 2 * e + se - nw - 2 * w - sw) / (8 * spacing)
        dzdy = (sw + 2 * s + se - nw - 2 * n - ne) / (8 * spacing)
        slope_deg = math.degrees(math.atan(math.sqrt(dzdx * dzdx + dzdy * dzdy)))
        relief = max(samples) - min(samples)
        score = 0.70 * math.exp(-slope_deg / 8.0) + 0.30 * math.exp(-relief / 30.0)
        return center, slope_deg, relief, score


WORLD_COVER_SCORES = {
    10: 0.35,
    20: 0.50,
    30: 0.80,
    40: 0.75,
    50: 0.85,
    60: 0.90,
    70: 0.30,
    80: 0.05,
    90: 0.20,
    95: 0.15,
    100: 0.45,
}


class WorldCoverSampler:
    def __init__(self, directory: str | Path):
        try:
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - ambiente sem dependência
            raise RuntimeError("Pillow é necessário para ler ESA WorldCover") from exc
        Image.MAX_IMAGE_PIXELS = None
        self.images: dict[str, Any] = {}
        for path in sorted(Path(directory).glob("ESA_WorldCover_10m_2021_v200_*_Map.tif")):
            tile = path.name.split("_v200_")[1].split("_Map")[0]
            self.images[tile] = Image.open(path)

    @staticmethod
    def tile(lat: float, lon: float) -> str:
        return f"{'N00' if lat >= 0 else 'S03'}{'W054' if lon < -51 else 'W051'}"

    def sample(self, lat: float, lon: float) -> int | None:
        tile = self.tile(lat, lon)
        image = self.images.get(tile)
        if image is None:
            return None
        lat0 = 0 if tile.startswith("N00") else -3
        lon0 = -54 if tile.endswith("W054") else -51
        x = math.floor((lon - lon0) / 3.0 * 36_000)
        y = math.floor((lat0 + 3.0 - lat) / 3.0 * 36_000)
        if not (0 <= x < 36_000 and 0 <= y < 36_000):
            return None
        code = int(image.getpixel((x, y)))
        return code if code in WORLD_COVER_SCORES else None

    def close(self) -> None:
        for image in self.images.values():
            image.close()


def _nearest(index: SpatialSegmentIndex, lat: float, lon: float, max_m: float, cls_filter: str | None = None) -> tuple[float, Segment | None]:
    dlat = max_m / 110_574.0
    dlon = max_m / (111_320.0 * max(0.01, math.cos(math.radians(lat))))
    candidates = index.query_bbox(lat - dlat, lon - dlon, lat + dlat, lon + dlon)
    best_distance, best = math.inf, None
    for seg in candidates:
        if cls_filter is not None and seg.cls != cls_filter:
            continue
        distance = _point_segment_distance(seg, lat, lon)
        if distance < best_distance:
            best_distance, best = distance, seg
    return best_distance, best


def extract_sector_features(
    sectors: Sequence[Mapping[str, Any]],
    buffer_rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    road_index: SpatialSegmentIndex,
    hydro_index: SpatialSegmentIndex,
    hgt: HGTSampler,
    world_cover: WorldCoverSampler,
    road_timestamp: str | None,
    hydro_timestamp: str | None,
) -> list[dict[str, Any]]:
    cfg = config["feature_extraction"]
    by_buffer: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for sector in sectors:
        by_buffer[(str(sector["scenario_id"]), str(sector["candidate_id"]))].append(sector)
    source_by_key = {(str(r["scenario_id"]), str(r["candidate_id"])): r for r in buffer_rows}
    output: list[dict[str, Any]] = []
    for key in sorted(by_buffer):
        source = source_by_key[key]
        lat0 = float(source["estimated_lat"])
        lon0 = float(source["estimated_lon"])
        radius = float(source["adaptive_radius_m"])
        dlat = radius / 110_574.0
        dlon = radius / (111_320.0 * max(0.01, math.cos(math.radians(lat0))))
        roads_nearby = road_index.query_bbox(lat0 - dlat, lon0 - dlon, lat0 + dlat, lon0 + dlon)
        hydros_nearby = hydro_index.query_bbox(lat0 - dlat, lon0 - dlon, lat0 + dlat, lon0 + dlon)
        sector_list = sorted(by_buffer[key], key=lambda s: (int(s["ring_index"]), int(s["direction_index"])))
        sector_polygons_xy = [sector["_geometry_xy"] for sector in sector_list]
        road_lengths, _ = _allocate_lengths(
            roads_nearby, lat0, lon0, sector_polygons_xy, float(cfg["line_chunk_m"]), "road"
        )
        trail_lengths, _ = _allocate_lengths(
            roads_nearby, lat0, lon0, sector_polygons_xy, float(cfg["line_chunk_m"]), "trail"
        )
        hydro_lengths, hydro_severity_lengths = _allocate_lengths(
            hydros_nearby, lat0, lon0, sector_polygons_xy, float(cfg["line_chunk_m"]), None
        )

        for local_index, sector in enumerate(sector_list):
            rep_lat = float(sector["representative_lat"])
            rep_lon = float(sector["representative_lon"])
            max_nearest = float(cfg["nearest_search_limit_m"])
            road_distance, nearest_road = _nearest(road_index, rep_lat, rep_lon, max_nearest, "road")
            trail_distance, nearest_trail = _nearest(road_index, rep_lat, rep_lon, max_nearest, "trail")
            water_distance, nearest_water = _nearest(hydro_index, rep_lat, rep_lon, max_nearest, None)
            road_prox = math.exp(-road_distance / 2000.0) if math.isfinite(road_distance) else 0.0
            trail_prox = math.exp(-trail_distance / 1500.0) if math.isfinite(trail_distance) else 0.0
            area_km2 = float(sector["sector_area_m2"]) / 1_000_000.0
            road_density = road_lengths[local_index] / 1000.0 / area_km2
            trail_density = trail_lengths[local_index] / 1000.0 / area_km2
            density_score = min(1.0, (road_density + trail_density) / 4.0)
            geo02 = 0.50 * road_prox + 0.25 * trail_prox + 0.25 * density_score

            hydro_density = hydro_lengths[local_index] / 1000.0 / area_km2
            nearest_severity = nearest_water.severity if nearest_water is not None else 0.0
            proximity_pressure = math.exp(-water_distance / 1500.0) * nearest_severity if math.isfinite(water_distance) else 0.0
            density_pressure = min(1.0, hydro_density / 3.0)
            barrier_pressure = min(1.0, 0.75 * proximity_pressure + 0.25 * density_pressure)
            geo03 = max(0.0, 1.0 - barrier_pressure)

            terrain_values: list[tuple[float, float, float, float]] = []
            land_codes: list[int] = []
            for sample_lat, sample_lon in sector["sample_points"]:
                terrain = hgt.metrics(float(sample_lat), float(sample_lon))
                if terrain is not None:
                    terrain_values.append(terrain)
                code = world_cover.sample(float(sample_lat), float(sample_lon))
                if code is not None:
                    land_codes.append(code)
            expected_samples = len(sector["sample_points"])
            minimum_valid_fraction = float(cfg.get("minimum_valid_raster_sample_fraction", 1.0))
            terrain_coverage = len(terrain_values) / expected_samples if expected_samples else 0.0
            worldcover_coverage = len(land_codes) / expected_samples if expected_samples else 0.0
            geo04 = (
                sum(v[3] for v in terrain_values) / len(terrain_values)
                if terrain_values and terrain_coverage >= minimum_valid_fraction
                else None
            )
            geo05 = (
                sum(WORLD_COVER_SCORES[c] for c in land_codes) / len(land_codes)
                if land_codes and worldcover_coverage >= minimum_valid_fraction
                else None
            )
            land_counts = {code: land_codes.count(code) for code in sorted(set(land_codes))}
            water_wetland_prop = sum(land_counts.get(code, 0) for code in (80, 90)) / len(land_codes) if land_codes else None
            forest_mangrove_prop = sum(land_counts.get(code, 0) for code in (10, 95)) / len(land_codes) if land_codes else None
            barrier_flags: list[str] = []
            if nearest_water is not None and water_distance <= 250 and nearest_severity >= 0.65:
                barrier_flags.append("BARREIRA_HIDRICA_POTENCIAL_ALTA")
            elif nearest_water is not None and water_distance <= 750:
                barrier_flags.append("BARREIRA_HIDRICA_POTENCIAL_MODERADA")
            if water_wetland_prop is not None and water_wetland_prop >= 0.25:
                barrier_flags.append("COBERTURA_AGUA_UMIDA_POTENCIAL")
            if forest_mangrove_prop is not None and forest_mangrove_prop >= 0.70:
                barrier_flags.append("VEGETACAO_DENSA_POTENCIAL")

            module_values = {"geo02": geo02, "geo03": geo03, "geo04": geo04, "geo05": geo05}
            available = sum(v is not None and math.isfinite(v) for v in module_values.values())
            status = "DISPONIVEL" if available == 4 else "PARCIAL" if available else "NAO_DISPONIVEL"
            feature = {
                k: v
                for k, v in sector.items()
                if k not in {"geometry_coordinates", "geometry", "sample_points"} and not k.startswith("_")
            }
            feature.update(
                {
                    "road_distance_m": round(road_distance, 3) if math.isfinite(road_distance) else None,
                    "nearest_road_type": nearest_road.subtype if nearest_road else None,
                    "trail_distance_m": round(trail_distance, 3) if math.isfinite(trail_distance) else None,
                    "nearest_trail_type": nearest_trail.subtype if nearest_trail else None,
                    "road_length_sector_km": round(road_lengths[local_index] / 1000.0, 6),
                    "trail_length_sector_km": round(trail_lengths[local_index] / 1000.0, 6),
                    "road_density_km_km2": round(road_density, 6),
                    "trail_density_km_km2": round(trail_density, 6),
                    "geo02_score": round(geo02, 9),
                    "road_trail_access_score": round(geo02, 9),
                    "water_distance_m": round(water_distance, 3) if math.isfinite(water_distance) else None,
                    "nearest_water_category": nearest_water.subtype if nearest_water else None,
                    "nearest_water_severity": nearest_severity,
                    "hydro_length_sector_km": round(hydro_lengths[local_index] / 1000.0, 6),
                    "hydro_severity_weighted_length_km": round(hydro_severity_lengths[local_index] / 1000.0, 6),
                    "hydro_density_km_km2": round(hydro_density, 6),
                    "geo03_score": round(geo03, 9),
                    "hydro_access_score": round(geo03, 9),
                    "elevation_mean_m": round(sum(v[0] for v in terrain_values) / len(terrain_values), 3) if terrain_values else None,
                    "slope_mean_deg": round(sum(v[1] for v in terrain_values) / len(terrain_values), 6) if terrain_values else None,
                    "relief_mean_m": round(sum(v[2] for v in terrain_values) / len(terrain_values), 6) if terrain_values else None,
                    "terrain_sample_count": len(terrain_values),
                    "terrain_expected_sample_count": expected_samples,
                    "terrain_sample_coverage": round(terrain_coverage, 6),
                    "geo04_score": round(geo04, 9) if geo04 is not None else None,
                    "terrain_access_score": round(geo04, 9) if geo04 is not None else None,
                    "worldcover_sample_count": len(land_codes),
                    "worldcover_expected_sample_count": expected_samples,
                    "worldcover_sample_coverage": round(worldcover_coverage, 6),
                    "worldcover_class_counts": json.dumps(land_counts, ensure_ascii=False, sort_keys=True),
                    "water_wetland_prop": round(water_wetland_prop, 6) if water_wetland_prop is not None else None,
                    "forest_mangrove_prop": round(forest_mangrove_prop, 6) if forest_mangrove_prop is not None else None,
                    "geo05_score": round(geo05, 9) if geo05 is not None else None,
                    "landcover_access_score": round(geo05, 9) if geo05 is not None else None,
                    "modules_available": available,
                    "geo_completeness": round(available / 4.0, 6),
                    "feature_status": status,
                    "barrier_flags": ";".join(barrier_flags) if barrier_flags else "NAO_SINALIZADA",
                    "osm_road_timestamp": road_timestamp,
                    "osm_hydro_timestamp": hydro_timestamp,
                    "feature_method": "OSM_LINE_CHUNKS_PLUS_9_POINT_AREA_STRATIFIED_RASTER_SAMPLE",
                    "source_provenance": "GEO-02/03: OpenStreetMap; GEO-04: Mapzen/Skadi-SRTMGL1; GEO-05: ESA WorldCover 2021 v200",
                    "upstream_review_status": sector.get("source_buffer_review_status"),
                    "field_confirmation": "PENDENTE",
                    "ground_truth_used": False,
                }
            )
            output.append(feature)
    return sorted(output, key=lambda r: (r["scenario_id"], r["candidate_id"], r["ring_index"], r["direction_index"]))


SCORE_FIELD_MAP = {
    "geo02": "road_trail_access_score",
    "geo03": "hydro_access_score",
    "geo04": "terrain_access_score",
    "geo05": "landcover_access_score",
}


def _weight_sets(config: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for item in config["scoring"]["weight_sets"]:
        result[str(item["weight_set"])] = {
            "geo02": float(item["road_trail_weight"]),
            "geo03": float(item["hydro_weight"]),
            "geo04": float(item["terrain_weight"]),
            "geo05": float(item["landcover_weight"]),
        }
    return result


def _weighted_score(row: Mapping[str, Any], weights: Mapping[str, float]) -> tuple[float | None, dict[str, float | None], int]:
    contributions: dict[str, float | None] = {}
    missing = 0
    for module, field in SCORE_FIELD_MAP.items():
        value = row.get(field)
        if value is None:
            missing += 1
            contributions[module] = None
        else:
            contributions[module] = float(weights[module]) * float(value)
    if missing:
        return None, contributions, missing
    return sum(float(value) for value in contributions.values() if value is not None), contributions, 0


def rank_sector_records(records: Sequence[Mapping[str, Any]], config: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Ordena setores dentro de cada buffer; nunca compara candidatos distintos."""
    enforce_ground_truth_firewall(list(records), config)
    weight_sets = _weight_sets(config)
    for name, weights in weight_sets.items():
        if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-12):
            raise ContractError(f"Pesos de {name} não somam 1")
    low_margin = float(config["ranking"]["low_margin_threshold"])
    stability_threshold = float(config["ranking"]["robust_stability_threshold"])
    minimum_unique_wins = int(config["ranking"].get("robust_stability_minimum_top1_wins", 4))
    score_decimals = int(config["ranking"].get("score_comparison_decimals", 9))
    if config["ranking"].get("rank_method") != "COMPETITION_RANK":
        raise ContractError("A v1.1 exige ranking de competição")
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in records:
        row = dict(raw)
        required_score_fields = (
            "road_trail_access_score",
            "hydro_access_score",
            "terrain_access_score",
            "landcover_access_score",
        )
        for field in required_score_fields:
            value = row.get(field)
            if value is not None:
                number = _finite_number(value, field)
                if not 0.0 <= number <= 1.0:
                    raise ContractError(f"{field} fora de [0,1]: {row.get('sector_id')}")
                row[field] = number
        completeness = _finite_number(row.get("geo_completeness", 0.0), "geo_completeness")
        if not 0.0 <= completeness <= 1.0:
            raise ContractError(f"geo_completeness fora de [0,1]: {row.get('sector_id')}")
        row["geo_completeness"] = completeness
        row["ground_truth_used"] = False
        grouped[(str(row["scenario_id"]), str(row["candidate_id"]))].append(row)

    ranked_all: list[dict[str, Any]] = []
    for key in sorted(grouped):
        rows = sorted(grouped[key], key=lambda row: str(row["sector_id"]))
        if len({str(row["sector_id"]) for row in rows}) != len(rows):
            raise ContractError(f"sector_id duplicado no buffer {key}")
        top_by_set: dict[str, list[str]] = {}
        for set_name, weights in weight_sets.items():
            for row in rows:
                score, contributions, missing_count = _weighted_score(row, weights)
                row.setdefault("scores_by_weight_set", {})[set_name] = round(score, score_decimals) if score is not None else None
                row.setdefault("contributions_by_weight_set", {})[set_name] = {
                    module: round(value, 9) if value is not None else None
                    for module, value in contributions.items()
                }
                row["missing_module_count"] = max(int(row.get("missing_module_count", 0)), missing_count)
            complete = [row for row in rows if row["scores_by_weight_set"][set_name] is not None]
            for row in rows:
                row.setdefault("ranks_by_weight_set", {})[set_name] = None
            score_values = [float(row["scores_by_weight_set"][set_name]) for row in complete]
            for row in complete:
                score_value = float(row["scores_by_weight_set"][set_name])
                row["ranks_by_weight_set"][set_name] = 1 + sum(
                    1 for other in score_values if other > score_value
                )
            top_by_set[set_name] = sorted(
                str(row["sector_id"])
                for row in complete
                if row["ranks_by_weight_set"][set_name] == 1
            )

        support_points: dict[str, float] = defaultdict(float)
        membership_count: dict[str, int] = defaultdict(int)
        unique_win_count: dict[str, int] = defaultdict(int)
        for top_ids in top_by_set.values():
            if not top_ids:
                continue
            fractional = 1.0 / len(top_ids)
            for sector_id in top_ids:
                membership_count[sector_id] += 1
                support_points[sector_id] += fractional
            if len(top_ids) == 1:
                unique_win_count[top_ids[0]] += 1

        base_top = top_by_set.get("BASE", [])
        winner = next((row for row in rows if len(base_top) == 1 and str(row["sector_id"]) == base_top[0]), None)
        base_order = sorted(
            [row for row in rows if row["scores_by_weight_set"].get("BASE") is not None],
            key=lambda row: (-float(row["scores_by_weight_set"]["BASE"]), str(row["sector_id"])),
        )
        if len(base_top) > 1:
            margin = 0.0
        elif len(base_order) >= 2:
            margin = float(base_order[0]["scores_by_weight_set"]["BASE"]) - float(base_order[1]["scores_by_weight_set"]["BASE"])
        elif len(base_order) == 1:
            margin = float(base_order[0]["scores_by_weight_set"]["BASE"])
        else:
            margin = None
        winner_id = str(winner["sector_id"]) if winner is not None else None
        top_stability = support_points[winner_id] / len(weight_sets) if winner_id is not None else None
        sensitivity_ties = sorted(
            name for name, ids in top_by_set.items() if name != "BASE" and len(ids) > 1
        )
        upstream_review = any(
            str(row.get("upstream_review_status", row.get("source_buffer_review_status", ""))) == "REVISAR"
            for row in rows
        )
        group_warnings: list[str] = []
        blocking_warnings: list[str] = []
        if upstream_review:
            group_warnings.append("UPSTREAM_REVIEW_REQUIRED")
            blocking_warnings.append("UPSTREAM_REVIEW_REQUIRED")
        if any(int(row.get("missing_module_count", 0)) > 0 or float(row.get("geo_completeness", 0.0)) < 1.0 for row in rows):
            group_warnings.append("INCOMPLETE_GEO")
            blocking_warnings.append("INCOMPLETE_GEO")
        if any(not str(row.get("source_provenance", "")).strip() for row in rows):
            group_warnings.append("MISSING_SOURCE_PROVENANCE")
            blocking_warnings.append("MISSING_SOURCE_PROVENANCE")
        if margin is None:
            group_warnings.append("NO_COMPLETE_SECTOR")
            blocking_warnings.append("NO_COMPLETE_SECTOR")
        elif margin < low_margin:
            group_warnings.append("LOW_MARGIN")
            blocking_warnings.append("LOW_MARGIN")
        if len(base_top) > 1:
            group_warnings.extend(["BASE_TOP_TIE", "NO_UNIQUE_TOP1"])
            blocking_warnings.extend(["BASE_TOP_TIE", "NO_UNIQUE_TOP1"])
        if sensitivity_ties:
            group_warnings.append("SENSITIVITY_TOP_TIE")
        if winner_id is not None and (
            top_stability is None
            or top_stability < stability_threshold
            or unique_win_count[winner_id] < minimum_unique_wins
        ):
            group_warnings.append("RANKING_UNSTABLE")
            blocking_warnings.append("RANKING_UNSTABLE")
        if winner is not None and str(winner.get("barrier_flags", "NAO_SINALIZADA")) != "NAO_SINALIZADA":
            group_warnings.append("POTENTIAL_BARRIER")
            blocking_warnings.append("POTENTIAL_BARRIER")
        group_status = "PRIORIZADO" if not blocking_warnings else "REVISAR"

        for row in rows:
            missing = int(row.get("missing_module_count", 0)) > 0 or float(row.get("geo_completeness", 0.0)) < 1.0
            warnings = list(group_warnings)
            if missing:
                warnings.append("MISSING_REQUIRED_GEO_SCORE")
            priority = row["scores_by_weight_set"].get("BASE")
            base_rank = row["ranks_by_weight_set"].get("BASE")
            row["priority_score"] = priority
            row["score_base"] = priority
            row["sector_rank"] = base_rank
            row["rank_base_within_buffer"] = base_rank
            row["base_top_member"] = str(row["sector_id"]) in base_top
            row["selected_sector"] = bool(winner_id is not None and str(row["sector_id"]) == winner_id)
            row["rank_margin"] = round(margin, 9) if margin is not None else None
            row["buffer_base_margin"] = row["rank_margin"]
            sector_id = str(row["sector_id"])
            row["top1_count"] = membership_count[sector_id]
            row["top1_membership_count"] = membership_count[sector_id]
            row["top1_unique_win_count"] = unique_win_count[sector_id]
            row["top1_support_points"] = round(support_points[sector_id], 9)
            row["top1_stability"] = round(support_points[sector_id] / len(weight_sets), 9)
            row["top1_by_weight_set"] = top_by_set
            row["weight_sets_with_top_tie"] = sensitivity_ties + (["BASE"] if len(base_top) > 1 else [])
            row["decision_status"] = "REVISAR" if missing else group_status
            row["buffer_decision_status"] = group_status
            row["warning_codes"] = ";".join(dict.fromkeys(warnings)) if warnings else "NONE"
            row["buffer_warning_codes"] = ";".join(dict.fromkeys(group_warnings)) if group_warnings else "NONE"
            row["supervision_required"] = True
            row["score_interpretation"] = "PRIORIDADE_OPERACIONAL_TERRITORIAL_NAO_PROBABILIDADE"
            row["ground_truth_used"] = False
        ranked_all.extend(rows)

    return sorted(
        ranked_all,
        key=lambda row: (
            str(row["scenario_id"]),
            str(row["candidate_id"]),
            row["sector_rank"] is None,
            row["sector_rank"] if row["sector_rank"] is not None else 10**9,
            str(row["sector_id"]),
        ),
    )


def summarize_buffer_decisions(ranked: Sequence[Mapping[str, Any]], config: Mapping[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in ranked:
        grouped[(str(row["scenario_id"]), str(row["candidate_id"]))].append(row)
    decisions: list[dict[str, Any]] = []
    for key in sorted(grouped):
        rows = grouped[key]
        winner = next((row for row in rows if row.get("selected_sector")), None)
        base_top_ids = sorted(str(row["sector_id"]) for row in rows if row.get("base_top_member"))
        first = rows[0]
        top_by_set = {
            name: sorted(
                str(row["sector_id"])
                for row in rows
                if row.get("ranks_by_weight_set", {}).get(name) == 1
            )
            for name in _weight_sets(config)
        }
        decisions.append(
            {
                "protocol_id": config["protocol_id"],
                "scenario_id": key[0],
                "candidate_id": key[1],
                "top1_sector_id": winner.get("sector_id") if winner else None,
                "top1_sector_ids_base": json.dumps(base_top_ids, ensure_ascii=False),
                "top1_unique": winner is not None,
                "top1_score_base": winner.get("priority_score") if winner else None,
                "base_margin": winner.get("rank_margin") if winner else None,
                "top1_stability": winner.get("top1_stability") if winner else None,
                "top1_unique_win_count": winner.get("top1_unique_win_count") if winner else 0,
                "top1_membership_count": winner.get("top1_membership_count") if winner else 0,
                "top1_support_points": winner.get("top1_support_points") if winner else 0.0,
                "top1_by_weight_set": json.dumps(top_by_set, ensure_ascii=False, sort_keys=True),
                "weight_sets_with_top_tie": json.dumps(first.get("weight_sets_with_top_tie", []), ensure_ascii=False),
                "decision_status": first.get("buffer_decision_status", "REVISAR"),
                "warning_codes": first.get("buffer_warning_codes", "NO_COMPLETE_SECTOR"),
                "source_execution_classification": first.get("source_execution_classification"),
                "confirmatory_eligible": False,
                "supervision_required": True,
                "ground_truth_used": False,
            }
        )
    return decisions


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return value


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], excluded: set[str] | None = None) -> None:
    excluded = excluded or set()
    fields = sorted({key for row in rows for key in row if key not in excluded})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fields})


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_sector_geojson(
    sectors: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    ranked: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    features = []
    for sector in sectors:
        props = {
            k: v
            for k, v in sector.items()
            if k not in {"geometry_coordinates", "geometry", "sample_points"} and not k.startswith("_")
        }
        if ranked and str(sector["sector_id"]) in ranked:
            row = ranked[str(sector["sector_id"])]
            for key in (
                "geo02_score",
                "geo03_score",
                "geo04_score",
                "geo05_score",
                "score_base",
                "rank_base_within_buffer",
                "base_top_member",
                "selected_sector",
                "top1_stability",
                "top1_unique_win_count",
                "barrier_flags",
                "buffer_decision_status",
                "buffer_warning_codes",
            ):
                props[key] = row.get(key)
        props["ground_truth_used"] = False
        features.append(
            {
                "type": "Feature",
                "id": sector["sector_id"],
                "properties": props,
                "geometry": {"type": "Polygon", "coordinates": [sector["geometry_coordinates"]]},
            }
        )
    return {
        "type": "FeatureCollection",
        "name": config["protocol_id"],
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "ground_truth_used": False,
        "features": features,
    }


def _source_file(path: Path, role: str) -> dict[str, Any]:
    return {"role": role, "path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    config_path = Path(args.config).resolve()
    buffer_json_path = Path(args.buffer_json).resolve()
    buffer_geojson_path = Path(args.buffer_geojson).resolve()
    buffer_manifest_path = Path(args.buffer_manifest).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    config = load_json(config_path)
    buffer_doc = load_json(buffer_json_path)
    buffer_geojson = load_json(buffer_geojson_path)
    buffer_manifest = load_json(buffer_manifest_path)
    validate_firewall_config(config)
    buffer_rows = validate_buffer_contract(
        buffer_doc,
        buffer_geojson,
        buffer_manifest,
        buffer_json_path,
        buffer_geojson_path,
        config,
    )
    sectors = make_sector_records(buffer_rows, config)

    road_path = Path(args.roads).resolve()
    hydro_path = Path(args.hydro).resolve()
    dem_dir = Path(args.dem_dir).resolve()
    worldcover_dir = Path(args.worldcover_dir).resolve()
    roads, road_timestamp = load_road_segments(road_path, config)
    hydros, hydro_timestamp = load_hydro_segments(hydro_path, config)
    road_index = SpatialSegmentIndex(roads, float(config["feature_extraction"]["spatial_index_cell_deg"]))
    hydro_index = SpatialSegmentIndex(hydros, float(config["feature_extraction"]["spatial_index_cell_deg"]))
    hgt = HGTSampler(dem_dir)
    world_cover = WorldCoverSampler(worldcover_dir)
    try:
        features = extract_sector_features(
            sectors,
            buffer_rows,
            config,
            road_index,
            hydro_index,
            hgt,
            world_cover,
            road_timestamp,
            hydro_timestamp,
        )
    finally:
        world_cover.close()
    ranked = rank_sector_records(features, config)
    decisions = summarize_buffer_decisions(ranked, config)

    ranked_by_id = {str(row["sector_id"]): row for row in ranked}
    geometry_path = output_dir / "sector_polygons_dev.geojson"
    features_path = output_dir / "sector_features_dev.csv"
    ranking_path = output_dir / "sector_ranking_dev.csv"
    decisions_path = output_dir / "buffer_decisions_dev.csv"
    results_path = output_dir / "sector_results_dev.json"
    warnings_path = output_dir / "warnings_dev.log"
    manifest_path = output_dir / "manifest_setorizacao_dev.json"

    geometry_doc = build_sector_geojson(sectors, config, ranked_by_id)
    enforce_ground_truth_firewall(geometry_doc, config)
    enforce_ground_truth_firewall(features, config)
    enforce_ground_truth_firewall(ranked, config)
    enforce_ground_truth_firewall(decisions, config)
    write_json(geometry_path, geometry_doc)
    write_csv(features_path, features)
    write_csv(ranking_path, ranked)
    write_csv(decisions_path, decisions)
    result_doc = {
        "protocol_id": config["protocol_id"],
        "engine_version": config["engine_version"],
        "execution_phase": "DEV-S",
        "execution_classification": "DESENVOLVIMENTO_NAO_CONFIRMATORIO",
        "ground_truth_used": False,
        "buffer_count": len(buffer_rows),
        "sector_count": len(ranked),
        "sectors_per_buffer": int(config["geometry"]["sectors_per_buffer"]),
        "ranking_grain": "scenario_id+candidate_id+sector_id",
        "ranking_scope": "WITHIN_BUFFER_ONLY",
        "rank_method": config["ranking"]["rank_method"],
        "tie_policy": config["ranking"]["tie_policy"],
        "score_interpretation": "PRIORIDADE_OPERACIONAL_TERRITORIAL_NAO_PROBABILIDADE",
        "decisions": decisions,
        "results": ranked,
    }
    enforce_ground_truth_firewall(result_doc, config)
    write_json(results_path, result_doc)
    warnings_lines = [
        f"{row['scenario_id']}|{row['candidate_id']}|{row['decision_status']}|{row['warning_codes']}"
        for row in decisions
        if row["warning_codes"] != "NONE"
    ]
    warnings_path.write_text("\n".join(warnings_lines) + ("\n" if warnings_lines else ""), encoding="utf-8")

    scientific_projection_hash = canonical_hash(
        [
            {
                "sector_id": row["sector_id"],
                "score_base": row["score_base"],
                "rank_base_within_buffer": row["rank_base_within_buffer"],
                "decision_status": row["buffer_decision_status"],
                "selected_sector": row["selected_sector"],
                "top1_stability": row["top1_stability"],
            }
            for row in ranked
        ]
    )
    source_files = [
        _source_file(buffer_json_path, "input_buffer_json"),
        _source_file(buffer_geojson_path, "input_buffer_geojson"),
        _source_file(buffer_manifest_path, "input_buffer_manifest"),
        _source_file(config_path, "config"),
        _source_file(Path(__file__).resolve(), "engine"),
        _source_file(road_path, "source_geo02_osm"),
        _source_file(hydro_path, "source_geo03_osm"),
    ]
    for path in sorted(dem_dir.glob("*.hgt.gz")):
        source_files.append(_source_file(path.resolve(), "source_geo04_dem"))
    for path in sorted(worldcover_dir.glob("*.tif")):
        source_files.append(_source_file(path.resolve(), "source_geo05_worldcover"))
    output_files = [
        _source_file(path, "output")
        for path in (geometry_path, features_path, ranking_path, decisions_path, results_path, warnings_path)
    ]
    scientific_bundle_hash = canonical_hash(
        {Path(item["path"]).name: item["sha256"] for item in output_files}
    )
    manifest = {
        "protocol_id": config["protocol_id"],
        "engine_version": config["engine_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python_version": platform.python_version(),
        "ground_truth_used": False,
        "execution_phase": "DEV-S",
        "execution_classification": "DESENVOLVIMENTO_NAO_CONFIRMATORIO",
        "buffer_count": len(buffer_rows),
        "sector_count": len(ranked),
        "sectors_per_buffer": int(config["geometry"]["sectors_per_buffer"]),
        "decision_count": len(decisions),
        "scientific_projection_sha256": scientific_projection_hash,
        "scientific_bundle_sha256": scientific_bundle_hash,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "firewall": "GROUND_TRUTH_PROHIBITED_AND_NOT_USED",
        "files": source_files + output_files,
    }
    enforce_ground_truth_firewall(manifest, config)
    write_json(manifest_path, manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--buffer-json", required=True)
    parser.add_argument("--buffer-geojson", required=True)
    parser.add_argument("--buffer-manifest", required=True)
    parser.add_argument("--roads", required=True)
    parser.add_argument("--hydro", required=True)
    parser.add_argument("--dem-dir", required=True)
    parser.add_argument("--worldcover-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = run_pipeline(args)
    except (ContractError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
