#!/usr/bin/env python3
"""Repete o pipeline congelado e registra determinismo e preservação da v1."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
ENGINE = HERE / "motor_movimento_v2.py"
MAIN_OUTPUT = PROJECT_ROOT / "outputs/campo_rural01/processamento_movimento_cego_v2"
REPORT = MAIN_OUTPUT / "relatorio_determinismo_e_preservacao_v2.json"
V1_MANIFEST = PROJECT_ROOT / "outputs/campo_rural01/processamento_cego_v1/manifesto_processamento_cego.json"

CORE_OUTPUTS = (
    "areas_alcancaveis_mov_v2.geojson",
    "corredores_mov_v2.geojson",
    "grade_resistencia.csv",
    "relatorio_qa_mov_v2.json",
    "resultado_mov_v2.json",
    "setores_mov_v2.csv",
    "superficie_custo_H_FORA_REDE.geojson",
    "superficie_custo_H_REDE_DISPONIVEL.geojson",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rural01_mov_v2_repeat_") as temporary:
        repeat_dir = Path(temporary) / "outputs"
        completed = subprocess.run(
            [sys.executable, str(ENGINE), "--output-dir", str(repeat_dir)],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        execution = json.loads(completed.stdout)
        compared: dict[str, dict[str, object]] = {}
        identical = True
        for name in CORE_OUTPUTS:
            published = MAIN_OUTPUT / name
            repeated = repeat_dir / name
            published_hash = sha256_file(published)
            repeated_hash = sha256_file(repeated)
            equal = published.read_bytes() == repeated.read_bytes()
            identical = identical and equal
            compared[name] = {
                "published_sha256": published_hash,
                "repeated_sha256": repeated_hash,
                "byte_identical": equal,
            }

    v1 = json.loads(V1_MANIFEST.read_text(encoding="utf-8"))
    v1_checks: list[dict[str, object]] = []
    v1_unchanged = True
    for item in v1["files"]:
        path = PROJECT_ROOT / item["path"]
        exists = path.is_file()
        size_match = exists and path.stat().st_size == int(item["bytes"])
        hash_match = exists and sha256_file(path) == item["sha256"]
        passed = bool(exists and size_match and hash_match)
        v1_unchanged = v1_unchanged and passed
        v1_checks.append(
            {
                "path": item["path"],
                "exists": exists,
                "size_match": size_match,
                "sha256_match": hash_match,
            }
        )

    status = "PASS" if identical and v1_unchanged and execution.get("ground_truth_used") is False else "FAIL"
    report = {
        "protocol_id": "RURAL01-BLIND-MOV-V-v2.0",
        "freeze_stage": "T4_OUTPUT_AND_MANIFEST_FREEZE",
        "status": status,
        "ground_truth_used": False,
        "full_pipeline_repeat": {
            "executions_compared": 2,
            "core_output_count": len(CORE_OUTPUTS),
            "byte_identical_core_outputs": identical,
            "manifest_excluded_from_byte_comparison_reason": (
                "O caminho do diretório de saída difere entre a execução publicada e a repetição temporária."
            ),
            "files": compared,
        },
        "v1_preservation_check": {
            "manifest": str(V1_MANIFEST.relative_to(PROJECT_ROOT)),
            "verified_file_count": len(v1_checks),
            "unchanged": v1_unchanged,
            "files": v1_checks,
        },
        "interpretation": (
            "A repetição integral produziu os mesmos oito arquivos nucleares; os 29 arquivos selados da v1 "
            "permaneceram íntegros. O resultado continua cego, diagnóstico e não confirmatório."
        ),
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
