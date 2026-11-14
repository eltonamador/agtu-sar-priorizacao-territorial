#!/usr/bin/env python3
"""Gera candidatos semissinteticos cegos para o piloto de campo REP-S.

O arquivo reservado de referencia e lido exclusivamente por este gerador. A
saida cega nao inclui coordenadas protegidas nem variaveis derivadas da
distancia real. O modulo de buffer, GEO e ranking deve receber somente a saida
cega, depois de seu congelamento criptografico.

Dependencias: somente a biblioteca padrao do Python.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import sys
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = SCRIPT_DIR / "config_field_candidates_v1.json"
UINT32_MASK = 0xFFFFFFFF
UINT32_SCALE = 2**32
# Atualizado somente quando uma nova versao formal do protocolo e emitida.
EXPECTED_CONFIG_SHA256 = "2e245308bd06b3c9ec89df7630de37b95f0e6e5b351d8bcb9cdb59d0ac19163d"


class GenerationError(RuntimeError):
    """Erro de protocolo, entrada, segregacao ou gravacao."""


class XorShift32:
    """PRNG xorshift32 com contagem explicita de sorteios."""

    def __init__(self, seed: int):
        if not isinstance(seed, int) or not 0 < seed <= UINT32_MASK:
            raise GenerationError("A semente xorshift32 deve estar entre 1 e 2^32-1.")
        self.state = seed & UINT32_MASK
        self.draw_count = 0

    def next_uint32(self) -> int:
        value = self.state
        value ^= (value << 13) & UINT32_MASK
        value ^= value >> 17
        value ^= (value << 5) & UINT32_MASK
        self.state = value & UINT32_MASK
        self.draw_count += 1
        return self.state

    def next_float(self) -> float:
        return self.next_uint32() / UINT32_SCALE


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def stable_hash(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def normalize_text(value: Any) -> str:
    return str(value if value is not None else "").strip()


def fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


def load_config(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise GenerationError(f"Nao foi possivel ler a configuracao: {path}") from exc
    observed_config_sha256 = sha256_bytes(raw)
    if observed_config_sha256 != EXPECTED_CONFIG_SHA256:
        raise GenerationError(
            "Falha de integridade: o SHA-256 da configuracao diverge do protocolo congelado."
        )
    try:
        config = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GenerationError("A configuracao JSON e invalida.") from exc
    validate_config(config)
    return config, observed_config_sha256


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("protocol_id") != "FIELD-CAND-v1.0":
        raise GenerationError("protocol_id divergente de FIELD-CAND-v1.0.")
    if config.get("freeze_date") != "2026-10-15":
        raise GenerationError("freeze_date divergente da data congelada 2026-10-15.")
    if config.get("site_count") != 4 or config.get("candidates_per_site") != 3:
        raise GenerationError("O protocolo exige 4 sites e 3 candidatos por site.")

    seed = config.get("seed") or {}
    material = normalize_text(seed.get("material_utf8"))
    expected_sha = hashlib.sha256(material.encode("utf-8")).hexdigest()
    if seed.get("sha256") != expected_sha:
        raise GenerationError("O SHA-256 declarado da semente nao corresponde ao material.")
    expected_uint32 = int(expected_sha[:8], 16)
    if seed.get("uint32") != expected_uint32 or expected_uint32 == 0:
        raise GenerationError("O estado uint32 declarado da semente e invalido.")

    prng = config.get("prng") or {}
    if prng.get("algorithm") != "xorshift32":
        raise GenerationError("O algoritmo congelado deve ser xorshift32.")
    if prng.get("draws_per_site") != 14 or prng.get("expected_total_draws") != 56:
        raise GenerationError("A contagem congelada de sorteios deve ser 14 por site e 56 no total.")

    bands = config.get("distance_bands_m") or []
    expected_bands = [
        ("PROXIMO", 250.0, 800.0),
        ("INTERMEDIARIO", 800.0, 2000.0),
        ("DISTANTE", 2000.0, 4500.0),
    ]
    observed_bands = [
        (band.get("id"), float(band.get("minimum")), float(band.get("maximum_exclusive")))
        for band in bands
    ]
    if observed_bands != expected_bands:
        raise GenerationError("As tres faixas de distancia divergem do protocolo congelado.")

    buffer_inputs = config.get("buffer_inputs") or {}
    if float(buffer_inputs.get("base_radius_m")) != 2000.0:
        raise GenerationError("base_radius_m deve permanecer em 2000 m.")
    if buffer_inputs.get("r0_semantics") != "nominal_base":
        raise GenerationError("r0_semantics deve permanecer nominal_base.")
    if buffer_inputs.get("factors_applied") not in ("", None):
        raise GenerationError("factors_applied deve permanecer vazio.")
    if buffer_inputs.get("position_dispersion_m") not in ("", None):
        raise GenerationError("position_dispersion_m deve permanecer vazio.")

    blind_schema = list(config.get("blind_output_schema") or [])
    forbidden = list(config.get("blind_forbidden_column_fragments") or [])
    violations = forbidden_headers(blind_schema, forbidden)
    if violations:
        raise GenerationError(f"Schema cego contem colunas proibidas: {', '.join(violations)}")


def forbidden_headers(headers: Iterable[str], forbidden_fragments: Sequence[str]) -> list[str]:
    violations: list[str] = []
    for header in headers:
        folded_header = fold_text(str(header))
        if any(fold_text(fragment) in folded_header for fragment in forbidden_fragments):
            violations.append(str(header))
    return violations


def parse_finite_float(value: Any, field: str, row_number: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise GenerationError(f"Linha {row_number}: {field} nao numerico.") from exc
    if not math.isfinite(number):
        raise GenerationError(f"Linha {row_number}: {field} nao finito.")
    return number


def environment_lookup(config: Mapping[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for label, canonical in (config.get("environment_mapping") or {}).items():
        mapping[fold_text(normalize_text(label))] = normalize_text(canonical)
        mapping[fold_text(normalize_text(canonical))] = normalize_text(canonical)
    return mapping


def read_reserved_ground_truth(path: Path, config: Mapping[str, Any]) -> list[dict[str, Any]]:
    try:
        stream = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise GenerationError(f"Nao foi possivel abrir o CSV reservado: {path}") from exc
    with stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)):
            raise GenerationError("O CSV reservado possui cabecalhos duplicados.")
        required = list(config["input_required_columns"])
        missing = [field for field in required if field not in headers]
        if missing:
            raise GenerationError(f"Campos obrigatorios ausentes: {', '.join(missing)}")
        raw_rows = list(reader)

    expected_count = int(config["site_count"])
    if len(raw_rows) != expected_count:
        raise GenerationError(f"Esperados {expected_count} sites; encontrados {len(raw_rows)}.")

    environments = environment_lookup(config)
    coordinate_places = int(config["rounding"]["coordinates_decimal_places"])
    rows: list[dict[str, Any]] = []
    for row_number, raw in enumerate(raw_rows, start=2):
        site_id = normalize_text(raw.get("site_id"))
        scenario_id = normalize_text(raw.get("scenario_id"))
        planned_environment = normalize_text(raw.get("planned_environment"))
        if not site_id or not scenario_id or not planned_environment:
            raise GenerationError(
                f"Linha {row_number}: site_id, scenario_id e planned_environment sao obrigatorios."
            )
        latitude = parse_finite_float(raw.get("ground_truth_lat"), "ground_truth_lat", row_number)
        longitude = parse_finite_float(raw.get("ground_truth_lon"), "ground_truth_lon", row_number)
        if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
            raise GenerationError(f"Linha {row_number}: coordenada fora do intervalo WGS84.")
        environment_class = environments.get(fold_text(planned_environment))
        if not environment_class:
            allowed = ", ".join(config["environment_mapping"].keys())
            raise GenerationError(
                f"Linha {row_number}: ambiente planejado invalido; use um de: {allowed}."
            )

        normalized_source = {
            "site_id": site_id,
            "scenario_id": scenario_id,
            "ground_truth_lat": f"{latitude:.{coordinate_places}f}",
            "ground_truth_lon": f"{longitude:.{coordinate_places}f}",
            "planned_environment": planned_environment,
            "environment_class": environment_class,
        }
        rows.append(
            {
                **normalized_source,
                "ground_truth_lat_value": latitude,
                "ground_truth_lon_value": longitude,
            }
        )

    if len({row["site_id"] for row in rows}) != expected_count:
        raise GenerationError("site_id deve ser unico nos quatro registros.")
    if len({row["scenario_id"] for row in rows}) != expected_count:
        raise GenerationError("scenario_id deve ser unico nos quatro registros.")

    if config.get("require_each_planned_environment_once"):
        expected = Counter(config["environment_mapping"].values())
        observed = Counter(row["environment_class"] for row in rows)
        if observed != expected:
            raise GenerationError(
                "Os quatro estratos planejados devem aparecer exatamente uma vez: "
                + ", ".join(expected.keys())
            )

    return sorted(rows, key=lambda row: (row["scenario_id"], row["site_id"]))


def uniform_continuous(rng: Any, minimum: float, maximum_exclusive: float) -> tuple[float, int]:
    value = minimum + (maximum_exclusive - minimum) * rng.next_float()
    return value, int(rng.draw_count)


def uniform_integer_inclusive(rng: Any, minimum: int, maximum: int) -> tuple[int, int]:
    width = maximum - minimum + 1
    value = minimum + min(int(rng.next_float() * width), width - 1)
    return value, int(rng.draw_count)


def permute_bands(rng: Any, bands: Sequence[Mapping[str, Any]]) -> tuple[list[Mapping[str, Any]], list[int]]:
    result = list(bands)
    draw_indices: list[int] = []
    for index in range(len(result) - 1, 0, -1):
        target = min(int(rng.next_float() * (index + 1)), index)
        draw_indices.append(int(rng.draw_count))
        result[index], result[target] = result[target], result[index]
    return result, draw_indices


def destination_point(
    latitude_deg: float,
    longitude_deg: float,
    distance_m: float,
    bearing_deg: float,
    earth_radius_m: float,
) -> tuple[float, float]:
    latitude = math.radians(latitude_deg)
    longitude = math.radians(longitude_deg)
    bearing = math.radians(bearing_deg)
    angular_distance = distance_m / earth_radius_m

    destination_latitude = math.asin(
        math.sin(latitude) * math.cos(angular_distance)
        + math.cos(latitude) * math.sin(angular_distance) * math.cos(bearing)
    )
    destination_longitude = longitude + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(latitude),
        math.cos(angular_distance) - math.sin(latitude) * math.sin(destination_latitude),
    )
    destination_longitude = (destination_longitude + math.pi) % (2 * math.pi) - math.pi
    return math.degrees(destination_latitude), math.degrees(destination_longitude)


def generate_candidates_for_site(
    site: Mapping[str, Any],
    config: Mapping[str, Any],
    rng: Any,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    bands, permutation_draw_indices = permute_bands(rng, config["distance_bands_m"])
    numeric_places = int(config["rounding"]["generated_numeric_decimal_places"])
    coordinate_places = int(config["rounding"]["coordinates_decimal_places"])
    buffer_inputs = config["buffer_inputs"]
    quality_spec = config["detection_quality"]
    age_spec = config["information_age_min"]
    bearing_spec = config["bearing_degrees"]
    protocol_id = str(config["protocol_id"])

    blind_rows: list[dict[str, str]] = []
    secure_rows: list[dict[str, str]] = []
    for slot, band in enumerate(bands, start=1):
        distance, distance_draw_index = uniform_continuous(
            rng, float(band["minimum"]), float(band["maximum_exclusive"])
        )
        bearing, bearing_draw_index = uniform_continuous(
            rng,
            float(bearing_spec["minimum"]),
            float(bearing_spec["maximum_exclusive"]),
        )
        quality, quality_draw_index = uniform_continuous(
            rng,
            float(quality_spec["minimum"]),
            float(quality_spec["maximum_exclusive"]),
        )
        age, age_draw_index = uniform_integer_inclusive(
            rng,
            int(age_spec["minimum"]),
            int(age_spec["maximum_inclusive"]),
        )

        estimated_latitude, estimated_longitude = destination_point(
            float(site["ground_truth_lat_value"]),
            float(site["ground_truth_lon_value"]),
            distance,
            bearing,
            float(config["earth_radius_m"]),
        )
        if not -90.0 <= estimated_latitude <= 90.0 or not -180.0 <= estimated_longitude <= 180.0:
            raise GenerationError("O deslocamento geodesico produziu coordenada invalida.")

        candidate_id = f"{site['scenario_id']}-C{slot}"
        public_candidate_source = {
            "site_id": str(site["site_id"]),
            "scenario_id": str(site["scenario_id"]),
            "candidate_id": candidate_id,
            "candidate_slot": str(slot),
            "partition": str(config["partition"]),
            "estimated_lat": f"{estimated_latitude:.{coordinate_places}f}",
            "estimated_lon": f"{estimated_longitude:.{coordinate_places}f}",
            "base_radius_m": f"{float(buffer_inputs['base_radius_m']):.0f}",
            "r0_semantics": str(buffer_inputs["r0_semantics"]),
            "detection_quality": f"{quality:.{numeric_places}f}",
            "environment_class": str(site["environment_class"]),
            "position_dispersion_m": "",
            "information_age_min": str(age),
            "factors_applied": "",
            "r0_provenance": str(buffer_inputs["r0_provenance"]),
            "data_origin": str(buffer_inputs["data_origin"]),
            "execution_phase": str(config["execution_phase"]),
            "freeze_status": str(config["freeze_status"]),
            "protocol_id": protocol_id,
            "interpretation_boundary": str(config["interpretation_boundary"]),
        }
        source_row_hash = stable_hash(public_candidate_source)
        blind_base = {**public_candidate_source, "source_row_hash": source_row_hash}
        blind_hash = stable_hash(blind_base)
        blind_row = {**blind_base, "blind_row_sha256": blind_hash}
        blind_row = {field: blind_row[field] for field in config["blind_output_schema"]}

        secure_base = {
            "site_id": str(site["site_id"]),
            "scenario_id": str(site["scenario_id"]),
            "ground_truth_lat": str(site["ground_truth_lat"]),
            "ground_truth_lon": str(site["ground_truth_lon"]),
            "planned_environment": str(site["planned_environment"]),
            "environment_class": str(site["environment_class"]),
            "candidate_id": candidate_id,
            "candidate_slot": str(slot),
            "distance_band_generator_only": str(band["id"]),
            "distance_m_generator_only": f"{distance:.{numeric_places}f}",
            "bearing_deg_generator_only": f"{bearing:.{numeric_places}f}",
            "permutation_draw_indices_generator_only": ";".join(
                str(value) for value in permutation_draw_indices
            ),
            "distance_draw_index_generator_only": str(distance_draw_index),
            "bearing_draw_index_generator_only": str(bearing_draw_index),
            "quality_draw_index_generator_only": str(quality_draw_index),
            "age_draw_index_generator_only": str(age_draw_index),
            "estimated_lat": blind_row["estimated_lat"],
            "estimated_lon": blind_row["estimated_lon"],
            "base_radius_m": blind_row["base_radius_m"],
            "r0_semantics": blind_row["r0_semantics"],
            "detection_quality": blind_row["detection_quality"],
            "position_dispersion_m": "",
            "information_age_min": blind_row["information_age_min"],
            "factors_applied": "",
            "r0_provenance": blind_row["r0_provenance"],
            "data_origin": blind_row["data_origin"],
            "source_row_hash": source_row_hash,
            "execution_phase": blind_row["execution_phase"],
            "freeze_status": blind_row["freeze_status"],
            "blind_row_sha256": blind_hash,
            "protocol_id": protocol_id,
        }
        secure_hash = stable_hash(secure_base)
        secure_row = {**secure_base, "secure_row_sha256": secure_hash}
        secure_row = {field: secure_row[field] for field in config["secure_output_schema"]}

        blind_rows.append(blind_row)
        secure_rows.append(secure_row)

    return blind_rows, secure_rows


def csv_bytes(headers: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(headers), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in headers})
    return buffer.getvalue().encode("utf-8")


def validate_blind_rows(rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]) -> None:
    schema = list(config["blind_output_schema"])
    forbidden = list(config["blind_forbidden_column_fragments"])
    violations = forbidden_headers(schema, forbidden)
    if violations:
        raise GenerationError(f"Colunas proibidas vazaram para a saida cega: {', '.join(violations)}")
    for index, row in enumerate(rows, start=2):
        if list(row.keys()) != schema:
            raise GenerationError(f"Linha cega {index}: schema divergente do protocolo.")
        if row.get("position_dispersion_m") != "" or row.get("factors_applied") != "":
            raise GenerationError(f"Linha cega {index}: campos congelados deveriam estar vazios.")
        if row.get("base_radius_m") != "2000" or row.get("r0_semantics") != "nominal_base":
            raise GenerationError(f"Linha cega {index}: semantica de r0 divergente.")


def paths_are_distinct(paths: Sequence[Path]) -> bool:
    normalized = [path.expanduser().resolve() for path in paths]
    return len(normalized) == len(set(normalized))


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            temporary_path.unlink(missing_ok=True)
        finally:
            raise


def run_generator(
    input_gt: Path,
    blind_output: Path,
    secure_output: Path,
    manifest_output: Path,
    config_path: Path = DEFAULT_CONFIG,
    overwrite: bool = False,
) -> dict[str, Any]:
    input_gt = input_gt.expanduser().resolve()
    blind_output = blind_output.expanduser().resolve()
    secure_output = secure_output.expanduser().resolve()
    manifest_output = manifest_output.expanduser().resolve()
    config_path = config_path.expanduser().resolve()

    if blind_output == secure_output:
        raise GenerationError("As saidas cega e segura nao podem usar o mesmo caminho.")
    if not paths_are_distinct(
        [input_gt, config_path, blind_output, secure_output, manifest_output]
    ):
        raise GenerationError(
            "Entrada, configuracao e arquivos de saida devem ter caminhos distintos."
        )
    if not input_gt.is_file():
        raise GenerationError(f"CSV reservado nao encontrado: {input_gt}")
    if not overwrite:
        existing = [path for path in (blind_output, secure_output, manifest_output) if path.exists()]
        if existing:
            raise GenerationError(
                "Saida existente; use --overwrite somente em execucao deliberada: "
                + ", ".join(str(path) for path in existing)
            )

    config, config_sha256 = load_config(config_path)
    sites = read_reserved_ground_truth(input_gt, config)
    rng = XorShift32(int(config["seed"]["uint32"]))

    all_blind_rows: list[dict[str, str]] = []
    all_secure_rows: list[dict[str, str]] = []
    for site in sites:
        blind_rows, secure_rows = generate_candidates_for_site(site, config, rng)
        all_blind_rows.extend(blind_rows)
        all_secure_rows.extend(secure_rows)

    expected_candidates = int(config["site_count"]) * int(config["candidates_per_site"])
    if len(all_blind_rows) != expected_candidates or len(all_secure_rows) != expected_candidates:
        raise GenerationError("Cardinalidade de candidatos divergente do protocolo.")
    if rng.draw_count != int(config["prng"]["expected_total_draws"]):
        raise GenerationError("Quantidade de sorteios divergente do protocolo congelado.")
    validate_blind_rows(all_blind_rows, config)

    blind_payload = csv_bytes(config["blind_output_schema"], all_blind_rows)
    secure_payload = csv_bytes(config["secure_output_schema"], all_secure_rows)
    manifest: dict[str, Any] = {
        "protocol_id": config["protocol_id"],
        "protocol_status": config["status"],
        "freeze_date": config["freeze_date"],
        "validation_modality": config["validation_modality"],
        "config_sha256": config_sha256,
        "seed_material_utf8": config["seed"]["material_utf8"],
        "seed_sha256": config["seed"]["sha256"],
        "seed_uint32": config["seed"]["uint32"],
        "prng_algorithm": config["prng"]["algorithm"],
        "draw_order_per_site": config["prng"]["draw_order_per_site"],
        "draw_count": rng.draw_count,
        "final_prng_state_uint32": rng.state,
        "site_count": len(sites),
        "candidate_count": len(all_blind_rows),
        "candidates_per_site": config["candidates_per_site"],
        "input_ground_truth_csv_sha256": sha256_file(input_gt),
        "blind_output_sha256": sha256_bytes(blind_payload),
        "secure_output_sha256": sha256_bytes(secure_payload),
        "blind_schema": config["blind_output_schema"],
        "secure_schema": config["secure_output_schema"],
        "forbidden_blind_columns_detected": [],
        "ground_truth_used_only_inside_generator": True,
        "ground_truth_used_by_buffer_geo_or_ranking": False,
        "base_radius_m": config["buffer_inputs"]["base_radius_m"],
        "r0_semantics": config["buffer_inputs"]["r0_semantics"],
        "interpretation_boundary": config["interpretation_boundary"],
    }
    manifest["manifest_payload_sha256"] = stable_hash(manifest)
    manifest_payload = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    atomic_write(blind_output, blind_payload)
    atomic_write(secure_output, secure_payload)
    atomic_write(manifest_output, manifest_payload)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gera candidatos semissinteticos cegos do protocolo FIELD-CAND-v1.0."
    )
    parser.add_argument("--input-gt", type=Path, required=True, help="CSV reservado.")
    parser.add_argument("--blind-output", type=Path, required=True, help="CSV para o pipeline cego.")
    parser.add_argument("--secure-output", type=Path, required=True, help="CSV reservado do gerador.")
    parser.add_argument("--manifest-output", type=Path, required=True, help="Manifesto JSON.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Configuracao congelada.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Substitui saidas existentes de forma deliberada; nao altera o protocolo.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = run_generator(
            input_gt=args.input_gt,
            blind_output=args.blind_output,
            secure_output=args.secure_output,
            manifest_output=args.manifest_output,
            config_path=args.config,
            overwrite=args.overwrite,
        )
    except GenerationError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "OK",
                "protocol_id": manifest["protocol_id"],
                "site_count": manifest["site_count"],
                "candidate_count": manifest["candidate_count"],
                "draw_count": manifest["draw_count"],
                "blind_output_sha256": manifest["blind_output_sha256"],
                "secure_output_sha256": manifest["secure_output_sha256"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
