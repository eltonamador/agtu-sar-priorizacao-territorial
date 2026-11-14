#!/usr/bin/env python3
"""Gera a cadeia de custódia visual autorizada do cenário RURAL-01.

O construtor é deliberadamente limitado a uma lista branca de quinze arquivos
já copiados para a pasta isolada do cenário. Ele não percorre a pasta de origem
geral, não procura outros arquivos e não produz footprint espacial. As imagens
são aceitas somente como contexto; não alteram numericamente o núcleo LOC.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = Path(__file__).resolve()
EXTRACTOR_PATH = BUILDER_PATH.with_name("extract_visual_metadata.swift")
INPUT_DIR = ROOT / "outputs" / "campo_rural01" / "reservado_originais"
DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "campo_rural01" / "entrada_cega_v1"
SWIFT_EXECUTABLE = Path("/usr/bin/swift")
SWIFT_MODULE_CACHE = Path("/tmp/agtu-rural01-swift-module-cache")

SCENARIO_ID = "RURAL-01"
CONTRACT_ID = "RURAL01-VISUAL-CUSTODY-v1.0"
METADATA_CONTRACT_ID = "RURAL01-VISUAL-METADATA-v1.0"

# A lista branca é intencional: arquivos não relacionados ao conjunto
# autorizado jamais são descobertos por glob, find ou varredura de diretório.
AUTHORIZED_FILES = (
    "ParicasSolo0376.HEIC",
    "ParicasSolo0377.HEIC",
    "ParicasSolo0378.HEIC",
    "ParicasSolo0379.HEIC",
    "ParicasSolo0380.HEIC",
    "ParicasSolo0381.HEIC",
    "ParicasDrone0858.JPG",
    "ParicasDrone0859.JPG",
    "ParicasDrone0860.JPG",
    "ParicasDrone0861.JPG",
    "ParicasDrone0862.JPG",
    "ParicasDrone0863.JPG",
    "ParicasDrone0864.JPG",
    "ParicasDrone0865.JPG",
    "ParicasDrone0866.JPG",
)

EXPECTED_SHA256 = {
    "ParicasSolo0376.HEIC": "2c8af50430755c2ba7e874485346eec3f81bc8a187e13616d18951e018bb907f",
    "ParicasSolo0377.HEIC": "54395546c9880a6e6839e30f7042dbc60cc4e1eae4b0cc5641a30a110b2b7042",
    "ParicasSolo0378.HEIC": "b4444762ec5f819bf79ad0fbec962b9064bc7f7ff3374d9aff964c4b1da30e1d",
    "ParicasSolo0379.HEIC": "4253a5817e395f5cab4cbfc43ca3e5e956d487c8f9c5965e775c46d8e955bacb",
    "ParicasSolo0380.HEIC": "bbe50b7dc8aafbc532adac82eb08f7d428bf2d422bf712626a4199e6a32c251d",
    "ParicasSolo0381.HEIC": "eaf26580697d9d3beae10d4228b076d17ae190409e9205e7363ad76a4ddac6a2",
    "ParicasDrone0858.JPG": "fb5c4aee4913faa8a05862519d924ae226b7dc1e6bcb2effae8a4609f33436ae",
    "ParicasDrone0859.JPG": "f7d8ecf6bee65efef186202d45fd862ef8bdcf2aa93dd05fe058aa12825758e5",
    "ParicasDrone0860.JPG": "7bd5e444903242f7a3914c47608b3c7069493816c6ae36d603f7b1bd0ce19efe",
    "ParicasDrone0861.JPG": "e881927670a96dfd866a9d91debc947a3af56c2bcf868e860cd85c7da3822cd6",
    "ParicasDrone0862.JPG": "6c27c61704dadb0563896cc791cfaae40771e8c55581aa4b7a778ca267921ee7",
    "ParicasDrone0863.JPG": "a3d77cf5c7d4398c1ede2ed9bbf58d9cbd72f8857546866c4957eec518a7c89e",
    "ParicasDrone0864.JPG": "06ddd56efc73121e78c426a53be90b202addd970fd429d8bcab47ab6cc1b633c",
    "ParicasDrone0865.JPG": "05a83255cf86a8b7377e7a9b754f8db57f09215275c24a4313fd9fccee70546d",
    "ParicasDrone0866.JPG": "f2705fd572732c1e0e04c63bfb8e6b5fcb3fd425c5f7682026cfe42e1220e34a",
}

_EXIF_DATETIME_RE = re.compile(r"^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})$")


class ManifestError(ValueError):
    """O conjunto não satisfaz o contrato de custódia congelado."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def with_payload_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result.pop("payload_sha256", None)
    result["payload_sha256"] = canonical_sha256(result)
    return result


def write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    data = canonical_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _finite_number(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return int(value) if isinstance(value, int) else number


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.strip()
    return result or None


def _numeric_xmp(value: Any) -> float | None:
    text = _clean_text(value)
    if text is None:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _iso_local(raw: Any, offset: Any) -> str | None:
    text = _clean_text(raw)
    if text is None:
        return None
    match = _EXIF_DATETIME_RE.fullmatch(text)
    if match is None:
        return None
    year, month, day, hour, minute, second = match.groups()
    suffix = _clean_text(offset) or ""
    return f"{year}-{month}-{day}T{hour}:{minute}:{second}{suffix}"


def _custody_manifest() -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for name in AUTHORIZED_FILES:
        path = INPUT_DIR / name
        if not path.is_file():
            raise ManifestError(f"Arquivo autorizado ausente: {name}")
        actual_hash = file_sha256(path)
        if actual_hash != EXPECTED_SHA256[name]:
            raise ManifestError(f"Hash divergente para o arquivo autorizado: {name}")
        files.append({
            "relative_path": f"reservado_originais/{name}",
            "file_name": name,
            "bytes": path.stat().st_size,
            "sha256": actual_hash,
        })

    return with_payload_hash({
        "contract_id": CONTRACT_ID,
        "scenario_id": SCENARIO_ID,
        "source_directory": "outputs/campo_rural01/reservado_originais",
        "selection_method": "EXPLICIT_ALLOWLIST_NO_DIRECTORY_DISCOVERY",
        "authorized_file_count": len(AUTHORIZED_FILES),
        "verified_file_count": len(files),
        "all_hashes_match_frozen_values": True,
        "files": files,
        "builder": {
            "relative_path": "work/rural01_processamento_cego_v1/build_visual_manifest.py",
            "sha256": file_sha256(BUILDER_PATH),
        },
        "metadata_extractor": {
            "relative_path": "work/rural01_processamento_cego_v1/extract_visual_metadata.swift",
            "sha256": file_sha256(EXTRACTOR_PATH),
            "api": "APPLE_IMAGEIO_WHITELIST",
        },
    })


def _extract_metadata() -> list[dict[str, Any]]:
    if not SWIFT_EXECUTABLE.is_file():
        raise ManifestError("Runtime Swift não disponível para leitura ImageIO.")
    command = [
        str(SWIFT_EXECUTABLE),
        "-module-cache-path",
        str(SWIFT_MODULE_CACHE),
        str(EXTRACTOR_PATH),
        *(str(INPUT_DIR / name) for name in AUTHORIZED_FILES),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if completed.returncode != 0:
        raise ManifestError(
            "Falha na extração ImageIO: " + completed.stderr.strip()[:500]
        )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ManifestError("O extrator ImageIO não retornou JSON válido.") from exc
    if not isinstance(value, list) or len(value) != len(AUTHORIZED_FILES):
        raise ManifestError("O extrator não retornou exatamente quinze registros.")
    indexed: dict[str, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("file"), str):
            raise ManifestError("Registro ImageIO inválido.")
        name = item["file"]
        if name in indexed or name not in EXPECTED_SHA256:
            raise ManifestError("Nome inesperado ou repetido no retorno ImageIO.")
        if item.get("error") is not None:
            raise ManifestError(f"Leitura ImageIO falhou para {name}.")
        indexed[name] = item
    if set(indexed) != set(AUTHORIZED_FILES):
        raise ManifestError("O retorno ImageIO difere da lista branca autorizada.")
    return [indexed[name] for name in AUTHORIZED_FILES]


def _normalized_record(index: int, raw: Mapping[str, Any]) -> dict[str, Any]:
    name = str(raw["file"])
    platform = "SOLO" if name.startswith("ParicasSolo") else "DRONE"
    media_format = "HEIC" if name.endswith(".HEIC") else "JPEG"
    offset = _clean_text(raw.get("offset_original"))
    embedded_time = _iso_local(raw.get("date_time_original"), offset)
    dji_xmp = {
        "absolute_altitude_m": _numeric_xmp(raw.get("dji_AbsoluteAltitude")),
        "relative_altitude_m": _numeric_xmp(raw.get("dji_RelativeAltitude")),
        "gimbal_roll_deg": _numeric_xmp(raw.get("dji_GimbalRollDegree")),
        "gimbal_yaw_deg": _numeric_xmp(raw.get("dji_GimbalYawDegree")),
        "gimbal_pitch_deg": _numeric_xmp(raw.get("dji_GimbalPitchDegree")),
        "flight_roll_deg": _numeric_xmp(raw.get("dji_FlightRollDegree")),
        "flight_yaw_deg": _numeric_xmp(raw.get("dji_FlightYawDegree")),
        "flight_pitch_deg": _numeric_xmp(raw.get("dji_FlightPitchDegree")),
    }
    if platform != "DRONE":
        dji_xmp = {key: None for key in dji_xmp}

    return {
        "visual_id": f"RURAL01-VIS-{index:03d}",
        "file_name": name,
        "relative_path": f"reservado_originais/{name}",
        "sha256": EXPECTED_SHA256[name],
        "bytes": int(raw["bytes"]),
        "platform": platform,
        "media_format": media_format,
        "media_uti": _clean_text(raw.get("uti")),
        "dimensions_px": {
            "width": int(raw["width"]),
            "height": int(raw["height"]),
        },
        "sensor_modality": "RGB_VISIBLE_NON_THERMAL",
        "thermal_channel_present": False,
        "camera": {
            "make": _clean_text(raw.get("make")),
            "model": _clean_text(raw.get("model")),
            "lens_model": _clean_text(raw.get("lens_model")),
            "software": _clean_text(raw.get("software")),
        },
        "capture_time": {
            "embedded_datetime_original_raw": _clean_text(raw.get("date_time_original")),
            "embedded_offset_raw": offset,
            "embedded_datetime_iso_when_offset_available": embedded_time if offset else None,
            "timezone_status": "EXPLICIT_IN_METADATA" if offset else "OFFSET_NOT_EMBEDDED",
            "operator_declared_time_mapping": None,
            "status": "REVIEW_TEMPORAL_CONFLICT",
        },
        "gps": {
            "latitude": _finite_number(raw.get("latitude")),
            "longitude": _finite_number(raw.get("longitude")),
            "altitude_m": _finite_number(raw.get("altitude_m")),
            "horizontal_error_m": _finite_number(raw.get("horizontal_error_m")),
            "image_direction_deg_true": _finite_number(raw.get("image_direction_deg_true")),
            "gps_date_raw": _clean_text(raw.get("gps_date")),
            "gps_time_utc_raw": _clean_text(raw.get("gps_time_utc")),
            "speed": _finite_number(raw.get("speed")),
            "speed_ref": _clean_text(raw.get("speed_ref")),
        },
        "optics": {
            "focal_length_mm": _finite_number(raw.get("focal_length_mm")),
            "focal_length_35mm": _finite_number(raw.get("focal_length_35mm")),
            "f_number": _finite_number(raw.get("f_number")),
            "exposure_s": _finite_number(raw.get("exposure_s")),
            "iso": _finite_number(raw.get("iso")),
            "orientation": _finite_number(raw.get("orientation")),
        },
        "dji_xmp": dji_xmp,
        "controls": {
            "authorized_for_context": True,
            "spatial_footprint_authorized": False,
            "loc_numeric_effect": False,
            "det_review_status": "REVISAR",
            "det_determination": "INDETERMINADO",
            "target_visibility_assessment": "INDETERMINADO",
        },
    }


def _metadata_manifest(
    custody: Mapping[str, Any], custody_file_sha256: str,
) -> dict[str, Any]:
    extracted = _extract_metadata()
    records = [
        _normalized_record(index, raw)
        for index, raw in enumerate(extracted, start=1)
    ]
    if any(item["bytes"] <= 0 for item in records):
        raise ManifestError("Arquivo visual vazio ou com tamanho inválido.")

    return with_payload_hash({
        "contract_id": METADATA_CONTRACT_ID,
        "scenario_id": SCENARIO_ID,
        "custody_manifest": {
            "relative_path": "outputs/campo_rural01/entrada_cega_v1/manifesto_sha256_conjunto_a.json",
            "file_sha256": custody_file_sha256,
            "payload_sha256": custody["payload_sha256"],
        },
        "file_count": len(records),
        "declared_capture_sessions": {
            "source": "OPERADOR",
            "date": "2026-10-22",
            "local_times": ["06:10:00", "06:22:00"],
            "timezone": "America/Belem",
            "utc_offset": "-03:00",
            "mapping_to_individual_files": "NOT_AVAILABLE",
        },
        "embedded_capture_summary": {
            "date": "2026-10-21",
            "overall_local_time_range_raw": ["07:46:40", "07:54:49"],
            "ground_images_local_time_range_with_explicit_offset": [
                "07:46:40-03:00", "07:47:00-03:00"
            ],
            "drone_images_local_time_range_without_embedded_offset": [
                "07:52:02", "07:54:49"
            ],
            "ground_gps_utc_time_range": ["10:46:39", "10:46:59"],
        },
        "temporal_review": {
            "temporal_conflict": True,
            "status": "AWAITING_OPERATOR_CONFIRMATION",
            "reason": (
                "A data e os horários declarados pelo operador não coincidem "
                "com DateTimeOriginal e, nas imagens de solo, com GPS UTC."
            ),
            "resolution_required": (
                "Confirmar se a data declarada, o relógio dos equipamentos ou "
                "a associação dos arquivos ao voo foi informada incorretamente."
            ),
            "metadata_values_preserved_without_overwrite": True,
        },
        "operational_annotations": [
            {
                "annotation_id": "RURAL01-ANN-VEICULO-001",
                "source": "OPERADOR",
                "statement": "O veículo branco visível nas fotografias pertence à equipe.",
                "effect_on_loc": "NONE",
                "effect_on_det": "CONTEXT_ONLY",
            }
        ],
        "global_controls": {
            "authorized_for_context": True,
            "spatial_footprint_authorized": False,
            "spatial_footprint_reason": (
                "Conflito temporal pendente e ausência de orientação óptica "
                "confiável suficiente para footprint automatizado."
            ),
            "loc_numeric_effect": False,
            "det_review_status": "REVISAR",
            "det_determination": "INDETERMINADO",
            "rgb_non_thermal": True,
            "target_location_or_evaluation_position_used": False,
        },
        "records": records,
    })


def build(output_dir: Path) -> dict[str, str]:
    custody = _custody_manifest()
    custody_path = output_dir / "manifesto_sha256_conjunto_a.json"
    write_json_atomic(custody_path, custody)
    custody_file_sha256 = file_sha256(custody_path)

    metadata = _metadata_manifest(custody, custody_file_sha256)
    metadata_path = output_dir / "manifesto_metadados_visuais.json"
    write_json_atomic(metadata_path, metadata)

    return {
        "custody_manifest": str(custody_path),
        "custody_manifest_sha256": file_sha256(custody_path),
        "metadata_manifest": str(metadata_path),
        "metadata_manifest_sha256": file_sha256(metadata_path),
        "file_count": str(len(AUTHORIZED_FILES)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Constrói manifestos visuais determinísticos do RURAL-01."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    result = build(args.output_dir.resolve())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
