#!/usr/bin/env python3
"""Adaptador auditável PERFIL V2 + TERRITORIAL -> entrada congelada PERFIL V3.

O adaptador nunca completa pistas por inferência. Direções e destinos somente
entram no V3 quando existe uma revisão espacial congelada com os metadados que
faltam no compilado V2. Sem essa revisão, a pista é registrada como excluída.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import math
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import profile_ranker as ranker


ADAPTER_ID = "PERFIL-V3-INTEGRATOR-v1.0"
REVIEW_PROTOCOL = "PERFIL-V3-SPATIAL-REVIEW-v1.0"
REVIEW_FREEZE_PROJECTION_ID = "PERFIL-V3-SPATIAL-REVIEW-FREEZE-v1"
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_GT_KEY_FRAGMENTS = (
    "groundtruth", "truelocation", "truecoordinate", "truelat", "truelon",
    "victimlat", "victimlon", "targetlat", "targetlon", "posicaoverdadeira",
    "posicaoreal", "localizacaoverdadeira", "localizacaoreal", "coordenadareal",
    "latitudereal", "longitudereal", "referenciaverdadeira", "gabarito",
)
_CARDINAL_AZIMUTH = {
    "N": 0.0,
    "NE": 45.0,
    "E": 90.0,
    "SE": 135.0,
    "S": 180.0,
    "SW": 225.0,
    "W": 270.0,
    "NW": 315.0,
}
_CONFIRMATORY_CLASSIFICATIONS = frozenset(
    {"ELEGIVEL_PARA_AVALIACAO_CONFIRMATORIA"}
)
_V2_SCOPE_GUARDS = {
    "ground_truth_firewall_passed": True,
    "unknown_values_create_effect": False,
    "free_text_directly_converted_to_weight": False,
    "suspicion_upgraded_to_confirmation": False,
    "weights_or_ranking_implemented": False,
}
_V2_FIREWALL_POLICY_ID = "PERFIL-V2-GT-FIREWALL-v1.1"
_TERRITORIAL_FIREWALL_SENTINEL = "GROUND_TRUTH_PROHIBITED_AND_NOT_USED"


class IntegrationError(ValueError):
    """Falha de contrato, proveniência ou coerência na integração."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntegrationError(f"Não foi possível ler JSON válido: {path}") from exc


def _parse_datetime(value: Any, path: str) -> datetime:
    if not isinstance(value, str):
        raise IntegrationError(f"{path}: data/hora textual obrigatória.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IntegrationError(f"{path}: data/hora inválida.") from exc
    if parsed.utcoffset() is None:
        raise IntegrationError(f"{path}: fuso horário obrigatório.")
    return parsed


def _identifier(value: Any, path: str) -> str:
    try:
        return ranker._validate_identifier(value, path)  # contrato compartilhado com o V3
    except ranker.InputValidationError as exc:
        raise IntegrationError(str(exc)) from exc


def _sha256(value: Any, path: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise IntegrationError(f"{path}: SHA-256 hexadecimal minúsculo esperado.")
    return value


def _strict_false(value: Any, path: str, *, allow_csv_string: bool = False) -> None:
    if value is False:
        return
    if allow_csv_string and isinstance(value, str) and value.strip().lower() == "false":
        return
    raise IntegrationError(f"{path}: ground_truth_used deve ser false.")


def enforce_source_gt_firewall(
    value: Any,
    path: str = "$",
    *,
    allow_csv_string: bool = False,
    validate_control_values: bool = True,
) -> None:
    """Varrimento de fontes, permitindo apenas os controles negativos oficiais."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = ranker._normalized_key(str(key))
            allowed = {"groundtruthused", "groundtruthabsent", "groundtruthfirewallpassed"}
            if normalized not in allowed and any(
                fragment in normalized for fragment in _FORBIDDEN_GT_KEY_FRAGMENTS
            ):
                raise IntegrationError(f"Chave de referência verdadeira proibida em {path}.{key}.")
            if validate_control_values and normalized == "groundtruthused":
                _strict_false(
                    child, f"{path}.{key}", allow_csv_string=allow_csv_string
                )
            elif validate_control_values and normalized in {
                "groundtruthabsent", "groundtruthfirewallpassed"
            }:
                if child is not True:
                    raise IntegrationError(f"{path}.{key}: controle deve ser true.")
            enforce_source_gt_firewall(
                child,
                f"{path}.{key}",
                allow_csv_string=allow_csv_string,
                validate_control_values=validate_control_values,
            )
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            enforce_source_gt_firewall(
                child,
                f"{path}[{index}]",
                allow_csv_string=allow_csv_string,
                validate_control_values=validate_control_values,
            )
    elif isinstance(value, str) and any(pattern.search(value) for pattern in ranker._FORBIDDEN_TEXT):
        raise IntegrationError(f"Marcador textual de referência verdadeira proibido em {path}.")


def _finite(value: Any, path: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise IntegrationError(f"{path}: número finito esperado.") from exc
    if not math.isfinite(number):
        raise IntegrationError(f"{path}: número finito esperado.")
    return number


def verify_v2_compiled(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise IntegrationError("Compilado V2 deve ser um objeto JSON.")
    enforce_source_gt_firewall(payload, "V2")
    expected = {
        "compiler_id": "PERFIL-V2-QUAL-COMPILER-v1.1",
        "schema_id": "urn:agtu:sar:perfil-vitima:v2-draft-2",
        "source_record_status": "CONGELADO",
        "ground_truth_absent": True,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise IntegrationError(f"Compilado V2: {key} deve ser {value!r}.")
    if payload.get("protocol_version") != "PERFIL-V2-DRAFT.2":
        raise IntegrationError("Compilado V2 usa protocol_version inesperado.")
    if payload.get("mode") != "QUALITATIVO_SEM_PESOS_SEM_RANKING":
        raise IntegrationError("Compilado V2 não comprova modo estritamente qualitativo.")
    input_sha256 = payload.get("input_sha256")
    if not isinstance(input_sha256, str) or not _SHA_RE.fullmatch(input_sha256):
        raise IntegrationError("Compilado V2 sem input_sha256 válido.")
    freeze_validation = payload.get("freeze_validation")
    if (
        not isinstance(freeze_validation, Mapping)
        or set(freeze_validation) != {"projection_id", "status"}
        or freeze_validation.get("projection_id") != "PERFIL-V2-FREEZE-PROJECTION-v1"
        or freeze_validation.get("status") != "VERIFIED"
    ):
        raise IntegrationError("Compilado V2 não comprova validação do congelamento de origem.")
    source_freeze = payload.get("source_freeze_metadata")
    if not isinstance(source_freeze, Mapping):
        raise IntegrationError("Compilado V2 sem source_freeze_metadata.")
    if source_freeze.get("schema_id") != expected["schema_id"]:
        raise IntegrationError("Compilado V2 referencia esquema de congelamento inesperado.")
    if not isinstance(source_freeze.get("payload_sha256"), str) or not _SHA_RE.fullmatch(
        source_freeze["payload_sha256"]
    ):
        raise IntegrationError("Compilado V2 contém hash de congelamento inválido.")
    _parse_datetime(source_freeze.get("frozen_at"), "V2.source_freeze_metadata.frozen_at")
    scope_guards = payload.get("scope_guards")
    if not isinstance(scope_guards, Mapping) or dict(scope_guards) != _V2_SCOPE_GUARDS:
        raise IntegrationError("Compilado V2 não comprova as guardas qualitativas esperadas.")
    firewall_manifest = payload.get("firewall_manifest")
    expected_firewall = {
        "policy_id": _V2_FIREWALL_POLICY_ID,
        "recursive_key_scan": True,
        "forbidden_alias_scan_pt_en": True,
        "explicit_text_marker_scan": True,
        "schema_disallows_free_objects_in_facts": True,
        "text_fields_sanitized_declared": True,
        "status": "PASS",
    }
    if not isinstance(firewall_manifest, Mapping) or dict(firewall_manifest) != expected_firewall:
        raise IntegrationError("Compilado V2 não comprova firewall aprovado e completo.")
    declared = payload.get("compiled_sha256")
    if not isinstance(declared, str) or not _SHA_RE.fullmatch(declared):
        raise IntegrationError("Compilado V2 sem compiled_sha256 válido.")
    projected = deepcopy(payload)
    projected.pop("compiled_sha256", None)
    calculated = ranker.canonical_sha256(projected)
    if not hmac.compare_digest(declared, calculated):
        raise IntegrationError("compiled_sha256 do V2 não confere; arquivo alterado.")
    hypotheses = payload.get("hypotheses")
    if not isinstance(hypotheses, list):
        raise IntegrationError("Compilado V2 sem lista hypotheses.")
    return payload, {
        "file_sha256": file_sha256(path),
        "internal_compiled_sha256": calculated,
        "source_input_sha256": input_sha256,
        "source_frozen_at": source_freeze["frozen_at"],
    }


def review_freeze_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    projected = deepcopy(dict(payload))
    metadata = projected.get("freeze_metadata")
    if not isinstance(metadata, Mapping):
        raise IntegrationError("Revisão espacial sem freeze_metadata.")
    projected["freeze_metadata"] = dict(metadata)
    projected["freeze_metadata"].pop("payload_sha256", None)
    return projected


def calculate_review_freeze_sha256(payload: Mapping[str, Any]) -> str:
    return ranker.canonical_sha256(review_freeze_projection(payload))


def _validate_review_entry(entry: Any, index: int, scenario_id: str, candidate_id: str) -> None:
    path = f"review.entries[{index}]"
    if not isinstance(entry, Mapping):
        raise IntegrationError(f"{path}: objeto esperado.")
    common = {"source_hypothesis_id", "decision", "reviewed_at"}
    if not common.issubset(entry):
        raise IntegrationError(f"{path}: campos comuns ausentes.")
    _identifier(entry["source_hypothesis_id"], f"{path}.source_hypothesis_id")
    _parse_datetime(entry["reviewed_at"], f"{path}.reviewed_at")
    if entry["decision"] == "EXCLUIR":
        allowed = common | {"reason"}
        if (
            set(entry) != allowed
            or not isinstance(entry.get("reason"), str)
            or not entry["reason"].strip()
            or len(entry["reason"]) > 300
        ):
            raise IntegrationError(f"{path}: exclusão exige somente reason textual não vazio.")
        return
    if entry["decision"] != "INCLUIR":
        raise IntegrationError(f"{path}.decision: use INCLUIR ou EXCLUIR.")
    family = entry.get("family")
    if family == "DIRECAO":
        allowed = common | {"family", "origin_candidate_id", "spatial_source"}
        if set(entry) != allowed:
            raise IntegrationError(f"{path}: campos inválidos para DIRECAO.")
        if entry.get("origin_candidate_id") != candidate_id:
            raise IntegrationError(f"{path}: direção deve partir do candidate_id da integração.")
    elif family == "DESTINO":
        allowed = common | {
            "family", "hypothesis_type", "location_uncertainty_m", "spatial_source"
        }
        if set(entry) != allowed:
            raise IntegrationError(f"{path}: campos inválidos para DESTINO.")
        if entry.get("hypothesis_type") not in {"DESTINO_DECLARADO", "LUGAR_FAMILIAR"}:
            raise IntegrationError(f"{path}.hypothesis_type: tipo não permitido.")
        uncertainty = _finite(entry.get("location_uncertainty_m"), f"{path}.location_uncertainty_m")
        if uncertainty < 0:
            raise IntegrationError(f"{path}.location_uncertainty_m: valor negativo.")
    else:
        raise IntegrationError(f"{path}.family: família não permitida.")
    source = entry.get("spatial_source")
    if not isinstance(source, str) or not source.strip() or len(source) > 256:
        raise IntegrationError(f"{path}.spatial_source: texto de 1 a 256 caracteres esperado.")


def validate_spatial_review(payload: Mapping[str, Any]) -> None:
    ranker.enforce_ground_truth_firewall(payload)
    keys = {
        "protocol_version", "scenario_id", "candidate_id", "record_status", "created_at",
        "ground_truth_absent", "source_profile_file_sha256",
        "source_territorial_manifest_sha256", "reviewer_code", "entries", "freeze_metadata"
    }
    if set(payload) != keys:
        raise IntegrationError("Revisão espacial contém campos ausentes ou extras.")
    if payload["protocol_version"] != REVIEW_PROTOCOL:
        raise IntegrationError("Versão inesperada da revisão espacial.")
    scenario_id = _identifier(payload["scenario_id"], "review.scenario_id")
    candidate_id = _identifier(payload["candidate_id"], "review.candidate_id")
    _identifier(payload["reviewer_code"], "review.reviewer_code")
    created = _parse_datetime(payload["created_at"], "review.created_at")
    if payload["ground_truth_absent"] is not True:
        raise IntegrationError("review.ground_truth_absent deve ser true.")
    for key in ("source_profile_file_sha256", "source_territorial_manifest_sha256"):
        if not isinstance(payload[key], str) or not _SHA_RE.fullmatch(payload[key]):
            raise IntegrationError(f"review.{key}: SHA-256 hexadecimal minúsculo esperado.")
    entries = payload["entries"]
    if not isinstance(entries, list) or len(entries) > 100:
        raise IntegrationError("review.entries deve ser lista com até 100 itens.")
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        _validate_review_entry(entry, index, scenario_id, candidate_id)
        reviewed = _parse_datetime(entry["reviewed_at"], f"review.entries[{index}].reviewed_at")
        if reviewed < created:
            raise IntegrationError("reviewed_at não pode anteceder created_at da revisão.")
        hypothesis_id = entry["source_hypothesis_id"]
        if hypothesis_id in seen:
            raise IntegrationError("Revisão espacial repete source_hypothesis_id.")
        seen.add(hypothesis_id)
    status = payload["record_status"]
    metadata = payload["freeze_metadata"]
    if status == "RASCUNHO":
        if metadata is not None:
            raise IntegrationError("Revisão RASCUNHO deve manter freeze_metadata=null.")
        return
    if status != "CONGELADO" or not isinstance(metadata, Mapping):
        raise IntegrationError("Revisão deve ser RASCUNHO ou CONGELADO verificável.")
    if set(metadata) != {"frozen_at", "projection_id", "payload_sha256"}:
        raise IntegrationError("freeze_metadata da revisão contém campos ausentes ou extras.")
    frozen = _parse_datetime(metadata["frozen_at"], "review.freeze_metadata.frozen_at")
    if frozen < created:
        raise IntegrationError("Congelamento da revisão não pode anteceder sua criação.")
    for index, entry in enumerate(entries):
        if _parse_datetime(entry["reviewed_at"], f"review.entries[{index}].reviewed_at") > frozen:
            raise IntegrationError("reviewed_at não pode ser posterior ao congelamento.")
    if metadata["projection_id"] != REVIEW_FREEZE_PROJECTION_ID:
        raise IntegrationError("Projeção de congelamento da revisão é inesperada.")
    declared = metadata["payload_sha256"]
    if not isinstance(declared, str) or not _SHA_RE.fullmatch(declared):
        raise IntegrationError("Hash de congelamento da revisão inválido.")
    if not hmac.compare_digest(declared, calculate_review_freeze_sha256(payload)):
        raise IntegrationError("Hash da revisão espacial não confere; pacote alterado.")


def prepare_frozen_review(payload: Mapping[str, Any], frozen_at: str) -> dict[str, Any]:
    if payload.get("record_status") != "RASCUNHO":
        raise IntegrationError("Somente revisão RASCUNHO pode ser congelada.")
    validate_spatial_review(payload)
    _parse_datetime(frozen_at, "--frozen-at")
    frozen = deepcopy(dict(payload))
    frozen["record_status"] = "CONGELADO"
    frozen["freeze_metadata"] = {
        "frozen_at": frozen_at,
        "projection_id": REVIEW_FREEZE_PROJECTION_ID,
        "payload_sha256": "0" * 64,
    }
    frozen["freeze_metadata"]["payload_sha256"] = calculate_review_freeze_sha256(frozen)
    validate_spatial_review(frozen)
    return frozen


def _manifest_entry_for(path: Path, digest: str, files: Sequence[Any], role: str) -> Mapping[str, Any]:
    matches: list[Mapping[str, Any]] = []
    for item in files:
        if not isinstance(item, Mapping) or item.get("role") != role:
            continue
        declared_path = item.get("path")
        if item.get("sha256") != digest or not isinstance(declared_path, str):
            continue
        if Path(declared_path).name == path.name or Path(declared_path).resolve() == path.resolve():
            matches.append(item)
    if len(matches) != 1:
        raise IntegrationError(
            f"Manifesto territorial deve identificar exatamente uma vez {path.name} como {role}."
        )
    return matches[0]


def verify_territorial_manifest(
    manifest_path: Path, ranking_path: Path, polygons_path: Path, buffers_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise IntegrationError("Manifesto territorial deve ser objeto JSON.")
    _strict_false(manifest.get("ground_truth_used"), "manifest.ground_truth_used")
    firewall = manifest.get("firewall")
    if firewall != _TERRITORIAL_FIREWALL_SENTINEL:
        raise IntegrationError("Manifesto territorial não declara firewall de ground truth.")
    manifest_for_scan = deepcopy(manifest)
    manifest_for_scan.pop("firewall", None)
    enforce_source_gt_firewall(manifest_for_scan, "manifest")
    if not isinstance(manifest.get("protocol_id"), str) or not manifest["protocol_id"].strip():
        raise IntegrationError("Manifesto territorial sem protocol_id.")
    generated = _parse_datetime(manifest.get("generated_at_utc"), "manifest.generated_at_utc")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise IntegrationError("Manifesto territorial sem lista files.")
    ranking_digest = file_sha256(ranking_path)
    polygons_digest = file_sha256(polygons_path)
    buffers_digest = file_sha256(buffers_path)
    _manifest_entry_for(ranking_path, ranking_digest, files, "output")
    _manifest_entry_for(polygons_path, polygons_digest, files, "output")
    _manifest_entry_for(buffers_path, buffers_digest, files, "input_buffer_json")
    return manifest, {
        "manifest_file_sha256": file_sha256(manifest_path),
        "ranking_file_sha256": ranking_digest,
        "polygons_file_sha256": polygons_digest,
        "buffers_file_sha256": buffers_digest,
        "generated_at": generated.isoformat(),
    }


def load_authoritative_candidate(
    buffers_path: Path, scenario_id: str, candidate_id: str
) -> dict[str, Any]:
    payload = _load_json(buffers_path)
    if not isinstance(payload, Mapping):
        raise IntegrationError("JSON autoritativo de buffers deve ser objeto.")
    enforce_source_gt_firewall(payload, "buffers")
    _strict_false(payload.get("ground_truth_used"), "buffers.ground_truth_used")
    results = payload.get("results")
    if not isinstance(results, list):
        raise IntegrationError("JSON autoritativo de buffers sem results.")
    matches: list[Mapping[str, Any]] = []
    for index, item in enumerate(results):
        if not isinstance(item, Mapping):
            raise IntegrationError(f"buffers.results[{index}]: objeto esperado.")
        if item.get("scenario_id") == scenario_id and item.get("candidate_id") == candidate_id:
            _strict_false(item.get("ground_truth_used"), f"buffers.results[{index}].ground_truth_used")
            matches.append(item)
    if len(matches) != 1:
        raise IntegrationError("JSON de buffers deve conter exatamente um cenário/candidato solicitado.")
    item = matches[0]
    lat = _finite(item.get("estimated_lat"), "buffer.estimated_lat")
    lon = _finite(item.get("estimated_lon"), "buffer.estimated_lon")
    if not -90 < lat < 90 or not -180 <= lon <= 180:
        raise IntegrationError("Centro autoritativo do candidato fora do WGS 84.")
    source_row_hash = item.get("source_row_hash")
    if not isinstance(source_row_hash, str) or not _SHA_RE.fullmatch(source_row_hash):
        raise IntegrationError("Buffer autoritativo sem source_row_hash válido.")
    classification = item.get("execution_classification")
    if not isinstance(classification, str) or not classification.strip():
        raise IntegrationError("Buffer autoritativo sem execution_classification.")
    if not isinstance(item.get("confirmatory_eligible"), bool):
        raise IntegrationError("Buffer autoritativo sem confirmatory_eligible booleano.")
    return {
        "latitude": lat,
        "longitude": lon,
        "source_row_hash": source_row_hash,
        "execution_classification": classification,
        "confirmatory_eligible": item.get("confirmatory_eligible") is True,
        "protocol_id": item.get("protocol_id"),
    }


def _unwrap_ring(ring: Sequence[Sequence[float]]) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    for lon_raw, lat_raw in ring:
        lon = float(lon_raw)
        if result:
            while lon - result[-1][0] > 180:
                lon -= 360
            while lon - result[-1][0] < -180:
                lon += 360
        result.append((lon, float(lat_raw)))
    return result


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> int:
    value = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if math.isclose(value, 0.0, rel_tol=0.0, abs_tol=1e-14):
        return 0
    return 1 if value > 0 else -1


def _on_segment(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> bool:
    return (
        min(a[0], b[0]) - 1e-14 <= p[0] <= max(a[0], b[0]) + 1e-14
        and min(a[1], b[1]) - 1e-14 <= p[1] <= max(a[1], b[1]) + 1e-14
        and _orientation(a, b, p) == 0
    )


def _segments_intersect(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]
) -> bool:
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    return (
        (o1 == 0 and _on_segment(a, b, c))
        or (o2 == 0 and _on_segment(a, b, d))
        or (o3 == 0 and _on_segment(c, d, a))
        or (o4 == 0 and _on_segment(c, d, b))
    )


def validate_simple_polygon(ring: Any, path: str) -> list[list[float]]:
    try:
        validated = ranker._validate_polygon(ring, path)
    except ranker.InputValidationError as exc:
        raise IntegrationError(str(exc)) from exc
    points = _unwrap_ring(validated)
    if len(set(points[:-1])) != len(points) - 1:
        raise IntegrationError(f"{path}: vértice repetido fora do fechamento.")
    edge_count = len(points) - 1
    for i in range(edge_count):
        for j in range(i + 1, edge_count):
            if j == i + 1 or (i == 0 and j == edge_count - 1):
                continue
            if _segments_intersect(points[i], points[i + 1], points[j], points[j + 1]):
                raise IntegrationError(f"{path}: polígono auto-intersectante.")
    return validated


def load_territorial_sectors(
    ranking_path: Path,
    polygons_path: Path,
    scenario_id: str,
    candidate_id: str,
    candidate_meta: Mapping[str, Any],
    territorial_protocol_id: str,
    expected_sector_count: int,
) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, str]] = {}
    with ranking_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {
            "scenario_id", "candidate_id", "sector_id", "score_base", "priority_score",
            "azimuth_start_deg", "azimuth_end_deg", "ground_truth_used", "protocol_id",
            "source_buffer_geometry_sha256", "source_row_hash", "source_execution_classification"
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise IntegrationError("CSV territorial não contém todas as colunas obrigatórias.")
        enforce_source_gt_firewall(
            {field_name: None for field_name in reader.fieldnames},
            "ranking cabeçalho",
            validate_control_values=False,
        )
        for line_number, row in enumerate(reader, start=2):
            enforce_source_gt_firewall(
                row, f"ranking linha {line_number}", allow_csv_string=True
            )
            if row["scenario_id"] != scenario_id or row["candidate_id"] != candidate_id:
                continue
            _strict_false(
                row["ground_truth_used"],
                f"ranking linha {line_number}.ground_truth_used",
                allow_csv_string=True,
            )
            if row["protocol_id"] != territorial_protocol_id:
                raise IntegrationError("CSV territorial usa protocol_id divergente do manifesto.")
            if row["source_row_hash"] != candidate_meta["source_row_hash"]:
                raise IntegrationError("CSV territorial diverge do source_row_hash do buffer autoritativo.")
            if row["source_execution_classification"] != candidate_meta["execution_classification"]:
                raise IntegrationError("CSV territorial diverge da classificação do buffer autoritativo.")
            sector_id = _identifier(row["sector_id"], f"ranking linha {line_number}.sector_id")
            if sector_id in rows:
                raise IntegrationError(f"CSV territorial repete sector_id {sector_id}.")
            score = _finite(row["score_base"], f"ranking linha {line_number}.score_base")
            priority = _finite(row["priority_score"], f"ranking linha {line_number}.priority_score")
            if not 0 <= score <= 1 or not math.isclose(score, priority, abs_tol=1e-12):
                raise IntegrationError("score_base inválido ou divergente de priority_score.")
            rows[sector_id] = row
    if len(rows) != expected_sector_count or len(rows) < 2:
        raise IntegrationError(
            f"Integração esperava {expected_sector_count} setores e encontrou {len(rows)}."
        )

    geojson = _load_json(polygons_path)
    if not isinstance(geojson, Mapping) or geojson.get("type") != "FeatureCollection":
        raise IntegrationError("GeoJSON territorial deve ser FeatureCollection.")
    _strict_false(geojson.get("ground_truth_used"), "geojson.ground_truth_used")
    enforce_source_gt_firewall(geojson, "geojson")
    features = geojson.get("features")
    if not isinstance(features, list):
        raise IntegrationError("GeoJSON territorial sem features.")
    relevant: dict[str, Mapping[str, Any]] = {}
    for index, feature in enumerate(features):
        if not isinstance(feature, Mapping):
            raise IntegrationError(f"GeoJSON feature {index}: objeto esperado.")
        props = feature.get("properties")
        if not isinstance(props, Mapping):
            raise IntegrationError(f"GeoJSON feature {index}: properties ausente.")
        if props.get("scenario_id") != scenario_id or props.get("candidate_id") != candidate_id:
            continue
        _strict_false(props.get("ground_truth_used"), f"geojson feature {index}.ground_truth_used")
        if props.get("protocol_id") != territorial_protocol_id:
            raise IntegrationError("GeoJSON territorial usa protocol_id divergente do manifesto.")
        if props.get("source_row_hash") != candidate_meta["source_row_hash"]:
            raise IntegrationError("GeoJSON territorial diverge do source_row_hash do buffer autoritativo.")
        if props.get("source_execution_classification") != candidate_meta["execution_classification"]:
            raise IntegrationError("GeoJSON territorial diverge da classificação do buffer autoritativo.")
        sector_id = _identifier(props.get("sector_id"), f"geojson feature {index}.sector_id")
        if feature.get("id") != sector_id:
            raise IntegrationError(f"GeoJSON feature {index}: id diverge de sector_id.")
        if sector_id in relevant:
            raise IntegrationError(f"GeoJSON repete sector_id {sector_id}.")
        relevant[sector_id] = feature
    if set(rows) != set(relevant):
        raise IntegrationError("Conjuntos de setores do CSV e do GeoJSON divergem.")

    sectors: list[dict[str, Any]] = []
    for sector_id in sorted(rows):
        row = rows[sector_id]
        feature = relevant[sector_id]
        props = feature["properties"]
        geometry = feature.get("geometry")
        if not isinstance(geometry, Mapping) or geometry.get("type") != "Polygon":
            raise IntegrationError(f"{sector_id}: somente Polygon simples é aceito.")
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) != 1:
            raise IntegrationError(f"{sector_id}: polígonos com buracos não são aceitos.")
        ring = validate_simple_polygon(coordinates[0], f"{sector_id}.polygon")
        score = _finite(row["score_base"], f"{sector_id}.score_base")
        start = _finite(row["azimuth_start_deg"], f"{sector_id}.azimuth_start_deg")
        end = _finite(row["azimuth_end_deg"], f"{sector_id}.azimuth_end_deg")
        for field, csv_value, property_name in (
            ("score", score, "score_base"),
            ("start", start, "azimuth_start_deg"),
            ("end", end, "azimuth_end_deg"),
        ):
            geo_value = _finite(props.get(property_name), f"{sector_id}.properties.{property_name}")
            if not math.isclose(csv_value, geo_value, abs_tol=1e-9):
                raise IntegrationError(f"{sector_id}: {field} diverge entre CSV e GeoJSON.")
        if row["source_buffer_geometry_sha256"] != props.get("source_buffer_geometry_sha256"):
            raise IntegrationError(f"{sector_id}: hash da geometria de buffer diverge entre fontes.")
        sectors.append(
            {
                "sector_id": sector_id,
                "territorial_score": score,
                "bearing_start_deg": start,
                "bearing_end_deg": end,
                "polygon": ring,
            }
        )
    return sectors


def _single_support(hypothesis: Mapping[str, Any]) -> Mapping[str, Any]:
    supports = hypothesis.get("supports")
    if not isinstance(supports, list) or len(supports) != 1 or not isinstance(supports[0], Mapping):
        raise IntegrationError(
            f"{hypothesis.get('hypothesis_id')}: inclusão exige exatamente um suporte V2 inequívoco."
        )
    support = supports[0]
    if support.get("authorized_for_model") is not True:
        raise IntegrationError(f"{hypothesis.get('hypothesis_id')}: suporte não autorizado.")
    return support


def map_hypotheses(
    compiled: Mapping[str, Any],
    review: Mapping[str, Any] | None,
    scenario_id: str,
    candidate_id: str,
    candidate_meta: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    review_by_id: dict[str, Mapping[str, Any]] = {}
    if review is not None:
        if review["scenario_id"] != scenario_id or review["candidate_id"] != candidate_id:
            raise IntegrationError("Revisão espacial não corresponde ao cenário/candidato.")
        review_by_id = {entry["source_hypothesis_id"]: entry for entry in review["entries"]}
    source_by_id: dict[str, Mapping[str, Any]] = {}
    for item in compiled["hypotheses"]:
        if not isinstance(item, Mapping):
            raise IntegrationError("Hipótese V2 inválida.")
        hypothesis_id = _identifier(item.get("hypothesis_id"), "V2.hypothesis_id")
        if hypothesis_id in source_by_id:
            raise IntegrationError("Compilado V2 repete hypothesis_id.")
        source_by_id[hypothesis_id] = item
    unknown_reviews = sorted(set(review_by_id) - set(source_by_id))
    if unknown_reviews:
        raise IntegrationError("Revisão referencia hipótese V2 inexistente: " + ", ".join(unknown_reviews))

    included: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for hypothesis_id in sorted(source_by_id):
        source = source_by_id[hypothesis_id]
        if source.get("hypothesis_type") not in {"DIRECAO_OBSERVADA", "DESTINO_OU_LUGAR_FAMILIAR"}:
            continue
        entry = review_by_id.get(hypothesis_id)
        if entry is None:
            excluded.append({"source_hypothesis_id": hypothesis_id, "reason": "SEM_REVISAO_ESPACIAL_CONGELADA"})
            continue
        if entry["decision"] == "EXCLUIR":
            excluded.append({"source_hypothesis_id": hypothesis_id, "reason": entry["reason"]})
            continue
        if source.get("spatialized") is not True or source.get("spatial_status") != "ESPACIALIZADA":
            raise IntegrationError(f"{hypothesis_id}: revisão tentou incluir hipótese V2 não espacializada.")
        support = _single_support(source)
        nature, confidence = support.get("nature"), support.get("confidence")
        if nature not in ranker._NATURE_FACTOR or confidence not in ranker._CONFIDENCE_FACTOR:
            raise IntegrationError(f"{hypothesis_id}: natureza ou confiança inválida.")
        source_clue_id = source.get("source_clue_id")
        evidence_group_id = _identifier(source_clue_id, f"{hypothesis_id}.source_clue_id")
        common = {
            "hypothesis_id": f"V3-{hypothesis_id}",
            "evidence_group_id": evidence_group_id,
            "spatialized": True,
            "authorized_for_model": True,
            "nature": nature,
            "confidence": confidence,
        }
        if source["hypothesis_type"] == "DIRECAO_OBSERVADA":
            if entry.get("family") != "DIRECAO":
                raise IntegrationError(f"{hypothesis_id}: revisão usa família incompatível.")
            data = source.get("direction_data")
            if not isinstance(data, Mapping):
                raise IntegrationError(f"{hypothesis_id}: direction_data ausente.")
            azimuth = data.get("azimuth_deg")
            if azimuth is None:
                azimuth = _CARDINAL_AZIMUTH.get(data.get("cardinal_direction"))
            azimuth = _finite(azimuth, f"{hypothesis_id}.azimuth")
            tolerance = _finite(data.get("angular_tolerance_deg"), f"{hypothesis_id}.tolerance")
            origin = source.get("associated_location")
            if not isinstance(origin, Mapping):
                excluded.append(
                    {"source_hypothesis_id": hypothesis_id, "reason": "ORIGEM_DIRECAO_SEM_COORDENADA"}
                )
                continue
            try:
                origin_lat = _finite(origin.get("latitude"), f"{hypothesis_id}.origin.latitude")
                origin_lon = _finite(origin.get("longitude"), f"{hypothesis_id}.origin.longitude")
            except IntegrationError:
                excluded.append(
                    {"source_hypothesis_id": hypothesis_id, "reason": "ORIGEM_DIRECAO_SEM_COORDENADA"}
                )
                continue
            if origin_lat != float(candidate_meta["latitude"]) or origin_lon != float(
                candidate_meta["longitude"]
            ):
                excluded.append(
                    {"source_hypothesis_id": hypothesis_id, "reason": "ORIGEM_DIRECAO_DIVERGE_DO_CANDIDATO"}
                )
                continue
            included.append(
                {
                    **common,
                    "family": "DIRECAO",
                    "hypothesis_type": "DIRECAO_OBSERVADA",
                    "direction": {
                        "origin_candidate_id": candidate_id,
                        "azimuth_deg": azimuth,
                        "tolerance_deg": tolerance,
                    },
                }
            )
        else:
            if entry.get("family") != "DESTINO":
                raise IntegrationError(f"{hypothesis_id}: revisão usa família incompatível.")
            location = source.get("associated_location")
            if not isinstance(location, Mapping):
                raise IntegrationError(f"{hypothesis_id}: associated_location ausente.")
            latitude = _finite(location.get("latitude"), f"{hypothesis_id}.latitude")
            longitude = _finite(location.get("longitude"), f"{hypothesis_id}.longitude")
            included.append(
                {
                    **common,
                    "family": "DESTINO",
                    "hypothesis_type": entry["hypothesis_type"],
                    "destination": {
                        "latitude": latitude,
                        "longitude": longitude,
                        "location_uncertainty_m": float(entry["location_uncertainty_m"]),
                        "spatial_source": entry["spatial_source"],
                    },
                }
            )
    return included, excluded


def build_v3_input(
    *,
    profile_path: Path,
    territorial_manifest_path: Path,
    ranking_path: Path,
    polygons_path: Path,
    buffers_path: Path,
    scenario_id: str,
    candidate_id: str,
    source_loc_input_sha256: str,
    source_case_revision: int,
    created_at: str,
    frozen_at: str,
    spatial_review_path: Path | None = None,
    allow_nonconfirmatory: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    scenario_id = _identifier(scenario_id, "scenario_id")
    candidate_id = _identifier(candidate_id, "candidate_id")
    source_loc_input_sha256 = _sha256(
        source_loc_input_sha256, "source_loc_input_sha256"
    )
    if (
        not isinstance(source_case_revision, int)
        or isinstance(source_case_revision, bool)
        or source_case_revision < 1
    ):
        raise IntegrationError("source_case_revision deve ser inteiro positivo.")
    created = _parse_datetime(created_at, "created_at")
    frozen = _parse_datetime(frozen_at, "frozen_at")
    if frozen < created:
        raise IntegrationError("frozen_at não pode anteceder created_at.")
    compiled, profile_meta = verify_v2_compiled(profile_path)
    if compiled.get("scenario_id") != scenario_id:
        raise IntegrationError("Compilado V2 não corresponde ao scenario_id solicitado.")
    manifest, territorial_meta = verify_territorial_manifest(
        territorial_manifest_path, ranking_path, polygons_path, buffers_path
    )
    candidate_meta = load_authoritative_candidate(buffers_path, scenario_id, candidate_id)
    manifest_classification = manifest.get("execution_classification")
    if not isinstance(manifest_classification, str) or not manifest_classification.strip():
        raise IntegrationError("Manifesto territorial sem execution_classification.")
    confirmatory = (
        candidate_meta["confirmatory_eligible"] is True
        and candidate_meta["execution_classification"] in _CONFIRMATORY_CLASSIFICATIONS
        and manifest_classification in _CONFIRMATORY_CLASSIFICATIONS
    )
    nonconfirmatory = not confirmatory
    if nonconfirmatory and not allow_nonconfirmatory:
        raise IntegrationError(
            "Pacote territorial não confirmatório; use autorização explícita apenas para ensaio diagnóstico."
        )
    source_times = [
        _parse_datetime(profile_meta["source_frozen_at"], "V2.frozen_at"),
        _parse_datetime(territorial_meta["generated_at"], "territorial.generated_at"),
    ]
    review: Mapping[str, Any] | None = None
    review_meta: dict[str, Any] | None = None
    if spatial_review_path is not None:
        loaded = _load_json(spatial_review_path)
        if not isinstance(loaded, Mapping):
            raise IntegrationError("Revisão espacial deve ser objeto JSON.")
        validate_spatial_review(loaded)
        if loaded["record_status"] != "CONGELADO":
            raise IntegrationError("Somente revisão espacial CONGELADA pode incluir pistas.")
        review = loaded
        if loaded["source_profile_file_sha256"] != profile_meta["file_sha256"]:
            raise IntegrationError("Revisão espacial não está vinculada ao arquivo V2 usado.")
        if loaded["source_territorial_manifest_sha256"] != territorial_meta["manifest_file_sha256"]:
            raise IntegrationError("Revisão espacial não está vinculada ao manifesto territorial usado.")
        review_meta = {
            "file_sha256": file_sha256(spatial_review_path),
            "payload_sha256": loaded["freeze_metadata"]["payload_sha256"],
            "frozen_at": loaded["freeze_metadata"]["frozen_at"],
        }
        source_times.append(_parse_datetime(review_meta["frozen_at"], "review.frozen_at"))
        if _parse_datetime(loaded["created_at"], "review.created_at") < max(source_times[:2]):
            raise IntegrationError("Revisão espacial foi criada antes dos artefatos que declara revisar.")
    if created < max(source_times):
        raise IntegrationError("created_at da integração não pode anteceder os artefatos de origem.")

    sector_count = manifest.get("sectors_per_buffer")
    if not isinstance(sector_count, int) or sector_count < 2:
        raise IntegrationError("Manifesto territorial sem sectors_per_buffer válido.")
    sectors = load_territorial_sectors(
        ranking_path,
        polygons_path,
        scenario_id,
        candidate_id,
        candidate_meta,
        str(manifest["protocol_id"]),
        sector_count,
    )
    hypotheses, exclusions = map_hypotheses(
        compiled, review, scenario_id, candidate_id, candidate_meta
    )
    draft = {
        "protocol_version": "PERFIL-V3-QUANT-v1.0",
        "scenario_id": scenario_id,
        "candidate_id": candidate_id,
        "record_status": "RASCUNHO",
        "created_at": created_at,
        "ground_truth_absent": True,
        "source_loc_input_sha256": source_loc_input_sha256,
        "source_case_revision": source_case_revision,
        "source_profile_compiled_sha256": profile_meta["file_sha256"],
        "source_territorial_manifest_sha256": territorial_meta["manifest_file_sha256"],
        "source_spatial_review_sha256": (
            review_meta["file_sha256"] if review_meta is not None else None
        ),
        "sectors": sectors,
        "hypotheses": hypotheses,
        "freeze_metadata": None,
    }
    result = ranker.prepare_frozen_input(draft, frozen_at)
    report: dict[str, Any] = {
        "adapter_id": ADAPTER_ID,
        "status": "PASS",
        "scenario_id": scenario_id,
        "candidate_id": candidate_id,
        "source_loc_input_sha256": source_loc_input_sha256,
        "source_case_revision": source_case_revision,
        "ground_truth_absent": True,
        "source_profile": {"path": str(profile_path), **profile_meta},
        "source_territorial": {
            "manifest_path": str(territorial_manifest_path),
            "ranking_path": str(ranking_path),
            "polygons_path": str(polygons_path),
            "buffers_path": str(buffers_path),
            "protocol_id": manifest["protocol_id"],
            "execution_classification": candidate_meta["execution_classification"],
            "manifest_execution_classification": manifest_classification,
            "confirmatory_eligible": candidate_meta["confirmatory_eligible"],
            "confirmatory_policy_allowlist": sorted(_CONFIRMATORY_CLASSIFICATIONS),
            "confirmatory_package": confirmatory,
            "nonconfirmatory_explicitly_allowed": bool(nonconfirmatory and allow_nonconfirmatory),
            **territorial_meta,
        },
        "source_spatial_review": (
            {"path": str(spatial_review_path), **review_meta} if review_meta is not None else None
        ),
        "sector_count": len(sectors),
        "included_hypothesis_ids": [item["hypothesis_id"] for item in hypotheses],
        "excluded_spatial_hypotheses": exclusions,
        "v3_input_payload_sha256": result["freeze_metadata"]["payload_sha256"],
        "topology_checks": {
            "closed": True,
            "positive_area": True,
            "simple_no_self_intersection": True,
            "holes_absent": True,
        },
    }
    report["report_sha256"] = ranker.canonical_sha256(report)
    return result, report


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ranker.canonical_json_bytes(value))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze = subparsers.add_parser("freeze-review", help="Congela revisão espacial em arquivo separado.")
    freeze.add_argument("--input", required=True, type=Path)
    freeze.add_argument("--frozen-at", required=True)
    freeze.add_argument("--output", required=True, type=Path)
    build = subparsers.add_parser("build", help="Constrói entrada V3 congelada e relatório de integração.")
    build.add_argument("--profile", required=True, type=Path)
    build.add_argument("--territorial-manifest", required=True, type=Path)
    build.add_argument("--ranking", required=True, type=Path)
    build.add_argument("--polygons", required=True, type=Path)
    build.add_argument("--buffers", required=True, type=Path)
    build.add_argument("--spatial-review", type=Path)
    build.add_argument("--scenario-id", required=True)
    build.add_argument("--candidate-id", required=True)
    build.add_argument("--source-loc-input-sha256", required=True)
    build.add_argument("--source-case-revision", required=True, type=int)
    build.add_argument("--created-at", required=True)
    build.add_argument("--frozen-at", required=True)
    build.add_argument("--output", required=True, type=Path)
    build.add_argument("--report", required=True, type=Path)
    build.add_argument(
        "--allow-nonconfirmatory",
        action="store_true",
        help="Permite somente ensaio diagnóstico e registra a condição no relatório.",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "freeze-review":
        if args.input.resolve() == args.output.resolve():
            raise IntegrationError("A revisão congelada deve ser gravada em arquivo diferente.")
        payload = _load_json(args.input)
        if not isinstance(payload, Mapping):
            raise IntegrationError("Revisão espacial deve ser objeto JSON.")
        _write_json(args.output, prepare_frozen_review(payload, args.frozen_at))
        return 0
    if args.output.resolve() == args.report.resolve():
        raise IntegrationError("Entrada V3 e relatório devem usar arquivos diferentes.")
    result, report = build_v3_input(
        profile_path=args.profile,
        territorial_manifest_path=args.territorial_manifest,
        ranking_path=args.ranking,
        polygons_path=args.polygons,
        buffers_path=args.buffers,
        spatial_review_path=args.spatial_review,
        scenario_id=args.scenario_id,
        candidate_id=args.candidate_id,
        source_loc_input_sha256=args.source_loc_input_sha256,
        source_case_revision=args.source_case_revision,
        created_at=args.created_at,
        frozen_at=args.frozen_at,
        allow_nonconfirmatory=args.allow_nonconfirmatory,
    )
    _write_json(args.output, result)
    _write_json(args.report, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
