#!/usr/bin/env python3
"""Avalia uma referência revelada do RURAL-01 contra T0--T4 congelados.

O programa é deliberadamente pós-abertura. Ele nunca recalcula a superfície de
resistência, os setores, os custos, os corredores ou os rankings congelados.
Antes de ler a referência, valida o ledger T4 e o manifesto territorial v1 por
tamanho e SHA-256. A publicação é determinística, versionada e atômica.

Semântica: custos são metros equivalentes de esforço de uma heurística de
desenvolvimento. Corredores são linhas diagnósticas de menor custo até pontos
representativos; não são rotas observadas nem uma largura física de busca.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
T4_DIR = ROOT / "outputs/campo_rural01/processamento_movimento_cego_v2"
V1_DIR = ROOT / "outputs/campo_rural01/processamento_cego_v1"
DEFAULT_OUTPUT_DIR = ROOT / "outputs/campo_rural01/avaliacao_pos_abertura_v1"

T4_LEDGER = T4_DIR / "ledger_congelamento_T4_mov_v2.json"
V1_MANIFEST = V1_DIR / "manifesto_processamento_cego.json"
GRID_PATH = T4_DIR / "grade_resistencia.csv"
SECTOR_SUMMARY_PATH = T4_DIR / "setores_mov_v2.csv"
CORRIDOR_PATH = T4_DIR / "corredores_mov_v2.geojson"
V1_SECTORS_PATH = V1_DIR / "setores_rural01.geojson"
V1_TOP3_PATH = V1_DIR / "top3_rural01.json"
MOV_RESULT_PATH = T4_DIR / "resultado_mov_v2.json"
CONFIG_PATH = HERE / "config_avaliacao_t5_t6_v1.json"
PROTOCOL_PATH = HERE / "PROTOCOLO_AVALIACAO_RURAL01_T45_T6_v1_CONGELADO.md"
REFERENCE_SCHEMA_PATH = HERE / "schema_referencia_t5_v1.json"
EVALUATOR_FREEZE_LEDGER = (
    ROOT
    / "outputs/campo_rural01/avaliador_t45_congelado_v1"
    / "ledger_congelamento_avaliador_t45_v1.json"
)

T45_REQUIRED_BASENAMES = {
    "PROTOCOLO_AVALIACAO_RURAL01_T45_T6_v1_CONGELADO.md",
    "config_avaliacao_t5_t6_v1.json",
    "schema_referencia_t5_v1.json",
    "MODELO_REGISTRO_T5_SEM_COORDENADA.json",
    "evaluate_rural01_reference.py",
    "test_evaluate_rural01_reference.py",
    "congelar_avaliador_t45.py",
    "relatorio_testes_avaliador_t45_v1.json",
    "relatorio_qa_avaliador_t45_v1.json",
    "RESUMO_CONGELAMENTO_T45.md",
}
T45_ALLOWED_FILE_ROLES = {"T45_EVALUATOR_PACKAGE", "T45_FREEZE_RECEIPT"}

PROTOCOL_ID = "RURAL01-EVAL-T45-T6-v1.0"
SCENARIO_ID = "RURAL-01"
SOURCE_LAT = 0.188611
SOURCE_LON = -51.155556
EARTH_RADIUS_M = 6_371_008.8
DOMAIN_RADIUS_M = 1500.0
DOMAIN_TOLERANCE_M = 0.05
GRID_RESOLUTION_M = 30.0
GRID_MAX_SNAP_M = 21.2132034356
COMPARISON_EPSILON_M = 0.05
NUMERIC_EPSILON_M = COMPARISON_EPSILON_M

PRIMARY_BASE_SCENARIOS = (
    "H_REDE_DISPONIVEL__BASE",
    "H_FORA_REDE__BASE",
)
SENSITIVITY_SCENARIOS = (
    "H_REDE_DISPONIVEL__SUAVE",
    "H_REDE_DISPONIVEL__BASE",
    "H_REDE_DISPONIVEL__FORTE",
    "H_FORA_REDE__SUAVE",
    "H_FORA_REDE__BASE",
    "H_FORA_REDE__FORTE",
)
ABLATION_SCENARIOS = (
    "ABL__SEM_HIDRO",
    "ABL__SEM_COBERTURA",
    "ABL__SEM_RELEVO",
    "ABL__SEM_DESCONTO_REDE",
)
COUNTERFACTUAL_SCENARIOS = ("SENS__COM_DUPLICACAO_HIDRO_COBERTURA",)

SCIENTIFIC_OUTPUTS = (
    "registro_abertura_referencia.json",
    "resultado_avaliacao_t5_t6.json",
    "metricas_cenarios.csv",
    "areas_bandas_custo.csv",
    "metricas_corredores.csv",
    "referencia_avaliacao_t5_t6.geojson",
    "relatorio_qa_t5_t6.json",
    "RELATORIO_AVALIACAO_RURAL01_T6.md",
)


class EvaluationContractError(ValueError):
    """Violação de integridade, esquema ou regra pré-especificada."""


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return value


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fields})


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_aware_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationContractError(f"{field} deve ser data-hora ISO 8601 com fuso")
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise EvaluationContractError(f"{field} deve ser data-hora ISO 8601 válida") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvaluationContractError(f"{field} deve declarar o fuso horário")
    return parsed


def _require_exact_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    allowed: set[str],
    field: str,
) -> None:
    missing = sorted(required - set(value))
    extras = sorted(set(value) - allowed)
    if missing:
        raise EvaluationContractError(f"{field} sem campos obrigatórios: {', '.join(missing)}")
    if extras:
        raise EvaluationContractError(f"{field} contém campos não permitidos: {', '.join(extras)}")


def _finite(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise EvaluationContractError(f"{field} deve ser numérico") from exc
    if not math.isfinite(number):
        raise EvaluationContractError(f"{field} deve ser finito")
    return number


def _safe_root_path(root: Path, value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise EvaluationContractError(f"Caminho fora da raiz do projeto: {value}") from exc
    return candidate


def _verify_file_records(records: Sequence[Mapping[str, Any]], root: Path) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for item in records:
        path = _safe_root_path(root, str(item.get("path", "")))
        expected_bytes = int(item.get("bytes", -1))
        expected_sha = str(item.get("sha256", ""))
        exists = path.is_file()
        actual_bytes = path.stat().st_size if exists else None
        actual_sha = sha256_file(path) if exists else None
        ok = exists and actual_bytes == expected_bytes and actual_sha == expected_sha
        verified.append(
            {
                "path": str(path.relative_to(root.resolve())) if exists else str(item.get("path", "")),
                "exists": exists,
                "expected_bytes": expected_bytes,
                "actual_bytes": actual_bytes,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "valid": ok,
            }
        )
    return verified


def verify_t4_ledger(ledger_path: Path = T4_LEDGER, root: Path = ROOT) -> dict[str, Any]:
    """Valida payload, estado e todos os arquivos registrados no ledger T4."""
    ledger = load_json(ledger_path)
    projected = {key: value for key, value in ledger.items() if key != "payload_sha256"}
    payload_valid = ledger.get("payload_sha256") == canonical_hash(projected)
    records = _verify_file_records(ledger.get("files", []), root)
    checks = {
        "payload_sha256_valid": payload_valid,
        "status_frozen_before_reveal": ledger.get("status") == "CONGELADO_ANTES_DA_REVELACAO",
        "freeze_stage_t4": ledger.get("freeze_stage") == "T4_OUTPUT_AND_MANIFEST_FREEZE",
        "ground_truth_unused": ledger.get("ground_truth_used") is False,
        "reference_inaccessible_to_engine": ledger.get("reference_package_accessible_to_engine") is False,
        "all_ledger_checks_passed": bool(ledger.get("checks")) and all(ledger.get("checks", {}).values()),
        "file_count_matches": int(ledger.get("file_count", -1)) == len(records),
        "all_files_match": bool(records) and all(item["valid"] for item in records),
    }
    receipt = {
        "status": "INSUMOS_VERIFICADOS" if all(checks.values()) else "NAO_AVALIAVEL_INTEGRIDADE",
        "technical_status": "PASS" if all(checks.values()) else "FAIL",
        "ledger_path": str(ledger_path.resolve().relative_to(root.resolve())),
        "ledger_sha256": sha256_file(ledger_path),
        "payload_sha256": ledger.get("payload_sha256"),
        "checks": checks,
        "verified_file_count": sum(bool(item["valid"]) for item in records),
        "listed_file_count": len(records),
    }
    if receipt["technical_status"] != "PASS":
        failures = [name for name, passed in checks.items() if not passed]
        raise EvaluationContractError(f"Falha de integridade/hash no ledger T4: {', '.join(failures)}")
    return receipt


def verify_v1_manifest(manifest_path: Path = V1_MANIFEST, root: Path = ROOT) -> dict[str, Any]:
    """Valida o manifesto v1 e todos os arquivos que ele lista."""
    manifest = load_json(manifest_path)
    records = _verify_file_records(manifest.get("files", []), root)
    checks = {
        "protocol_id_valid": manifest.get("protocol_id") == "RURAL01-BLIND-SET-v1.0",
        "ground_truth_unused": manifest.get("ground_truth_used") is False,
        "confirmatory_eligible_false": manifest.get("confirmatory_eligible") is False,
        "determinism_preserved": manifest.get("determinism_run1_hashes_match_published_outputs") is True,
        "listed_files_present": bool(records),
        "all_files_match": bool(records) and all(item["valid"] for item in records),
    }
    receipt = {
        "status": "INSUMOS_VERIFICADOS" if all(checks.values()) else "NAO_AVALIAVEL_INTEGRIDADE",
        "technical_status": "PASS" if all(checks.values()) else "FAIL",
        "manifest_path": str(manifest_path.resolve().relative_to(root.resolve())),
        "manifest_sha256": sha256_file(manifest_path),
        "checks": checks,
        "verified_file_count": sum(bool(item["valid"]) for item in records),
        "listed_file_count": len(records),
    }
    if receipt["technical_status"] != "PASS":
        failures = [name for name, passed in checks.items() if not passed]
        raise EvaluationContractError(f"Falha de integridade/hash no manifesto v1: {', '.join(failures)}")
    return receipt


def verify_t45_opening_gate(
    reference: Mapping[str, Any],
    ledger_path: Path = EVALUATOR_FREEZE_LEDGER,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Confere que o registro T5 foi aberto somente após o selo íntegro T4.5."""
    normalized = validate_reference(reference, require_frozen_record=True)
    ledger_path = ledger_path.resolve()
    if not ledger_path.is_file():
        raise EvaluationContractError("Ledger T4.5 do avaliador ausente; abertura T5 não autorizada")
    ledger = load_json(ledger_path)
    projected = {key: value for key, value in ledger.items() if key != "payload_sha256"}
    raw_records = ledger.get("files")
    records = _verify_file_records(raw_records, root) if isinstance(raw_records, list) else []
    record_roles = {
        str(item.get("role")) for item in raw_records or [] if isinstance(item, Mapping)
    }
    record_basenames = {
        Path(str(item.get("path", ""))).name
        for item in raw_records or []
        if isinstance(item, Mapping)
    }
    tests = ledger.get("tests") if isinstance(ledger.get("tests"), Mapping) else {}
    qa = ledger.get("qa") if isinstance(ledger.get("qa"), Mapping) else {}
    checks: dict[str, bool] = {
        "protocol_id_valid": ledger.get("protocol_id") == PROTOCOL_ID,
        "stage_valid": ledger.get("stage") == "T4_5_PRE_REVEAL_EVALUATOR_FREEZE",
        "status_frozen": ledger.get("status") == "CONGELADO_ANTES_DA_REVELACAO",
        "reference_absent_when_frozen": (
            ledger.get("ground_truth_received") is False
            and ledger.get("reference_coordinates_present") is False
        ),
        "payload_sha256_valid": ledger.get("payload_sha256") == canonical_hash(projected),
        "reference_opening_authorized": ledger.get("reference_opening_allowed_after_this_ledger") is True,
        "retuning_forbidden": ledger.get("retuning_after_reference_opening") is False,
        "records_nonempty": bool(records),
        "file_count_matches": int(ledger.get("file_count", -1)) == len(records),
        "all_listed_files_match": bool(records) and all(item["valid"] for item in records),
        "file_roles_valid": (
            bool(record_roles)
            and record_roles <= T45_ALLOWED_FILE_ROLES
            and T45_ALLOWED_FILE_ROLES <= record_roles
        ),
        "required_artifacts_listed": T45_REQUIRED_BASENAMES <= record_basenames,
        "tests_passed": tests.get("status") == "PASS" and int(tests.get("tests_run", -1)) >= 20,
        "qa_passed": (
            qa.get("status") == "PASS"
            and int(qa.get("passed_check_count", -1)) == int(qa.get("check_count", -2))
            and int(qa.get("check_count", -2)) > 0
        ),
    }
    if not all(checks.values()):
        failed = [key for key, value in checks.items() if not value]
        raise EvaluationContractError(f"Falha de integridade no selo T4.5: {', '.join(failed)}")

    actual_sha = sha256_file(ledger_path)
    declared_sha = str(normalized["opening_record"]["evaluator_freeze_manifest_sha256"])
    if declared_sha.casefold() != actual_sha:
        raise EvaluationContractError("Hash do selo T4.5 declarado na abertura diverge do ledger real")
    frozen_at = _parse_aware_datetime(ledger.get("created_at_local"), "ledger.created_at_local")
    opened_at = _parse_aware_datetime(normalized["opening_record"].get("opened_at"), "opening.opened_at")
    if opened_at <= frozen_at:
        raise EvaluationContractError("opening.opened_at deve ser posterior ao congelamento T4.5")
    return {
        "status": "ABERTURA_T5_AUTORIZADA",
        "technical_status": "PASS",
        "ledger_path": str(ledger_path.relative_to(root.resolve())),
        "ledger_sha256": actual_sha,
        "ledger_payload_sha256": ledger.get("payload_sha256"),
        "frozen_at": ledger.get("created_at_local"),
        "opened_at": normalized["opening_record"].get("opened_at"),
        "opened_after_freeze": True,
        "listed_file_count": len(records),
    }


def aeqd_forward(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    """AEQD esférica congelada; retorna leste/norte em metros."""
    phi = math.radians(_finite(lat, "latitude"))
    lam = math.radians(_finite(lon, "longitude"))
    phi0 = math.radians(_finite(lat0, "latitude_origem"))
    lam0 = math.radians(_finite(lon0, "longitude_origem"))
    delta = (lam - lam0 + math.pi) % (2.0 * math.pi) - math.pi
    cos_c = max(
        -1.0,
        min(1.0, math.sin(phi0) * math.sin(phi) + math.cos(phi0) * math.cos(phi) * math.cos(delta)),
    )
    c = math.acos(cos_c)
    k = 1.0 if c <= 1e-15 else c / math.sin(c)
    x = EARTH_RADIUS_M * k * math.cos(phi) * math.sin(delta)
    y = EARTH_RADIUS_M * k * (
        math.cos(phi0) * math.sin(phi) - math.sin(phi0) * math.cos(phi) * math.cos(delta)
    )
    return x, y


def aeqd_inverse(x: float, y: float, lat0: float, lon0: float) -> tuple[float, float]:
    """Inversa da AEQD esférica congelada; retorna latitude/longitude."""
    x = _finite(x, "x_m")
    y = _finite(y, "y_m")
    phi0 = math.radians(_finite(lat0, "latitude_origem"))
    lam0 = math.radians(_finite(lon0, "longitude_origem"))
    rho = math.hypot(x, y)
    if rho <= 1e-12:
        return float(lat0), float(lon0)
    c = rho / EARTH_RADIUS_M
    sin_c, cos_c = math.sin(c), math.cos(c)
    phi = math.asin(cos_c * math.sin(phi0) + y * sin_c * math.cos(phi0) / rho)
    lam = lam0 + math.atan2(
        x * sin_c,
        rho * math.cos(phi0) * cos_c - y * math.sin(phi0) * sin_c,
    )
    lon = (math.degrees(lam) + 180.0) % 360.0 - 180.0
    return math.degrees(phi), lon


def classify_domain(
    x_m: float,
    y_m: float,
    radius_m: float = DOMAIN_RADIUS_M,
    tolerance_m: float = DOMAIN_TOLERANCE_M,
) -> dict[str, Any]:
    distance = math.hypot(_finite(x_m, "x_m"), _finite(y_m, "y_m"))
    radius = _finite(radius_m, "radius_m")
    tolerance = _finite(tolerance_m, "tolerance_m")
    if radius <= 0 or tolerance < 0:
        raise EvaluationContractError("Raio/tolerância de domínio inválidos")
    if distance > radius + tolerance:
        status = "EXTERIOR"
        classification = "EXTERIOR_DOMINIO"
    elif abs(distance - radius) <= tolerance:
        status = "BORDA"
        classification = "BORDA_DOMINIO"
    else:
        status = "INTERIOR"
        classification = "INTERIOR"
    return {
        "status": status,
        "classification": classification,
        "distance_from_source_m": round(distance, 9),
        "radius_m": radius,
        "boundary_tolerance_m": tolerance,
        "inside_evaluation_domain": status != "EXTERIOR",
        "eligible_for_spatial_evaluation": status != "EXTERIOR",
    }


def _angular_delta_deg(first: float, second: float) -> float:
    return abs((first - second + 180.0) % 360.0 - 180.0)


def match_sectors(
    x_m: float,
    y_m: float,
    sector_features: Sequence[Mapping[str, Any]],
    tolerance_m: float = DOMAIN_TOLERANCE_M,
) -> dict[str, Any]:
    """Associa todos os setores tocados; o primário usa o pior rank v1."""
    x = _finite(x_m, "x_m")
    y = _finite(y_m, "y_m")
    tolerance = _finite(tolerance_m, "tolerance_m")
    rho = math.hypot(x, y)
    azimuth = (math.degrees(math.atan2(x, y)) + 360.0) % 360.0
    if rho <= tolerance:
        angular_tolerance = 180.0
    else:
        angular_tolerance = math.degrees(math.asin(min(1.0, tolerance / rho)))

    matches: list[dict[str, Any]] = []
    for feature in sector_features:
        props = feature.get("properties", {})
        sector_id = str(props.get("sector_id") or feature.get("id") or "")
        inner = _finite(props.get("inner_radius_m"), f"{sector_id}.inner_radius_m")
        outer = _finite(props.get("outer_radius_m"), f"{sector_id}.outer_radius_m")
        center = _finite(props.get("azimuth_center_deg"), f"{sector_id}.azimuth_center_deg")
        rank = int(props.get("rank_base_within_buffer"))
        radial_match = inner - tolerance <= rho <= outer + tolerance
        delta = _angular_delta_deg(azimuth, center)
        directional_match = rho <= tolerance or delta <= 22.5 + angular_tolerance
        if not (radial_match and directional_match):
            continue
        radial_boundary = abs(rho - inner) <= tolerance or abs(rho - outer) <= tolerance
        angular_boundary_distance = 0.0 if rho <= tolerance else rho * abs(math.sin(math.radians(delta - 22.5)))
        angular_boundary = rho <= tolerance or angular_boundary_distance <= tolerance
        matches.append(
            {
                "sector_id": sector_id,
                "v1_rank": rank,
                "ring_id": str(props.get("ring_id")),
                "direction": str(props.get("direction")),
                "radial_boundary": radial_boundary,
                "angular_boundary": angular_boundary,
            }
        )

    matches.sort(key=lambda item: item["sector_id"])
    primary = None
    if matches:
        primary = sorted(matches, key=lambda item: (-int(item["v1_rank"]), item["sector_id"]))[0]
    boundary_case = len(matches) > 1 or any(
        item["radial_boundary"] or item["angular_boundary"] for item in matches
    )
    return {
        "method": "FROZEN_POLAR_LIMITS_IN_LOCAL_SPHERICAL_AEQD",
        "boundary_tolerance_m": tolerance,
        "distance_m": round(rho, 9),
        "azimuth_deg": round(azimuth, 9),
        "matched_sectors": matches,
        "matched_sector_ids": [item["sector_id"] for item in matches],
        "boundary_case": boundary_case,
        "classification": "BORDA_SETORIAL" if boundary_case else "SETOR_UNICO" if matches else "SEM_SETOR",
        "primary_sector_id_v1_worst": primary["sector_id"] if primary else None,
        "primary_v1_rank_worst": primary["v1_rank"] if primary else None,
        "conservative_v1_sector_id": primary["sector_id"] if primary else None,
        "conservative_v1_rank": primary["v1_rank"] if primary else None,
        "primary_tie_break": "WORST_RANK_THEN_SECTOR_ID_ASC",
    }


def nearest_grid_cell(
    x_m: float,
    y_m: float,
    grid_rows: Sequence[Mapping[str, Any]],
    max_distance_m: float = GRID_MAX_SNAP_M,
) -> dict[str, Any]:
    """Seleciona por (distância², row, col); rejeita além da meia diagonal."""
    if not grid_rows:
        raise EvaluationContractError("Grade congelada vazia")
    x = _finite(x_m, "x_m")
    y = _finite(y_m, "y_m")
    maximum = _finite(max_distance_m, "max_distance_m")
    candidates: list[tuple[float, int, int, str, Mapping[str, Any]]] = []
    for row in grid_rows:
        rx = _finite(row.get("x_m"), "grade.x_m")
        ry = _finite(row.get("y_m"), "grade.y_m")
        d2 = (x - rx) ** 2 + (y - ry) ** 2
        grid_row = int(row.get("row", 0))
        grid_col = int(row.get("col", 0))
        candidates.append((d2, grid_row, grid_col, str(row.get("cell_id", "")), row))
    d2, grid_row, grid_col, _cell_id, selected = min(
        candidates, key=lambda item: (item[0], item[1], item[2], item[3])
    )
    distance = math.sqrt(d2)
    accepted = distance <= maximum + NUMERIC_EPSILON_M
    return {
        "status": "CELULA_ASSOCIADA" if accepted else "SEM_CELULA_NO_SUPORTE_DISCRETO",
        "cell": selected if accepted else None,
        "cell_id": str(selected["cell_id"]) if accepted else None,
        "row": grid_row if accepted else None,
        "col": grid_col if accepted else None,
        "snap_distance_m": round(distance, 9),
        "max_snap_distance_m": maximum,
        "tie_break": "MIN_DISTANCE_SQUARED_THEN_ROW_THEN_COL",
    }


def inclusive_ecdf_percentile(value: float, population: Iterable[float]) -> float:
    """100*N(x<=valor)/N, com valores finitos; menor percentil é melhor."""
    target = _finite(value, "ecdf_value")
    values = [_finite(item, "ecdf_population") for item in population]
    if not values:
        raise EvaluationContractError("População ECDF vazia")
    return 100.0 * sum(item <= target for item in values) / len(values)


def cost_band(value: float | None) -> str:
    if value is None:
        return "NAO_DISPONIVEL"
    try:
        cost = float(value)
    except (TypeError, ValueError):
        return "NAO_DISPONIVEL"
    if not math.isfinite(cost):
        return "NAO_DISPONIVEL"
    if cost < 0:
        raise EvaluationContractError("Custo acumulado não pode ser negativo")
    if cost <= 500.0:
        return "B1_ATE_UM_TERCO"
    if cost <= 1000.0:
        return "B2_ENTRE_UM_E_DOIS_TERCOS"
    if cost <= 1500.0:
        return "B3_ENTRE_DOIS_TERCOS_E_ORCAMENTO"
    return "B4_ACIMA_DO_ORCAMENTO"


def point_segment_distance_m(
    point_xy: tuple[float, float],
    start_xy: tuple[float, float],
    end_xy: tuple[float, float],
) -> float:
    px, py = point_xy
    ax, ay = start_xy
    bx, by = end_xy
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def minimum_distance_to_linestring_m(
    point_xy: tuple[float, float], line_xy: Sequence[tuple[float, float]]
) -> float:
    if not line_xy:
        raise EvaluationContractError("LineString vazio")
    if len(line_xy) == 1:
        return math.hypot(point_xy[0] - line_xy[0][0], point_xy[1] - line_xy[0][1])
    return min(point_segment_distance_m(point_xy, a, b) for a, b in zip(line_xy, line_xy[1:]))


def _corridor_id(feature: Mapping[str, Any]) -> str:
    props = feature.get("properties", {})
    return str(
        feature.get("id")
        or f"{props.get('sector_id', 'SEM_SETOR')}::{props.get('cost_scenario_id', 'SEM_CENARIO')}"
    )


def validate_reference(
    reference: Mapping[str, Any], *, require_frozen_record: bool = False
) -> dict[str, Any]:
    """Valida o registro T5; o formato plano é aceito só pela API de testes.

    A execução de linha de comando exige o registro estruturado definido em
    ``schema_referencia_t5_v1.json``. O formato plano mantém a API unitária
    simples, mas não é aceito para publicação.
    """
    if reference.get("scenario_id") != SCENARIO_ID:
        raise EvaluationContractError("scenario_id da referência deve ser RURAL-01")

    structured = "position" in reference
    if require_frozen_record and not structured:
        raise EvaluationContractError("Publicação exige registro T5 estruturado com position/source/opening")

    if structured:
        required = {
            "schema_version", "record_id", "scenario_id", "stage", "status",
            "reference_received", "reference_role", "verification_status",
            "position", "source", "opening", "missing_fields", "notes",
        }
        _require_exact_keys(
            reference,
            required=required,
            allowed=required | {"$schema"},
            field="Registro T5",
        )
        if reference.get("schema_version") != "1.0" or reference.get("stage") != "T5_REFERENCE_OPENING":
            raise EvaluationContractError("Versão/etapa do registro T5 inválida")
        if not isinstance(reference.get("record_id"), str) or not str(reference["record_id"]).strip():
            raise EvaluationContractError("record_id deve ser texto não vazio")
        if reference.get("status") != "REVELADO_CONGELADO" or reference.get("reference_received") is not True:
            raise EvaluationContractError("Registro T5 ainda não está REVELADO_CONGELADO")
        allowed_roles = {"POSICAO_DECLARADA_ALVO_SIMULADO", "REFERENCIA_CAMPO_COM_PROVENIENCIA"}
        if reference.get("reference_role") not in allowed_roles:
            raise EvaluationContractError("reference_role não permitido pelo protocolo")
        allowed_verification = {
            "DECLARADA_NAO_AFERIDA_INDEPENDENTEMENTE", "CAMPO_COM_PROVENIENCIA", "NAO_DISPONIVEL"
        }
        if reference.get("verification_status") not in allowed_verification:
            raise EvaluationContractError("verification_status não permitido pelo protocolo")
        position = reference.get("position")
        source = reference.get("source")
        opening = reference.get("opening")
        if not isinstance(position, Mapping) or not isinstance(source, Mapping) or not isinstance(opening, Mapping):
            raise EvaluationContractError("position/source/opening devem ser objetos")
        position_keys = {"latitude", "longitude", "crs", "coordinate_order"}
        source_keys = {
            "collection_method", "equipment", "horizontal_accuracy_m",
            "position_observed_at", "source_artifact", "source_artifact_sha256",
            "provenance_note",
        }
        opening_keys = {
            "opened_at", "opened_by", "opening_method", "evaluator_freeze_manifest_sha256"
        }
        _require_exact_keys(position, required=position_keys, allowed=position_keys, field="position")
        _require_exact_keys(source, required=source_keys, allowed=source_keys, field="source")
        _require_exact_keys(opening, required=opening_keys, allowed=opening_keys, field="opening")
        if position.get("crs") != "EPSG:4326" or position.get("coordinate_order") != "LONGITUDE_LATITUDE":
            raise EvaluationContractError("CRS ou ordem de coordenadas divergente")
        _parse_aware_datetime(opening.get("opened_at"), "opening.opened_at")
        for key in ("opened_by", "opening_method"):
            if not isinstance(opening.get(key), str) or not str(opening[key]).strip():
                raise EvaluationContractError(f"opening.{key} deve ser texto não vazio")
        freeze_sha = str(opening["evaluator_freeze_manifest_sha256"])
        if len(freeze_sha) != 64 or any(char not in "0123456789abcdef" for char in freeze_sha.casefold()):
            raise EvaluationContractError("opening.evaluator_freeze_manifest_sha256 inválido")
        for key in ("collection_method", "equipment", "source_artifact"):
            value = source.get(key)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise EvaluationContractError(f"source.{key} deve ser texto não vazio ou null")
        observed = source.get("position_observed_at")
        if observed is not None:
            _parse_aware_datetime(observed, "source.position_observed_at")
        artifact_sha = source.get("source_artifact_sha256")
        if artifact_sha is not None and (
            not isinstance(artifact_sha, str)
            or len(artifact_sha) != 64
            or any(char not in "0123456789abcdef" for char in artifact_sha.casefold())
        ):
            raise EvaluationContractError("source.source_artifact_sha256 inválido")
        if not isinstance(source.get("provenance_note"), str) or not source["provenance_note"].strip():
            raise EvaluationContractError("source.provenance_note deve ser texto não vazio")
        missing_fields = reference.get("missing_fields")
        if (
            not isinstance(missing_fields, list)
            or any(not isinstance(item, str) for item in missing_fields)
            or len(missing_fields) != len(set(missing_fields))
        ):
            raise EvaluationContractError("missing_fields deve ser lista sem duplicatas")
        allowed_missing = {
            "position", "reference_role", "verification_status", "collection_method", "equipment",
            "horizontal_accuracy_m", "position_observed_at", "source_artifact",
            "source_artifact_sha256", "opened_at", "opened_by", "opening_method",
            "evaluator_freeze_manifest_sha256",
        }
        if any(item not in allowed_missing for item in missing_fields):
            raise EvaluationContractError("missing_fields contém identificador não permitido")
        if not isinstance(reference.get("notes"), str):
            raise EvaluationContractError("notes deve ser texto")
        latitude_value = position.get("latitude")
        longitude_value = position.get("longitude")
        reference_id = str(reference.get("record_id"))
        horizontal_accuracy = source.get("horizontal_accuracy_m")
        observed_at = source.get("position_observed_at")
        revealed_at = opening.get("opened_at")
        collection_method = source.get("collection_method")
        equipment = source.get("equipment")
        source_note = source.get("provenance_note")
        role = reference.get("reference_role")
        verification = reference.get("verification_status")
        opening_record = dict(opening)
        source_record = dict(source)
    else:
        required = {"scenario_id", "latitude", "longitude"}
        missing = sorted(required - set(reference))
        if missing:
            raise EvaluationContractError(f"Referência sem campos obrigatórios: {', '.join(missing)}")
        latitude_value = reference.get("latitude")
        longitude_value = reference.get("longitude")
        reference_id = str(reference.get("reference_id") or "NAO_DISPONIVEL")
        horizontal_accuracy = reference.get("horizontal_accuracy_m")
        observed_at = reference.get("observed_at")
        revealed_at = reference.get("opened_at_local")
        collection_method = reference.get("collection_method")
        equipment = reference.get("equipment")
        source_note = reference.get("source_note") or reference.get("provenance")
        role = reference.get("reference_role")
        verification = reference.get("verification_status")
        opening_record = None
        source_record = None

    latitude = _finite(latitude_value, "latitude")
    longitude = _finite(longitude_value, "longitude")
    if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
        raise EvaluationContractError("Coordenada da referência fora do domínio geográfico")
    if horizontal_accuracy is not None:
        horizontal_accuracy = _finite(horizontal_accuracy, "horizontal_accuracy_m")
        if horizontal_accuracy < 0:
            raise EvaluationContractError("horizontal_accuracy_m não pode ser negativa")
    normalized = {
        "scenario_id": SCENARIO_ID,
        "reference_id": reference_id,
        "latitude": latitude,
        "longitude": longitude,
        "latitude_text_as_received": str(latitude_value),
        "longitude_text_as_received": str(longitude_value),
        "reference_role": role,
        "verification_status": verification,
        "horizontal_accuracy_m": horizontal_accuracy,
        "observed_at": observed_at,
        "revealed_at_local": revealed_at,
        "collection_method": collection_method,
        "equipment": equipment,
        "source_note": source_note,
        "source_record": source_record,
        "opening_record": opening_record,
        "input_contract": "STRUCTURED_T5_SCHEMA" if structured else "FLAT_TEST_API",
    }
    normalized["normalized_reference_sha256"] = canonical_hash(normalized)
    return normalized


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_frozen_data() -> dict[str, Any]:
    grid = _read_csv(GRID_PATH)
    summaries = _read_csv(SECTOR_SUMMARY_PATH)
    sectors_doc = load_json(V1_SECTORS_PATH)
    corridors_doc = load_json(CORRIDOR_PATH)
    top3_doc = load_json(V1_TOP3_PATH)
    mov_result = load_json(MOV_RESULT_PATH)
    if len(grid) != 7845:
        raise EvaluationContractError(f"Grade congelada inesperada: {len(grid)} células")
    if len(sectors_doc.get("features", [])) != 24:
        raise EvaluationContractError("Pacote v1 não contém 24 setores")
    if len(corridors_doc.get("features", [])) != 48:
        raise EvaluationContractError("Pacote MOV-V não contém 48 corredores BASE")
    return {
        "grid": grid,
        "sector_summaries": summaries,
        "sector_features": sectors_doc["features"],
        "corridor_features": corridors_doc["features"],
        "v1_top3": top3_doc["areas"],
        "mov_result": mov_result,
    }


def _scenario_class(scenario_id: str) -> str:
    if scenario_id in PRIMARY_BASE_SCENARIOS:
        return "BASE_COPRIMARIA"
    if scenario_id in SENSITIVITY_SCENARIOS:
        return "SENSIBILIDADE"
    if scenario_id in ABLATION_SCENARIOS:
        return "ABLACAO_SECUNDARIA"
    if scenario_id in COUNTERFACTUAL_SCENARIOS:
        return "CONTRAFACTUAL_SECUNDARIO"
    raise EvaluationContractError(f"Cenário de custo não pré-especificado: {scenario_id}")


def _cost_scenario_ids(grid_rows: Sequence[Mapping[str, Any]]) -> list[str]:
    if not grid_rows:
        return []
    result = sorted(key.removeprefix("cost__") for key in grid_rows[0] if key.startswith("cost__"))
    expected = set(SENSITIVITY_SCENARIOS) | set(ABLATION_SCENARIOS) | set(COUNTERFACTUAL_SCENARIOS)
    if set(result) != expected:
        raise EvaluationContractError(
            f"Cenários na grade divergem do contrato: esperado {sorted(expected)}, obtido {result}"
        )
    return result


def _summary_lookup(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], Mapping[str, Any]]:
    lookup: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in rows:
        key = (str(row["cost_scenario_id"]), str(row["sector_id"]))
        if key in lookup:
            raise EvaluationContractError(f"Resumo setorial duplicado: {key}")
        lookup[key] = row
    return lookup


def _band_area_rows(scenario_id: str, costs: Sequence[float]) -> list[dict[str, Any]]:
    counts = {band: 0 for band in (
        "B1_ATE_UM_TERCO",
        "B2_ENTRE_UM_E_DOIS_TERCOS",
        "B3_ENTRE_DOIS_TERCOS_E_ORCAMENTO",
        "B4_ACIMA_DO_ORCAMENTO",
    )}
    for value in costs:
        counts[cost_band(value)] += 1
    circle_area = math.pi * DOMAIN_RADIUS_M**2
    valid_grid_area = len(costs) * GRID_RESOLUTION_M**2
    return [
        {
            "cost_scenario_id": scenario_id,
            "scenario_class": _scenario_class(scenario_id),
            "cost_band": band,
            "cell_count": count,
            "approximate_area_m2_center_mask": round(count * GRID_RESOLUTION_M**2, 3),
            "fraction_of_valid_grid_cells": round(count / len(costs), 9),
            "fraction_of_1500m_analytical_circle_approx": round(
                count * GRID_RESOLUTION_M**2 / circle_area, 9
            ),
            "valid_grid_approximate_area_m2": round(valid_grid_area, 3),
            "analytical_circle_area_m2": round(circle_area, 3),
            "area_method": "CELL_CENTER_MASK_COUNT_TIMES_900_M2_APPROXIMATION",
        }
        for band, count in counts.items()
    ]


def _scenario_metrics(
    grid_rows: Sequence[Mapping[str, Any]],
    summary_rows: Sequence[Mapping[str, Any]],
    matched_sector_ids: Sequence[str],
    snapped_cell: Mapping[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    lookup = _summary_lookup(summary_rows)
    scenario_rows: list[dict[str, Any]] = []
    area_rows: list[dict[str, Any]] = []
    for scenario_id in _cost_scenario_ids(grid_rows):
        cost_key = f"cost__{scenario_id}"
        costs = [_finite(row[cost_key], cost_key) for row in grid_rows]
        area_rows.extend(_band_area_rows(scenario_id, costs))
        sector_rank_rows: list[dict[str, Any]] = []
        for sector_id in matched_sector_ids:
            frozen = lookup.get((scenario_id, sector_id))
            if frozen is None:
                raise EvaluationContractError(f"Resumo ausente: {(scenario_id, sector_id)}")
            sector_rank_rows.append(
                {
                    "sector_id": sector_id,
                    "mobility_rank": int(frozen["mobility_rank_within_buffer"]),
                    "accessibility_index": _finite(frozen["accessibility_index"], "accessibility_index"),
                    "reachable_fraction": _finite(frozen["reachable_fraction"], "reachable_fraction"),
                }
            )
        sector_rank_rows.sort(key=lambda item: item["sector_id"])
        primary_sector = None
        if sector_rank_rows:
            primary_sector = sorted(
                sector_rank_rows, key=lambda item: (-int(item["mobility_rank"]), item["sector_id"])
            )[0]
        value = _finite(snapped_cell[cost_key], cost_key) if snapped_cell is not None else None
        percentile = inclusive_ecdf_percentile(value, costs) if value is not None else None
        scenario_rows.append(
            {
                "cost_scenario_id": scenario_id,
                "scenario_class": _scenario_class(scenario_id),
                "hypothesis_id": (
                    "H_REDE_DISPONIVEL"
                    if scenario_id.startswith("H_REDE_DISPONIVEL") or scenario_id.startswith("ABL__") or scenario_id.startswith("SENS__")
                    else "H_FORA_REDE"
                ),
                "sensitivity_profile": (
                    scenario_id.split("__", 1)[1]
                    if scenario_id.startswith("H_")
                    else "ABLATION" if scenario_id.startswith("ABL__") else "CONTRAFACTUAL_NAO_PROMOVIDO"
                ),
                "cell_id": str(snapped_cell["cell_id"]) if snapped_cell is not None else None,
                "accumulated_cost_m_equivalent": round(value, 6) if value is not None else None,
                "cost_m_equivalent": round(value, 6) if value is not None else None,
                "inclusive_ecdf_percentile": round(percentile, 9) if percentile is not None else None,
                "percentile_direction": "LOWER_IS_BETTER",
                "cost_band": cost_band(value),
                "within_1500_cost_budget": value <= 1500.0 if value is not None else None,
                "matched_sector_ranks": sector_rank_rows,
                "primary_sector_id_worst_rank": primary_sector["sector_id"] if primary_sector else None,
                "primary_sector_rank_worst": primary_sector["mobility_rank"] if primary_sector else None,
                "any_matched_sector_rank_le_3": (
                    any(int(item["mobility_rank"]) <= 3 for item in sector_rank_rows)
                    if sector_rank_rows else None
                ),
                "all_matched_sectors_rank_le_3": (
                    all(int(item["mobility_rank"]) <= 3 for item in sector_rank_rows)
                    if sector_rank_rows else None
                ),
                "rank_interpretation": "RELATIVE_MOVEMENT_ACCESS_NOT_LOCATION_PROBABILITY",
            }
        )
    scenario_rows.sort(key=lambda item: item["cost_scenario_id"])
    area_rows.sort(key=lambda item: (item["cost_scenario_id"], item["cost_band"]))
    return scenario_rows, area_rows


def _sensitivity_summary(scenario_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(row["cost_scenario_id"]): row for row in scenario_rows}
    summaries: list[dict[str, Any]] = []
    for hypothesis in ("H_REDE_DISPONIVEL", "H_FORA_REDE"):
        ids = [f"{hypothesis}__{profile}" for profile in ("SUAVE", "BASE", "FORTE")]
        rows = [by_id[item] for item in ids]
        reachable = [row["within_1500_cost_budget"] for row in rows]
        top3 = [row["all_matched_sectors_rank_le_3"] for row in rows]
        ranks = [row["primary_sector_rank_worst"] for row in rows]
        summaries.append(
            {
                "hypothesis_id": hypothesis,
                "cost_scenario_ids": ids,
                "profiles": ["SUAVE", "BASE", "FORTE"],
                "within_budget_values": reachable,
                "within_budget_stable": len(set(reachable)) == 1 if None not in reachable else None,
                "all_matched_top3_values": top3,
                "all_matched_top3_stable": len(set(top3)) == 1 if None not in top3 else None,
                "primary_worst_ranks": ranks,
                "primary_rank_span": max(ranks) - min(ranks) if None not in ranks else None,
                "interpretation": "SENSITIVITY_DIAGNOSTIC_NOT_CALIBRATION",
            }
        )
    return summaries


def _result_taxonomy(
    domain: Mapping[str, Any],
    snap: Mapping[str, Any],
    scenario_rows: Sequence[Mapping[str, Any]],
    sensitivity_rows: Sequence[Mapping[str, Any]],
    corridor_rows: Sequence[Mapping[str, Any]],
    integrity: Mapping[str, Any],
) -> dict[str, Any]:
    """Classifica dimensões separadas sem produzir um veredito empírico global."""
    if domain["status"] == "INTERIOR":
        domain_state = "DENTRO_DOMINIO"
    elif domain["status"] == "BORDA":
        domain_state = "BORDA_DOMINIO"
    else:
        domain_state = "FORA_ESCOPO_DOMINIO"

    grid_state = (
        "CELULA_ASSOCIADA"
        if snap.get("cell_id") is not None
        else "SEM_CELULA_NO_SUPORTE_DISCRETO"
    )
    per_scenario: dict[str, dict[str, str]] = {}
    for row in scenario_rows:
        if row["within_1500_cost_budget"] is None:
            budget_state = "NAO_AVALIAVEL_CUSTO"
        else:
            budget_state = (
                "DENTRO_ORCAMENTO"
                if row["within_1500_cost_budget"]
                else "NEGATIVO_ALCANCABILIDADE_ACIMA_ORCAMENTO"
            )
        if row["primary_sector_rank_worst"] is None:
            ranking_state = "NAO_AVALIAVEL_SETOR"
        else:
            ranking_state = (
                "SETOR_TOP3"
                if int(row["primary_sector_rank_worst"]) <= 3
                else "NEGATIVO_PRIORIZACAO_FORA_TOP3"
            )
        per_scenario[str(row["cost_scenario_id"])] = {
            "budget": budget_state,
            "ranking": ranking_state,
        }

    corridor_by_hypothesis: dict[str, str] = {}
    for hypothesis in ("H_REDE_DISPONIVEL", "H_FORA_REDE"):
        primary_nearest = [
            row for row in corridor_rows
            if row["hypothesis_id"] == hypothesis
            and row["scope"] == "PRIMARY_MOV_V_TOP3"
            and row["is_nearest_in_scope"]
        ]
        if not primary_nearest:
            corridor_state = "NAO_AVALIAVEL_CORREDOR"
        else:
            corridor_state = (
                "DENTRO_SUPORTE_DISCRETO_TOP3_MOVV"
                if primary_nearest[0]["nearest_within_discrete_grid_support"]
                else "NEGATIVO_CORREDOR_TOP3_MOVV_FORA_SUPORTE"
            )
        corridor_by_hypothesis[hypothesis] = corridor_state

    sensitivity_by_hypothesis: dict[str, str] = {}
    for row in sensitivity_rows:
        if row["within_budget_stable"] is None or row["all_matched_top3_stable"] is None:
            state = "NAO_AVALIAVEL_SENSIBILIDADE"
        elif row["within_budget_stable"] and row["all_matched_top3_stable"]:
            state = "ESTAVEL_NO_CRITERIO"
        else:
            state = "NEGATIVO_ROBUSTEZ_INSTAVEL"
        sensitivity_by_hypothesis[str(row["hypothesis_id"])] = state

    base_signatures: list[tuple[str, str, str] | None] = []
    for scenario_id in PRIMARY_BASE_SCENARIOS:
        hypothesis = scenario_id.removesuffix("__BASE")
        states = per_scenario.get(scenario_id)
        if states is None or corridor_by_hypothesis.get(hypothesis) == "NAO_AVALIAVEL_CORREDOR":
            base_signatures.append(None)
        else:
            base_signatures.append(
                (states["budget"], states["ranking"], corridor_by_hypothesis[hypothesis])
            )
    if any(item is None for item in base_signatures):
        hypotheses_state = "NAO_AVALIAVEL_HIPOTESES"
    elif base_signatures[0] == base_signatures[1]:
        hypotheses_state = "CONCORDANTES_NO_CRITERIO"
    else:
        hypotheses_state = "DIVERGENTES_ENTRE_HIPOTESES"

    integrity_state = (
        "INSUMOS_VERIFICADOS"
        if all(
            item.get("technical_status") == "PASS"
            for item in integrity.values()
        )
        else "NAO_AVALIAVEL_INTEGRIDADE"
    )
    return {
        "global_empirical_verdict": None,
        "global_empirical_pass_fail_forbidden": True,
        "cross_dimension_aggregate_score": None,
        "domain": domain_state,
        "grid": grid_state,
        "per_cost_scenario": per_scenario,
        "corridor_by_hypothesis": corridor_by_hypothesis,
        "sensitivity_by_hypothesis": sensitivity_by_hypothesis,
        "hypotheses": hypotheses_state,
        "integrity": integrity_state,
        "negative_results_preserved": True,
    }


def _corridor_distance_rows(
    point_xy: tuple[float, float],
    corridor_features: Sequence[Mapping[str, Any]],
    summary_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    lookup = _summary_lookup(summary_rows)
    rows: list[dict[str, Any]] = []
    for scenario_id in PRIMARY_BASE_SCENARIOS:
        hypothesis = scenario_id.removesuffix("__BASE")
        candidates: list[dict[str, Any]] = []
        for feature in corridor_features:
            props = feature.get("properties", {})
            if props.get("cost_scenario_id") != scenario_id:
                continue
            sector_id = str(props["sector_id"])
            summary = lookup[(scenario_id, sector_id)]
            mobility_rank = int(summary["mobility_rank_within_buffer"])
            coords = feature.get("geometry", {}).get("coordinates", [])
            line_xy = [
                aeqd_forward(float(lat), float(lon), SOURCE_LAT, SOURCE_LON)
                for lon, lat in coords
            ]
            distance = minimum_distance_to_linestring_m(point_xy, line_xy)
            candidates.append(
                {
                    "corridor_id": _corridor_id(feature),
                    "sector_id": sector_id,
                    "hypothesis_id": hypothesis,
                    "cost_scenario_id": scenario_id,
                    "mobility_rank": mobility_rank,
                    "v1_top3_member": props.get("v1_top3_member") is True,
                    "distance_m": distance,
                }
            )
        if len(candidates) != 24:
            raise EvaluationContractError(f"Esperados 24 corredores em {scenario_id}; obtidos {len(candidates)}")
        scoped = (
            ("PRIMARY_MOV_V_TOP3", [item for item in candidates if item["mobility_rank"] <= 3], True),
            ("SECONDARY_V1_TOP3", [item for item in candidates if item["v1_top3_member"]], True),
            ("DIAGNOSTIC_ANY_24", candidates, False),
        )
        for scope, eligible, emit_each in scoped:
            if not eligible:
                raise EvaluationContractError(f"Conjunto de corredores vazio: {scenario_id}/{scope}")
            ordered = sorted(
                eligible,
                key=lambda item: (item["distance_m"], item["sector_id"], item["corridor_id"]),
            )
            nearest = ordered[0]
            emitted = sorted(eligible, key=lambda item: (item["sector_id"], item["corridor_id"])) if emit_each else [nearest]
            for item in emitted:
                rows.append(
                    {
                        **{key: value for key, value in item.items() if key != "distance_m"},
                        "scope": scope,
                        "eligible_corridor_count": len(eligible),
                        "distance_m": round(float(item["distance_m"]), 9),
                        "is_nearest_in_scope": item["corridor_id"] == nearest["corridor_id"],
                        "nearest_corridor_id_in_scope": nearest["corridor_id"],
                        "nearest_distance_m_in_scope": round(float(nearest["distance_m"]), 9),
                        "within_discrete_grid_support": (
                            item["distance_m"] <= GRID_MAX_SNAP_M + COMPARISON_EPSILON_M
                        ),
                        "nearest_within_discrete_grid_support": (
                            nearest["distance_m"] <= GRID_MAX_SNAP_M + COMPARISON_EPSILON_M
                        ),
                        "discrete_support_threshold_m": GRID_MAX_SNAP_M,
                        "comparison_epsilon_m": COMPARISON_EPSILON_M,
                        "support_semantics": "HALF_CELL_DIAGONAL_NOT_PHYSICAL_CORRIDOR_WIDTH",
                    }
                )
    rows.sort(
        key=lambda item: (
            item["hypothesis_id"],
            item["scope"],
            item["sector_id"],
            item["corridor_id"],
        )
    )
    return rows


def _v1_metrics(match: Mapping[str, Any], v1_top3: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    matches = list(match["matched_sectors"])
    top_ids = {str(item["sector_id"]) for item in v1_top3}
    ranks = [{"sector_id": item["sector_id"], "v1_rank": int(item["v1_rank"])} for item in matches]
    worst = None
    if ranks:
        worst = sorted(ranks, key=lambda item: (-item["v1_rank"], item["sector_id"]))[0]
    return {
        "matched_sector_ranks": ranks,
        "primary_sector_id_worst_rank": worst["sector_id"] if worst else None,
        "primary_sector_rank_worst": worst["v1_rank"] if worst else None,
        "any_matched_sector_in_frozen_top3": any(item["sector_id"] in top_ids for item in ranks) if ranks else None,
        "all_matched_sectors_in_frozen_top3": all(item["sector_id"] in top_ids for item in ranks) if ranks else None,
        "frozen_top3_sector_ids": sorted(top_ids),
        "ranking_semantics": "TERRITORIAL_ANALYTICAL_PRIORITY_NOT_LOCATION_PROBABILITY",
    }


def build_evaluation(
    reference: Mapping[str, Any],
    *,
    frozen_data: Mapping[str, Any] | None = None,
    integrity_receipts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Constrói a avaliação sem alterar ou recalcular qualquer artefato T0--T4."""
    normalized = validate_reference(reference)
    receipts = dict(integrity_receipts or {
        "t4_ledger": verify_t4_ledger(),
        "v1_manifest": verify_v1_manifest(),
    })
    frozen = dict(frozen_data or load_frozen_data())
    x_m, y_m = aeqd_forward(
        normalized["latitude"], normalized["longitude"], SOURCE_LAT, SOURCE_LON
    )
    domain = classify_domain(x_m, y_m)

    if domain["status"] == "EXTERIOR":
        sector_match = {
            "method": "NOT_APPLIED_OUTSIDE_DOMAIN",
            "boundary_tolerance_m": DOMAIN_TOLERANCE_M,
            "distance_m": domain["distance_from_source_m"],
            "azimuth_deg": round((math.degrees(math.atan2(x_m, y_m)) + 360.0) % 360.0, 9),
            "matched_sectors": [],
            "matched_sector_ids": [],
            "boundary_case": False,
            "classification": "SEM_SETOR",
            "primary_sector_id_v1_worst": None,
            "primary_v1_rank_worst": None,
            "conservative_v1_sector_id": None,
            "conservative_v1_rank": None,
            "primary_tie_break": "WORST_RANK_THEN_SECTOR_ID_ASC",
        }
        snap = {
            "status": "NOT_APPLIED_OUTSIDE_DOMAIN",
            "cell": None,
            "cell_id": None,
            "row": None,
            "col": None,
            "snap_distance_m": None,
            "max_snap_distance_m": GRID_MAX_SNAP_M,
            "tie_break": "MIN_DISTANCE_SQUARED_THEN_ROW_THEN_COL",
        }
    else:
        sector_match = match_sectors(x_m, y_m, frozen["sector_features"])
        if not sector_match["matched_sector_ids"]:
            raise EvaluationContractError("Ponto no domínio sem associação a setor congelado")
        snap = nearest_grid_cell(x_m, y_m, frozen["grid"])

    snapped_cell = snap["cell"]
    scenario_rows, area_rows = _scenario_metrics(
        frozen["grid"],
        frozen["sector_summaries"],
        sector_match["matched_sector_ids"],
        snapped_cell,
    )
    corridor_rows = (
        _corridor_distance_rows((x_m, y_m), frozen["corridor_features"], frozen["sector_summaries"])
        if domain["status"] != "EXTERIOR"
        else []
    )
    v1 = _v1_metrics(sector_match, frozen["v1_top3"])
    by_scenario = {row["cost_scenario_id"]: row for row in scenario_rows}
    base_comparison = []
    for scenario_id in PRIMARY_BASE_SCENARIOS:
        item = by_scenario[scenario_id]
        base_comparison.append(
            {
                "cost_scenario_id": scenario_id,
                "hypothesis_id": item["hypothesis_id"],
                "v1_primary_worst_rank": v1["primary_sector_rank_worst"],
                "mov_v_primary_worst_rank": item["primary_sector_rank_worst"],
                "mov_v_minus_v1_rank": (
                    item["primary_sector_rank_worst"] - v1["primary_sector_rank_worst"]
                    if item["primary_sector_rank_worst"] is not None
                    and v1["primary_sector_rank_worst"] is not None
                    else None
                ),
                "interpretation": "DESCRIPTIVE_RANK_COMPARISON_NO_ACCURACY_AGGREGATION",
            }
        )

    ablations = [by_scenario[item] for item in ABLATION_SCENARIOS]
    counterfactuals = [by_scenario[item] for item in COUNTERFACTUAL_SCENARIOS]
    sensitivity_summary = _sensitivity_summary(scenario_rows)
    taxonomy = _result_taxonomy(
        domain,
        snap,
        scenario_rows,
        sensitivity_summary,
        corridor_rows,
        receipts,
    )
    grid_cell_summary = None
    if snapped_cell is not None:
        grid_cell_summary = {
            key: snapped_cell.get(key)
            for key in ("cell_id", "row", "col", "x_m", "y_m", "lat", "lon", "sector_id")
        }
    grid_public = {key: value for key, value in snap.items() if key != "cell"}
    sensitivity_rows = [by_scenario[item] for item in SENSITIVITY_SCENARIOS]
    six_scenario_summary = {
        "evaluated_scenario_count": len(sensitivity_rows),
        "count_within_budget_0_to_6": sum(
            row["within_1500_cost_budget"] is True for row in sensitivity_rows
        ),
        "count_top3_0_to_6": sum(
            row["primary_sector_rank_worst"] is not None
            and int(row["primary_sector_rank_worst"]) <= 3
            for row in sensitivity_rows
        ),
        "missing_budget_count": sum(
            row["within_1500_cost_budget"] is None for row in sensitivity_rows
        ),
        "missing_ranking_count": sum(
            row["primary_sector_rank_worst"] is None for row in sensitivity_rows
        ),
        "mean_cost_across_scenarios": None,
        "retrospective_profile_selected": False,
    }
    result = {
        "protocol_id": PROTOCOL_ID,
        "scenario_id": SCENARIO_ID,
        "phase": "T5_REFERENCE_OPENING_AND_T6_PRESPECIFIED_EVALUATION",
        "evaluation_version": "1.0",
        "reference": normalized,
        "source_point": {"latitude": SOURCE_LAT, "longitude": SOURCE_LON, "crs": "EPSG:4326"},
        "analysis_crs": (
            "+proj=aeqd +lat_0=0.188611 +lon_0=-51.155556 "
            "+R=6371008.8 +units=m +no_defs"
        ),
        "reference_projected": {"x_m": round(x_m, 9), "y_m": round(y_m, 9)},
        "domain": domain,
        "sector_assignment": sector_match,
        "sector_association": sector_match,
        "grid_assignment": grid_public,
        "grid_association": {**grid_public, "cell": grid_cell_summary},
        "v1_frozen_ranking": v1,
        "scenario_metrics": scenario_rows,
        "scenario_metrics_by_id": by_scenario,
        "primary_base_hypotheses": {
            scenario_id: by_scenario[scenario_id] for scenario_id in PRIMARY_BASE_SCENARIOS
        },
        "sensitivity_results": {
            scenario_id: by_scenario[scenario_id] for scenario_id in SENSITIVITY_SCENARIOS
        },
        "cost_band_areas": area_rows,
        "base_coprimary_comparison": base_comparison,
        "sensitivity_stability": sensitivity_summary,
        "six_scenario_sensitivity_summary": six_scenario_summary,
        "ablation_metrics_secondary": ablations,
        "ablation_results": {
            scenario_id: by_scenario[scenario_id] for scenario_id in ABLATION_SCENARIOS
        },
        "counterfactual_metrics_secondary": counterfactuals,
        "corridor_metrics": corridor_rows,
        "integrity": receipts,
        "result_taxonomy": taxonomy,
        "profile_v3": {
            "role": "OPTIONAL_COMPLEMENTARY_CONTEXT",
            "status": "ABSTENCAO_PERFIL",
            "reason": "PERFIL_V3_NAO_FORNECIDO_AO_AVALIADOR_T6",
            "modified_frozen_territorial_results": False,
            "compensates_spatial_result": False,
            "defines_reference_sector": False,
        },
        "hypothesis_selection_status": "NENHUMA_HIPOTESE_SELECIONADA",
        "method_guardrails": {
            "rankings_recomputed": False,
            "cost_surfaces_recomputed": False,
            "sectors_recomputed": False,
            "corridors_recomputed": False,
            "hypotheses_collapsed": False,
            "aggregate_hit_or_error_label_created": False,
            "output_is_probability": False,
            "operational_command": False,
            "retuning_after_reference_opening": False,
        },
        "interpretation": (
            "Métricas descritivas de um caso pós-abertura contra artefatos congelados. "
            "Não constituem probabilidade de presença, rota observada, eficácia geral ou comando operacional."
        ),
    }
    return result


def build_geojson(result: Mapping[str, Any], frozen_data: Mapping[str, Any]) -> dict[str, Any]:
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "id": "RURAL-01::E0",
            "properties": {"role": "PONTO_INICIAL_PLANEJAMENTO", "label": "E0"},
            "geometry": {"type": "Point", "coordinates": [SOURCE_LON, SOURCE_LAT]},
        },
        {
            "type": "Feature",
            "id": "RURAL-01::REFERENCIA_T5",
            "properties": {
                "role": result["reference"]["reference_role"],
                "verification_status": result["reference"]["verification_status"],
                "domain_status": result["domain"]["status"],
            },
            "geometry": {
                "type": "Point",
                "coordinates": [result["reference"]["longitude"], result["reference"]["latitude"]],
            },
        },
    ]
    matched_ids = set(result["sector_assignment"]["matched_sector_ids"])
    for source in frozen_data["sector_features"]:
        sector_id = str(source.get("properties", {}).get("sector_id") or source.get("id"))
        if sector_id not in matched_ids:
            continue
        features.append(
            {
                "type": "Feature",
                "id": sector_id,
                "properties": {
                    "role": "SETOR_TOCADO_PELA_REFERENCIA",
                    "sector_id": sector_id,
                    "v1_rank": source["properties"]["rank_base_within_buffer"],
                    "primary_v1_worst": sector_id
                    == result["v1_frozen_ranking"]["primary_sector_id_worst_rank"],
                },
                "geometry": source["geometry"],
            }
        )
    if result["grid_assignment"]["cell_id"] is not None:
        cell_id = result["grid_assignment"]["cell_id"]
        row = next(item for item in frozen_data["grid"] if str(item["cell_id"]) == cell_id)
        features.append(
            {
                "type": "Feature",
                "id": f"RURAL-01::SNAP::{cell_id}",
                "properties": {
                    "role": "CENTRO_CELULA_ASSOCIADA",
                    "cell_id": cell_id,
                    "snap_distance_m": result["grid_assignment"]["snap_distance_m"],
                },
                "geometry": {"type": "Point", "coordinates": [float(row["lon"]), float(row["lat"])]},
            }
        )
    corridor_metrics_by_id: dict[str, list[Mapping[str, Any]]] = {}
    for row in result["corridor_metrics"]:
        corridor_metrics_by_id.setdefault(str(row["corridor_id"]), []).append(row)
    for source in frozen_data["corridor_features"]:
        corridor_id = _corridor_id(source)
        if corridor_id not in corridor_metrics_by_id:
            continue
        metrics = sorted(
            corridor_metrics_by_id[corridor_id],
            key=lambda item: (item["scope"], item["hypothesis_id"]),
        )
        scopes = [str(item["scope"]) for item in metrics]
        nearest_scopes = [str(item["scope"]) for item in metrics if item["is_nearest_in_scope"]]
        features.append(
            {
                "type": "Feature",
                "id": corridor_id,
                "properties": {
                    "role": "CORREDOR_CONGELADO_AVALIADO",
                    "scopes": scopes,
                    "nearest_in_scopes": nearest_scopes,
                    "hypothesis_id": metrics[0]["hypothesis_id"],
                    "distance_m": metrics[0]["distance_m"],
                    "support_semantics": metrics[0]["support_semantics"],
                },
                "geometry": source["geometry"],
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "RURAL01_AVALIACAO_T5_T6_v1",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": features,
    }


def build_qa(result: Mapping[str, Any], frozen_data: Mapping[str, Any]) -> dict[str, Any]:
    scenarios = {row["cost_scenario_id"] for row in result["scenario_metrics"]}
    corridor_scopes = {
        str(row["scope"]) for row in result["corridor_metrics"]
    }
    expected_corridor_scopes = {
        "PRIMARY_MOV_V_TOP3", "SECONDARY_V1_TOP3", "DIAGNOSTIC_ANY_24"
    }
    checks = {
        "t4_ledger_valid": result["integrity"]["t4_ledger"].get("technical_status") == "PASS",
        "v1_manifest_valid": result["integrity"]["v1_manifest"].get("technical_status") == "PASS",
        "t45_opening_gate_valid_or_unit_api": (
            "t45_evaluator_freeze" not in result["integrity"]
            or result["integrity"]["t45_evaluator_freeze"].get("technical_status") == "PASS"
        ),
        "reference_schema_valid": result["reference"]["scenario_id"] == SCENARIO_ID,
        "spherical_aeqd_manifested": result["analysis_crs"].startswith("+proj=aeqd"),
        "grid_has_7845_valid_cells": len(frozen_data["grid"]) == 7845,
        "v1_has_24_sectors": len(frozen_data["sector_features"]) == 24,
        "mov_v_has_48_base_corridors": len(frozen_data["corridor_features"]) == 48,
        "two_base_hypotheses_present": set(PRIMARY_BASE_SCENARIOS) <= scenarios,
        "six_sensitivity_scenarios_present": set(SENSITIVITY_SCENARIOS) <= scenarios,
        "four_ablations_present": set(ABLATION_SCENARIOS) <= scenarios,
        "three_corridor_scopes_present_or_outside": (
            corridor_scopes == expected_corridor_scopes
            if result["domain"]["status"] != "EXTERIOR"
            else not corridor_scopes
        ),
        "outside_domain_has_no_spatial_assignments": (
            True
            if result["domain"]["status"] != "EXTERIOR"
            else not result["sector_assignment"]["matched_sector_ids"]
            and result["grid_assignment"]["cell_id"] is None
            and not result["corridor_metrics"]
        ),
        "inside_domain_has_sector": (
            True
            if result["domain"]["status"] == "EXTERIOR"
            else bool(result["sector_assignment"]["matched_sector_ids"])
        ),
        "snap_respects_half_diagonal": (
            True
            if result["grid_assignment"]["cell_id"] is None
            else result["grid_assignment"]["snap_distance_m"] <= GRID_MAX_SNAP_M + NUMERIC_EPSILON_M
        ),
        "no_aggregate_hit_error": result["method_guardrails"]["aggregate_hit_or_error_label_created"] is False,
        "no_recomputation_or_retuning": all(
            result["method_guardrails"][key] is False
            for key in (
                "rankings_recomputed",
                "cost_surfaces_recomputed",
                "sectors_recomputed",
                "corridors_recomputed",
                "retuning_after_reference_opening",
            )
        ),
    }
    return {
        "protocol_id": PROTOCOL_ID,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "passed_check_count": sum(bool(value) for value in checks.values()),
        "check_count": len(checks),
        "checks": checks,
        "review_flags": [
            flag
            for flag, active in (
                ("REFERENCE_OUTSIDE_1500M_DOMAIN", result["domain"]["status"] == "EXTERIOR"),
                ("REFERENCE_ON_DOMAIN_OR_SECTOR_BOUNDARY", result["domain"]["status"] == "BORDA" or result["sector_assignment"]["boundary_case"]),
                ("NO_GRID_CELL_WITHIN_HALF_DIAGONAL", result["domain"]["status"] != "EXTERIOR" and result["grid_assignment"]["cell_id"] is None),
                ("REFERENCE_PRECISION_NOT_INFORMED", result["reference"]["horizontal_accuracy_m"] is None),
            )
            if active
        ],
    }


def _opening_record(reference: Mapping[str, Any], reference_file_sha256: str | None) -> dict[str, Any]:
    return {
        "protocol_id": PROTOCOL_ID,
        "scenario_id": SCENARIO_ID,
        "event": "T5_REFERENCE_OPENING",
        "reference": reference,
        "reference_file_sha256": reference_file_sha256,
        "timestamp_policy": "ONLY_USER_SUPPLIED_REVEALED_AT_LOCAL_IS_RECORDED",
        "t4_artifacts_changed": False,
    }


def _markdown_report(result: Mapping[str, Any]) -> str:
    taxonomy = result["result_taxonomy"]
    base = result["primary_base_hypotheses"]
    lines = [
        "# Relatório de avaliação pós-abertura — RURAL-01",
        "",
        f"- Protocolo: `{result['protocol_id']}`.",
        f"- Referência: `{result['reference']['reference_id']}`.",
        f"- Estado no domínio: **{taxonomy['domain']}**.",
        f"- Associação à grade: **{taxonomy['grid']}**.",
        f"- Integridade dos insumos: **{taxonomy['integrity']}**.",
        "- Veredito empírico global: **não calculado por pré-especificação**.",
        "",
        "## Hipóteses BASE coprimárias",
        "",
        "As hipóteses foram mantidas lado a lado, sem média, escolha de vencedora ou promoção retrospectiva.",
        "",
        "| Hipótese | Custo acumulado (m equivalentes) | Percentil ECDF inclusivo | Banda | Orçamento | Rank conservador do setor |",
        "|---|---:|---:|---|---|---:|",
    ]
    for scenario_id in PRIMARY_BASE_SCENARIOS:
        row = base[scenario_id]
        cost = "não avaliável" if row["accumulated_cost_m_equivalent"] is None else f"{row['accumulated_cost_m_equivalent']:.6f}"
        percentile = "não avaliável" if row["inclusive_ecdf_percentile"] is None else f"{row['inclusive_ecdf_percentile']:.6f}%"
        budget = taxonomy["per_cost_scenario"][scenario_id]["budget"]
        rank = row["primary_sector_rank_worst"]
        lines.append(
            f"| {row['hypothesis_id']} | {cost} | {percentile} | {row['cost_band']} | {budget} | {rank if rank is not None else 'não avaliável'} |"
        )
    lines.extend(
        [
            "",
            "## Sensibilidade e corredores",
            "",
            (
                "Nos seis cenários de sensibilidade, "
                f"{result['six_scenario_sensitivity_summary']['count_within_budget_0_to_6']}/6 "
                "ficaram dentro do orçamento congelado e "
                f"{result['six_scenario_sensitivity_summary']['count_top3_0_to_6']}/6 "
                "associaram a referência a setor Top-3 pelo critério conservador."
            ),
        ]
    )
    for hypothesis in ("H_REDE_DISPONIVEL", "H_FORA_REDE"):
        nearest = [
            row for row in result["corridor_metrics"]
            if row["hypothesis_id"] == hypothesis
            and row["scope"] == "PRIMARY_MOV_V_TOP3"
            and row["is_nearest_in_scope"]
        ]
        if nearest:
            row = nearest[0]
            lines.append(
                f"- {hypothesis}: corredor Top-3 MOV-V BASE mais próximo a {row['nearest_distance_m_in_scope']:.6f} m; "
                f"estado **{taxonomy['corridor_by_hypothesis'][hypothesis]}**."
            )
        else:
            lines.append(
                f"- {hypothesis}: corredor Top-3 MOV-V BASE **não avaliável**."
            )
    lines.extend(
        [
            "",
            "## Taxonomia diagnóstica",
            "",
            f"- Relação entre hipóteses: **{taxonomy['hypotheses']}**.",
            f"- Perfil V3: **{result['profile_v3']['status']}**; não altera o resultado territorial congelado.",
            "- Resultados negativos, divergentes ou não avaliáveis permanecem registrados por dimensão.",
            "",
            "## Limites de interpretação",
            "",
            "Custos representam metros equivalentes de esforço, não distância percorrida ou tempo. "
            "Rankings expressam prioridade territorial relativa, não probabilidade de presença. "
            "Corredores são linhas diagnósticas de menor custo até representantes setoriais, não trajetórias observadas. "
            "A tolerância de 21,2132034356 m corresponde ao suporte discreto de meia diagonal da célula de 30 m, não à largura física de um corredor. "
            "Nenhum resultado comanda a operação nem demonstra eficácia geral.",
            "",
            "Nenhum mapa foi gerado nesta etapa; a figura cartográfica permanece produto visual posterior e não interfere nas métricas T6.",
            "",
        ]
    )
    return "\n".join(lines)


def build_scientific_outputs(
    output_dir: Path,
    reference: Mapping[str, Any],
    frozen_data: Mapping[str, Any],
    integrity_receipts: Mapping[str, Any],
    reference_file_sha256: str | None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    result = build_evaluation(
        reference,
        frozen_data=frozen_data,
        integrity_receipts=integrity_receipts,
    )
    write_json(
        output_dir / "registro_abertura_referencia.json",
        _opening_record(result["reference"], reference_file_sha256),
    )
    write_json(output_dir / "resultado_avaliacao_t5_t6.json", result)
    write_csv(output_dir / "metricas_cenarios.csv", result["scenario_metrics"])
    write_csv(output_dir / "areas_bandas_custo.csv", result["cost_band_areas"])
    write_csv(output_dir / "metricas_corredores.csv", result["corridor_metrics"])
    write_json(output_dir / "referencia_avaliacao_t5_t6.geojson", build_geojson(result, frozen_data))
    qa = build_qa(result, frozen_data)
    write_json(output_dir / "relatorio_qa_t5_t6.json", qa)
    (output_dir / "RELATORIO_AVALIACAO_RURAL01_T6.md").write_text(
        _markdown_report(result), encoding="utf-8"
    )
    if qa["status"] != "PASS":
        raise EvaluationContractError("QA T5--T6 falhou")
    return result


def _compare_directories(first: Path, second: Path) -> dict[str, Any]:
    rows = []
    for name in SCIENTIFIC_OUTPUTS:
        first_hash = sha256_file(first / name)
        second_hash = sha256_file(second / name)
        rows.append(
            {
                "path": name,
                "run1_sha256": first_hash,
                "run2_sha256": second_hash,
                "equal": first_hash == second_hash,
            }
        )
    return {
        "status": "PASS" if all(row["equal"] for row in rows) else "FAIL",
        "all_equal": all(row["equal"] for row in rows),
        "file_count": len(rows),
        "files": rows,
    }


def _manifest_outputs(directory: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "role": "output",
        }
        for path in sorted(directory.iterdir())
        if path.is_file() and path.name != "manifesto_avaliacao_t5_t6.json"
    ]


def _validate_existing_output(
    output_dir: Path,
    normalized_reference_hash: str,
) -> dict[str, Any]:
    manifest_path = output_dir / "manifesto_avaliacao_t5_t6.json"
    if not manifest_path.is_file():
        raise EvaluationContractError("Diretório de saída já existe sem manifesto; use nova versão")
    manifest = load_json(manifest_path)
    projected = {key: value for key, value in manifest.items() if key != "payload_sha256"}
    if manifest.get("payload_sha256") != canonical_hash(projected):
        raise EvaluationContractError("Manifesto existente com payload inválido")
    if manifest.get("normalized_reference_sha256") != normalized_reference_hash:
        raise EvaluationContractError("Referência diferente; publique em novo diretório versionado")
    if manifest.get("evaluator_sha256") != sha256_file(Path(__file__)):
        raise EvaluationContractError("Avaliador mudou; publique em novo diretório versionado")
    if manifest.get("config_sha256") != sha256_file(CONFIG_PATH):
        raise EvaluationContractError("Configuração mudou; publique em novo diretório versionado")
    if manifest.get("protocol_sha256") != sha256_file(PROTOCOL_PATH):
        raise EvaluationContractError("Protocolo mudou; publique em novo diretório versionado")
    records = _verify_file_records(
        [
            {**item, "path": str(output_dir.relative_to(ROOT) / item["path"])}
            for item in manifest.get("output_files", [])
        ],
        ROOT,
    )
    if not records or not all(item["valid"] for item in records):
        raise EvaluationContractError("Arquivos de saída existentes divergem do manifesto")
    return manifest


def run_and_publish(reference_path: Path, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    """Valida, executa duas vezes e publica por rename atômico sem sobrescrever."""
    reference_path = reference_path.resolve()
    output_dir = output_dir.resolve()
    raw_reference = load_json(reference_path)
    normalized = validate_reference(raw_reference, require_frozen_record=True)
    t45_before = verify_t45_opening_gate(raw_reference)
    if output_dir.exists():
        return _validate_existing_output(output_dir, normalized["normalized_reference_sha256"])

    t4_before = verify_t4_ledger()
    v1_before = verify_v1_manifest()
    integrity = {
        "t4_ledger": t4_before,
        "v1_manifest": v1_before,
        "t45_evaluator_freeze": t45_before,
    }
    frozen = load_frozen_data()
    reference_file_sha = sha256_file(reference_path)
    output_dir.parent.mkdir(parents=True, exist_ok=True)

    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.stage-", dir=output_dir.parent))
    repeat = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.repeat-", dir=output_dir.parent))
    try:
        # mkdtemp cria os diretórios; a função científica exige destino novo.
        stage.rmdir()
        repeat.rmdir()
        build_scientific_outputs(stage, raw_reference, frozen, integrity, reference_file_sha)
        build_scientific_outputs(repeat, raw_reference, frozen, integrity, reference_file_sha)
        determinism = _compare_directories(stage, repeat)
        if determinism["status"] != "PASS":
            raise EvaluationContractError("Avaliação T5--T6 não determinística")
        write_json(stage / "relatorio_determinismo_t5_t6.json", determinism)

        t4_after = verify_t4_ledger()
        v1_after = verify_v1_manifest()
        t45_after = verify_t45_opening_gate(raw_reference)
        upstream_unchanged = (
            t4_before["ledger_sha256"] == t4_after["ledger_sha256"]
            and v1_before["manifest_sha256"] == v1_after["manifest_sha256"]
            and t45_before["ledger_sha256"] == t45_after["ledger_sha256"]
        )
        if not upstream_unchanged:
            raise EvaluationContractError("Artefatos T0--T4 mudaram durante a avaliação")

        manifest: dict[str, Any] = {
            "protocol_id": PROTOCOL_ID,
            "scenario_id": SCENARIO_ID,
            "evaluation_version": "1.0",
            "publication_policy": "ATOMIC_CREATE_ONLY_VERSIONED_NO_OVERWRITE",
            "normalized_reference_sha256": normalized["normalized_reference_sha256"],
            "reference_file_sha256": reference_file_sha,
            "evaluator_path": str(Path(__file__).resolve().relative_to(ROOT)),
            "evaluator_sha256": sha256_file(Path(__file__)),
            "config_path": str(CONFIG_PATH.resolve().relative_to(ROOT)),
            "config_sha256": sha256_file(CONFIG_PATH),
            "protocol_path": str(PROTOCOL_PATH.resolve().relative_to(ROOT)),
            "protocol_sha256": sha256_file(PROTOCOL_PATH),
            "reference_schema_path": str(REFERENCE_SCHEMA_PATH.resolve().relative_to(ROOT)),
            "reference_schema_sha256": sha256_file(REFERENCE_SCHEMA_PATH),
            "evaluator_freeze_ledger_path": str(EVALUATOR_FREEZE_LEDGER.resolve().relative_to(ROOT)),
            "evaluator_freeze_ledger_sha256": t45_before["ledger_sha256"],
            "t4_ledger_before_sha256": t4_before["ledger_sha256"],
            "t4_ledger_after_sha256": t4_after["ledger_sha256"],
            "v1_manifest_before_sha256": v1_before["manifest_sha256"],
            "v1_manifest_after_sha256": v1_after["manifest_sha256"],
            "t45_evaluator_freeze_before_sha256": t45_before["ledger_sha256"],
            "t45_evaluator_freeze_after_sha256": t45_after["ledger_sha256"],
            "upstream_unchanged": True,
            "determinism": determinism,
            "output_files": _manifest_outputs(stage),
            "map_generated": False,
            "rankings_recomputed": False,
            "cost_surfaces_recomputed": False,
            "sectors_recomputed": False,
            "corridors_recomputed": False,
        }
        manifest["payload_sha256"] = canonical_hash(manifest)
        write_json(stage / "manifesto_avaliacao_t5_t6.json", manifest)
        os.replace(stage, output_dir)
        return manifest
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if repeat.exists():
            shutil.rmtree(repeat)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, help="JSON da referência aberto somente após T4")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)
    manifest = run_and_publish(Path(args.reference), Path(args.output_dir))
    result = load_json(Path(args.output_dir) / "resultado_avaliacao_t5_t6.json")
    print(
        json.dumps(
            {
                "status": "PASS",
                "protocol_id": PROTOCOL_ID,
                "output_dir": str(Path(args.output_dir).resolve()),
                "domain_status": result["domain"]["status"],
                "matched_sector_ids": result["sector_assignment"]["matched_sector_ids"],
                "grid_cell_id": result["grid_assignment"]["cell_id"],
                "two_base_hypotheses_kept_separate": True,
                "upstream_unchanged": manifest["upstream_unchanged"],
                "map_generated": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
