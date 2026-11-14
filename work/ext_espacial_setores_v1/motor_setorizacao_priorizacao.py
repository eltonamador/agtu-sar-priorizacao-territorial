#!/usr/bin/env python3
"""Motor auditável de setorização e priorização territorial (EXT-ESP-SET-v1.0).

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
FORBIDDEN_GT_KEYS = {
    "ground_truth_lat",
    "ground_truth_lon",
    "ground_truth_longitude",
    "truth_lat",
    "truth_lon",
    "reference_lat",
    "reference_lon",
    "real_lat",
    "real_lon",
    "target_lat",
    "target_lon",
    "distance_to_truth",
    "distance_to_truth_m",
    "distance_to_ground_truth",
    "distance_to_reference",
    "distance_to_reference_m",
    "inside_buffer",
    "ground_truth_sector",
    "correct_sector",
    "true_lat",
    "true_lon",
    "victim_lat",
    "victim_lon",
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


def enforce_ground_truth_firewall(value: Any) -> None:
    """Bloqueia coordenadas/derivações da referência e exige controles false."""
    for path, item in _walk(value):
        key = path.rsplit(".", 1)[-1].lower()
        if key in FORBIDDEN_GT_KEYS:
            raise ContractError(f"Campo proibido pelo firewall: {path}")
        if key == "ground_truth_used" and item is not False:
            raise ContractError(f"ground_truth_used deve ser booleano false: {path}")


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
) -> list[dict[str, Any]]:
    enforce_ground_truth_firewall(buffer_doc)
    if buffer_geojson is not None:
        enforce_ground_truth_firewall(buffer_geojson)
    if buffer_manifest is not None:
        enforce_ground_truth_firewall(buffer_manifest)
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
        if not scenario_id or not candidate_id:
            raise ContractError("scenario_id/candidate_id vazios")
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
        for feature in features:
            props = feature.get("properties", {})
            key = (str(props.get("scenario_id", "")), str(props.get("candidate_id", "")))
            if key in geo_keys:
                raise ContractError(f"Feição duplicada: {key}")
            geo_keys.add(key)
            if feature.get("id") != f"{key[0]}::{key[1]}":
                raise ContractError(f"ID de feição divergente: {key}")
            geometry = feature.get("geometry", {})
            coordinates = geometry.get("coordinates", [])
            if geometry.get("type") != "Polygon" or len(coordinates) != 1 or len(coordinates[0]) < 4:
                raise ContractError(f"Geometria inválida: {key}")
            if coordinates[0][0] != coordinates[0][-1]:
                raise ContractError(f"Anel não fechado: {key}")
        if geo_keys != keys:
            raise ContractError("Conjunto de candidatos difere entre JSON e GeoJSON")

    if buffer_manifest is not None:
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


def _shoelace_area(coords: Sequence[Sequence[float]], lat0: float, lon0: float) -> float:
    points = [local_xy(float(lat), float(lon), lat0, lon0) for lon, lat in coords]
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(points, points[1:]))) / 2.0


def _sector_polygon(
    lat: float,
    lon: float,
    inner_m: float,
    outer_m: float,
    start_deg: float,
    end_deg: float,
    arc_segments: int,
) -> list[list[float]]:
    bearings = [start_deg + (end_deg - start_deg) * i / arc_segments for i in range(arc_segments + 1)]
    outer = [destination(lat, lon, outer_m, b) for b in bearings]
    if inner_m <= 1e-12:
        latlon = [(lat, lon), *outer, (lat, lon)]
    else:
        inner = [destination(lat, lon, inner_m, b) for b in reversed(bearings)]
        latlon = [*outer, *inner, outer[0]]
    return [[p_lon, p_lat] for p_lat, p_lon in latlon]


def _sector_sample_points(
    lat: float,
    lon: float,
    inner_m: float,
    outer_m: float,
    start_deg: float,
    end_deg: float,
    radial_samples: int,
    angular_samples: int,
) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    for ri in range(radial_samples):
        q_r = (ri + 0.5) / radial_samples
        radius = math.sqrt(inner_m * inner_m + q_r * (outer_m * outer_m - inner_m * inner_m))
        for ai in range(angular_samples):
            q_a = (ai + 0.5) / angular_samples
            result.append(destination(lat, lon, radius, start_deg + q_a * (end_deg - start_deg)))
    return result


def make_sector_records(buffer_rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]) -> list[dict[str, Any]]:
    geometry = config["geometry"]
    ring_count = int(geometry.get("ring_count", geometry.get("rings", 0)))
    direction_centers = geometry.get("direction_centers_deg")
    directions = list(direction_centers.keys()) if isinstance(direction_centers, dict) else list(geometry.get("direction_labels", []))
    if ring_count != 3 or len(directions) != 8:
        raise ContractError("SETOR-v1 exige 3 anéis e 8 direções")
    arc_segments = int(
        geometry.get(
            "arc_segments_per_45_degrees",
            round(45.0 / float(geometry.get("arc_step_deg", 5.0))),
        )
    )
    rotation = float(geometry.get("rotation_deg", 0.0))
    raster_sampling = config.get("feature_extraction", {}).get("raster_sampling", {})
    radial_samples = int(geometry.get("radial_samples", raster_sampling.get("radial_samples", 3)))
    angular_samples = int(geometry.get("angular_samples", raster_sampling.get("angular_samples", 3)))
    output: list[dict[str, Any]] = []
    for source in sorted(buffer_rows, key=lambda r: (str(r["scenario_id"]), str(r["candidate_id"]))):
        lat = float(source["estimated_lat"])
        lon = float(source["estimated_lon"])
        radius = float(source["adaptive_radius_m"])
        radial_bounds = [radius * math.sqrt(i / ring_count) for i in range(ring_count + 1)]
        theoretical_area = math.pi * radius * radius / (ring_count * len(directions))
        for ring_index in range(ring_count):
            inner_m = radial_bounds[ring_index]
            outer_m = radial_bounds[ring_index + 1]
            for direction_index, label in enumerate(directions):
                center = rotation + direction_index * 360.0 / len(directions)
                half = 180.0 / len(directions)
                start = center - half
                end = center + half
                ring_id = f"R{ring_index + 1:02d}"
                sector_id = f"{source['scenario_id']}::{source['candidate_id']}::{ring_id}::{label}"
                coords = _sector_polygon(lat, lon, inner_m, outer_m, start, end, arc_segments)
                rep_radius = math.sqrt((inner_m * inner_m + outer_m * outer_m) / 2.0)
                rep_lat, rep_lon = destination(lat, lon, rep_radius, center)
                samples = _sector_sample_points(
                    lat, lon, inner_m, outer_m, start, end, radial_samples, angular_samples
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
                        "sector_area_m2": round(theoretical_area, 6),
                        "polygon_planar_area_m2": round(planar_area, 6),
                        "area_relative_error": round(abs(planar_area - theoretical_area) / theoretical_area, 9),
                        "representative_lat": rep_lat,
                        "representative_lon": rep_lon,
                        "sample_points": [[p[0], p[1]] for p in samples],
                        "geometry_coordinates": coords,
                        "geometry": {"type": "Polygon", "coordinates": [coords]},
                        "source_buffer_review_status": source["review_status"],
                        "source_execution_classification": source["execution_classification"],
                        "source_confirmatory_eligible": bool(source["confirmatory_eligible"]),
                        "source_row_hash": source["source_row_hash"],
                        "ground_truth_used": False,
                    }
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


def load_road_segments(path: str | Path) -> tuple[list[Segment], str | None]:
    doc = load_json(path)
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


def load_hydro_segments(path: str | Path) -> tuple[list[Segment], str | None]:
    doc = load_json(path)
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


def _allocate_lengths(
    segments: Sequence[Segment],
    lat0: float,
    lon0: float,
    radius_m: float,
    chunk_m: float,
    cls_filter: str | None = None,
) -> tuple[list[float], list[float]]:
    lengths = [0.0] * 24
    severity_lengths = [0.0] * 24
    for seg in segments:
        if cls_filter is not None and seg.cls != cls_filter:
            continue
        clipped = _clip_segment_circle(seg, lat0, lon0, radius_m)
        if clipped is None:
            continue
        ax, ay, bx, by = clipped
        length = math.hypot(bx - ax, by - ay)
        steps = max(1, int(math.ceil(length / chunk_m)))
        for i in range(steps):
            t0, t1 = i / steps, (i + 1) / steps
            mx = ax + ((t0 + t1) / 2.0) * (bx - ax)
            my = ay + ((t0 + t1) / 2.0) * (by - ay)
            index = _sector_index_for_xy(mx, my, radius_m)
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
        road_lengths, _ = _allocate_lengths(roads_nearby, lat0, lon0, radius, float(cfg["line_chunk_m"]), "road")
        trail_lengths, _ = _allocate_lengths(roads_nearby, lat0, lon0, radius, float(cfg["line_chunk_m"]), "trail")
        hydro_lengths, hydro_severity_lengths = _allocate_lengths(hydros_nearby, lat0, lon0, radius, float(cfg["line_chunk_m"]), None)

        sector_list = sorted(by_buffer[key], key=lambda s: (int(s["ring_index"]), int(s["direction_index"])))
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
            geo04 = sum(v[3] for v in terrain_values) / len(terrain_values) if terrain_values else None
            geo05 = sum(WORLD_COVER_SCORES[c] for c in land_codes) / len(land_codes) if land_codes else None
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
            feature = {k: v for k, v in sector.items() if k not in {"geometry_coordinates", "geometry", "sample_points"}}
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
                    "geo04_score": round(geo04, 9) if geo04 is not None else None,
                    "terrain_access_score": round(geo04, 9) if geo04 is not None else None,
                    "worldcover_sample_count": len(land_codes),
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
    enforce_ground_truth_firewall(list(records))
    weight_sets = _weight_sets(config)
    for name, weights in weight_sets.items():
        if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-12):
            raise ContractError(f"Pesos de {name} não somam 1")
    low_margin = float(config["ranking"]["low_margin_threshold"])
    stability_threshold = float(config["ranking"]["robust_stability_threshold"])
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
        top_by_set: dict[str, str] = {}
        for set_name, weights in weight_sets.items():
            for row in rows:
                score, contributions, missing_count = _weighted_score(row, weights)
                row.setdefault("scores_by_weight_set", {})[set_name] = round(score, 9) if score is not None else None
                row.setdefault("contributions_by_weight_set", {})[set_name] = {
                    module: round(value, 9) if value is not None else None
                    for module, value in contributions.items()
                }
                row["missing_module_count"] = max(int(row.get("missing_module_count", 0)), missing_count)
            complete = [row for row in rows if row["scores_by_weight_set"][set_name] is not None]
            ordered = sorted(complete, key=lambda row: (-float(row["scores_by_weight_set"][set_name]), str(row["sector_id"])))
            for row in rows:
                row.setdefault("ranks_by_weight_set", {})[set_name] = None
            for rank, row in enumerate(ordered, start=1):
                row["ranks_by_weight_set"][set_name] = rank
            if ordered:
                top_by_set[set_name] = str(ordered[0]["sector_id"])

        counts: dict[str, int] = defaultdict(int)
        for sector_id in top_by_set.values():
            counts[sector_id] += 1
        base_order = sorted(
            [row for row in rows if row["scores_by_weight_set"].get("BASE") is not None],
            key=lambda row: (-float(row["scores_by_weight_set"]["BASE"]), str(row["sector_id"])),
        )
        winner = base_order[0] if base_order else None
        if len(base_order) >= 2:
            margin = float(base_order[0]["scores_by_weight_set"]["BASE"]) - float(base_order[1]["scores_by_weight_set"]["BASE"])
        elif len(base_order) == 1:
            margin = float(base_order[0]["scores_by_weight_set"]["BASE"])
        else:
            margin = None
        top_stability = counts[str(winner["sector_id"])] / len(weight_sets) if winner is not None else 0.0
        tie = margin is not None and math.isclose(margin, 0.0, abs_tol=1e-12)
        upstream_review = any(
            str(row.get("upstream_review_status", row.get("source_buffer_review_status", ""))) == "REVISAR"
            for row in rows
        )
        group_warnings: list[str] = []
        if upstream_review:
            group_warnings.append("UPSTREAM_REVIEW_REQUIRED")
        if any(int(row.get("missing_module_count", 0)) > 0 or float(row.get("geo_completeness", 0.0)) < 1.0 for row in rows):
            group_warnings.append("INCOMPLETE_GEO")
        if margin is None:
            group_warnings.append("NO_COMPLETE_SECTOR")
        elif margin < low_margin:
            group_warnings.append("LOW_MARGIN")
        if tie:
            group_warnings.append("TOP_SCORE_TIE")
        if top_stability < stability_threshold:
            group_warnings.append("RANKING_UNSTABLE")
        if winner is not None and str(winner.get("barrier_flags", "NAO_SINALIZADA")) != "NAO_SINALIZADA":
            group_warnings.append("POTENTIAL_BARRIER")
        group_status = "PRIORIZADO" if not group_warnings else "REVISAR"

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
            row["selected_sector"] = bool(winner is not None and row["sector_id"] == winner["sector_id"])
            row["rank_margin"] = round(margin, 9) if margin is not None else None
            row["buffer_base_margin"] = row["rank_margin"]
            row["top1_count"] = counts[str(row["sector_id"])]
            row["top1_stability"] = round(counts[str(row["sector_id"])] / len(weight_sets), 9)
            row["decision_status"] = "REVISAR" if missing else group_status
            row["buffer_decision_status"] = row["decision_status"]
            row["warning_codes"] = ";".join(dict.fromkeys(warnings)) if warnings else "NONE"
            row["buffer_warning_codes"] = row["warning_codes"]
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
        decisions.append(
            {
                "protocol_id": config["protocol_id"],
                "scenario_id": key[0],
                "candidate_id": key[1],
                "top1_sector_id": winner.get("sector_id") if winner else None,
                "top1_score_base": winner.get("priority_score") if winner else None,
                "base_margin": winner.get("rank_margin") if winner else None,
                "top1_stability": winner.get("top1_stability") if winner else 0.0,
                "top1_by_weight_set": json.dumps(
                    {
                        name: next((row["sector_id"] for row in rows if row.get("ranks_by_weight_set", {}).get(name) == 1), None)
                        for name in _weight_sets(config)
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "decision_status": winner.get("decision_status", "REVISAR") if winner else "REVISAR",
                "warning_codes": winner.get("warning_codes", "NO_COMPLETE_SECTOR") if winner else "NO_COMPLETE_SECTOR",
                "source_execution_classification": winner.get("source_execution_classification") if winner else None,
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


def build_sector_geojson(sectors: Sequence[Mapping[str, Any]], ranked: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    features = []
    for sector in sectors:
        props = {k: v for k, v in sector.items() if k not in {"geometry_coordinates", "geometry", "sample_points"}}
        if ranked and str(sector["sector_id"]) in ranked:
            row = ranked[str(sector["sector_id"])]
            for key in (
                "geo02_score",
                "geo03_score",
                "geo04_score",
                "geo05_score",
                "score_base",
                "rank_base_within_buffer",
                "top1_stability",
                "barrier_flags",
                "buffer_decision_status",
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
        "name": "EXT-ESP-SET-v1.0",
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
    enforce_ground_truth_firewall(config)
    buffer_rows = validate_buffer_contract(
        buffer_doc,
        buffer_geojson,
        buffer_manifest,
        buffer_json_path,
        buffer_geojson_path,
    )
    sectors = make_sector_records(buffer_rows, config)

    road_path = Path(args.roads).resolve()
    hydro_path = Path(args.hydro).resolve()
    dem_dir = Path(args.dem_dir).resolve()
    worldcover_dir = Path(args.worldcover_dir).resolve()
    roads, road_timestamp = load_road_segments(road_path)
    hydros, hydro_timestamp = load_hydro_segments(hydro_path)
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

    write_json(geometry_path, build_sector_geojson(sectors, ranked_by_id))
    write_csv(features_path, features)
    write_csv(ranking_path, ranked)
    write_csv(decisions_path, decisions)
    result_doc = {
        "protocol_id": config["protocol_id"],
        "engine_version": config["engine_version"],
        "execution_phase": "DEV_S",
        "execution_classification": "DESENVOLVIMENTO_NAO_CONFIRMATORIO",
        "ground_truth_used": False,
        "buffer_count": len(buffer_rows),
        "sector_count": len(ranked),
        "sectors_per_buffer": 24,
        "ranking_grain": "scenario_id+candidate_id+sector_id",
        "ranking_scope": "WITHIN_BUFFER_ONLY",
        "score_interpretation": "PRIORIDADE_OPERACIONAL_TERRITORIAL_NAO_PROBABILIDADE",
        "decisions": decisions,
        "results": ranked,
    }
    write_json(results_path, result_doc)
    warnings_lines = [
        f"{row['scenario_id']}|{row['candidate_id']}|{row['decision_status']}|{row['warning_codes']}"
        for row in decisions
        if row["warning_codes"] != "NONE"
    ]
    warnings_path.write_text("\n".join(warnings_lines) + ("\n" if warnings_lines else ""), encoding="utf-8")

    scientific_hash = canonical_hash(
        [
            {
                "sector_id": row["sector_id"],
                "score_base": row["score_base"],
                "rank_base_within_buffer": row["rank_base_within_buffer"],
                "decision": row["buffer_decision_status"],
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
    manifest = {
        "protocol_id": config["protocol_id"],
        "engine_version": config["engine_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python_version": platform.python_version(),
        "ground_truth_used": False,
        "execution_phase": "DEV_S",
        "execution_classification": "DESENVOLVIMENTO_NAO_CONFIRMATORIO",
        "buffer_count": len(buffer_rows),
        "sector_count": len(ranked),
        "sectors_per_buffer": 24,
        "decision_count": len(decisions),
        "scientific_output_sha256": scientific_hash,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "firewall": "GROUND_TRUTH_PROHIBITED_AND_NOT_USED",
        "files": source_files + output_files,
    }
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
