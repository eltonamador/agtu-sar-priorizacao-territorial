#!/usr/bin/env python3
"""Congela o avaliador T4.5 do RURAL-01 antes da abertura da referência.

O script não recebe coordenadas de avaliação e não executa T6. Ele apenas:

1. verifica os pacotes cegos T2, territorial v1 e MOV-V T4;
2. executa os testes sintéticos do avaliador;
3. confere as decisões metodológicas que precisam estar predefinidas;
4. publica, de forma atômica, recibos e um ledger SHA-256 do T4.5.

Depois de criado, o ledger deve ser tratado como somente leitura. Uma nova
especificação exige novo diretório/versionamento, nunca sobrescrita silenciosa.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CASE_ROOT = ROOT / "outputs/campo_rural01"
DEFAULT_OUTPUT = CASE_ROOT / "avaliador_t45_congelado_v1"

T4_LEDGER = CASE_ROOT / "processamento_movimento_cego_v2/ledger_congelamento_T4_mov_v2.json"
V1_MANIFEST = CASE_ROOT / "processamento_cego_v1/manifesto_processamento_cego.json"
T2_MANIFEST = CASE_ROOT / "t2_congelado_final/manifesto_t2_rural01.json"

CONFIG = HERE / "config_avaliacao_t5_t6_v1.json"
PROTOCOL = HERE / "PROTOCOLO_AVALIACAO_RURAL01_T45_T6_v1_CONGELADO.md"
SCHEMA = HERE / "schema_referencia_t5_v1.json"
EMPTY_TEMPLATE = HERE / "MODELO_REGISTRO_T5_SEM_COORDENADA.json"
EVALUATOR = HERE / "evaluate_rural01_reference.py"
TEST_SUITE = HERE / "test_evaluate_rural01_reference.py"

PROTOCOL_ID = "RURAL01-EVAL-T45-T6-v1.0"
EXPECTED_T4_STATUS = "CONGELADO_ANTES_DA_REVELACAO"
EXPECTED_BANDS = (
    ("B1_ATE_UM_TERCO", 0.0, 500.0),
    ("B2_ENTRE_UM_E_DOIS_TERCOS", 500.0, 1000.0),
    ("B3_ENTRE_DOIS_TERCOS_E_ORCAMENTO", 1000.0, 1500.0),
    ("B4_ACIMA_DO_ORCAMENTO", 1500.0, None),
)
EXPECTED_PACKAGE_FILES = (
    PROTOCOL,
    CONFIG,
    SCHEMA,
    EMPTY_TEMPLATE,
    EVALUATOR,
    TEST_SUITE,
    Path(__file__).resolve(),
)
EXPECTED_BASE_SCHEMA_REQUIRED = {
    "schema_version",
    "record_id",
    "scenario_id",
    "stage",
    "status",
    "reference_received",
    "missing_fields",
    "notes",
}
EXPECTED_REVEALED_REQUIRED = {
    "reference_role",
    "verification_status",
    "position",
    "source",
    "opening",
}
EXPECTED_SOURCE_REQUIRED = {
    "collection_method",
    "equipment",
    "horizontal_accuracy_m",
    "position_observed_at",
    "source_artifact",
    "source_artifact_sha256",
    "provenance_note",
}
EXPECTED_OPENING_REQUIRED = {
    "opened_at",
    "opened_by",
    "opening_method",
    "evaluator_freeze_manifest_sha256",
}


class FreezeError(RuntimeError):
    """Uma porta obrigatória do congelamento T4.5 falhou."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any, *, trailing_newline: bool = False) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if trailing_newline:
        raw += "\n"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FreezeError(f"JSON obrigatório inválido: {path}") from exc


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FreezeError(message)


def plain_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def resolve_project_path(value: str) -> Path:
    path = Path(value)
    resolved = path if path.is_absolute() else ROOT / path
    try:
        resolved.resolve().relative_to(ROOT.resolve())
    except ValueError as exc:
        raise FreezeError(f"Caminho fora do projeto: {value}") from exc
    return resolved


def verify_listed_files(document: Mapping[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for item in document.get("files", []):
        require(isinstance(item, Mapping), "Entrada de manifesto não é objeto")
        require(isinstance(item.get("path"), str), "Entrada de manifesto sem path")
        path = resolve_project_path(str(item["path"]))
        require(path not in seen, f"Arquivo duplicado no manifesto: {path}")
        seen.add(path)
        exists = path.is_file()
        actual_bytes = path.stat().st_size if exists else None
        actual_sha = sha256_file(path) if exists else None
        expected_bytes = int(item.get("bytes", -1))
        expected_sha = str(item.get("sha256", ""))
        rows.append(
            {
                "path": str(path.relative_to(ROOT)),
                "exists": exists,
                "expected_bytes": expected_bytes,
                "actual_bytes": actual_bytes,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "matches": exists and actual_bytes == expected_bytes and actual_sha == expected_sha,
            }
        )
    require(rows, "Manifesto sem arquivos")
    return {
        "file_count": len(rows),
        "all_match": all(row["matches"] for row in rows),
        "files": rows,
    }


def verify_t4() -> dict[str, Any]:
    ledger = load_json(T4_LEDGER)
    payload = {key: value for key, value in ledger.items() if key != "payload_sha256"}
    payload_ok = ledger.get("payload_sha256") == canonical_hash(payload)
    listed = verify_listed_files(ledger)
    return {
        "path": str(T4_LEDGER.relative_to(ROOT)),
        "sha256": sha256_file(T4_LEDGER),
        "status": ledger.get("status"),
        "payload_sha256_valid": payload_ok,
        "listed_files": listed,
        "valid": (
            ledger.get("status") == EXPECTED_T4_STATUS
            and ledger.get("ground_truth_used") is False
            and payload_ok
            and listed["all_match"]
        ),
    }


def verify_v1() -> dict[str, Any]:
    manifest = load_json(V1_MANIFEST)
    listed = verify_listed_files(manifest)
    return {
        "path": str(V1_MANIFEST.relative_to(ROOT)),
        "sha256": sha256_file(V1_MANIFEST),
        "protocol_id": manifest.get("protocol_id"),
        "listed_files": listed,
        "valid": (
            manifest.get("protocol_id") == "RURAL01-BLIND-SET-v1.0"
            and manifest.get("ground_truth_used") is False
            and manifest.get("sector_count") == 24
            and listed["all_match"]
        ),
    }


def verify_t2() -> dict[str, Any]:
    manifest = load_json(T2_MANIFEST)
    payload = {key: value for key, value in manifest.items() if key != "payload_sha256"}
    # O gerador T2 inclui uma quebra de linha na serialização canônica.
    payload_ok = manifest.get("payload_sha256") == canonical_hash(payload, trailing_newline=True)
    listed = verify_listed_files(manifest)
    return {
        "path": str(T2_MANIFEST.relative_to(ROOT)),
        "sha256": sha256_file(T2_MANIFEST),
        "status": manifest.get("status"),
        "payload_sha256_valid": payload_ok,
        "listed_files": listed,
        "valid": (
            manifest.get("status") == "CONGELADO_PASS"
            and manifest.get("ground_truth_used") is False
            and manifest.get("evaluation_position_received_in_package") is False
            and payload_ok
            and listed["all_match"]
        ),
    }


def run_tests() -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(TEST_SUITE)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    match = re.search(r"Ran\s+(\d+)\s+tests?", combined)
    tests_run = int(match.group(1)) if match else None
    return {
        "protocol_id": PROTOCOL_ID,
        "stage": "T4_5_PRE_REVEAL_EVALUATOR_TESTS",
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "status": "PASS" if completed.returncode == 0 and tests_run else "FAIL",
        "return_code": completed.returncode,
        "tests_run": tests_run,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "evaluator_sha256": sha256_file(EVALUATOR),
        "test_suite_sha256": sha256_file(TEST_SUITE),
        "config_sha256": sha256_file(CONFIG),
    }


def file_record(path: Path, role: str, *, recorded_as: Path | None = None) -> dict[str, Any]:
    logical_path = recorded_as or path
    return {
        "path": str(logical_path.relative_to(ROOT)),
        "role": role,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _schema_contract_valid(schema: Mapping[str, Any]) -> bool:
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return False
    position = properties.get("position")
    source = properties.get("source")
    opening = properties.get("opening")
    if not all(isinstance(value, Mapping) for value in (position, source, opening)):
        return False
    position_properties = position.get("properties")
    if not isinstance(position_properties, Mapping):
        return False
    serialized_conditions = json.dumps(schema.get("allOf", []), ensure_ascii=False, sort_keys=True)
    return (
        schema.get("type") == "object"
        and schema.get("additionalProperties") is False
        and EXPECTED_BASE_SCHEMA_REQUIRED <= set(schema.get("required", []))
        and set(properties.get("status", {}).get("enum", []))
        == {"AGUARDANDO_REVELACAO", "REVELADO_CONGELADO"}
        and set(position.get("required", []))
        == {"latitude", "longitude", "crs", "coordinate_order"}
        and position_properties.get("crs", {}).get("const") == "EPSG:4326"
        and position_properties.get("coordinate_order", {}).get("const")
        == "LONGITUDE_LATITUDE"
        and set(source.get("required", [])) == EXPECTED_SOURCE_REQUIRED
        and set(opening.get("required", [])) == EXPECTED_OPENING_REQUIRED
        and "AGUARDANDO_REVELACAO" in serialized_conditions
        and "REVELADO_CONGELADO" in serialized_conditions
        and all(item in serialized_conditions for item in EXPECTED_REVEALED_REQUIRED)
    )


def _declared_upstream_valid(config: Mapping[str, Any]) -> bool:
    upstream = config.get("upstream")
    if not isinstance(upstream, Mapping):
        return False
    required_files = upstream.get("required_files")
    if not isinstance(required_files, list) or len(required_files) != 9:
        return False
    seen: set[Path] = set()
    for item in required_files:
        if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
            return False
        path = resolve_project_path(str(item["path"]))
        if path in seen or not path.is_file() or sha256_file(path) != item.get("sha256"):
            return False
        seen.add(path)
    declared_ledger = upstream.get("t4_ledger")
    if not isinstance(declared_ledger, Mapping):
        return False
    ledger_path = resolve_project_path(str(declared_ledger.get("path", "")))
    if ledger_path != T4_LEDGER or sha256_file(ledger_path) != declared_ledger.get("sha256"):
        return False
    t4 = load_json(T4_LEDGER)
    t4_hashes = {
        str(item.get("sha256"))
        for item in t4.get("files", [])
        if isinstance(item, Mapping)
    }
    return (
        upstream.get("movement_configuration_sha256")
        in {str(item.get("sha256")) for item in required_files if isinstance(item, Mapping)}
        and upstream.get("movement_protocol_sha256") in t4_hashes
    )


def validate_specification(
    config: Mapping[str, Any],
    empty_template: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> dict[str, bool]:
    bands = config.get("cost_evaluation", {}).get("bands", [])
    normalized_bands = tuple(
        (str(item.get("id")), float(item.get("lower")), None if item.get("upper") is None else float(item.get("upper")))
        for item in bands
    )
    hypotheses = config.get("principal_hypotheses", [])
    corridor = config.get("corridor_evaluation", {})
    primary = corridor.get("primary_set", {})
    secondary = corridor.get("secondary_set", {})
    diagnostic = corridor.get("diagnostic_any24_set", {})
    geometry = config.get("geometry", {})
    reference_position = empty_template.get("position")
    coordinates_absent = reference_position is None or (
        isinstance(reference_position, Mapping)
        and reference_position.get("latitude") is None
        and reference_position.get("longitude") is None
    )
    return {
        "protocol_and_status_frozen": (
            config.get("protocol_id") == PROTOCOL_ID
            and config.get("status") == EXPECTED_T4_STATUS
        ),
        "reference_not_received": config.get("blind_state", {}).get("reference_received") is False,
        "reference_coordinates_absent_from_config": config.get("blind_state", {}).get("reference_coordinates_present_in_config") is False,
        "empty_template_has_no_coordinates": coordinates_absent,
        "reference_schema_semantics_fixed": _schema_contract_valid(schema),
        "empty_template_identity_valid": (
            empty_template.get("schema_version") == "1.0"
            and empty_template.get("scenario_id") == "RURAL-01"
            and empty_template.get("stage") == "T5_REFERENCE_OPENING"
            and empty_template.get("status") == "AGUARDANDO_REVELACAO"
            and empty_template.get("reference_received") is False
            and not any(key in empty_template for key in ("position", "source", "opening"))
        ),
        "declared_upstream_files_match": _declared_upstream_valid(config),
        "retuning_forbidden": config.get("blind_state", {}).get("retuning_after_opening") is False,
        "global_pass_fail_forbidden": config.get("blind_state", {}).get("global_empirical_pass_fail_forbidden") is True,
        "domain_and_numeric_tolerance_fixed": (
            float(geometry.get("domain_radius_m", -1)) == 1500.0
            and float(geometry.get("domain_boundary_tolerance_m", -1)) == 0.05
        ),
        "grid_support_fixed": abs(float(geometry.get("half_cell_diagonal_m", -1)) - 21.2132034356) < 1e-10,
        "inclusive_ecdf_fixed": config.get("cost_evaluation", {}).get("ecdf", {}).get("method") == "INCLUSIVE_EMPIRICAL_CDF",
        "cost_bands_fixed_to_budget_thirds": normalized_bands == EXPECTED_BANDS,
        "two_equal_principal_hypotheses": (
            len(hypotheses) == 2
            and {item.get("hypothesis_id") for item in hypotheses} == {"H_REDE_DISPONIVEL", "H_FORA_REDE"}
            and all(item.get("status") == "PARALLEL_EQUAL_STATUS" for item in hypotheses)
            and config.get("hypothesis_aggregation", {}).get("winner_selection_forbidden") is True
        ),
        "primary_corridor_is_mov_v_top3": primary.get("selector") == "JOIN_CORRIDOR_TO_SETORES_MOV_V2_BY_HYPOTHESIS_ID_AND_SECTOR_ID_WHERE_SENSITIVITY_PROFILE_BASE_AND_MOBILITY_RANK_LE_3",
        "secondary_corridor_is_v1_top3": secondary.get("selector") == "v1_top3_member == true",
        "diagnostic_corridor_is_any24": diagnostic.get("selector") == "ALL_24_FROZEN_SECTOR_CORRIDORS",
        "corridor_support_not_physical_width": corridor.get("threshold_semantics") == "HALF_DIAGONAL_OF_30M_CELL_NOT_PHYSICAL_WIDTH",
        "six_sensitivity_scenarios_fixed": len(config.get("sensitivity", {}).get("required_cost_scenarios", [])) == 6,
        "ablations_secondary_only": config.get("ablations", {}).get("role") == "SECONDARY_DIAGNOSTIC_ONLY",
        "profile_v3_cannot_modify_spatial_result": config.get("profile_v3", {}).get("may_modify_frozen_territorial_results") is False,
        "negative_results_preserved": config.get("result_taxonomy", {}).get("negative_result_must_be_preserved") is True,
        "missing_values_not_invented": config.get("missing_data", {}).get("invent_values") is False,
    }


def package_files() -> list[Path]:
    files = sorted(EXPECTED_PACKAGE_FILES)
    missing = sorted(str(path) for path in files if not path.is_file())
    require(not missing, f"Arquivos do avaliador ausentes: {', '.join(missing)}")
    return files


def freeze(output_dir: Path) -> dict[str, Any]:
    require(not output_dir.exists(), f"Destino de congelamento já existe: {output_dir}")
    config = load_json(CONFIG)
    empty_template = load_json(EMPTY_TEMPLATE)
    schema = load_json(SCHEMA)

    t4_before = verify_t4()
    v1_before = verify_v1()
    t2_before = verify_t2()
    require(t4_before["valid"], "Ledger T4 ou seus 29 arquivos não estão íntegros")
    require(v1_before["valid"], "Manifesto territorial v1 ou seus arquivos não estão íntegros")
    require(t2_before["valid"], "Manifesto T2 ou seus arquivos não estão íntegros")

    tests = run_tests()
    require(tests["status"] == "PASS", "Suíte sintética do avaliador falhou")
    require(isinstance(tests["tests_run"], int) and tests["tests_run"] >= 20, "Cobertura mínima de 20 testes não atingida")

    specification = validate_specification(config, empty_template, schema)
    require(all(specification.values()), "Especificação T4.5 não satisfaz todas as portas")

    t4_after = verify_t4()
    v1_after = verify_v1()
    t2_after = verify_t2()
    upstream_unchanged = (
        t4_before["sha256"] == t4_after["sha256"]
        and v1_before["sha256"] == v1_after["sha256"]
        and t2_before["sha256"] == t2_after["sha256"]
        and t4_after["valid"]
        and v1_after["valid"]
        and t2_after["valid"]
    )
    require(upstream_unchanged, "Um pacote T0–T4 mudou durante o teste do avaliador")

    package = package_files()
    created_at = datetime.now(ZoneInfo("America/Belem")).isoformat(timespec="seconds")
    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=parent))
    try:
        tests_doc = dict(tests)
        tests_doc["created_at_local"] = created_at
        tests_doc["payload_sha256"] = canonical_hash(tests_doc)
        write_json(temp_dir / "relatorio_testes_avaliador_t45_v1.json", tests_doc)

        checks: dict[str, bool] = {
            "t4_ledger_and_29_files_intact": bool(t4_after["valid"] and t4_after["listed_files"]["file_count"] == 29),
            "v1_manifest_and_29_files_intact": bool(v1_after["valid"] and v1_after["listed_files"]["file_count"] == 29),
            "t2_manifest_intact": bool(t2_after["valid"]),
            "synthetic_tests_pass": tests_doc["status"] == "PASS",
            "synthetic_test_count_at_least_20": int(tests_doc["tests_run"]) >= 20,
            "upstream_unchanged_during_tests": upstream_unchanged,
            **specification,
        }
        qa: dict[str, Any] = {
            "protocol_id": PROTOCOL_ID,
            "stage": "T4_5_PRE_REVEAL_EVALUATOR_FREEZE",
            "created_at_local": created_at,
            "status": "PASS" if all(checks.values()) else "FAIL",
            "passed_check_count": sum(bool(value) for value in checks.values()),
            "check_count": len(checks),
            "checks": checks,
            "ground_truth_received": False,
            "reference_coordinates_present": False,
            "t4_verification": t4_after,
            "v1_verification": v1_after,
            "t2_verification": t2_after,
        }
        qa["payload_sha256"] = canonical_hash(qa)
        require(qa["status"] == "PASS", "QA T4.5 falhou")
        write_json(temp_dir / "relatorio_qa_avaliador_t45_v1.json", qa)

        summary = f"""# Congelamento T4.5 do avaliador RURAL-01\n\n- protocolo: `{PROTOCOL_ID}`;\n- estado: **CONGELADO ANTES DA REVELAÇÃO**;\n- instante local do selo: `{created_at}` (`America/Belem`);\n- posição de referência recebida: **não**;\n- coordenadas de referência presentes: **não**;\n- T4 MOV-V: **{t4_after['listed_files']['file_count']}/{t4_after['listed_files']['file_count']} arquivos íntegros**;\n- territorial v1: **{v1_after['listed_files']['file_count']}/{v1_after['listed_files']['file_count']} arquivos íntegros**;\n- testes sintéticos: **{tests_doc['tests_run']} aprovados**;\n- controles de QA: **{qa['passed_check_count']}/{qa['check_count']} aprovados**.\n\nEste selo fecha as regras de percentil, bandas, bordas, grade, rankings, hipóteses, sensibilidades e corredores antes de T5. O arquivo-modelo continua sem coordenada. A próxima etapa autorizada é registrar a posição declarada do alvo simulado em arquivo T5 separado e imutável; depois, executar T6 sem modificar T0–T4.5.\n"""
        (temp_dir / "RESUMO_CONGELAMENTO_T45.md").write_text(summary, encoding="utf-8")

        work_records = [file_record(path, "T45_EVALUATOR_PACKAGE") for path in package]
        receipt_records = [
            file_record(
                path,
                "T45_FREEZE_RECEIPT",
                recorded_as=output_dir / path.name,
            )
            for path in sorted(temp_dir.iterdir())
            if path.is_file()
        ]
        ledger: dict[str, Any] = {
            "protocol_id": PROTOCOL_ID,
            "stage": "T4_5_PRE_REVEAL_EVALUATOR_FREEZE",
            "status": EXPECTED_T4_STATUS,
            "created_at_local": created_at,
            "timezone": "America/Belem",
            "scenario_id": "RURAL-01",
            "ground_truth_received": False,
            "reference_coordinates_present": False,
            "reference_opening_allowed_after_this_ledger": True,
            "retuning_after_reference_opening": False,
            "hypothesis_selection_after_opening": False,
            "global_pass_fail_forbidden": True,
            "upstream": {
                "t4_ledger_sha256": t4_after["sha256"],
                "t4_payload_sha256": load_json(T4_LEDGER).get("payload_sha256"),
                "v1_manifest_sha256": v1_after["sha256"],
                "t2_manifest_sha256": t2_after["sha256"],
            },
            "tests": {
                "status": tests_doc["status"],
                "tests_run": tests_doc["tests_run"],
                "receipt_sha256": sha256_file(temp_dir / "relatorio_testes_avaliador_t45_v1.json"),
            },
            "qa": {
                "status": qa["status"],
                "passed_check_count": qa["passed_check_count"],
                "check_count": qa["check_count"],
                "receipt_sha256": sha256_file(temp_dir / "relatorio_qa_avaliador_t45_v1.json"),
            },
            "files": work_records + receipt_records,
            "file_count": len(work_records) + len(receipt_records),
            "interpretation": (
                "O avaliador, suas convenções e seus testes foram selados antes de T5. "
                "O selo não contém a posição reservada e não produz resultado T6."
            ),
        }
        ledger["payload_sha256"] = canonical_hash(ledger)
        write_json(temp_dir / "ledger_congelamento_avaliador_t45_v1.json", ledger)

        reloaded = load_json(temp_dir / "ledger_congelamento_avaliador_t45_v1.json")
        payload = {key: value for key, value in reloaded.items() if key != "payload_sha256"}
        require(reloaded.get("payload_sha256") == canonical_hash(payload), "Payload do ledger T4.5 inválido")
        os.replace(temp_dir, output_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    return load_json(output_dir / "ledger_congelamento_avaliador_t45_v1.json")


def verify_frozen(output_dir: Path) -> dict[str, Any]:
    ledger_path = output_dir / "ledger_congelamento_avaliador_t45_v1.json"
    ledger = load_json(ledger_path)
    payload = {key: value for key, value in ledger.items() if key != "payload_sha256"}
    listed = verify_listed_files(ledger)
    tests_path = output_dir / "relatorio_testes_avaliador_t45_v1.json"
    qa_path = output_dir / "relatorio_qa_avaliador_t45_v1.json"
    tests_doc = load_json(tests_path)
    qa_doc = load_json(qa_path)
    ledger_tests = ledger.get("tests") if isinstance(ledger.get("tests"), Mapping) else {}
    ledger_qa = ledger.get("qa") if isinstance(ledger.get("qa"), Mapping) else {}
    tests_payload = {key: value for key, value in tests_doc.items() if key != "payload_sha256"}
    qa_payload = {key: value for key, value in qa_doc.items() if key != "payload_sha256"}
    tests_valid = (
        tests_doc.get("status") == "PASS"
        and (plain_int(tests_doc.get("tests_run")) or -1) >= 20
        and tests_doc.get("payload_sha256") == canonical_hash(tests_payload)
        and ledger_tests.get("receipt_sha256") == sha256_file(tests_path)
        and ledger_tests.get("status") == tests_doc.get("status")
        and ledger_tests.get("tests_run") == tests_doc.get("tests_run")
    )
    qa_valid = (
        qa_doc.get("status") == "PASS"
        and plain_int(qa_doc.get("passed_check_count"))
        == plain_int(qa_doc.get("check_count"))
        and (plain_int(qa_doc.get("check_count")) or -1) > 0
        and qa_doc.get("payload_sha256") == canonical_hash(qa_payload)
        and ledger_qa.get("receipt_sha256") == sha256_file(qa_path)
        and ledger_qa.get("status") == qa_doc.get("status")
        and ledger_qa.get("passed_check_count") == qa_doc.get("passed_check_count")
        and ledger_qa.get("check_count") == qa_doc.get("check_count")
    )
    t4 = verify_t4()
    v1 = verify_v1()
    t2 = verify_t2()
    status = (
        ledger.get("status") == EXPECTED_T4_STATUS
        and ledger.get("ground_truth_received") is False
        and ledger.get("reference_coordinates_present") is False
        and ledger.get("payload_sha256") == canonical_hash(payload)
        and plain_int(ledger.get("file_count")) == len(ledger.get("files", []))
        and listed["all_match"]
        and tests_valid
        and qa_valid
        and t4["valid"]
        and v1["valid"]
        and t2["valid"]
    )
    return {
        "status": "PASS" if status else "FAIL",
        "ledger": str(ledger_path.relative_to(ROOT)),
        "ledger_sha256": sha256_file(ledger_path),
        "listed_files": listed["file_count"],
        "all_listed_files_match": listed["all_match"],
        "tests_receipt_valid": tests_valid,
        "qa_receipt_valid": qa_valid,
        "upstream_t4_valid": t4["valid"],
        "upstream_v1_valid": v1["valid"],
        "upstream_t2_valid": t2["valid"],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    if args.verify_only:
        result = verify_frozen(output_dir)
    else:
        ledger = freeze(output_dir)
        result = {
            "status": ledger["status"],
            "stage": ledger["stage"],
            "tests_run": ledger["tests"]["tests_run"],
            "qa": f"{ledger['qa']['passed_check_count']}/{ledger['qa']['check_count']}",
            "file_count": ledger["file_count"],
            "payload_sha256": ledger["payload_sha256"],
            "ledger": str((output_dir / 'ledger_congelamento_avaliador_t45_v1.json').relative_to(ROOT)),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] in {"PASS", EXPECTED_T4_STATUS} else 1


if __name__ == "__main__":
    raise SystemExit(main())
