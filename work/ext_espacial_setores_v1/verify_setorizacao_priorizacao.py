#!/usr/bin/env python3
"""Verificador independente das saídas DEV-S de setorização e priorização.

O programa não importa o motor que produziu os resultados. Ele lê apenas o
contrato congelado, o JSON de buffers e os artefatos gravados no diretório de
resultados. O relatório contém uma lista explícita de verificações PASS/FAIL e
o processo termina com código 0 somente quando todas elas passam.
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


VERIFIER_ID = "EXT-ESP-SET-VERIFY-v1.0"
EXPECTED_BUFFER_COUNT = 90
EXPECTED_SECTORS_PER_BUFFER = 24
EXPECTED_SECTOR_COUNT = EXPECTED_BUFFER_COUNT * EXPECTED_SECTORS_PER_BUFFER

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
    "ground_truth_lat",
    "ground_truth_lon",
    "reference_lat",
    "reference_lon",
    "true_lat",
    "true_lon",
    "victim_lat",
    "victim_lon",
    "target_lat",
    "target_lon",
    "distance_to_truth",
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

    if geometry.get("rings") != 3:
        errors.append(f"geometry.rings={geometry.get('rings')!r}, esperado 3")
    if geometry.get("directions") != 8:
        errors.append(f"geometry.directions={geometry.get('directions')!r}, esperado 8")
    if geometry.get("sectors_per_buffer") != EXPECTED_SECTORS_PER_BUFFER:
        errors.append("geometry.sectors_per_buffer não é 24")
    centers = geometry.get("direction_centers_deg")
    if not isinstance(centers, dict) or len(centers) != 8:
        errors.append("direction_centers_deg não contém oito direções")
    fractions = geometry.get("ring_boundaries_as_radius_fraction")
    if not isinstance(fractions, list) or len(fractions) != 4:
        errors.append("ring_boundaries_as_radius_fraction não contém quatro limites")
    if ranking.get("scope") != "WITHIN_CANDIDATE_BUFFER_ONLY":
        errors.append("ranking.scope não está restrito ao buffer do candidato")
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
        "Contrato congelado confirma 3 anéis × 8 direções e ranking intrabuffer."
        if not errors
        else "; ".join(errors),
        {"rings": geometry.get("rings"), "directions": geometry.get("directions"), "weight_sets": weight_names},
    )


def check_manifest_hashes(
    manifest: Mapping[str, Any], manifest_path: Path, buffer_path: Path, config_path: Path, results_dir: Path
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

    supplied_roles = {"input_buffer_json": buffer_path.resolve(), "config": config_path.resolve()}
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
            "decision": row.get("buffer_decision_status"),
        }
        for row in sector_rows
    ]
    actual = canonical_hash(projection)
    expected = str(manifest.get("scientific_output_sha256", ""))
    passed = len(expected) == 64 and actual == expected
    return (
        passed,
        "Hash científico canônico coincide com o manifesto."
        if passed
        else f"Hash científico divergente: esperado={expected!r}, calculado={actual}",
        {"scientific_output_sha256": actual},
    )


def check_cardinalities(
    buffer_doc: Mapping[str, Any],
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
        if value != EXPECTED_BUFFER_COUNT:
            errors.append(f"{label}={value!r}, esperado {EXPECTED_BUFFER_COUNT}")

    sector_values = {
        "result_doc.sector_count": result_doc.get("sector_count"),
        "manifest.sector_count": manifest.get("sector_count"),
        "len(result_doc.results)": len(sector_rows),
        "len(GeoJSON.features)": len(features),
        "len(features_csv)": len(feature_csv_rows),
        "len(ranking_csv)": len(ranking_csv_rows),
    }
    for label, value in sector_values.items():
        if value != EXPECTED_SECTOR_COUNT:
            errors.append(f"{label}={value!r}, esperado {EXPECTED_SECTOR_COUNT}")

    for label, value in {
        "result_doc.sectors_per_buffer": result_doc.get("sectors_per_buffer"),
        "manifest.sectors_per_buffer": manifest.get("sectors_per_buffer"),
    }.items():
        if value != EXPECTED_SECTORS_PER_BUFFER:
            errors.append(f"{label}={value!r}, esperado {EXPECTED_SECTORS_PER_BUFFER}")

    return (
        not errors,
        "Cardinalidades coerentes: 90 buffers, 2.160 setores e 90 decisões."
        if not errors
        else "; ".join(sample(errors)),
        {
            "buffers": len(buffer_rows),
            "sectors": len(sector_rows),
            "decisions": len(decision_rows),
            "sectors_per_buffer": result_doc.get("sectors_per_buffer"),
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
    expected_pairs = {(ring, direction) for ring in range(1, 4) for direction in range(1, 9)}
    for key, rows in grouped.items():
        if len(rows) != EXPECTED_SECTORS_PER_BUFFER:
            errors.append(f"{key} contém {len(rows)} setores")
            continue
        pairs = {(integer_value(row.get("ring_index")), integer_value(row.get("direction_index"))) for row in rows}
        if pairs != expected_pairs:
            errors.append(f"{key} não contém exatamente o produto cartesiano 3×8")
        for row in rows:
            ring = integer_value(row.get("ring_index"))
            direction = integer_value(row.get("direction_index"))
            if ring is None or direction is None or not (1 <= ring <= 3 and 1 <= direction <= 8):
                continue
            expected_label = direction_labels[direction - 1] if len(direction_labels) == 8 else None
            if row.get("direction_label") != expected_label or row.get("direction") != expected_label:
                errors.append(f"rótulo direcional incoerente em {row.get('sector_id')}")
            if row.get("ring_id") != f"R{ring:02d}":
                errors.append(f"ring_id incoerente em {row.get('sector_id')}")
            if row.get("sector_index") != (ring - 1) * 8 + direction:
                errors.append(f"sector_index incoerente em {row.get('sector_id')}")

    scenario_counts = Counter(key[0] for key in grouped)
    if len(scenario_counts) != 30 or set(scenario_counts.values()) != {3}:
        errors.append("estrutura esperada de 30 cenários × 3 candidatos não foi preservada")

    return (
        not errors,
        "Cada um dos 90 buffers contém exatamente 3 anéis × 8 direções."
        if not errors
        else "; ".join(sample(errors)),
        {"buffer_groups": len(grouped), "scenarios": len(scenario_counts), "sectors_per_group": 24},
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
        "Os 2.160 IDs são únicos, seguem o template e coincidem no GeoJSON."
        if not errors
        else "; ".join(sample(errors)),
        {"unique_sector_ids": len(set(sector_ids)), "unique_feature_ids": len(set(feature_ids))},
    )


def check_areas(
    buffer_rows: Sequence[Mapping[str, Any]], sector_rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> tuple[bool, str, Mapping[str, Any]]:
    errors: list[str] = []
    tolerance = finite_number(config.get("geometry", {}).get("area_equality_relative_tolerance"))
    tolerance = 0.01 if tolerance is None else tolerance
    boundaries = config.get("geometry", {}).get("ring_boundaries_as_radius_fraction", [])
    buffer_by_key = {key_of(row): row for row in buffer_rows}
    grouped = group_rows(sector_rows)
    max_sector_error = 0.0
    max_union_error = 0.0
    max_reported_area_error_delta = 0.0

    for key, rows in grouped.items():
        parent = buffer_by_key.get(key)
        if parent is None:
            errors.append(f"buffer pai ausente para {key}")
            continue
        radius = finite_number(parent.get("adaptive_radius_m"))
        parent_area = finite_number(parent.get("buffer_area_m2"))
        if radius is None or radius <= 0 or parent_area is None or parent_area <= 0:
            errors.append(f"raio/área inválido no buffer {key}")
            continue
        expected_sector_area = math.pi * radius * radius / EXPECTED_SECTORS_PER_BUFFER
        sector_areas: list[float] = []
        for row in rows:
            area = finite_number(row.get("sector_area_m2"))
            polygon_area = finite_number(row.get("polygon_planar_area_m2"))
            reported_error = finite_number(row.get("area_relative_error"))
            if area is None or area <= 0:
                errors.append(f"sector_area_m2 inválida em {row.get('sector_id')}")
                continue
            sector_areas.append(area)
            error = relative_error(area, expected_sector_area)
            max_sector_error = max(max_sector_error, error)
            if error > tolerance:
                errors.append(f"área teórica fora da tolerância em {row.get('sector_id')}: {error:.6g}")
            if polygon_area is None or polygon_area <= 0 or reported_error is None:
                errors.append(f"área poligonal/erro ausente em {row.get('sector_id')}")
            else:
                calculated = relative_error(polygon_area, area)
                max_reported_area_error_delta = max(max_reported_area_error_delta, abs(calculated - reported_error))
                if calculated > tolerance:
                    errors.append(f"área poligonal fora da tolerância em {row.get('sector_id')}: {calculated:.6g}")
                if not math.isclose(calculated, reported_error, abs_tol=2e-8):
                    errors.append(f"area_relative_error incoerente em {row.get('sector_id')}")

            ring = integer_value(row.get("ring_index"))
            inner = finite_number(row.get("inner_radius_m"))
            outer = finite_number(row.get("outer_radius_m"))
            if ring is not None and isinstance(boundaries, list) and len(boundaries) == 4:
                expected_inner = radius * float(boundaries[ring - 1])
                expected_outer = radius * float(boundaries[ring])
                if inner is None or relative_error(inner, max(expected_inner, 1e-15)) > 2e-6:
                    if not (expected_inner == 0.0 and inner == 0.0):
                        errors.append(f"inner_radius_m incoerente em {row.get('sector_id')}")
                if outer is None or relative_error(outer, expected_outer) > 2e-6:
                    errors.append(f"outer_radius_m incoerente em {row.get('sector_id')}")

        if sector_areas:
            union_error = relative_error(sum(sector_areas), parent_area)
            max_union_error = max(max_union_error, union_error)
            if union_error > tolerance:
                errors.append(f"soma das áreas diverge do buffer {key}: {union_error:.6g}")
            spread = relative_error(max(sector_areas), min(sector_areas))
            if spread > tolerance:
                errors.append(f"setores não têm áreas equivalentes em {key}: {spread:.6g}")

    return (
        not errors,
        "Áreas setoriais, soma por buffer, raios anelares e erros declarados respeitam a tolerância."
        if not errors
        else "; ".join(sample(errors)),
        {
            "relative_tolerance": tolerance,
            "max_sector_theoretical_relative_error": round(max_sector_error, 12),
            "max_buffer_sum_relative_error": round(max_union_error, 12),
            "max_reported_error_delta": round(max_reported_area_error_delta, 12),
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
        min_vertices = unique_vertices if min_vertices is None else min(min_vertices, unique_vertices)
        max_vertices = max(max_vertices, unique_vertices)

    return (
        not errors,
        "As 2.160 geometrias são polígonos fechados, finitos e com vértices suficientes."
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
    min_score = 1.0
    max_score = 0.0
    min_completeness = 1.0
    complete_count = 0
    for row in sector_rows:
        sector_id = row.get("sector_id")
        valid_scores: dict[str, float] = {}
        for field in REQUIRED_SCORE_FIELDS:
            number = finite_number(row.get(field))
            if number is None or not 0.0 <= number <= 1.0:
                errors.append(f"{field} fora de [0,1] em {sector_id}")
            else:
                valid_scores[field] = number
                min_score = min(min_score, number)
                max_score = max(max_score, number)
        completeness = finite_number(row.get("geo_completeness"))
        if completeness is None or not 0.0 <= completeness <= 1.0:
            errors.append(f"geo_completeness fora de [0,1] em {sector_id}")
        else:
            min_completeness = min(min_completeness, completeness)
            if math.isclose(completeness, required_completeness, abs_tol=1e-12):
                complete_count += 1
            else:
                errors.append(f"completude {completeness} difere de {required_completeness} em {sector_id}")
        if row.get("modules_available") != 4 or row.get("missing_module_count") != 0:
            errors.append(f"contagem de módulos incoerente em {sector_id}")
        if not str(row.get("source_provenance", "")).strip():
            errors.append(f"proveniência ausente em {sector_id}")

        scores_by_set = row.get("scores_by_weight_set")
        contributions_by_set = row.get("contributions_by_weight_set")
        if not isinstance(scores_by_set, dict) or set(scores_by_set) != set(weight_sets):
            errors.append(f"scores_by_weight_set incompleto em {sector_id}")
            continue
        if not isinstance(contributions_by_set, dict) or set(contributions_by_set) != set(weight_sets):
            errors.append(f"contributions_by_weight_set incompleto em {sector_id}")
            continue
        if len(valid_scores) != len(REQUIRED_SCORE_FIELDS):
            continue
        for name, weights in weight_sets.items():
            score = finite_number(scores_by_set.get(name))
            expected = sum(valid_scores[field] * weights[field] for field in REQUIRED_SCORE_FIELDS)
            if score is None or not 0.0 <= score <= 1.0 or not math.isclose(score, expected, abs_tol=2e-8):
                errors.append(f"escore {name} incoerente em {sector_id}")
            contributions = contributions_by_set.get(name)
            if not isinstance(contributions, dict) or set(contributions) != set(SCORE_TO_MODULE.values()):
                errors.append(f"contribuições {name} incompletas em {sector_id}")
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
        if not close_number(row.get("priority_score"), base_score) or not close_number(row.get("score_base"), base_score):
            errors.append(f"aliases do escore BASE incoerentes em {sector_id}")

    return (
        not errors,
        "Todos os escores estão em [0,1], têm proveniência e completude GEO integral."
        if not errors
        else "; ".join(sample(errors)),
        {
            "sectors_complete": complete_count,
            "required_completeness": required_completeness,
            "minimum_score": round(min_score, 9),
            "maximum_score": round(max_score, 9),
            "minimum_geo_completeness": round(min_completeness, 9),
        },
    )


def expected_rank_order(rows: Sequence[Mapping[str, Any]], weight_set: str) -> list[str]:
    return [
        str(row["sector_id"])
        for row in sorted(
            rows,
            key=lambda row: (-float(row["scores_by_weight_set"][weight_set]), str(row["sector_id"])),
        )
    ]


def check_ranks(
    sector_rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> tuple[bool, str, Mapping[str, Any]]:
    errors: list[str] = []
    grouped = group_rows(sector_rows)
    weight_names = list(weight_sets_from_config(config))
    expected_ranks = list(range(1, EXPECTED_SECTORS_PER_BUFFER + 1))
    permutations_checked = 0
    for key, rows in grouped.items():
        for weight_name in weight_names:
            rank_values: list[int] = []
            by_rank: dict[int, str] = {}
            for row in rows:
                ranks = row.get("ranks_by_weight_set")
                rank = integer_value(ranks.get(weight_name)) if isinstance(ranks, dict) else None
                if rank is None:
                    errors.append(f"rank {weight_name} ausente em {row.get('sector_id')}")
                    continue
                rank_values.append(rank)
                by_rank[rank] = str(row.get("sector_id"))
            if sorted(rank_values) != expected_ranks:
                errors.append(f"ranks {weight_name} não formam 1..24 em {key}")
                continue
            permutations_checked += 1
            expected_order = expected_rank_order(rows, weight_name)
            actual_order = [by_rank[index] for index in expected_ranks]
            if actual_order != expected_order:
                errors.append(f"ordenação {weight_name} incoerente com escore/ID em {key}")

        base_ranks = [integer_value(row.get("sector_rank")) for row in rows]
        aliases = [integer_value(row.get("rank_base_within_buffer")) for row in rows]
        if sorted(value for value in base_ranks if value is not None) != expected_ranks:
            errors.append(f"sector_rank não forma 1..24 em {key}")
        if aliases != base_ranks:
            errors.append(f"rank_base_within_buffer difere de sector_rank em {key}")
        for row in rows:
            ranks = row.get("ranks_by_weight_set", {})
            if row.get("sector_rank") != ranks.get("BASE"):
                errors.append(f"rank BASE incoerente em {row.get('sector_id')}")

    return (
        not errors,
        "Cada conjunto de pesos produz ranks 1..24 independentes dentro de cada buffer."
        if not errors
        else "; ".join(sample(errors)),
        {"buffer_groups": len(grouped), "weight_sets": len(weight_names), "rank_permutations_checked": permutations_checked},
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
    weight_names = list(weight_sets_from_config(config))
    selected_total = 0
    prioritized = 0
    review = 0

    for key, rows in grouped.items():
        selected = [row for row in rows if row.get("selected_sector") is True]
        selected_total += len(selected)
        if len(selected) != 1:
            errors.append(f"{key} tem {len(selected)} setores selecionados, esperado 1")
            continue
        winner = selected[0]
        base_order = sorted(rows, key=lambda row: (-float(row["score_base"]), str(row["sector_id"])))
        if winner.get("sector_id") != base_order[0].get("sector_id") or winner.get("sector_rank") != 1:
            errors.append(f"setor selecionado não é o Top-1 BASE em {key}")
        margin = float(base_order[0]["score_base"]) - float(base_order[1]["score_base"])

        top_by_set: dict[str, str] = {}
        top1_counts: Counter[str] = Counter()
        for name in weight_names:
            top = min(rows, key=lambda row: integer_value(row["ranks_by_weight_set"].get(name)) or 10**9)
            top_id = str(top["sector_id"])
            top_by_set[name] = top_id
            top1_counts[top_id] += 1
        winner_stability = top1_counts[str(winner["sector_id"])] / len(weight_names)

        warnings: list[str] = []
        if any(str(row.get("upstream_review_status", row.get("source_buffer_review_status", ""))) == "REVISAR" for row in rows):
            warnings.append("UPSTREAM_REVIEW_REQUIRED")
        if any(
            int(row.get("missing_module_count", 0)) > 0 or float(row.get("geo_completeness", 0.0)) < 1.0
            for row in rows
        ):
            warnings.append("INCOMPLETE_GEO")
        if margin < low_margin:
            warnings.append("LOW_MARGIN")
        if math.isclose(margin, 0.0, abs_tol=1e-12):
            warnings.append("TOP_SCORE_TIE")
        if winner_stability < stability_threshold:
            warnings.append("RANKING_UNSTABLE")
        if str(winner.get("barrier_flags", "NAO_SINALIZADA")) != "NAO_SINALIZADA":
            warnings.append("POTENTIAL_BARRIER")
        expected_status = "REVISAR" if warnings else "PRIORIZADO"
        if expected_status == "PRIORIZADO":
            prioritized += 1
        else:
            review += 1

        for row in rows:
            sector_id = row.get("sector_id")
            if not close_number(row.get("rank_margin"), margin) or not close_number(row.get("buffer_base_margin"), margin):
                errors.append(f"margem incoerente em {sector_id}")
            expected_count = top1_counts[str(sector_id)]
            if row.get("top1_count") != expected_count:
                errors.append(f"top1_count incoerente em {sector_id}")
            if not close_number(row.get("top1_stability"), expected_count / len(weight_names)):
                errors.append(f"top1_stability incoerente em {sector_id}")
            if row.get("decision_status") != expected_status or row.get("buffer_decision_status") != expected_status:
                errors.append(f"status incoerente em {sector_id}: esperado {expected_status}")
            if codes(row.get("warning_codes")) != warnings or codes(row.get("buffer_warning_codes")) != warnings:
                errors.append(f"warning_codes incoerente em {sector_id}")
            if row.get("supervision_required") is not True:
                errors.append(f"supervisão humana não exigida em {sector_id}")

        decision_matches = decisions_by_key.get(key, [])
        if len(decision_matches) != 1:
            errors.append(f"{key} tem {len(decision_matches)} decisões, esperado 1")
            continue
        decision = decision_matches[0]
        if decision.get("top1_sector_id") != winner.get("sector_id"):
            errors.append(f"top1_sector_id da decisão diverge em {key}")
        if not close_number(decision.get("top1_score_base"), winner.get("score_base")):
            errors.append(f"top1_score_base da decisão diverge em {key}")
        if not close_number(decision.get("base_margin"), margin):
            errors.append(f"base_margin da decisão diverge em {key}")
        if not close_number(decision.get("top1_stability"), winner_stability):
            errors.append(f"top1_stability da decisão diverge em {key}")
        if decision.get("decision_status") != expected_status or codes(decision.get("warning_codes")) != warnings:
            errors.append(f"status/alertas da decisão incoerentes em {key}")
        try:
            declared_top_by_set = json.loads(str(decision.get("top1_by_weight_set", "")))
        except json.JSONDecodeError:
            declared_top_by_set = None
        if declared_top_by_set != top_by_set:
            errors.append(f"top1_by_weight_set incoerente em {key}")
        if decision.get("confirmatory_eligible") is not False or decision.get("supervision_required") is not True:
            errors.append(f"guardrails da decisão incoerentes em {key}")

    if set(decisions_by_key) != set(grouped):
        errors.append("chaves das decisões divergem das chaves dos buffers setorizados")

    return (
        not errors,
        "Há exatamente um Top-1 por buffer; margens, estabilidade, alertas e decisões são coerentes."
        if not errors
        else "; ".join(sample(errors)),
        {
            "selected_sectors": selected_total,
            "decisions_prioritized": prioritized,
            "decisions_review": review,
            "low_margin_threshold": low_margin,
            "stability_threshold": stability_threshold,
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
            try:
                csv_rank = int(ranking.get("rank_base_within_buffer", ""))
                csv_score = float(ranking.get("score_base", ""))
            except (TypeError, ValueError):
                errors.append(f"rank/escore inválido no ranking CSV: {sector_id}")
            else:
                if csv_rank != source.get("rank_base_within_buffer") or not close_number(csv_score, source.get("score_base")):
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
            if not close_number(properties.get("score_base"), source.get("score_base")):
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
            if target.get("top1_sector_id") != source.get("top1_sector_id"):
                errors.append(f"Top-1 diverge no CSV de decisões: {key}")
            if target.get("decision_status") != source.get("decision_status"):
                errors.append(f"status diverge no CSV de decisões: {key}")
            if not close_number(float(target.get("base_margin", "nan")), source.get("base_margin")):
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
) -> tuple[bool, str, Mapping[str, Any]]:
    configured = config.get("ground_truth_firewall", {}).get("forbidden_columns_or_fragments", [])
    forbidden = DEFAULT_GT_FRAGMENTS | {str(value).lower() for value in configured}
    violations: list[str] = []
    control_fields = 0

    for label, document in json_documents:
        for path, key, value in walk_json(document):
            normalized = key.lower()
            if normalized == "ground_truth_used":
                control_fields += 1
                if value is not False:
                    violations.append(f"{label}:{path} deve ser booleano false")
                continue
            if any(fragment in normalized for fragment in forbidden):
                violations.append(f"{label}:{path} contém campo proibido")

    for label, headers, rows in csv_documents:
        for header in headers:
            normalized = header.lower()
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
        {"forbidden_fragments": len(forbidden), "ground_truth_control_fields_checked": control_fields},
    )


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
    for row in sector_rows:
        for key in row:
            normalized = str(key).lower()
            if normalized in CROSS_BUFFER_RANK_FIELDS or any(token in normalized for token in ("global_sector_rank", "rank_across_buffer")):
                unexpected.add(str(key))
    if unexpected:
        errors.append(f"campos de ranking cross-buffer encontrados: {sorted(unexpected)}")

    grouped = group_rows(sector_rows)
    for key, rows in grouped.items():
        ranks = sorted(integer_value(row.get("rank_base_within_buffer")) for row in rows if integer_value(row.get("rank_base_within_buffer")) is not None)
        if ranks != list(range(1, EXPECTED_SECTORS_PER_BUFFER + 1)):
            errors.append(f"rank não reinicia em 1..24 no buffer {key}")

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
    checks: Checks, *, results_dir: Path, buffer_path: Path, config_path: Path, report_path: Path
) -> dict[str, Any]:
    passed = len(checks.items) - len(checks.failed)
    return {
        "verifier_id": VERIFIER_ID,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "PASS" if not checks.failed else "FAIL",
        "inputs": {
            "results_dir": str(results_dir),
            "buffer_json": str(buffer_path),
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
    parser.add_argument("--config", required=True, type=Path, help="Configuração congelada da setorização")
    parser.add_argument("--report", required=True, type=Path, help="Caminho do relatório JSON de verificação")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results_dir = args.results_dir.expanduser().resolve()
    buffer_path = args.buffer_json.expanduser().resolve()
    config_path = args.config.expanduser().resolve()
    report_path = args.report.expanduser().resolve()
    paths = {name: (results_dir / filename).resolve() for name, filename in RESULT_FILES.items()}

    protected = set(paths.values()) | {buffer_path, config_path}
    if report_path in protected:
        print("ERRO: --report não pode sobrescrever uma entrada ou saída científica.", file=sys.stderr)
        return 1

    checks = Checks()
    missing = [str(path) for path in [buffer_path, config_path, *paths.values()] if not path.is_file()]
    if missing:
        checks.add(
            "FILES_PRESENT",
            "Todos os arquivos necessários existem.",
            False,
            f"Arquivos ausentes: {sample(missing)}",
            {"missing_count": len(missing)},
        )
        report = build_report(
            checks, results_dir=results_dir, buffer_path=buffer_path, config_path=config_path, report_path=report_path
        )
        write_report(report_path, report)
        print(json.dumps(report["summary"], ensure_ascii=False), file=sys.stderr)
        return 1

    try:
        buffer_doc = load_json(buffer_path)
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
            checks, results_dir=results_dir, buffer_path=buffer_path, config_path=config_path, report_path=report_path
        )
        write_report(report_path, report)
        print(json.dumps(report["summary"], ensure_ascii=False), file=sys.stderr)
        return 1

    checks.add(
        "FILES_PRESENT_AND_PARSE",
        "Todos os arquivos necessários existem e são legíveis.",
        True,
        "Entradas e saídas foram abertas sem erro de sintaxe ou codificação.",
        {"files_loaded": 9},
    )

    if not all(isinstance(document, dict) for document in (buffer_doc, config, manifest, result_doc, geojson)):
        checks.add(
            "ROOT_OBJECTS",
            "Documentos JSON têm objeto na raiz.",
            False,
            "Ao menos um JSON não possui objeto na raiz; as demais verificações não são seguras.",
        )
        report = build_report(
            checks, results_dir=results_dir, buffer_path=buffer_path, config_path=config_path, report_path=report_path
        )
        write_report(report_path, report)
        print(json.dumps(report["summary"], ensure_ascii=False), file=sys.stderr)
        return 1

    buffer_rows = buffer_doc.get("results") if isinstance(buffer_doc.get("results"), list) else []
    sector_rows = result_doc.get("results") if isinstance(result_doc.get("results"), list) else []
    decision_rows = result_doc.get("decisions") if isinstance(result_doc.get("decisions"), list) else []

    checks.run("CONFIG_CONTRACT", "A configuração preserva 3×8, pesos válidos, firewall e ranking intrabuffer.", lambda: check_config(config))
    checks.run(
        "MANIFEST_HASHES",
        "Hashes SHA-256 e tamanhos de todos os arquivos do manifesto conferem.",
        lambda: check_manifest_hashes(manifest, paths["manifest"], buffer_path, config_path, results_dir),
    )
    checks.run(
        "SCIENTIFIC_HASH",
        "O hash canônico do resultado científico coincide com o manifesto.",
        lambda: check_scientific_hash(manifest, sector_rows),
    )
    checks.run(
        "CARDINALITIES",
        "As saídas contêm 90 buffers, 2.160 setores, 24 setores por buffer e 90 decisões.",
        lambda: check_cardinalities(
            buffer_doc,
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
        lambda: check_areas(buffer_rows, sector_rows, config),
    )
    checks.run(
        "CLOSED_GEOMETRIES",
        "Todas as geometrias são polígonos fechados com coordenadas válidas.",
        lambda: check_geometries(geojson, config),
    )
    checks.run(
        "SCORES_AND_COMPLETENESS",
        "Escores estão em [0,1] e a completude/proveniência GEO está íntegra.",
        lambda: check_scores(sector_rows, config),
    )
    checks.run(
        "WITHIN_BUFFER_RANKS",
        "Os ranks formam 1..24 em cada buffer e em cada conjunto de pesos.",
        lambda: check_ranks(sector_rows, config),
    )
    checks.run(
        "SELECTION_AND_DECISIONS",
        "Há um selecionado por buffer e a decisão é coerente com escore, margem e estabilidade.",
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
                ("manifest", manifest),
                ("sector_results", result_doc),
                ("sector_geojson", geojson),
            ),
            (
                ("sector_features_csv", feature_headers, feature_csv_rows),
                ("sector_ranking_csv", ranking_headers, ranking_csv_rows),
                ("buffer_decisions_csv", decision_headers, decision_csv_rows),
            ),
            warnings_text,
        ),
    )
    checks.run(
        "NO_CROSS_BUFFER_RANKING",
        "Não existe ranking global, entre candidatos ou entre buffers.",
        lambda: check_no_cross_buffer_ranking(result_doc, sector_rows, config),
    )

    report = build_report(
        checks, results_dir=results_dir, buffer_path=buffer_path, config_path=config_path, report_path=report_path
    )
    write_report(report_path, report)
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if not checks.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
