#!/usr/bin/env python3
"""Executa a suíte MATA-01 MOV-V e emite recibo verificável."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
ENGINE = HERE / "motor_movimento_mata01_v1.py"
TESTS = HERE / "test_motor_movimento_mata01_v1.py"
CONFIG = HERE / "config_mata01_mov_v1.json"
OUTPUT = PROJECT_ROOT / "outputs/campo_mata01/processamento_movimento_cego_v1/relatorio_testes_mata01_mov_v1.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.discover(str(HERE), pattern=TESTS.name)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    payload = {
        "protocol_id": "MATA01-BLIND-MOV-V-v1.0",
        "status": "PASS" if result.wasSuccessful() else "FAIL",
        "tests_run": result.testsRun,
        "failure_count": len(result.failures),
        "error_count": len(result.errors),
        "engine_sha256": sha256_file(ENGINE),
        "test_suite_sha256": sha256_file(TESTS),
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "config_sha256": sha256_file(CONFIG),
    }
    payload["payload_sha256"] = canonical_hash(payload)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
