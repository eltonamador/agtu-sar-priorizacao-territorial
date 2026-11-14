#!/usr/bin/env python3
"""Prepara a entrada cega do ensaio DEV do buffer adaptativo.

O script lê exclusivamente as abas cegas ``6_CANDIDATOS_CEGOS`` e
``8_GEO_FEATURES`` do workbook DEV-V2, combina os registros pela chave
``scenario_id`` + ``candidate_id`` e grava uma entrada mínima, sem campos de
ground truth. Também produz uma trilha de auditoria sem coordenadas de
referência.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook


WORKBOOK_RELATIVE = Path(
    "outputs/sprint2_s2_35_dev_v2_implementacao/"
    "DEV_V2_Implementacao_Controlada_S2_35_v1.xlsx"
)
CANDIDATE_SHEET = "6_CANDIDATOS_CEGOS"
GEO_SHEET = "8_GEO_FEATURES"
EXPECTED_ROWS = 90

OUTPUT_FIELDS = [
    "scenario_id",
    "candidate_id",
    "estimated_lat",
    "estimated_lon",
    "base_radius_m",
    "detection_quality",
    "environment_class",
    "position_dispersion_m",
    "information_age_min",
    "r0_semantics",
    "factors_applied",
    "r0_provenance",
    "data_origin",
    "source_row_hash",
    "execution_phase",
]

CANDIDATE_FIELDS = {
    "scenario_id",
    "candidate_id",
    "estimated_lat",
    "estimated_lon",
    "uncertainty_radius_m",
    "confidence_score",
    "information_age_min",
    "data_origin",
    "blind_row_sha256",
}
GEO_FIELDS = {
    "scenario_id",
    "candidate_id",
    "estimated_lat",
    "estimated_lon",
    "environment_class",
    "blind_row_sha256",
}

# Esses nomes não podem aparecer no arquivo derivado usado pelo motor.
FORBIDDEN_OUTPUT_PATTERNS = (
    "ground_truth",
    "groundtruth",
    "reference_lat",
    "reference_lon",
    "true_lat",
    "true_lon",
    "base_lat",
    "base_lon",
    "distance_to_reference",
    "relevant_candidate",
    "generator_distance",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PreparationError(RuntimeError):
    """Falha de integridade na preparação da entrada cega."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_header(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def read_sheet_rows(workbook_path: Path, sheet_name: str) -> tuple[list[str], list[dict[str, Any]]]:
    """Lê uma única aba em modo somente leitura e devolve registros."""
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            raise PreparationError(f"Aba obrigatória ausente: {sheet_name}")
        sheet = workbook[sheet_name]
        iterator = sheet.iter_rows(values_only=True)
        try:
            headers = [normalize_header(value) for value in next(iterator)]
        except StopIteration as exc:
            raise PreparationError(f"Aba vazia: {sheet_name}") from exc
        if not all(headers) or len(set(headers)) != len(headers):
            raise PreparationError(f"Cabeçalho vazio ou duplicado em {sheet_name}")

        rows: list[dict[str, Any]] = []
        for values in iterator:
            if all(value is None for value in values):
                continue
            padded = list(values) + [None] * max(0, len(headers) - len(values))
            rows.append(dict(zip(headers, padded[: len(headers)])))
        return headers, rows
    finally:
        workbook.close()


def require_fields(headers: Iterable[str], required: set[str], sheet_name: str) -> None:
    missing = sorted(required - set(headers))
    if missing:
        raise PreparationError(
            f"Campos obrigatórios ausentes em {sheet_name}: {', '.join(missing)}"
        )


def key_for(row: dict[str, Any], sheet_name: str) -> tuple[str, str]:
    scenario_id = str(row.get("scenario_id") or "").strip()
    candidate_id = str(row.get("candidate_id") or "").strip()
    if not scenario_id or not candidate_id:
        raise PreparationError(f"Chave vazia em {sheet_name}: {row!r}")
    return scenario_id, candidate_id


def numeric(value: Any, field: str, key: tuple[str, str]) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PreparationError(f"{field} não numérico em {key}: {value!r}") from exc
    if not math.isfinite(number):
        raise PreparationError(f"{field} não finito em {key}: {value!r}")
    return number


def clean_number(value: float) -> int | float:
    if value.is_integer():
        return int(value)
    return value


def validate_output_schema(fields: Iterable[str]) -> list[str]:
    violations = []
    for field in fields:
        normalized = field.lower()
        if any(pattern in normalized for pattern in FORBIDDEN_OUTPUT_PATTERNS):
            violations.append(field)
    return violations


def describe(values: list[float]) -> dict[str, float]:
    if not values:
        raise PreparationError("Não há valores para estatística descritiva")
    return {
        "min": min(values),
        "median": statistics.median(values),
        "mean": statistics.fmean(values),
        "max": max(values),
    }


def pearson_correlation(left: list[float], right: list[float]) -> float:
    """Calcula a correlação de Pearson sem dependência estatística externa."""
    if len(left) != len(right) or len(left) < 2:
        raise PreparationError("Séries incompatíveis para correlação")
    mean_left = statistics.fmean(left)
    mean_right = statistics.fmean(right)
    numerator = sum((x - mean_left) * (y - mean_right) for x, y in zip(left, right))
    denominator_left = sum((x - mean_left) ** 2 for x in left)
    denominator_right = sum((y - mean_right) ** 2 for y in right)
    denominator = math.sqrt(denominator_left * denominator_right)
    if denominator == 0:
        raise PreparationError("Série constante impede o cálculo da correlação")
    return numerator / denominator


def prepare(workbook_path: Path, output_csv: Path, audit_json: Path) -> dict[str, Any]:
    if not workbook_path.is_file():
        raise PreparationError(f"Workbook não encontrado: {workbook_path}")

    candidate_headers, candidate_rows = read_sheet_rows(workbook_path, CANDIDATE_SHEET)
    geo_headers, geo_rows = read_sheet_rows(workbook_path, GEO_SHEET)
    require_fields(candidate_headers, CANDIDATE_FIELDS, CANDIDATE_SHEET)
    require_fields(geo_headers, GEO_FIELDS, GEO_SHEET)

    if len(candidate_rows) != EXPECTED_ROWS:
        raise PreparationError(
            f"{CANDIDATE_SHEET}: esperado {EXPECTED_ROWS}, encontrado {len(candidate_rows)}"
        )
    if len(geo_rows) != EXPECTED_ROWS:
        raise PreparationError(
            f"{GEO_SHEET}: esperado {EXPECTED_ROWS}, encontrado {len(geo_rows)}"
        )

    candidate_keys = [key_for(row, CANDIDATE_SHEET) for row in candidate_rows]
    geo_keys = [key_for(row, GEO_SHEET) for row in geo_rows]
    if len(set(candidate_keys)) != EXPECTED_ROWS:
        duplicates = sorted(key for key, count in Counter(candidate_keys).items() if count > 1)
        raise PreparationError(f"Chaves duplicadas em {CANDIDATE_SHEET}: {duplicates}")
    if len(set(geo_keys)) != EXPECTED_ROWS:
        duplicates = sorted(key for key, count in Counter(geo_keys).items() if count > 1)
        raise PreparationError(f"Chaves duplicadas em {GEO_SHEET}: {duplicates}")
    if set(candidate_keys) != set(geo_keys):
        missing_geo = sorted(set(candidate_keys) - set(geo_keys))
        extra_geo = sorted(set(geo_keys) - set(candidate_keys))
        raise PreparationError(
            f"Chaves divergentes entre abas; ausentes em GEO={missing_geo}, extras em GEO={extra_geo}"
        )

    forbidden = validate_output_schema(OUTPUT_FIELDS)
    if forbidden:
        raise PreparationError(f"Campos proibidos no schema de saída: {forbidden}")

    geo_by_key = {key_for(row, GEO_SHEET): row for row in geo_rows}
    output_rows: list[dict[str, Any]] = []
    matching_hashes = 0
    matching_coordinates = 0
    base_radius_values: list[float] = []
    quality_values: list[float] = []
    age_values: list[float] = []
    environment_counts: Counter[str] = Counter()

    for candidate in candidate_rows:
        key = key_for(candidate, CANDIDATE_SHEET)
        geo = geo_by_key[key]

        candidate_hash = str(candidate.get("blind_row_sha256") or "").strip().lower()
        geo_hash = str(geo.get("blind_row_sha256") or "").strip().lower()
        if not SHA256_RE.fullmatch(candidate_hash):
            raise PreparationError(f"Hash inválido em {CANDIDATE_SHEET}, chave {key}")
        if not SHA256_RE.fullmatch(geo_hash):
            raise PreparationError(f"Hash inválido em {GEO_SHEET}, chave {key}")
        if candidate_hash != geo_hash:
            raise PreparationError(f"Hash divergente entre abas na chave {key}")
        matching_hashes += 1

        lat = numeric(candidate.get("estimated_lat"), "estimated_lat", key)
        lon = numeric(candidate.get("estimated_lon"), "estimated_lon", key)
        geo_lat = numeric(geo.get("estimated_lat"), "GEO estimated_lat", key)
        geo_lon = numeric(geo.get("estimated_lon"), "GEO estimated_lon", key)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise PreparationError(f"Coordenada candidata fora do domínio em {key}: {lat}, {lon}")
        if abs(lat - geo_lat) > 1e-10 or abs(lon - geo_lon) > 1e-10:
            raise PreparationError(f"Coordenadas divergentes entre abas na chave {key}")
        matching_coordinates += 1

        base_radius = numeric(candidate.get("uncertainty_radius_m"), "uncertainty_radius_m", key)
        quality = numeric(candidate.get("confidence_score"), "confidence_score", key)
        age = numeric(candidate.get("information_age_min"), "information_age_min", key)
        if base_radius <= 0:
            raise PreparationError(f"Raio-base não positivo em {key}: {base_radius}")
        if not 0 <= quality <= 1:
            raise PreparationError(f"Qualidade fora de [0, 1] em {key}: {quality}")
        if age < 0:
            raise PreparationError(f"Idade da informação negativa em {key}: {age}")

        environment = str(geo.get("environment_class") or "").strip()
        if not environment:
            raise PreparationError(f"environment_class vazio em {key}")

        row = {
            "scenario_id": key[0],
            "candidate_id": key[1],
            "estimated_lat": clean_number(lat),
            "estimated_lon": clean_number(lon),
            "base_radius_m": clean_number(base_radius),
            "detection_quality": clean_number(quality),
            "environment_class": environment,
            "position_dispersion_m": "",
            "information_age_min": clean_number(age),
            "r0_semantics": "diagnostic_legacy",
            "factors_applied": "",
            "r0_provenance": "SEMI_SINTETICO_DERIVADO_DO_GERADOR_DEV_V2",
            "data_origin": str(candidate.get("data_origin") or "").strip(),
            "source_row_hash": candidate_hash,
            "execution_phase": "DEV_DRY_RUN",
        }
        if set(row) != set(OUTPUT_FIELDS):
            raise PreparationError(f"Schema inesperado na linha {key}")
        output_rows.append(row)
        base_radius_values.append(base_radius)
        quality_values.append(quality)
        age_values.append(age)
        environment_counts[environment] += 1

    if len(output_rows) != EXPECTED_ROWS or len({(r['scenario_id'], r['candidate_id']) for r in output_rows}) != EXPECTED_ROWS:
        raise PreparationError("A saída não preservou exatamente 90 chaves únicas")

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_FIELDS, extrasaction="raise")
        writer.writeheader()
        writer.writerows(output_rows)

    # Verificação pós-gravação: cabeçalho e cardinalidade do artefato persistido.
    with output_csv.open("r", encoding="utf-8", newline="") as stream:
        persisted = csv.DictReader(stream)
        persisted_fields = persisted.fieldnames or []
        persisted_rows = list(persisted)
    persisted_forbidden = validate_output_schema(persisted_fields)
    if persisted_fields != OUTPUT_FIELDS:
        raise PreparationError("O cabeçalho persistido difere do schema congelado")
    if persisted_forbidden:
        raise PreparationError(f"Campos proibidos persistidos: {persisted_forbidden}")
    if len(persisted_rows) != EXPECTED_ROWS:
        raise PreparationError("O CSV persistido não contém exatamente 90 registros")

    audit = {
        "artifact": "EXT-ESP-BUF-v1.0 — entrada cega DEV",
        "source": {
            "workbook": workbook_path.as_posix(),
            "workbook_sha256": sha256_file(workbook_path),
            "sheets_read": [CANDIDATE_SHEET, GEO_SHEET],
            "read_policy": "Somente abas cegas; nenhuma outra aba foi lida.",
            "selected_candidate_fields": sorted(CANDIDATE_FIELDS),
            "selected_geo_fields": sorted(GEO_FIELDS),
        },
        "counts": {
            "candidate_rows": len(candidate_rows),
            "geo_rows": len(geo_rows),
            "joined_rows": len(output_rows),
            "unique_keys": len({(r['scenario_id'], r['candidate_id']) for r in output_rows}),
            "matching_hashes": matching_hashes,
            "matching_coordinates": matching_coordinates,
        },
        "checks": {
            "expected_90_rows": True,
            "keys_unique": True,
            "keys_complete_across_sheets": True,
            "blind_hashes_match": True,
            "candidate_coordinates_match_across_blind_sheets": True,
            "forbidden_fields_in_output": [],
            "output_contains_reference_coordinates": False,
            "output_schema_exact": True,
        },
        "statistics": {
            "base_radius_m": describe(base_radius_values),
            "detection_quality": describe(quality_values),
            "information_age_min": describe(age_values),
            "environment_class_counts": dict(sorted(environment_counts.items())),
            "position_dispersion_missing_count": EXPECTED_ROWS,
            "pearson_r_base_radius_vs_information_age": pearson_correlation(
                base_radius_values, age_values
            ),
        },
        "output": {
            "csv": output_csv.as_posix(),
            "csv_sha256": sha256_file(output_csv),
            "columns": OUTPUT_FIELDS,
            "r0_semantics": "diagnostic_legacy",
            "r0_provenance": "SEMI_SINTETICO_DERIVADO_DO_GERADOR_DEV_V2",
            "execution_phase": "DEV_DRY_RUN",
        },
        "interpretation_boundary": (
            "Entrada destinada exclusivamente ao ensaio de desenvolvimento do motor. "
            "O raio-base legado é semissintético e não sustenta inferência confirmatória; "
            "a dispersão posicional permanece ausente e não foi inventada."
        ),
    }

    audit_json.parent.mkdir(parents=True, exist_ok=True)
    audit_json.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return audit


def parse_args() -> argparse.Namespace:
    repository_root = Path(__file__).resolve().parents[2]
    default_workbook = repository_root / WORKBOOK_RELATIVE
    default_output_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=default_workbook)
    parser.add_argument("--output-csv", type=Path, default=default_output_dir / "input_dev_blind.csv")
    parser.add_argument("--audit-json", type=Path, default=default_output_dir / "source_audit.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit = prepare(
        workbook_path=args.workbook.resolve(),
        output_csv=args.output_csv.resolve(),
        audit_json=args.audit_json.resolve(),
    )
    print(
        json.dumps(
            {
                "status": "OK",
                "joined_rows": audit["counts"]["joined_rows"],
                "matching_hashes": audit["counts"]["matching_hashes"],
                "output_csv": audit["output"]["csv"],
                "audit_json": args.audit_json.resolve().as_posix(),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
