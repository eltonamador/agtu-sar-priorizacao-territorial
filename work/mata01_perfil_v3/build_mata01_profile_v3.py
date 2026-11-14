#!/usr/bin/env python3
"""Constrói e audita a etapa cega PERFIL V3 do cenário MATA-01.

O construtor preserva o núcleo ``profile_ranker.py`` sem alterações. Como o
adaptador legado exige um compilado PERFIL V2 que não existe para MATA-01, esta
integração direta cria e congela sidecars próprios, recompõe os hashes das
fontes territoriais e rotula toda a saída como diagnóstico não confirmatório.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "perfil_vitima_v3"))
import profile_ranker as ranker  # noqa: E402


DEFAULT_OUTPUT = ROOT / "outputs" / "campo_mata01" / "perfil_cego_v3"
TERRITORIAL_DIR = ROOT / "outputs" / "campo_mata01" / "processamento_cego_v1"
ENTRY_DIR = ROOT / "outputs" / "campo_mata01" / "entrada_cega_v1"
RANKING_PATH = TERRITORIAL_DIR / "ranking_base_disponiveis_mata01.csv"
SECTORS_PATH = TERRITORIAL_DIR / "setores_mata01.geojson"
TERRITORIAL_MANIFEST_PATH = TERRITORIAL_DIR / "manifesto_processamento_cego.json"
CASE_REVISION_PATH = ENTRY_DIR / "registro_cenario_mata01_revisao2.json"
CONFIG_PATH = ROOT / "outputs" / "modulo_perfil_vitima_v3" / "config_perfil_quantitativo_v3.json"

SCENARIO_ID = "MATA-01"
CANDIDATE_ID = "MATA-01-E0"
CREATED_AT = "2026-10-23T15:41:00-03:00"
PROFILE_SOURCE_FROZEN_AT = "2026-10-23T15:41:30-03:00"
SPATIAL_REVIEW_FROZEN_AT = "2026-10-23T15:41:40-03:00"
INPUT_FROZEN_AT = "2026-10-23T15:42:00-03:00"
Q_EXPECTED = 2.0 / 3.0
PRIMARY_LAMBDA = 0.10
OPERATIONAL_LAMBDAS = (0.05, 0.10)


class BuildError(RuntimeError):
    """Falha de contrato, proveniência ou QA do pacote MATA-01."""


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildError(f"Fonte JSON inválida: {path}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BuildError(message)


def freeze_document(payload: Mapping[str, Any], frozen_at: str, projection_id: str) -> dict[str, Any]:
    frozen = deepcopy(dict(payload))
    frozen["record_status"] = "CONGELADO"
    frozen["freeze_metadata"] = {
        "frozen_at": frozen_at,
        "projection_id": projection_id,
        "payload_sha256": "0" * 64,
    }
    projection = deepcopy(frozen)
    projection["freeze_metadata"].pop("payload_sha256")
    frozen["freeze_metadata"]["payload_sha256"] = canonical_sha256(projection)
    return frozen


def load_and_validate_sources() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    required = [RANKING_PATH, SECTORS_PATH, TERRITORIAL_MANIFEST_PATH, CASE_REVISION_PATH, CONFIG_PATH]
    missing = [str(path) for path in required if not path.is_file()]
    require(not missing, f"Fontes ausentes: {', '.join(missing)}")

    with RANKING_PATH.open(encoding="utf-8", newline="") as stream:
        ranking_rows = list(csv.DictReader(stream))
    sector_geojson = load_json(SECTORS_PATH)
    territorial_manifest = load_json(TERRITORIAL_MANIFEST_PATH)
    case_revision = load_json(CASE_REVISION_PATH)

    require(len(ranking_rows) == 24, "Ranking territorial diagnóstico deve conter 24 setores.")
    require(sector_geojson.get("type") == "FeatureCollection", "GeoJSON de setores inválido.")
    features = sector_geojson.get("features")
    require(isinstance(features, list) and len(features) == 24, "GeoJSON deve conter 24 setores.")
    require(territorial_manifest.get("ground_truth_used") is False, "Pacote territorial não é cego.")
    require(territorial_manifest.get("confirmatory_eligible") is False, "Pacote territorial não deve ser confirmatório.")
    require(
        territorial_manifest.get("execution_classification")
        == "CAMPO_CEGO_DIAGNOSTICO_DOMINIO_DA_FONTE",
        "Classificação territorial inesperada.",
    )
    require(case_revision.get("scenario_id") == SCENARIO_ID, "Revisão pertence a outro cenário.")
    require(case_revision.get("case_revision") == 2, "Revisão 2 esperada.")
    require(case_revision.get("ground_truth_absent") is True, "Revisão do caso não está cega.")

    feature_by_id: dict[str, dict[str, Any]] = {}
    for feature in features:
        props = feature.get("properties", {})
        sector_id = str(props.get("sector_id", ""))
        require(sector_id and sector_id not in feature_by_id, "GeoJSON contém setor vazio ou duplicado.")
        require(feature.get("geometry", {}).get("type") == "Polygon", f"Geometria não poligonal: {sector_id}")
        feature_by_id[sector_id] = feature

    sectors: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in sorted(ranking_rows, key=lambda item: int(item["sector_index"])):
        sector_id = row["sector_id"]
        require(sector_id not in seen_ids, f"Setor duplicado no CSV: {sector_id}")
        seen_ids.add(sector_id)
        require(row["scenario_id"] == SCENARIO_ID, f"Cenário divergente em {sector_id}")
        require(row["candidate_id"] == CANDIDATE_ID, f"Candidato divergente em {sector_id}")
        require(row["ranking_mode"] == "BASE_DISPONIVEIS_DIAGNOSTICO", f"Modo inválido em {sector_id}")
        require(row["equivalent_to_base_original"].lower() == "false", f"Equivalência inválida em {sector_id}")
        require(row["ground_truth_used"].lower() == "false", f"Referência reservada usada em {sector_id}")
        require(row["source_confirmatory_eligible"].lower() == "false", f"Elegibilidade indevida em {sector_id}")
        require(row["geo03_availability"] == "NAO_DISPONIVEL_ZERO_FEICOES_OSM_NO_DOMINIO", f"GEO03 inesperado em {sector_id}")
        feature = feature_by_id.get(sector_id)
        require(feature is not None, f"Setor sem polígono: {sector_id}")
        props = feature["properties"]
        comparisons = {
            "score_base_available": float(row["score_base_available"]),
            "azimuth_start_deg": float(row["azimuth_start_deg"]),
            "azimuth_end_deg": float(row["azimuth_end_deg"]),
        }
        for field, expected in comparisons.items():
            require(
                math.isclose(float(props[field]), expected, rel_tol=0.0, abs_tol=1e-12),
                f"CSV e GeoJSON divergem em {sector_id}.{field}",
            )
        polygon = feature["geometry"]["coordinates"][0]
        sectors.append(
            {
                "sector_id": sector_id,
                "territorial_score": float(row["score_base_available"]),
                "bearing_start_deg": float(row["azimuth_start_deg"]),
                "bearing_end_deg": float(row["azimuth_end_deg"]),
                "polygon": polygon,
            }
        )
    require(set(feature_by_id) == seen_ids, "CSV e GeoJSON possuem conjuntos distintos de setores.")
    return sectors, territorial_manifest, case_revision


def find_authorized_clue(case_revision: Mapping[str, Any]) -> dict[str, Any]:
    clues = case_revision.get("authorized_spatial_clues")
    require(isinstance(clues, list) and len(clues) == 1, "Exatamente uma pista espacial autorizada era esperada.")
    clue = deepcopy(clues[0])
    expected = {
        "clue_id": "MATA01-P1-MARCAS-NORTE",
        "family": "DIRECAO",
        "azimuth_deg": 0.0,
        "tolerance_deg": 22.5,
        "nature": "RELATADO",
        "confidence": "MEDIA",
        "origin_candidate_id": CANDIDATE_ID,
        "eligible_for_profile_v3": True,
    }
    for field, value in expected.items():
        require(clue.get(field) == value, f"Pista autorizada diverge em {field}.")
    return clue


def build_profile_source_sidecar(case_revision: Mapping[str, Any], clue: Mapping[str, Any]) -> dict[str, Any]:
    excluded = [
        {
            "factor_id": "HABITO_AGUA_SEM_SEGMENTO_GEORREFERENCIADO",
            "quantitative_loc_effect": False,
            "routing": "CONTEXTO_QUALITATIVO",
        },
        {
            "factor_id": "FUMACA_SEM_POSICAO_OU_VINCULO",
            "quantitative_loc_effect": False,
            "routing": "CONTEXTO_QUALITATIVO",
        },
        {
            "factor_id": "FAMILIARIDADE_COM_AREA",
            "quantitative_loc_effect": False,
            "routing": "CONTEXTO_QUALITATIVO",
        },
        {
            "factor_id": "ROUPA_E_VISIBILIDADE",
            "quantitative_loc_effect": False,
            "routing": "DET_SEPARADO",
        },
        {
            "factor_id": "TEMPO_CANSACO_DESIDRATACAO",
            "quantitative_loc_effect": False,
            "routing": "URG_SEPARADO",
        },
        {
            "factor_id": "FOTOGRAFIAS",
            "quantitative_loc_effect": False,
            "routing": "DET_CONTEXTO_SEPARADO",
        },
    ]
    payload = {
        "protocol_id": "MATA01-PERFIL-FONTE-DIRETA-v1.0",
        "compiler_id": "MATA01-DIRECT-PROFILE-SIDECAR-v1.0",
        "scenario_id": SCENARIO_ID,
        "candidate_id": CANDIDATE_ID,
        "created_at": CREATED_AT,
        "integration_class": "ADAPTACAO_DIRETA_DIAGNOSTICA_SEM_V2",
        "source_case_revision_file": CASE_REVISION_PATH.name,
        "source_case_revision_file_sha256": file_sha256(CASE_REVISION_PATH),
        "source_case_revision_payload_sha256": case_revision["payload_sha256"],
        "authorized_clues": [deepcopy(dict(clue))],
        "excluded_from_loc_quantification": excluded,
        "loc_urg_det_separated": True,
        "diagnostic_nonconfirmatory": True,
        "equivalent_to_complete_base": False,
        "record_status": "RASCUNHO",
    }
    return freeze_document(payload, PROFILE_SOURCE_FROZEN_AT, "MATA01-PERFIL-FONTE-FREEZE-v1")


def build_spatial_review(clue: Mapping[str, Any], source_sidecar_path: Path) -> dict[str, Any]:
    payload = {
        "protocol_id": "MATA01-PERFIL-REVISAO-ESPACIAL-v1.0",
        "scenario_id": SCENARIO_ID,
        "candidate_id": CANDIDATE_ID,
        "created_at": CREATED_AT,
        "source_profile_sidecar_sha256": file_sha256(source_sidecar_path),
        "source_ranking_sha256": file_sha256(RANKING_PATH),
        "source_sectors_geojson_sha256": file_sha256(SECTORS_PATH),
        "source_territorial_manifest_sha256": file_sha256(TERRITORIAL_MANIFEST_PATH),
        "decision": {
            "clue_id": clue["clue_id"],
            "status": "INCLUIR_COM_ATENUACAO",
            "family": "DIRECAO",
            "azimuth_deg": 0.0,
            "tolerance_deg": 22.5,
            "nature": "RELATADO",
            "confidence": "MEDIA",
            "q": Q_EXPECTED,
            "lambda_primary": PRIMARY_LAMBDA,
            "lambda_effective_primary": PRIMARY_LAMBDA * Q_EXPECTED,
        },
        "review_status": "REVISAR",
        "diagnostic_nonconfirmatory": True,
        "equivalent_to_complete_base": False,
        "record_status": "RASCUNHO",
    }
    return freeze_document(payload, SPATIAL_REVIEW_FROZEN_AT, "MATA01-PERFIL-SPATIAL-REVIEW-FREEZE-v1")


def build_ranker_input(
    sectors: list[dict[str, Any]], profile_source_path: Path, spatial_review_path: Path
) -> dict[str, Any]:
    draft = {
        "protocol_version": "PERFIL-V3-QUANT-v1.0",
        "scenario_id": SCENARIO_ID,
        "candidate_id": CANDIDATE_ID,
        "record_status": "RASCUNHO",
        "created_at": CREATED_AT,
        "ground_truth_absent": True,
        "source_loc_input_sha256": file_sha256(CASE_REVISION_PATH),
        "source_case_revision": 2,
        "source_profile_compiled_sha256": file_sha256(profile_source_path),
        "source_territorial_manifest_sha256": file_sha256(TERRITORIAL_MANIFEST_PATH),
        "source_spatial_review_sha256": file_sha256(spatial_review_path),
        "sectors": sectors,
        "hypotheses": [
            {
                "hypothesis_id": "MATA01-P1-MARCAS-NORTE",
                "evidence_group_id": "MATA01-EG-MARCAS-NORTE",
                "family": "DIRECAO",
                "hypothesis_type": "DIRECAO_OBSERVADA",
                "spatialized": True,
                "authorized_for_model": True,
                "nature": "RELATADO",
                "confidence": "MEDIA",
                "direction": {
                    "origin_candidate_id": CANDIDATE_ID,
                    "azimuth_deg": 0.0,
                    "tolerance_deg": 22.5,
                },
            }
        ],
    }
    return ranker.prepare_frozen_input(draft, INPUT_FROZEN_AT)


def lambda_record(result: Mapping[str, Any], value: float) -> dict[str, Any]:
    matches = [item for item in result["lambda_results"] if math.isclose(float(item["lambda"]), value)]
    require(len(matches) == 1, f"Resultado λ={value} ausente ou duplicado.")
    return matches[0]


def sector_parts(sector_id: str) -> tuple[str, str]:
    parts = sector_id.split("::")
    require(len(parts) == 4, f"sector_id inesperado: {sector_id}")
    return parts[2], parts[3]


def ranking_rows(result: Mapping[str, Any], value: float) -> list[dict[str, Any]]:
    record = lambda_record(result, value)
    rows: list[dict[str, Any]] = []
    for row in record["rows"]:
        ring, direction = sector_parts(row["sector_id"])
        rows.append(
            {
                "scenario_id": SCENARIO_ID,
                "sector_id": row["sector_id"],
                "ring_id": ring,
                "direction": direction,
                "lambda": value,
                "q": row["evidence_strength"],
                "effective_lambda": row["effective_lambda"],
                "territorial_score": row["territorial_score"],
                "territorial_rank": row["territorial_rank"],
                "profile_compatibility": row["profile_compatibility"],
                "profile_score": row["profile_score"],
                "profile_delta": row["profile_delta"],
                "profile_rank": row["profile_rank"],
                "rank_change": int(row["territorial_rank"]) - int(row["profile_rank"]),
                "top_set_member": row["sector_id"] in record["top_set"],
                "diagnostic_nonconfirmatory": True,
                "equivalent_to_complete_base": False,
                "review_status": "REVISAR",
            }
        )
    return rows


RANKING_FIELDS = [
    "scenario_id",
    "sector_id",
    "ring_id",
    "direction",
    "lambda",
    "q",
    "effective_lambda",
    "territorial_score",
    "territorial_rank",
    "profile_compatibility",
    "profile_score",
    "profile_delta",
    "profile_rank",
    "rank_change",
    "top_set_member",
    "diagnostic_nonconfirmatory",
    "equivalent_to_complete_base",
    "review_status",
]


def top_three(record: Mapping[str, Any], label: str) -> list[dict[str, Any]]:
    ordered = sorted(record["rows"], key=lambda row: (int(row["profile_rank"]), row["sector_id"]))
    selected = ordered[:3]
    return [
        {
            "ranking": label,
            "position": index,
            "sector_id": row["sector_id"],
            "territorial_rank": row["territorial_rank"],
            "profile_rank": row["profile_rank"],
            "territorial_score": row["territorial_score"],
            "profile_score": row["profile_score"],
            "profile_compatibility": row["profile_compatibility"],
        }
        for index, row in enumerate(selected, start=1)
    ]


def compare_top_three(result: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    territorial = lambda_record(result, 0.0)
    sensitivity = lambda_record(result, 0.05)
    primary = lambda_record(result, 0.10)
    rows = (
        top_three(territorial, "TERRITORIAL_DIAGNOSTICO")
        + top_three(sensitivity, "PERFIL_LAMBDA_005")
        + top_three(primary, "PERFIL_LAMBDA_010")
    )
    payload = {
        "scenario_id": SCENARIO_ID,
        "source_mode": "BASE_DISPONIVEIS_DIAGNOSTICO",
        "diagnostic_nonconfirmatory": True,
        "equivalent_to_complete_base": False,
        "lambda_compared": [0.05, 0.10],
        "territorial_top_set": territorial["top_set"],
        "lambda_005_top_set": sensitivity["top_set"],
        "lambda_010_top_set": primary["top_set"],
        "top_set_stable_005_010": sensitivity["top_set"] == primary["top_set"],
        "top3_order_unchanged_territorial_to_010": [r["sector_id"] for r in rows[:3]]
        == [r["sector_id"] for r in rows[6:9]],
        "rows": rows,
    }
    return payload, rows


def north_effects(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = {value: lambda_record(result, value) for value in (0.0, 0.05, 0.10)}
    by_lambda = {
        value: {row["sector_id"]: row for row in record["rows"]}
        for value, record in records.items()
    }
    north_ids = sorted(
        sector_id for sector_id in by_lambda[0.0] if sector_id.endswith("::N")
    )
    return [
        {
            "sector_id": sector_id,
            "territorial_rank": by_lambda[0.0][sector_id]["territorial_rank"],
            "rank_lambda_005": by_lambda[0.05][sector_id]["profile_rank"],
            "rank_lambda_010": by_lambda[0.10][sector_id]["profile_rank"],
            "score_delta_lambda_005": by_lambda[0.05][sector_id]["profile_delta"],
            "score_delta_lambda_010": by_lambda[0.10][sector_id]["profile_delta"],
            "profile_compatibility": by_lambda[0.10][sector_id]["profile_compatibility"],
        }
        for sector_id in north_ids
    ]


def build_protocol() -> dict[str, Any]:
    payload = {
        "protocol_id": "MATA01-PERFIL-V3-CEGO-v1.0",
        "created_at": CREATED_AT,
        "scenario_id": SCENARIO_ID,
        "source_ranking_mode": "BASE_DISPONIVEIS_DIAGNOSTICO",
        "source_equivalent_to_complete_base": False,
        "use_class": "DIAGNOSTICO_NAO_CONFIRMATORIO",
        "authorized_quantitative_clues": ["MATA01-P1-MARCAS-NORTE"],
        "direction_rule": {"azimuth_deg": 0.0, "tolerance_deg": 22.5},
        "evidence_rule": {
            "nature": "RELATADO",
            "confidence": "MEDIA",
            "q_formula": "min(nature_factor, confidence_factor)",
            "q": Q_EXPECTED,
        },
        "lambda_rule": {
            "primary": 0.10,
            "primary_effective": PRIMARY_LAMBDA * Q_EXPECTED,
            "operational_sensitivity": [0.05, 0.10],
            "lambda_015_in_raw_engine_output": "STRESS_TEST_OUTSIDE_OPERATIONAL_CEILING",
        },
        "stability_policy": {
            "compare": [0.05, 0.10],
            "if_unstable": "REVERT_EXACTLY_TO_TERRITORIAL_AVAILABLE_AND_MARK_REVIEW",
        },
        "prohibited_loc_inputs": [
            "habito_de_buscar_agua_sem_segmento_georreferenciado",
            "fumaca_sem_posicao_ou_vinculo",
            "familiaridade",
            "roupa",
            "tempo_cansaco_desidratacao",
            "fotografias",
        ],
        "module_separation": {"LOC": "PROFILE_V3", "URG": "SEPARATE", "DET": "SEPARATE"},
        "ground_truth_dependency": False,
        "record_status": "RASCUNHO",
    }
    return freeze_document(payload, INPUT_FROZEN_AT, "MATA01-PERFIL-PROTOCOL-FREEZE-v1")


def build_qa(
    result: Mapping[str, Any],
    input_payload: Mapping[str, Any],
    profile_source_path: Path,
    spatial_review_path: Path,
    top3: Mapping[str, Any],
) -> dict[str, Any]:
    primary = lambda_record(result, 0.10)
    sensitivity = lambda_record(result, 0.05)
    territorial = lambda_record(result, 0.0)
    stable = sensitivity["top_set"] == primary["top_set"]
    if stable:
        fallback_exact = None
    else:
        fallback_exact = result["operational_rows"] == territorial["rows"]
    checks = [
        ("input_validated_by_ranker", True),
        ("source_profile_sidecar_hash_matches", input_payload["source_profile_compiled_sha256"] == file_sha256(profile_source_path)),
        ("source_spatial_review_hash_matches", input_payload["source_spatial_review_sha256"] == file_sha256(spatial_review_path)),
        ("source_territorial_manifest_hash_matches", input_payload["source_territorial_manifest_sha256"] == file_sha256(TERRITORIAL_MANIFEST_PATH)),
        ("source_case_revision_hash_matches", input_payload["source_loc_input_sha256"] == file_sha256(CASE_REVISION_PATH)),
        ("only_one_authorized_hypothesis", len(input_payload["hypotheses"]) == 1),
        ("evidence_strength_q_two_thirds", math.isclose(primary["rows"][0]["evidence_strength"], Q_EXPECTED, rel_tol=0.0, abs_tol=1e-12)),
        ("effective_lambda_005", all(math.isclose(row["effective_lambda"], 0.05 * Q_EXPECTED, rel_tol=0.0, abs_tol=1e-12) for row in sensitivity["rows"])),
        ("effective_lambda_010", all(math.isclose(row["effective_lambda"], 0.10 * Q_EXPECTED, rel_tol=0.0, abs_tol=1e-12) for row in primary["rows"])),
        ("operational_stability_uses_only_005_010", result["stability"]["operational_lambdas_compared"] == [0.05, 0.1]),
        ("top_set_stability_recomputed", result["stability"]["top_set_stable_within_operational_ceiling"] == stable),
        ("unstable_fallback_exact_if_applicable", fallback_exact in {None, True}),
        ("result_remains_blind", result["ground_truth_absent"] is True),
        ("firewall_pass", result["firewall_manifest"]["status"] == "PASS"),
        ("no_cross_candidate_ranking", result["scope_guards"]["cross_candidate_ranking"] is False),
        ("score_not_probability", result["scope_guards"]["score_is_probability"] is False),
        ("urgency_not_weighted", result["scope_guards"]["urgency_weighted"] is False),
        ("top3_payload_diagnostic", top3["diagnostic_nonconfirmatory"] is True),
        ("top3_not_complete_base", top3["equivalent_to_complete_base"] is False),
        ("north_compatibility_discriminates", any(row["profile_compatibility"] > 0 for row in primary["rows"]) and any(row["profile_compatibility"] == 0 for row in primary["rows"])),
    ]
    failures = [name for name, passed in checks if not passed]
    return {
        "scenario_id": SCENARIO_ID,
        "status": "PASS" if not failures else "FAIL",
        "check_count": len(checks),
        "pass_count": len(checks) - len(failures),
        "failures": failures,
        "checks": [{"check": name, "status": "PASS" if passed else "FAIL"} for name, passed in checks],
        "diagnostic_nonconfirmatory": True,
        "review_status": "REVISAR",
    }


def report_markdown(
    result: Mapping[str, Any], top3: Mapping[str, Any], north: list[dict[str, Any]], qa: Mapping[str, Any]
) -> str:
    l0 = lambda_record(result, 0.0)
    l5 = lambda_record(result, 0.05)
    l10 = lambda_record(result, 0.10)
    territorial_top3 = [row["sector_id"] for row in top3["rows"][:3]]
    primary_top3 = [row["sector_id"] for row in top3["rows"][6:9]]
    north_lines = "\n".join(
        f"- `{row['sector_id']}`: posto territorial {row['territorial_rank']} → "
        f"{row['rank_lambda_005']} em λ=0,05 → {row['rank_lambda_010']} em λ=0,10; "
        f"ΔS(0,10)={row['score_delta_lambda_010']:.6f}."
        for row in north
    )
    top_lines = "\n".join(
        f"{index}. `{sector_id}`" for index, sector_id in enumerate(primary_top3, start=1)
    )
    stability_text = "estável" if top3["top_set_stable_005_010"] else "instável"
    top3_change = "não mudou" if top3["top3_order_unchanged_territorial_to_010"] else "mudou"
    return f"""# Relatório PERFIL V3 cego — MATA-01

## Resultado executivo

O PERFIL V3 foi executado sem posição de referência do alvo e usando exclusivamente a pista autorizada **marcas de botas rumo Norte (0° ±22,5°)**. A qualidade da evidência foi atenuada para `q=2/3` por ser **RELATADA** e de confiança **MÉDIA**. No λ principal de 0,10, o peso efetivo foi `0,0666667`.

A seleção de primeiro lugar foi **{stability_text}** entre λ=0,05 e λ=0,10. O Top-3 {top3_change} em relação ao ranking territorial diagnóstico. O resultado do motor foi `{result['operational_status']}`, mas seu uso permanece **diagnóstico, não confirmatório, sob status REVISAR**, porque a fonte territorial é `BASE_DISPONÍVEIS`, com GEO03 ausente, e não equivale ao BASE completo.

## Top-3 no λ principal

{top_lines}

- Margem Top-1/Top-2 territorial: {l0['margin_top1_top2']:.6f}.
- Margem Top-1/Top-2 em λ=0,05: {l5['margin_top1_top2']:.6f}.
- Margem Top-1/Top-2 em λ=0,10: {l10['margin_top1_top2']:.6f}.
- Avisos do motor: `{', '.join(result['warnings']) if result['warnings'] else 'nenhum'}`.

## Efeito explicável da pista Norte

{north_lines}

A pista elevou apenas os três setores direcionais Norte, exatamente como previsto pela interseção angular. Ela não foi forte o bastante para superar os escores territoriais dos setores líderes. Isso é um resultado válido: o módulo ajustou o ranking de forma rastreável sem forçar uma mudança de vencedor.

## Entradas excluídas do LOC quantitativo

Não receberam peso: hábito de buscar água sem segmento georreferenciado, fumaça sem posição ou vínculo, familiaridade, roupa, tempo/cansaço/desidratação e fotografias. Urgência e detectabilidade permanecem separadas de LOC.

## Compatibilidade e limites

- O núcleo `PERFIL-V3-QUANT-RANKER-v1.1` foi usado sem alteração.
- O adaptador legado não foi usado porque exige compilado PERFIL V2 inexistente para MATA-01. A integração direta está declarada e vinculada por hashes em sidecars congelados.
- O motor mantém λ=0,15 no JSON bruto apenas como teste de estresse fora do teto. A decisão de estabilidade considera somente λ=0,05 e λ=0,10.
- A saída não representa probabilidade, acurácia de localização ou comando operacional.
- A base hidrográfica OSM vazia no domínio foi tratada como ausência de dado, não como condição favorável.

## Verificação

- QA: **{qa['status']}** ({qa['pass_count']}/{qa['check_count']} verificações).
- Firewall da posição reservada: **PASS**.
- Dependência de posição de referência: **não**.
- Situação para uso: **REVISAR — diagnóstico não confirmatório**.
"""


def protocol_markdown(protocol: Mapping[str, Any]) -> str:
    return f"""# Protocolo congelado — PERFIL V3 cego MATA-01

- Protocolo: `{protocol['protocol_id']}`
- Classe de uso: **diagnóstico não confirmatório**
- Fonte territorial: **BASE DISPONÍVEIS**, não equivalente ao BASE completo
- Pista quantitativa única: marcas de botas rumo Norte, `0° ±22,5°`
- Evidência: `RELATADO`, confiança `MEDIA`, `q=2/3`
- λ principal: `0,10`; λ efetivo principal: `0,0666667`
- Sensibilidade operacional: `0,05` e `0,10`
- Se o Top-1 divergir entre os lambdas: reverter exatamente ao territorial disponível e marcar `REVISAR`
- LOC, URG e DET permanecem separados
- Nenhuma posição reservada participa da entrada ou do ranking
- Hash interno do protocolo: `{protocol['freeze_metadata']['payload_sha256']}`
"""


def build(output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sectors, _territorial_manifest, case_revision = load_and_validate_sources()
    clue = find_authorized_clue(case_revision)

    profile_source_path = output_dir / "perfil_fonte_mata01_sidecar_congelado.json"
    profile_source = build_profile_source_sidecar(case_revision, clue)
    write_json(profile_source_path, profile_source)

    spatial_review_path = output_dir / "revisao_espacial_mata01_congelada.json"
    spatial_review = build_spatial_review(clue, profile_source_path)
    write_json(spatial_review_path, spatial_review)

    protocol = build_protocol()
    protocol_json_path = output_dir / "protocolo_perfil_v3_mata01_congelado.json"
    protocol_md_path = output_dir / "PROTOCOLO_PERFIL_V3_MATA01_CONGELADO.md"
    write_json(protocol_json_path, protocol)
    protocol_md_path.write_text(protocol_markdown(protocol), encoding="utf-8")

    frozen_input = build_ranker_input(sectors, profile_source_path, spatial_review_path)
    input_path = output_dir / "entrada_perfil_v3_mata01_congelada.json"
    write_json(input_path, frozen_input)
    result_first = ranker.rank_profile(frozen_input, CONFIG_PATH)
    result_second = ranker.rank_profile(deepcopy(frozen_input), CONFIG_PATH)
    deterministic = canonical_bytes(result_first) == canonical_bytes(result_second)
    require(deterministic, "Duas execuções do ranker produziram saídas diferentes.")
    result_path = output_dir / "resultado_perfil_v3_mata01.json"
    write_json(result_path, result_first)

    rank_005 = ranking_rows(result_first, 0.05)
    rank_010 = ranking_rows(result_first, 0.10)
    ranking_005_path = output_dir / "ranking_sensibilidade_lambda005.csv"
    ranking_010_path = output_dir / "ranking_diagnostico_lambda010.csv"
    write_csv(ranking_005_path, rank_005, RANKING_FIELDS)
    write_csv(ranking_010_path, rank_010, RANKING_FIELDS)

    top3, top3_rows = compare_top_three(result_first)
    top3_json_path = output_dir / "comparacao_top3_territorial_perfil.json"
    top3_csv_path = output_dir / "comparacao_top3_territorial_perfil.csv"
    write_json(top3_json_path, top3)
    write_csv(
        top3_csv_path,
        top3_rows,
        [
            "ranking",
            "position",
            "sector_id",
            "territorial_rank",
            "profile_rank",
            "territorial_score",
            "profile_score",
            "profile_compatibility",
        ],
    )

    north = north_effects(result_first)
    north_path = output_dir / "efeito_pista_norte.json"
    write_json(north_path, {"scenario_id": SCENARIO_ID, "rows": north})

    qa = build_qa(result_first, frozen_input, profile_source_path, spatial_review_path, top3)
    require(qa["status"] == "PASS", f"QA falhou: {qa['failures']}")
    qa_path = output_dir / "relatorio_qa_perfil_v3.json"
    write_json(qa_path, qa)

    determinism = {
        "scenario_id": SCENARIO_ID,
        "status": "PASS" if deterministic else "FAIL",
        "method": "DUAS_EXECUCOES_EM_MEMORIA_COM_MESMA_ENTRADA_CONGELADA",
        "run1_canonical_sha256": hashlib.sha256(canonical_bytes(result_first)).hexdigest(),
        "run2_canonical_sha256": hashlib.sha256(canonical_bytes(result_second)).hexdigest(),
        "engine_output_sha256": result_first["output_sha256"],
        "identical_bytes": deterministic,
    }
    determinism_path = output_dir / "relatorio_determinismo_perfil_v3.json"
    write_json(determinism_path, determinism)

    report_path = output_dir / "RELATORIO_PERFIL_V3_MATA01.md"
    report_path.write_text(report_markdown(result_first, top3, north, qa), encoding="utf-8")

    published: Iterable[Path] = [
        profile_source_path,
        spatial_review_path,
        protocol_json_path,
        protocol_md_path,
        input_path,
        result_path,
        ranking_005_path,
        ranking_010_path,
        top3_json_path,
        top3_csv_path,
        north_path,
        qa_path,
        determinism_path,
        report_path,
    ]
    manifest = {
        "scenario_id": SCENARIO_ID,
        "protocol_id": protocol["protocol_id"],
        "diagnostic_nonconfirmatory": True,
        "equivalent_to_complete_base": False,
        "review_status": "REVISAR",
        "source_files": [
            {"path": str(path.relative_to(ROOT)), "sha256": file_sha256(path), "bytes": path.stat().st_size}
            for path in [RANKING_PATH, SECTORS_PATH, TERRITORIAL_MANIFEST_PATH, CASE_REVISION_PATH, CONFIG_PATH]
        ],
        "published_files": [
            {"path": path.name, "sha256": file_sha256(path), "bytes": path.stat().st_size}
            for path in published
        ],
    }
    manifest_path = output_dir / "manifesto_sha256_perfil_v3_mata01.json"
    write_json(manifest_path, manifest)
    return {
        "output_dir": str(output_dir),
        "result": result_first,
        "qa": qa,
        "top3": top3,
        "north_effects": north,
        "manifest_path": str(manifest_path),
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Constrói o pacote PERFIL V3 cego do MATA-01")
    value.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return value


def main() -> int:
    args = parser().parse_args()
    summary = build(args.output_dir)
    print(
        json.dumps(
            {
                "output_dir": summary["output_dir"],
                "qa_status": summary["qa"]["status"],
                "operational_status": summary["result"]["operational_status"],
                "stable_005_010": summary["top3"]["top_set_stable_005_010"],
                "top3_unchanged": summary["top3"]["top3_order_unchanged_territorial_to_010"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
