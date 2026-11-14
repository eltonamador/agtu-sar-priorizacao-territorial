#!/usr/bin/env python3
"""Cria e verifica o ledger final do congelamento T4 do RURAL-01 MOV-V v2."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUTPUT = ROOT / "outputs/campo_rural01/processamento_movimento_cego_v2"
LEDGER = OUTPUT / "ledger_congelamento_T4_mov_v2.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_manifest(manifest: dict[str, Any]) -> bool:
    expected_payload = manifest.get("payload_sha256")
    payload = {key: value for key, value in manifest.items() if key != "payload_sha256"}
    if expected_payload != canonical_hash(payload):
        return False
    for item in manifest.get("files", []):
        path = Path(item["path"])
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file() or path.stat().st_size != int(item["bytes"]) or sha256_file(path) != item["sha256"]:
            return False
    return True


def verify_cartographic_manifest(manifest: dict[str, Any]) -> bool:
    for group in ("sources", "outputs"):
        for item in manifest.get(group, []):
            path = ROOT / item["path"]
            if not path.is_file() or path.stat().st_size != int(item["bytes"]) or sha256_file(path) != item["sha256"]:
                return False
    return True


def file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def main() -> int:
    config = load_json(HERE / "config_mov_v2.json")
    qa = load_json(OUTPUT / "relatorio_qa_mov_v2.json")
    tests = load_json(OUTPUT / "relatorio_testes_mov_v2.json")
    result = load_json(OUTPUT / "resultado_mov_v2.json")
    determinism = load_json(OUTPUT / "relatorio_determinismo_e_preservacao_v2.json")
    engine_manifest = load_json(OUTPUT / "manifesto_mov_v2.json")
    cartographic_manifest = load_json(OUTPUT / "manifesto_cartografico_mov_v2.json")

    test_payload = {key: value for key, value in tests.items() if key != "payload_sha256"}
    test_hashes_current = all(
        (
            tests[receipt_key] == sha256_file(HERE / filename)
            for receipt_key, filename in (
                ("engine_sha256", "motor_movimento_v2.py"),
                ("test_suite_sha256", "test_motor_movimento_v2.py"),
                ("config_sha256", "config_mov_v2.json"),
                ("runner_sha256", "run_tests_with_receipt.py"),
            )
        )
    )
    checks = {
        "configuration_frozen_t4": (
            config.get("status") == "CONGELADO_ANTES_DA_REVELACAO"
            and config.get("freeze", {}).get("current_stage") == "T4_OUTPUT_AND_MANIFEST_FREEZE"
        ),
        "blind_controls_closed": (
            config.get("blind_control", {}).get("ground_truth_used") is False
            and config.get("blind_control", {}).get("reference_package_accessible_to_engine") is False
            and config.get("blind_control", {}).get("reference_opening_allowed_only_after_T4") is True
        ),
        "result_blind": result.get("ground_truth_used") is False,
        "qa_passed": qa.get("status") == "PASS" and qa.get("passed_gate_count") == qa.get("gate_count") == 37,
        "test_suite_passed": (
            tests.get("status") == "PASS"
            and tests.get("tests_run") == 21
            and tests.get("failure_count") == 0
            and tests.get("error_count") == 0
            and tests.get("payload_sha256") == canonical_hash(test_payload)
            and test_hashes_current
        ),
        "engine_manifest_integrity": verify_manifest(engine_manifest),
        "cartographic_manifest_integrity": verify_cartographic_manifest(cartographic_manifest),
        "determinism_and_v1_preservation": (
            determinism.get("status") == "PASS"
            and determinism.get("full_pipeline_repeat", {}).get("byte_identical_core_outputs") is True
            and determinism.get("v1_preservation_check", {}).get("unchanged") is True
            and determinism.get("v1_preservation_check", {}).get("verified_file_count") == 29
        ),
        "map_png_valid": (OUTPUT / "Mapa_RURAL01_Resistencia_Corredores_MOV_V_v2.png").is_file(),
        "map_pdf_valid": (OUTPUT / "Mapa_RURAL01_Resistencia_Corredores_MOV_V_v2.pdf").read_bytes()[:5] == b"%PDF-",
        "no_hypothesis_selected": result.get("hypothesis_selection_status") == "NENHUMA_HIPOTESE_SELECIONADA_REGIME_DESCONHECIDO",
        "time_not_converted": result.get("elapsed_hours_role") == "CONTEXTO_NAO_CONVERTIDO_AUTOMATICAMENTE_EM_DISTANCIA_OU_TEMPO_ATIVO",
    }

    work_files = sorted(path for path in HERE.iterdir() if path.is_file())
    output_files = sorted(path for path in OUTPUT.iterdir() if path.is_file() and path != LEDGER)
    files = [file_record(path) for path in work_files + output_files]
    passed = all(checks.values())
    ledger: dict[str, Any] = {
        "protocol_id": config["protocol_id"],
        "engine_version": config["engine_version"],
        "status": "CONGELADO_ANTES_DA_REVELACAO" if passed else "FALHA_NO_CONGELAMENTO",
        "freeze_stage": "T4_OUTPUT_AND_MANIFEST_FREEZE",
        "created_at_local": datetime.now(ZoneInfo("America/Belem")).isoformat(),
        "ground_truth_used": False,
        "reference_package_accessible_to_engine": False,
        "retuning_after_reference_opening": False,
        "hypothesis_selection_status": result["hypothesis_selection_status"],
        "review_status": result["review_status"],
        "checks": checks,
        "passed_check_count": sum(bool(value) for value in checks.values()),
        "check_count": len(checks),
        "file_count": len(files),
        "files": files,
        "linked_receipts": {
            "test_suite_payload_sha256": tests["payload_sha256"],
            "engine_manifest_payload_sha256": engine_manifest["payload_sha256"],
            "cartographic_png_sha256": sha256_file(OUTPUT / "Mapa_RURAL01_Resistencia_Corredores_MOV_V_v2.png"),
            "determinism_report_sha256": sha256_file(OUTPUT / "relatorio_determinismo_e_preservacao_v2.json"),
        },
        "interpretation": (
            "T0–T4 foram selados antes da abertura da posição verdadeira. REVISAR permanece como estado "
            "interpretativo do resultado e não invalida o congelamento; ele impede uso confirmatório ou comando operacional."
        ),
    }
    ledger["payload_sha256"] = canonical_hash(ledger)
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    reloaded = load_json(LEDGER)
    payload = {key: value for key, value in reloaded.items() if key != "payload_sha256"}
    if reloaded.get("payload_sha256") != canonical_hash(payload) or not passed:
        raise SystemExit("Falha na verificação do ledger T4")
    print(json.dumps({
        "status": reloaded["status"],
        "checks": f"{reloaded['passed_check_count']}/{reloaded['check_count']}",
        "files": reloaded["file_count"],
        "payload_sha256": reloaded["payload_sha256"],
        "ledger": str(LEDGER),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
