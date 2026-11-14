#!/usr/bin/env python3
"""Executa e audita o processamento cego diagnóstico do cenário URBE-01.

Este invólucro não modifica o motor científico existente. A setorização, a
extração de atributos GEO e o ranking BASE são importados diretamente de
``work/ext_espacial_setores_v1_1/motor_setorizacao_priorizacao.py``. O único
cálculo acrescentado é o ranking PERFIL congelado para URBE-01.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import platform
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
MOTOR_PATH = PROJECT_ROOT / "work/ext_espacial_setores_v1_1/motor_setorizacao_priorizacao.py"
BASE_CONFIG_PATH = PROJECT_ROOT / "work/ext_espacial_setores_v1_1/config_setorizacao_priorizacao_v1_1.json"
OVERLAY_CONFIG_PATH = HERE / "config_urbe01_blind_v1.json"
PROTOCOL_PATH = HERE / "PROTOCOLO_URBE01_CEGO_v1.md"
DEFAULT_GEO_DIR = PROJECT_ROOT / "outputs/sprint2_s2_06_geo05_v33"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs/campo_urbe01/processamento_cego_v1"

SCIENTIFIC_FILES = (
    "entrada_raio_fonte.json",
    "entrada_raio_fonte.geojson",
    "manifesto_entrada_raio_fonte.json",
    "config_efetiva_urbe01_blind.json",
    "protocolo_urbe01_cego_v1.md",
    "atributos_geo_setores.csv",
    "ranking_base_original.csv",
    "ranking_perfil_urbe01.csv",
    "setores_urbe01.geojson",
    "top3_base_original.csv",
    "top3_base_original.json",
    "top3_perfil_urbe01.csv",
    "top3_perfil_urbe01.json",
    "resultado_urbe01_cego.json",
    "avisos_revisao.log",
)


def _load_motor() -> Any:
    spec = importlib.util.spec_from_file_location("motor_setorizacao_priorizacao_v1_1", MOTOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Não foi possível importar o motor: {MOTOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _relative_or_absolute(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def _file_entry(path: Path, role: str) -> dict[str, Any]:
    return {
        "role": role,
        "path": _relative_or_absolute(path),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def build_effective_config(motor: Any, overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Produz configuração efetiva sem alterar o JSON nem o motor de origem."""
    config = copy.deepcopy(motor.load_json(BASE_CONFIG_PATH))
    config["protocol_id"] = str(overlay["protocol_id"])
    config["protocol_name"] = str(overlay["protocol_name"])
    config["version"] = str(overlay["version"])
    config["engine_version"] = "1.0.0-urbe-blind-wrapper+EXT-ESP-SET-v1.1"
    config["status"] = str(overlay["status"])
    config["phase"] = "CAMPO_URBE01_CEGO"
    config["scope"]["classification"] = "CASO_UNICO_CEGO_DIAGNOSTICO_NAO_CONFIRMATORIO"
    config["scope"]["description"] = (
        "Setorização e priorização intrabuffer do raio de 2.500 m recebido da fonte para URBE-01. "
        "Executada antes da abertura da posição de referência e destinada à revisão humana."
    )
    config["dependencies"]["upstream_buffer_protocol"] = str(overlay["upstream"]["protocol_id"])
    config["ranking"]["primary_weight_set"] = "BASE"
    config["urbe01_blind_profile"] = copy.deepcopy(overlay["profile"])
    config["urbe01_profile_facts"] = copy.deepcopy(overlay["profile_facts"])
    config["urbe01_interpretation"] = copy.deepcopy(overlay["interpretation"])
    config["execution_control"] = {
        "directional_preference_applied": False,
        "ring_penalty_applied": False,
        "confirmatory_eligible": False,
        "ground_truth_used": False,
    }
    config["limitations"] = list(config.get("limitations", [])) + [
        "O caso URBE-01 utiliza um único ponto e o raio informado pela fonte; não estima a posição da vítima.",
        "O ranking PERFIL recalcula o componente territorial com pesos 35/20/25/20; somente o componente contextual C tem peso de 10% no escore final.",
        "Nem o componente territorial do PERFIL nem o componente contextual criam preferência direcional ou penalidade por anel.",
        "AP1, AP2 e AP3 são áreas analíticas para revisão humana, não probabilidades nem detecções.",
    ]
    motor.validate_firewall_config(config)
    return config


def build_source_radius_inputs(
    motor: Any,
    output_dir: Path,
    config: Mapping[str, Any],
    overlay: Mapping[str, Any],
) -> tuple[Path, Path, Path]:
    upstream = overlay["upstream"]
    lat = float(upstream["estimated_lat"])
    lon = float(upstream["estimated_lon"])
    radius = float(upstream["source_radius_m"])
    row_basis = {
        "protocol_id": upstream["protocol_id"],
        "scenario_id": upstream["scenario_id"],
        "candidate_id": upstream["candidate_id"],
        "estimated_lat": lat,
        "estimated_lon": lon,
        "adaptive_radius_m": radius,
        "radius_origin": "INFORMADO_PELA_FONTE",
        "source_timestamp_local": upstream["source_timestamp_local"],
        "source_record_origin": upstream["source_record_origin"],
        "source_metadata_verification": upstream["source_metadata_verification"],
        "detection_quality": None,
        "review_status": upstream["review_status"],
        "execution_classification": upstream["execution_classification"],
        "confirmatory_eligible": False,
        "ground_truth_used": False,
    }
    row = dict(row_basis)
    row["buffer_area_m2"] = math.pi * radius * radius
    row["source_row_hash"] = _canonical_hash(row_basis)
    buffer_doc = {
        "protocol_id": upstream["protocol_id"],
        "protocol_version": "1.0",
        "scenario_count": 1,
        "record_count": 1,
        "execution_classification": upstream["execution_classification"],
        "confirmatory_eligible": False,
        "ground_truth_used": False,
        "results": [row],
    }

    ring: list[list[float]] = []
    for index in range(144):
        point_lat, point_lon = motor.destination(lat, lon, radius, index * 360.0 / 144.0)
        ring.append([point_lon, point_lat])
    ring.append(ring[0])
    buffer_geojson = {
        "type": "FeatureCollection",
        "name": str(upstream["protocol_id"]),
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "ground_truth_used": False,
        "features": [
            {
                "type": "Feature",
                "id": f"{upstream['scenario_id']}::{upstream['candidate_id']}",
                "properties": {
                    "protocol_id": upstream["protocol_id"],
                    "scenario_id": upstream["scenario_id"],
                    "candidate_id": upstream["candidate_id"],
                    "radius_m": radius,
                    "radius_origin": "INFORMADO_PELA_FONTE",
                    "confirmatory_eligible": False,
                    "ground_truth_used": False,
                },
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        ],
    }

    json_path = output_dir / "entrada_raio_fonte.json"
    geojson_path = output_dir / "entrada_raio_fonte.geojson"
    manifest_path = output_dir / "manifesto_entrada_raio_fonte.json"
    motor.enforce_ground_truth_firewall(buffer_doc, config)
    motor.enforce_ground_truth_firewall(buffer_geojson, config)
    motor.write_json(json_path, buffer_doc)
    motor.write_json(geojson_path, buffer_geojson)
    source_manifest = {
        "protocol_id": upstream["protocol_id"],
        "record_count": 1,
        "ground_truth_used": False,
        "files": [
            {"role": "output", "path": json_path.name, "sha256": _sha256(json_path), "bytes": json_path.stat().st_size},
            {"role": "output", "path": geojson_path.name, "sha256": _sha256(geojson_path), "bytes": geojson_path.stat().st_size},
        ],
    }
    motor.enforce_ground_truth_firewall(source_manifest, config)
    motor.write_json(manifest_path, source_manifest)
    return json_path, geojson_path, manifest_path


def calculate_profile_ranking(
    ranked_base: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Aplica literalmente a fórmula PERFIL congelada, sem azimute ou anel."""
    decimals = int(config["ranking"]["score_comparison_decimals"])
    low_margin = float(config["ranking"]["low_margin_threshold"])
    rows: list[dict[str, Any]] = []
    for original in ranked_base:
        row = dict(original)
        required = {
            "GEO02": row.get("geo02_score"),
            "GEO03": row.get("geo03_score"),
            "GEO04": row.get("geo04_score"),
            "GEO05": row.get("geo05_score"),
            "dwater": row.get("water_distance_m"),
            "water_wetland_prop": row.get("water_wetland_prop"),
            "road_density": row.get("road_density_km_km2"),
        }
        if any(value is None for value in required.values()):
            profile_base = awater = aisolation = context = final = None
        else:
            geo02 = float(required["GEO02"])
            geo03 = float(required["GEO03"])
            geo04 = float(required["GEO04"])
            geo05 = float(required["GEO05"])
            dwater = max(0.0, float(required["dwater"]))
            water_prop = min(1.0, max(0.0, float(required["water_wetland_prop"])))
            road_density = max(0.0, float(required["road_density"]))
            profile_base = 0.35 * geo02 + 0.20 * geo03 + 0.25 * geo04 + 0.20 * geo05
            awater = math.exp(-dwater / 750.0) * geo03 * (1.0 - water_prop)
            aisolation = geo02 * (1.0 - min(road_density / 4.0, 1.0))
            context = 0.60 * awater + 0.40 * aisolation
            final = 0.90 * profile_base + 0.10 * context
        row["profile_base_score"] = round(profile_base, decimals) if profile_base is not None else None
        row["profile_awater"] = round(awater, decimals) if awater is not None else None
        row["profile_aisolation"] = round(aisolation, decimals) if aisolation is not None else None
        row["profile_context_score"] = round(context, decimals) if context is not None else None
        row["profile_final_score"] = round(final, decimals) if final is not None else None
        row["profile_context_maximum_weight"] = 0.10
        row["profile_directional_preference_applied"] = False
        row["profile_ring_penalty_applied"] = False
        row["profile_rank_within_buffer"] = None
        row["profile_selected_sector"] = False
        row["ground_truth_used"] = False
        rows.append(row)

    scores = [float(row["profile_final_score"]) for row in rows if row["profile_final_score"] is not None]
    for row in rows:
        score = row["profile_final_score"]
        if score is not None:
            row["profile_rank_within_buffer"] = 1 + sum(1 for other in scores if other > float(score))

    complete = sorted(
        [row for row in rows if row["profile_final_score"] is not None],
        key=lambda row: (-float(row["profile_final_score"]), str(row["sector_id"])),
    )
    top_rank_ids = [str(row["sector_id"]) for row in complete if row["profile_rank_within_buffer"] == 1]
    unique_top = len(top_rank_ids) == 1
    margin = (
        0.0
        if len(top_rank_ids) > 1
        else float(complete[0]["profile_final_score"]) - float(complete[1]["profile_final_score"])
        if len(complete) >= 2
        else float(complete[0]["profile_final_score"])
        if complete
        else None
    )
    base_top_ids = sorted(str(row["sector_id"]) for row in rows if row.get("base_top_member"))
    profile_top_id = top_rank_ids[0] if unique_top else None
    base_top_id = base_top_ids[0] if len(base_top_ids) == 1 else None
    ranking_changed = base_top_id != profile_top_id
    warnings: list[str] = ["UPSTREAM_REVIEW_REQUIRED"]
    if not complete:
        warnings.append("PROFILE_INCOMPLETE")
    if not unique_top:
        warnings.append("PROFILE_TOP_TIE_OR_MISSING")
    if margin is not None and margin < low_margin:
        warnings.append("PROFILE_LOW_MARGIN")
    if ranking_changed:
        warnings.append("PROFILE_TOP1_DIFFERS_FROM_BASE")
    for row in rows:
        row["profile_top_ids"] = top_rank_ids
        row["profile_top_unique"] = unique_top
        row["profile_selected_sector"] = unique_top and str(row["sector_id"]) == profile_top_id
        row["profile_margin"] = round(margin, decimals) if margin is not None else None
        row["profile_top1_differs_from_base"] = ranking_changed
        row["profile_decision_status"] = "REVISAR"
        row["profile_warning_codes"] = ";".join(warnings)
        row["profile_score_interpretation"] = "PRIORIDADE_ANALITICA_TERRITORIAL_NAO_PROBABILIDADE"
    return sorted(
        rows,
        key=lambda row: (
            row["profile_rank_within_buffer"] is None,
            row["profile_rank_within_buffer"] if row["profile_rank_within_buffer"] is not None else 10**9,
            str(row["sector_id"]),
        ),
    )


def _top3_rows(rows: Sequence[Mapping[str, Any]], mode: str) -> list[dict[str, Any]]:
    if mode == "BASE":
        score_field, rank_field = "score_base", "rank_base_within_buffer"
    else:
        score_field, rank_field = "profile_final_score", "profile_rank_within_buffer"
    ordered = sorted(
        [row for row in rows if row.get(score_field) is not None],
        key=lambda row: (-float(row[score_field]), str(row["sector_id"])),
    )[:3]
    top3: list[dict[str, Any]] = []
    for order, row in enumerate(ordered, start=1):
        top3.append(
            {
                "area_label": f"AP{order}",
                "presentation_order": order,
                "presentation_order_is_tie_break": False,
                "ranking_mode": mode,
                "scenario_id": row["scenario_id"],
                "candidate_id": row["candidate_id"],
                "sector_id": row["sector_id"],
                "analytical_rank": row.get(rank_field),
                "score": row.get(score_field),
                "ring_id": row["ring_id"],
                "direction": row["direction"],
                "representative_lat": row["representative_lat"],
                "representative_lon": row["representative_lon"],
                "inner_radius_m": row["inner_radius_m"],
                "outer_radius_m": row["outer_radius_m"],
                "geo02_score": row.get("geo02_score"),
                "geo03_score": row.get("geo03_score"),
                "geo04_score": row.get("geo04_score"),
                "geo05_score": row.get("geo05_score"),
                "barrier_flags": row.get("barrier_flags"),
                "decision_status": row.get("buffer_decision_status") if mode == "BASE" else row.get("profile_decision_status"),
                "score_interpretation": "PRIORIDADE_ANALITICA_TERRITORIAL_NAO_PROBABILIDADE",
                "confirmatory_eligible": False,
                "ground_truth_used": False,
            }
        )
    return top3


def _clean_feature_rows(features: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            key: value
            for key, value in row.items()
            if key not in {"geometry", "geometry_coordinates", "sample_points"} and not key.startswith("_")
        }
        for row in features
    ]


def build_scientific_outputs(
    motor: Any,
    output_dir: Path,
    roads_path: Path,
    hydro_path: Path,
    dem_dir: Path,
    worldcover_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    overlay = _load_json(OVERLAY_CONFIG_PATH)
    config = build_effective_config(motor, overlay)
    config_path = output_dir / "config_efetiva_urbe01_blind.json"
    motor.write_json(config_path, config)
    shutil.copyfile(PROTOCOL_PATH, output_dir / "protocolo_urbe01_cego_v1.md")

    buffer_json_path, buffer_geojson_path, buffer_manifest_path = build_source_radius_inputs(
        motor, output_dir, config, overlay
    )
    buffer_doc = motor.load_json(buffer_json_path)
    buffer_geojson = motor.load_json(buffer_geojson_path)
    buffer_manifest = motor.load_json(buffer_manifest_path)
    buffer_rows = motor.validate_buffer_contract(
        buffer_doc,
        buffer_geojson,
        buffer_manifest,
        buffer_json_path,
        buffer_geojson_path,
        config,
    )
    sectors = motor.make_sector_records(buffer_rows, config)
    if len(sectors) != 24:
        raise RuntimeError(f"Esperados 24 setores; recebidos {len(sectors)}")

    roads, road_timestamp = motor.load_road_segments(roads_path, config)
    hydros, hydro_timestamp = motor.load_hydro_segments(hydro_path, config)
    cell_deg = float(config["feature_extraction"]["spatial_index_cell_deg"])
    road_index = motor.SpatialSegmentIndex(roads, cell_deg)
    hydro_index = motor.SpatialSegmentIndex(hydros, cell_deg)
    hgt = motor.HGTSampler(dem_dir)
    world_cover = motor.WorldCoverSampler(worldcover_dir)
    try:
        features = motor.extract_sector_features(
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

    ranked_base = motor.rank_sector_records(features, config)
    ranked_profile = calculate_profile_ranking(ranked_base, config)
    top3_base = _top3_rows(ranked_base, "BASE")
    top3_profile = _top3_rows(ranked_profile, "PERFIL")

    ranked_by_id = {str(row["sector_id"]): row for row in ranked_base}
    profile_by_id = {str(row["sector_id"]): row for row in ranked_profile}
    geometry_doc = motor.build_sector_geojson(sectors, config, ranked_by_id)
    for feature in geometry_doc["features"]:
        row = profile_by_id[str(feature["id"])]
        feature["properties"].update(
            {
                "profile_base_score": row["profile_base_score"],
                "profile_awater": row["profile_awater"],
                "profile_aisolation": row["profile_aisolation"],
                "profile_context_score": row["profile_context_score"],
                "profile_final_score": row["profile_final_score"],
                "profile_rank_within_buffer": row["profile_rank_within_buffer"],
                "profile_selected_sector": row["profile_selected_sector"],
                "profile_directional_preference_applied": False,
                "profile_ring_penalty_applied": False,
            }
        )

    feature_rows = _clean_feature_rows(features)
    result_doc = {
        "protocol_id": config["protocol_id"],
        "engine_version": config["engine_version"],
        "upstream_protocol_id": config["dependencies"]["upstream_buffer_protocol"],
        "scenario_id": "URBE-01",
        "candidate_id": "URBE-01-E0",
        "execution_classification": "CAMPO_CEGO_DIAGNOSTICO_RAIO_DA_FONTE",
        "review_status": "REVISAR",
        "confirmatory_eligible": False,
        "ground_truth_used": False,
        "received_point": {
            "estimated_lat": 0.015833,
            "estimated_lon": -51.068056,
            "radius_m": 2500.0,
            "radius_origin": "INFORMADO_PELA_FONTE",
        },
        "sector_count": len(sectors),
        "ranking_scope": "WITHIN_RECEIVED_SOURCE_RADIUS_ONLY",
        "directional_preference_applied": False,
        "ring_penalty_applied": False,
        "base_method": "BASE_ORIGINAL_EXT_ESP_SET_v1_1",
        "profile_method": copy.deepcopy(_load_json(OVERLAY_CONFIG_PATH)["profile"]),
        "profile_facts": copy.deepcopy(_load_json(OVERLAY_CONFIG_PATH)["profile_facts"]),
        "top3_base": top3_base,
        "top3_profile": top3_profile,
        "base_results": ranked_base,
        "profile_results": ranked_profile,
        "interpretation": {
            "score": "PRIORIDADE_ANALITICA_TERRITORIAL_NAO_PROBABILIDADE",
            "areas": "AP1_AP2_AP3_EXIGEM_REVISAO_HUMANA",
            "operational_command": False,
        },
    }

    for value in (feature_rows, ranked_base, ranked_profile, geometry_doc, top3_base, top3_profile, result_doc):
        motor.enforce_ground_truth_firewall(value, config)

    motor.write_csv(output_dir / "atributos_geo_setores.csv", feature_rows)
    motor.write_csv(output_dir / "ranking_base_original.csv", ranked_base)
    motor.write_csv(output_dir / "ranking_perfil_urbe01.csv", ranked_profile)
    motor.write_json(output_dir / "setores_urbe01.geojson", geometry_doc)
    motor.write_csv(output_dir / "top3_base_original.csv", top3_base)
    motor.write_json(
        output_dir / "top3_base_original.json",
        {"ranking_mode": "BASE", "ground_truth_used": False, "areas": top3_base},
    )
    motor.write_csv(output_dir / "top3_perfil_urbe01.csv", top3_profile)
    motor.write_json(
        output_dir / "top3_perfil_urbe01.json",
        {"ranking_mode": "PERFIL", "ground_truth_used": False, "areas": top3_profile},
    )
    motor.write_json(output_dir / "resultado_urbe01_cego.json", result_doc)

    base_first = ranked_base[0]
    profile_first = ranked_profile[0]
    warning_lines = [
        "URBE-01|URBE-01-E0|REVISAR|EXECUCAO_DIAGNOSTICA_NAO_CONFIRMATORIA",
        f"BASE|{base_first.get('sector_id')}|{base_first.get('buffer_warning_codes')}",
        f"PERFIL|{profile_first.get('sector_id')}|{profile_first.get('profile_warning_codes')}",
        "INTERPRETACAO|AP1_AP2_AP3_SAO_AREAS_ANALITICAS_NAO_PROBABILIDADES_OU_DETECCOES",
    ]
    _write_text(output_dir / "avisos_revisao.log", "\n".join(warning_lines) + "\n")

    return {
        "config": config,
        "buffer_rows": buffer_rows,
        "sectors": sectors,
        "features": features,
        "ranked_base": ranked_base,
        "ranked_profile": ranked_profile,
        "top3_base": top3_base,
        "top3_profile": top3_profile,
    }


def _compare_runs(run1: Path, run2: Path) -> dict[str, Any]:
    comparisons: list[dict[str, Any]] = []
    all_equal = True
    for name in SCIENTIFIC_FILES:
        first = run1 / name
        second = run2 / name
        if not first.exists() or not second.exists():
            equal = False
            hash1 = _sha256(first) if first.exists() else None
            hash2 = _sha256(second) if second.exists() else None
        else:
            hash1 = _sha256(first)
            hash2 = _sha256(second)
            equal = hash1 == hash2
        all_equal = all_equal and equal
        comparisons.append({"file": name, "run1_sha256": hash1, "run2_sha256": hash2, "equal": equal})
    return {
        "test": "DUAS_EXECUCOES_INDEPENDENTES_MESMAS_ENTRADAS",
        "status": "PASS" if all_equal else "FAIL",
        "all_scientific_files_equal": all_equal,
        "compared_file_count": len(comparisons),
        "ground_truth_used": False,
        "files": comparisons,
    }


def _validate_outputs(
    motor: Any,
    run: Mapping[str, Any],
    output_dir: Path,
    determinism: Mapping[str, Any],
) -> dict[str, Any]:
    ranked_base = run["ranked_base"]
    ranked_profile = run["ranked_profile"]
    top3_base = run["top3_base"]
    top3_profile = run["top3_profile"]
    sectors = run["sectors"]
    features = run["features"]
    gates = {
        "sector_count_is_24": len(sectors) == 24,
        "feature_count_is_24": len(features) == 24,
        "base_rank_count_is_24": len(ranked_base) == 24,
        "profile_rank_count_is_24": len(ranked_profile) == 24,
        "top3_base_count_is_3": len(top3_base) == 3,
        "top3_profile_count_is_3": len(top3_profile) == 3,
        "all_geo_complete": all(float(row.get("geo_completeness", 0.0)) == 1.0 for row in features),
        "all_scores_in_unit_interval": all(
            row.get("profile_final_score") is not None and 0.0 <= float(row["profile_final_score"]) <= 1.0
            for row in ranked_profile
        ),
        "no_directional_preference": all(row["profile_directional_preference_applied"] is False for row in ranked_profile),
        "no_ring_penalty": all(row["profile_ring_penalty_applied"] is False for row in ranked_profile),
        "all_control_flags_false": all(row.get("ground_truth_used") is False for row in ranked_profile),
        "deterministic_repeat_matches": determinism["status"] == "PASS",
        "scientific_files_present": all((output_dir / name).exists() for name in SCIENTIFIC_FILES),
    }
    status = "PASS" if all(gates.values()) else "FAIL"
    report = {
        "protocol_id": run["config"]["protocol_id"],
        "status": status,
        "gate_count": len(gates),
        "passed_gate_count": sum(bool(value) for value in gates.values()),
        "gates": gates,
        "ground_truth_used": False,
    }
    motor.enforce_ground_truth_firewall(report, run["config"])
    if status != "PASS":
        failed = [name for name, value in gates.items() if not value]
        raise RuntimeError(f"Falha nos gates de QA: {', '.join(failed)}")
    return report


def _write_execution_report(
    output_dir: Path,
    run: Mapping[str, Any],
    determinism: Mapping[str, Any],
    qa: Mapping[str, Any],
) -> None:
    base = run["top3_base"]
    profile = run["top3_profile"]
    lines = [
        "# Relatório de execução — URBE-01 processamento cego v1.0",
        "",
        "## Resultado da execução",
        "",
        "- classificação: diagnóstica e não confirmatória;",
        "- situação: revisar;",
        "- ponto processado: URBE-01-E0;",
        "- raio recebido da fonte: 2.500 m;",
        "- setores produzidos: 24;",
        "- preferência direcional: não aplicada;",
        "- penalidade por anel: não aplicada;",
        "- posição de referência usada no processamento: não.",
        "",
        "## Top 3 — BASE original",
        "",
        "| Área | Setor | Posto | Escore |",
        "|---|---|---:|---:|",
    ]
    for row in base:
        lines.append(f"| {row['area_label']} | {row['sector_id']} | {row['analytical_rank']} | {float(row['score']):.9f} |")
    lines.extend(
        [
            "",
            "## Top 3 — PERFIL URBE-01",
            "",
            "| Área | Setor | Posto | Escore |",
            "|---|---|---:|---:|",
        ]
    )
    for row in profile:
        lines.append(f"| {row['area_label']} | {row['sector_id']} | {row['analytical_rank']} | {float(row['score']):.9f} |")
    lines.extend(
        [
            "",
            "## Controle de reprodutibilidade e QA",
            "",
            f"- duas execuções independentes: **{determinism['status']}**;",
            f"- arquivos científicos idênticos: {determinism['all_scientific_files_equal']};",
            f"- gates de QA: **{qa['passed_gate_count']}/{qa['gate_count']} ({qa['status']})**.",
            "",
            "## Interpretação",
            "",
            "AP1, AP2 e AP3 são áreas de prioridade analítica para revisão humana. Os escores não representam probabilidade de presença, detecção ou localização determinada da vítima. A eventual comparação posterior deve usar saídas já congeladas e ocorrer fora deste processamento.",
            "",
        ]
    )
    _write_text(output_dir / "relatorio_execucao_urbe01.md", "\n".join(lines))


def _write_manifest(
    motor: Any,
    output_dir: Path,
    run: Mapping[str, Any],
    roads_path: Path,
    hydro_path: Path,
    dem_dir: Path,
    worldcover_dir: Path,
    elapsed_seconds: float,
) -> Path:
    determinism_path = output_dir / "relatorio_determinismo.json"
    determinism = _load_json(determinism_path)
    run1_hashes = {
        str(item["file"]): str(item["run1_sha256"])
        for item in determinism.get("files", [])
    }
    if set(run1_hashes) != set(SCIENTIFIC_FILES):
        raise RuntimeError("Relatório de determinismo não cobre exatamente os artefatos científicos congelados")
    for name in SCIENTIFIC_FILES:
        current_hash = _sha256(output_dir / name)
        if current_hash != run1_hashes[name]:
            raise RuntimeError(f"Hash publicado diverge do run1 antes do manifesto: {name}")

    input_files = [
        _file_entry(MOTOR_PATH, "engine_imported_unchanged"),
        _file_entry(BASE_CONFIG_PATH, "base_config_source"),
        _file_entry(OVERLAY_CONFIG_PATH, "urbe01_config_source"),
        _file_entry(PROTOCOL_PATH, "protocol_source"),
        _file_entry(roads_path, "source_geo02_osm"),
        _file_entry(hydro_path, "source_geo03_osm"),
    ]
    for path in sorted(dem_dir.glob("*.hgt.gz")):
        input_files.append(_file_entry(path, "source_geo04_dem"))
    for path in sorted(worldcover_dir.glob("*.tif")):
        input_files.append(_file_entry(path, "source_geo05_worldcover"))
    output_files = [
        _file_entry(path, "output")
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path.name != "manifesto_processamento_cego.json"
    ]
    scientific_hashes = {name: _sha256(output_dir / name) for name in SCIENTIFIC_FILES}
    manifest = {
        "protocol_id": run["config"]["protocol_id"],
        "upstream_protocol_id": run["config"]["dependencies"]["upstream_buffer_protocol"],
        "engine_version": run["config"]["engine_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python_version": platform.python_version(),
        "execution_classification": "CAMPO_CEGO_DIAGNOSTICO_RAIO_DA_FONTE",
        "review_status": "REVISAR",
        "confirmatory_eligible": False,
        "ground_truth_used": False,
        "sector_count": len(run["sectors"]),
        "scientific_projection_sha256": _canonical_hash(scientific_hashes),
        "determinism_run1_hashes_match_published_outputs": True,
        "determinism_compared_file_count": len(SCIENTIFIC_FILES),
        "elapsed_seconds_two_runs_and_qa": round(elapsed_seconds, 3),
        "files": input_files + output_files,
    }
    motor.enforce_ground_truth_firewall(manifest, run["config"])
    path = output_dir / "manifesto_processamento_cego.json"
    motor.write_json(path, manifest)
    return path


def _verify_published_hash_chain(output_dir: Path, manifest_path: Path) -> dict[str, Any]:
    """Exige igualdade run1 = arquivo final = hash registrado no manifesto."""
    determinism = _load_json(output_dir / "relatorio_determinismo.json")
    manifest = _load_json(manifest_path)
    run1 = {str(item["file"]): str(item["run1_sha256"]) for item in determinism.get("files", [])}
    manifest_outputs: dict[str, str] = {}
    for item in manifest.get("files", []):
        if item.get("role") == "output":
            manifest_outputs[Path(str(item["path"])).name] = str(item["sha256"])
    checks: list[dict[str, Any]] = []
    for name in SCIENTIFIC_FILES:
        actual = _sha256(output_dir / name)
        run1_hash = run1.get(name)
        manifest_hash = manifest_outputs.get(name)
        equal = bool(actual == run1_hash == manifest_hash)
        checks.append(
            {
                "file": name,
                "run1_sha256": run1_hash,
                "published_sha256": actual,
                "manifest_sha256": manifest_hash,
                "all_equal": equal,
            }
        )
    status = "PASS" if len(checks) == len(SCIENTIFIC_FILES) and all(item["all_equal"] for item in checks) else "FAIL"
    if status != "PASS":
        failed = [item["file"] for item in checks if not item["all_equal"]]
        raise RuntimeError(f"Cadeia de hashes run1/publicado/manifesto diverge: {', '.join(failed)}")
    return {
        "status": status,
        "checked_file_count": len(checks),
        "relation": "RUN1_SHA256_EQUALS_PUBLISHED_SHA256_EQUALS_MANIFEST_SHA256",
        "files": checks,
    }


def run_twice_and_publish(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    motor = _load_motor()
    output_dir = Path(args.output_dir).resolve()
    roads_path = Path(args.roads).resolve()
    hydro_path = Path(args.hydro).resolve()
    dem_dir = Path(args.dem_dir).resolve()
    worldcover_dir = Path(args.worldcover_dir).resolve()
    for required in (roads_path, hydro_path, dem_dir, worldcover_dir, MOTOR_PATH, BASE_CONFIG_PATH, OVERLAY_CONFIG_PATH, PROTOCOL_PATH):
        if not required.exists():
            raise FileNotFoundError(required)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Remove somente os artefatos pertencentes a esta versão, preservando qualquer arquivo alheio.
    owned = set(SCIENTIFIC_FILES) | {
        "relatorio_determinismo.json",
        "relatorio_qa.json",
        "relatorio_execucao_urbe01.md",
        "manifesto_processamento_cego.json",
    }
    for name in owned:
        path = output_dir / name
        if path.exists() and path.is_file():
            path.unlink()

    run1 = build_scientific_outputs(motor, output_dir, roads_path, hydro_path, dem_dir, worldcover_dir)
    with tempfile.TemporaryDirectory(prefix="urbe01_blind_repeat_") as temporary:
        second_dir = Path(temporary)
        build_scientific_outputs(motor, second_dir, roads_path, hydro_path, dem_dir, worldcover_dir)
        determinism = _compare_runs(output_dir, second_dir)
    if determinism["status"] != "PASS":
        raise RuntimeError("As duas execuções não produziram artefatos científicos idênticos")
    motor.write_json(output_dir / "relatorio_determinismo.json", determinism)

    qa = _validate_outputs(motor, run1, output_dir, determinism)
    motor.write_json(output_dir / "relatorio_qa.json", qa)
    _write_execution_report(output_dir, run1, determinism, qa)
    manifest_path = _write_manifest(
        motor,
        output_dir,
        run1,
        roads_path,
        hydro_path,
        dem_dir,
        worldcover_dir,
        time.perf_counter() - started,
    )
    hash_chain = _verify_published_hash_chain(output_dir, manifest_path)
    return {
        "status": "PASS",
        "output_dir": str(output_dir),
        "manifest": str(manifest_path),
        "determinism": determinism["status"],
        "qa": qa["status"],
        "published_hash_chain": hash_chain["status"],
        "published_hash_chain_file_count": hash_chain["checked_file_count"],
        "sector_count": len(run1["sectors"]),
        "top3_base": run1["top3_base"],
        "top3_profile": run1["top3_profile"],
        "ground_truth_used": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--roads", default=str(DEFAULT_GEO_DIR / "osm_highways_raw.json"))
    parser.add_argument("--hydro", default=str(DEFAULT_GEO_DIR / "osm_hydrography_raw.json"))
    parser.add_argument("--dem-dir", default=str(DEFAULT_GEO_DIR))
    parser.add_argument("--worldcover-dir", default=str(DEFAULT_GEO_DIR / "worldcover_tiles"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_twice_and_publish(args)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
