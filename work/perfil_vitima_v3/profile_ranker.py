#!/usr/bin/env python3
"""Rankeador quantitativo prospectivo do módulo PERFIL V3.

Escopo propositalmente estreito: somente direção observada estruturada e
destino/lugar explicitamente georreferenciado podem alterar o ranking
territorial. Nenhuma estatística externa é convertida em peso ou distância.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import re
import unicodedata
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = (
    ROOT / "outputs" / "modulo_perfil_vitima_v3" / "config_perfil_quantitativo_v3.json"
)
ENGINE_ID = "PERFIL-V3-QUANT-RANKER-v1.1"
FREEZE_PROJECTION_ID = "PERFIL-V3-INPUT-FREEZE-PROJECTION-v1"
_EARTH_RADIUS_M = 6_371_008.8
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ProfileRankerError(ValueError):
    """Erro-base do rankeador."""


class GroundTruthFirewallError(ProfileRankerError):
    """A entrada contém marcador de ground truth ou equivalente."""


class InputValidationError(ProfileRankerError):
    """A entrada não satisfaz o contrato quantitativo."""


_ALLOWED_GT_KEY = "groundtruthabsent"
_FORBIDDEN_KEYS = {
    "groundtruth",
    "groundtruthlat",
    "groundtruthlatitude",
    "groundtruthlon",
    "groundtruthlongitude",
    "truelocation",
    "truecoordinate",
    "truecoordinates",
    "truelat",
    "truelatitude",
    "truelon",
    "truelongitude",
    "victimlat",
    "victimlatitude",
    "victimlon",
    "victimlongitude",
    "targetlat",
    "targetlatitude",
    "targetlon",
    "targetlongitude",
    "posicaoverdadeira",
    "localizacaoverdadeira",
    "localizacaoreal",
    "posicaoreal",
    "coordenadareal",
    "coordenadasreais",
    "latitudereal",
    "longitudereal",
    "referenciaverdadeira",
    "gabarito",
}
_FORBIDDEN_KEY_FRAGMENTS = (
    "groundtruth", "truelocation", "truecoordinate", "truelat", "truelon",
    "victimlat", "victimlon", "targetlat", "targetlon", "posicaoverdadeira",
    "posicaoreal", "localizacaoverdadeira", "localizacaoreal", "coordenadareal",
    "latitudereal", "longitudereal", "referenciaverdadeira", "gabarito",
)
_FORBIDDEN_TEXT = (
    re.compile(r"\bground[\s_-]*truth\b", re.IGNORECASE),
    re.compile(r"\btrue[\s_-]*(?:location|coordinate|latitude|longitude|lat|lon)\b", re.IGNORECASE),
    re.compile(r"\bvictim[\s_-]*(?:latitude|longitude|lat|lon)\b", re.IGNORECASE),
    re.compile(r"\bposi[cç][aã]o\s+verdadeira\b", re.IGNORECASE),
    re.compile(r"\blocaliza[cç][aã]o\s+(?:verdadeira|real)\b", re.IGNORECASE),
    re.compile(r"\bcoordenadas?\s+reais?\b", re.IGNORECASE),
    re.compile(r"\brefer[eê]ncia\s+verdadeira\b", re.IGNORECASE),
    re.compile(r"\bgabarito\s*[:=]", re.IGNORECASE),
)

_NATURE_FACTOR = {
    "CONFIRMADO": 1.0,
    "OBSERVADO": 1.0,
    "RELATADO": 2.0 / 3.0,
    "SUSPEITO": 1.0 / 3.0,
    "INFERIDO": 1.0 / 3.0,
    "NAO_DISPONIVEL": 0.0,
}
_CONFIDENCE_FACTOR = {
    "ALTA": 1.0,
    "MEDIA": 2.0 / 3.0,
    "BAIXA": 1.0 / 3.0,
    "NAO_AVALIADA": 0.0,
}
_ALLOWED_FAMILIES = {"DIRECAO", "DESTINO"}
_ALLOWED_TYPES = {
    "DIRECAO": {"DIRECAO_OBSERVADA"},
    "DESTINO": {"DESTINO_DECLARADO", "LUGAR_FAMILIAR"},
}


def _normalized_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", ascii_text.lower())


def enforce_ground_truth_firewall(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = _normalized_key(str(key))
            if normalized != _ALLOWED_GT_KEY and any(
                fragment in normalized for fragment in _FORBIDDEN_KEY_FRAGMENTS
            ):
                raise GroundTruthFirewallError(f"Chave proibida pelo firewall em {path}.{key}.")
            if normalized == _ALLOWED_GT_KEY and child is not True:
                raise GroundTruthFirewallError(
                    f"Controle ground_truth_absent deve ser true em {path}.{key}."
                )
            enforce_ground_truth_firewall(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            enforce_ground_truth_firewall(child, f"{path}[{index}]")
    elif isinstance(value, str) and any(pattern.search(value) for pattern in _FORBIDDEN_TEXT):
        raise GroundTruthFirewallError(f"Marcador textual proibido pelo firewall em {path}.")


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def freeze_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    projected = deepcopy(dict(payload))
    metadata = projected.get("freeze_metadata")
    if not isinstance(metadata, Mapping):
        raise InputValidationError("freeze_metadata ausente para projeção de congelamento.")
    projected["freeze_metadata"] = dict(metadata)
    projected["freeze_metadata"].pop("payload_sha256", None)
    return projected


def calculate_freeze_sha256(payload: Mapping[str, Any]) -> str:
    return canonical_sha256(freeze_projection(payload))


def prepare_frozen_input(payload: Mapping[str, Any], frozen_at: str) -> dict[str, Any]:
    frozen = deepcopy(dict(payload))
    frozen["record_status"] = "CONGELADO"
    frozen["freeze_metadata"] = {
        "frozen_at": frozen_at,
        "projection_id": FREEZE_PROJECTION_ID,
        "payload_sha256": "0" * 64,
    }
    frozen["freeze_metadata"]["payload_sha256"] = calculate_freeze_sha256(frozen)
    validate_input(frozen)
    return frozen


def _parse_datetime(value: str, path: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise InputValidationError(f"{path}: data/hora inválida.") from exc
    if parsed.utcoffset() is None:
        raise InputValidationError(f"{path}: fuso horário obrigatório.")
    return parsed


def _require_keys(obj: Mapping[str, Any], required: Iterable[str], path: str) -> None:
    for key in required:
        if key not in obj:
            raise InputValidationError(f"{path}: campo obrigatório ausente: {key}")


def _reject_extra_keys(obj: Mapping[str, Any], allowed: Iterable[str], path: str) -> None:
    extras = sorted(set(obj) - set(allowed))
    if extras:
        raise InputValidationError(f"{path}: campos não permitidos: {', '.join(extras)}")


def _finite_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputValidationError(f"{path}: número esperado.")
    number = float(value)
    if not math.isfinite(number):
        raise InputValidationError(f"{path}: número deve ser finito.")
    return number


def _validate_identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise InputValidationError(
            f"{path}: identificador deve seguir ^[A-Za-z0-9][A-Za-z0-9._:-]{{0,127}}$."
        )
    return value


def _validate_polygon(polygon: Any, path: str) -> list[list[float]]:
    if not isinstance(polygon, list) or len(polygon) < 4:
        raise InputValidationError(f"{path}: polígono requer ao menos quatro vértices.")
    result: list[list[float]] = []
    for index, pair in enumerate(polygon):
        if not isinstance(pair, list) or len(pair) != 2:
            raise InputValidationError(f"{path}[{index}]: coordenada [lon, lat] esperada.")
        lon = _finite_number(pair[0], f"{path}[{index}][0]")
        lat = _finite_number(pair[1], f"{path}[{index}][1]")
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            raise InputValidationError(f"{path}[{index}]: coordenada fora do WGS 84.")
        result.append([lon, lat])
    if result[0] != result[-1]:
        raise InputValidationError(f"{path}: polígono deve estar fechado.")
    unwrapped_longitudes: list[float] = []
    for lon, _lat in result:
        adjusted = lon
        if unwrapped_longitudes:
            while adjusted - unwrapped_longitudes[-1] > 180.0:
                adjusted -= 360.0
            while adjusted - unwrapped_longitudes[-1] < -180.0:
                adjusted += 360.0
        unwrapped_longitudes.append(adjusted)
    twice_area = sum(
        unwrapped_longitudes[index] * result[index + 1][1]
        - unwrapped_longitudes[index + 1] * result[index][1]
        for index in range(len(result) - 1)
    )
    if math.isclose(twice_area, 0.0, rel_tol=0.0, abs_tol=1e-15):
        raise InputValidationError(f"{path}: polígono degenerado com área nula.")
    return result


def validate_input(payload: Mapping[str, Any]) -> None:
    enforce_ground_truth_firewall(payload)
    top_level_keys = (
        "protocol_version",
        "scenario_id",
        "candidate_id",
        "record_status",
        "created_at",
        "ground_truth_absent",
        "source_loc_input_sha256",
        "source_case_revision",
        "source_profile_compiled_sha256",
        "source_territorial_manifest_sha256",
        "source_spatial_review_sha256",
        "sectors",
        "hypotheses",
        "freeze_metadata",
    )
    _require_keys(
        payload,
        top_level_keys,
        "$",
    )
    _reject_extra_keys(payload, top_level_keys, "$")
    if payload["protocol_version"] != "PERFIL-V3-QUANT-v1.0":
        raise InputValidationError("$.protocol_version: versão inesperada.")
    scenario_id = _validate_identifier(payload["scenario_id"], "$.scenario_id")
    candidate_id = _validate_identifier(payload["candidate_id"], "$.candidate_id")
    if payload["record_status"] != "CONGELADO":
        raise InputValidationError("Somente entrada CONGELADA pode ser ranqueada.")
    if payload["ground_truth_absent"] is not True:
        raise InputValidationError("ground_truth_absent deve ser true.")
    created_at = _parse_datetime(str(payload["created_at"]), "$.created_at")
    for key in (
        "source_loc_input_sha256",
        "source_profile_compiled_sha256",
        "source_territorial_manifest_sha256",
    ):
        if not isinstance(payload[key], str) or re.fullmatch(r"[0-9a-f]{64}", payload[key]) is None:
            raise InputValidationError(f"$.{key}: SHA-256 hexadecimal minúsculo esperado.")
    if (
        not isinstance(payload["source_case_revision"], int)
        or isinstance(payload["source_case_revision"], bool)
        or payload["source_case_revision"] < 1
    ):
        raise InputValidationError("$.source_case_revision: inteiro positivo esperado.")
    review_sha = payload["source_spatial_review_sha256"]
    if review_sha is not None and (
        not isinstance(review_sha, str) or re.fullmatch(r"[0-9a-f]{64}", review_sha) is None
    ):
        raise InputValidationError("$.source_spatial_review_sha256: SHA-256 ou null esperado.")

    metadata = payload["freeze_metadata"]
    if not isinstance(metadata, Mapping):
        raise InputValidationError("$.freeze_metadata: objeto esperado.")
    _require_keys(metadata, ("frozen_at", "projection_id", "payload_sha256"), "$.freeze_metadata")
    _reject_extra_keys(metadata, ("frozen_at", "projection_id", "payload_sha256"), "$.freeze_metadata")
    frozen_at = _parse_datetime(str(metadata["frozen_at"]), "$.freeze_metadata.frozen_at")
    if frozen_at < created_at:
        raise InputValidationError("Congelamento não pode anteceder a criação da entrada.")
    if metadata["projection_id"] != FREEZE_PROJECTION_ID:
        raise InputValidationError("Projeção de congelamento inesperada.")
    declared = str(metadata["payload_sha256"])
    if re.fullmatch(r"[0-9a-f]{64}", declared) is None:
        raise InputValidationError("Hash de congelamento inválido.")
    expected = calculate_freeze_sha256(payload)
    if not hmac.compare_digest(declared, expected):
        raise InputValidationError("Hash de congelamento não confere; pacote alterado.")

    sectors = payload["sectors"]
    if not isinstance(sectors, list) or len(sectors) < 2:
        raise InputValidationError("$.sectors: ao menos dois setores são necessários.")
    sector_ids: set[str] = set()
    for index, sector in enumerate(sectors):
        path = f"$.sectors[{index}]"
        if not isinstance(sector, Mapping):
            raise InputValidationError(f"{path}: objeto esperado.")
        _require_keys(
            sector,
            ("sector_id", "territorial_score", "bearing_start_deg", "bearing_end_deg", "polygon"),
            path,
        )
        _reject_extra_keys(
            sector,
            ("sector_id", "territorial_score", "bearing_start_deg", "bearing_end_deg", "polygon"),
            path,
        )
        sector_id = _validate_identifier(sector["sector_id"], f"{path}.sector_id")
        if sector_id in sector_ids:
            raise InputValidationError(f"{path}.sector_id: duplicado.")
        sector_ids.add(sector_id)
        score = _finite_number(sector["territorial_score"], f"{path}.territorial_score")
        if not 0 <= score <= 1:
            raise InputValidationError(f"{path}.territorial_score: fora de [0,1].")
        bearing_values: dict[str, float] = {}
        for field in ("bearing_start_deg", "bearing_end_deg"):
            bearing = _finite_number(sector[field], f"{path}.{field}")
            if not 0 <= bearing <= 360:
                raise InputValidationError(f"{path}.{field}: fora de [0,360].")
            bearing_values[field] = bearing
        if math.isclose(
            bearing_values["bearing_start_deg"] % 360.0,
            bearing_values["bearing_end_deg"] % 360.0,
            abs_tol=1e-12,
        ):
            raise InputValidationError(f"{path}: setor com largura angular nula ou ambígua.")
        _validate_polygon(sector["polygon"], f"{path}.polygon")

    hypotheses = payload["hypotheses"]
    if not isinstance(hypotheses, list):
        raise InputValidationError("$.hypotheses: lista esperada.")
    if hypotheses and review_sha is None:
        raise InputValidationError("Hipóteses incluídas exigem source_spatial_review_sha256.")
    hypothesis_ids: set[str] = set()
    group_evidence: dict[tuple[str, str], tuple[str, str]] = {}
    global_group_family: dict[str, str] = {}
    for index, hypothesis in enumerate(hypotheses):
        path = f"$.hypotheses[{index}]"
        if not isinstance(hypothesis, Mapping):
            raise InputValidationError(f"{path}: objeto esperado.")
        _require_keys(
            hypothesis,
            (
                "hypothesis_id",
                "evidence_group_id",
                "family",
                "hypothesis_type",
                "spatialized",
                "authorized_for_model",
                "nature",
                "confidence",
            ),
            path,
        )
        hypothesis_id = _validate_identifier(
            hypothesis["hypothesis_id"], f"{path}.hypothesis_id"
        )
        if hypothesis_id in hypothesis_ids:
            raise InputValidationError(f"{path}.hypothesis_id: duplicado.")
        hypothesis_ids.add(hypothesis_id)
        group_id = _validate_identifier(
            hypothesis["evidence_group_id"], f"{path}.evidence_group_id"
        )
        family = str(hypothesis["family"])
        if family not in _ALLOWED_FAMILIES:
            raise InputValidationError(f"{path}.family: efeito quantitativo não permitido.")
        allowed_hypothesis_keys = {
            "hypothesis_id",
            "evidence_group_id",
            "family",
            "hypothesis_type",
            "spatialized",
            "authorized_for_model",
            "nature",
            "confidence",
            "direction" if family == "DIRECAO" else "destination",
        }
        _reject_extra_keys(hypothesis, allowed_hypothesis_keys, path)
        if hypothesis["hypothesis_type"] not in _ALLOWED_TYPES[family]:
            raise InputValidationError(f"{path}.hypothesis_type: incompatível com a família.")
        if not isinstance(hypothesis["spatialized"], bool):
            raise InputValidationError(f"{path}.spatialized: booleano esperado.")
        if not isinstance(hypothesis["authorized_for_model"], bool):
            raise InputValidationError(f"{path}.authorized_for_model: booleano esperado.")
        nature = str(hypothesis["nature"])
        confidence = str(hypothesis["confidence"])
        if nature not in _NATURE_FACTOR or confidence not in _CONFIDENCE_FACTOR:
            raise InputValidationError(f"{path}: natureza ou confiança inválida.")
        group_key = (family, group_id)
        if group_id in global_group_family and global_group_family[group_id] != family:
            raise InputValidationError(
                f"{path}: evidence_group_id não pode acumular influência em famílias diferentes."
            )
        global_group_family[group_id] = family
        evidence_pair = (nature, confidence)
        if group_key in group_evidence and group_evidence[group_key] != evidence_pair:
            raise InputValidationError(f"{path}: mesmo grupo de evidência com classificação divergente.")
        group_evidence[group_key] = evidence_pair

        if family == "DIRECAO":
            _require_keys(hypothesis, ("direction",), path)
            direction = hypothesis["direction"]
            if not isinstance(direction, Mapping):
                raise InputValidationError(f"{path}.direction: objeto esperado.")
            _require_keys(
                direction,
                ("origin_candidate_id", "azimuth_deg", "tolerance_deg"),
                f"{path}.direction",
            )
            _reject_extra_keys(
                direction,
                ("origin_candidate_id", "azimuth_deg", "tolerance_deg"),
                f"{path}.direction",
            )
            origin_candidate_id = _validate_identifier(
                direction["origin_candidate_id"],
                f"{path}.direction.origin_candidate_id",
            )
            if origin_candidate_id != candidate_id:
                raise InputValidationError(
                    f"{path}.direction.origin_candidate_id: deve coincidir com $.candidate_id."
                )
            azimuth = _finite_number(direction["azimuth_deg"], f"{path}.direction.azimuth_deg")
            tolerance = _finite_number(direction["tolerance_deg"], f"{path}.direction.tolerance_deg")
            if not 0 <= azimuth < 360 or not 0 < tolerance <= 180:
                raise InputValidationError(f"{path}.direction: azimute/tolerância inválidos.")
        else:
            _require_keys(hypothesis, ("destination",), path)
            destination = hypothesis["destination"]
            if not isinstance(destination, Mapping):
                raise InputValidationError(f"{path}.destination: objeto esperado.")
            _require_keys(
                destination,
                ("latitude", "longitude", "location_uncertainty_m", "spatial_source"),
                f"{path}.destination",
            )
            _reject_extra_keys(
                destination,
                ("latitude", "longitude", "location_uncertainty_m", "spatial_source"),
                f"{path}.destination",
            )
            lat = _finite_number(destination["latitude"], f"{path}.destination.latitude")
            lon = _finite_number(destination["longitude"], f"{path}.destination.longitude")
            uncertainty = _finite_number(
                destination["location_uncertainty_m"], f"{path}.destination.location_uncertainty_m"
            )
            if not -90 < lat < 90 or not -180 <= lon <= 180 or uncertainty < 0:
                raise InputValidationError(f"{path}.destination: valores espaciais inválidos.")
            spatial_source = destination["spatial_source"]
            if (
                not isinstance(spatial_source, str)
                or not spatial_source.strip()
                or len(spatial_source) > 256
            ):
                raise InputValidationError(
                    f"{path}.destination.spatial_source: string não vazia de até 256 caracteres esperada."
                )


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("protocol_id") != "PERFIL-V3-QUANT-v1.0":
        raise InputValidationError("Configuração quantitativa inesperada.")
    if config.get("engine_id") != ENGINE_ID:
        raise InputValidationError("Configuração referencia versão inesperada do motor.")
    if config.get("status") not in {"CANDIDATO_A_CONGELAMENTO", "CONGELADO"}:
        raise InputValidationError(
            "Configuração deve estar marcada como CANDIDATO_A_CONGELAMENTO ou CONGELADO."
        )
    scoring = config.get("scoring", {})
    if scoring.get("lambda_primary") != 0.10:
        raise InputValidationError("lambda principal deve ser 0,10 nesta versão candidata.")
    if scoring.get("lambda_operational_ceiling") != 0.10:
        raise InputValidationError("teto heurístico operacional deve ser 0,10.")
    if scoring.get("lambda_sensitivity") != [0.0, 0.05, 0.1, 0.15]:
        raise InputValidationError("Grade de sensibilidade inesperada.")
    attenuation = config.get("evidence_attenuation", {})
    if attenuation.get("nature_factor") != _NATURE_FACTOR:
        raise InputValidationError("Fatores de natureza divergem do motor.")
    if attenuation.get("confidence_factor") != _CONFIDENCE_FACTOR:
        raise InputValidationError("Fatores de confiança divergem do motor.")
    if set(config.get("allowed_quantitative_families", [])) != _ALLOWED_FAMILIES:
        raise InputValidationError("Famílias quantitativas divergem do motor.")
    ranking = config.get("ranking", {})
    expected_ranking = {
        "method": "COMPETITION_RANK",
        "score_comparison_decimals": 12,
        "tie_break_is_substantive": False,
        "low_margin_threshold_diagnostic": 0.05,
        "low_margin_is_validated": False,
        "unstable_top_set_status": "REVISAR_INSTABILIDADE",
        "unstable_top_set_operational_effect": False,
        "unstable_top_set_operational_rows": "TERRITORIAL_EXACT",
    }
    for field, expected_value in expected_ranking.items():
        actual_value = ranking.get(field)
        if field == "score_comparison_decimals" and isinstance(actual_value, bool):
            raise InputValidationError("Precisão de comparação do ranking inválida.")
        if actual_value != expected_value:
            raise InputValidationError(f"$.ranking.{field}: valor diverge do motor.")
    spatial = config.get("spatial_rules", {})
    if spatial.get("destination_uncertainty_method") != (
        "LOCAL_EQUIRECTANGULAR_BINARY_CIRCLE_POLYGON_INTERSECTION"
    ):
        raise InputValidationError("Método de incerteza do destino diverge do motor.")
    earth_radius = _finite_number(spatial.get("earth_radius_m"), "$.spatial_rules.earth_radius_m")
    if not math.isclose(earth_radius, _EARTH_RADIUS_M, rel_tol=0.0, abs_tol=1e-9):
        raise InputValidationError("Raio terrestre da projeção local diverge do motor.")
    return config


def _angular_segments(start: float, end: float) -> list[tuple[float, float]]:
    start = start % 360.0
    end = end % 360.0
    if math.isclose(start, end, abs_tol=1e-12):
        raise InputValidationError("Intervalo angular com largura nula ou ambígua.")
    if start < end:
        return [(start, end)]
    return [(start, 360.0), (0.0, end)]


def _wedge_segments(azimuth: float, tolerance: float) -> list[tuple[float, float]]:
    if tolerance >= 180.0:
        return [(0.0, 360.0)]
    return _angular_segments(azimuth - tolerance, azimuth + tolerance)


def _overlap_length(first: Sequence[tuple[float, float]], second: Sequence[tuple[float, float]]) -> float:
    total = 0.0
    for a_start, a_end in first:
        for b_start, b_end in second:
            total += max(0.0, min(a_end, b_end) - max(a_start, b_start))
    return total


def direction_compatibility(sector: Mapping[str, Any], direction: Mapping[str, Any]) -> float:
    sector_segments = _angular_segments(
        float(sector["bearing_start_deg"]), float(sector["bearing_end_deg"])
    )
    sector_width = sum(end - start for start, end in sector_segments)
    wedge = _wedge_segments(float(direction["azimuth_deg"]), float(direction["tolerance_deg"]))
    if sector_width <= 0:
        raise InputValidationError("Setor com largura angular nula.")
    return min(1.0, max(0.0, _overlap_length(sector_segments, wedge) / sector_width))


def _point_on_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> bool:
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > 1e-12:
        return False
    dot = (px - ax) * (bx - ax) + (py - ay) * (by - ay)
    if dot < -1e-12:
        return False
    squared = (bx - ax) ** 2 + (by - ay) ** 2
    return dot <= squared + 1e-12


def _point_in_polygon_xy(x: float, y: float, polygon: Sequence[Sequence[float]]) -> bool:
    inside = False
    for index in range(len(polygon) - 1):
        ax, ay = float(polygon[index][0]), float(polygon[index][1])
        bx, by = float(polygon[index + 1][0]), float(polygon[index + 1][1])
        if _point_on_segment(x, y, ax, ay, bx, by):
            return True
        if (ay > y) != (by > y):
            x_cross = (bx - ax) * (y - ay) / (by - ay) + ax
            if x < x_cross:
                inside = not inside
    return inside


def _wrap_longitude_delta_deg(delta: float) -> float:
    wrapped = (delta + 180.0) % 360.0 - 180.0
    if math.isclose(wrapped, -180.0, abs_tol=1e-12) and delta > 0:
        return 180.0
    return wrapped


def _project_polygon_local_equirectangular(
    center_lon: float,
    center_lat: float,
    polygon: Sequence[Sequence[float]],
    earth_radius_m: float,
) -> list[list[float]]:
    """Projeta um polígono em metros ao redor do destino, com desembrulho antimeridiano."""
    if not -90.0 < center_lat < 90.0:
        raise InputValidationError("Projeção local não aceita centro exatamente nos polos.")
    raw_deltas = [
        _wrap_longitude_delta_deg(float(pair[0]) - center_lon) for pair in polygon
    ]
    unwrapped: list[float] = []
    for raw in raw_deltas:
        adjusted = raw
        if unwrapped:
            while adjusted - unwrapped[-1] > 180.0:
                adjusted -= 360.0
            while adjusted - unwrapped[-1] < -180.0:
                adjusted += 360.0
        unwrapped.append(adjusted)
    cosine = math.cos(math.radians(center_lat))
    return [
        [
            earth_radius_m * math.radians(delta_lon) * cosine,
            earth_radius_m * math.radians(float(pair[1]) - center_lat),
        ]
        for pair, delta_lon in zip(polygon, unwrapped)
    ]


def _distance_origin_to_segment(ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    squared_length = dx * dx + dy * dy
    if squared_length <= 1e-24:
        return math.hypot(ax, ay)
    position = max(0.0, min(1.0, -(ax * dx + ay * dy) / squared_length))
    return math.hypot(ax + position * dx, ay + position * dy)


def point_in_polygon(lon: float, lat: float, polygon: Sequence[Sequence[float]]) -> bool:
    """Inclui a borda e trata polígonos locais que cruzam o antimeridiano."""
    projected = _project_polygon_local_equirectangular(
        lon, lat, polygon, _EARTH_RADIUS_M
    )
    return _point_in_polygon_xy(0.0, 0.0, projected)


def destination_compatibility(
    sector: Mapping[str, Any],
    destination: Mapping[str, Any],
    earth_radius_m: float = _EARTH_RADIUS_M,
) -> float:
    """Compatibilidade binária pela interseção círculo de incerteza × setor."""
    lon = float(destination["longitude"])
    lat = float(destination["latitude"])
    radius = float(destination.get("location_uncertainty_m", 0.0))
    projected = _project_polygon_local_equirectangular(
        lon, lat, sector["polygon"], earth_radius_m
    )
    if _point_in_polygon_xy(0.0, 0.0, projected):
        return 1.0
    minimum_distance = min(
        _distance_origin_to_segment(
            float(projected[index][0]),
            float(projected[index][1]),
            float(projected[index + 1][0]),
            float(projected[index + 1][1]),
        )
        for index in range(len(projected) - 1)
    )
    return 1.0 if minimum_distance <= radius + 1e-9 else 0.0


def evidence_quality(hypothesis: Mapping[str, Any]) -> float:
    return min(
        _NATURE_FACTOR[str(hypothesis["nature"])],
        _CONFIDENCE_FACTOR[str(hypothesis["confidence"])],
    )


def _competition_ranks(rows: list[dict[str, Any]], score_field: str, decimals: int) -> None:
    ordered = sorted(rows, key=lambda item: (-round(float(item[score_field]), decimals), item["sector_id"]))
    previous: float | None = None
    previous_rank = 0
    for position, row in enumerate(ordered, start=1):
        score = round(float(row[score_field]), decimals)
        if previous is None or score != previous:
            previous_rank = position
            previous = score
        row[score_field.replace("score", "rank")] = previous_rank


def _top_set(rows: Sequence[Mapping[str, Any]], score_field: str, decimals: int) -> list[str]:
    top = max(round(float(row[score_field]), decimals) for row in rows)
    return sorted(
        str(row["sector_id"])
        for row in rows
        if round(float(row[score_field]), decimals) == top
    )


def _circular_distance(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _direction_conflict(hypotheses: Sequence[Mapping[str, Any]]) -> bool:
    directions = [
        hypothesis
        for hypothesis in hypotheses
        if hypothesis["family"] == "DIRECAO"
        and hypothesis["authorized_for_model"] is True
        and hypothesis["spatialized"] is True
        and evidence_quality(hypothesis) > 0
    ]
    for left_index, left in enumerate(directions):
        for right in directions[left_index + 1 :]:
            if left["evidence_group_id"] == right["evidence_group_id"]:
                continue
            left_dir, right_dir = left["direction"], right["direction"]
            separation = _circular_distance(
                float(left_dir["azimuth_deg"]), float(right_dir["azimuth_deg"])
            )
            if separation > float(left_dir["tolerance_deg"]) + float(right_dir["tolerance_deg"]):
                return True
    return False


def rank_profile(
    payload: Mapping[str, Any],
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    validate_input(payload)
    config = load_config(config_path)
    earth_radius_m = float(config["spatial_rules"]["earth_radius_m"])
    sectors = [deepcopy(dict(sector)) for sector in payload["sectors"]]
    hypotheses = [deepcopy(dict(item)) for item in payload["hypotheses"]]
    warnings: list[str] = []
    excluded: list[dict[str, Any]] = []
    group_members: dict[tuple[str, str], list[tuple[Mapping[str, Any], float, list[float]]]] = {}

    for hypothesis in hypotheses:
        q = evidence_quality(hypothesis)
        reason: str | None = None
        if not hypothesis["authorized_for_model"]:
            reason = "NAO_AUTORIZADA"
        elif not hypothesis["spatialized"]:
            reason = "NAO_ESPACIALIZADA"
        elif q <= 0:
            reason = "QUALIDADE_SEM_EFEITO"

        compatibilities: list[float] = []
        if reason is None:
            if hypothesis["family"] == "DIRECAO":
                compatibilities = [direction_compatibility(sector, hypothesis["direction"]) for sector in sectors]
            else:
                compatibilities = [
                    destination_compatibility(
                        sector,
                        hypothesis["destination"],
                        earth_radius_m,
                    )
                    for sector in sectors
                ]
                if not any(value > 0 for value in compatibilities):
                    reason = "DESTINO_FORA_DO_DOMINIO"
                    warnings.append("DESTINO_FORA_DO_DOMINIO_SEM_PROJECAO_A_BORDA")

        if reason is not None:
            excluded.append(
                {
                    "hypothesis_id": hypothesis["hypothesis_id"],
                    "evidence_group_id": hypothesis["evidence_group_id"],
                    "reason": reason,
                }
            )
            continue
        if max(compatibilities) - min(compatibilities) <= 1e-12:
            nondiscrimination_reason = "COMPATIBILIDADE_NAO_DISCRIMINANTE"
            if (
                hypothesis["family"] == "DESTINO"
                and float(hypothesis["destination"]["location_uncertainty_m"]) > 0.0
            ):
                nondiscrimination_reason = "INCERTEZA_DESTINO_NAO_DISCRIMINANTE"
                warnings.append("INCERTEZA_DESTINO_NAO_DISCRIMINANTE_REVISAR")
            excluded.append(
                {
                    "hypothesis_id": hypothesis["hypothesis_id"],
                    "evidence_group_id": hypothesis["evidence_group_id"],
                    "reason": nondiscrimination_reason,
                }
            )
            continue
        key = (str(hypothesis["family"]), str(hypothesis["evidence_group_id"]))
        group_members.setdefault(key, []).append((hypothesis, q, compatibilities))

    if _direction_conflict(hypotheses):
        warnings.append("DIRECOES_INDEPENDENTES_CONFLITANTES_REVISAR")

    group_records: list[dict[str, Any]] = []
    for (family, group_id), members in sorted(group_members.items()):
        q_values = {round(item[1], 12) for item in members}
        if len(q_values) != 1:
            raise InputValidationError("Grupo de evidência com qualidade divergente.")
        q = members[0][1]
        union = [max(member[2][index] for member in members) for index in range(len(sectors))]
        group_records.append(
            {
                "family": family,
                "evidence_group_id": group_id,
                "q": q,
                "hypothesis_ids": sorted(str(member[0]["hypothesis_id"]) for member in members),
                "compatibility": union,
                "duplicates_or_alternatives_collapsed": max(0, len(members) - 1),
            }
        )

    family_records: list[dict[str, Any]] = []
    for family in sorted(_ALLOWED_FAMILIES):
        members = [group for group in group_records if group["family"] == family]
        if not members:
            continue
        q_family = max(float(group["q"]) for group in members)
        compatibility = [
            max(float(group["q"]) * float(group["compatibility"][index]) for group in members)
            / q_family
            for index in range(len(sectors))
        ]
        family_records.append(
            {
                "family": family,
                "q_family": q_family,
                "compatibility": compatibility,
                "evidence_group_ids": sorted(str(group["evidence_group_id"]) for group in members),
            }
        )

    abstained = False
    abstention_reason: str | None = None
    if not family_records:
        abstained = True
        abstention_reason = "SEM_HIPOTESE_ESPACIAL_QUANTITATIVA_ELEGIVEL"
        compatibility_profile = [0.0 for _ in sectors]
    else:
        denominator = sum(float(family["q_family"]) for family in family_records)
        profile_strength = max(float(family["q_family"]) for family in family_records)
        compatibility_profile = [
            sum(
                float(family["q_family"]) * float(family["compatibility"][index])
                for family in family_records
            )
            / denominator
            for index in range(len(sectors))
        ]
        if max(compatibility_profile) - min(compatibility_profile) <= 1e-12:
            abstained = True
            abstention_reason = "PERFIL_NAO_DISCRIMINA_SETORES"

    if not family_records:
        profile_strength = 0.0

    decimals = int(config["ranking"]["score_comparison_decimals"])
    lambda_results: list[dict[str, Any]] = []
    primary_rows: list[dict[str, Any]] | None = None
    for lambda_value in config["scoring"]["lambda_sensitivity"]:
        rows: list[dict[str, Any]] = []
        for index, sector in enumerate(sectors):
            territorial = float(sector["territorial_score"])
            if abstained or math.isclose(float(lambda_value), 0.0, abs_tol=1e-15):
                score = territorial
                effective_lambda = 0.0
            else:
                effective_lambda = float(lambda_value) * profile_strength
                score = (1.0 - effective_lambda) * territorial + effective_lambda * float(
                    compatibility_profile[index]
                )
            rows.append(
                {
                    "sector_id": str(sector["sector_id"]),
                    "territorial_score": territorial,
                    "profile_compatibility": float(compatibility_profile[index]),
                    "evidence_strength": profile_strength,
                    "effective_lambda": effective_lambda,
                    "profile_score": score,
                    "profile_delta": score - territorial,
                }
            )
        _competition_ranks(rows, "territorial_score", decimals)
        _competition_ranks(rows, "profile_score", decimals)
        top_set = _top_set(rows, "profile_score", decimals)
        ordered_scores = sorted((float(row["profile_score"]) for row in rows), reverse=True)
        margin = ordered_scores[0] - ordered_scores[1] if len(ordered_scores) > 1 else None
        lambda_record = {
            "lambda": float(lambda_value),
            "role": (
                "ABLACAO_TERRITORIAL"
                if math.isclose(float(lambda_value), 0.0)
                else "PRINCIPAL"
                if math.isclose(float(lambda_value), float(config["scoring"]["lambda_primary"]))
                else "SENSIBILIDADE"
                if float(lambda_value) <= float(config["scoring"]["lambda_operational_ceiling"])
                else "ESTRESSE_FORA_DO_TETO_OPERACIONAL"
            ),
            "effect_applied": not abstained and float(lambda_value) > 0,
            "top_set": top_set,
            "top_unique": len(top_set) == 1,
            "margin_top1_top2": margin,
            "rows": sorted(rows, key=lambda row: (row["profile_rank"], row["sector_id"])),
        }
        lambda_results.append(lambda_record)
        if math.isclose(float(lambda_value), float(config["scoring"]["lambda_primary"])):
            primary_rows = lambda_record["rows"]

    if primary_rows is None:
        raise InputValidationError("Configuração não produziu resultado principal.")

    nonzero_top_sets = {
        tuple(record["top_set"])
        for record in lambda_results
        if 0 < float(record["lambda"]) <= float(config["scoring"]["lambda_operational_ceiling"])
    }
    stable_within_ceiling = len(nonzero_top_sets) <= 1
    if not stable_within_ceiling:
        warnings.append("TOP1_INSTAVEL_NA_FAIXA_OPERACIONAL_REVISAR")
    primary_record = next(record for record in lambda_results if record["role"] == "PRINCIPAL")
    territorial_record = next(
        record for record in lambda_results if record["role"] == "ABLACAO_TERRITORIAL"
    )
    if abstained:
        operational_effect_applied = False
        operational_status = "ABSTENCAO_PERFIL"
        operational_rows = deepcopy(territorial_record["rows"])
    elif not stable_within_ceiling:
        operational_effect_applied = False
        operational_status = "REVISAR_INSTABILIDADE"
        operational_rows = deepcopy(territorial_record["rows"])
    else:
        operational_effect_applied = True
        operational_status = "EFEITO_PERFIL_APLICADO"
        operational_rows = deepcopy(primary_record["rows"])
    if not primary_record["top_unique"]:
        warnings.append("SEM_TOP1_UNICO_REVISAR")
    margin = primary_record["margin_top1_top2"]
    if margin is not None and margin < float(config["ranking"]["low_margin_threshold_diagnostic"]):
        warnings.append("MARGEM_BAIXA_DIAGNOSTICA_REVISAR")

    result: dict[str, Any] = {
        "engine_id": ENGINE_ID,
        "protocol_id": config["protocol_id"],
        "config_status": config["status"],
        "scenario_id": payload["scenario_id"],
        "candidate_id": payload["candidate_id"],
        "mode": "QUANTITATIVO_PROSPECTIVO_LIMITADO",
        "ground_truth_absent": True,
        "source_loc_input_sha256": payload["source_loc_input_sha256"],
        "source_case_revision": payload["source_case_revision"],
        "input_sha256": canonical_sha256(payload),
        "config_sha256": canonical_sha256(config),
        "source_profile_compiled_sha256": payload["source_profile_compiled_sha256"],
        "source_territorial_manifest_sha256": payload["source_territorial_manifest_sha256"],
        "source_spatial_review_sha256": payload["source_spatial_review_sha256"],
        "abstained": abstained,
        "abstention_reason": abstention_reason,
        "warnings": sorted(set(warnings)),
        "evidence_quality_policy": "q=min(natureza,confianca); níveis 0,1/3,2/3,1",
        "aggregation_policy": "max no grupo; max atenuado na família; média entre famílias por q_f",
        "group_records": group_records,
        "family_records": family_records,
        "excluded_hypotheses": excluded,
        "lambda_results": lambda_results,
        "primary_lambda": config["scoring"]["lambda_primary"],
        "primary_rows": primary_rows,
        "operational_effect_applied": operational_effect_applied,
        "operational_status": operational_status,
        "operational_rows": operational_rows,
        "sector_order": [str(sector["sector_id"]) for sector in sectors],
        "stability": {
            "top_set_stable_within_operational_ceiling": stable_within_ceiling,
            "operational_lambdas_compared": [0.05, 0.1],
        },
        "scope_guards": {
            "allowed_quantitative_families": sorted(_ALLOWED_FAMILIES),
            "mobility_weighted": False,
            "cognition_weighted": False,
            "age_weighted": False,
            "personality_weighted": False,
            "urgency_weighted": False,
            "external_statistics_used_as_weights_or_distances": False,
            "destination_uncertainty_used_as_binary_geometry": True,
            "destination_uncertainty_converted_to_decay_or_weight": False,
            "destination_outside_domain_projected_to_edge": False,
            "direction_origin_bound_to_candidate": True,
            "cross_candidate_ranking": False,
            "score_is_probability": False,
            "source_hash_format_validated": True,
            "source_artifact_content_hash_recomputed": False,
        },
        "firewall_manifest": {
            "recursive_key_scan": True,
            "explicit_text_marker_scan": True,
            "freeze_hash_verified": True,
            "status": "PASS",
        },
    }
    result["output_sha256"] = canonical_sha256(result)
    return result


def load_input(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise InputValidationError("A raiz da entrada deve ser um objeto JSON.")
    return value


def write_output(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rankeador quantitativo PERFIL V3")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--prepare-freeze", action="store_true")
    parser.add_argument("--frozen-at")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = load_input(args.input)
    if args.prepare_freeze:
        if args.output is None or args.frozen_at is None:
            raise SystemExit("--prepare-freeze exige --output e --frozen-at.")
        if args.output.resolve() == args.input.resolve():
            raise SystemExit("A saída congelada deve ser diferente da entrada.")
        frozen = prepare_frozen_input(payload, args.frozen_at)
        write_output(args.output, frozen)
        return 0
    result = rank_profile(payload, args.config)
    if args.output is None:
        print(canonical_json_bytes(result).decode("utf-8"), end="")
    else:
        write_output(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

