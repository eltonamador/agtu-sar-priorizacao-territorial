#!/usr/bin/env python3
"""Prepara T1 e executa/congela T1.5--T2 do REP-S espacial.

O programa jamais recebe o CSV de ground truth. A unica ligacao com a
referencia reservada e o compromisso SHA-256 ja emitido pelo FIELD-CAND-v1.0.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from common import (
    DEFAULT_CONFIG,
    ProtocolError,
    atomic_write_bytes,
    csv_payload,
    file_record,
    fold_text,
    load_config,
    parse_finite_float,
    read_csv,
    read_json,
    sha256_bytes,
    sha256_file,
    stable_hash,
    utc_now,
    validate_dependencies,
    write_json,
)


SCRIPT_VERSION = "1.0.0"


def _ensure_hex_digest(value: Any, field: str) -> str:
    digest = str(value or "").strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ProtocolError(f"{field} deve conter SHA-256 hexadecimal.")
    return digest


def _manifest_payload_valid(manifest: Mapping[str, Any]) -> bool:
    expected = manifest.get("manifest_payload_sha256")
    if not expected:
        return False
    payload = dict(manifest)
    payload.pop("manifest_payload_sha256", None)
    return stable_hash(payload) == expected


def _forbidden_headers(headers: Sequence[str], fragments: Sequence[str]) -> list[str]:
    violations: list[str] = []
    for header in headers:
        token = fold_text(header).replace(" ", "_")
        if any(fold_text(fragment).replace(" ", "_") in token for fragment in fragments):
            violations.append(header)
    return violations


def validate_field_candidate_package(
    blind_csv: Path,
    generator_manifest_path: Path,
    config: Mapping[str, Any],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    manifest = read_json(generator_manifest_path)
    if not isinstance(manifest, dict):
        raise ProtocolError("Manifesto FIELD-CAND deve ser objeto JSON.")
    if not _manifest_payload_valid(manifest):
        raise ProtocolError("manifest_payload_sha256 do FIELD-CAND nao confere.")
    if manifest.get("protocol_id") != config["dependencies"]["field_candidate_protocol"]:
        raise ProtocolError("Protocolo do gerador de candidatos divergente.")
    expected = config["cardinality"]
    if manifest.get("site_count") != expected["sites"]:
        raise ProtocolError("site_count do FIELD-CAND diverge do protocolo.")
    if manifest.get("candidate_count") != expected["candidate_buffers"]:
        raise ProtocolError("candidate_count do FIELD-CAND diverge do protocolo.")
    if manifest.get("candidates_per_site") != expected["candidates_per_site"]:
        raise ProtocolError("candidates_per_site do FIELD-CAND diverge do protocolo.")
    if manifest.get("ground_truth_used_by_buffer_geo_or_ranking") is not False:
        raise ProtocolError("Manifesto FIELD-CAND nao preserva a barreira de ground truth.")
    if manifest.get("ground_truth_used_only_inside_generator") is not True:
        raise ProtocolError("Uso reservado do ground truth pelo gerador nao foi declarado.")
    dependency_hashes = {
        item["role"]: item["sha256"] for item in config["dependencies"]["pinned_files"]
    }
    if manifest.get("config_sha256") != dependency_hashes["field_candidate_config"]:
        raise ProtocolError("Configuracao FIELD-CAND nao corresponde a versao fixada.")
    if sha256_file(blind_csv) != manifest.get("blind_output_sha256"):
        raise ProtocolError("CSV cego FIELD-CAND diverge do hash do manifesto.")
    _ensure_hex_digest(manifest.get("input_ground_truth_csv_sha256"), "input_ground_truth_csv_sha256")

    headers, rows = read_csv(blind_csv)
    expected_headers = list(config["blind_interface"]["required_input_columns"])
    if headers != expected_headers:
        raise ProtocolError("Schema ou ordem de colunas do CSV FIELD-CAND diverge do protocolo.")
    violations = _forbidden_headers(headers, config["blind_interface"]["forbidden_header_fragments"])
    if violations:
        raise ProtocolError("Cabecalhos proibidos na entrada cega: " + ", ".join(violations))
    if len(rows) != expected["candidate_buffers"]:
        raise ProtocolError("Cardinalidade do CSV cego divergente.")

    required_values = config["blind_interface"]["required_values"]
    keys: set[tuple[str, str]] = set()
    slots_by_scenario: dict[str, set[int]] = defaultdict(set)
    sites_by_scenario: dict[str, set[str]] = defaultdict(set)
    environments_by_scenario: dict[str, set[str]] = defaultdict(set)
    for row_number, row in enumerate(rows, start=2):
        for field, required in required_values.items():
            observed = row.get(field, "")
            if isinstance(required, float):
                if parse_finite_float(observed, f"linha {row_number}:{field}") != required:
                    raise ProtocolError(f"Linha {row_number}: {field} diverge do valor congelado.")
            elif observed != str(required):
                raise ProtocolError(f"Linha {row_number}: {field} diverge do valor congelado.")
        scenario_id = row["scenario_id"].strip()
        candidate_id = row["candidate_id"].strip()
        site_id = row["site_id"].strip()
        if not scenario_id or not candidate_id or not site_id:
            raise ProtocolError(f"Linha {row_number}: identificadores vazios.")
        key = (scenario_id, candidate_id)
        if key in keys:
            raise ProtocolError(f"Chave duplicada no FIELD-CAND: {key}.")
        keys.add(key)
        try:
            slot = int(row["candidate_slot"])
        except ValueError as exc:
            raise ProtocolError(f"Linha {row_number}: candidate_slot invalido.") from exc
        if candidate_id != f"{scenario_id}-C{slot}" or slot not in {1, 2, 3}:
            raise ProtocolError(f"Linha {row_number}: candidate_id/slot inconsistente.")
        latitude = parse_finite_float(row["estimated_lat"], f"linha {row_number}:estimated_lat")
        longitude = parse_finite_float(row["estimated_lon"], f"linha {row_number}:estimated_lon")
        quality = parse_finite_float(row["detection_quality"], f"linha {row_number}:detection_quality")
        age = parse_finite_float(row["information_age_min"], f"linha {row_number}:information_age_min")
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ProtocolError(f"Linha {row_number}: coordenada fora de EPSG:4326.")
        if not 0.35 <= quality < 0.95 or not 5 <= age <= 180:
            raise ProtocolError(f"Linha {row_number}: qualidade/idade fora do FIELD-CAND.")
        if row["position_dispersion_m"] or row["factors_applied"]:
            raise ProtocolError(f"Linha {row_number}: campos congelados deveriam permanecer vazios.")

        public_source = {
            field: row[field]
            for field in headers
            if field not in {"source_row_hash", "blind_row_sha256"}
        }
        if stable_hash(public_source) != row["source_row_hash"]:
            raise ProtocolError(f"Linha {row_number}: source_row_hash divergente.")
        blind_base = {**public_source, "source_row_hash": row["source_row_hash"]}
        if stable_hash(blind_base) != row["blind_row_sha256"]:
            raise ProtocolError(f"Linha {row_number}: blind_row_sha256 divergente.")
        slots_by_scenario[scenario_id].add(slot)
        sites_by_scenario[scenario_id].add(site_id)
        environments_by_scenario[scenario_id].add(row["environment_class"])

    if len(slots_by_scenario) != expected["sites"]:
        raise ProtocolError("Quantidade de cenarios divergente.")
    for scenario_id in sorted(slots_by_scenario):
        if slots_by_scenario[scenario_id] != {1, 2, 3}:
            raise ProtocolError(f"Cenario {scenario_id} nao contem exatamente C1, C2 e C3.")
        if len(sites_by_scenario[scenario_id]) != 1 or len(environments_by_scenario[scenario_id]) != 1:
            raise ProtocolError(f"Cenario {scenario_id} mistura site ou ambiente.")
    observed_environments = Counter(next(iter(value)) for value in environments_by_scenario.values())
    if observed_environments != Counter(expected["planned_environment_classes"]):
        raise ProtocolError("Os quatro estratos planejados devem aparecer exatamente uma vez.")
    return rows, manifest


def prepare_t1(
    *,
    blind_csv: Path,
    generator_manifest_path: Path,
    output_csv: Path,
    output_manifest: Path,
    config_path: Path = DEFAULT_CONFIG,
) -> dict[str, Any]:
    targets = [blind_csv.resolve(), generator_manifest_path.resolve(), output_csv.resolve(), output_manifest.resolve()]
    if len(set(targets)) != len(targets):
        raise ProtocolError("Entradas e saidas de T1 devem usar caminhos distintos.")
    if output_csv.exists() or output_manifest.exists():
        raise ProtocolError("Saida T1 existente; o protocolo nao permite sobrescrita.")
    config, config_hash = load_config(config_path)
    dependencies = validate_dependencies(config, config_path)
    rows, generator_manifest = validate_field_candidate_package(blind_csv, generator_manifest_path, config)
    output_headers = list(config["blind_interface"]["buffer_output_columns"])
    output_rows = [{field: row.get(field, "") for field in output_headers} for row in rows]
    payload = csv_payload(output_headers, output_rows)
    atomic_write_bytes(output_csv, payload)

    candidate_map = [
        {
            "site_id": row["site_id"],
            "scenario_id": row["scenario_id"],
            "candidate_id": row["candidate_id"],
            "environment_class": row["environment_class"],
        }
        for row in rows
    ]
    manifest: dict[str, Any] = {
        "protocol_id": config["protocol_id"],
        "script_version": SCRIPT_VERSION,
        "state": "ENTRADA_CEGA_CONGELADA",
        "milestone": "T1",
        "generated_at_utc": utc_now(),
        "validation_modality": config["validation_modality"],
        "ground_truth_used": False,
        "ground_truth_sha256_commitment": generator_manifest["input_ground_truth_csv_sha256"],
        "config_sha256": config_hash,
        "dependencies": dependencies,
        "files": [
            file_record(blind_csv, "field_candidate_blind_input"),
            file_record(generator_manifest_path, "field_candidate_manifest"),
            {
                "role": "buffer_input_t1",
                "path": str(output_csv.resolve()),
                "sha256": sha256_bytes(payload),
                "bytes": len(payload),
            },
        ],
        "site_count": config["cardinality"]["sites"],
        "candidate_count": len(rows),
        "candidate_map": sorted(candidate_map, key=lambda item: (item["scenario_id"], item["candidate_id"])),
        "state_history": [
            {"milestone": "T-1", "state": "PLANO_CONGELADO", "evidence": config_hash},
            {
                "milestone": "T0",
                "state": "GROUND_TRUTH_LACRADO",
                "evidence": generator_manifest["input_ground_truth_csv_sha256"],
            },
            {"milestone": "T1", "state": "ENTRADA_CEGA_CONGELADA", "evidence": sha256_bytes(payload)},
        ],
    }
    manifest["manifest_payload_sha256"] = stable_hash(manifest)
    write_json(output_manifest, manifest)
    return manifest


def _run_command(command: Sequence[str], cwd: Path, log_path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    payload = completed.stdout.encode("utf-8")
    atomic_write_bytes(log_path, payload)
    if completed.returncode != 0:
        raise ProtocolError(f"Comando falhou ({completed.returncode}); consulte {log_path}.")
    return {
        "command": [str(item) for item in command],
        "working_directory": str(cwd),
        "exit_code": completed.returncode,
        "log": file_record(log_path, "test_or_execution_log"),
    }


def _role_path(dependencies: Sequence[Mapping[str, Any]], role: str) -> Path:
    matches = [Path(str(item["path"])) for item in dependencies if item["role"] == role]
    if len(matches) != 1:
        raise ProtocolError(f"Dependencia congelada nao encontrada de modo unico: {role}.")
    return matches[0]


def _validate_t1_manifest(t1_manifest_path: Path, buffer_input: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    manifest = read_json(t1_manifest_path)
    if not isinstance(manifest, dict) or not _manifest_payload_valid(manifest):
        raise ProtocolError("Manifesto T1 invalido.")
    if manifest.get("protocol_id") != config["protocol_id"] or manifest.get("milestone") != "T1":
        raise ProtocolError("Manifesto nao representa T1 deste protocolo.")
    if manifest.get("ground_truth_used") is not False:
        raise ProtocolError("Manifesto T1 viola o firewall.")
    records = [item for item in manifest.get("files", []) if item.get("role") == "buffer_input_t1"]
    if len(records) != 1 or Path(records[0]["path"]).resolve() != buffer_input.resolve():
        raise ProtocolError("CSV de buffer nao corresponde ao manifesto T1.")
    if sha256_file(buffer_input) != records[0]["sha256"]:
        raise ProtocolError("CSV de buffer foi alterado depois de T1.")
    return manifest


def _run_test_suites(output_root: Path, dependencies: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    audit_dir = output_root / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    field_engine = _role_path(dependencies, "field_candidate_engine")
    buffer_engine = _role_path(dependencies, "buffer_engine")
    sector_engine = _role_path(dependencies, "sector_engine")
    commands = [
        (
            [sys.executable, "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py", "-v"],
            field_engine.parent,
            audit_dir / "tests_field_candidate.log",
            "FIELD-CAND-v1.0",
        ),
        (
            [
                sys.executable,
                "test_motor_buffer_adaptativo.py",
                "-v",
                "--json-report",
                str((audit_dir / "tests_buffer.json").resolve()),
            ],
            buffer_engine.parent,
            audit_dir / "tests_buffer.log",
            "EXT-ESP-BUF-v1.0",
        ),
        (
            [sys.executable, "-m", "unittest", "-v", "test_motor_setorizacao_priorizacao.py"],
            sector_engine.parent,
            audit_dir / "tests_sector.log",
            "EXT-ESP-SET-v1.1",
        ),
    ]
    evidence = []
    for command, cwd, log, protocol in commands:
        result = _run_command(command, cwd, log)
        result["protocol"] = protocol
        evidence.append(result)
    return evidence


def _execute_once(
    *,
    label: str,
    output_root: Path,
    buffer_input: Path,
    roads: Path,
    hydro: Path,
    dem_dir: Path,
    worldcover_dir: Path,
    dependencies: Sequence[Mapping[str, Any]],
) -> dict[str, Path]:
    run_dir = output_root / label
    buffer_dir = run_dir / "buffer"
    sector_dir = run_dir / "sectors"
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=False)
    buffer_paths = {
        "buffer_csv": buffer_dir / "buffer_results.csv",
        "buffer_json": buffer_dir / "buffer_results.json",
        "buffer_geojson": buffer_dir / "buffer_polygons.geojson",
        "buffer_manifest": buffer_dir / "manifest_buffer.json",
    }
    buffer_command = [
        sys.executable,
        str(_role_path(dependencies, "buffer_engine")),
        "--input",
        str(buffer_input),
        "--config",
        str(_role_path(dependencies, "buffer_config")),
        "--output-csv",
        str(buffer_paths["buffer_csv"]),
        "--output-json",
        str(buffer_paths["buffer_json"]),
        "--output-geojson",
        str(buffer_paths["buffer_geojson"]),
        "--manifest",
        str(buffer_paths["buffer_manifest"]),
    ]
    _run_command(buffer_command, output_root, logs_dir / "buffer_engine.log")
    sector_command = [
        sys.executable,
        str(_role_path(dependencies, "sector_engine")),
        "--config",
        str(_role_path(dependencies, "sector_config")),
        "--buffer-json",
        str(buffer_paths["buffer_json"]),
        "--buffer-geojson",
        str(buffer_paths["buffer_geojson"]),
        "--buffer-manifest",
        str(buffer_paths["buffer_manifest"]),
        "--roads",
        str(roads),
        "--hydro",
        str(hydro),
        "--dem-dir",
        str(dem_dir),
        "--worldcover-dir",
        str(worldcover_dir),
        "--output-dir",
        str(sector_dir),
    ]
    _run_command(sector_command, output_root, logs_dir / "sector_engine.log")
    return {
        **buffer_paths,
        "sector_geojson": sector_dir / "sector_polygons_dev.geojson",
        "sector_features_csv": sector_dir / "sector_features_dev.csv",
        "sector_ranking_csv": sector_dir / "sector_ranking_dev.csv",
        "buffer_decisions_csv": sector_dir / "buffer_decisions_dev.csv",
        "sector_results_json": sector_dir / "sector_results_dev.json",
        "sector_warnings_log": sector_dir / "warnings_dev.log",
        "sector_manifest": sector_dir / "manifest_setorizacao_dev.json",
    }


def _validate_run_outputs(paths: Mapping[str, Path], config: Mapping[str, Any]) -> None:
    buffer = read_json(paths["buffer_json"])
    sector = read_json(paths["sector_results_json"])
    buffer_manifest = read_json(paths["buffer_manifest"])
    sector_manifest = read_json(paths["sector_manifest"])
    expected = config["cardinality"]
    if buffer.get("ground_truth_used") is not False or buffer.get("record_count") != expected["candidate_buffers"]:
        raise ProtocolError("Saida de buffer viola cardinalidade ou firewall.")
    if buffer_manifest.get("ground_truth_used") is not False:
        raise ProtocolError("Manifesto de buffer viola o firewall.")
    if sector.get("ground_truth_used") is not False:
        raise ProtocolError("Saida setorial viola o firewall.")
    if sector.get("buffer_count") != expected["candidate_buffers"]:
        raise ProtocolError("buffer_count setorial divergente.")
    if sector.get("sector_count") != expected["expected_sectors"]:
        raise ProtocolError("sector_count divergente.")
    if sector.get("sectors_per_buffer") != expected["sectors_per_buffer"]:
        raise ProtocolError("sectors_per_buffer divergente.")
    if sector.get("ranking_scope") != "WITHIN_BUFFER_ONLY":
        raise ProtocolError("Motor setorial tentou ampliar indevidamente o escopo do ranking.")
    if sector_manifest.get("ground_truth_used") is not False:
        raise ProtocolError("Manifesto setorial viola o firewall.")


def run_blind_pipeline(
    *,
    buffer_input: Path,
    t1_manifest_path: Path,
    roads: Path,
    hydro: Path,
    dem_dir: Path,
    worldcover_dir: Path,
    output_root: Path,
    config_path: Path = DEFAULT_CONFIG,
) -> dict[str, Any]:
    buffer_input = buffer_input.resolve()
    t1_manifest_path = t1_manifest_path.resolve()
    roads = roads.resolve()
    hydro = hydro.resolve()
    dem_dir = dem_dir.resolve()
    worldcover_dir = worldcover_dir.resolve()
    output_root = output_root.resolve()
    config_path = config_path.resolve()
    if output_root.exists():
        raise ProtocolError("Diretorio T2 ja existe; use um novo caminho para preservar a imutabilidade.")
    for source in (buffer_input, t1_manifest_path, roads, hydro):
        if not source.is_file():
            raise ProtocolError(f"Arquivo necessario ausente: {source}")
    for directory in (dem_dir, worldcover_dir):
        if not directory.is_dir():
            raise ProtocolError(f"Diretorio GEO necessario ausente: {directory}")
    config, config_hash = load_config(config_path)
    dependencies = validate_dependencies(config, config_path)
    t1 = _validate_t1_manifest(t1_manifest_path, buffer_input, config)
    output_root.mkdir(parents=True, exist_ok=False)
    test_evidence = _run_test_suites(output_root, dependencies)
    first = _execute_once(
        label="run_a",
        output_root=output_root,
        buffer_input=buffer_input,
        roads=roads,
        hydro=hydro,
        dem_dir=dem_dir,
        worldcover_dir=worldcover_dir,
        dependencies=dependencies,
    )
    second = _execute_once(
        label="run_b",
        output_root=output_root,
        buffer_input=buffer_input,
        roads=roads,
        hydro=hydro,
        dem_dir=dem_dir,
        worldcover_dir=worldcover_dir,
        dependencies=dependencies,
    )
    _validate_run_outputs(first, config)
    _validate_run_outputs(second, config)
    scientific_roles = (
        "buffer_csv",
        "buffer_json",
        "buffer_geojson",
        "sector_geojson",
        "sector_features_csv",
        "sector_ranking_csv",
        "buffer_decisions_csv",
        "sector_results_json",
        "sector_warnings_log",
    )
    comparisons: list[dict[str, Any]] = []
    for role in scientific_roles:
        hash_a = sha256_file(first[role])
        hash_b = sha256_file(second[role])
        identical = hash_a == hash_b
        comparisons.append({"role": role, "run_a_sha256": hash_a, "run_b_sha256": hash_b, "identical": identical})
        if not identical:
            raise ProtocolError(f"Determinismo reprovado no artefato cientifico: {role}.")

    primary_files = [file_record(first[role], role) for role in (*scientific_roles, "buffer_manifest", "sector_manifest")]
    repeat_files = [file_record(second[role], f"repeat_{role}") for role in (*scientific_roles, "buffer_manifest", "sector_manifest")]
    source_records = [
        file_record(roads, "source_geo02_roads"),
        file_record(hydro, "source_geo03_hydro"),
        *[file_record(path, "source_geo04_dem") for path in sorted(dem_dir.glob("*.hgt.gz"))],
        *[file_record(path, "source_geo05_worldcover") for path in sorted(worldcover_dir.glob("*.tif"))],
    ]
    if not any(item["role"] == "source_geo04_dem" for item in source_records):
        raise ProtocolError("Nenhum quadrante DEM .hgt.gz foi usado.")
    if not any(item["role"] == "source_geo05_worldcover" for item in source_records):
        raise ProtocolError("Nenhum quadrante WorldCover .tif foi usado.")

    manifest: dict[str, Any] = {
        "protocol_id": config["protocol_id"],
        "script_version": SCRIPT_VERSION,
        "state": "SAIDAS_CEGAS_CONGELADAS",
        "milestone": "T2",
        "generated_at_utc": utc_now(),
        "validation_modality": config["validation_modality"],
        "interpretation": config["interpretation"],
        "ground_truth_used": False,
        "ground_truth_sha256_commitment": t1["ground_truth_sha256_commitment"],
        "config_sha256": config_hash,
        "t1_manifest": file_record(t1_manifest_path, "t1_manifest"),
        "buffer_input": file_record(buffer_input, "buffer_input_t1"),
        "dependencies": dependencies,
        "test_evidence": test_evidence,
        "determinism": {
            "required": True,
            "scientific_files_compared_byte_for_byte": True,
            "all_identical": True,
            "comparisons": comparisons,
        },
        "primary_files": primary_files,
        "repeat_files": repeat_files,
        "source_files": source_records,
        "candidate_map": t1["candidate_map"],
        "site_count": t1["site_count"],
        "candidate_count": t1["candidate_count"],
        "sector_count": config["cardinality"]["expected_sectors"],
        "raw_sector_engine_label_notice": config["freeze_policy"]["raw_sector_engine_labels"],
        "state_history": [
            *t1["state_history"],
            {
                "milestone": "T1.5",
                "state": "MOTORES_VERIFICADOS",
                "evidence": stable_hash(test_evidence),
            },
            {
                "milestone": "T2",
                "state": "SAIDAS_CEGAS_CONGELADAS",
                "evidence": stable_hash(comparisons),
            },
        ],
    }
    manifest["manifest_payload_sha256"] = stable_hash(manifest)
    manifest_path = output_root / "manifest_t2_rep_s_spatial.json"
    write_json(manifest_path, manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare-t1", help="Valida FIELD-CAND e congela a interface do buffer.")
    prepare.add_argument("--blind-csv", type=Path, required=True)
    prepare.add_argument("--field-cand-manifest", type=Path, required=True)
    prepare.add_argument("--output-csv", type=Path, required=True)
    prepare.add_argument("--output-manifest", type=Path, required=True)
    prepare.add_argument("--config", type=Path, default=DEFAULT_CONFIG)

    run = subparsers.add_parser("run-blind", help="Executa duas vezes e congela as saidas em T2.")
    run.add_argument("--buffer-input", type=Path, required=True)
    run.add_argument("--t1-manifest", type=Path, required=True)
    run.add_argument("--roads", type=Path, required=True)
    run.add_argument("--hydro", type=Path, required=True)
    run.add_argument("--dem-dir", type=Path, required=True)
    run.add_argument("--worldcover-dir", type=Path, required=True)
    run.add_argument("--output-root", type=Path, required=True)
    run.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prepare-t1":
            result = prepare_t1(
                blind_csv=args.blind_csv,
                generator_manifest_path=args.field_cand_manifest,
                output_csv=args.output_csv,
                output_manifest=args.output_manifest,
                config_path=args.config,
            )
        else:
            result = run_blind_pipeline(
                buffer_input=args.buffer_input,
                t1_manifest_path=args.t1_manifest,
                roads=args.roads,
                hydro=args.hydro,
                dem_dir=args.dem_dir,
                worldcover_dir=args.worldcover_dir,
                output_root=args.output_root,
                config_path=args.config,
            )
    except ProtocolError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "OK",
                "protocol_id": result["protocol_id"],
                "milestone": result["milestone"],
                "state": result["state"],
                "ground_truth_used": result["ground_truth_used"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
