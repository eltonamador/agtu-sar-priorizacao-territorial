#!/usr/bin/env python3
"""Metadados visuais e vínculo espacial externo ao motor LOC.

O módulo produz dois artefatos determinísticos, ambos posteriores ao
congelamento do caso. Ele não altera o caso, não altera o resultado LOC e não
recebe ground truth. A associação visual--setor é sempre recalculada a partir
dos bytes da imagem, de metadados técnicos em lista branca e dos polígonos do
resultado LOC validado.
"""

from __future__ import annotations

import argparse
import hmac
import json
import math
import re
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import integrated_protocol as protocol


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "outputs" / "protocolo_integrado_v1" / "visual_spatial_policy_v1.json"
SWIFT_HELPER_PATH = Path(__file__).resolve().with_name("extract_image_metadata.swift")
SWIFT_EXECUTABLE = Path("/usr/bin/swift")
SWIFT_MODULE_CACHE = Path("/tmp/agtu-swift-module-cache")

INSPECTION_VERSION = "VISUAL-FILE-INSPECTION-v1"
MANIFEST_CONTRACT_VERSION = "VISUAL-METADATA-MANIFEST-v1"
BINDING_CONTRACT_VERSION = "VISUAL-SECTOR-BINDING-v1"
EXTRACTOR_ID = "IMAGEIO-WHITELIST-v1"
BINDING_ENGINE_ID = "VISUAL-SPATIAL-BINDER-v1"
CONTEXTUAL_METHOD = "CONTEXTUAL_NO_AUTOMATIC_FOOTPRINT-v1"

DECODED = "PIXELS_DECODED_AND_DIMENSIONS_VALIDATED"
STRUCTURAL_ONLY = "CONTAINER_STRUCTURE_ONLY"
NOT_DECODED = "PIXELS_NOT_DECODED"

APPROXIMATE = "APROXIMADO_METADADOS"
CALIBRATED = "VERIFICADO_CALIBRADO"
CONTEXTUAL = "CONTEXTUAL_INSUFICIENTE"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_EXIF_DATETIME_RE = re.compile(
    r"^(?P<year>\d{4}):(?P<month>\d{2}):(?P<day>\d{2})[ T]"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})$"
)
_OFFSET_RE = re.compile(r"^[+-](?:0\d|1[0-4]):[0-5]\d$")


def _policy() -> tuple[dict[str, Any], str]:
    try:
        value = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise protocol.InputValidationError(
            "A política visual-espacial não pôde ser carregada."
        ) from exc
    required = {
        "policy_id", "footprint_method", "automatic_platforms",
        "required_lens_direction", "operator_nadir_allows_approximate_footprint",
        "metadata_gimbal_pitch_required", "metadata_gimbal_pitch_is_discriminant",
        "gps_consistency_tolerance_m", "agl_minimum_m", "agl_maximum_m",
        "agl_absolute_tolerance_m", "agl_relative_tolerance_fraction",
        "capture_time_tolerance_seconds", "focal_35mm_minimum_mm",
        "focal_35mm_maximum_mm", "maximum_footprint_radius_m",
        "footprint_vertices", "calibrated_camera_profiles",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise protocol.InputValidationError(
            "A política visual-espacial não corresponde ao contrato v1."
        )
    if value["policy_id"] != "VISUAL-SPATIAL-POLICY-v1":
        raise protocol.InputValidationError("policy_id visual-espacial inesperado.")
    if value["footprint_method"] != "NADIR_CONSERVATIVE_CIRCULAR_FOOTPRINT-v1":
        raise protocol.InputValidationError("Método de footprint não autorizado.")
    if value["required_lens_direction"] != "NADIR":
        raise protocol.InputValidationError("Direção exigida pela política deve ser NADIR.")
    if value["operator_nadir_allows_approximate_footprint"] is not True:
        raise protocol.InputValidationError("A política não autoriza footprint aproximado NADIR.")
    if value["metadata_gimbal_pitch_required"] is not False:
        raise protocol.InputValidationError("Pitch DJI não pode ser requisito nesta política.")
    if value["metadata_gimbal_pitch_is_discriminant"] is not False:
        raise protocol.InputValidationError("Pitch DJI não pode ser discriminante nesta política.")
    if not isinstance(value["automatic_platforms"], list) or not value["automatic_platforms"]:
        raise protocol.InputValidationError("automatic_platforms inválido.")
    numeric_positive = (
        "gps_consistency_tolerance_m", "agl_minimum_m", "agl_maximum_m",
        "agl_absolute_tolerance_m", "agl_relative_tolerance_fraction",
        "capture_time_tolerance_seconds", "focal_35mm_minimum_mm",
        "focal_35mm_maximum_mm", "maximum_footprint_radius_m",
    )
    for key in numeric_positive:
        item = value[key]
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)) or float(item) <= 0:
            raise protocol.InputValidationError(f"Política visual: {key} deve ser positivo.")
    vertices = value["footprint_vertices"]
    if isinstance(vertices, bool) or not isinstance(vertices, int) or not 8 <= vertices <= 360:
        raise protocol.InputValidationError("footprint_vertices deve estar entre 8 e 360.")
    if not isinstance(value["calibrated_camera_profiles"], list):
        raise protocol.InputValidationError("calibrated_camera_profiles deve ser lista.")
    return value, protocol.canonical_sha256(value)


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _bounded_text(value: Any, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed[:maximum] if trimmed else None


def _number_field(
    source: Mapping[str, Any], key: str, *, minimum: float | None = None,
    maximum: float | None = None, exclusive_minimum: bool = False,
    exclusive_maximum: bool = False,
) -> float | None:
    value = _finite_number(source.get(key))
    if value is None:
        return None
    if minimum is not None and (value <= minimum if exclusive_minimum else value < minimum):
        return None
    if maximum is not None and (value >= maximum if exclusive_maximum else value > maximum):
        return None
    return value


def _normalize_metadata(raw: Any) -> tuple[dict[str, Any], int | None, int | None]:
    if not isinstance(raw, Mapping):
        return {}, None, None
    width_value = raw.get("pixel_width")
    height_value = raw.get("pixel_height")
    width = width_value if isinstance(width_value, int) and not isinstance(width_value, bool) and width_value > 0 else None
    height = height_value if isinstance(height_value, int) and not isinstance(height_value, bool) and height_value > 0 else None
    result: dict[str, Any] = {}

    camera_raw = raw.get("camera")
    if isinstance(camera_raw, Mapping):
        camera = {
            key: item
            for key in ("make", "model", "software")
            if (item := _bounded_text(camera_raw.get(key), 256)) is not None
        }
        if camera:
            result["camera"] = camera

    timestamps_raw = raw.get("timestamps")
    if isinstance(timestamps_raw, Mapping):
        maximums = {
            "datetime_original": 64,
            "datetime_digitized": 64,
            "datetime_tiff": 64,
            "offset_time_original": 16,
            "subsec_time_original": 32,
        }
        timestamps = {
            key: item
            for key, maximum in maximums.items()
            if (item := _bounded_text(timestamps_raw.get(key), maximum)) is not None
        }
        if timestamps:
            result["timestamps"] = timestamps

    gps_raw = raw.get("gps")
    if isinstance(gps_raw, Mapping):
        gps: dict[str, Any] = {}
        latitude = _number_field(gps_raw, "latitude", minimum=-90, maximum=90)
        longitude = _number_field(gps_raw, "longitude", minimum=-180, maximum=180)
        altitude = _number_field(gps_raw, "altitude_m")
        h_error = _number_field(gps_raw, "horizontal_positioning_error_m", minimum=0)
        direction = _number_field(gps_raw, "image_direction_deg", minimum=0, maximum=360, exclusive_maximum=True)
        for key, item in (
            ("latitude", latitude), ("longitude", longitude),
            ("altitude_m", altitude),
            ("horizontal_positioning_error_m", h_error),
            ("image_direction_deg", direction),
        ):
            if item is not None:
                gps[key] = item
        for key, allowed, maximum in (
            ("latitude_ref", {"N", "S"}, 1),
            ("longitude_ref", {"E", "W"}, 1),
        ):
            item = _bounded_text(gps_raw.get(key), maximum)
            if item is not None and item.upper() in allowed:
                gps[key] = item.upper()
        for key, maximum in (
            ("date_stamp", 32), ("time_stamp", 64), ("image_direction_ref", 16),
        ):
            item = _bounded_text(gps_raw.get(key), maximum)
            if item is not None:
                gps[key] = item
        altitude_ref = gps_raw.get("altitude_ref")
        if isinstance(altitude_ref, (str, int, float)) and not isinstance(altitude_ref, bool):
            if not isinstance(altitude_ref, float) or math.isfinite(altitude_ref):
                gps["altitude_ref"] = altitude_ref
        if gps:
            result["gps"] = gps

    orientation_raw = raw.get("orientation")
    if isinstance(orientation_raw, Mapping):
        item = orientation_raw.get("exif_orientation")
        if isinstance(item, int) and not isinstance(item, bool) and 1 <= item <= 8:
            result["orientation"] = {"exif_orientation": item}

    optics_raw = raw.get("optics")
    if isinstance(optics_raw, Mapping):
        optics = {}
        for key in ("focal_length_mm", "focal_length_35mm"):
            item = _number_field(optics_raw, key, minimum=0, exclusive_minimum=True)
            if item is not None:
                optics[key] = item
        if optics:
            result["optics"] = optics

    dji_raw = raw.get("dji_xmp")
    if isinstance(dji_raw, Mapping):
        dji = {}
        ranges: dict[str, tuple[float | None, float | None]] = {
            "absolute_altitude_m": (None, None),
            "relative_altitude_m": (None, None),
            "gimbal_pitch_deg": (-180, 180),
            "gimbal_yaw_deg": (-360, 360),
            "gimbal_roll_deg": (-180, 180),
            "flight_pitch_deg": (-180, 180),
            "flight_yaw_deg": (-360, 360),
            "flight_roll_deg": (-180, 180),
            "gps_latitude": (-90, 90),
            "gps_longitude": (-180, 180),
        }
        for key, (minimum, maximum) in ranges.items():
            item = _number_field(dji_raw, key, minimum=minimum, maximum=maximum)
            if item is not None:
                dji[key] = item
        if dji:
            result["dji_xmp"] = dji
    return result, width, height


def _structural_fallback(path: Path, media_type: str, error_code: str) -> dict[str, Any]:
    try:
        protocol._validate_visual_media_signature(path, media_type)
    except (OSError, protocol.ProtocolError):
        status = NOT_DECODED
        failure = "CONTAINER_INVALID_OR_UNSUPPORTED"
    else:
        status = STRUCTURAL_ONLY
        failure = error_code
    return {
        "inspection_version": INSPECTION_VERSION,
        "decode_status": status,
        "pixel_width": None,
        "pixel_height": None,
        "metadata": {},
        "inspection_error": failure,
    }


def inspect_visual_file(path: Path | str, media_type: str) -> dict[str, Any]:
    """Decodifica pixels e devolve apenas metadados técnicos autorizados."""
    source = Path(path)
    if media_type not in {"IMAGE_JPEG", "IMAGE_HEIC", "IMAGE_PNG", "VIDEO"}:
        raise protocol.InputValidationError("media_type visual inválido.")
    if not source.is_file():
        raise protocol.InputValidationError("Arquivo visual não encontrado.")
    if media_type == "VIDEO":
        return _structural_fallback(source, media_type, "VIDEO_SEM_DECODIFICACAO_IMAGEIO")
    if not SWIFT_EXECUTABLE.is_file() or not SWIFT_HELPER_PATH.is_file():
        return _structural_fallback(source, media_type, "IMAGEIO_HELPER_INDISPONIVEL")
    try:
        completed = subprocess.run(
            [
                str(SWIFT_EXECUTABLE),
                "-module-cache-path", str(SWIFT_MODULE_CACHE),
                str(SWIFT_HELPER_PATH), str(source),
            ],
            check=False,
            capture_output=True,
            timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired):
        return _structural_fallback(source, media_type, "IMAGEIO_EXECUCAO_FALHOU")
    if completed.returncode != 0:
        return _structural_fallback(source, media_type, "IMAGEIO_NAO_DECODIFICOU_PIXELS")
    try:
        decoded = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _structural_fallback(source, media_type, "IMAGEIO_SAIDA_INVALIDA")
    if (
        not isinstance(decoded, Mapping)
        or decoded.get("contract_version") != EXTRACTOR_ID
        or decoded.get("status") != "OK"
        or decoded.get("decode_status") != DECODED
    ):
        return _structural_fallback(source, media_type, "IMAGEIO_CONTRATO_INVALIDO")
    metadata, width, height = _normalize_metadata(decoded.get("metadata"))
    if width is None or height is None:
        return _structural_fallback(source, media_type, "IMAGEIO_DIMENSOES_INVALIDAS")
    return {
        "inspection_version": INSPECTION_VERSION,
        "decode_status": DECODED,
        "pixel_width": width,
        "pixel_height": height,
        "metadata": metadata,
        "inspection_error": None,
    }


def _resolve_visual_paths(
    payload: Mapping[str, Any], artifact_map: Mapping[str, Any], artifact_root: Path | str,
) -> dict[str, Path]:
    protocol.enforce_ground_truth_firewall(artifact_map, "$artifact_map")
    if not isinstance(artifact_map, Mapping):
        raise protocol.InputValidationError("artifact_map deve ser objeto.")
    expected = {f"visual:{item['visual_id']}" for item in payload["visual_evidence"]}
    supplied_visual = {str(key) for key in artifact_map if str(key).startswith("visual:")}
    if supplied_visual != expected:
        missing = sorted(expected - supplied_visual)
        extras = sorted(supplied_visual - expected)
        raise protocol.InputValidationError(
            f"artifact_map visual divergente; ausentes={missing}; extras={extras}."
        )
    root = Path(artifact_root).resolve()
    if not root.is_dir():
        raise protocol.InputValidationError("artifact_root deve ser diretório existente.")
    resolved: dict[str, Path] = {}
    for binding_id in sorted(expected):
        relative = artifact_map[binding_id]
        if not isinstance(relative, str) or not relative.strip():
            raise protocol.InputValidationError(
                f"artifact_map.{binding_id}: caminho relativo textual esperado."
            )
        candidate_relative = Path(relative)
        if candidate_relative.is_absolute():
            raise protocol.InputValidationError(
                f"artifact_map.{binding_id}: caminho absoluto não permitido."
            )
        candidate = (root / candidate_relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise protocol.InputValidationError(
                f"artifact_map.{binding_id}: caminho sai da raiz autorizada."
            ) from exc
        if not candidate.is_file():
            raise protocol.InputValidationError(
                f"artifact_map.{binding_id}: arquivo não encontrado."
            )
        resolved[binding_id] = candidate
    return resolved


def _operator_record(visual: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "platform", "capture_at", "capture_time_precision", "capture_time_source",
        "camera_position_relative_to_point", "lens_aim_direction_cardinal",
        "lens_aim_azimuth_deg", "altitude_agl_m", "altitude_agl_source",
        "authorized_for_context",
    )
    return {key: deepcopy(visual[key]) for key in keys}


def _coordinate_pair(metadata: Mapping[str, Any], source: str) -> tuple[float, float] | None:
    if source == "EXIF":
        container = metadata.get("gps")
        lat_key, lon_key = "latitude", "longitude"
    else:
        container = metadata.get("dji_xmp")
        lat_key, lon_key = "gps_latitude", "gps_longitude"
    if not isinstance(container, Mapping):
        return None
    latitude = _finite_number(container.get(lat_key))
    longitude = _finite_number(container.get(lon_key))
    if latitude is None or longitude is None or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return latitude, longitude


def _haversine_m(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, first)
    lat2, lon2 = map(math.radians, second)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 6_371_008.8 * 2 * math.asin(min(1.0, math.sqrt(a)))


def _metadata_capture_datetime(
    metadata: Mapping[str, Any], operator_at: datetime | None,
) -> tuple[datetime | None, list[str]]:
    warnings: list[str] = []
    gps = metadata.get("gps")
    if isinstance(gps, Mapping):
        date_stamp = gps.get("date_stamp")
        time_stamp = gps.get("time_stamp")
        if isinstance(date_stamp, str) and isinstance(time_stamp, str):
            normalized_date = date_stamp.replace(":", "-")
            try:
                parsed = datetime.fromisoformat(f"{normalized_date}T{time_stamp}")
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed, warnings
            except ValueError:
                warnings.append("HORARIO_GPS_NAO_INTERPRETAVEL")
    timestamps = metadata.get("timestamps")
    if not isinstance(timestamps, Mapping):
        return None, warnings
    raw = timestamps.get("datetime_original")
    if not isinstance(raw, str):
        raw = timestamps.get("datetime_digitized")
    if not isinstance(raw, str):
        raw = timestamps.get("datetime_tiff")
    if not isinstance(raw, str):
        return None, warnings
    match = _EXIF_DATETIME_RE.fullmatch(raw.strip())
    if match is None:
        warnings.append("HORARIO_EXIF_NAO_INTERPRETAVEL")
        return None, warnings
    base = datetime(**{key: int(value) for key, value in match.groupdict().items()})
    subsec = timestamps.get("subsec_time_original")
    if isinstance(subsec, str) and subsec.isdigit():
        base = base.replace(microsecond=int((subsec + "000000")[:6]))
    offset = timestamps.get("offset_time_original")
    if isinstance(offset, str) and _OFFSET_RE.fullmatch(offset):
        try:
            return datetime.fromisoformat(base.isoformat() + offset), warnings
        except ValueError:
            warnings.append("FUSO_EXIF_NAO_INTERPRETAVEL")
    if operator_at is not None and operator_at.tzinfo is not None:
        warnings.append("FUSO_EXIF_INFERIDO_DO_OPERADOR")
        return base.replace(tzinfo=operator_at.tzinfo), warnings
    warnings.append("FUSO_EXIF_AUSENTE")
    return None, warnings


def _conflict(code: str, field: str, operator_value: Any, metadata_value: Any) -> dict[str, Any]:
    def scalar(value: Any) -> Any:
        if value is None or isinstance(value, (str, bool)):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
            return value
        return str(value)
    return {
        "code": code,
        "field": field,
        "operator_value": scalar(operator_value),
        "metadata_value": scalar(metadata_value),
    }


def _analyze_record(
    operator: Mapping[str, Any], inspection: Mapping[str, Any], policy: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    metadata = inspection["metadata"]
    conflicts: list[dict[str, Any]] = []
    warnings: list[str] = []
    exif_gps = _coordinate_pair(metadata, "EXIF")
    dji_gps = _coordinate_pair(metadata, "DJI")
    if exif_gps is not None and dji_gps is not None:
        separation = _haversine_m(exif_gps, dji_gps)
        if separation > float(policy["gps_consistency_tolerance_m"]):
            conflicts.append(_conflict(
                "GPS_EXIF_DJI_DIVERGENTE", "gps",
                f"{exif_gps[0]:.8f},{exif_gps[1]:.8f}",
                f"{dji_gps[0]:.8f},{dji_gps[1]:.8f}",
            ))
    elif exif_gps is None and dji_gps is None:
        warnings.append("GPS_METADADO_AUSENTE")
    elif exif_gps is None:
        warnings.append("GPS_APENAS_DJI_XMP")
    else:
        warnings.append("GPS_APENAS_EXIF")

    dji = metadata.get("dji_xmp")
    relative_altitude = dji.get("relative_altitude_m") if isinstance(dji, Mapping) else None
    operator_altitude = operator.get("altitude_agl_m")
    relative_number = _finite_number(relative_altitude)
    operator_number = _finite_number(operator_altitude)
    if relative_number is None:
        warnings.append("ALTITUDE_RELATIVA_DJI_AUSENTE")
    if operator_number is None:
        warnings.append("ALTITUDE_AGL_OPERADOR_AUSENTE")
    if relative_number is not None and operator_number is not None:
        tolerance = max(
            float(policy["agl_absolute_tolerance_m"]),
            abs(operator_number) * float(policy["agl_relative_tolerance_fraction"]),
        )
        if abs(relative_number - operator_number) > tolerance:
            conflicts.append(_conflict(
                "ALTITUDE_AGL_DIVERGENTE", "altitude_agl_m",
                operator_number, relative_number,
            ))

    if isinstance(dji, Mapping) and "gimbal_pitch_deg" in dji:
        warnings.append("PITCH_DJI_REGISTRADO_NAO_DISCRIMINANTE")
    if operator.get("lens_aim_direction_cardinal") != "NADIR":
        warnings.append("ORIENTACAO_NAO_NADIR")

    operator_at: datetime | None = None
    if isinstance(operator.get("capture_at"), str):
        try:
            operator_at = datetime.fromisoformat(operator["capture_at"].replace("Z", "+00:00"))
        except ValueError:
            operator_at = None
    metadata_at, time_warnings = _metadata_capture_datetime(metadata, operator_at)
    warnings.extend(time_warnings)
    if operator.get("capture_time_source") == "METADADO_ARQUIVO" and metadata_at is None:
        conflicts.append(_conflict(
            "HORARIO_METADADO_AUSENTE", "capture_at", operator.get("capture_at"), None,
        ))
    elif operator_at is not None and metadata_at is not None:
        delta_seconds = abs((operator_at - metadata_at).total_seconds())
        if delta_seconds > float(policy["capture_time_tolerance_seconds"]):
            if operator.get("capture_time_precision") == "EXATA":
                conflicts.append(_conflict(
                    "HORARIO_OPERADOR_METADADO_DIVERGENTE", "capture_at",
                    operator.get("capture_at"), metadata_at.isoformat(),
                ))
            else:
                warnings.append("HORARIO_APROXIMADO_DIVERGENTE")
    if inspection["decode_status"] != DECODED:
        warnings.append("PIXELS_NAO_DECODIFICADOS")
    return (
        sorted(conflicts, key=lambda item: (item["code"], item["field"])),
        sorted(set(warnings)),
    )


def _with_self_hash(value: Mapping[str, Any], field: str = "output_sha256") -> dict[str, Any]:
    result = deepcopy(dict(value))
    result.pop(field, None)
    result[field] = protocol.canonical_sha256(result)
    return result


def _case_payload_sha(payload: Mapping[str, Any]) -> str:
    metadata = payload.get("freeze_metadata")
    if not isinstance(metadata, Mapping):
        raise protocol.InputValidationError("Caso sem metadados de congelamento.")
    value = metadata.get("payload_sha256")
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise protocol.InputValidationError("Hash do caso congelado inválido.")
    return value


def extract_visual_metadata_manifest(
    payload: Mapping[str, Any], artifact_map: Mapping[str, Any], artifact_root: Path | str,
) -> dict[str, Any]:
    """Extrai um manifesto determinístico dos arquivos ligados ao caso."""
    protocol.validate_case(payload)
    if payload["record_status"] != "CONGELADO":
        raise protocol.InputValidationError("O manifesto visual exige caso congelado.")
    protocol.enforce_ground_truth_firewall(payload)
    policy, policy_sha = _policy()
    resolved = _resolve_visual_paths(payload, artifact_map, artifact_root)
    records: list[dict[str, Any]] = []
    for visual in sorted(payload["visual_evidence"], key=lambda item: item["visual_id"]):
        path = resolved[f"visual:{visual['visual_id']}"]
        actual_sha = protocol.file_sha256(path)
        if not hmac.compare_digest(actual_sha, visual["file_sha256"]):
            raise protocol.InputValidationError(
                f"Arquivo de {visual['visual_id']} não confere com o hash congelado."
            )
        inspection = inspect_visual_file(path, visual["media_type"])
        operator = _operator_record(visual)
        conflicts, warnings = _analyze_record(operator, inspection, policy)
        record = {
            "visual_id": visual["visual_id"],
            "file_sha256": actual_sha,
            "media_type": visual["media_type"],
            "operator_record": operator,
            "inspection": inspection,
            "conflicts": conflicts,
            "warnings": warnings,
        }
        record["record_sha256"] = protocol.canonical_sha256(record)
        records.append(record)
    manifest = {
        "manifest_contract_version": MANIFEST_CONTRACT_VERSION,
        "extractor_id": EXTRACTOR_ID,
        "policy_id": policy["policy_id"],
        "policy_sha256": policy_sha,
        "scenario_id": payload["scenario_id"],
        "case_revision": payload["case_revision"],
        "source_case_payload_sha256": _case_payload_sha(payload),
        "ground_truth_used": False,
        "records": records,
    }
    manifest = _with_self_hash(manifest)
    protocol.enforce_ground_truth_firewall(manifest)
    return manifest


def _validate_manifest(payload: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    protocol.enforce_ground_truth_firewall(manifest)
    policy, policy_sha = _policy()
    keys = {
        "manifest_contract_version", "extractor_id", "policy_id", "policy_sha256",
        "scenario_id", "case_revision", "source_case_payload_sha256",
        "ground_truth_used", "records", "output_sha256",
    }
    if not isinstance(manifest, Mapping) or set(manifest) != keys:
        raise protocol.InputValidationError("Manifesto visual não corresponde ao contrato v1.")
    expected_header = {
        "manifest_contract_version": MANIFEST_CONTRACT_VERSION,
        "extractor_id": EXTRACTOR_ID,
        "policy_id": policy["policy_id"],
        "policy_sha256": policy_sha,
        "scenario_id": payload["scenario_id"],
        "case_revision": payload["case_revision"],
        "source_case_payload_sha256": _case_payload_sha(payload),
        "ground_truth_used": False,
    }
    for key, expected in expected_header.items():
        if manifest.get(key) != expected:
            raise protocol.InputValidationError(f"Manifesto visual diverge em {key}.")
    records = manifest.get("records")
    if not isinstance(records, list):
        raise protocol.InputValidationError("Manifesto visual: records deve ser lista.")
    case_visuals = {item["visual_id"]: item for item in payload["visual_evidence"]}
    if [item.get("visual_id") for item in records if isinstance(item, Mapping)] != sorted(case_visuals):
        raise protocol.InputValidationError("Manifesto visual não contém exatamente os visuais do caso.")
    record_keys = {
        "visual_id", "file_sha256", "media_type", "operator_record", "inspection",
        "conflicts", "warnings", "record_sha256",
    }
    for index, record in enumerate(records):
        if not isinstance(record, Mapping) or set(record) != record_keys:
            raise protocol.InputValidationError(f"Manifesto records[{index}] inválido.")
        visual = case_visuals[record["visual_id"]]
        if record["file_sha256"] != visual["file_sha256"] or record["media_type"] != visual["media_type"]:
            raise protocol.InputValidationError(f"Manifesto records[{index}] diverge do caso.")
        if record["operator_record"] != _operator_record(visual):
            raise protocol.InputValidationError(f"Manifesto records[{index}] altera o registro do operador.")
        projected = deepcopy(dict(record))
        declared_record_sha = projected.pop("record_sha256")
        if not isinstance(declared_record_sha, str) or not hmac.compare_digest(
            declared_record_sha, protocol.canonical_sha256(projected)
        ):
            raise protocol.InputValidationError(f"Manifesto records[{index}] foi alterado.")
    projected_manifest = deepcopy(dict(manifest))
    declared_sha = projected_manifest.pop("output_sha256")
    if not isinstance(declared_sha, str) or not hmac.compare_digest(
        declared_sha, protocol.canonical_sha256(projected_manifest)
    ):
        raise protocol.InputValidationError("Hash do manifesto visual não confere.")


def _validate_loc_result(payload: Mapping[str, Any], loc_result: Mapping[str, Any]) -> str:
    protocol.enforce_ground_truth_firewall(loc_result, "$loc_result")
    if not isinstance(loc_result, Mapping) or not isinstance(loc_result.get("profile_runs"), list):
        raise protocol.InputValidationError("Resultado LOC não corresponde ao envelope esperado.")
    rebuilt = protocol.build_loc_result_envelope(payload, loc_result["profile_runs"])
    if protocol.canonical_json_bytes(rebuilt) != protocol.canonical_json_bytes(loc_result):
        raise protocol.InputValidationError("Resultado LOC diverge da reexecução autorizada.")
    loc_sha = protocol.canonical_sha256(loc_result)
    declared = payload["source_artifacts"].get("loc_result_sha256")
    if not isinstance(declared, str) or not hmac.compare_digest(declared, loc_sha):
        raise protocol.InputValidationError("Hash do resultado LOC não confere com o caso congelado.")
    return loc_sha


def _sector_polygons(loc_result: Mapping[str, Any]) -> dict[str, list[list[float]]]:
    result: dict[str, list[list[float]]] = {}
    for run in loc_result["profile_runs"]:
        valid_ids = {
            row["sector_id"]
            for row in run["profile_result"]["operational_rows"]
        }
        for sector in run["profile_input"]["sectors"]:
            sector_id = sector["sector_id"]
            if sector_id not in valid_ids:
                continue
            ring = [[float(point[0]), float(point[1])] for point in sector["polygon"]]
            if sector_id in result:
                raise protocol.InputValidationError(f"Setor LOC duplicado: {sector_id}.")
            result[sector_id] = ring
    return result


def _circle_footprint(
    latitude: float, longitude: float, radius_m: float, vertices: int,
) -> dict[str, Any] | None:
    if abs(latitude) >= 89.9:
        return None
    earth_radius = 6_371_008.8
    angular = radius_m / earth_radius
    lat1 = math.radians(latitude)
    lon1 = math.radians(longitude)
    ring: list[list[float]] = []
    for index in range(vertices):
        bearing = 2 * math.pi * index / vertices
        lat2 = math.asin(
            math.sin(lat1) * math.cos(angular)
            + math.cos(lat1) * math.sin(angular) * math.cos(bearing)
        )
        lon2 = lon1 + math.atan2(
            math.sin(bearing) * math.sin(angular) * math.cos(lat1),
            math.cos(angular) - math.sin(lat1) * math.sin(lat2),
        )
        lon_deg = (math.degrees(lon2) + 540.0) % 360.0 - 180.0
        ring.append([round(lon_deg, 10), round(math.degrees(lat2), 10)])
    ring.append(list(ring[0]))
    return {"type": "Polygon", "coordinates": [ring]}


def _rings_intersect(first: Sequence[Sequence[float]], second: Sequence[Sequence[float]]) -> bool:
    if any(protocol._point_in_ring(point, second) for point in first[:-1]):
        return True
    if any(protocol._point_in_ring(point, first) for point in second[:-1]):
        return True
    return any(
        protocol._segments_intersect(first[index], first[index + 1], second[other], second[other + 1])
        for index in range(len(first) - 1)
        for other in range(len(second) - 1)
    )


def _camera_is_calibrated(metadata: Mapping[str, Any], policy: Mapping[str, Any]) -> bool:
    camera = metadata.get("camera")
    if not isinstance(camera, Mapping):
        return False
    make = camera.get("make")
    model = camera.get("model")
    for profile in policy["calibrated_camera_profiles"]:
        if not isinstance(profile, Mapping):
            continue
        calibration_sha = profile.get("calibration_sha256")
        if (
            profile.get("verified") is True
            and profile.get("make") == make
            and profile.get("model") == model
            and isinstance(calibration_sha, str)
            and _SHA_RE.fullmatch(calibration_sha)
        ):
            return True
    return False


def _contextual_binding(record: Mapping[str, Any], reasons: Sequence[str]) -> dict[str, Any]:
    return {
        "visual_id": record["visual_id"],
        "file_sha256": record["file_sha256"],
        "metadata_record_sha256": record["record_sha256"],
        "quality": CONTEXTUAL,
        "method": CONTEXTUAL_METHOD,
        "spatially_qualified": False,
        "footprint_radius_m": None,
        "footprint_geojson": None,
        "applicable_sector_ids": [],
        "reason_codes": sorted(set(reasons)) or ["METADADOS_INSUFICIENTES"],
    }


def _build_record_binding(
    record: Mapping[str, Any], sectors: Mapping[str, list[list[float]]], policy: Mapping[str, Any],
) -> dict[str, Any]:
    operator = record["operator_record"]
    inspection = record["inspection"]
    metadata = inspection["metadata"]
    reasons: list[str] = []
    if operator["platform"] not in policy["automatic_platforms"]:
        reasons.append("PLATAFORMA_CONTEXTUAL")
    if operator["lens_aim_direction_cardinal"] != policy["required_lens_direction"]:
        reasons.append("CAPTURA_OBLIQUA_OU_DIRECAO_INSUFICIENTE")
    if operator["authorized_for_context"] is not True:
        reasons.append("USO_CONTEXTUAL_NAO_AUTORIZADO")
    if inspection["decode_status"] != DECODED or inspection["pixel_width"] is None or inspection["pixel_height"] is None:
        reasons.append("PIXELS_NAO_DECODIFICADOS")
    spatial_conflicts = {
        "GPS_EXIF_DJI_DIVERGENTE", "ALTITUDE_AGL_DIVERGENTE",
        "HORARIO_METADADO_AUSENTE", "HORARIO_OPERADOR_METADADO_DIVERGENTE",
    }
    if any(item["code"] in spatial_conflicts for item in record["conflicts"]):
        reasons.append("CONFLITO_METADADOS_RELEVANTE")

    exif_gps = _coordinate_pair(metadata, "EXIF")
    dji_gps = _coordinate_pair(metadata, "DJI")
    coordinate = exif_gps or dji_gps
    if coordinate is None:
        reasons.append("GPS_METADADO_INSUFICIENTE")

    dji = metadata.get("dji_xmp")
    relative_altitude = (
        _finite_number(dji.get("relative_altitude_m"))
        if isinstance(dji, Mapping) else None
    )
    operator_altitude = _finite_number(operator.get("altitude_agl_m"))
    if relative_altitude is None or relative_altitude <= 0:
        reasons.append("ALTITUDE_RELATIVA_DJI_INSUFICIENTE")
    if operator_altitude is None:
        reasons.append("ALTITUDE_AGL_OPERADOR_INSUFICIENTE")
    elif not float(policy["agl_minimum_m"]) <= operator_altitude <= float(policy["agl_maximum_m"]):
        reasons.append("ALTITUDE_AGL_FORA_DA_POLITICA")

    optics = metadata.get("optics")
    focal_35 = (
        _finite_number(optics.get("focal_length_35mm"))
        if isinstance(optics, Mapping) else None
    )
    if focal_35 is None or not float(policy["focal_35mm_minimum_mm"]) <= focal_35 <= float(policy["focal_35mm_maximum_mm"]):
        reasons.append("FOCAL_35MM_INSUFICIENTE")
    if reasons:
        return _contextual_binding(record, reasons)

    assert coordinate is not None and operator_altitude is not None and focal_35 is not None
    full_frame_diagonal_mm = math.hypot(36.0, 24.0)
    diagonal_fov = 2.0 * math.atan(full_frame_diagonal_mm / (2.0 * focal_35))
    optical_radius_m = operator_altitude * math.tan(diagonal_fov / 2.0)
    gps_metadata = metadata.get("gps")
    horizontal_error_m = (
        _finite_number(gps_metadata.get("horizontal_positioning_error_m"))
        if isinstance(gps_metadata, Mapping) else None
    )
    radius_m = optical_radius_m + (
        horizontal_error_m if horizontal_error_m is not None and horizontal_error_m >= 0 else 0.0
    )
    if not math.isfinite(radius_m) or radius_m <= 0 or radius_m > float(policy["maximum_footprint_radius_m"]):
        return _contextual_binding(record, ["RAIO_FOOTPRINT_FORA_DA_POLITICA"])
    footprint = _circle_footprint(
        coordinate[0], coordinate[1], radius_m, int(policy["footprint_vertices"]),
    )
    if footprint is None:
        return _contextual_binding(record, ["FOOTPRINT_GEODESICO_NAO_CALCULAVEL"])
    ring = footprint["coordinates"][0]
    applicable = sorted(
        sector_id for sector_id, sector_ring in sectors.items()
        if _rings_intersect(ring, sector_ring)
    )
    calibrated = _camera_is_calibrated(metadata, policy)
    quality = CALIBRATED if calibrated else APPROXIMATE
    result_reasons = [
        "FOOTPRINT_CAMERA_CALIBRADA" if calibrated else "FOOTPRINT_APROXIMADO_METADADOS",
        "ERRO_HORIZONTAL_GPS_INCLUIDO_NO_RAIO" if horizontal_error_m is not None
        else "ERRO_HORIZONTAL_GPS_NAO_DISPONIVEL",
        "ORIENTACAO_NADIR_INFORMADA_PELO_OPERADOR",
        "PITCH_DJI_NAO_UTILIZADO_COMO_DISCRIMINANTE",
    ]
    if not applicable:
        result_reasons.append("SEM_INTERSECAO_COM_SETOR_LOC")
    return {
        "visual_id": record["visual_id"],
        "file_sha256": record["file_sha256"],
        "metadata_record_sha256": record["record_sha256"],
        "quality": quality,
        "method": policy["footprint_method"],
        "spatially_qualified": True,
        "footprint_radius_m": round(radius_m, 6),
        "footprint_geojson": footprint,
        "applicable_sector_ids": applicable,
        "reason_codes": sorted(result_reasons),
    }


def build_visual_sector_binding(
    payload: Mapping[str, Any], loc_result: Mapping[str, Any], manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Recalcula footprints e interseções; não aceita associação manual."""
    protocol.validate_case(payload)
    if payload["record_status"] != "CONGELADO":
        raise protocol.InputValidationError("O vínculo visual exige caso congelado.")
    _validate_manifest(payload, manifest)
    loc_sha = _validate_loc_result(payload, loc_result)
    policy, policy_sha = _policy()
    sectors = _sector_polygons(loc_result)
    bindings = [
        _build_record_binding(record, sectors, policy)
        for record in manifest["records"]
    ]
    output = {
        "binding_contract_version": BINDING_CONTRACT_VERSION,
        "engine_id": BINDING_ENGINE_ID,
        "policy_id": policy["policy_id"],
        "policy_sha256": policy_sha,
        "scenario_id": payload["scenario_id"],
        "case_revision": payload["case_revision"],
        "source_case_payload_sha256": _case_payload_sha(payload),
        "loc_input_sha256": protocol.calculate_loc_input_sha256(payload),
        "loc_result_sha256": loc_sha,
        "metadata_manifest_sha256": manifest["output_sha256"],
        "ground_truth_used": False,
        "affects_loc": False,
        "bindings": bindings,
    }
    output = _with_self_hash(output)
    protocol.enforce_ground_truth_firewall(output)
    return output


def _validate_binding(
    payload: Mapping[str, Any], loc_result: Mapping[str, Any], manifest: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> None:
    protocol.enforce_ground_truth_firewall(binding, "$visual_sector_binding")
    if not isinstance(binding, Mapping):
        raise protocol.InputValidationError("Vínculo visual deve ser objeto.")
    rebuilt = build_visual_sector_binding(payload, loc_result, manifest)
    if protocol.canonical_json_bytes(rebuilt) != protocol.canonical_json_bytes(binding):
        raise protocol.InputValidationError("Vínculo visual diverge da reexecução autorizada.")


def validate_visual_package(
    payload: Mapping[str, Any], loc_result: Mapping[str, Any],
    manifest: Mapping[str, Any], binding: Mapping[str, Any],
    artifact_map: Mapping[str, Any], artifact_root: Path | str,
) -> dict[str, Any]:
    """Reextrai os originais e valida integralmente o pacote visual externo."""
    reextracted = extract_visual_metadata_manifest(payload, artifact_map, artifact_root)
    if protocol.canonical_json_bytes(reextracted) != protocol.canonical_json_bytes(manifest):
        raise protocol.InputValidationError("Manifesto visual diverge da reextração dos originais.")
    _validate_binding(payload, loc_result, manifest, binding)
    verified_pairs: dict[str, str] = {}
    contextual_ids: list[str] = []
    for item in binding["bindings"]:
        if item["quality"] in {APPROXIMATE, CALIBRATED}:
            for sector_id in item["applicable_sector_ids"]:
                verified_pairs[f"{item['visual_id']}::{sector_id}"] = item["quality"]
        else:
            contextual_ids.append(item["visual_id"])
    decoded_ids = [
        record["visual_id"] for record in manifest["records"]
        if record["inspection"]["decode_status"] == DECODED
    ]
    return {
        "status": "VERIFIED",
        "source_case_payload_sha256": _case_payload_sha(payload),
        "loc_result_sha256": binding["loc_result_sha256"],
        "metadata_manifest_sha256": manifest["output_sha256"],
        "visual_sector_binding_sha256": binding["output_sha256"],
        "verified_pairs": dict(sorted(verified_pairs.items())),
        "decoded_visual_ids": sorted(decoded_ids),
        "contextual_visual_ids": sorted(contextual_ids),
        "ground_truth_used": False,
        "affects_loc": False,
    }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise protocol.InputValidationError(f"JSON inválido: {path.name}.") from exc
    if not isinstance(value, dict):
        raise protocol.InputValidationError(f"Objeto JSON esperado: {path.name}.")
    return value


def _write_json(path: Path | None, value: Mapping[str, Any]) -> None:
    data = protocol.canonical_json_bytes(value)
    if path is None:
        print(data.decode("utf-8"), end="")
        return
    try:
        with path.open("xb") as stream:
            stream.write(data)
    except FileExistsError as exc:
        raise protocol.InputValidationError(f"Arquivo de saída já existe: {path}.") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Inspeciona um arquivo visual.")
    inspect.add_argument("--input", required=True, type=Path)
    inspect.add_argument("--media-type", required=True)
    inspect.add_argument("--output", type=Path)
    manifest = commands.add_parser("extract-manifest", help="Gera manifesto visual.")
    manifest.add_argument("--case", required=True, type=Path)
    manifest.add_argument("--artifact-map", required=True, type=Path)
    manifest.add_argument("--artifact-root", required=True, type=Path)
    manifest.add_argument("--output", type=Path)
    binding = commands.add_parser("build-binding", help="Gera vínculo imagem--setor.")
    binding.add_argument("--case", required=True, type=Path)
    binding.add_argument("--loc-result", required=True, type=Path)
    binding.add_argument("--manifest", required=True, type=Path)
    binding.add_argument("--output", type=Path)
    validate = commands.add_parser("validate-package", help="Revalida todo o pacote visual.")
    validate.add_argument("--case", required=True, type=Path)
    validate.add_argument("--loc-result", required=True, type=Path)
    validate.add_argument("--manifest", required=True, type=Path)
    validate.add_argument("--binding", required=True, type=Path)
    validate.add_argument("--artifact-map", required=True, type=Path)
    validate.add_argument("--artifact-root", required=True, type=Path)
    validate.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "inspect":
            result = inspect_visual_file(args.input, args.media_type)
        elif args.command == "extract-manifest":
            result = extract_visual_metadata_manifest(
                _load_json(args.case), _load_json(args.artifact_map), args.artifact_root,
            )
        elif args.command == "build-binding":
            result = build_visual_sector_binding(
                _load_json(args.case), _load_json(args.loc_result), _load_json(args.manifest),
            )
        else:
            result = validate_visual_package(
                _load_json(args.case), _load_json(args.loc_result),
                _load_json(args.manifest), _load_json(args.binding),
                _load_json(args.artifact_map), args.artifact_root,
            )
        _write_json(args.output, result)
    except protocol.ProtocolError as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
