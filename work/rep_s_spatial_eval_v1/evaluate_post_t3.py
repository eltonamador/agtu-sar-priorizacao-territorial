#!/usr/bin/env python3
"""Abre o ground truth depois de T2 e calcula a avaliacao setorial T3--T4."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from common import (
    DEFAULT_CONFIG,
    ProtocolError,
    assert_file_record,
    closed_polygon_membership,
    file_record,
    fold_text,
    haversine_m,
    load_config,
    mean,
    median,
    parse_bool,
    parse_finite_float,
    proportion_record,
    read_csv,
    read_json,
    sha256_file,
    stable_hash,
    utc_now,
    validate_dependencies,
    write_csv,
    write_json,
)


SCRIPT_VERSION = "1.0.0"


def _manifest_payload_valid(manifest: Mapping[str, Any]) -> bool:
    expected = manifest.get("manifest_payload_sha256")
    if not expected:
        return False
    payload = dict(manifest)
    payload.pop("manifest_payload_sha256", None)
    return stable_hash(payload) == expected


def _find_file(manifest: Mapping[str, Any], collection: str, role: str) -> Path:
    matches = [item for item in manifest.get(collection, []) if item.get("role") == role]
    if len(matches) != 1:
        raise ProtocolError(f"Manifesto T2 nao contem papel unico {collection}:{role}.")
    return assert_file_record(matches[0])


def validate_t2_manifest(
    manifest_path: Path, config: Mapping[str, Any], config_hash: str
) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or not _manifest_payload_valid(manifest):
        raise ProtocolError("Manifesto T2 invalido ou adulterado.")
    if manifest.get("protocol_id") != config["protocol_id"]:
        raise ProtocolError("Protocolo do manifesto T2 divergente.")
    if manifest.get("milestone") != "T2" or manifest.get("state") != "SAIDAS_CEGAS_CONGELADAS":
        raise ProtocolError("A avaliacao exige T2 concluido.")
    if manifest.get("ground_truth_used") is not False:
        raise ProtocolError("T2 nao preservou o firewall do ground truth.")
    if manifest.get("config_sha256") != config_hash:
        raise ProtocolError("Configuracao da avaliacao diverge daquela usada em T2.")
    determinism = manifest.get("determinism") or {}
    if determinism.get("all_identical") is not True:
        raise ProtocolError("T2 nao comprovou determinismo das saidas cientificas.")
    for collection in ("primary_files", "repeat_files", "source_files", "dependencies"):
        for record in manifest.get(collection, []):
            assert_file_record(record)
    assert_file_record(manifest["t1_manifest"])
    assert_file_record(manifest["buffer_input"])
    return manifest


def read_ground_truth(path: Path, config: Mapping[str, Any], expected_hash: str) -> list[dict[str, Any]]:
    observed_hash = sha256_file(path)
    if observed_hash != expected_hash:
        raise ProtocolError("Ground truth aberto em T3 diverge do compromisso SHA-256 de T0.")
    headers, rows = read_csv(path)
    required = list(config["ground_truth"]["required_columns"])
    missing = [field for field in required if field not in headers]
    if missing:
        raise ProtocolError("Ground truth sem campos obrigatorios: " + ", ".join(missing))
    if len(rows) != config["cardinality"]["sites"]:
        raise ProtocolError("Ground truth deve conter exatamente quatro sites.")
    normalized: list[dict[str, Any]] = []
    seen_site: set[str] = set()
    seen_scenario: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        site_id = str(row.get("site_id", "")).strip()
        scenario_id = str(row.get("scenario_id", "")).strip()
        environment = str(row.get("planned_environment", "")).strip()
        if not site_id or not scenario_id or not environment:
            raise ProtocolError(f"Linha {row_number} do ground truth contem identificador/estrato vazio.")
        if site_id in seen_site or scenario_id in seen_scenario:
            raise ProtocolError("site_id e scenario_id devem ser unicos no ground truth.")
        seen_site.add(site_id)
        seen_scenario.add(scenario_id)
        latitude = parse_finite_float(row.get("ground_truth_lat"), f"linha {row_number}:ground_truth_lat")
        longitude = parse_finite_float(row.get("ground_truth_lon"), f"linha {row_number}:ground_truth_lon")
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ProtocolError(f"Linha {row_number}: coordenada fora de EPSG:4326.")
        normalized.append(
            {
                "site_id": site_id,
                "scenario_id": scenario_id,
                "ground_truth_lat": latitude,
                "ground_truth_lon": longitude,
                "planned_environment": environment,
            }
        )
    return sorted(normalized, key=lambda item: (item["scenario_id"], item["site_id"]))


def _load_buffers(path: Path, expected_count: int) -> dict[tuple[str, str], dict[str, Any]]:
    document = read_json(path)
    if document.get("ground_truth_used") is not False:
        raise ProtocolError("JSON de buffers declara uso indevido do ground truth.")
    results = document.get("results")
    if not isinstance(results, list) or len(results) != expected_count:
        raise ProtocolError("JSON de buffers tem cardinalidade divergente.")
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in results:
        if row.get("ground_truth_used") is not False:
            raise ProtocolError("Registro de buffer viola o firewall.")
        key = (str(row.get("scenario_id", "")), str(row.get("candidate_id", "")))
        if not all(key) or key in by_key:
            raise ProtocolError("Chave de buffer vazia ou duplicada.")
        by_key[key] = dict(row)
    return by_key


def _load_sector_geometry(
    path: Path, expected_count: int
) -> dict[tuple[str, str], dict[str, list[list[float]]]]:
    document = read_json(path)
    if document.get("ground_truth_used") is not False:
        raise ProtocolError("GeoJSON setorial declara uso indevido do ground truth.")
    features = document.get("features")
    if not isinstance(features, list) or len(features) != expected_count:
        raise ProtocolError("GeoJSON setorial tem cardinalidade divergente.")
    grouped: dict[tuple[str, str], dict[str, list[list[float]]]] = defaultdict(dict)
    for feature in features:
        properties = feature.get("properties") or {}
        scenario = str(properties.get("scenario_id", ""))
        candidate = str(properties.get("candidate_id", ""))
        sector_id = str(properties.get("sector_id", feature.get("id", "")))
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []
        if geometry.get("type") != "Polygon" or len(coordinates) != 1:
            raise ProtocolError(f"Geometria setorial invalida: {sector_id}.")
        ring = coordinates[0]
        if len(ring) < 4 or ring[0] != ring[-1]:
            raise ProtocolError(f"Anel setorial invalido: {sector_id}.")
        key = (scenario, candidate)
        if sector_id in grouped[key]:
            raise ProtocolError(f"sector_id duplicado: {sector_id}.")
        grouped[key][sector_id] = ring
    return dict(grouped)


def _optional_float(value: Any, field: str) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return parse_finite_float(value, field)


def _optional_int(value: Any, field: str) -> int | None:
    number = _optional_float(value, field)
    if number is None:
        return None
    if not float(number).is_integer() or number < 1:
        raise ProtocolError(f"{field} deve ser rank inteiro positivo.")
    return int(number)


def _load_ranking(
    path: Path, expected_count: int, sectors_per_buffer: int
) -> dict[tuple[str, str], dict[str, dict[str, Any]]]:
    _headers, rows = read_csv(path)
    if len(rows) != expected_count:
        raise ProtocolError("CSV de ranking setorial tem cardinalidade divergente.")
    grouped: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row_number, row in enumerate(rows, start=2):
        if parse_bool(row.get("ground_truth_used"), f"linha {row_number}:ground_truth_used"):
            raise ProtocolError("Ranking setorial declara uso indevido do ground truth.")
        scenario = str(row.get("scenario_id", "")).strip()
        candidate = str(row.get("candidate_id", "")).strip()
        sector_id = str(row.get("sector_id", "")).strip()
        if not scenario or not candidate or not sector_id:
            raise ProtocolError(f"Linha {row_number}: chave setorial vazia.")
        key = (scenario, candidate)
        if sector_id in grouped[key]:
            raise ProtocolError(f"sector_id duplicado no ranking: {sector_id}.")
        rank = _optional_int(
            row.get("rank_base_within_buffer", row.get("sector_rank")),
            f"linha {row_number}:rank_base_within_buffer",
        )
        area = parse_finite_float(row.get("sector_area_m2"), f"linha {row_number}:sector_area_m2")
        if area <= 0:
            raise ProtocolError(f"Linha {row_number}: area setorial nao positiva.")
        completeness = parse_finite_float(row.get("geo_completeness"), f"linha {row_number}:geo_completeness")
        scores = [
            _optional_float(row.get(field), f"linha {row_number}:{field}")
            for field in ("geo02_score", "geo03_score", "geo04_score", "geo05_score")
        ]
        geo_complete = math.isclose(completeness, 1.0, abs_tol=1e-12) and all(
            score is not None and 0.0 <= score <= 1.0 for score in scores
        )
        grouped[key][sector_id] = {
            "sector_id": sector_id,
            "rank": rank,
            "area_m2": area,
            "geo_complete": geo_complete,
            "geo_completeness": completeness,
        }
    for key, values in grouped.items():
        if len(values) != sectors_per_buffer:
            raise ProtocolError(f"Buffer {key} nao contem {sectors_per_buffer} setores no ranking.")
    return dict(grouped)


def relevant_sector_set(
    *,
    ground_truth_lat: float,
    ground_truth_lon: float,
    center_lat: float,
    center_lon: float,
    polygons: Mapping[str, Sequence[Sequence[float]]],
    tolerance_m: float,
) -> tuple[list[str], list[str], float | None]:
    relevant: list[str] = []
    boundary: list[str] = []
    minimum_distance: float | None = None
    for sector_id, ring in sorted(polygons.items()):
        member, on_boundary, distance = closed_polygon_membership(
            point_lat=ground_truth_lat,
            point_lon=ground_truth_lon,
            polygon_lon_lat=ring,
            center_lat=center_lat,
            center_lon=center_lon,
            tolerance_m=tolerance_m,
        )
        minimum_distance = distance if minimum_distance is None else min(minimum_distance, distance)
        if member:
            relevant.append(sector_id)
            if on_boundary:
                boundary.append(sector_id)
    return relevant, boundary, minimum_distance


def evaluate_candidate(
    *,
    site_id: str,
    environment_class: str,
    ground_truth: Mapping[str, Any],
    buffer: Mapping[str, Any],
    polygons: Mapping[str, Sequence[Sequence[float]]],
    ranking: Mapping[str, Mapping[str, Any]],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    if set(polygons) != set(ranking):
        raise ProtocolError("Conjunto de sector_id difere entre geometria e ranking.")
    center_lat = parse_finite_float(buffer.get("estimated_lat"), "estimated_lat")
    center_lon = parse_finite_float(buffer.get("estimated_lon"), "estimated_lon")
    ground_lat = float(ground_truth["ground_truth_lat"])
    ground_lon = float(ground_truth["ground_truth_lon"])
    tolerance = float(config["boundary_rule"]["boundary_tolerance_m"])
    relevant, boundary, nearest_boundary = relevant_sector_set(
        ground_truth_lat=ground_lat,
        ground_truth_lon=ground_lon,
        center_lat=center_lat,
        center_lon=center_lon,
        polygons=polygons,
        tolerance_m=tolerance,
    )
    distance = haversine_m(center_lat, center_lon, ground_lat, ground_lon)
    fixed_radius = float(config["metrics"]["fixed_baseline_radius_m"])
    total_area = sum(float(item["area_m2"]) for item in ranking.values())
    geo_complete_count = sum(bool(item["geo_complete"]) for item in ranking.values())
    ranks = [ranking[sector_id]["rank"] for sector_id in relevant]
    ranks_available = bool(relevant) and all(rank is not None for rank in ranks)
    rank_min = min(ranks) if ranks_available else None
    rank_max = max(ranks) if ranks_available else None
    area_primary = (
        sum(float(item["area_m2"]) for item in ranking.values() if item["rank"] is not None and item["rank"] <= rank_min)
        if rank_min is not None
        else None
    )
    area_conservative = (
        sum(float(item["area_m2"]) for item in ranking.values() if item["rank"] is not None and item["rank"] <= rank_max)
        if rank_max is not None
        else None
    )
    result: dict[str, Any] = {
        "site_id": site_id,
        "scenario_id": str(buffer["scenario_id"]),
        "candidate_id": str(buffer["candidate_id"]),
        "environment_class": environment_class,
        "distance_candidate_to_truth_m": round(distance, 6),
        "adaptive_radius_m": float(buffer["adaptive_radius_m"]),
        "adaptive_buffer_area_m2": float(buffer["buffer_area_m2"]),
        "fixed_baseline_radius_m": fixed_radius,
        "fixed_baseline_area_m2": math.pi * fixed_radius**2,
        "adaptive_area_ratio_to_fixed": float(buffer["buffer_area_m2"]) / (math.pi * fixed_radius**2),
        "adaptive_coverage": bool(relevant),
        "fixed_coverage": distance <= fixed_radius,
        "relevant_sector_count": len(relevant),
        "relevant_sector_ids": ";".join(relevant),
        "boundary_member_count": len(boundary),
        "boundary_sector_ids": ";".join(boundary),
        "assignment_case": (
            "OUTSIDE_BUFFER"
            if not relevant
            else "BOUNDARY_SET_VALUED"
            if len(relevant) > 1 or boundary
            else "INTERIOR_SINGLETON"
        ),
        "nearest_sector_boundary_m": nearest_boundary,
        "rank_evaluable": ranks_available,
        "truth_rank_min": rank_min,
        "truth_rank_max": rank_max,
        "reciprocal_rank_primary": 0.0 if rank_min is None else 1.0 / rank_min,
        "reciprocal_rank_conservative": 0.0 if rank_max is None else 1.0 / rank_max,
        "accumulated_area_primary_m2": area_primary,
        "accumulated_area_conservative_m2": area_conservative,
        "accumulated_area_primary_fraction": None if area_primary is None else area_primary / total_area,
        "accumulated_area_conservative_fraction": None if area_conservative is None else area_conservative / total_area,
        "buffer_sector_area_total_m2": total_area,
        "geo_complete_sector_count": geo_complete_count,
        "geo_sector_count": len(ranking),
        "geo_data_coverage_rate": geo_complete_count / len(ranking),
        "geo_data_buffer_complete": geo_complete_count == len(ranking),
        "buffer_review_status": str(buffer.get("review_status", "")),
        "buffer_confirmatory_eligible": bool(buffer.get("confirmatory_eligible")),
    }
    for k in config["metrics"]["top_k"]:
        result[f"top{k}_primary"] = rank_min is not None and rank_min <= int(k)
        result[f"top{k}_conservative"] = rank_max is not None and rank_max <= int(k)
    return result


def _environment_from_ground_truth_label(label: str) -> str:
    mapping = {
        "urbano": "URBANO",
        "semirrural": "MISTO",
        "semi_rural": "MISTO",
        "rural": "RURAL/ABERTO",
        "mata": "MATA",
    }
    token = fold_text(label).replace("-", "_").replace(" ", "_")
    return mapping.get(token, label.strip().upper())


def evaluate_all(
    *,
    ground_truth_rows: Sequence[Mapping[str, Any]],
    candidate_map: Sequence[Mapping[str, Any]],
    buffers: Mapping[tuple[str, str], Mapping[str, Any]],
    geometry: Mapping[tuple[str, str], Mapping[str, Sequence[Sequence[float]]]],
    ranking: Mapping[tuple[str, str], Mapping[str, Mapping[str, Any]]],
    config: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    gt_by_key = {(str(row["site_id"]), str(row["scenario_id"])): row for row in ground_truth_rows}
    map_by_candidate: dict[tuple[str, str], Mapping[str, Any]] = {}
    scenarios_to_sites: dict[str, set[str]] = defaultdict(set)
    for row in candidate_map:
        key = (str(row["scenario_id"]), str(row["candidate_id"]))
        if key in map_by_candidate:
            raise ProtocolError(f"candidate_map duplicado: {key}.")
        map_by_candidate[key] = row
        scenarios_to_sites[str(row["scenario_id"])].add(str(row["site_id"]))
    if set(map_by_candidate) != set(buffers) or set(buffers) != set(geometry) or set(geometry) != set(ranking):
        raise ProtocolError("As chaves de candidato diferem entre T1, buffer, geometria e ranking.")

    candidate_results: list[dict[str, Any]] = []
    for key in sorted(buffers):
        mapping = map_by_candidate[key]
        site_id = str(mapping["site_id"])
        gt_key = (site_id, key[0])
        if gt_key not in gt_by_key:
            raise ProtocolError(f"Ground truth nao encontrado para {gt_key}.")
        gt = gt_by_key[gt_key]
        environment = str(mapping["environment_class"])
        if _environment_from_ground_truth_label(str(gt["planned_environment"])) != environment:
            raise ProtocolError(f"Estrato de campo diverge do FIELD-CAND no cenario {key[0]}.")
        candidate_results.append(
            evaluate_candidate(
                site_id=site_id,
                environment_class=environment,
                ground_truth=gt,
                buffer=buffers[key],
                polygons=geometry[key],
                ranking=ranking[key],
                config=config,
            )
        )
    if {tuple(key) for key in gt_by_key} != {
        (next(iter(sites)), scenario) for scenario, sites in scenarios_to_sites.items()
    }:
        raise ProtocolError("Ground truth e candidate_map nao possuem os mesmos quatro sites/cenarios.")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidate_results:
        grouped[row["scenario_id"]].append(row)
    scenario_results: list[dict[str, Any]] = []
    for scenario_id in sorted(grouped):
        rows = grouped[scenario_id]
        if len(rows) != config["cardinality"]["candidates_per_site"]:
            raise ProtocolError(f"Cenario {scenario_id} sem tres candidatos.")
        available_ranks = [row["truth_rank_min"] for row in rows if row["truth_rank_min"] is not None]
        scenario_results.append(
            {
                "site_id": rows[0]["site_id"],
                "scenario_id": scenario_id,
                "environment_class": rows[0]["environment_class"],
                "adaptive_candidates_covering_truth": sum(bool(row["adaptive_coverage"]) for row in rows),
                "fixed_candidates_covering_truth": sum(bool(row["fixed_coverage"]) for row in rows),
                "scenario_any_adaptive_coverage": any(bool(row["adaptive_coverage"]) for row in rows),
                "scenario_any_fixed_coverage": any(bool(row["fixed_coverage"]) for row in rows),
                "minimum_candidate_distance_to_truth_m": min(float(row["distance_candidate_to_truth_m"]) for row in rows),
                "best_within_buffer_truth_rank_min_descriptive": min(available_ranks) if available_ranks else None,
                "all_three_geo_buffers_complete": all(bool(row["geo_data_buffer_complete"]) for row in rows),
                "note": "O melhor rank e descritivo; setores de buffers distintos nao formam ranking global.",
            }
        )
    summary = aggregate_metrics(candidate_results, scenario_results, config)
    return candidate_results, scenario_results, summary


def aggregate_metrics(
    candidates: Sequence[Mapping[str, Any]],
    scenarios: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    covered = [row for row in candidates if row["adaptive_coverage"]]
    ranked_covered = [row for row in covered if row["rank_evaluable"]]
    metrics: dict[str, Any] = {
        "candidate_buffer_count": len(candidates),
        "scenario_count": len(scenarios),
        "adaptive_candidate_coverage": proportion_record(
            sum(bool(row["adaptive_coverage"]) for row in candidates), len(candidates)
        ),
        "fixed_candidate_coverage": proportion_record(
            sum(bool(row["fixed_coverage"]) for row in candidates), len(candidates)
        ),
        "scenario_any_adaptive_coverage": proportion_record(
            sum(bool(row["scenario_any_adaptive_coverage"]) for row in scenarios), len(scenarios)
        ),
        "scenario_any_fixed_coverage": proportion_record(
            sum(bool(row["scenario_any_fixed_coverage"]) for row in scenarios), len(scenarios)
        ),
        "geo_sector_coverage": proportion_record(
            sum(int(row["geo_complete_sector_count"]) for row in candidates),
            sum(int(row["geo_sector_count"]) for row in candidates),
        ),
        "geo_complete_buffers": proportion_record(
            sum(bool(row["geo_data_buffer_complete"]) for row in candidates), len(candidates)
        ),
        "boundary_assignments": {
            "set_valued_candidate_buffers": sum(int(row["relevant_sector_count"]) > 1 for row in candidates),
            "maximum_relevant_set_size": max((int(row["relevant_sector_count"]) for row in candidates), default=0),
        },
        "ranking": {
            "covered_candidate_buffers": len(covered),
            "covered_and_ranked_candidate_buffers": len(ranked_covered),
            "mrr_primary_unconditional": mean([float(row["reciprocal_rank_primary"]) for row in candidates]),
            "mrr_conservative_unconditional": mean(
                [float(row["reciprocal_rank_conservative"]) for row in candidates]
            ),
            "mrr_primary_conditional_covered": mean(
                [float(row["reciprocal_rank_primary"]) for row in covered]
            ),
            "mrr_conservative_conditional_covered": mean(
                [float(row["reciprocal_rank_conservative"]) for row in covered]
            ),
            "mrr_primary_conditional_ranked_covered": mean(
                [float(row["reciprocal_rank_primary"]) for row in ranked_covered]
            ),
            "mrr_conservative_conditional_ranked_covered": mean(
                [float(row["reciprocal_rank_conservative"]) for row in ranked_covered]
            ),
        },
        "accumulated_area": {
            "primary_mean_m2_covered_ranked": mean(
                [float(row["accumulated_area_primary_m2"]) for row in ranked_covered]
            ),
            "primary_median_m2_covered_ranked": median(
                [float(row["accumulated_area_primary_m2"]) for row in ranked_covered]
            ),
            "conservative_mean_m2_covered_ranked": mean(
                [float(row["accumulated_area_conservative_m2"]) for row in ranked_covered]
            ),
            "conservative_median_m2_covered_ranked": median(
                [float(row["accumulated_area_conservative_m2"]) for row in ranked_covered]
            ),
            "primary_mean_fraction_covered_ranked": mean(
                [float(row["accumulated_area_primary_fraction"]) for row in ranked_covered]
            ),
            "conservative_mean_fraction_covered_ranked": mean(
                [float(row["accumulated_area_conservative_fraction"]) for row in ranked_covered]
            ),
        },
        "by_environment": {},
        "interpretation_boundary": config["interpretation"],
    }
    for k in config["metrics"]["top_k"]:
        metrics["ranking"][f"top{k}_primary_unconditional"] = proportion_record(
            sum(bool(row[f"top{k}_primary"]) for row in candidates), len(candidates)
        )
        metrics["ranking"][f"top{k}_conservative_unconditional"] = proportion_record(
            sum(bool(row[f"top{k}_conservative"]) for row in candidates), len(candidates)
        )
        metrics["ranking"][f"top{k}_primary_conditional_covered"] = proportion_record(
            sum(bool(row[f"top{k}_primary"]) for row in covered), len(covered)
        )
        metrics["ranking"][f"top{k}_conservative_conditional_covered"] = proportion_record(
            sum(bool(row[f"top{k}_conservative"]) for row in covered), len(covered)
        )

    environments = sorted({str(row["environment_class"]) for row in candidates})
    for environment in environments:
        candidate_subset = [row for row in candidates if row["environment_class"] == environment]
        scenario_subset = [row for row in scenarios if row["environment_class"] == environment]
        metrics["by_environment"][environment] = {
            "candidate_adaptive_coverage": proportion_record(
                sum(bool(row["adaptive_coverage"]) for row in candidate_subset), len(candidate_subset)
            ),
            "candidate_fixed_coverage": proportion_record(
                sum(bool(row["fixed_coverage"]) for row in candidate_subset), len(candidate_subset)
            ),
            "scenario_any_adaptive_coverage": proportion_record(
                sum(bool(row["scenario_any_adaptive_coverage"]) for row in scenario_subset),
                len(scenario_subset),
            ),
            "geo_complete_buffers": proportion_record(
                sum(bool(row["geo_data_buffer_complete"]) for row in candidate_subset),
                len(candidate_subset),
            ),
        }
    return metrics


def _csv_safe_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    for row in rows:
        converted: dict[str, Any] = {}
        for key, value in row.items():
            if value is None:
                converted[key] = ""
            elif isinstance(value, bool):
                converted[key] = str(value).lower()
            else:
                converted[key] = value
        safe.append(converted)
    return safe


def evaluate_post_t3(
    *,
    t2_manifest_path: Path,
    ground_truth_path: Path,
    output_dir: Path,
    config_path: Path = DEFAULT_CONFIG,
) -> dict[str, Any]:
    if output_dir.exists():
        raise ProtocolError("Diretorio T4 ja existe; escolha um novo caminho.")
    config, config_hash = load_config(config_path)
    validate_dependencies(config, config_path)
    t2 = validate_t2_manifest(t2_manifest_path, config, config_hash)
    expected_commitment = str(t2.get("ground_truth_sha256_commitment", ""))
    ground_truth = read_ground_truth(ground_truth_path, config, expected_commitment)

    buffers_path = _find_file(t2, "primary_files", "buffer_json")
    geometry_path = _find_file(t2, "primary_files", "sector_geojson")
    ranking_path = _find_file(t2, "primary_files", "sector_ranking_csv")
    expected = config["cardinality"]
    buffers = _load_buffers(buffers_path, expected["candidate_buffers"])
    geometry = _load_sector_geometry(geometry_path, expected["expected_sectors"])
    ranking = _load_ranking(
        ranking_path, expected["expected_sectors"], expected["sectors_per_buffer"]
    )
    candidate_rows, scenario_rows, summary = evaluate_all(
        ground_truth_rows=ground_truth,
        candidate_map=t2["candidate_map"],
        buffers=buffers,
        geometry=geometry,
        ranking=ranking,
        config=config,
    )

    output_dir.mkdir(parents=True, exist_ok=False)
    candidate_path = output_dir / "candidate_sector_evaluation.csv"
    scenario_path = output_dir / "scenario_spatial_evaluation.csv"
    summary_path = output_dir / "metrics_summary.json"
    candidate_headers = list(candidate_rows[0])
    scenario_headers = list(scenario_rows[0])
    write_csv(candidate_path, candidate_headers, _csv_safe_rows(candidate_rows))
    write_csv(scenario_path, scenario_headers, _csv_safe_rows(scenario_rows))
    write_json(summary_path, summary)

    opened_at = utc_now()
    manifest: dict[str, Any] = {
        "protocol_id": config["protocol_id"],
        "script_version": SCRIPT_VERSION,
        "state": "AVALIACAO_SETORIAL_CONCLUIDA",
        "milestone": "T4",
        "generated_at_utc": utc_now(),
        "validation_modality": config["validation_modality"],
        "interpretation": config["interpretation"],
        "allowed_claim": config["freeze_policy"]["allowed_claim"],
        "forbidden_claim": config["freeze_policy"]["forbidden_claim"],
        "retuning_after_t3": False,
        "config_sha256": config_hash,
        "t2_manifest": file_record(t2_manifest_path, "t2_manifest"),
        "ground_truth_t3": {
            **file_record(ground_truth_path, "ground_truth_opened_at_t3"),
            "opened_at_utc": opened_at,
            "commitment_verified": True,
            "used_only_for_evaluation": True,
        },
        "inputs_from_t2": [
            file_record(buffers_path, "buffer_json"),
            file_record(geometry_path, "sector_geojson"),
            file_record(ranking_path, "sector_ranking_csv"),
        ],
        "outputs": [
            file_record(candidate_path, "candidate_sector_evaluation"),
            file_record(scenario_path, "scenario_spatial_evaluation"),
            file_record(summary_path, "metrics_summary"),
        ],
        "boundary_rule": config["boundary_rule"],
        "metrics_rule": config["metrics"],
        "candidate_count": len(candidate_rows),
        "scenario_count": len(scenario_rows),
        "state_history": [
            *t2["state_history"],
            {
                "milestone": "T3",
                "state": "GROUND_TRUTH_ABERTO_PARA_AVALIACAO",
                "evidence": expected_commitment,
                "opened_at_utc": opened_at,
            },
            {
                "milestone": "T4",
                "state": "AVALIACAO_SETORIAL_CONCLUIDA",
                "evidence": stable_hash(summary),
            },
        ],
    }
    manifest["manifest_payload_sha256"] = stable_hash(manifest)
    write_json(output_dir / "manifest_t4_rep_s_spatial.json", manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--t2-manifest", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = evaluate_post_t3(
            t2_manifest_path=args.t2_manifest,
            ground_truth_path=args.ground_truth,
            output_dir=args.output_dir,
            config_path=args.config,
        )
    except ProtocolError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "OK",
                "protocol_id": result["protocol_id"],
                "milestone": result["milestone"],
                "state": result["state"],
                "candidate_count": result["candidate_count"],
                "scenario_count": result["scenario_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
