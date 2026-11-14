#!/usr/bin/env python3
"""Executa e audita o nucleo territorial cego do cenario MATA-01.

O invólucro importa, sem alteracao, o motor EXT-ESP-SET-v1.1. O raio de
5 km e tratado como dominio operacional informado pela fonte, e nao como
resultado do buffer adaptativo. Perfil, pistas, fotografias e qualquer
posicao declarada do alvo simulado permanecem fora do calculo.
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
OVERLAY_CONFIG_PATH = HERE / "config_mata01_blind_v1.json"
PROTOCOL_PATH = HERE / "PROTOCOLO_MATA01_CEGO_v1.md"
DEFAULT_GEO_DIR = PROJECT_ROOT / "outputs/sprint2_s2_06_geo05_v33"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs/campo_mata01/processamento_cego_v1"

SCIENTIFIC_FILES = (
    "entrada_raio_fonte_mata01.json",
    "entrada_raio_fonte_mata01.geojson",
    "manifesto_entrada_raio_fonte_mata01.json",
    "config_efetiva_mata01_blind.json",
    "protocolo_mata01_cego_v1.md",
    "atributos_geo_setores_mata01.csv",
    "ranking_base_original_abstido_mata01.csv",
    "ranking_base_disponiveis_mata01.csv",
    "setores_mata01.geojson",
    "top3_base_disponiveis_mata01.csv",
    "top3_base_disponiveis_mata01.json",
    "resultado_mata01_cego.json",
    "avisos_revisao.log",
)


def _load_motor() -> Any:
    spec = importlib.util.spec_from_file_location("motor_setorizacao_priorizacao_v1_1_mata01", MOTOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Nao foi possivel importar o motor: {MOTOR_PATH}")
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
    config = copy.deepcopy(motor.load_json(BASE_CONFIG_PATH))
    config["protocol_id"] = str(overlay["protocol_id"])
    config["protocol_name"] = str(overlay["protocol_name"])
    config["version"] = str(overlay["version"])
    config["engine_version"] = "1.0.0-mata01-blind-wrapper+EXT-ESP-SET-v1.1"
    config["status"] = str(overlay["status"])
    config["phase"] = "CAMPO_MATA01_CEGO"
    config["scope"]["classification"] = "CASO_UNICO_CEGO_DIAGNOSTICO_NAO_CONFIRMATORIO"
    config["scope"]["description"] = (
        "Setorizacao e priorizacao territorial do dominio de 5.000 m informado para MATA-01, "
        "sem buffer adaptativo e sem acesso a qualquer posicao declarada do alvo simulado."
    )
    config["dependencies"]["upstream_buffer_protocol"] = str(overlay["upstream"]["protocol_id"])
    config["ranking"]["primary_weight_set"] = "BASE"
    sampling = overlay["raster_sampling_override"]
    config["feature_extraction"]["raster_sampling"] = {
        "method": sampling["method"],
        "radial_samples": int(sampling["radial_samples"]),
        "angular_samples": int(sampling["angular_samples"]),
        "samples_per_sector": int(sampling["samples_per_sector"]),
        "nominal_cell_area_m2": float(sampling["nominal_cell_area_m2"]),
        "nominal_linear_support_m": float(sampling["nominal_linear_support_m"]),
    }
    # A configuracao de origem descreve o amostrador padrao de nove pontos.
    # MATA-01 substitui esse amostrador por 3.600 pontos por setor; portanto,
    # a descricao metodologica precisa acompanhar a configuracao realmente
    # executada para nao deixar uma contradicao no artefato de auditoria.
    config["feature_extraction"]["geo04_method"] = (
        "Media de 3.600 amostras deterministicas estratificadas por setor; "
        "em cada amostra, declividade Horn 3 x 3 e elevacao SRTMGL1/Mapzen."
    )
    config["feature_extraction"]["geo05_method"] = (
        "Media ponderada das classes em 3.600 amostras deterministicas "
        "estratificadas por setor do ESA WorldCover 2021 v200."
    )
    config["feature_extraction"]["limitations"] = [
        "A alocacao linear por subsegmentos e uma aproximacao deterministica de desenvolvimento.",
        "As 3.600 amostras raster por setor representam amostragem areal estratificada, nao censo de todos os pixels.",
        "As fontes publicas nao comprovam transitabilidade nem condicao territorial atual.",
    ]
    config["mata01_source_input"] = copy.deepcopy(overlay["upstream"])
    config["mata01_context_boundary"] = copy.deepcopy(overlay["context_boundary"])
    config["mata01_source_snapshot"] = copy.deepcopy(overlay["source_snapshot"])
    config["mata01_interpretation"] = copy.deepcopy(overlay["interpretation"])
    config["execution_control"] = {
        "direct_source_radius_used": True,
        "adaptive_buffer_engine_used": False,
        "missing_detection_quality_imputed": False,
        "profile_used_in_quantitative_ranking": False,
        "directional_preference_applied": False,
        "ring_penalty_applied": False,
        "photographs_used_in_quantitative_ranking": False,
        "confirmatory_eligible": False,
        "ground_truth_used": False,
    }
    config["limitations"] = list(config.get("limitations", [])) + [
        "MATA-01 usa um unico ponto e o dominio direto de 5 km informado pelo pesquisador; o motor nao estimou esse raio.",
        "A qualidade de deteccao nao estava disponivel e nenhum valor foi imputado.",
        "Perfil, pista ao Norte, habito de buscar agua e fotografias permanecem contextuais e nao alteram este ranking.",
        "OSM e instantaneo de cartografia voluntaria; WorldCover representa 2021; nenhuma camada comprova condicao atual ou transitabilidade sob o dossel.",
        "AP1, AP2 e AP3 sao areas analiticas para revisao humana, nao probabilidades, deteccoes ou ordens operacionais.",
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
        "radius_origin": upstream["radius_origin"],
        "radius_method": upstream["radius_method"],
        "r0_semantics": upstream["r0_semantics"],
        "additional_factors_applied_by_engine": upstream["additional_factors_applied_by_engine"],
        "detection_quality": None,
        "detection_quality_imputed": False,
        "radius_rationale": upstream["radius_rationale"],
        "event_timestamp_local": upstream["event_timestamp_local"],
        "coordinate_capture_timestamp_local": upstream["coordinate_capture_timestamp_local"],
        "source_record_origin": upstream["source_record_origin"],
        "point_semantics": upstream["point_semantics"],
        "source_metadata_verification": upstream["source_metadata_verification"],
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
        "radius_m": radius,
        "radius_origin": upstream["radius_origin"],
        "radius_method": upstream["radius_method"],
        "r0_semantics": upstream["r0_semantics"],
        "additional_factors_applied_by_engine": False,
        "detection_quality_available": False,
        "detection_quality_imputed": False,
        "adaptive_buffer_status": "NAO_EXECUTADO_ENTRADA_INSUFICIENTE",
        "radius_review_status": upstream["review_status"],
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
                    "radius_origin": upstream["radius_origin"],
                    "radius_method": upstream["radius_method"],
                    "r0_semantics": upstream["r0_semantics"],
                    "additional_factors_applied_by_engine": False,
                    "review_status": upstream["review_status"],
                    "confirmatory_eligible": False,
                    "ground_truth_used": False,
                },
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        ],
    }

    json_path = output_dir / "entrada_raio_fonte_mata01.json"
    geojson_path = output_dir / "entrada_raio_fonte_mata01.geojson"
    manifest_path = output_dir / "manifesto_entrada_raio_fonte_mata01.json"
    motor.enforce_ground_truth_firewall(buffer_doc, config)
    motor.enforce_ground_truth_firewall(buffer_geojson, config)
    motor.write_json(json_path, buffer_doc)
    motor.write_json(geojson_path, buffer_geojson)
    source_manifest = {
        "protocol_id": upstream["protocol_id"],
        "record_count": 1,
        "radius_m": radius,
        "radius_origin": upstream["radius_origin"],
        "radius_method": upstream["radius_method"],
        "r0_semantics": upstream["r0_semantics"],
        "additional_factors_applied_by_engine": False,
        "detection_quality_imputed": False,
        "adaptive_buffer_status": "NAO_EXECUTADO_ENTRADA_INSUFICIENTE",
        "radius_review_status": upstream["review_status"],
        "ground_truth_used": False,
        "files": [
            {"role": "output", "path": json_path.name, "sha256": _sha256(json_path), "bytes": json_path.stat().st_size},
            {"role": "output", "path": geojson_path.name, "sha256": _sha256(geojson_path), "bytes": geojson_path.stat().st_size},
        ],
    }
    motor.enforce_ground_truth_firewall(source_manifest, config)
    motor.write_json(manifest_path, source_manifest)
    return json_path, geojson_path, manifest_path


def _top3_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        [row for row in rows if row.get("score_base_available") is not None],
        key=lambda row: (-float(row["score_base_available"]), str(row["sector_id"])),
    )[:3]
    top3: list[dict[str, Any]] = []
    seen_ranks: set[int] = set()
    for order, row in enumerate(ordered, start=1):
        rank = int(row["rank_base_available_within_buffer"])
        top3.append(
            {
                "area_label": f"AP{order}",
                "presentation_order": order,
                "presentation_order_is_tie_break": rank in seen_ranks,
                "ranking_mode": "BASE_DISPONIVEIS_DIAGNOSTICO",
                "ranking_protocol_id": "MATA01-BLIND-SET-AVAILABLE-v1.0",
                "equivalent_to_base_original": False,
                "scenario_id": row["scenario_id"],
                "candidate_id": row["candidate_id"],
                "sector_id": row["sector_id"],
                "analytical_rank": rank,
                "score": row["score_base_available"],
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
                "effective_geo02_weight": 0.4,
                "effective_geo03_weight": 0.0,
                "effective_geo04_weight": 0.26666666666666666,
                "effective_geo05_weight": 0.3333333333333333,
                "barrier_flags": row.get("barrier_flags"),
                "decision_status": row.get("buffer_decision_status"),
                "score_interpretation": "PRIORIDADE_ANALITICA_TERRITORIAL_NAO_PROBABILIDADE",
                "directional_preference_applied": False,
                "confirmatory_eligible": False,
                "ground_truth_used": False,
            }
        )
        seen_ranks.add(rank)
    return top3


def _domain_segment_count(motor: Any, segments: Sequence[Any], lat: float, lon: float, radius_m: float) -> int:
    """Conta segmentos cuja distancia minima ao centro intercepta o dominio."""
    return sum(motor._point_segment_distance(segment, lat, lon) <= radius_m for segment in segments)


def _apply_hydro_abstention(features: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Marca GEO-03 ausente; vazio cartografico nunca vira favorabilidade."""
    output: list[dict[str, Any]] = []
    for raw in features:
        row = dict(raw)
        row["water_distance_m"] = None
        row["nearest_water_category"] = None
        row["nearest_water_severity"] = None
        row["hydro_length_sector_km"] = None
        row["hydro_severity_weighted_length_km"] = None
        row["hydro_density_km_km2"] = None
        row["geo03_score"] = None
        row["hydro_access_score"] = None
        row["geo03_availability"] = "NAO_DISPONIVEL_ZERO_FEICOES_OSM_NO_DOMINIO"
        row["modules_available"] = 3
        row["missing_module_count"] = 1
        row["geo_completeness"] = 0.75
        row["feature_status"] = "PARCIAL"
        existing = str(row.get("barrier_flags") or "")
        flags = [] if existing in {"", "NAO_SINALIZADA"} else existing.split(";")
        flags.append("GEO03_OSM_HIDRO_INDISPONIVEL")
        row["barrier_flags"] = ";".join(sorted(set(flags)))
        row["feature_method"] = (
            "OSM_LINE_CHUNKS_GEO02_PLUS_3600_POINT_EQUAL_AREA_POLAR_STRATIFIED_RASTER_SAMPLE_GEO04_GEO05;"
            "GEO03_ABSTAINED_ZERO_OSM_FEATURES_WITHIN_DOMAIN"
        )
        row["source_provenance"] = (
            "GEO-02: OpenStreetMap; GEO-03: indisponivel (zero feicoes OSM no dominio); "
            "GEO-04: Mapzen/Skadi-SRTMGL1; GEO-05: ESA WorldCover 2021 v200"
        )
        expected = int(row.get("worldcover_expected_sample_count") or 0)
        area = float(row["sector_area_m2"])
        row["raster_nominal_cell_area_m2"] = round(area / expected, 6) if expected else None
        row["raster_nominal_linear_support_m"] = round(math.sqrt(area / expected), 6) if expected else None
        output.append(row)
    return output


def _build_base_original_abstained(features: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in features:
        row = dict(raw)
        row.update(
            {
                "ranking_protocol_id": "MATA01-BLIND-SET-v1.0",
                "ranking_mode": "BASE_ORIGINAL",
                "ranking_status": "ABSTIDO_GEO03_INDISPONIVEL",
                "score_base": None,
                "rank_base_within_buffer": None,
                "base_top_member": False,
                "selected_sector": False,
                "buffer_decision_status": "REVISAR",
                "buffer_warning_codes": "INCOMPLETE_GEO;GEO03_EMPTY_WITHIN_DOMAIN;BASE_ORIGINAL_ABSTAINED",
                "score_interpretation": "ABSTENCAO_SEM_PRIORIZACAO",
            }
        )
        output.append(row)
    return output


def _rank_available_modules(features: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Ranking diagnostico separado com os pesos BASE remanescentes renormalizados."""
    weights = {"geo02": 0.4, "geo04": 0.26666666666666666, "geo05": 0.3333333333333333}
    if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-12):
        raise RuntimeError("Pesos do BASE-DISPONIVEIS nao somam 1")
    output: list[dict[str, Any]] = []
    for raw in features:
        row = dict(raw)
        values = {
            "geo02": row.get("road_trail_access_score"),
            "geo04": row.get("terrain_access_score"),
            "geo05": row.get("landcover_access_score"),
        }
        missing = [name for name, value in values.items() if value is None]
        contributions = {
            name: (None if values[name] is None else float(weights[name]) * float(values[name]))
            for name in weights
        }
        score = None if missing else sum(float(value) for value in contributions.values() if value is not None)
        row.update(
            {
                "ranking_protocol_id": "MATA01-BLIND-SET-AVAILABLE-v1.0",
                "ranking_mode": "BASE_DISPONIVEIS_DIAGNOSTICO",
                "equivalent_to_base_original": False,
                "effective_geo02_weight": weights["geo02"],
                "effective_geo03_weight": 0.0,
                "effective_geo04_weight": weights["geo04"],
                "effective_geo05_weight": weights["geo05"],
                "contribution_base_available_geo02": contributions["geo02"],
                "contribution_base_available_geo03": None,
                "contribution_base_available_geo04": contributions["geo04"],
                "contribution_base_available_geo05": contributions["geo05"],
                "score_base_available": round(score, 9) if score is not None else None,
                "rank_base_available_within_buffer": None,
                "base_available_top_member": False,
                "selected_sector": False,
                "buffer_decision_status": "REVISAR",
                "buffer_warning_codes": (
                    "GEO03_ABSTAINED;BASE_AVAILABLE_NOT_EQUIVALENT_BASE_FULL"
                    + (";MISSING_AVAILABLE_MODULE" if missing else "")
                ),
                "score_interpretation": "PRIORIDADE_ANALITICA_TERRITORIAL_DIAGNOSTICA_NAO_PROBABILIDADE",
            }
        )
        output.append(row)
    ordered = sorted(
        [row for row in output if row["score_base_available"] is not None],
        key=lambda row: (-float(row["score_base_available"]), str(row["sector_id"])),
    )
    previous_score: float | None = None
    current_rank = 0
    for index, row in enumerate(ordered, start=1):
        score = float(row["score_base_available"])
        if previous_score is None or score != previous_score:
            current_rank = index
        row["rank_base_available_within_buffer"] = current_rank
        row["base_available_top_member"] = current_rank == 1
        previous_score = score
    return sorted(output, key=lambda row: (int(row["ring_index"]), int(row["direction_index"])))


def _worldcover_summary(features: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts: dict[int, int] = {}
    total = 0
    for row in features:
        raw = row.get("worldcover_class_counts") or "{}"
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        for code, count in parsed.items():
            code_int = int(code)
            counts[code_int] = counts.get(code_int, 0) + int(count)
            total += int(count)
    return {
        "sample_count": total,
        "class_counts": {str(code): counts[code] for code in sorted(counts)},
        "water_class_80_count": counts.get(80, 0),
        "wetland_class_90_count": counts.get(90, 0),
        "water_class_80_fraction": round(counts.get(80, 0) / total, 9) if total else None,
        "wetland_class_90_fraction": round(counts.get(90, 0) / total, 9) if total else None,
        "water_plus_wetland_fraction": round((counts.get(80, 0) + counts.get(90, 0)) / total, 9) if total else None,
        "interpretation": "EVIDENCIA_GEO05_NAO_SUBSTITUI_GEO03_OSM_AUSENTE",
    }


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
    config_path = output_dir / "config_efetiva_mata01_blind.json"
    motor.write_json(config_path, config)
    shutil.copyfile(PROTOCOL_PATH, output_dir / "protocolo_mata01_cego_v1.md")

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
    upstream = overlay["upstream"]
    hydro_domain_segment_count = _domain_segment_count(
        motor,
        hydros,
        float(upstream["estimated_lat"]),
        float(upstream["estimated_lon"]),
        float(upstream["source_radius_m"]),
    )
    if hydro_domain_segment_count != 0:
        raise RuntimeError(
            "O protocolo congelado pressupoe zero feicoes OSM hidro no dominio; "
            f"foram encontradas {hydro_domain_segment_count}. Nova versao e necessaria."
        )
    cell_deg = float(config["feature_extraction"]["spatial_index_cell_deg"])
    road_index = motor.SpatialSegmentIndex(roads, cell_deg)
    hydro_index = motor.SpatialSegmentIndex(hydros, cell_deg)
    hgt = motor.HGTSampler(dem_dir)
    world_cover = motor.WorldCoverSampler(worldcover_dir)
    try:
        extracted_features = motor.extract_sector_features(
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

    features = _apply_hydro_abstention(extracted_features)
    ranked_original = _build_base_original_abstained(features)
    ranked_available = _rank_available_modules(features)
    top3 = _top3_rows(ranked_available)
    original_by_id = {str(row["sector_id"]): row for row in ranked_original}
    available_by_id = {str(row["sector_id"]): row for row in ranked_available}
    geometry_doc = motor.build_sector_geojson(sectors, config, original_by_id)
    for feature in geometry_doc["features"]:
        row = available_by_id[str(feature["id"])]
        feature["properties"].update(
            {
                "ranking_protocol_id_available": row["ranking_protocol_id"],
                "ranking_mode_available": row["ranking_mode"],
                "equivalent_to_base_original": False,
                "score_base_available": row["score_base_available"],
                "rank_base_available_within_buffer": row["rank_base_available_within_buffer"],
                "base_available_top_member": row["base_available_top_member"],
                "geo03_availability": row["geo03_availability"],
            }
        )
    feature_rows = _clean_feature_rows(features)
    worldcover_summary = _worldcover_summary(features)
    result_doc = {
        "protocol_id": config["protocol_id"],
        "engine_version": config["engine_version"],
        "upstream_protocol_id": config["dependencies"]["upstream_buffer_protocol"],
        "scenario_id": upstream["scenario_id"],
        "candidate_id": upstream["candidate_id"],
        "execution_classification": upstream["execution_classification"],
        "review_status": "REVISAR",
        "radius_m": float(upstream["source_radius_m"]),
        "radius_origin": upstream["radius_origin"],
        "radius_method": upstream["radius_method"],
        "r0_semantics": upstream["r0_semantics"],
        "additional_factors_applied_by_engine": False,
        "adaptive_buffer_status": "NAO_EXECUTADO_ENTRADA_INSUFICIENTE",
        "detection_quality_available": False,
        "detection_quality_imputed": False,
        "confirmatory_eligible": False,
        "ground_truth_used": False,
        "received_point": {
            "estimated_lat": float(upstream["estimated_lat"]),
            "estimated_lon": float(upstream["estimated_lon"]),
            "point_semantics": upstream["point_semantics"],
            "event_timestamp_local": upstream["event_timestamp_local"],
            "coordinate_capture_timestamp_local": upstream["coordinate_capture_timestamp_local"],
            "radius_m": float(upstream["source_radius_m"]),
            "radius_origin": upstream["radius_origin"],
            "radius_method": upstream["radius_method"],
            "radius_review_status": "REVISAR",
        },
        "environment_declared": overlay["context_boundary"]["environment_declared"],
        "source_snapshot": overlay["source_snapshot"],
        "hydrography_osm_within_domain": {
            "segment_count": hydro_domain_segment_count,
            "availability": "NAO_DISPONIVEL_ZERO_FEICOES_OSM_NO_DOMINIO",
            "empty_means_no_water": False,
            "used_as_favorable_score": False,
        },
        "raster_sampling": overlay["raster_sampling_override"],
        "worldcover_domain_summary": worldcover_summary,
        "sector_count": len(sectors),
        "ranking_scope": "WITHIN_RECEIVED_SOURCE_RADIUS_ONLY",
        "base_original": {
            "protocol_id": config["protocol_id"],
            "status": "ABSTIDO_GEO03_INDISPONIVEL",
            "top3_generated": False,
            "results": ranked_original,
        },
        "base_available": {
            "protocol_id": "MATA01-BLIND-SET-AVAILABLE-v1.0",
            "status": "DIAGNOSTICO_REVISAR",
            "equivalent_to_base_original": False,
            "weights": overlay["ranking"]["available_modules_weights"],
            "top3": top3,
            "results": ranked_available,
        },
        "profile_used_in_quantitative_ranking": False,
        "north_clue_used_in_quantitative_ranking": False,
        "water_habit_used_in_quantitative_ranking": False,
        "photographs_used_in_quantitative_ranking": False,
        "directional_preference_applied": False,
        "ring_penalty_applied": False,
        "interpretation": {
            "base_original": "ABSTENCAO_SEM_PRIORIZACAO",
            "base_available_score": "PRIORIDADE_ANALITICA_TERRITORIAL_DIAGNOSTICA_NAO_PROBABILIDADE",
            "areas": "AP1_AP2_AP3_EXISTEM_APENAS_NO_BASE_DISPONIVEIS_E_EXIGEM_REVISAO_HUMANA",
            "operational_command": False,
            "temporal_and_field_confirmation_required": True,
        },
    }

    for value in (feature_rows, ranked_original, ranked_available, geometry_doc, top3, result_doc):
        motor.enforce_ground_truth_firewall(value, config)

    motor.write_csv(output_dir / "atributos_geo_setores_mata01.csv", feature_rows)
    motor.write_csv(output_dir / "ranking_base_original_abstido_mata01.csv", ranked_original)
    motor.write_csv(output_dir / "ranking_base_disponiveis_mata01.csv", ranked_available)
    motor.write_json(output_dir / "setores_mata01.geojson", geometry_doc)
    motor.write_csv(output_dir / "top3_base_disponiveis_mata01.csv", top3)
    motor.write_json(
        output_dir / "top3_base_disponiveis_mata01.json",
        {
            "protocol_id": "MATA01-BLIND-SET-AVAILABLE-v1.0",
            "ranking_mode": "BASE_DISPONIVEIS_DIAGNOSTICO",
            "equivalent_to_base_original": False,
            "base_original_status": "ABSTIDO_GEO03_INDISPONIVEL",
            "weights": overlay["ranking"]["available_modules_weights"],
            "interpretation": "AREAS_ANALITICAS_DIAGNOSTICAS_PARA_REVISAO_HUMANA",
            "ground_truth_used": False,
            "areas": top3,
        },
    )
    motor.write_json(output_dir / "resultado_mata01_cego.json", result_doc)

    first = sorted(
        ranked_available,
        key=lambda row: (-float(row["score_base_available"]), str(row["sector_id"])),
    )[0]
    warning_lines = [
        "MATA-01|MATA-01-E0|REVISAR|EXECUCAO_DIAGNOSTICA_NAO_CONFIRMATORIA",
        "BASE_ORIGINAL|ABSTIDO|GEO03_INDISPONIVEL_ZERO_FEICOES_OSM_NO_DOMINIO",
        f"BASE_DISPONIVEIS|{first.get('sector_id')}|NAO_EQUIVALENTE_AO_BASE_COMPLETO",
        "RAIO|5000_M|DOMINIO_INFORMADO_PELO_PESQUISADOR|SEM_BUFFER_ADAPTATIVO",
        "DETECTION_QUALITY|NAO_DISPONIVEL|NAO_IMPUTADA",
        "PONTO|PLANEJAMENTO_REGISTRADO_APOS_O_EVENTO|NAO_TRATADO_COMO_UPV_CONTEMPORANEO",
        "OSM|BASE_2026-08-17|COBERTURA_VOLUNTARIA_PODE_SER_INCOMPLETA",
        "WORLDCOVER|PRODUTO_2021|NAO_COMPROVA_CONDICAO_ATUAL",
        "SRTM|RELEVO_REGIONAL|NAO_REPRESENTA_TRANSITABILIDADE_SOB_DOSSEL",
        "RASTER|3600_AMOSTRAS_POR_SETOR|SUPORTE_NOMINAL_APROXIMADO_30_M|NAO_CENSO_DE_PIXELS",
        "PERFIL_E_PISTAS|SEGREGADOS|NAO_APLICADOS_AO_RANKING_TERRITORIAL_V1",
        "FOTOGRAFIAS|SEGREGADAS|NAO_APLICADAS_AO_RANKING",
        "INTERPRETACAO|AP1_AP2_AP3_EXISTEM_APENAS_NO_BASE_DISPONIVEIS_E_NAO_SAO_PROBABILIDADES_OU_DETECCOES",
    ]
    _write_text(output_dir / "avisos_revisao.log", "\n".join(warning_lines) + "\n")

    return {
        "config": config,
        "buffer_rows": buffer_rows,
        "sectors": sectors,
        "features": features,
        "ranked_original": ranked_original,
        "ranked_available": ranked_available,
        "top3": top3,
        "hydro_domain_segment_count": hydro_domain_segment_count,
        "worldcover_summary": worldcover_summary,
    }


def _compare_runs(run1: Path, run2: Path) -> dict[str, Any]:
    comparisons: list[dict[str, Any]] = []
    all_equal = True
    for name in SCIENTIFIC_FILES:
        first = run1 / name
        second = run2 / name
        hash1 = _sha256(first) if first.exists() else None
        hash2 = _sha256(second) if second.exists() else None
        equal = hash1 is not None and hash1 == hash2
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
    ranked_original = run["ranked_original"]
    ranked_available = run["ranked_available"]
    top3 = run["top3"]
    sectors = run["sectors"]
    features = run["features"]
    overlay = _load_json(OVERLAY_CONFIG_PATH)
    gates = {
        "sector_count_is_24": len(sectors) == 24,
        "feature_count_is_24": len(features) == 24,
        "original_rank_row_count_is_24": len(ranked_original) == 24,
        "available_rank_row_count_is_24": len(ranked_available) == 24,
        "top3_count_is_3": len(top3) == 3,
        "geo03_domain_segment_count_is_zero": run["hydro_domain_segment_count"] == 0,
        "all_geo03_values_are_missing": all(row.get("hydro_access_score") is None for row in features),
        "all_geo_completeness_is_075": all(float(row.get("geo_completeness", 0.0)) == 0.75 for row in features),
        "base_original_fully_abstained": all(
            row.get("score_base") is None
            and row.get("rank_base_within_buffer") is None
            and row.get("ranking_status") == "ABSTIDO_GEO03_INDISPONIVEL"
            for row in ranked_original
        ),
        "all_available_scores_in_unit_interval": all(
            row.get("score_base_available") is not None
            and 0.0 <= float(row["score_base_available"]) <= 1.0
            for row in ranked_available
        ),
        "available_weights_sum_to_one": math.isclose(
            0.4 + 0.26666666666666666 + 0.3333333333333333, 1.0, abs_tol=1e-12
        ),
        "available_output_not_labelled_equivalent": all(
            row.get("equivalent_to_base_original") is False for row in ranked_available
        ),
        "all_sectors_have_3600_expected_samples": all(
            int(row.get("terrain_expected_sample_count", 0)) == 3600
            and int(row.get("worldcover_expected_sample_count", 0)) == 3600
            for row in features
        ),
        "all_raster_sample_coverage_is_complete": all(
            float(row.get("terrain_sample_coverage", 0.0)) == 1.0
            and float(row.get("worldcover_sample_coverage", 0.0)) == 1.0
            for row in features
        ),
        "all_worldcover_class_counts_sum_to_3600": all(
            sum(int(value) for value in json.loads(str(row["worldcover_class_counts"])).values()) == 3600
            for row in features
        ),
        "no_directional_preference": all(row.get("directional_preference_applied") is not True for row in top3),
        "all_control_flags_false": all(row.get("ground_truth_used") is False for row in ranked_available),
        "adaptive_buffer_not_used": run["config"]["execution_control"]["adaptive_buffer_engine_used"] is False,
        "missing_detection_quality_not_imputed": run["config"]["execution_control"]["missing_detection_quality_imputed"] is False,
        "declared_radius_is_5000_m": float(overlay["upstream"]["source_radius_m"]) == 5000.0,
        "expected_dem_tile_available": (DEFAULT_GEO_DIR / "S01W052.hgt.gz").exists(),
        "expected_worldcover_tile_available": (
            DEFAULT_GEO_DIR / "worldcover_tiles/ESA_WorldCover_10m_2021_v200_S03W054_Map.tif"
        ).exists(),
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
    lines = [
        "# Relatorio de execucao — MATA-01 territorial cego v1.0",
        "",
        "## Resultado",
        "",
        "- classificacao: diagnostica e nao confirmatoria;",
        "- situacao: revisar;",
        "- ponto processado: MATA-01-E0;",
        "- dominio circular recebido: 5.000 m;",
        "- origem do dominio: informado pelo pesquisador sob incerteza alta;",
        "- buffer adaptativo: nao executado por ausencia de qualidade de deteccao;",
        "- imputacao de qualidade: nao;",
        "- setores produzidos: 24;",
        "- perfil, pista ao Norte e habito de buscar agua: nao aplicados ao ranking territorial v1;",
        "- fotografias: nao aplicadas ao ranking quantitativo;",
        "- posicao declarada do alvo simulado usada no processamento: nao.",
        "",
        "- GEO-03: indisponivel (zero feicoes OSM no dominio);",
        "- BASE original: abstido, sem Top-3;",
        "- grade raster: 3.600 amostras por setor, suporte nominal aproximado de 30 m;",
        "",
        "## Top 3 territorial — BASE-DISPONIVEIS (diagnostico separado)",
        "",
        "| Area | Setor | Posto | Escore | Direcao | Anel | GEO-02 | GEO-03 | GEO-04 | GEO-05 |",
        "|---|---|---:|---:|---|---|---:|---:|---:|---:|",
    ]
    for row in run["top3"]:
        geo03_text = "—" if row["geo03_score"] is None else f"{float(row['geo03_score']):.6f}"
        lines.append(
            f"| {row['area_label']} | {row['sector_id']} | {row['analytical_rank']} | "
            f"{float(row['score']):.9f} | {row['direction']} | {row['ring_id']} | "
            f"{float(row['geo02_score']):.6f} | {geo03_text} | "
            f"{float(row['geo04_score']):.6f} | {float(row['geo05_score']):.6f} |"
        )
    lines.extend(
        [
            "",
            "## Reprodutibilidade e QA",
            "",
            f"- duas execucoes independentes: **{determinism['status']}**;",
            f"- arquivos cientificos identicos: {determinism['all_scientific_files_equal']};",
            f"- gates de QA: **{qa['passed_gate_count']}/{qa['gate_count']} ({qa['status']})**.",
            "",
            "## Interpretacao e limites",
            "",
            "AP1, AP2 e AP3 pertencem somente ao BASE-DISPONIVEIS, cujo peso foi renormalizado para GEO-02 0,40, GEO-04 0,26666666666666666 e GEO-05 0,3333333333333333. Essa analise nao equivale ao BASE completo. Os escores nao representam probabilidade de presenca, precisao de localizacao, deteccao ou comando operacional. A diferenca temporal entre OSM, WorldCover, SRTM e o ensaio exige confirmacao em campo. Em especial, cobertura aerea e relevo regional nao revelam por si so vegetacao emaranhada, solo encharcado, barrancos estreitos, quedas de arvores ou passagem efetiva sob o dossel.",
            "",
            "## Sintese de cobertura WorldCover no dominio amostrado",
            "",
            f"- celulas/amostras validas: {run['worldcover_summary']['sample_count']};",
            f"- classe 80 (agua): {run['worldcover_summary']['water_class_80_count']} ({100 * float(run['worldcover_summary']['water_class_80_fraction']):.3f}%);",
            f"- classe 90 (area umida): {run['worldcover_summary']['wetland_class_90_count']} ({100 * float(run['worldcover_summary']['wetland_class_90_fraction']):.3f}%);",
            "- essas classes pertencem a GEO-05 e nao preenchem artificialmente GEO-03.",
            "",
        ]
    )
    _write_text(output_dir / "relatorio_execucao_mata01.md", "\n".join(lines))


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
    determinism = _load_json(output_dir / "relatorio_determinismo.json")
    run1_hashes = {str(item["file"]): str(item["run1_sha256"]) for item in determinism.get("files", [])}
    if set(run1_hashes) != set(SCIENTIFIC_FILES):
        raise RuntimeError("Relatorio de determinismo nao cobre exatamente os artefatos cientificos")
    for name in SCIENTIFIC_FILES:
        if _sha256(output_dir / name) != run1_hashes[name]:
            raise RuntimeError(f"Hash publicado diverge da primeira execucao: {name}")

    input_files = [
        _file_entry(MOTOR_PATH, "engine_imported_unchanged"),
        _file_entry(BASE_CONFIG_PATH, "base_config_source"),
        _file_entry(OVERLAY_CONFIG_PATH, "mata01_config_source"),
        _file_entry(PROTOCOL_PATH, "protocol_source"),
        _file_entry(roads_path, "source_geo02_osm"),
        _file_entry(hydro_path, "source_geo03_osm"),
    ]
    for path in sorted(dem_dir.glob("*.hgt.gz")):
        input_files.append(_file_entry(path, "source_geo04_dem"))
    for path in sorted(worldcover_dir.glob("*.tif")):
        input_files.append(_file_entry(path, "source_geo05_worldcover"))
    manifest_output_names = set(SCIENTIFIC_FILES) | {
        "relatorio_determinismo.json",
        "relatorio_qa.json",
        "relatorio_execucao_mata01.md",
    }
    output_files = [_file_entry(output_dir / name, "output") for name in sorted(manifest_output_names)]
    scientific_hashes = {name: _sha256(output_dir / name) for name in SCIENTIFIC_FILES}
    manifest = {
        "protocol_id": run["config"]["protocol_id"],
        "upstream_protocol_id": run["config"]["dependencies"]["upstream_buffer_protocol"],
        "engine_version": run["config"]["engine_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python_version": platform.python_version(),
        "execution_classification": "CAMPO_CEGO_DIAGNOSTICO_DOMINIO_DA_FONTE",
        "review_status": "REVISAR",
        "radius_m": 5000.0,
        "radius_origin": "INFORMADO_PELO_PESQUISADOR",
        "radius_method": "DOMINIO_OPERACIONAL_DIRETO_SEM_BUFFER_ADAPTATIVO",
        "r0_semantics": "source_declared_operational_domain",
        "additional_factors_applied_by_engine": False,
        "detection_quality_imputed": False,
        "adaptive_buffer_status": "NAO_EXECUTADO_ENTRADA_INSUFICIENTE",
        "confirmatory_eligible": False,
        "ground_truth_used": False,
        "sector_count": len(run["sectors"]),
        "used_spatial_tiles": {
            "dem": "S01W052.hgt.gz",
            "worldcover": "ESA_WorldCover_10m_2021_v200_S03W054_Map.tif",
        },
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
    determinism = _load_json(output_dir / "relatorio_determinismo.json")
    manifest = _load_json(manifest_path)
    run1 = {str(item["file"]): str(item["run1_sha256"]) for item in determinism.get("files", [])}
    manifest_outputs = {
        Path(str(item["path"])).name: str(item["sha256"])
        for item in manifest.get("files", [])
        if item.get("role") == "output"
    }
    checks = []
    for name in SCIENTIFIC_FILES:
        actual = _sha256(output_dir / name)
        equal = actual == run1.get(name) == manifest_outputs.get(name)
        checks.append(
            {
                "file": name,
                "run1_sha256": run1.get(name),
                "published_sha256": actual,
                "manifest_sha256": manifest_outputs.get(name),
                "all_equal": equal,
            }
        )
    status = "PASS" if len(checks) == len(SCIENTIFIC_FILES) and all(item["all_equal"] for item in checks) else "FAIL"
    if status != "PASS":
        failed = [item["file"] for item in checks if not item["all_equal"]]
        raise RuntimeError(f"Cadeia de hashes diverge: {', '.join(failed)}")
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
    for required in (
        roads_path,
        hydro_path,
        dem_dir,
        worldcover_dir,
        MOTOR_PATH,
        BASE_CONFIG_PATH,
        OVERLAY_CONFIG_PATH,
        PROTOCOL_PATH,
    ):
        if not required.exists():
            raise FileNotFoundError(required)
    output_dir.mkdir(parents=True, exist_ok=True)

    owned = set(SCIENTIFIC_FILES) | {
        "relatorio_determinismo.json",
        "relatorio_qa.json",
        "relatorio_execucao_mata01.md",
        "manifesto_processamento_cego.json",
    }
    for name in owned:
        path = output_dir / name
        if path.exists() and path.is_file():
            path.unlink()

    run1 = build_scientific_outputs(motor, output_dir, roads_path, hydro_path, dem_dir, worldcover_dir)
    with tempfile.TemporaryDirectory(prefix="mata01_blind_repeat_") as temporary:
        second_dir = Path(temporary)
        build_scientific_outputs(motor, second_dir, roads_path, hydro_path, dem_dir, worldcover_dir)
        determinism = _compare_runs(output_dir, second_dir)
    if determinism["status"] != "PASS":
        raise RuntimeError("As duas execucoes nao produziram artefatos cientificos identicos")
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
        "top3": run1["top3"],
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
