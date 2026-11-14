#!/usr/bin/env python3
"""Executa a suíte MOV-V e grava um recibo verificável em JSON."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import unittest
from pathlib import Path
from typing import Any, Sequence


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
TEST_PATH = HERE / "test_motor_movimento_v2.py"
ENGINE_PATH = HERE / "motor_movimento_v2.py"
CONFIG_PATH = HERE / "config_mov_v2.json"
DEFAULT_RECEIPT_PATH = (
    PROJECT_ROOT
    / "outputs/campo_rural01/processamento_movimento_cego_v2/relatorio_testes_mov_v2.json"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_suite(output_path: Path) -> dict[str, Any]:
    suite = unittest.defaultTestLoader.discover(str(HERE), pattern=TEST_PATH.name)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    receipt: dict[str, Any] = {
        "status": "PASS" if result.wasSuccessful() else "FAIL",
        "tests_run": result.testsRun,
        "failure_count": len(result.failures),
        "error_count": len(result.errors),
        "skipped_count": len(result.skipped),
        "failures": [{"test": str(test), "detail": detail} for test, detail in result.failures],
        "errors": [{"test": str(test), "detail": detail} for test, detail in result.errors],
        "skipped": [{"test": str(test), "reason": reason} for test, reason in result.skipped],
        "python_version": platform.python_version(),
        "engine_sha256": sha256_file(ENGINE_PATH),
        "test_suite_sha256": sha256_file(TEST_PATH),
        "config_sha256": sha256_file(CONFIG_PATH),
        "runner_sha256": sha256_file(Path(__file__).resolve()),
    }
    receipt["payload_sha256"] = canonical_hash(receipt)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not result.wasSuccessful():
        raise SystemExit(stream.getvalue())
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_RECEIPT_PATH))
    args = parser.parse_args(argv)
    receipt = run_suite(Path(args.output).resolve())
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
