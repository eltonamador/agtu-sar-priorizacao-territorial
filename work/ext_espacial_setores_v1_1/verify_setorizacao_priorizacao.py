#!/usr/bin/env python3
"""Verificador independente das saídas DEV-S de setorização e priorização v1.1.

O programa não importa o motor que produziu os resultados. Ele lê apenas o
contrato congelado, o JSON e o GeoJSON autoritativo dos buffers e os artefatos
gravados no diretório de resultados. O relatório contém uma lista explícita de
verificações PASS/FAIL e o processo termina com código 0 somente quando todas
elas passam.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


VERIFIER_ID = "EXT-ESP-SET-VERIFY-v1.1"

RESULT_FILES = {
    "manifest": "manifest_setorizacao_dev.json",
    "results": "sector_results_dev.json",
    "geojson": "sector_polygons_dev.geojson",
    "features_csv": "sector_features_dev.csv",
    "ranking_csv": "sector_ranking_dev.csv",
    "decisions_csv": "buffer_decisions_dev.csv",
    "warnings": "warnings_dev.log",
}

MANIFEST_OUTPUTS = {
    RESULT_FILES["geojson"],
    RESULT_FILES["features_csv"],
    RESULT_FILES["ranking_csv"],
    RESULT_FILES["decisions_csv"],
    RESULT_FILES["results"],
    RESULT_FILES["warnings"],
}

REQUIRED_SCORE_FIELDS = (
    "road_trail_access_score",
    "hydro_access_score",
    "terrain_access_score",
    "landcover_access_score",
)

SCORE_TO_WEIGHT = {
    "road_trail_access_score": "road_trail_weight",
    "hydro_access_score": "hydro_weight",
    "terrain_access_score": "terrain_weight",
    "landcover_access_score": "landcover_weight",
}

SCORE_TO_MODULE = {
    "road_trail_access_score": "geo02",
    "hydro_access_score": "geo03",
    "terrain_access_score": "geo04",
    "landcover_access_score": "geo05",
}

DEFAULT_GT_FRAGMENTS = {
    "ground_truth",
    "ground_truth_lat",
    "ground_truth_lon",
    "truth_",
    "reference_lat",
    "reference_lon",
    "true_lat",
    "true_lon",
    "real_lat",
    "real_lon",
    "victim_lat",
    "victim_lon",
    "target_lat",
    "target_lon",
    "base_lat",
    "base_lon",
    "generator_distance",
    "distance_to_truth",
    "distance_to_ground_truth",
    "distance_to_reference",
    "inside_buffer",
    "sector_contains_truth",
    "reference_sector",
    "correct_sector",
    "relevant_candidate",
}

CROSS_BUFFER_RANK_FIELDS = {
    "global_rank",
    "rank_global",
    "scenario_rank",
    "rank_scenario",
    "cross_buffer_rank",
    "rank_cross_buffer",
    "cross_candidate_rank",
    "rank_cross_candidate",
    "candidate_rank",
    "buffer_rank",
    "buffer_id",
    "scenario_global_rank",
    "candidate_global_rank",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def integer_value(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def relative_error(actual: float, expected: float) -> float:
    denominator = max(abs(expected), 1e-15)
    return abs(actual - expected) / denominator


def close_number(actual: Any, expected: Any, *, abs_tol: float = 2e-8) -> bool:
    a = finite_number(actual)
    b = finite_number(expected)
    return a is not None and b is not None and math.isclose(a, b, rel_tol=0.0, abs_tol=abs_tol)


def optional_number_equal(actual: Any, expected: Any, *, abs_tol: float = 2e-8) -> bool:
    if actual in (None, "") and expected is None:
        return True
    if isinstance(actual, str):
        try:
            actual = float(actual)
        except ValueError:
            return False
    if isinstance(expected, str):
        try:
            expected = float(expected)
        except ValueError:
            return False
    return close_number(actual, expected, abs_tol=abs_tol)


def bool_from_csv(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def codes(value: Any) -> list[str]:
    if value in (None, "", "NONE"):
        return []
    return [item for item in str(value).split(";") if item]


def key_of(row: Mapping[str, Any]) -> tuple[str, str]:
    return str(row.get("scenario_id", "")), str(row.get("candidate_id", ""))


def sample(items: Iterable[Any], limit: int = 8) -> list[Any]:
    values = list(items)
    return values[:limit]


def resolve_manifest_path(raw: Any, manifest_path: Path) -> Path:
    path = Path(str(raw))
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path.resolve()


def normalize_key(value: Any) -> str:
    return str(value).strip().lower()


def polygon_ring(geometry: Any) -> list[tuple[float, float]] | None:
    """Extrai o anel externo aberto de um Polygon GeoJSON simples."""
    if not isinstance(geometry, Mapping) or geometry.get("type") != "Polygon":
        return None
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) != 1 or not isinstance(coordinates[0], list):
        return None
    output: list[tuple[float, float]] = []
    for coordinate in coordinates[0]:
        if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
            return None
        lon = finite_number(coordinate[0])
        lat = finite_number(coordinate[1])
        if lon is None or lat is None:
            return None
        output.append((lon, lat))
    if len(output) >= 2 and output[0] == output[-1]:
        output.pop()
    return output if len(output) >= 3 else None


def local_xy_ring(
    ring: Sequence[tuple[float, float]], lat0: float, lon0: float
) -> list[tuple[float, float]]:
    """Projeção azimutal equidistante esférica local, implementada independentemente."""
    earth_radius_m = 6_371_008.8
    phi0 = math.radians(lat0)
    lam0 = math.radians(lon0)
    output: list[tuple[float, float]] = []
    for lon, lat in ring:
        phi = math.radians(lat)
        lam = math.radians(lon)
        delta = (lam - lam0 + math.pi) % (2.0 * math.pi) - math.pi
        cosine = max(
            -1.0,
            min(1.0, math.sin(phi0) * math.sin(phi) + math.cos(phi0) * math.cos(phi) * math.cos(delta)),
        )
        angular_distance = math.acos(cosine)
        scale = 1.0 if angular_distance <= 1e-15 else angular_distance / math.sin(angular_distance)
        x = earth_radius_m * scale * math.cos(phi) * math.sin(delta)
        y = earth_radius_m * scale * (
            math.cos(phi0) * math.sin(phi) - math.sin(phi0) * math.cos(phi) * math.cos(delta)
        )
        output.append((x, y))
    return output


def signed_area(points: Sequence[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    return 0.5 * sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(points, (*points[1:], points[0]))
    )


def polygon_area(points: Sequence[tuple[float, float]]) -> float:
    return abs(signed_area(points))


def cross(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def point_on_segment(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float], tolerance: float
) -> bool:
    length = math.dist(start, end)
    if length <= tolerance:
        return math.dist(point, start) <= tolerance
    if abs(cross(start, end, point)) / length > tolerance:
        return False
    return (
        min(start[0], end[0]) - tolerance <= point[0] <= max(start[0], end[0]) + tolerance
        and min(start[1], end[1]) - tolerance <= point[1] <= max(start[1], end[1]) + tolerance
    )


def point_location(
    point: tuple[float, float], polygon: Sequence[tuple[float, float]], tolerance: float
) -> int:
    """Retorna 1 no interior, 0 na fronteira e -1 no exterior."""
    for start, end in zip(polygon, (*polygon[1:], polygon[0])):
        if point_on_segment(point, start, end, tolerance):
            return 0
    inside = False
    px, py = point
    for (x1, y1), (x2, y2) in zip(polygon, (*polygon[1:], polygon[0])):
        if (y1 > py) != (y2 > py):
            crossing_x = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
            if crossing_x > px:
                inside = not inside
    return 1 if inside else -1


def proper_segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
    tolerance: float,
) -> bool:
    ab_c = cross(a, b, c)
    ab_d = cross(a, b, d)
    cd_a = cross(c, d, a)
    cd_b = cross(c, d, b)
    ab_tolerance = tolerance * max(math.dist(a, b), 1.0)
    cd_tolerance = tolerance * max(math.dist(c, d), 1.0)
    return (
        ((ab_c > ab_tolerance and ab_d < -ab_tolerance) or (ab_c < -ab_tolerance and ab_d > ab_tolerance))
        and ((cd_a > cd_tolerance and cd_b < -cd_tolerance) or (cd_a < -cd_tolerance and cd_b > cd_tolerance))
    )


def polygon_within_polygon(
    child: Sequence[tuple[float, float]], parent: Sequence[tuple[float, float]], tolerance: float
) -> bool:
    """Valida inclusão por vértices, pontos médios e cruzamentos próprios."""
    probes = list(child) + [
        ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        for a, b in zip(child, (*child[1:], child[0]))
    ]
    if any(point_location(point, parent, tolerance) < 0 for point in probes):
        return False
    for a, b in zip(child, (*child[1:], child[0])):
        for c, d in zip(parent, (*parent[1:], parent[0])):
            if proper_segments_intersect(a, b, c, d, tolerance):
                return False
    return True


def remove_collinear(
    points: Sequence[tuple[float, float]], tolerance: float = 1e-9
) -> list[tuple[float, float]]:
    output: list[tuple[float, float]] = []
    for point in points:
        if not output or math.dist(point, output[-1]) > tolerance:
            output.append(point)
    if len(output) > 1 and math.dist(output[0], output[-1]) <= tolerance:
        output.pop()
    changed = True
    while changed and len(output) > 3:
        changed = False
        kept: list[tuple[float, float]] = []
        for index, point in enumerate(output):
            previous = output[index - 1]
            following = output[(index + 1) % len(output)]
            if abs(cross(previous, point, following)) <= tolerance and point_on_segment(
                point, previous, following, tolerance
            ):
                changed = True
            else:
                kept.append(point)
        output = kept
    return output


def point_in_triangle(
    point: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    tolerance: float,
) -> bool:
    values = (cross(a, b, point), cross(b, c, point), cross(c, a, point))
    return min(values) >= -tolerance


def triangulate_polygon(points: Sequence[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """Triangula um polígono simples por corte de orelhas, sem bibliotecas externas."""
    polygon = remove_collinear(points)
    if len(polygon) < 3 or polygon_area(polygon) <= 1e-9:
        return []
    if signed_area(polygon) < 0:
        polygon.reverse()
    indices = list(range(len(polygon)))
    triangles: list[list[tuple[float, float]]] = []
    epsilon = max(1e-9, polygon_area(polygon) * 1e-14)
    guard = 0
    while len(indices) > 3 and guard < len(polygon) ** 2:
        guard += 1
        ear_found = False
        for position, current in enumerate(indices):
            previous = indices[position - 1]
            following = indices[(position + 1) % len(indices)]
            a, b, c = polygon[previous], polygon[current], polygon[following]
            if cross(a, b, c) <= epsilon:
                continue
            if any(
                point_in_triangle(polygon[other], a, b, c, epsilon)
                for other in indices
                if other not in {previous, current, following}
            ):
                continue
            triangles.append([a, b, c])
            del indices[position]
            ear_found = True
            break
        if not ear_found:
            return []
    if len(indices) == 3:
        triangles.append([polygon[index] for index in indices])
    return triangles


def line_intersection(
    start: tuple[float, float],
    end: tuple[float, float],
    clip_start: tuple[float, float],
    clip_end: tuple[float, float],
) -> tuple[float, float]:
    dx1, dy1 = end[0] - start[0], end[1] - start[1]
    dx2, dy2 = clip_end[0] - clip_start[0], clip_end[1] - clip_start[1]
    denominator = dx1 * dy2 - dy1 * dx2
    if abs(denominator) <= 1e-18:
        return end
    t = ((clip_start[0] - start[0]) * dy2 - (clip_start[1] - start[1]) * dx2) / denominator
    return start[0] + t * dx1, start[1] + t * dy1


def convex_clip(
    subject: Sequence[tuple[float, float]], clipper: Sequence[tuple[float, float]]
) -> list[tuple[float, float]]:
    output = list(subject)
    clip = list(clipper)
    if signed_area(clip) < 0:
        clip.reverse()
    for clip_start, clip_end in zip(clip, (*clip[1:], clip[0])):
        source = output
        output = []
        if not source:
            break
        previous = source[-1]
        previous_inside = cross(clip_start, clip_end, previous) >= -1e-9
        for current in source:
            current_inside = cross(clip_start, clip_end, current) >= -1e-9
            if current_inside:
                if not previous_inside:
                    output.append(line_intersection(previous, current, clip_start, clip_end))
                output.append(current)
            elif previous_inside:
                output.append(line_intersection(previous, current, clip_start, clip_end))
            previous, previous_inside = current, current_inside
    return output


def polygon_intersection_area(
    first_triangles: Sequence[Sequence[tuple[float, float]]],
    second_triangles: Sequence[Sequence[tuple[float, float]]],
) -> float:
    total = 0.0
    for first in first_triangles:
        first_min_x = min(point[0] for point in first)
        first_max_x = max(point[0] for point in first)
        first_min_y = min(point[1] for point in first)
        first_max_y = max(point[1] for point in first)
        for second in second_triangles:
            if (
                first_max_x < min(point[0] for point in second)
                or max(point[0] for point in second) < first_min_x
                or first_max_y < min(point[1] for point in second)
                or max(point[1] for point in second) < first_min_y
            ):
                continue
            total += polygon_area(convex_clip(first, second))
    return total


class Checks:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(
        self,
        check_id: str,
        description: str,
        passed: bool,
        detail: str,
        metrics: Mapping[str, Any] | None = None,
    ) -> None:
        item: dict[str, Any] = {
            "id": check_id,
            "description": description,
            "status": "PASS" if passed else "FAIL",
            "detail": detail,
        }
        if metrics:
            item["metrics"] = dict(metrics)
        self.items.append(item)

    def run(
        self,
        check_id: str,
        description: str,
        function: Callable[[], tuple[bool, str, Mapping[str, Any] | None]],
    ) -> None:
        try:
            passed, detail, metrics = function()
        except Exception as exc:  # relatório deve registrar a falha, não abortar silenciosamente
            self.add(check_id, description, False, f"Exceção durante a verificação: {type(exc).__name__}: {exc}")
        else:
            self.add(check_id, description, passed, detail, metrics)

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [item for item in self.items if item["status"] == "FAIL"]


def check_config(config: Mapping[str, Any]) -> tuple[bool, str, Mapping[str, Any]]:
    errors: list[str] = []
    geometry = config.get("geometry", {})
    ranking = config.get("ranking", {})
    firewall = config.get("ground_truth_firewall", {})
    weight_sets = config.get("scoring", {}).get("weight_sets", [])

    if config.get("protocol_id") != "EXT-ESP-SET-v1.1":
        errors.append(f"protocol_id={config.get('protocol_id')!r}, esperado 'EXT-ESP-SET-v1.1'")
    if geometry.get("rings") != 3:
        errors.append(f"geometry.rings={geometry.get('rings')!r}, esperado 3")
    if geometry.get("directions") != 8:
        errors.append(f"geometry.directions={geometry.get('directions')!r}, esperado 8")
    expected_per_buffer = int(geometry.get("rings", 0)) * int(geometry.get("directions", 0))
    if geometry.get("sectors_per_buffer") != expected_per_buffer or expected_per_buffer <= 0:
        errors.append("geometry.sectors_per_buffer não é 24")
    if geometry.get("authoritative_parent_geometry") != "INPUT_BUFFER_GEOJSON":
        errors.append("GeoJSON de buffer não está definido como geometria autoritativa")
    if geometry.get("outer_boundary_reused_exactly") is not True:
        errors.append("reuso exato da fronteira externa não está congelado")
    centers = geometry.get("direction_centers_deg")
    if not isinstance(centers, dict) or len(centers) != 8:
        errors.append("direction_centers_deg não contém oito direções")
    fractions = geometry.get("ring_boundaries_as_radius_fraction")
    if not isinstance(fractions, list) or len(fractions) != 4:
        errors.append("ring_boundaries_as_radius_fraction não contém quatro limites")
    if ranking.get("scope") != "WITHIN_CANDIDATE_BUFFER_ONLY":
        errors.append("ranking.scope não está restrito ao buffer do candidato")
    if ranking.get("rank_method") != "COMPETITION_RANK":
        errors.append("ranking.rank_method não é COMPETITION_RANK")
    if ranking.get("base_top_tie_policy") != "NO_SELECTION_AND_REVISAR":
        errors.append("política de empate BASE não impede seleção")
    if ranking.get("sensitivity_top_tie_policy") != "FRACTIONAL_SUPPORT_AND_EXPLICIT_FLAG":
        errors.append("política de empate de sensibilidade não usa suporte fracionário")
    for field in ("cross_candidate_ranking", "cross_buffer_ranking", "scenario_global_sector_ranking"):
        if ranking.get(field) is not False:
            errors.append(f"ranking.{field} deve ser false")
    if firewall.get("enabled") is not True:
        errors.append("firewall de ground truth não está habilitado")
    allowed = firewall.get("allowed_control_field", {})
    if allowed.get("field") != "ground_truth_used" or allowed.get("required_value") is not False:
        errors.append("controle ground_truth_used=false não está congelado")

    weight_names: list[str] = []
    for item in weight_sets if isinstance(weight_sets, list) else []:
        name = str(item.get("weight_set", ""))
        weight_names.append(name)
        total = sum(float(item.get(field, math.nan)) for field in SCORE_TO_WEIGHT.values())
        if not math.isfinite(total) or not math.isclose(total, 1.0, abs_tol=1e-12):
            errors.append(f"pesos de {name or '<sem nome>'} somam {total!r}")
    if "BASE" not in weight_names:
        errors.append("conjunto de pesos BASE ausente")

    return (
        not errors,
        "Contrato v1.1 confirma geometria autoritativa, 3 anéis × 8 direções, competition rank e ranking intrabuffer."
        if not errors
        else "; ".join(errors),
        {
            "protocol_id": config.get("protocol_id"),
            "rings": geometry.get("rings"),
            "directions": geometry.get("directions"),
            "sectors_per_buffer": geometry.get("sectors_per_buffer"),
            "rank_method": ranking.get("rank_method"),
            "weight_sets": weight_names,
        },
    )


def check_manifest_hashes(
    manifest: Mapping[str, Any],
    manifest_path: Path,
    buffer_path: Path,
    buffer_geojson_path: Path,
    config_path: Path,
    results_dir: Path,
) -> tuple[bool, str, Mapping[str, Any]]:
    errors: list[str] = []
    file_items = manifest.get("files")
    if not isinstance(file_items, list) or not file_items:
        return False, "Manifesto não contém lista de arquivos.", {"files_checked": 0}

    seen_paths: set[Path] = set()
    role_paths: defaultdict[str, list[Path]] = defaultdict(list)
    checked = 0
    for index, item in enumerate(file_items):
        if not isinstance(item, dict):
            errors.append(f"files[{index}] não é objeto")
            continue
        role = str(item.get("role", ""))
        path = resolve_manifest_path(item.get("path", ""), manifest_path)
        role_paths[role].append(path)
        if path in seen_paths:
            errors.append(f"arquivo repetido no manifesto: {path}")
        seen_paths.add(path)
        expected_hash = str(item.get("sha256", ""))
        expected_bytes = item.get("bytes")
        if len(expected_hash) != 64 or any(char not in "0123456789abcdef" for char in expected_hash.lower()):
            errors.append(f"SHA-256 inválido no manifesto: {path.name}")
            continue
        if not path.is_file():
            errors.append(f"arquivo do manifesto não existe: {path}")
            continue
        checked += 1
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            errors.append(f"hash divergente: {path.name}")
        if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int) or path.stat().st_size != expected_bytes:
            errors.append(f"tamanho divergente ou inválido: {path.name}")

    supplied_roles = {
        "input_buffer_json": buffer_path.resolve(),
        "input_buffer_geojson": buffer_geojson_path.resolve(),
        "config": config_path.resolve(),
    }
    for role, supplied in supplied_roles.items():
        matches = [path for path in role_paths.get(role, []) if path == supplied]
        if len(matches) != 1:
            errors.append(f"manifesto não vincula univocamente --{role.replace('_', '-')} ao arquivo fornecido")

    output_names = [path.name for path in role_paths.get("output", [])]
    if set(output_names) != MANIFEST_OUTPUTS or len(output_names) != len(MANIFEST_OUTPUTS):
        errors.append(
            "conjunto de outputs do manifesto diverge do contrato: "
            f"encontrado={sorted(output_names)} esperado={sorted(MANIFEST_OUTPUTS)}"
        )
    for name in MANIFEST_OUTPUTS:
        expected_path = (results_dir / name).resolve()
        if expected_path not in role_paths.get("output", []):
            errors.append(f"output não está vinculado ao diretório informado: {name}")

    return (
        not errors,
        f"Todos os {checked} arquivos registrados têm tamanho e SHA-256 íntegros."
        if not errors
        else "; ".join(sample(errors)),
        {"files_declared": len(file_items), "files_checked": checked, "output_files": len(output_names)},
    )


def check_scientific_hash(
    manifest: Mapping[str, Any], sector_rows: Sequence[Mapping[str, Any]]
) -> tuple[bool, str, Mapping[str, Any]]:
    projection = [
        {
            "sector_id": row.get("sector_id"),
            "score_base": row.get("score_base"),
            "rank_base_within_buffer": row.get("rank_base_within_buffer"),
            "decision_status": row.get("buffer_decision_status"),
            "selected_sector": row.get("selected_sector"),
            "top1_stability": row.get("top1_stability"),
        }
        for row in sector_rows
    ]
    actual = canonical_hash(projection)
    expected = str(manifest.get("scientific_projection_sha256", ""))
    passed = len(expected) == 64 and actual == expected
    return (
        passed,
        "Hash científico canônico coincide com o manifesto."
        if passed
        else f"Hash científico divergente: esperado={expected!r}, calculado={actual}",
        {"scientific_projection_sha256": actual},
    )


def check_scientific_bundle_hash(
    manifest: Mapping[str, Any], manifest_path: Path
) -> tuple[bool, str, Mapping[str, Any]]:
    output_items = [item for item in manifest.get("files", []) if isinstance(item, dict) and item.get("role") == "output"]
    declared = {
        resolve_manifest_path(item.get("path", ""), manifest_path).name: str(item.get("sha256", ""))
        for item in output_items
    }
    actual = canonical_hash(declared)
    expected = str(manifest.get("scientific_bundle_sha256", ""))
    passed = set(declared) == MANIFEST_OUTPUTS and len(expected) == 64 and actual == expected
    return (
        passed,
        "Hash canônico do conjunto dos seis outputs científicos coincide com o manifesto."
        if passed
        else f"Hash do conjunto divergente: esperado={expected!r}, calculado={actual}",
        {"scientific_bundle_sha256": actual, "output_count": len(declared)},
    )


def check_cardinalities(
    buffer_doc: Mapping[str, Any],
    config: Mapping[str, Any],
    result_doc: Mapping[str, Any],
    manifest: Mapping[str, Any],
    sector_rows: Sequence[Mapping[str, Any]],
    decision_rows: Sequence[Mapping[str, Any]],
    geojson: Mapping[str, Any],
    feature_csv_rows: Sequence[Mapping[str, Any]],
    ranking_csv_rows: Sequence[Mapping[str, Any]],
    decision_csv_rows: Sequence[Mapping[str, Any]],
) -> tuple[bool, str, Mapping[str, Any]]:
    errors: list[str] = []
    buffer_rows = buffer_doc.get("results")
    features = geojson.get("features")
    if not isinstance(buffer_rows, list):
        buffer_rows = []
        errors.append("buffer_doc.results não é lista")
    if not isinstance(features, list):
        features = []
        errors.append("GeoJSON.features não é lista")

    expected_buffer_count = len(buffer_rows)
    expected_per_buffer = integer_value(config.get("geometry", {}).get("sectors_per_buffer")) or 0
    expected_sector_count = expected_buffer_count * expected_per_buffer
    protocol_id = config.get("protocol_id")
    for label, document in (("result_doc", result_doc), ("manifest", manifest)):
        if document.get("protocol_id") != protocol_id:
            errors.append(f"{label}.protocol_id={document.get('protocol_id')!r}, esperado {protocol_id!r}")

    expected_values = {
        "buffer_doc.record_count": buffer_doc.get("record_count"),
        "len(buffer_doc.results)": len(buffer_rows),
        "result_doc.buffer_count": result_doc.get("buffer_count"),
        "manifest.buffer_count": manifest.get("buffer_count"),
        "result_doc.decision_count": len(decision_rows),
        "manifest.decision_count": manifest.get("decision_count"),
        "len(decision_csv)": len(decision_csv_rows),
    }
    for label, value in expected_values.items():
        if value != expected_buffer_count:
            errors.append(f"{label}={value!r}, esperado {expected_buffer_count}")

    sector_values = {
        "result_doc.sector_count": result_doc.get("sector_count"),
        "manifest.sector_count": manifest.get("sector_count"),
        "len(result_doc.results)": len(sector_rows),
        "len(GeoJSON.features)": len(features),
        "len(features_csv)": len(feature_csv_rows),
        "len(ranking_csv)": len(ranking_csv_rows),
    }
    for label, value in sector_values.items():
        if value != expected_sector_count:
            errors.append(f"{label}={value!r}, esperado {expected_sector_count}")

    for label, value in {
        "result_doc.sectors_per_buffer": result_doc.get("sectors_per_buffer"),
        "manifest.sectors_per_buffer": manifest.get("sectors_per_buffer"),
    }.items():
        if value != expected_per_buffer:
            errors.append(f"{label}={value!r}, esperado {expected_per_buffer}")

    return (
        not errors,
        f"Cardinalidades derivadas coerentes: {expected_buffer_count} buffers, "
        f"{expected_sector_count} setores e {expected_buffer_count} decisões."
        if not errors
        else "; ".join(sample(errors)),
        {
            "buffers": len(buffer_rows),
            "sectors": len(sector_rows),
            "decisions": len(decision_rows),
            "expected_buffers": expected_buffer_count,
            "expected_sectors": expected_sector_count,
            "sectors_per_buffer": expected_per_buffer,
        },
    )


def group_rows(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    grouped: defaultdict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[key_of(row)].append(row)
    return dict(grouped)


def check_partition_3x8(
    buffer_rows: Sequence[Mapping[str, Any]], sector_rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> tuple[bool, str, Mapping[str, Any]]:
    errors: list[str] = []
    grouped = group_rows(sector_rows)
    input_keys = [key_of(row) for row in buffer_rows]
    if len(input_keys) != len(set(input_keys)):
        errors.append("chaves (scenario_id, candidate_id) duplicadas no JSON de buffers")
    if set(grouped) != set(input_keys):
        missing = sorted(set(input_keys) - set(grouped))
        extra = sorted(set(grouped) - set(input_keys))
        errors.append(f"buffers sem correspondência: faltantes={sample(missing)}, extras={sample(extra)}")

    centers = config.get("geometry", {}).get("direction_centers_deg", {})
    direction_labels = list(centers) if isinstance(centers, dict) else []
    ring_count = integer_value(config.get("geometry", {}).get("rings")) or 0
    direction_count = integer_value(config.get("geometry", {}).get("directions")) or 0
    expected_per_buffer = ring_count * direction_count
    expected_pairs = {
        (ring, direction)
        for ring in range(1, ring_count + 1)
        for direction in range(1, direction_count + 1)
    }
    for key, rows in grouped.items():
        if len(rows) != expected_per_buffer:
            errors.append(f"{key} contém {len(rows)} setores")
            continue
        pairs = {(integer_value(row.get("ring_index")), integer_value(row.get("direction_index"))) for row in rows}
        if pairs != expected_pairs:
            errors.append(f"{key} não contém exatamente o produto cartesiano 3×8")
        for row in rows:
            ring = integer_value(row.get("ring_index"))
            direction = integer_value(row.get("direction_index"))
            if ring is None or direction is None or not (1 <= ring <= ring_count and 1 <= direction <= direction_count):
                continue
            expected_label = direction_labels[direction - 1] if len(direction_labels) == 8 else None
            if row.get("direction_label") != expected_label or row.get("direction") != expected_label:
                errors.append(f"rótulo direcional incoerente em {row.get('sector_id')}")
            if row.get("ring_id") != f"R{ring:02d}":
                errors.append(f"ring_id incoerente em {row.get('sector_id')}")
            if row.get("sector_index") != (ring - 1) * direction_count + direction:
                errors.append(f"sector_index incoerente em {row.get('sector_id')}")

    scenario_counts = Counter(key[0] for key in grouped)

    return (
        not errors,
        f"Cada um dos {len(input_keys)} buffers contém exatamente {ring_count} anéis × {direction_count} direções."
        if not errors
        else "; ".join(sample(errors)),
        {
            "buffer_groups": len(grouped),
            "scenarios": len(scenario_counts),
            "candidate_counts_by_scenario": dict(sorted(scenario_counts.items())),
            "sectors_per_group": expected_per_buffer,
        },
    )


def check_identifiers(
    sector_rows: Sequence[Mapping[str, Any]], geojson: Mapping[str, Any]
) -> tuple[bool, str, Mapping[str, Any]]:
    errors: list[str] = []
    sector_ids = [str(row.get("sector_id", "")) for row in sector_rows]
    if any(not value for value in sector_ids):
        errors.append("há sector_id vazio")
    duplicates = [value for value, count in Counter(sector_ids).items() if count > 1]
    if duplicates:
        errors.append(f"sector_id duplicado: {sample(sorted(duplicates))}")
    for row in sector_rows:
        ring = integer_value(row.get("ring_index"))
        if ring is None:
            continue
        expected = (
            f"{row.get('scenario_id')}::{row.get('candidate_id')}::"
            f"R{ring:02d}::{row.get('direction_label')}"
        )
        if row.get("sector_id") != expected:
            errors.append(f"ID fora do template: {row.get('sector_id')!r}, esperado {expected!r}")

    features = geojson.get("features", []) if isinstance(geojson.get("features"), list) else []
    feature_ids: list[str] = []
    for feature in features:
        if not isinstance(feature, dict):
            errors.append("feature GeoJSON não é objeto")
            continue
        feature_id = str(feature.get("id", ""))
        property_id = str((feature.get("properties") or {}).get("sector_id", ""))
        feature_ids.append(feature_id)
        if feature_id != property_id:
            errors.append(f"Feature.id difere de properties.sector_id: {feature_id!r}")
    if len(feature_ids) != len(set(feature_ids)):
        errors.append("IDs das feições GeoJSON não são únicos")
    if set(feature_ids) != set(sector_ids):
        errors.append("conjunto de IDs do GeoJSON diverge do JSON científico")

    return (
        not errors,
        f"Os {len(sector_ids)} IDs são únicos, seguem o template e coincidem no GeoJSON."
        if not errors
        else "; ".join(sample(errors)),
        {"unique_sector_ids": len(set(sector_ids)), "unique_feature_ids": len(set(feature_ids))},
    )


def check_authoritative_partition(
    buffer_rows: Sequence[Mapping[str, Any]],
    buffer_geojson: Mapping[str, Any],
    sector_rows: Sequence[Mapping[str, Any]],
    sector_geojson: Mapping[str, Any],
    config: Mapping[str, Any],
) -> tuple[bool, str, Mapping[str, Any]]:
    """Confere a partição contra o polígono efetivamente recebido, não contra πr²."""
    errors: list[str] = []
    geometry_config = config.get("geometry", {})
    area_tolerance = finite_number(geometry_config.get("area_equality_relative_tolerance")) or 0.01
    partition_tolerance = finite_number(
        geometry_config.get("partition_area_conservation_relative_tolerance")
    ) or 1e-6
    sectors_per_buffer = integer_value(geometry_config.get("sectors_per_buffer")) or 0
    boundaries = geometry_config.get("ring_boundaries_as_radius_fraction", [])
    buffer_by_key = {key_of(row): row for row in buffer_rows}
    sector_groups = group_rows(sector_rows)

    parent_features = buffer_geojson.get("features", [])
    parent_geometry_by_key: dict[tuple[str, str], Any] = {}
    if not isinstance(parent_features, list):
        return False, "buffer GeoJSON.features não é lista.", {"buffers_checked": 0}
    for feature in parent_features:
        if not isinstance(feature, Mapping):
            errors.append("feição do buffer GeoJSON não é objeto")
            continue
        properties = feature.get("properties") if isinstance(feature.get("properties"), Mapping) else {}
        key = (str(properties.get("scenario_id", "")), str(properties.get("candidate_id", "")))
        if key in parent_geometry_by_key:
            errors.append(f"geometria autoritativa duplicada: {key}")
        parent_geometry_by_key[key] = feature.get("geometry")

    sector_features = sector_geojson.get("features", [])
    sector_geometry_by_id: dict[str, Any] = {}
    if not isinstance(sector_features, list):
        return False, "sector GeoJSON.features não é lista.", {"buffers_checked": 0}
    for feature in sector_features:
        if isinstance(feature, Mapping):
            sector_geometry_by_id[str(feature.get("id", ""))] = feature.get("geometry")

    max_equal_area_error = 0.0
    max_partition_error = 0.0
    max_reported_area_delta = 0.0
    max_overlap_area = 0.0
    outside_sector_count = 0
    overlap_pair_count = 0
    uncovered_parent_edge_count = 0
    buffers_checked = 0
    for key, rows in sector_groups.items():
        parent_row = buffer_by_key.get(key)
        parent_ring_lonlat = polygon_ring(parent_geometry_by_key.get(key))
        if parent_row is None or parent_ring_lonlat is None:
            errors.append(f"buffer/GeoJSON autoritativo ausente ou inválido para {key}")
            continue
        lat0 = finite_number(parent_row.get("estimated_lat"))
        lon0 = finite_number(parent_row.get("estimated_lon"))
        radius = finite_number(parent_row.get("adaptive_radius_m"))
        if lat0 is None or lon0 is None or radius is None or radius <= 0:
            errors.append(f"centro/raio inválido no buffer {key}")
            continue
        parent_xy = local_xy_ring(parent_ring_lonlat, lat0, lon0)
        parent_area = polygon_area(parent_xy)
        if parent_area <= 0:
            errors.append(f"área autoritativa não positiva em {key}")
            continue
        buffers_checked += 1
        expected_sector_area = parent_area / sectors_per_buffer
        absolute_overlap_tolerance = max(parent_area * partition_tolerance, 1e-5)
        coordinate_tolerance = max(math.sqrt(parent_area) * 1e-6, 0.002)
        if point_location((0.0, 0.0), parent_xy, coordinate_tolerance) < 0:
            errors.append(f"centro do candidato está fora do buffer autoritativo em {key}")
        if geometry_config.get("parent_geometry_must_be_star_shaped_about_candidate") is True:
            boundary_probes = list(parent_xy) + [
                ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
                for a, b in zip(parent_xy, (*parent_xy[1:], parent_xy[0]))
            ]
            if any(
                point_location((probe[0] * fraction, probe[1] * fraction), parent_xy, coordinate_tolerance) < 0
                for probe in boundary_probes
                for fraction in (0.25, 0.5, 0.75)
            ):
                errors.append(f"buffer não é estrelado sobre o centro do candidato em {key}")
        sector_polygons: list[tuple[str, list[tuple[float, float]], list[list[tuple[float, float]]]]] = []
        measured_areas: list[float] = []
        for row in rows:
            sector_id = str(row.get("sector_id", ""))
            sector_ring_lonlat = polygon_ring(sector_geometry_by_id.get(sector_id))
            if sector_ring_lonlat is None:
                errors.append(f"geometria setorial ausente ou inválida: {sector_id}")
                continue
            sector_xy = local_xy_ring(sector_ring_lonlat, lat0, lon0)
            measured_area = polygon_area(sector_xy)
            measured_areas.append(measured_area)
            triangles = triangulate_polygon(sector_xy)
            if not triangles:
                errors.append(f"polígono setorial não pôde ser triangulado: {sector_id}")
            sector_polygons.append((sector_id, sector_xy, triangles))

            if not polygon_within_polygon(sector_xy, parent_xy, coordinate_tolerance):
                outside_sector_count += 1
                errors.append(f"setor não está contido no buffer autoritativo: {sector_id}")

            equality_error = relative_error(measured_area, expected_sector_area)
            max_equal_area_error = max(max_equal_area_error, equality_error)
            if equality_error > area_tolerance:
                errors.append(f"área efetiva fora da tolerância em {sector_id}: {equality_error:.6g}")

            reported_area = finite_number(row.get("sector_area_m2"))
            polygon_reported = finite_number(row.get("polygon_planar_area_m2"))
            parent_reported = finite_number(row.get("authoritative_buffer_planar_area_m2"))
            reported_error = finite_number(row.get("area_relative_error"))
            if reported_area is None or polygon_reported is None or parent_reported is None or reported_error is None:
                errors.append(f"metadados de área autoritativa ausentes em {sector_id}")
            else:
                deltas = (
                    relative_error(reported_area, measured_area),
                    relative_error(polygon_reported, measured_area),
                    relative_error(parent_reported, parent_area),
                    abs(reported_error - equality_error),
                )
                max_reported_area_delta = max(max_reported_area_delta, *deltas)
                if any(delta > max(partition_tolerance, 2e-8) for delta in deltas):
                    errors.append(f"metadados de área divergem da geometria em {sector_id}")
            if row.get("geometry_source") != "INPUT_BUFFER_GEOJSON":
                errors.append(f"geometry_source incoerente em {sector_id}")

            ring_index = integer_value(row.get("ring_index"))
            inner = finite_number(row.get("inner_radius_m"))
            outer = finite_number(row.get("outer_radius_m"))
            if ring_index is not None and isinstance(boundaries, list) and len(boundaries) > ring_index:
                expected_inner = radius * float(boundaries[ring_index - 1])
                expected_outer = radius * float(boundaries[ring_index])
                if inner is None or not math.isclose(inner, expected_inner, rel_tol=2e-6, abs_tol=2e-4):
                    errors.append(f"inner_radius_m incoerente em {sector_id}")
                if outer is None or not math.isclose(outer, expected_outer, rel_tol=2e-6, abs_tol=2e-4):
                    errors.append(f"outer_radius_m incoerente em {sector_id}")

        if measured_areas:
            partition_error = relative_error(sum(measured_areas), parent_area)
            max_partition_error = max(max_partition_error, partition_error)
            if partition_error > partition_tolerance:
                errors.append(f"soma das áreas diverge do buffer autoritativo {key}: {partition_error:.6g}")

        all_sector_edges = [
            (start, end)
            for _, polygon, _ in sector_polygons
            for start, end in zip(polygon, (*polygon[1:], polygon[0]))
        ]
        for parent_start, parent_end in zip(parent_xy, (*parent_xy[1:], parent_xy[0])):
            probes = [
                (
                    parent_start[0] + fraction * (parent_end[0] - parent_start[0]),
                    parent_start[1] + fraction * (parent_end[1] - parent_start[1]),
                )
                for fraction in (0.25, 0.5, 0.75)
            ]
            if not all(
                any(point_on_segment(probe, edge_start, edge_end, coordinate_tolerance) for edge_start, edge_end in all_sector_edges)
                for probe in probes
            ):
                uncovered_parent_edge_count += 1
                errors.append(f"fronteira externa autoritativa não foi reutilizada integralmente em {key}")
                break

        for first_index, (first_id, _, first_triangles) in enumerate(sector_polygons):
            if not first_triangles:
                continue
            for second_id, _, second_triangles in sector_polygons[first_index + 1 :]:
                if not second_triangles:
                    continue
                overlap = polygon_intersection_area(first_triangles, second_triangles)
                max_overlap_area = max(max_overlap_area, overlap)
                if overlap > absolute_overlap_tolerance:
                    overlap_pair_count += 1
                    errors.append(
                        f"sobreposição positiva em {key}: {first_id} × {second_id} = {overlap:.6g} m²"
                    )

    if set(parent_geometry_by_key) != set(buffer_by_key):
        errors.append("chaves do GeoJSON autoritativo divergem do JSON de buffers")

    return (
        not errors,
        "A soma, a contenção e a ausência de sobreposição dos setores coincidem com cada GeoJSON autoritativo."
        if not errors
        else "; ".join(sample(errors)),
        {
            "buffers_checked": buffers_checked,
            "area_equality_relative_tolerance": area_tolerance,
            "partition_relative_tolerance": partition_tolerance,
            "max_sector_equal_area_relative_error": round(max_equal_area_error, 12),
            "max_partition_relative_error": round(max_partition_error, 12),
            "max_reported_area_delta": round(max_reported_area_delta, 12),
            "max_pairwise_overlap_m2": round(max_overlap_area, 9),
            "outside_sector_count": outside_sector_count,
            "overlap_pair_count": overlap_pair_count,
            "uncovered_parent_edge_count": uncovered_parent_edge_count,
        },
    )


def check_geometries(geojson: Mapping[str, Any], config: Mapping[str, Any]) -> tuple[bool, str, Mapping[str, Any]]:
    errors: list[str] = []
    if geojson.get("type") != "FeatureCollection":
        errors.append("raiz GeoJSON não é FeatureCollection")
    features = geojson.get("features")
    if not isinstance(features, list):
        return False, "GeoJSON.features não é lista.", {"geometries_checked": 0}
    minimum_unique = int(config.get("geometry", {}).get("minimum_unique_vertices", 4))
    checked = 0
    min_vertices: int | None = None
    max_vertices = 0
    for feature in features:
        feature_id = feature.get("id") if isinstance(feature, dict) else None
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if not isinstance(geometry, dict) or geometry.get("type") != "Polygon":
            errors.append(f"geometria não é Polygon: {feature_id!r}")
            continue
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) != 1 or not isinstance(coordinates[0], list):
            errors.append(f"Polygon deve conter exatamente um anel: {feature_id!r}")
            continue
        ring = coordinates[0]
        checked += 1
        if len(ring) < minimum_unique + 1:
            errors.append(f"anel tem poucos vértices: {feature_id!r}")
            continue
        if ring[0] != ring[-1]:
            errors.append(f"anel não está fechado: {feature_id!r}")
        valid_points: list[tuple[float, float]] = []
        for coordinate in ring:
            if not isinstance(coordinate, list) or len(coordinate) < 2:
                errors.append(f"coordenada inválida: {feature_id!r}")
                continue
            lon = finite_number(coordinate[0])
            lat = finite_number(coordinate[1])
            if lon is None or lat is None or not (-180 <= lon <= 180) or not (-90 <= lat <= 90):
                errors.append(f"longitude/latitude inválida: {feature_id!r}")
                continue
            valid_points.append((lon, lat))
        unique_vertices = len(set(valid_points[:-1] if valid_points and valid_points[0] == valid_points[-1] else valid_points))
        if unique_vertices < minimum_unique:
            errors.append(f"menos de {minimum_unique} vértices únicos: {feature_id!r}")
        open_ring = valid_points[:-1] if valid_points and valid_points[0] == valid_points[-1] else valid_points
        edges = list(zip(open_ring, (*open_ring[1:], open_ring[0]))) if len(open_ring) >= 3 else []
        for first_index, (a, b) in enumerate(edges):
            for second_index, (c, d) in enumerate(edges[first_index + 1 :], start=first_index + 1):
                adjacent = second_index in {first_index, first_index + 1} or (
                    first_index == 0 and second_index == len(edges) - 1
                )
                if not adjacent and proper_segments_intersect(a, b, c, d, 1e-12):
                    errors.append(f"anel auto-intersectante: {feature_id!r}")
                    break
        min_vertices = unique_vertices if min_vertices is None else min(min_vertices, unique_vertices)
        max_vertices = max(max_vertices, unique_vertices)

    return (
        not errors,
        f"As {checked} geometrias são polígonos fechados, finitos e com vértices suficientes."
        if not errors
        else "; ".join(sample(errors)),
        {"geometries_checked": checked, "min_unique_vertices": min_vertices, "max_unique_vertices": max_vertices},
    )


def weight_sets_from_config(config: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    output: dict[str, dict[str, float]] = {}
    for item in config.get("scoring", {}).get("weight_sets", []):
        name = str(item.get("weight_set", ""))
        output[name] = {score: float(item[weight]) for score, weight in SCORE_TO_WEIGHT.items()}
    return output


def check_scores(
    sector_rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> tuple[bool, str, Mapping[str, Any]]:
    errors: list[str] = []
    weight_sets = weight_sets_from_config(config)
    required_completeness = float(config.get("missing_data_policy", {}).get("required_geo_completeness", 1.0))
    raster_fraction = float(config.get("feature_extraction", {}).get("minimum_valid_raster_sample_fraction", 1.0))
    configured_samples = integer_value(
        config.get("feature_extraction", {}).get("raster_sampling", {}).get("samples_per_sector")
    ) or 0
    observed_scores: list[float] = []
    observed_completeness: list[float] = []
    complete_count = 0
    incomplete_count = 0
    for row in sector_rows:
        sector_id = row.get("sector_id")
        valid_scores: dict[str, float] = {}
        for field in REQUIRED_SCORE_FIELDS:
            raw = row.get(field)
            number = finite_number(raw)
            if raw is None:
                continue
            if number is None or not 0.0 <= number <= 1.0:
                errors.append(f"{field} não nulo fora de [0,1] em {sector_id}")
            elif number is not None:
                valid_scores[field] = number
                observed_scores.append(number)
        completeness = finite_number(row.get("geo_completeness"))
        if completeness is None or not 0.0 <= completeness <= 1.0:
            errors.append(f"geo_completeness fora de [0,1] em {sector_id}")
            completeness = 0.0
        else:
            observed_completeness.append(completeness)

        modules_available = integer_value(row.get("modules_available"))
        missing_module_count = integer_value(row.get("missing_module_count"))
        expected_available = len(valid_scores)
        expected_missing = len(REQUIRED_SCORE_FIELDS) - expected_available
        if modules_available != expected_available or missing_module_count != expected_missing:
            errors.append(f"contagem de módulos incoerente em {sector_id}")
        expected_completeness = expected_available / len(REQUIRED_SCORE_FIELDS)
        if not math.isclose(completeness, expected_completeness, abs_tol=1e-9):
            errors.append(f"geo_completeness não coincide com módulos disponíveis em {sector_id}")
        expected_feature_status = (
            "DISPONIVEL" if expected_available == len(REQUIRED_SCORE_FIELDS) else "PARCIAL" if expected_available else "NAO_DISPONIVEL"
        )
        if row.get("feature_status") != expected_feature_status:
            errors.append(f"feature_status incoerente em {sector_id}: esperado {expected_feature_status}")
        complete = expected_missing == 0 and completeness >= required_completeness
        complete_count += int(complete)
        incomplete_count += int(not complete)

        for prefix, score_field in (
            ("terrain", "terrain_access_score"),
            ("worldcover", "landcover_access_score"),
        ):
            count = integer_value(row.get(f"{prefix}_sample_count"))
            expected_count = integer_value(row.get(f"{prefix}_expected_sample_count"))
            coverage = finite_number(row.get(f"{prefix}_sample_coverage"))
            if count is None or expected_count is None or coverage is None:
                errors.append(f"metadados de amostragem {prefix} ausentes em {sector_id}")
                continue
            if expected_count != configured_samples or not 0 <= count <= expected_count:
                errors.append(f"contagem de amostras {prefix} incoerente em {sector_id}")
            expected_coverage = count / expected_count if expected_count else 0.0
            if not math.isclose(coverage, expected_coverage, abs_tol=1e-9):
                errors.append(f"cobertura amostral {prefix} incoerente em {sector_id}")
            if coverage < raster_fraction and row.get(score_field) is not None:
                errors.append(f"{score_field} deve ser nulo com cobertura {prefix} insuficiente em {sector_id}")

        scores_by_set = row.get("scores_by_weight_set")
        contributions_by_set = row.get("contributions_by_weight_set")
        if not isinstance(scores_by_set, dict) or set(scores_by_set) != set(weight_sets):
            errors.append(f"scores_by_weight_set incompleto em {sector_id}")
            continue
        if not isinstance(contributions_by_set, dict) or set(contributions_by_set) != set(weight_sets):
            errors.append(f"contributions_by_weight_set incompleto em {sector_id}")
            continue
        for name, weights in weight_sets.items():
            contributions = contributions_by_set.get(name)
            if not isinstance(contributions, dict) or set(contributions) != set(SCORE_TO_MODULE.values()):
                errors.append(f"contribuições {name} incompletas em {sector_id}")
                continue
            score_raw = scores_by_set.get(name)
            score = finite_number(score_raw)
            if not complete:
                if score_raw is not None:
                    errors.append(f"escore {name} deve ser nulo no setor incompleto {sector_id}")
                for field, module in SCORE_TO_MODULE.items():
                    expected_contribution = (
                        valid_scores[field] * weights[field] if field in valid_scores else None
                    )
                    contribution = contributions.get(module)
                    if expected_contribution is None:
                        if contribution is not None:
                            errors.append(f"contribuição {name}/{module} deve ser nula em {sector_id}")
                    elif not close_number(contribution, expected_contribution):
                        errors.append(f"contribuição {name}/{module} incoerente em {sector_id}")
                continue

            expected = sum(valid_scores[field] * weights[field] for field in REQUIRED_SCORE_FIELDS)
            if score is None or not 0.0 <= score <= 1.0 or not math.isclose(score, expected, abs_tol=2e-8):
                errors.append(f"escore {name} incoerente em {sector_id}")
            else:
                contribution_sum = 0.0
                for field, module in SCORE_TO_MODULE.items():
                    value = finite_number(contributions.get(module))
                    expected_contribution = valid_scores[field] * weights[field]
                    if value is None or not math.isclose(value, expected_contribution, abs_tol=2e-8):
                        errors.append(f"contribuição {name}/{module} incoerente em {sector_id}")
                        break
                    contribution_sum += value
                if score is not None and not math.isclose(contribution_sum, score, abs_tol=3e-8):
                    errors.append(f"soma das contribuições {name} diverge do escore em {sector_id}")

        base_score = scores_by_set.get("BASE")
        if base_score is None:
            if row.get("priority_score") is not None or row.get("score_base") is not None:
                errors.append(f"aliases do escore BASE devem ser nulos em {sector_id}")
        elif not close_number(row.get("priority_score"), base_score) or not close_number(
            row.get("score_base"), base_score
        ):
            errors.append(f"aliases do escore BASE incoerentes em {sector_id}")

    return (
        not errors,
        "Escores disponíveis estão em [0,1]; setores incompletos permanecem com escore nulo e sem renormalização."
        if not errors
        else "; ".join(sample(errors)),
        {
            "sectors_complete": complete_count,
            "sectors_incomplete": incomplete_count,
            "required_completeness": required_completeness,
            "minimum_score": round(min(observed_scores), 9) if observed_scores else None,
            "maximum_score": round(max(observed_scores), 9) if observed_scores else None,
            "minimum_geo_completeness": round(min(observed_completeness), 9) if observed_completeness else None,
        },
    )


def check_ranks(
    sector_rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> tuple[bool, str, Mapping[str, Any]]:
    errors: list[str] = []
    grouped = group_rows(sector_rows)
    weight_names = list(weight_sets_from_config(config))
    decimals = integer_value(config.get("ranking", {}).get("score_comparison_decimals")) or 9
    ranking_sets_checked = 0
    ties_found = 0
    incomplete_sector_count = 0
    for key, rows in grouped.items():
        for row in rows:
            ranks = row.get("ranks_by_weight_set")
            if not isinstance(ranks, Mapping) or set(ranks) != set(weight_names):
                errors.append(f"ranks_by_weight_set incompleto em {row.get('sector_id')}")
        for weight_name in weight_names:
            scored: list[tuple[Mapping[str, Any], float]] = []
            for row in rows:
                scores = row.get("scores_by_weight_set")
                score = finite_number(scores.get(weight_name)) if isinstance(scores, Mapping) else None
                ranks = row.get("ranks_by_weight_set")
                rank = integer_value(ranks.get(weight_name)) if isinstance(ranks, dict) else None
                if score is None:
                    if rank is not None:
                        errors.append(f"rank {weight_name} deve ser nulo sem escore em {row.get('sector_id')}")
                    continue
                scored.append((row, round(score, decimals)))
            ranking_sets_checked += 1
            top_size = sum(1 for _, score in scored if scored and score == max(value for _, value in scored))
            ties_found += int(top_size > 1)
            for row, score in scored:
                expected_rank = 1 + sum(1 for _, other in scored if other > score)
                actual_rank = integer_value(row.get("ranks_by_weight_set", {}).get(weight_name))
                if actual_rank != expected_rank:
                    errors.append(
                        f"competition rank {weight_name} incoerente em {row.get('sector_id')}: "
                        f"esperado {expected_rank}, obtido {actual_rank}"
                    )

        for row in rows:
            ranks = row.get("ranks_by_weight_set", {})
            base_rank = ranks.get("BASE") if isinstance(ranks, Mapping) else None
            if row.get("sector_rank") != base_rank or row.get("rank_base_within_buffer") != base_rank:
                errors.append(f"rank BASE incoerente em {row.get('sector_id')}")
            if row.get("score_base") is None:
                incomplete_sector_count += 1
                if base_rank is not None:
                    errors.append(f"setor sem score BASE recebeu rank em {row.get('sector_id')}")

    return (
        not errors,
        "Os ranks de competição foram recalculados por buffer; empates compartilham rank e setores sem escore ficam sem rank."
        if not errors
        else "; ".join(sample(errors)),
        {
            "buffer_groups": len(grouped),
            "weight_sets": len(weight_names),
            "ranking_sets_checked": ranking_sets_checked,
            "top_ties_found": ties_found,
            "incomplete_sectors": incomplete_sector_count,
            "score_comparison_decimals": decimals,
        },
    )


def check_decisions(
    sector_rows: Sequence[Mapping[str, Any]],
    decision_rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> tuple[bool, str, Mapping[str, Any]]:
    errors: list[str] = []
    grouped = group_rows(sector_rows)
    decisions_by_key: defaultdict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for decision in decision_rows:
        decisions_by_key[key_of(decision)].append(decision)
    low_margin = float(config.get("ranking", {}).get("low_margin_threshold", 0.05))
    stability_threshold = float(config.get("ranking", {}).get("robust_stability_threshold", 0.8))
    minimum_unique_wins = int(config.get("ranking", {}).get("robust_stability_minimum_top1_wins", 4))
    required_completeness = float(config.get("missing_data_policy", {}).get("required_geo_completeness", 1.0))
    decimals = int(config.get("ranking", {}).get("score_comparison_decimals", 9))
    weight_names = list(weight_sets_from_config(config))
    selected_total = 0
    prioritized = 0
    review = 0
    base_ties = 0
    sensitivity_ties = 0

    for key, rows in grouped.items():
        top_by_set: dict[str, list[str]] = {}
        for name in weight_names:
            scored = [
                (row, round(float(row["scores_by_weight_set"][name]), decimals))
                for row in rows
                if isinstance(row.get("scores_by_weight_set"), Mapping)
                and finite_number(row["scores_by_weight_set"].get(name)) is not None
            ]
            if scored:
                maximum = max(score for _, score in scored)
                top_by_set[name] = sorted(str(row["sector_id"]) for row, score in scored if score == maximum)
            else:
                top_by_set[name] = []

        base_top_ids = top_by_set.get("BASE", [])
        unique_base = len(base_top_ids) == 1
        winner_id = base_top_ids[0] if unique_base else None
        winner = next((row for row in rows if str(row.get("sector_id")) == winner_id), None)
        selected = [row for row in rows if row.get("selected_sector") is True]
        selected_total += len(selected)
        expected_selected = 1 if unique_base else 0
        if len(selected) != expected_selected:
            errors.append(f"{key} tem {len(selected)} setores selecionados, esperado {expected_selected}")
        if unique_base and (winner is None or winner.get("sector_rank") != 1):
            errors.append(f"setor selecionável não é Top-1 BASE em {key}")
        if unique_base and selected and selected[0].get("sector_id") != winner_id:
            errors.append(f"setor selecionado diverge do Top-1 BASE único em {key}")

        base_scored = sorted(
            [
                round(float(row["score_base"]), decimals)
                for row in rows
                if finite_number(row.get("score_base")) is not None
            ],
            reverse=True,
        )
        margin = (
            base_scored[0] - base_scored[1]
            if len(base_scored) >= 2
            else (base_scored[0] if len(base_scored) == 1 else None)
        )

        support_points: defaultdict[str, float] = defaultdict(float)
        membership_counts: Counter[str] = Counter()
        unique_win_counts: Counter[str] = Counter()
        tied_sets = [name for name, ids in top_by_set.items() if len(ids) > 1]
        for ids in top_by_set.values():
            if not ids:
                continue
            share = 1.0 / len(ids)
            for sector_id in ids:
                support_points[sector_id] += share
                membership_counts[sector_id] += 1
            if len(ids) == 1:
                unique_win_counts[ids[0]] += 1
        stability_by_id = {
            str(row.get("sector_id")): support_points[str(row.get("sector_id"))] / len(weight_names)
            for row in rows
        }
        winner_stability = stability_by_id.get(winner_id, 0.0) if winner_id else None
        winner_unique_wins = unique_win_counts.get(winner_id, 0) if winner_id else 0

        group_warnings: list[str] = []
        blocking_warnings: list[str] = []
        def add_warning(code: str, *, blocking: bool = True) -> None:
            if code not in group_warnings:
                group_warnings.append(code)
            if blocking and code not in blocking_warnings:
                blocking_warnings.append(code)

        if any(str(row.get("upstream_review_status", row.get("source_buffer_review_status", ""))) == "REVISAR" for row in rows):
            add_warning("UPSTREAM_REVIEW_REQUIRED")
        if any(
            int(row.get("missing_module_count", 0)) > 0
            or float(row.get("geo_completeness", 0.0)) < required_completeness
            for row in rows
        ):
            add_warning("INCOMPLETE_GEO")
        if not base_scored:
            add_warning("NO_COMPLETE_SECTOR")
        elif margin is not None and margin < low_margin:
            add_warning("LOW_MARGIN")
        if len(base_top_ids) > 1:
            base_ties += 1
            add_warning("BASE_TOP_TIE")
            add_warning("NO_UNIQUE_TOP1")
        elif not unique_base and base_scored:
            add_warning("NO_UNIQUE_TOP1")
        if any(name != "BASE" for name in tied_sets):
            sensitivity_ties += 1
            add_warning("SENSITIVITY_TOP_TIE", blocking=False)
        if unique_base and (
            winner_stability is None
            or winner_stability < stability_threshold
            or winner_unique_wins < minimum_unique_wins
        ):
            add_warning("RANKING_UNSTABLE")
        if winner is not None and str(winner.get("barrier_flags", "NAO_SINALIZADA")) != "NAO_SINALIZADA":
            add_warning("POTENTIAL_BARRIER")
        if any(not str(row.get("source_provenance", "")).strip() for row in rows):
            add_warning("MISSING_SOURCE_PROVENANCE")
        expected_status = "REVISAR" if blocking_warnings else "PRIORIZADO"
        if expected_status == "PRIORIZADO":
            prioritized += 1
        else:
            review += 1

        for row in rows:
            sector_id = row.get("sector_id")
            if margin is None:
                if row.get("rank_margin") is not None or row.get("buffer_base_margin") is not None:
                    errors.append(f"margem deve ser nula em {sector_id}")
            elif not close_number(row.get("rank_margin"), margin) or not close_number(
                row.get("buffer_base_margin"), margin
            ):
                errors.append(f"margem incoerente em {sector_id}")
            expected_membership = membership_counts[str(sector_id)]
            expected_unique_wins = unique_win_counts[str(sector_id)]
            expected_support = support_points[str(sector_id)]
            if row.get("top1_count") != expected_membership:
                errors.append(f"top1_count incoerente em {sector_id}")
            if row.get("top1_membership_count") != expected_membership:
                errors.append(f"top1_membership_count incoerente em {sector_id}")
            if row.get("top1_unique_win_count") != expected_unique_wins:
                errors.append(f"top1_unique_win_count incoerente em {sector_id}")
            if not close_number(row.get("top1_support_points"), expected_support):
                errors.append(f"top1_support_points incoerente em {sector_id}")
            if not close_number(row.get("top1_stability"), stability_by_id[str(sector_id)]):
                errors.append(f"top1_stability incoerente em {sector_id}")
            if row.get("decision_status") != expected_status or row.get("buffer_decision_status") != expected_status:
                errors.append(f"status incoerente em {sector_id}: esperado {expected_status}")
            row_warnings = list(group_warnings)
            missing = int(row.get("missing_module_count", 0)) > 0 or float(row.get("geo_completeness", 0.0)) < required_completeness
            if missing and "MISSING_REQUIRED_GEO_SCORE" not in row_warnings:
                row_warnings.append("MISSING_REQUIRED_GEO_SCORE")
            if set(codes(row.get("warning_codes"))) != set(row_warnings):
                errors.append(f"warning_codes incoerente em {sector_id}")
            if set(codes(row.get("buffer_warning_codes"))) != set(group_warnings):
                errors.append(f"buffer_warning_codes incoerente em {sector_id}")
            if row.get("supervision_required") is not True:
                errors.append(f"supervisão humana não exigida em {sector_id}")
            tied_declared = row.get("weight_sets_with_top_tie")
            if isinstance(tied_declared, int):
                if tied_declared != len(tied_sets):
                    errors.append(f"weight_sets_with_top_tie incoerente em {sector_id}")
            elif isinstance(tied_declared, list):
                if sorted(map(str, tied_declared)) != sorted(tied_sets):
                    errors.append(f"weight_sets_with_top_tie incoerente em {sector_id}")
            else:
                errors.append(f"weight_sets_with_top_tie ausente/inválido em {sector_id}")
            if row.get("top1_by_weight_set") != top_by_set:
                errors.append(f"top1_by_weight_set da linha incoerente em {sector_id}")

        decision_matches = decisions_by_key.get(key, [])
        if len(decision_matches) != 1:
            errors.append(f"{key} tem {len(decision_matches)} decisões, esperado 1")
            continue
        decision = decision_matches[0]
        if decision.get("top1_sector_id") != winner_id:
            errors.append(f"top1_sector_id da decisão diverge em {key}")
        if decision.get("top1_unique") is not unique_base:
            errors.append(f"top1_unique da decisão diverge em {key}")
        if unique_base:
            if not close_number(decision.get("top1_score_base"), winner.get("score_base") if winner else None):
                errors.append(f"top1_score_base da decisão diverge em {key}")
            if not close_number(decision.get("base_margin"), margin):
                errors.append(f"base_margin da decisão diverge em {key}")
            if not close_number(decision.get("top1_stability"), winner_stability):
                errors.append(f"top1_stability da decisão diverge em {key}")
            if decision.get("top1_unique_win_count") != winner_unique_wins:
                errors.append(f"top1_unique_win_count da decisão diverge em {key}")
        else:
            for field in ("top1_score_base", "base_margin", "top1_stability"):
                if decision.get(field) is not None:
                    errors.append(f"{field} deve ser nulo sem Top-1 único em {key}")
            if decision.get("top1_unique_win_count") != 0:
                errors.append(f"top1_unique_win_count deve ser zero sem Top-1 único em {key}")
            if decision.get("top1_membership_count") != 0:
                errors.append(f"top1_membership_count deve ser zero sem Top-1 único em {key}")
            if not close_number(decision.get("top1_support_points"), 0.0):
                errors.append(f"top1_support_points deve ser zero sem Top-1 único em {key}")
        if decision.get("decision_status") != expected_status or set(codes(decision.get("warning_codes"))) != set(
            group_warnings
        ):
            errors.append(f"status/alertas da decisão incoerentes em {key}")
        try:
            declared_top_by_set = json.loads(str(decision.get("top1_by_weight_set", "")))
        except json.JSONDecodeError:
            declared_top_by_set = None
        if declared_top_by_set != top_by_set:
            errors.append(f"top1_by_weight_set incoerente em {key}")
        try:
            declared_tied_sets = json.loads(str(decision.get("weight_sets_with_top_tie", "")))
        except json.JSONDecodeError:
            declared_tied_sets = None
        expected_tied_order = sorted(name for name in tied_sets if name != "BASE") + (
            ["BASE"] if "BASE" in tied_sets else []
        )
        if declared_tied_sets != expected_tied_order:
            errors.append(f"weight_sets_with_top_tie da decisão incoerente em {key}")
        try:
            declared_base_ids = json.loads(str(decision.get("top1_sector_ids_base", "")))
        except json.JSONDecodeError:
            declared_base_ids = None
        if declared_base_ids != base_top_ids:
            errors.append(f"top1_sector_ids_base incoerente em {key}")
        if decision.get("confirmatory_eligible") is not False or decision.get("supervision_required") is not True:
            errors.append(f"guardrails da decisão incoerentes em {key}")

    if set(decisions_by_key) != set(grouped):
        errors.append("chaves das decisões divergem das chaves dos buffers setorizados")

    return (
        not errors,
        "Seleção, empates, margem, suporte fracionário, vitórias únicas, alertas e decisões são coerentes."
        if not errors
        else "; ".join(sample(errors)),
        {
            "selected_sectors": selected_total,
            "decisions_prioritized": prioritized,
            "decisions_review": review,
            "low_margin_threshold": low_margin,
            "stability_threshold": stability_threshold,
            "minimum_unique_wins": minimum_unique_wins,
            "base_top_ties": base_ties,
            "buffers_with_sensitivity_ties": sensitivity_ties,
        },
    )


def check_cross_output_consistency(
    sector_rows: Sequence[Mapping[str, Any]],
    decision_rows: Sequence[Mapping[str, Any]],
    geojson: Mapping[str, Any],
    feature_csv_rows: Sequence[Mapping[str, str]],
    ranking_csv_rows: Sequence[Mapping[str, str]],
    decision_csv_rows: Sequence[Mapping[str, str]],
) -> tuple[bool, str, Mapping[str, Any]]:
    errors: list[str] = []
    json_by_id = {str(row.get("sector_id")): row for row in sector_rows}
    feature_by_id = {row.get("sector_id", ""): row for row in feature_csv_rows}
    ranking_by_id = {row.get("sector_id", ""): row for row in ranking_csv_rows}
    features = geojson.get("features", []) if isinstance(geojson.get("features"), list) else []
    geo_by_id = {str(feature.get("id")): feature for feature in features if isinstance(feature, dict)}
    expected_ids = set(json_by_id)
    for label, mapping in (("features CSV", feature_by_id), ("ranking CSV", ranking_by_id), ("GeoJSON", geo_by_id)):
        if len(mapping) != len(expected_ids) or set(mapping) != expected_ids:
            errors.append(f"IDs de {label} divergem do JSON científico")

    for sector_id, source in json_by_id.items():
        ranking = ranking_by_id.get(sector_id)
        feature = feature_by_id.get(sector_id)
        geo_feature = geo_by_id.get(sector_id)
        if ranking:
            raw_rank = ranking.get("rank_base_within_buffer", "")
            try:
                csv_rank = None if raw_rank == "" else int(raw_rank)
            except (TypeError, ValueError):
                csv_rank = "INVALID"
            if csv_rank != source.get("rank_base_within_buffer") or not optional_number_equal(
                ranking.get("score_base", ""), source.get("score_base")
            ):
                errors.append(f"ranking CSV diverge do JSON: {sector_id}")
            if bool_from_csv(ranking.get("selected_sector", "")) is not source.get("selected_sector"):
                errors.append(f"selected_sector diverge no ranking CSV: {sector_id}")
        if feature:
            try:
                csv_area = float(feature.get("sector_area_m2", ""))
            except (TypeError, ValueError):
                errors.append(f"área inválida no features CSV: {sector_id}")
            else:
                if not close_number(csv_area, source.get("sector_area_m2")):
                    errors.append(f"features CSV diverge do JSON: {sector_id}")
        if geo_feature:
            properties = geo_feature.get("properties", {})
            if not optional_number_equal(properties.get("score_base"), source.get("score_base")):
                errors.append(f"score GeoJSON diverge do JSON: {sector_id}")
            if properties.get("rank_base_within_buffer") != source.get("rank_base_within_buffer"):
                errors.append(f"rank GeoJSON diverge do JSON: {sector_id}")

    json_decisions = {key_of(row): row for row in decision_rows}
    csv_decisions = {key_of(row): row for row in decision_csv_rows}
    if len(csv_decisions) != len(decision_csv_rows) or set(csv_decisions) != set(json_decisions):
        errors.append("chaves do CSV de decisões divergem do JSON")
    else:
        for key, source in json_decisions.items():
            target = csv_decisions[key]
            csv_top = target.get("top1_sector_id") or None
            if csv_top != source.get("top1_sector_id"):
                errors.append(f"Top-1 diverge no CSV de decisões: {key}")
            if target.get("decision_status") != source.get("decision_status"):
                errors.append(f"status diverge no CSV de decisões: {key}")
            if not optional_number_equal(target.get("base_margin", ""), source.get("base_margin")):
                errors.append(f"margem diverge no CSV de decisões: {key}")

    return (
        not errors,
        "JSON, GeoJSON e três CSVs têm as mesmas chaves e valores científicos essenciais."
        if not errors
        else "; ".join(sample(errors)),
        {"sector_ids_compared": len(expected_ids), "decision_keys_compared": len(json_decisions)},
    )


def walk_json(value: Any, path: str = "$") -> Iterable[tuple[str, str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield child_path, str(key), child
            yield from walk_json(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_json(child, f"{path}[{index}]")


def check_ground_truth_firewall(
    config: Mapping[str, Any],
    json_documents: Sequence[tuple[str, Any]],
    csv_documents: Sequence[tuple[str, Sequence[str], Sequence[Mapping[str, str]]]],
    warnings_text: str,
    input_load_errors: Sequence[str] = (),
) -> tuple[bool, str, Mapping[str, Any]]:
    firewall = config.get("ground_truth_firewall", {})
    configured = firewall.get("forbidden_columns_or_fragments", [])
    forbidden = DEFAULT_GT_FRAGMENTS | {normalize_key(value) for value in configured}
    violations: list[str] = list(input_load_errors)
    control_fields = 0

    if firewall.get("enabled") is not True:
        violations.append("firewall desabilitado na configuração")
    if firewall.get("match_mode") != "NORMALIZED_KEY_SUBSTRING":
        violations.append("match_mode do firewall não é NORMALIZED_KEY_SUBSTRING")
    if firewall.get("case_insensitive") is not True or firewall.get("recursive") is not True:
        violations.append("firewall não está configurado como recursivo/case-insensitive")

    for label, document in json_documents:
        for path, key, value in walk_json(document):
            normalized = normalize_key(key)
            if normalized == "ground_truth_used":
                control_fields += 1
                if value is not False:
                    violations.append(f"{label}:{path} deve ser booleano false")
                continue
            if any(fragment in normalized for fragment in forbidden):
                violations.append(f"{label}:{path} contém campo proibido")

    for label, headers, rows in csv_documents:
        for header in headers:
            normalized = normalize_key(header)
            if normalized == "ground_truth_used":
                control_fields += 1
                bad = [index + 2 for index, row in enumerate(rows) if row.get(header, "").strip().lower() != "false"]
                if bad:
                    violations.append(f"{label}:{header} não é false nas linhas {sample(bad)}")
                continue
            if any(fragment in normalized for fragment in forbidden):
                violations.append(f"{label}:{header} é campo proibido")

    lowered_log = warnings_text.lower()
    for fragment in forbidden:
        if fragment in lowered_log:
            violations.append(f"warnings_dev.log contém fragmento proibido {fragment!r}")

    return (
        not violations,
        "Nenhum campo de referência real aparece; todo ground_truth_used é booleano false."
        if not violations
        else "; ".join(sample(violations)),
        {
            "forbidden_fragments": len(forbidden),
            "ground_truth_control_fields_checked": control_fields,
            "json_documents_checked": len(json_documents),
            "csv_documents_checked": len(csv_documents),
            "external_input_load_errors": len(input_load_errors),
        },
    )


def load_firewall_input_documents(
    manifest: Mapping[str, Any], manifest_path: Path
) -> tuple[list[tuple[str, Any]], list[str]]:
    """Carrega recursivamente entradas JSON/GeoJSON declaradas no manifesto."""
    documents: list[tuple[str, Any]] = []
    errors: list[str] = []
    skip_roles = {"output", "config", "engine", "input_buffer_json", "input_buffer_geojson"}
    for item in manifest.get("files", []):
        if not isinstance(item, Mapping) or str(item.get("role", "")) in skip_roles:
            continue
        path = resolve_manifest_path(item.get("path", ""), manifest_path)
        if path.suffix.lower() not in {".json", ".geojson"}:
            continue
        if not path.is_file():
            errors.append(f"entrada declarada para firewall não existe: {path}")
            continue
        try:
            document = load_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"não foi possível ler entrada do firewall {path.name}: {type(exc).__name__}: {exc}")
            continue
        documents.append((f"input:{item.get('role')}:{path.name}", document))
    return documents, errors


def check_no_cross_buffer_ranking(
    result_doc: Mapping[str, Any], sector_rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> tuple[bool, str, Mapping[str, Any]]:
    errors: list[str] = []
    ranking_config = config.get("ranking", {})
    if result_doc.get("ranking_scope") != "WITHIN_BUFFER_ONLY":
        errors.append(f"ranking_scope={result_doc.get('ranking_scope')!r}")
    if result_doc.get("ranking_grain") != "scenario_id+candidate_id+sector_id":
        errors.append(f"ranking_grain={result_doc.get('ranking_grain')!r}")
    if ranking_config.get("scope") != "WITHIN_CANDIDATE_BUFFER_ONLY":
        errors.append("escopo da configuração não é intrabuffer")
    for field in ("cross_candidate_ranking", "cross_buffer_ranking", "scenario_global_sector_ranking"):
        if ranking_config.get(field) is not False:
            errors.append(f"{field} não está false")

    unexpected: set[str] = set()
    for _, key, _ in walk_json(result_doc):
        normalized = str(key).lower()
        if normalized in CROSS_BUFFER_RANK_FIELDS or any(
            token in normalized for token in ("global_sector_rank", "rank_across_buffer")
        ):
            unexpected.add(str(key))
    if unexpected:
        errors.append(f"campos de ranking cross-buffer encontrados: {sorted(unexpected)}")

    grouped = group_rows(sector_rows)
    for key, rows in grouped.items():
        scored = [row for row in rows if finite_number(row.get("score_base")) is not None]
        if scored and not any(integer_value(row.get("rank_base_within_buffer")) == 1 for row in scored):
            errors.append(f"rank intrabuffer não reinicia em 1 no buffer {key}")
        if any(
            integer_value(row.get("rank_base_within_buffer")) is not None
            for row in rows
            if finite_number(row.get("score_base")) is None
        ):
            errors.append(f"setor sem escore recebeu rank no buffer {key}")

    return (
        not errors,
        "O ranking é estritamente intrabuffer e não há campo de ordenação entre buffers/candidatos."
        if not errors
        else "; ".join(sample(errors)),
        {"buffer_groups_checked": len(grouped), "unexpected_cross_buffer_fields": sorted(unexpected)},
    )


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def build_report(
    checks: Checks,
    *,
    results_dir: Path,
    buffer_path: Path,
    buffer_geojson_path: Path,
    config_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    passed = len(checks.items) - len(checks.failed)
    return {
        "verifier_id": VERIFIER_ID,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "PASS" if not checks.failed else "FAIL",
        "inputs": {
            "results_dir": str(results_dir),
            "buffer_json": str(buffer_path),
            "buffer_geojson": str(buffer_geojson_path),
            "config": str(config_path),
            "report": str(report_path),
        },
        "summary": {
            "checks_total": len(checks.items),
            "checks_passed": passed,
            "checks_failed": len(checks.failed),
            "exit_code": 0 if not checks.failed else 1,
        },
        "checks": checks.items,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", required=True, type=Path, help="Diretório com as saídas DEV-S")
    parser.add_argument("--buffer-json", required=True, type=Path, help="buffer_results_dev.json usado pelo motor")
    parser.add_argument(
        "--buffer-geojson", required=True, type=Path, help="buffer_polygons_dev.geojson autoritativo usado pelo motor"
    )
    parser.add_argument("--config", required=True, type=Path, help="Configuração congelada da setorização")
    parser.add_argument("--report", required=True, type=Path, help="Caminho do relatório JSON de verificação")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results_dir = args.results_dir.expanduser().resolve()
    buffer_path = args.buffer_json.expanduser().resolve()
    buffer_geojson_path = args.buffer_geojson.expanduser().resolve()
    config_path = args.config.expanduser().resolve()
    report_path = args.report.expanduser().resolve()
    paths = {name: (results_dir / filename).resolve() for name, filename in RESULT_FILES.items()}

    protected = set(paths.values()) | {buffer_path, buffer_geojson_path, config_path}
    if report_path in protected:
        print("ERRO: --report não pode sobrescrever uma entrada ou saída científica.", file=sys.stderr)
        return 1

    checks = Checks()
    missing = [str(path) for path in [buffer_path, buffer_geojson_path, config_path, *paths.values()] if not path.is_file()]
    if missing:
        checks.add(
            "FILES_PRESENT",
            "Todos os arquivos necessários existem.",
            False,
            f"Arquivos ausentes: {sample(missing)}",
            {"missing_count": len(missing)},
        )
        report = build_report(
            checks,
            results_dir=results_dir,
            buffer_path=buffer_path,
            buffer_geojson_path=buffer_geojson_path,
            config_path=config_path,
            report_path=report_path,
        )
        write_report(report_path, report)
        print(json.dumps(report["summary"], ensure_ascii=False), file=sys.stderr)
        return 1

    try:
        buffer_doc = load_json(buffer_path)
        buffer_geojson = load_json(buffer_geojson_path)
        config = load_json(config_path)
        manifest = load_json(paths["manifest"])
        result_doc = load_json(paths["results"])
        geojson = load_json(paths["geojson"])
        feature_headers, feature_csv_rows = load_csv(paths["features_csv"])
        ranking_headers, ranking_csv_rows = load_csv(paths["ranking_csv"])
        decision_headers, decision_csv_rows = load_csv(paths["decisions_csv"])
        warnings_text = paths["warnings"].read_text(encoding="utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
        checks.add(
            "FILES_PARSE",
            "JSON, GeoJSON, CSV e log podem ser lidos.",
            False,
            f"Falha de leitura: {type(exc).__name__}: {exc}",
        )
        report = build_report(
            checks,
            results_dir=results_dir,
            buffer_path=buffer_path,
            buffer_geojson_path=buffer_geojson_path,
            config_path=config_path,
            report_path=report_path,
        )
        write_report(report_path, report)
        print(json.dumps(report["summary"], ensure_ascii=False), file=sys.stderr)
        return 1

    checks.add(
        "FILES_PRESENT_AND_PARSE",
        "Todos os arquivos necessários existem e são legíveis.",
        True,
        "Entradas e saídas foram abertas sem erro de sintaxe ou codificação.",
        {"files_loaded": 10},
    )

    if not all(
        isinstance(document, dict)
        for document in (buffer_doc, buffer_geojson, config, manifest, result_doc, geojson)
    ):
        checks.add(
            "ROOT_OBJECTS",
            "Documentos JSON têm objeto na raiz.",
            False,
            "Ao menos um JSON não possui objeto na raiz; as demais verificações não são seguras.",
        )
        report = build_report(
            checks,
            results_dir=results_dir,
            buffer_path=buffer_path,
            buffer_geojson_path=buffer_geojson_path,
            config_path=config_path,
            report_path=report_path,
        )
        write_report(report_path, report)
        print(json.dumps(report["summary"], ensure_ascii=False), file=sys.stderr)
        return 1

    buffer_rows = buffer_doc.get("results") if isinstance(buffer_doc.get("results"), list) else []
    sector_rows = result_doc.get("results") if isinstance(result_doc.get("results"), list) else []
    decision_rows = result_doc.get("decisions") if isinstance(result_doc.get("decisions"), list) else []
    external_firewall_docs, external_firewall_errors = load_firewall_input_documents(manifest, paths["manifest"])

    checks.run("CONFIG_CONTRACT", "A configuração preserva 3×8, pesos válidos, firewall e ranking intrabuffer.", lambda: check_config(config))
    checks.run(
        "MANIFEST_HASHES",
        "Hashes SHA-256 e tamanhos de todos os arquivos do manifesto conferem.",
        lambda: check_manifest_hashes(
            manifest, paths["manifest"], buffer_path, buffer_geojson_path, config_path, results_dir
        ),
    )
    checks.run(
        "SCIENTIFIC_HASH",
        "O hash canônico do resultado científico coincide com o manifesto.",
        lambda: check_scientific_hash(manifest, sector_rows),
    )
    checks.run(
        "SCIENTIFIC_BUNDLE_HASH",
        "O hash canônico dos seis outputs científicos coincide com o manifesto.",
        lambda: check_scientific_bundle_hash(manifest, paths["manifest"]),
    )
    checks.run(
        "CARDINALITIES",
        "As cardinalidades das saídas coincidem com os buffers de entrada e a configuração.",
        lambda: check_cardinalities(
            buffer_doc,
            config,
            result_doc,
            manifest,
            sector_rows,
            decision_rows,
            geojson,
            feature_csv_rows,
            ranking_csv_rows,
            decision_csv_rows,
        ),
    )
    checks.run(
        "PARTITION_3X8",
        "Cada buffer tem o produto cartesiano de 3 anéis e 8 direções.",
        lambda: check_partition_3x8(buffer_rows, sector_rows, config),
    )
    checks.run(
        "UNIQUE_IDENTIFIERS",
        "Os IDs setoriais são únicos e obedecem ao template congelado.",
        lambda: check_identifiers(sector_rows, geojson),
    )
    checks.run(
        "AREA_CONSERVATION",
        "Áreas individuais e somadas respeitam a tolerância e o buffer pai.",
        lambda: check_authoritative_partition(buffer_rows, buffer_geojson, sector_rows, geojson, config),
    )
    checks.run(
        "CLOSED_GEOMETRIES",
        "Todas as geometrias são polígonos fechados com coordenadas válidas.",
        lambda: check_geometries(geojson, config),
    )
    checks.run(
        "SCORES_AND_COMPLETENESS",
        "Escores, nulos, contribuições e completude GEO seguem a política sem renormalização.",
        lambda: check_scores(sector_rows, config),
    )
    checks.run(
        "WITHIN_BUFFER_RANKS",
        "Os competition ranks e os ranks nulos foram recalculados dentro de cada buffer.",
        lambda: check_ranks(sector_rows, config),
    )
    checks.run(
        "SELECTION_AND_DECISIONS",
        "Seleção ou abstenção, co-vencedores, margem e suporte fracionário são coerentes.",
        lambda: check_decisions(sector_rows, decision_rows, config),
    )
    checks.run(
        "CROSS_OUTPUT_CONSISTENCY",
        "JSON, GeoJSON e CSVs representam as mesmas entidades e resultados essenciais.",
        lambda: check_cross_output_consistency(
            sector_rows,
            decision_rows,
            geojson,
            feature_csv_rows,
            ranking_csv_rows,
            decision_csv_rows,
        ),
    )
    checks.run(
        "GROUND_TRUTH_FIREWALL",
        "O ground truth não aparece nas entradas/saídas científicas e o controle permanece false.",
        lambda: check_ground_truth_firewall(
            config,
            (
                ("buffer_json", buffer_doc),
                ("buffer_geojson", buffer_geojson),
                ("manifest", manifest),
                ("sector_results", result_doc),
                ("sector_geojson", geojson),
                *external_firewall_docs,
            ),
            (
                ("sector_features_csv", feature_headers, feature_csv_rows),
                ("sector_ranking_csv", ranking_headers, ranking_csv_rows),
                ("buffer_decisions_csv", decision_headers, decision_csv_rows),
            ),
            warnings_text,
            external_firewall_errors,
        ),
    )
    checks.run(
        "NO_CROSS_BUFFER_RANKING",
        "Não existe ranking global, entre candidatos ou entre buffers.",
        lambda: check_no_cross_buffer_ranking(result_doc, sector_rows, config),
    )

    report = build_report(
        checks,
        results_dir=results_dir,
        buffer_path=buffer_path,
        buffer_geojson_path=buffer_geojson_path,
        config_path=config_path,
        report_path=report_path,
    )
    write_report(report_path, report)
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if not checks.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
