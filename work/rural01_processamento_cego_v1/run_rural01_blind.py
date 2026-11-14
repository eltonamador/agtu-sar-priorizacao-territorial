#!/usr/bin/env python3
"""Executa e audita o núcleo territorial cego do cenário RURAL-01.

O invólucro importa sem alteração o motor ``EXT-ESP-SET-v1.1``. Ele recebe
um único ponto e o raio direto informado pela fonte, produz 24 setores,
extrai atributos GEO-02 a GEO-05 e aplica somente o ranking BASE já
congelado. Perfil, direção declarada e fotografias não entram no cálculo.
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
OVERLAY_CONFIG_PATH = HERE / "config_rural01_blind_v1.json"
PROTOCOL_PATH = HERE / "PROTOCOLO_RURAL01_CEGO_v1.md"
DEFAULT_GEO_DIR = PROJECT_ROOT / "outputs/sprint2_s2_06_geo05_v33"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs/campo_rural01/processamento_cego_v1"

SCIENTIFIC_FILES = (
    "entrada_raio_fonte.json",
    "entrada_raio_fonte.geojson",
    "manifesto_entrada_raio_fonte.json",
    "config_efetiva_rural01_blind.json",
    "protocolo_rural01_cego_v1.md",
    "atributos_geo_setores.csv",
    "ranking_base_rural01.csv",
    "setores_rural01.geojson",
    "top3_rural01.csv",
    "top3_rural01.json",
    "resultado_rural01_cego.json",
    "avisos_revisao.log",
)


def _load_motor() -> Any:
    spec = importlib.util.spec_from_file_location("motor_setorizacao_priorizacao_v1_1_rural01", MOTOR_PATH)
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
    """Cria configuração efetiva preservando intactos motor e configuração-base."""
    config = copy.deepcopy(motor.load_json(BASE_CONFIG_PATH))
    config["protocol_id"] = str(overlay["protocol_id"])
    config["protocol_name"] = str(overlay["protocol_name"])
    config["version"] = str(overlay["version"])
    config["engine_version"] = "1.0.0-rural01-blind-wrapper+EXT-ESP-SET-v1.1"
    config["status"] = str(overlay["status"])
    config["phase"] = "CAMPO_RURAL01_CEGO"
    config["scope"]["classification"] = "CASO_UNICO_CEGO_DIAGNOSTICO_NAO_CONFIRMATORIO"
    config["scope"]["description"] = (
        "Setorização e priorização territorial do raio de 1.500 m informado pela fonte para RURAL-01, "
        "executada sem acesso à posição de avaliação e destinada à revisão humana."
    )
    config["dependencies"]["upstream_buffer_protocol"] = str(overlay["upstream"]["protocol_id"])
    config["ranking"]["primary_weight_set"] = "BASE"
    config["rural01_source_input"] = copy.deepcopy(overlay["upstream"])
    config["rural01_context_boundary"] = copy.deepcopy(overlay["context_boundary"])
    config["rural01_interpretation"] = copy.deepcopy(overlay["interpretation"])
    config["execution_control"] = {
        "direct_source_radius_used": True,
        "adaptive_buffer_engine_used": False,
        "profile_used_in_quantitative_ranking": False,
        "directional_preference_applied": False,
        "ring_penalty_applied": False,
        "photographs_used_in_quantitative_ranking": False,
        "confirmatory_eligible": False,
        "ground_truth_used": False,
    }
    config["limitations"] = list(config.get("limitations", [])) + [
        "RURAL-01 utiliza um único ponto e o raio direto informado pela fonte; o motor não estimou esse raio.",
        "A direção Norte declarada permanece contextual e não altera o ranking territorial.",
        "Fotografias e perfil não entram no núcleo territorial desta execução.",
        "AP1, AP2 e AP3 são áreas analíticas para revisão humana, não probabilidades, detecções ou ordens operacionais.",
    ]
    motor.validate_firewall_config(config)
    return config


def build_source_radius_inputs(
    motor: Any,
    output_dir: Path,
    config: Mapping[str, Any],
    overlay: Mapping[str, Any],
) -> tuple[Path, Path, Path]:
    """Materializa o raio informado pela fonte no contrato esperado pelo motor."""
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
        "radius_rationale": upstream["radius_rationale"],
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
        "radius_m": radius,
        "radius_origin": upstream["radius_origin"],
        "r0_semantics": upstream["r0_semantics"],
        "additional_factors_applied_by_engine": upstream["additional_factors_applied_by_engine"],
        "radius_review_status": upstream["review_status"],
        "erb_850_m_role": "RELATO_CONTEXTUAL_SEM_DERIVACAO_MATEMATICA_REPRODUZIDA",
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
                    "additional_factors_applied_by_engine": upstream["additional_factors_applied_by_engine"],
                    "review_status": upstream["review_status"],
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
        "radius_m": radius,
        "radius_origin": upstream["radius_origin"],
        "r0_semantics": upstream["r0_semantics"],
        "additional_factors_applied_by_engine": upstream["additional_factors_applied_by_engine"],
        "radius_review_status": upstream["review_status"],
        "erb_850_m_role": "RELATO_CONTEXTUAL_SEM_DERIVACAO_MATEMATICA_REPRODUZIDA",
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
        [row for row in rows if row.get("score_base") is not None],
        key=lambda row: (-float(row["score_base"]), str(row["sector_id"])),
    )[:3]
    top3: list[dict[str, Any]] = []
    seen_ranks: set[int] = set()
    for order, row in enumerate(ordered, start=1):
        rank = int(row["rank_base_within_buffer"])
        presentation_is_tie_break = rank in seen_ranks
        seen_ranks.add(rank)
        top3.append(
            {
                "area_label": f"AP{order}",
                "presentation_order": order,
                "presentation_order_is_tie_break": presentation_is_tie_break,
                "ranking_mode": "BASE",
                "scenario_id": row["scenario_id"],
                "candidate_id": row["candidate_id"],
                "sector_id": row["sector_id"],
                "analytical_rank": rank,
                "score": row["score_base"],
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
                "decision_status": row.get("buffer_decision_status"),
                "score_interpretation": "PRIORIDADE_ANALITICA_TERRITORIAL_NAO_PROBABILIDADE",
                "directional_preference_applied": False,
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
    config_path = output_dir / "config_efetiva_rural01_blind.json"
    motor.write_json(config_path, config)
    shutil.copyfile(PROTOCOL_PATH, output_dir / "protocolo_rural01_cego_v1.md")

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

    ranked = motor.rank_sector_records(features, config)
    for row in ranked:
        # O invólucro RURAL-01 é diagnóstico e não confirmatório. Padronizamos
        # a legenda do escore para evitar que "operacional" seja interpretado
        # como ordem de emprego ou probabilidade de presença.
        row["score_interpretation"] = (
            "PRIORIDADE_ANALITICA_TERRITORIAL_NAO_PROBABILIDADE"
        )
    top3 = _top3_rows(ranked)
    ranked_by_id = {str(row["sector_id"]): row for row in ranked}
    geometry_doc = motor.build_sector_geojson(sectors, config, ranked_by_id)
    feature_rows = _clean_feature_rows(features)

    result_doc = {
        "protocol_id": config["protocol_id"],
        "engine_version": config["engine_version"],
        "upstream_protocol_id": config["dependencies"]["upstream_buffer_protocol"],
        "scenario_id": "RURAL-01",
        "candidate_id": "RURAL-01-E0",
        "execution_classification": "CAMPO_CEGO_DIAGNOSTICO_RAIO_DA_FONTE",
        "review_status": "REVISAR",
        "radius_m": 1500.0,
        "radius_origin": "INFORMADO_PELA_FONTE",
        "r0_semantics": "source_adjusted_final",
        "additional_factors_applied_by_engine": False,
        "erb_850_m_role": "RELATO_CONTEXTUAL_SEM_DERIVACAO_MATEMATICA_REPRODUZIDA",
        "confirmatory_eligible": False,
        "ground_truth_used": False,
        "received_point": {
            "estimated_lat": 0.188611,
            "estimated_lon": -51.155556,
            "radius_m": 1500.0,
            "radius_origin": "INFORMADO_PELA_FONTE",
            "radius_method": "RAIO_DIRETO_SEM_BUFFER_ADAPTATIVO",
            "r0_semantics": "source_adjusted_final",
            "additional_factors_applied_by_engine": False,
            "radius_review_status": "REVISAR",
        },
        "sector_count": len(sectors),
        "ranking_scope": "WITHIN_RECEIVED_SOURCE_RADIUS_ONLY",
        "ranking_method": "BASE_ORIGINAL_EXT_ESP_SET_v1_1",
        "profile_used_in_quantitative_ranking": False,
        "probable_north_direction_used_in_quantitative_ranking": False,
        "photographs_used_in_quantitative_ranking": False,
        "directional_preference_applied": False,
        "ring_penalty_applied": False,
        "top3": top3,
        "results": ranked,
        "interpretation": {
            "score": "PRIORIDADE_ANALITICA_TERRITORIAL_NAO_PROBABILIDADE",
            "areas": "AP1_AP2_AP3_EXIGEM_REVISAO_HUMANA",
            "operational_command": False,
        },
    }

    for value in (feature_rows, ranked, geometry_doc, top3, result_doc):
        motor.enforce_ground_truth_firewall(value, config)

    motor.write_csv(output_dir / "atributos_geo_setores.csv", feature_rows)
    motor.write_csv(output_dir / "ranking_base_rural01.csv", ranked)
    motor.write_json(output_dir / "setores_rural01.geojson", geometry_doc)
    motor.write_csv(output_dir / "top3_rural01.csv", top3)
    motor.write_json(
        output_dir / "top3_rural01.json",
        {
            "ranking_mode": "BASE",
            "interpretation": "AREAS_ANALITICAS_PARA_REVISAO_HUMANA",
            "ground_truth_used": False,
            "areas": top3,
        },
    )
    motor.write_json(output_dir / "resultado_rural01_cego.json", result_doc)

    first = ranked[0]
    warning_lines = [
        "RURAL-01|RURAL-01-E0|REVISAR|EXECUCAO_DIAGNOSTICA_NAO_CONFIRMATORIA",
        f"BASE|{first.get('sector_id')}|{first.get('buffer_warning_codes')}",
        "RAIO|1500_M|INFORMADO_PELA_FONTE|SEM_BUFFER_ADAPTATIVO",
        "RAIO_850_M|RELATO_CONTEXTUAL|SEM_DERIVACAO_MATEMATICA_REPRODUZIDA",
        "DIRECAO_NORTE|CONTEXTUAL|NAO_APLICADA_AO_RANKING",
        "FOTOGRAFIAS|SEGREGADAS|NAO_APLICADAS_AO_RANKING",
        "INTERPRETACAO|AP1_AP2_AP3_SAO_AREAS_ANALITICAS_NAO_PROBABILIDADES_OU_DETECCOES",
    ]
    _write_text(output_dir / "avisos_revisao.log", "\n".join(warning_lines) + "\n")

    return {
        "config": config,
        "buffer_rows": buffer_rows,
        "sectors": sectors,
        "features": features,
        "ranked": ranked,
        "top3": top3,
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
    ranked = run["ranked"]
    top3 = run["top3"]
    sectors = run["sectors"]
    features = run["features"]
    gates = {
        "sector_count_is_24": len(sectors) == 24,
        "feature_count_is_24": len(features) == 24,
        "rank_count_is_24": len(ranked) == 24,
        "top3_count_is_3": len(top3) == 3,
        "all_geo_complete": all(float(row.get("geo_completeness", 0.0)) == 1.0 for row in features),
        "all_base_scores_in_unit_interval": all(
            row.get("score_base") is not None and 0.0 <= float(row["score_base"]) <= 1.0
            for row in ranked
        ),
        "no_directional_preference": all(row.get("directional_preference_applied") is not True for row in top3),
        "all_control_flags_false": all(row.get("ground_truth_used") is False for row in ranked),
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
        "# Relatório de execução — RURAL-01 territorial cego v1.0",
        "",
        "## Resultado",
        "",
        "- classificação: diagnóstica e não confirmatória;",
        "- situação: revisar;",
        "- ponto processado: RURAL-01-E0;",
        "- raio recebido da fonte: 1.500 m;",
        "- buffer adaptativo: não executado;",
        "- setores produzidos: 24;",
        "- perfil e direção Norte: não aplicados ao ranking;",
        "- fotografias: não aplicadas ao ranking;",
        "- posição de avaliação usada no processamento: não.",
        "",
        "## Top 3 territorial — BASE",
        "",
        "| Área | Setor | Posto | Escore | Direção | Anel |",
        "|---|---|---:|---:|---|---|",
    ]
    for row in run["top3"]:
        lines.append(
            f"| {row['area_label']} | {row['sector_id']} | {row['analytical_rank']} | "
            f"{float(row['score']):.9f} | {row['direction']} | {row['ring_id']} |"
        )
    lines.extend(
        [
            "",
            "## Reprodutibilidade e QA",
            "",
            f"- duas execuções independentes: **{determinism['status']}**;",
            f"- arquivos científicos idênticos: {determinism['all_scientific_files_equal']};",
            f"- gates de QA: **{qa['passed_gate_count']}/{qa['gate_count']} ({qa['status']})**.",
            "",
            "## Interpretação",
            "",
            "AP1, AP2 e AP3 são áreas de prioridade analítica territorial para revisão humana. Os escores não representam probabilidade de presença, detecção ou localização determinada. A comparação posterior deve usar apenas as saídas congeladas e ocorrer fora deste processamento.",
            "",
        ]
    )
    _write_text(output_dir / "relatorio_execucao_rural01.md", "\n".join(lines))


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
        raise RuntimeError("Relatório de determinismo não cobre exatamente os artefatos científicos")
    for name in SCIENTIFIC_FILES:
        if _sha256(output_dir / name) != run1_hashes[name]:
            raise RuntimeError(f"Hash publicado diverge da primeira execução: {name}")

    input_files = [
        _file_entry(MOTOR_PATH, "engine_imported_unchanged"),
        _file_entry(BASE_CONFIG_PATH, "base_config_source"),
        _file_entry(OVERLAY_CONFIG_PATH, "rural01_config_source"),
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
        "relatorio_execucao_rural01.md",
    }
    output_files = [
        _file_entry(output_dir / name, "output")
        for name in sorted(manifest_output_names)
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
        "radius_m": 1500.0,
        "radius_origin": "INFORMADO_PELA_FONTE",
        "r0_semantics": "source_adjusted_final",
        "additional_factors_applied_by_engine": False,
        "erb_850_m_role": "RELATO_CONTEXTUAL_SEM_DERIVACAO_MATEMATICA_REPRODUZIDA",
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
    determinism = _load_json(output_dir / "relatorio_determinismo.json")
    manifest = _load_json(manifest_path)
    run1 = {str(item["file"]): str(item["run1_sha256"]) for item in determinism.get("files", [])}
    manifest_outputs = {
        Path(str(item["path"])).name: str(item["sha256"])
        for item in manifest.get("files", [])
        if item.get("role") == "output"
    }
    checks: list[dict[str, Any]] = []
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
    required_paths = (
        roads_path,
        hydro_path,
        dem_dir,
        worldcover_dir,
        MOTOR_PATH,
        BASE_CONFIG_PATH,
        OVERLAY_CONFIG_PATH,
        PROTOCOL_PATH,
    )
    for required in required_paths:
        if not required.exists():
            raise FileNotFoundError(required)
    output_dir.mkdir(parents=True, exist_ok=True)

    owned = set(SCIENTIFIC_FILES) | {
        "relatorio_determinismo.json",
        "relatorio_qa.json",
        "relatorio_execucao_rural01.md",
        "manifesto_processamento_cego.json",
    }
    for name in owned:
        path = output_dir / name
        if path.exists() and path.is_file():
            path.unlink()

    run1 = build_scientific_outputs(motor, output_dir, roads_path, hydro_path, dem_dir, worldcover_dir)
    with tempfile.TemporaryDirectory(prefix="rural01_blind_repeat_") as temporary:
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
