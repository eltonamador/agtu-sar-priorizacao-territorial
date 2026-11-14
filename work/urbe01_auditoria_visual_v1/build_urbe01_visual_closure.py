#!/usr/bin/env python3
"""Fecha o piloto URBE-01 sem reclassificar retroativamente a fase cega.

O subprocesso visual usa somente os originais, o registro do operador e os
setores já congelados. A avaliação pós-abertura é lida apenas depois que a
auditoria visual foi produzida, para compor o relatório final do caso.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_WORK = ROOT / "work" / "protocolo_integrado_v1"
if str(PROTOCOL_WORK) not in sys.path:
    sys.path.insert(0, str(PROTOCOL_WORK))

import integrated_protocol as protocol  # noqa: E402
import visual_spatial_binding as visual  # noqa: E402


SCENARIO_ID = "URBE-01"
AUDIT_PROTOCOL_ID = "URBE01-VISUAL-RETRO-v1.0"
CLOSURE_PROTOCOL_ID = "URBE01-FORMAL-CLOSURE-v1.0"
PHASE = "POS_ABERTURA_RETROSPECTIVA"
CLASSIFICATION = "RETROSPECTIVO_POS_ABERTURA_NAO_CONFIRMATORIO"

WORK_DIR = ROOT / "work" / "urbe01_auditoria_visual_v1"
BUILDER_PATH = Path(__file__).resolve()
TEST_PATH = WORK_DIR / "test_build_urbe01_visual_closure.py"
REGISTRY_PATH = WORK_DIR / "registro_operador_visual_urbe01_v1.json"
CAMPO_DIR = ROOT / "outputs" / "campo_urbe01"
PHOTO_DIR = CAMPO_DIR / "reservado_originais"
PHOTO_MANIFEST_PATH = CAMPO_DIR / "manifesto_sha256.txt"
BLIND_DIR = CAMPO_DIR / "processamento_cego_v1"
BLIND_MANIFEST_PATH = BLIND_DIR / "manifesto_processamento_cego.json"
BLIND_RESULT_PATH = BLIND_DIR / "resultado_urbe01_cego.json"
SECTOR_PATH = BLIND_DIR / "setores_urbe01.geojson"
POST_DIR = CAMPO_DIR / "avaliacao_pos_abertura_v1"
POST_MANIFEST_PATH = POST_DIR / "manifesto_avaliacao_pos_abertura.json"
POST_RESULT_PATH = POST_DIR / "resultado_avaliacao_pos_abertura.json"

DEFAULT_AUDIT_DIR = CAMPO_DIR / "auditoria_visual_pos_abertura_v1"
DEFAULT_CLOSURE_DIR = CAMPO_DIR / "fechamento_formal_v1"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_CARDINAL_CENTERS = {
    "N": 0.0,
    "NE": 45.0,
    "E": 90.0,
    "SE": 135.0,
    "S": 180.0,
    "SW": 225.0,
    "W": 270.0,
    "NW": 315.0,
}
_POSITION_CENTERS = {"NORTE": 0.0, "LESTE": 90.0, "SUL": 180.0, "OESTE": 270.0}


class ClosureError(ValueError):
    """O pacote não pode ser fechado sem alterar ou inventar dados."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClosureError(f"JSON inválido: {path}") from exc
    if not isinstance(value, dict):
        raise ClosureError(f"Objeto JSON esperado: {path}")
    return value


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def with_self_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result.pop("output_sha256", None)
    result["output_sha256"] = protocol.canonical_sha256(result)
    return result


def write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    write_bytes_atomic(path, protocol.canonical_json_bytes(value))


def write_text(path: Path, value: str) -> None:
    write_bytes_atomic(path, (value.rstrip() + "\n").encode("utf-8"))


def circular_difference(first: float, second: float) -> float:
    return abs((first - second + 180.0) % 360.0 - 180.0)


def format_pt(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def initial_bearing_deg(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, first)
    lat2, lon2 = map(math.radians, second)
    delta_lon = lon2 - lon1
    y = math.sin(delta_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def metadata_coordinate(inspection: Mapping[str, Any]) -> tuple[float, float] | None:
    metadata = inspection.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    gps = metadata.get("gps")
    if not isinstance(gps, Mapping):
        return None
    latitude = gps.get("latitude")
    longitude = gps.get("longitude")
    if (
        isinstance(latitude, (int, float))
        and not isinstance(latitude, bool)
        and isinstance(longitude, (int, float))
        and not isinstance(longitude, bool)
        and math.isfinite(float(latitude))
        and math.isfinite(float(longitude))
    ):
        return float(latitude), float(longitude)
    return None


def metadata_heading(inspection: Mapping[str, Any], platform: str) -> tuple[float | None, str]:
    metadata = inspection.get("metadata")
    if not isinstance(metadata, Mapping):
        return None, "NAO_DISPONIVEL"
    if platform == "SOLO":
        gps = metadata.get("gps")
        value = gps.get("image_direction_deg") if isinstance(gps, Mapping) else None
        source = "EXIF_GPS_IMAGE_DIRECTION"
    else:
        dji = metadata.get("dji_xmp")
        value = dji.get("flight_yaw_deg") if isinstance(dji, Mapping) else None
        source = "DJI_FLIGHT_YAW_APROXIMACAO_NAO_GIMBAL"
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return float(value) % 360.0, source
    return None, "NAO_DISPONIVEL"


def directional_review(
    visual_item: Mapping[str, Any], inspection: Mapping[str, Any], planning_point: tuple[float, float],
) -> dict[str, Any]:
    coordinate = metadata_coordinate(inspection)
    camera_bearing = initial_bearing_deg(planning_point, coordinate) if coordinate else None
    position = visual_item["camera_position_relative_to_point"]
    expected_position = _POSITION_CENTERS.get(position)
    position_difference = (
        circular_difference(camera_bearing, expected_position)
        if camera_bearing is not None and expected_position is not None
        else None
    )
    position_status = "NAO_AVALIAVEL"
    if position_difference is not None:
        position_status = "COERENTE" if position_difference <= 22.5 else "REVISAR_DIVERGENCIA"

    heading, heading_source = metadata_heading(inspection, str(visual_item["platform"]))
    declared_direction = visual_item["lens_aim_direction_cardinal"]
    expected_heading = _CARDINAL_CENTERS.get(declared_direction)
    heading_difference = (
        circular_difference(heading, expected_heading)
        if heading is not None and expected_heading is not None
        else None
    )
    heading_status = "NAO_AVALIAVEL"
    if declared_direction == "NADIR":
        heading_status = "NAO_APLICAVEL_NADIR"
    elif heading_difference is not None:
        heading_status = "COERENTE" if heading_difference <= 22.5 else "REVISAR_DIVERGENCIA"
    return {
        "declared_camera_position": position,
        "camera_bearing_from_initial_deg": round(camera_bearing, 6) if camera_bearing is not None else None,
        "position_difference_deg": round(position_difference, 6) if position_difference is not None else None,
        "position_status": position_status,
        "declared_lens_direction": declared_direction,
        "metadata_heading_deg": round(heading, 6) if heading is not None else None,
        "metadata_heading_source": heading_source,
        "heading_difference_deg": round(heading_difference, 6) if heading_difference is not None else None,
        "heading_status": heading_status,
        "metadata_heading_is_not_direct_proof_of_lens_axis": heading_source.startswith("DJI_"),
    }


def parse_photo_manifest() -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, line in enumerate(PHOTO_MANIFEST_PATH.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or _SHA_RE.fullmatch(parts[0]) is None:
            raise ClosureError(f"Linha inválida no manifesto fotográfico: {line_number}")
        relative = parts[1].strip()
        prefix = "reservado_originais/"
        if not relative.startswith(prefix):
            raise ClosureError("Manifesto fotográfico contém caminho fora da pasta reservada.")
        result[relative[len(prefix):]] = parts[0]
    return result


def verify_photos(registry: Mapping[str, Any]) -> dict[str, Any]:
    declared_manifest = parse_photo_manifest()
    visual_items = registry.get("visual_evidence")
    if not isinstance(visual_items, list) or len(visual_items) != 10:
        raise ClosureError("O registro visual precisa conter exatamente 10 arquivos.")
    registry_paths = {str(item.get("relative_path")) for item in visual_items if isinstance(item, Mapping)}
    if registry_paths != set(declared_manifest):
        raise ClosureError("Registro do operador e manifesto fotográfico não contêm os mesmos arquivos.")
    verified: list[dict[str, Any]] = []
    for item in sorted(visual_items, key=lambda value: value["visual_id"]):
        path = PHOTO_DIR / item["relative_path"]
        actual = file_sha256(path)
        if actual != item["file_sha256"] or actual != declared_manifest[item["relative_path"]]:
            raise ClosureError(f"Hash fotográfico divergente: {item['visual_id']}")
        verified.append({
            "visual_id": item["visual_id"],
            "relative_path": item["relative_path"],
            "bytes": path.stat().st_size,
            "sha256": actual,
        })
    return {
        "manifest_sha256": file_sha256(PHOTO_MANIFEST_PATH),
        "verified_count": len(verified),
        "files": verified,
    }


def verify_manifest_files(manifest_path: Path, base_dir: Path, key: str) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    entries = manifest.get(key)
    if not isinstance(entries, list):
        raise ClosureError(f"Lista {key} ausente em {manifest_path.name}.")
    verified: list[dict[str, Any]] = []
    for index, item in enumerate(entries):
        if not isinstance(item, Mapping):
            raise ClosureError(f"Entrada {index} inválida em {manifest_path.name}.")
        raw_path = item.get("path")
        expected = item.get("sha256")
        if not isinstance(raw_path, str) or not isinstance(expected, str) or _SHA_RE.fullmatch(expected) is None:
            raise ClosureError(f"Entrada {index} incompleta em {manifest_path.name}.")
        candidate = (base_dir / raw_path).resolve()
        try:
            candidate.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise ClosureError(f"Caminho fora da raiz: {raw_path}") from exc
        if file_sha256(candidate) != expected or candidate.stat().st_size != item.get("bytes"):
            raise ClosureError(f"Artefato divergente: {raw_path}")
        verified.append({"path": raw_path, "sha256": expected, "bytes": candidate.stat().st_size})
    projection = [{"path": item["path"], "sha256": item["sha256"]} for item in verified]
    return {
        "manifest_sha256": file_sha256(manifest_path),
        "verified_count": len(verified),
        "tree_sha256": protocol.canonical_sha256(projection),
        "files": verified,
        "manifest": manifest,
    }


def verify_blind_package() -> dict[str, Any]:
    verification = verify_manifest_files(BLIND_MANIFEST_PATH, ROOT, "files")
    manifest = verification["manifest"]
    result = load_json(BLIND_RESULT_PATH)
    sectors = load_json(SECTOR_PATH)
    if manifest.get("ground_truth_used") is not False or result.get("ground_truth_used") is not False:
        raise ClosureError("O pacote cego não preserva o controle de ausência da referência.")
    if manifest.get("confirmatory_eligible") is not False or result.get("confirmatory_eligible") is not False:
        raise ClosureError("O caso legado não pode ser promovido a confirmatório.")
    features = sectors.get("features")
    if not isinstance(features, list) or len(features) != 24:
        raise ClosureError("São esperados 24 setores congelados.")
    return {
        "manifest_sha256": verification["manifest_sha256"],
        "verified_count": verification["verified_count"],
        "tree_sha256": verification["tree_sha256"],
        "blind_result_sha256": file_sha256(BLIND_RESULT_PATH),
        "sector_geojson_sha256": file_sha256(SECTOR_PATH),
        "sector_count": len(features),
        "review_status": result.get("review_status"),
        "confirmatory_eligible": False,
        "ground_truth_used": False,
    }


def sector_polygons() -> tuple[dict[str, list[list[float]]], dict[str, dict[str, Any]]]:
    document = load_json(SECTOR_PATH)
    polygons: dict[str, list[list[float]]] = {}
    properties: dict[str, dict[str, Any]] = {}
    for feature in document["features"]:
        if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
            raise ClosureError("Feature setorial inválida.")
        prop = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(prop, Mapping) or not isinstance(geometry, Mapping):
            raise ClosureError("Setor sem propriedade ou geometria.")
        sector_id = prop.get("sector_id")
        if not isinstance(sector_id, str) or geometry.get("type") != "Polygon":
            raise ClosureError("Contrato setorial inesperado.")
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates or not isinstance(coordinates[0], list):
            raise ClosureError("Polígono setorial inválido.")
        if sector_id in polygons:
            raise ClosureError(f"Setor duplicado: {sector_id}")
        polygons[sector_id] = [[float(point[0]), float(point[1])] for point in coordinates[0]]
        properties[sector_id] = dict(prop)
    if len(polygons) != 24:
        raise ClosureError("Conjunto setorial precisa conter 24 setores.")
    return polygons, properties


def build_visual_artifacts(
    registry: Mapping[str, Any], generated_at: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    policy, policy_sha = visual._policy()
    polygons, sector_properties = sector_polygons()
    planning = registry["planning_point"]
    planning_coordinate = (float(planning["latitude"]), float(planning["longitude"]))
    records: list[dict[str, Any]] = []
    for item in sorted(registry["visual_evidence"], key=lambda value: value["visual_id"]):
        source = PHOTO_DIR / item["relative_path"]
        actual_sha = file_sha256(source)
        if actual_sha != item["file_sha256"]:
            raise ClosureError(f"Arquivo visual alterado: {item['visual_id']}")
        inspection = visual.inspect_visual_file(source, item["media_type"])
        operator_record = visual._operator_record(item)
        conflicts, warnings = visual._analyze_record(operator_record, inspection, policy)
        coordinate = metadata_coordinate(inspection)
        distance_m = visual._haversine_m(planning_coordinate, coordinate) if coordinate else None
        record = {
            "visual_id": item["visual_id"],
            "relative_path": item["relative_path"],
            "file_sha256": actual_sha,
            "media_type": item["media_type"],
            "operator_record": operator_record,
            "inspection": inspection,
            "distance_from_initial_m": round(distance_m, 3) if distance_m is not None else None,
            "directional_review": directional_review(item, inspection, planning_coordinate),
            "conflicts": conflicts,
            "warnings": warnings,
        }
        record["record_sha256"] = protocol.canonical_sha256(record)
        records.append(record)

    metadata_manifest = with_self_hash({
        "manifest_contract_version": "URBE01-VISUAL-METADATA-RETRO-v1",
        "protocol_id": AUDIT_PROTOCOL_ID,
        "phase": PHASE,
        "execution_classification": CLASSIFICATION,
        "generated_at": generated_at,
        "scenario_id": SCENARIO_ID,
        "policy_id": policy["policy_id"],
        "policy_sha256": policy_sha,
        "operator_registry_sha256": file_sha256(REGISTRY_PATH),
        "photo_manifest_sha256": file_sha256(PHOTO_MANIFEST_PATH),
        "reference_known_to_researcher_at_execution": True,
        "reference_used_by_visual_audit": False,
        "ground_truth_used": False,
        "confirmatory_eligible": False,
        "target_included_by_design": False,
        "incidental_people_or_identifiers_possible": True,
        "privacy_distribution": registry["privacy_distribution"],
        "records": records,
    })

    bindings = [visual._build_record_binding(record, polygons, policy) for record in records]
    binding_document = with_self_hash({
        "binding_contract_version": "URBE01-VISUAL-SECTOR-RETRO-v1",
        "engine_id": visual.BINDING_ENGINE_ID,
        "protocol_id": AUDIT_PROTOCOL_ID,
        "phase": PHASE,
        "execution_classification": CLASSIFICATION,
        "generated_at": generated_at,
        "scenario_id": SCENARIO_ID,
        "policy_id": policy["policy_id"],
        "policy_sha256": policy_sha,
        "metadata_manifest_sha256": metadata_manifest["output_sha256"],
        "source_blind_result_sha256": file_sha256(BLIND_RESULT_PATH),
        "source_sector_geojson_sha256": file_sha256(SECTOR_PATH),
        "source_sector_count": len(polygons),
        "reference_known_to_researcher_at_execution": True,
        "reference_used_by_visual_audit": False,
        "ground_truth_used": False,
        "confirmatory_eligible": False,
        "rankings_recomputed": False,
        "sectors_recomputed": False,
        "weights_recomputed": False,
        "affects_loc": False,
        "affects_urg": False,
        "affects_frozen_det": False,
        "visual_role": "VERIFICACAO_TECNICA_DESCRITIVA_NAO_CONFIRMATORIA",
        "bindings": bindings,
    })

    a05 = next(item for item in bindings if item["visual_id"] == "A05")
    expected_r01 = sorted(
        sector_id for sector_id, prop in sector_properties.items()
        if prop.get("ring_index") == 1
    )
    contextual = sorted(item["visual_id"] for item in bindings if item["quality"] == visual.CONTEXTUAL)
    qualified = sorted(item["visual_id"] for item in bindings if item["quality"] == visual.APPROXIMATE)
    distances = [record["distance_from_initial_m"] for record in records if record["distance_from_initial_m"] is not None]
    summary = {
        "decoded_count": sum(record["inspection"]["decode_status"] == visual.DECODED for record in records),
        "record_count": len(records),
        "qualified_visual_ids": qualified,
        "contextual_visual_ids": contextual,
        "a05_quality": a05["quality"],
        "a05_footprint_radius_m": a05["footprint_radius_m"],
        "a05_sector_ids": a05["applicable_sector_ids"],
        "expected_r01_sector_ids": expected_r01,
        "minimum_camera_distance_from_initial_m": round(min(distances), 3),
        "maximum_camera_distance_from_initial_m": round(max(distances), 3),
        "directional_review_ids": sorted(
            record["visual_id"] for record in records
            if "REVISAR_DIVERGENCIA" in {
                record["directional_review"]["position_status"],
                record["directional_review"]["heading_status"],
            }
        ),
    }
    return metadata_manifest, binding_document, summary


def audit_report(summary: Mapping[str, Any]) -> str:
    sectors = ", ".join(summary["a05_sector_ids"])
    contextual = ", ".join(summary["contextual_visual_ids"])
    direction_review = ", ".join(summary["directional_review_ids"])
    minimum_distance = format_pt(float(summary["minimum_camera_distance_from_initial_m"]), 2)
    maximum_distance = format_pt(float(summary["maximum_camera_distance_from_initial_m"]), 2)
    footprint_radius = format_pt(float(summary["a05_footprint_radius_m"]), 6)
    return f"""# Auditoria visual retrospectiva do URBE-01

## Finalidade e limite de uso

Esta auditoria foi executada após a abertura da posição de referência. Por isso, sua classificação é **retrospectiva, descritiva e não confirmatória**. O subprocesso visual não consultou a posição revelada, não recalculou setores, pesos ou rankings e não alterou as saídas LOC, URG ou DET anteriormente congeladas.

## Integridade e extração

- fotografias conferidas: **{summary['record_count']} de {summary['record_count']}**;
- fotografias decodificadas com dimensões válidas: **{summary['decoded_count']} de {summary['record_count']}**;
- imagens espacialmente qualificadas: **{', '.join(summary['qualified_visual_ids'])}**;
- imagens mantidas apenas como contexto: **{contextual}**;
- distância das câmeras ao ponto inicial: entre **{minimum_distance} m** e **{maximum_distance} m**.

Os metadados completos contêm geotags e permanecem na subpasta `restrito`. Cópias destinadas à dissertação, à qualificação ou à circulação externa devem ser sanitizadas.

## Vínculo espacial obtido

Apenas a fotografia A05, registrada como tomada vertical do drone, permitiu calcular footprint conservador. O vínculo recebeu a classe `{summary['a05_quality']}` e raio de **{footprint_radius} m**. O círculo intersectou os oito setores do anel interno:

`{sectors}`.

Como a imagem cobre todas as direções de R01, ela demonstra aquisição e contexto visual nas proximidades do ponto inicial, mas **não diferencia uma hipótese direcional**, não sustenta R02 ou R03 e não melhora o ranking LOC.

## Registros que exigem cautela

As declarações cardinais e os metadados de direção ou posição precisam de revisão em: **{direction_review}**. O rumo de voo DJI não comprova, por si, o eixo óptico, e o campo de inclinação do gimbal permaneceu 0° tanto em imagens verticais quanto oblíquas. Por isso, as imagens de solo e as tomadas oblíquas não receberam footprint automático.

Há pessoas incidentais, placas e identificadores de imóveis em parte do conjunto. A afirmação metodologicamente correta é que o alvo não foi incluído por desenho; isso não equivale a afirmar que nenhuma pessoa aparece nas fotografias.

## Conclusão

O Conjunto A validou identidade dos arquivos, custódia, decodificação, extração de metadados e uma vinculação espacial limitada ao entorno imediato do ponto inicial. Seu benefício nesta rodada é documental e metodológico. Ele não altera o resultado negativo já obtido na avaliação pós-abertura e não deve ser apresentado como cobertura dos candidatos, do corredor de deslocamento ou da posição encontrada.
"""


def verify_post_opening_package() -> dict[str, Any]:
    verification = verify_manifest_files(POST_MANIFEST_PATH, POST_DIR, "output_files")
    result = load_json(POST_RESULT_PATH)
    conclusion = result.get("case_conclusion")
    if not isinstance(conclusion, Mapping):
        raise ClosureError("Conclusão pós-abertura ausente.")
    if conclusion.get("classification") != "NAO_COBERTO_NO_TOP3_BASE_NEM_PERFIL":
        raise ClosureError("Classificação pós-abertura inesperada.")
    comparison = result.get("profile_incremental_comparison")
    if not isinstance(comparison, Mapping):
        raise ClosureError("Comparação BASE/PERFIL ausente.")
    return {
        "manifest_sha256": verification["manifest_sha256"],
        "verified_count": verification["verified_count"],
        "tree_sha256": verification["tree_sha256"],
        "classification": conclusion["classification"],
        "general_efficiency_claim_allowed": conclusion["general_efficiency_claim_allowed"],
        "base_reference_rank": comparison["base_reference_rank"],
        "profile_reference_rank": comparison["profile_reference_rank"],
    }


def generated_file_entry(path: Path, role: str) -> dict[str, Any]:
    try:
        manifest_path = str(path.relative_to(ROOT))
    except ValueError:
        manifest_path = (
            str(Path(path.parent.name) / path.name)
            if path.parent.name == "restrito"
            else path.name
        )
    return {
        "path": manifest_path,
        "role": role,
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def build_package(audit_dir: Path, closure_dir: Path, generated_at: str) -> dict[str, Any]:
    registry = load_json(REGISTRY_PATH)
    if registry.get("phase") != PHASE or registry.get("scenario_id") != SCENARIO_ID:
        raise ClosureError("Registro do operador não corresponde ao fechamento URBE-01.")
    photo_verification = verify_photos(registry)
    blind_before = verify_blind_package()

    manifest_a, binding_a, summary_a = build_visual_artifacts(registry, generated_at)
    manifest_b, binding_b, summary_b = build_visual_artifacts(registry, generated_at)
    deterministic = (
        protocol.canonical_json_bytes(manifest_a) == protocol.canonical_json_bytes(manifest_b)
        and protocol.canonical_json_bytes(binding_a) == protocol.canonical_json_bytes(binding_b)
        and protocol.canonical_json_bytes(summary_a) == protocol.canonical_json_bytes(summary_b)
    )
    if not deterministic:
        raise ClosureError("A auditoria visual não foi determinística.")

    restricted_dir = audit_dir / "restrito"
    metadata_path = restricted_dir / "manifesto_inspecao_metadados_visuais_urbe01_v1.json"
    binding_path = restricted_dir / "vinculo_visual_setores_retrospectivo_urbe01_v1.json"
    report_path = audit_dir / "relatorio_auditoria_visual_urbe01_v1.md"
    determinism_path = audit_dir / "relatorio_determinismo_visual_urbe01_v1.json"
    qa_path = audit_dir / "relatorio_qa_visual_urbe01_v1.json"
    audit_manifest_path = audit_dir / "manifesto_auditoria_visual_urbe01_v1.json"

    write_json(metadata_path, manifest_a)
    write_json(binding_path, binding_a)
    write_text(report_path, audit_report(summary_a))

    determinism = with_self_hash({
        "protocol_id": AUDIT_PROTOCOL_ID,
        "scenario_id": SCENARIO_ID,
        "generated_at": generated_at,
        "runs": 2,
        "deterministic_repeat_matches": deterministic,
        "metadata_manifest_sha256_run_1": manifest_a["output_sha256"],
        "metadata_manifest_sha256_run_2": manifest_b["output_sha256"],
        "binding_sha256_run_1": binding_a["output_sha256"],
        "binding_sha256_run_2": binding_b["output_sha256"],
    })
    write_json(determinism_path, determinism)

    a05 = next(item for item in binding_a["bindings"] if item["visual_id"] == "A05")
    contextual_ids = sorted(
        item["visual_id"] for item in binding_a["bindings"]
        if item["quality"] == visual.CONTEXTUAL
    )
    qa_gates = {
        "photo_hashes_10_of_10_verified": photo_verification["verified_count"] == 10,
        "images_10_of_10_decoded": summary_a["decoded_count"] == 10,
        "blind_manifest_files_all_verified": blind_before["verified_count"] == 35,
        "visual_repeat_is_deterministic": deterministic,
        "only_a05_is_spatially_qualified": summary_a["qualified_visual_ids"] == ["A05"],
        "other_nine_images_are_contextual": contextual_ids == ["A00", "A02", "A03", "A04", "A06", "A07", "A08", "A09", "A10"],
        "a05_quality_is_approximate": a05["quality"] == visual.APPROXIMATE,
        "a05_footprint_is_finite_positive_and_within_policy": (
            isinstance(a05["footprint_radius_m"], (int, float))
            and math.isfinite(float(a05["footprint_radius_m"]))
            and 0 < float(a05["footprint_radius_m"]) <= 1000
        ),
        "a05_intersects_all_and_only_r01_sectors": summary_a["a05_sector_ids"] == summary_a["expected_r01_sector_ids"],
        "visual_audit_does_not_use_reference": manifest_a["reference_used_by_visual_audit"] is False,
        "visual_audit_does_not_affect_loc": binding_a["affects_loc"] is False,
        "visual_audit_is_not_confirmatory": binding_a["confirmatory_eligible"] is False,
    }
    qa = with_self_hash({
        "protocol_id": AUDIT_PROTOCOL_ID,
        "scenario_id": SCENARIO_ID,
        "generated_at": generated_at,
        "status": "PASS" if all(qa_gates.values()) else "FAIL",
        "gate_count": len(qa_gates),
        "passed_gate_count": sum(qa_gates.values()),
        "gates": qa_gates,
        "summary": summary_a,
    })
    if qa["status"] != "PASS":
        raise ClosureError("A auditoria visual falhou em um ou mais gates.")
    write_json(qa_path, qa)

    audit_files = [
        generated_file_entry(metadata_path, "restricted_metadata_manifest"),
        generated_file_entry(binding_path, "restricted_visual_sector_binding"),
        generated_file_entry(report_path, "sanitized_audit_report"),
        generated_file_entry(determinism_path, "determinism_report"),
        generated_file_entry(qa_path, "qa_report"),
    ]
    audit_manifest = with_self_hash({
        "protocol_id": AUDIT_PROTOCOL_ID,
        "scenario_id": SCENARIO_ID,
        "phase": PHASE,
        "execution_classification": CLASSIFICATION,
        "generated_at": generated_at,
        "reference_known_to_researcher_at_execution": True,
        "reference_used_by_visual_audit": False,
        "ground_truth_used": False,
        "confirmatory_eligible": False,
        "frozen_blind_package_modified": False,
        "rankings_recomputed": False,
        "sectors_recomputed": False,
        "weights_recomputed": False,
        "affects_loc": False,
        "affects_urg": False,
        "affects_frozen_det": False,
        "source_hashes": {
            "builder_sha256": file_sha256(BUILDER_PATH),
            "builder_test_sha256": file_sha256(TEST_PATH),
            "visual_engine_sha256": file_sha256(PROTOCOL_WORK / "visual_spatial_binding.py"),
            "swift_extractor_sha256": file_sha256(PROTOCOL_WORK / "extract_image_metadata.swift"),
            "operator_registry_sha256": file_sha256(REGISTRY_PATH),
            "photo_manifest_sha256": photo_verification["manifest_sha256"],
            "blind_manifest_sha256": blind_before["manifest_sha256"],
            "blind_result_sha256": blind_before["blind_result_sha256"],
            "sector_geojson_sha256": blind_before["sector_geojson_sha256"],
        },
        "files": audit_files,
    })
    write_json(audit_manifest_path, audit_manifest)

    blind_after = verify_blind_package()
    if blind_after["tree_sha256"] != blind_before["tree_sha256"]:
        raise ClosureError("O pacote cego foi alterado durante a auditoria visual.")
    post = verify_post_opening_package()

    matrix = with_self_hash({
        "contract_version": "URBE01-TRACEABILITY-MATRIX-v1",
        "scenario_id": SCENARIO_ID,
        "generated_at": generated_at,
        "phases": [
            {
                "phase": "PROCESSAMENTO_CEGO_LEGADO",
                "status": "CONGELADO_E_INTEGRO",
                "manifest_sha256": blind_before["manifest_sha256"],
                "tree_sha256": blind_before["tree_sha256"],
                "sector_count": 24,
                "ground_truth_used": False,
                "confirmatory_eligible": False,
            },
            {
                "phase": "AVALIACAO_POS_ABERTURA",
                "status": post["classification"],
                "manifest_sha256": post["manifest_sha256"],
                "tree_sha256": post["tree_sha256"],
                "base_reference_rank": post["base_reference_rank"],
                "profile_reference_rank": post["profile_reference_rank"],
                "general_efficiency_claim_allowed": post["general_efficiency_claim_allowed"],
            },
            {
                "phase": "AUDITORIA_VISUAL_POS_ABERTURA",
                "status": "PASS",
                "manifest_sha256": audit_manifest["output_sha256"],
                "qualified_visual_ids": summary_a["qualified_visual_ids"],
                "contextual_visual_ids": summary_a["contextual_visual_ids"],
                "affects_loc": False,
                "affects_urg": False,
                "affects_frozen_det": False,
            },
        ],
        "historical_placeholders": [
            {
                "path": "outputs/campo_urbe01/processamento_preparado_v1/ground_truth_reservado_urbe01_PREENCHER.csv",
                "status": "PLACEHOLDER_HISTORICO_NAO_UTILIZADO_NAO_PREENCHER_RETROATIVAMENTE",
            }
        ],
    })

    readme = f"""# Fechamento formal do URBE-01

O URBE-01 está encerrado como **piloto diagnóstico legado**. O processamento cego original permanece íntegro e não foi convertido retroativamente no contrato prospectivo mais recente.

Este fechamento reúne três fases distintas: processamento cego, avaliação pós-abertura e auditoria visual retrospectiva. A última usa metadados e setores já congelados, mas não altera LOC, URG, DET, pesos ou rankings.

## Veredito

- pacote cego: íntegro, 24 setores, classificação não confirmatória;
- resultado pós-abertura: referência fora do Top-3 BASE e PERFIL;
- auditoria visual: 10 imagens válidas; somente A05 com footprint aproximado;
- capacidade discriminante de A05: baixa, pois o footprint toca os oito setores de R01;
- estado do caso: **ENCERRADO_COM_RESULTADO_NEGATIVO_PRESERVADO**;
- uso científico: diagnóstico do protocolo, sem alegação de eficácia geral.

O protocolo integrado prospectivo completo deverá começar no próximo cenário antes da revelação de sua posição reservada.
"""

    closure_footprint_radius = format_pt(float(summary_a["a05_footprint_radius_m"]), 6)
    closure_minimum_distance = format_pt(float(summary_a["minimum_camera_distance_from_initial_m"]), 2)
    closure_maximum_distance = format_pt(float(summary_a["maximum_camera_distance_from_initial_m"]), 2)
    closure_report = f"""# Relatório de fechamento do piloto URBE-01

## Síntese executiva

O piloto URBE-01 foi concluído sem alteração dos artefatos cegos. Os 35 arquivos registrados no manifesto do processamento cego permanecem íntegros, assim como as 10 fotografias originais e os 10 produtos da avaliação pós-abertura.

## Resultado de localização preservado

A avaliação pós-abertura permaneceu negativa: o setor correspondente à referência ocupou o **18º lugar no ranking BASE** e o **19º lugar no ranking PERFIL**, ficando fora do Top-1 e do Top-3 em ambos. Esse resultado não foi recalibrado pela auditoria visual e não autoriza inferência sobre eficácia geral a partir de um caso único.

## Resultado da auditoria visual

As dez imagens foram decodificadas e tiveram seus hashes confirmados. Apenas A05, a tomada vertical do drone, gerou footprint aproximado de **{closure_footprint_radius} m**. Por estar próxima ao vértice central da setorização, a área interceptou os oito setores de R01 e não ofereceu discriminação direcional. As outras nove imagens permaneceram contextuais.

O conjunto visual caracteriza o entorno imediato do ponto inicial, com câmeras posicionadas entre **{closure_minimum_distance} m** e **{closure_maximum_distance} m** desse ponto. Ele não documenta os candidatos externos, o corredor de deslocamento nem a posição revelada.

## Rastreabilidade e limites

O subprocesso visual foi realizado depois da abertura da referência e está corretamente identificado como retrospectivo e não confirmatório. A referência era conhecida pelo pesquisador, mas não foi fornecida ao motor de metadados ou ao cálculo de interseção. O pacote visual não alterou LOC, URG, DET, setores, pesos ou rankings.

O DOCX de campo e o arquivo `ground_truth_reservado_urbe01_PREENCHER.csv` são registros históricos anteriores ao fechamento. O CSV não foi utilizado e não deve ser preenchido retroativamente.

## Decisão de encerramento

Classificação final: **ENCERRADO_COM_RESULTADO_NEGATIVO_PRESERVADO**. O URBE-01 cumpre a função de piloto diagnóstico para aquisição, integridade, rastreabilidade, processamento espacial e avaliação pós-abertura. O próximo cenário deverá nascer já no protocolo integrado prospectivo, com caso e LOC congelados antes da revelação da posição reservada.
"""

    closure_qa_gates = {
        "blind_files_35_of_35_verified": blind_after["verified_count"] == 35,
        "blind_tree_unchanged_by_visual_audit": blind_before["tree_sha256"] == blind_after["tree_sha256"],
        "photos_10_of_10_verified": photo_verification["verified_count"] == 10,
        "post_opening_files_10_of_10_verified": post["verified_count"] == 10,
        "visual_audit_passed": qa["status"] == "PASS",
        "negative_top3_result_preserved": post["classification"] == "NAO_COBERTO_NO_TOP3_BASE_NEM_PERFIL",
        "rankings_not_recomputed": audit_manifest["rankings_recomputed"] is False,
        "sectors_not_recomputed": audit_manifest["sectors_recomputed"] is False,
        "visual_audit_does_not_affect_frozen_outputs": all(
            audit_manifest[field] is False
            for field in ("affects_loc", "affects_urg", "affects_frozen_det")
        ),
        "case_not_promoted_to_confirmatory": audit_manifest["confirmatory_eligible"] is False,
    }
    closure_qa = with_self_hash({
        "protocol_id": CLOSURE_PROTOCOL_ID,
        "scenario_id": SCENARIO_ID,
        "generated_at": generated_at,
        "status": "PASS" if all(closure_qa_gates.values()) else "FAIL",
        "gate_count": len(closure_qa_gates),
        "passed_gate_count": sum(closure_qa_gates.values()),
        "gates": closure_qa_gates,
        "final_classification": "ENCERRADO_COM_RESULTADO_NEGATIVO_PRESERVADO",
    })
    if closure_qa["status"] != "PASS":
        raise ClosureError("O fechamento formal falhou em um ou mais gates.")

    closure_dir.mkdir(parents=True, exist_ok=True)
    readme_path = closure_dir / "README_FECHAMENTO_URBE01_v1.md"
    matrix_path = closure_dir / "matriz_rastreabilidade_urbe01_v1.json"
    closure_report_path = closure_dir / "relatorio_fechamento_urbe01_v1.md"
    closure_qa_path = closure_dir / "relatorio_qa_fechamento_urbe01_v1.json"
    closure_manifest_path = closure_dir / "manifesto_fechamento_urbe01_v1.json"
    write_text(readme_path, readme)
    write_json(matrix_path, matrix)
    write_text(closure_report_path, closure_report)
    write_json(closure_qa_path, closure_qa)

    closure_files = [
        generated_file_entry(readme_path, "closure_readme"),
        generated_file_entry(matrix_path, "traceability_matrix"),
        generated_file_entry(closure_report_path, "closure_report"),
        generated_file_entry(closure_qa_path, "closure_qa"),
    ]
    closure_manifest = with_self_hash({
        "protocol_id": CLOSURE_PROTOCOL_ID,
        "scenario_id": SCENARIO_ID,
        "generated_at": generated_at,
        "final_classification": "ENCERRADO_COM_RESULTADO_NEGATIVO_PRESERVADO",
        "confirmatory_eligible": False,
        "general_efficiency_claim_allowed": False,
        "frozen_blind_package_modified": False,
        "rankings_recomputed": False,
        "sectors_recomputed": False,
        "weights_recomputed": False,
        "source_manifests": {
            "blind_manifest_sha256": blind_after["manifest_sha256"],
            "post_opening_manifest_sha256": post["manifest_sha256"],
            "visual_audit_manifest_sha256": audit_manifest["output_sha256"],
        },
        "files": closure_files,
    })
    write_json(closure_manifest_path, closure_manifest)

    return {
        "status": "PASS",
        "scenario_id": SCENARIO_ID,
        "final_classification": closure_manifest["final_classification"],
        "visual_qa_gates": qa["gate_count"],
        "closure_qa_gates": closure_qa["gate_count"],
        "photos_verified": photo_verification["verified_count"],
        "blind_files_verified": blind_after["verified_count"],
        "post_opening_files_verified": post["verified_count"],
        "qualified_visual_ids": summary_a["qualified_visual_ids"],
        "a05_sector_count": len(summary_a["a05_sector_ids"]),
        "audit_manifest": str(audit_manifest_path),
        "closure_manifest": str(closure_manifest_path),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT_DIR)
    result.add_argument("--closure-dir", type=Path, default=DEFAULT_CLOSURE_DIR)
    result.add_argument("--generated-at", required=True)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = build_package(args.audit_dir, args.closure_dir, args.generated_at)
    except (ClosureError, protocol.ProtocolError, OSError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
