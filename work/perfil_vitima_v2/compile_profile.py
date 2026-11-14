#!/usr/bin/env python3
"""Compilador qualitativo do perfil da pessoa procurada — V2.

Este módulo lê o contrato ``perfil_vitima_v2.schema.json`` e transforma
somente fatos e pistas autorizados em hipóteses explícitas. Ele não calcula
pesos, escores ou rankings e rejeita qualquer chave que possa transportar a
posição verdadeira antes do congelamento das saídas.
"""

from __future__ import annotations

import argparse
import hmac
import hashlib
import json
import re
import unicodedata
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA_PATH = (
    ROOT / "outputs" / "modulo_perfil_vitima_v2" / "perfil_vitima_v2.schema.json"
)
COMPILER_ID = "PERFIL-V2-QUAL-COMPILER-v1.1"
FREEZE_HASH_PROJECTION_ID = "PERFIL-V2-FREEZE-PROJECTION-v1"
_CALCULATED_ELAPSED_TOLERANCE = timedelta(seconds=1)
_INFORMED_ELAPSED_TOLERANCE = timedelta(minutes=1)


class ProfileCompilerError(ValueError):
    """Erro-base do leitor/compilador."""


class GroundTruthFirewallError(ProfileCompilerError):
    """A entrada contém posição verdadeira ou marcador equivalente."""


class InputValidationError(ProfileCompilerError):
    """A entrada não satisfaz o contrato estruturado."""


_ALLOWED_FIREWALL_KEY = "groundtruthabsent"
_FORBIDDEN_NORMALIZED_KEYS = {
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

_FORBIDDEN_TEXT_PATTERNS = (
    re.compile(r"\bground[\s_-]*truth\b", re.IGNORECASE),
    re.compile(r"\btrue[\s_-]*(?:location|coordinate|latitude|longitude|lat|lon)\b", re.IGNORECASE),
    re.compile(r"\bvictim[\s_-]*(?:latitude|longitude|lat|lon)\b", re.IGNORECASE),
    re.compile(r"\bposi[cç][aã]o\s+verdadeira\b", re.IGNORECASE),
    re.compile(r"\blocaliza[cç][aã]o\s+(?:verdadeira|real)\b", re.IGNORECASE),
    re.compile(r"\bcoordenadas?\s+reais?\b", re.IGNORECASE),
    re.compile(r"\b(?:latitude|longitude)\s+real\b", re.IGNORECASE),
    re.compile(r"\brefer[eê]ncia\s+verdadeira\b", re.IGNORECASE),
    re.compile(r"\bgabarito\s*[:=]", re.IGNORECASE),
)


def _normalized_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", ascii_text.lower())


def enforce_ground_truth_firewall(value: Any, path: str = "$") -> None:
    """Rejeita recursivamente chaves capazes de revelar a resposta."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = _normalized_key(str(key))
            if normalized != _ALLOWED_FIREWALL_KEY and normalized in _FORBIDDEN_NORMALIZED_KEYS:
                raise GroundTruthFirewallError(
                    f"Chave proibida pelo firewall em {path}.{key}: posição verdadeira não pode entrar no módulo."
                )
            enforce_ground_truth_firewall(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            enforce_ground_truth_firewall(child, f"{path}[{index}]")
    elif isinstance(value, str):
        if any(pattern.search(value) for pattern in _FORBIDDEN_TEXT_PATTERNS):
            raise GroundTruthFirewallError(
                f"Marcador textual proibido pelo firewall em {path}: a entrada não pode mencionar a resposta."
            )


def _resolve_local_ref(root_schema: Mapping[str, Any], ref: str) -> Mapping[str, Any]:
    if not ref.startswith("#/"):
        raise InputValidationError(f"Referência de esquema externa não suportada: {ref}")
    current: Any = root_schema
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or token not in current:
            raise InputValidationError(f"Referência de esquema inválida: {ref}")
        current = current[token]
    if not isinstance(current, Mapping):
        raise InputValidationError(f"Referência de esquema não aponta para objeto: {ref}")
    return current


def _matches_json_type(value: Any, type_name: str) -> bool:
    if type_name == "null":
        return value is None
    if type_name == "object":
        return isinstance(value, Mapping)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    raise InputValidationError(f"Tipo JSON Schema não suportado: {type_name}")


def _parse_datetime(value: str, path: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputValidationError(f"{path}: data/hora inválida: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InputValidationError(
            f"{path}: data/hora deve incluir fuso horário ou sufixo Z."
        )
    return parsed


def _validate_datetime(value: str, path: str) -> None:
    _parse_datetime(value, path)


def _validate_schema_node(
    value: Any,
    schema: Mapping[str, Any],
    root_schema: Mapping[str, Any],
    path: str,
) -> None:
    if "$ref" in schema:
        target = _resolve_local_ref(root_schema, str(schema["$ref"]))
        _validate_schema_node(value, target, root_schema, path)
        return

    if "oneOf" in schema:
        matches = 0
        errors: list[str] = []
        for option in schema["oneOf"]:
            try:
                _validate_schema_node(value, option, root_schema, path)
                matches += 1
            except InputValidationError as exc:
                errors.append(str(exc))
        if matches != 1:
            detail = "; ".join(errors[:2])
            raise InputValidationError(
                f"{path}: deve satisfazer exatamente uma alternativa oneOf (satisfeitas={matches}). {detail}"
            )

    for condition in schema.get("allOf", []):
        if "if" in condition:
            try:
                _validate_schema_node(value, condition["if"], root_schema, path)
                branch = condition.get("then")
            except InputValidationError:
                branch = condition.get("else")
            if isinstance(branch, Mapping):
                _validate_schema_node(value, branch, root_schema, path)
        else:
            _validate_schema_node(value, condition, root_schema, path)

    if "const" in schema and value != schema["const"]:
        raise InputValidationError(f"{path}: valor deve ser {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise InputValidationError(f"{path}: valor fora da enumeração permitida: {value!r}")

    expected = schema.get("type")
    if expected is not None:
        types = [expected] if isinstance(expected, str) else list(expected)
        if not any(_matches_json_type(value, type_name) for type_name in types):
            raise InputValidationError(f"{path}: tipo inválido; esperado {types}, recebido {type(value).__name__}")

    if isinstance(value, Mapping):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise InputValidationError(f"{path}: campo obrigatório ausente: {key}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value) - set(properties))
            if extras:
                raise InputValidationError(f"{path}: campos não permitidos: {', '.join(extras)}")
        for key, child in value.items():
            if key in properties:
                _validate_schema_node(child, properties[key], root_schema, f"{path}.{key}")

    if isinstance(value, list):
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise InputValidationError(f"{path}: excede {schema['maxItems']} itens")
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            raise InputValidationError(f"{path}: requer ao menos {schema['minItems']} itens")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, child in enumerate(value):
                _validate_schema_node(child, item_schema, root_schema, f"{path}[{index}]")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise InputValidationError(f"{path}: texto menor que o mínimo permitido")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise InputValidationError(f"{path}: texto maior que o máximo permitido")
        if "pattern" in schema and re.fullmatch(str(schema["pattern"]), value) is None:
            raise InputValidationError(f"{path}: formato textual inválido")
        if schema.get("format") == "date-time":
            _validate_datetime(value, path)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise InputValidationError(f"{path}: valor abaixo do mínimo")
        if "maximum" in schema and value > schema["maximum"]:
            raise InputValidationError(f"{path}: valor acima do máximo")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise InputValidationError(f"{path}: valor deve ser maior que {schema['exclusiveMinimum']}")
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            raise InputValidationError(f"{path}: valor deve ser menor que {schema['exclusiveMaximum']}")


def load_schema(schema_path: Path = DEFAULT_SCHEMA_PATH) -> dict[str, Any]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if schema.get("$id") != "urn:agtu:sar:perfil-vitima:v2-draft-2":
        raise InputValidationError("Esquema inesperado para o compilador PERFIL V2.")
    return schema


def _validate_associated_location_semantics(payload: Mapping[str, Any]) -> None:
    for index, clue in enumerate(payload.get("clues", [])):
        location = clue.get("associated_location")
        if location is None:
            if clue.get("spatial_status") == "ESPACIALIZADA":
                raise InputValidationError(
                    f"$.clues[{index}]: ESPACIALIZADA exige associated_location com latitude e longitude."
                )
            continue
        lat = location.get("latitude")
        lon = location.get("longitude")
        if (lat is None) != (lon is None):
            raise InputValidationError(
                f"$.clues[{index}].associated_location: latitude e longitude devem aparecer juntas."
            )
        if clue.get("spatial_status") == "ESPACIALIZADA" and not _location_is_complete(location):
            raise InputValidationError(
                f"$.clues[{index}]: ESPACIALIZADA exige coordenadas completas ou geometry_reference."
            )


def _validate_identifier_uniqueness(payload: Mapping[str, Any]) -> None:
    identifiers: list[tuple[str, str]] = []
    profile = payload["victim_profile"]
    for field in (
        "age_group",
        "mobility",
        "maximum_plausible_travel_time",
        "cognitive_condition",
        "area_familiarity",
        "environment_experience",
        "relevant_medication_effect",
        "previous_disappearances",
    ):
        identifiers.append((str(profile[field]["fact_id"]), f"/victim_profile/{field}"))
    for index, fact in enumerate(profile["physical_or_sensory_limitations"]):
        identifiers.append((str(fact["fact_id"]), f"/victim_profile/physical_or_sensory_limitations/{index}"))
    for index, clue in enumerate(payload["clues"]):
        identifiers.append((str(clue["clue_id"]), f"/clues/{index}"))
    seen: dict[str, str] = {}
    for identifier, pointer in identifiers:
        if identifier in seen:
            raise InputValidationError(
                f"Identificador duplicado {identifier!r}: {seen[identifier]} e {pointer}."
            )
        seen[identifier] = pointer


def _value_is_unavailable(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return _normalized_key(value) in {
            "naodisponivel",
            "desconhecido",
            "desconhecida",
            "unknown",
        }
    if isinstance(value, Mapping) and "value_code" in value:
        return value.get("value_code") == "NAO_DISPONIVEL"
    return False


def _iter_evidenced_values(
    payload: Mapping[str, Any],
) -> Iterable[tuple[str, Any, Mapping[str, Any]]]:
    profile = payload["victim_profile"]
    for field in (
        "age_group",
        "mobility",
        "maximum_plausible_travel_time",
        "cognitive_condition",
        "area_familiarity",
        "environment_experience",
        "relevant_medication_effect",
        "previous_disappearances",
    ):
        fact = profile[field]
        yield f"$.victim_profile.{field}", _fact_value(fact), fact["evidence"]
    for index, fact in enumerate(profile["physical_or_sensory_limitations"]):
        yield (
            f"$.victim_profile.physical_or_sensory_limitations[{index}]",
            _fact_value(fact),
            fact["evidence"],
        )
    for index, clue in enumerate(payload["clues"]):
        yield f"$.clues[{index}]", clue["literal_description"], clue["evidence"]


def _validate_evidence_value_coherence(payload: Mapping[str, Any]) -> None:
    for pointer, value, evidence in _iter_evidenced_values(payload):
        unavailable = _value_is_unavailable(value)
        authorized = bool(evidence.get("authorized_for_model"))
        confidence = evidence.get("confidence")
        source = evidence.get("source")
        if unavailable and authorized:
            raise InputValidationError(
                f"{pointer}: valor não disponível não pode ser autorizado para produzir efeito."
            )
        if unavailable and confidence == "ALTA":
            raise InputValidationError(
                f"{pointer}: valor não disponível não pode ter confiança ALTA."
            )
        if not unavailable and authorized and source == "NAO_DISPONIVEL":
            raise InputValidationError(
                f"{pointer}: valor conhecido e autorizado exige fonte identificada."
            )


def _validate_temporal_coherence(payload: Mapping[str, Any]) -> None:
    collected_at = _parse_datetime(str(payload["collected_at"]), "$.collected_at")
    point = payload["last_planning_point"]
    point_timestamp_raw = point.get("timestamp")
    point_timestamp = None
    if point_timestamp_raw is not None:
        point_timestamp = _parse_datetime(
            str(point_timestamp_raw), "$.last_planning_point.timestamp"
        )
        if point_timestamp > collected_at:
            raise InputValidationError(
                "$.last_planning_point.timestamp: o ponto não pode ser posterior a collected_at."
            )

    metadata = payload.get("freeze_metadata")
    if isinstance(metadata, Mapping):
        frozen_at = _parse_datetime(str(metadata["frozen_at"]), "$.freeze_metadata.frozen_at")
        if collected_at > frozen_at:
            raise InputValidationError(
                "$.freeze_metadata.frozen_at: o congelamento não pode anteceder collected_at."
            )

    context = payload["search_context"]
    elapsed = context.get("elapsed_minutes")
    if elapsed is None or point_timestamp is None:
        return
    chronological_elapsed = collected_at - point_timestamp
    declared_elapsed = timedelta(minutes=float(elapsed))
    status = context.get("elapsed_status")
    mismatch = abs(chronological_elapsed - declared_elapsed)
    if status == "CALCULADO":
        tolerance = _CALCULATED_ELAPSED_TOLERANCE
    elif status == "INFORMADO" and point.get("timestamp_precision") == "EXATA":
        tolerance = _INFORMED_ELAPSED_TOLERANCE
    else:
        tolerance = None
    if tolerance is not None and mismatch > tolerance:
        raise InputValidationError(
            "$.search_context.elapsed_minutes: tempo transcorrido diverge do intervalo "
            "entre last_planning_point.timestamp e collected_at para a precisão declarada."
        )


def _validate_freeze_semantics(payload: Mapping[str, Any]) -> None:
    metadata = payload.get("freeze_metadata")
    if payload.get("record_status") == "CONGELADO":
        if not isinstance(metadata, Mapping):
            raise InputValidationError("Registro CONGELADO exige freeze_metadata.")
        if metadata.get("operator_code") != payload.get("operator_code"):
            raise InputValidationError("freeze_metadata.operator_code deve coincidir com operator_code.")
        declared_hash = str(metadata.get("payload_sha256", ""))
        calculated_hash = calculate_freeze_payload_sha256(payload)
        if not hmac.compare_digest(declared_hash, calculated_hash):
            raise InputValidationError(
                "freeze_metadata.payload_sha256 não confere com a projeção canônica do pacote."
            )
    elif metadata is not None:
        raise InputValidationError("Registro RASCUNHO deve manter freeze_metadata=null.")


def validate_input(
    payload: Mapping[str, Any],
    schema_path: Path = DEFAULT_SCHEMA_PATH,
) -> None:
    """Valida firewall, estrutura do esquema e coerência espacial mínima."""
    enforce_ground_truth_firewall(payload)
    schema = load_schema(schema_path)
    _validate_schema_node(payload, schema, schema, "$")
    _validate_associated_location_semantics(payload)
    _validate_identifier_uniqueness(payload)
    _validate_evidence_value_coherence(payload)
    _validate_temporal_coherence(payload)
    _validate_freeze_semantics(payload)


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def freeze_payload_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Retorna a projeção congelada coberta pelo hash, sem autorreferência.

    A projeção contém todo o pacote ``CONGELADO`` e todos os campos de
    ``freeze_metadata``, exceto o próprio ``payload_sha256``. Nenhum outro
    campo é descartado.
    """
    if payload.get("record_status") != "CONGELADO":
        raise InputValidationError("A projeção de congelamento exige record_status=CONGELADO.")
    metadata = payload.get("freeze_metadata")
    if not isinstance(metadata, Mapping):
        raise InputValidationError("A projeção de congelamento exige freeze_metadata.")
    projection = deepcopy(dict(payload))
    projected_metadata = projection.get("freeze_metadata")
    if not isinstance(projected_metadata, dict):
        raise InputValidationError("freeze_metadata inválido para projeção canônica.")
    projected_metadata.pop("payload_sha256", None)
    return projection


def calculate_freeze_payload_sha256(payload: Mapping[str, Any]) -> str:
    """Calcula SHA-256 da projeção canônica PERFIL-V2-FREEZE-PROJECTION-v1."""
    return canonical_sha256(freeze_payload_projection(payload))


def prepare_frozen_payload(
    payload: Mapping[str, Any],
    frozen_at: str,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
) -> dict[str, Any]:
    """Valida um rascunho e produz um pacote congelado com hash verificável."""
    if payload.get("record_status") != "RASCUNHO":
        raise InputValidationError("Somente um registro RASCUNHO pode ser congelado por esta função.")
    validate_input(payload, schema_path)
    _parse_datetime(frozen_at, "--frozen-at")
    schema_id = load_schema(schema_path)["$id"]
    frozen = deepcopy(dict(payload))
    frozen["record_status"] = "CONGELADO"
    frozen["freeze_metadata"] = {
        "frozen_at": frozen_at,
        "operator_code": frozen["operator_code"],
        "schema_id": schema_id,
        "payload_sha256": "0" * 64,
    }
    frozen["freeze_metadata"]["payload_sha256"] = calculate_freeze_payload_sha256(frozen)
    validate_input(frozen, schema_path)
    return frozen


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        normalized = _normalized_key(value)
        return bool(normalized) and normalized not in {
            "naodisponivel",
            "desconhecido",
            "desconhecida",
            "unknown",
        }
    if isinstance(value, (list, Mapping)):
        return bool(value)
    return True


def _evidence_usable(evidence: Mapping[str, Any], value: Any) -> tuple[bool, str | None]:
    if not bool(evidence.get("authorized_for_model")):
        return False, "NAO_AUTORIZADO_PARA_O_MODELO"
    if evidence.get("nature") == "NAO_DISPONIVEL" or not _has_value(value):
        return False, "NAO_DISPONIVEL_SEM_EFEITO"
    return True, None


def _support(pointer: str, value: Any, evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_pointer": pointer,
        "value": deepcopy(value),
        "nature": evidence["nature"],
        "source": evidence["source"],
        "source_code": evidence.get("source_code"),
        "observed_at": evidence.get("observed_at"),
        "time_precision": evidence.get("time_precision", "NAO_DISPONIVEL"),
        "confidence": evidence["confidence"],
        "authorized_for_model": True,
    }


def _fact_value(fact: Mapping[str, Any]) -> Any:
    if "value" in fact:
        return fact["value"]
    if "value_minutes" in fact:
        return fact["value_minutes"]
    if "value_code" in fact:
        return {
            "value_code": fact["value_code"],
            "description": fact.get("description"),
        }
    raise InputValidationError("Fato tipado sem valor reconhecido.")


def _fact_usable(fact: Mapping[str, Any], *, positive_only: bool = False) -> tuple[bool, str | None]:
    value = _fact_value(fact)
    usable, reason = _evidence_usable(fact["evidence"], value)
    if not usable:
        return usable, reason
    if isinstance(value, Mapping):
        code = value.get("value_code")
        if code == "NAO_DISPONIVEL":
            return False, "NAO_DISPONIVEL_SEM_EFEITO"
        if positive_only and code != "PRESENTE":
            return False, "AUSENCIA_CONFIRMADA_SEM_EFEITO"
    return True, None


def _location_is_complete(location: Any) -> bool:
    if not isinstance(location, Mapping):
        return False
    coordinate_pair = location.get("latitude") is not None and location.get("longitude") is not None
    geometry_reference = isinstance(location.get("geometry_reference"), str) and bool(
        location["geometry_reference"].strip()
    )
    return coordinate_pair or geometry_reference


def compile_profile(
    payload: Mapping[str, Any],
    schema_path: Path = DEFAULT_SCHEMA_PATH,
) -> dict[str, Any]:
    """Compila fatos/pistas autorizados em hipóteses qualitativas auditáveis."""
    validate_input(payload, schema_path)
    profile = payload["victim_profile"]
    context = payload["search_context"]

    pending_hypotheses: list[dict[str, Any]] = []
    non_spatializable: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    def exclude(pointer: str, category: str, reason: str, evidence: Mapping[str, Any] | None = None) -> None:
        item: dict[str, Any] = {
            "source_pointer": pointer,
            "category": category,
            "reason": reason,
        }
        if evidence is not None:
            item["nature"] = evidence.get("nature")
            item["confidence"] = evidence.get("confidence")
        excluded.append(item)

    # Restrição de alcance: fatos tipados podem ativar hipótese, nunca distância ou peso.
    reach_supports: list[dict[str, Any]] = []
    for field, category in (
        ("mobility", "MOBILIDADE"),
        ("maximum_plausible_travel_time", "TEMPO_PLAUSIVEL_DESLOCAMENTO"),
    ):
        fact = profile[field]
        pointer = f"/victim_profile/{field}"
        usable, reason = _fact_usable(fact)
        if usable:
            reach_supports.append(_support(pointer, _fact_value(fact), fact["evidence"]))
        else:
            exclude(pointer, category, str(reason), fact["evidence"])

    for index, fact in enumerate(profile["physical_or_sensory_limitations"]):
        pointer = f"/victim_profile/physical_or_sensory_limitations/{index}"
        usable, reason = _fact_usable(fact, positive_only=True)
        if usable:
            reach_supports.append(_support(pointer, _fact_value(fact), fact["evidence"]))
        else:
            exclude(pointer, "LIMITACAO_FISICA_OU_SENSORIAL", str(reason), fact["evidence"])

    if reach_supports:
        pending_hypotheses.append(
            {
                "hypothesis_type": "RESTRICAO_DE_ALCANCE",
                "statement": (
                    "Mobilidade, tempo plausível ou limitações autorizadas podem delimitar alcance, "
                    "mas não geram raio, velocidade ou direção sem regra quantitativa congelada."
                ),
                "spatial_status": "CONTEXTUAL_NAO_DIRECIONAL",
                "spatialized": False,
                "directional_preference_allowed": False,
                "direction_data": None,
                "supports": reach_supports,
                "operational_context": {
                    "elapsed_minutes": context.get("elapsed_minutes"),
                    "elapsed_status": context.get("elapsed_status"),
                    "travel_mode": context.get("travel_mode"),
                    "environment": context.get("environment"),
                },
            }
        )

    # Demais fatos são preservados, mas não recebem interpretação espacial automática.
    scalar_non_spatial = (
        ("age_group", "FAIXA_ETARIA", False),
        ("cognitive_condition", "CONDICAO_COGNITIVA", False),
        ("area_familiarity", "FAMILIARIDADE_AREA", False),
        ("environment_experience", "EXPERIENCIA_AMBIENTAL", False),
        ("relevant_medication_effect", "MEDICACAO", True),
        ("previous_disappearances", "DESAPARECIMENTOS_ANTERIORES", False),
    )
    for field, category, positive_only in scalar_non_spatial:
        fact = profile[field]
        pointer = f"/victim_profile/{field}"
        usable, reason = _fact_usable(fact, positive_only=positive_only)
        if usable:
            non_spatializable.append(
                {
                    "source_pointer": pointer,
                    "fact_id": fact["fact_id"],
                    "category": category,
                    "reason": "SEM_REGRA_ESPACIAL_FORMALIZADA_NESTA_VERSAO",
                    "support": _support(pointer, _fact_value(fact), fact["evidence"]),
                }
            )
        else:
            exclude(pointer, category, str(reason), fact["evidence"])

    clue_hypothesis_types = {
        "DESTINO_DECLARADO": "DESTINO_OU_LUGAR_FAMILIAR",
        "LUGAR_FAMILIAR": "DESTINO_OU_LUGAR_FAMILIAR",
        "AGUA_PESCA": "AGUA_OU_PESCA",
        "ISOLAMENTO": "ISOLAMENTO_OU_ABRIGO",
        "ABRIGO": "ISOLAMENTO_OU_ABRIGO",
        "DIRECAO_OBSERVADA": "DIRECAO_OBSERVADA",
        "ATIVIDADE_HABITUAL": "LOCAL_COMPATIVEL_COM_ATIVIDADE",
        "TRANSPORTE": "RESTRICAO_DE_ALCANCE",
    }
    for index, clue in enumerate(payload["clues"]):
        pointer = f"/clues/{index}"
        evidence = clue["evidence"]
        usable, reason = _evidence_usable(evidence, clue["literal_description"])
        if not usable:
            exclude(pointer, clue["clue_type"], str(reason), evidence)
            continue
        mapped_type = clue_hypothesis_types.get(clue["clue_type"])
        if mapped_type is None or clue["spatial_status"] == "NAO_ESPACIALIZAVEL":
            non_spatializable.append(
                {
                    "source_pointer": pointer,
                    "clue_id": clue["clue_id"],
                    "category": clue["clue_type"],
                    "reason": (
                        "OPERADOR_MARCOU_COMO_NAO_ESPACIALIZAVEL"
                        if clue["spatial_status"] == "NAO_ESPACIALIZAVEL"
                        else "SEM_REGRA_ESPACIAL_FORMALIZADA_NESTA_VERSAO"
                    ),
                    "support": _support(pointer, clue["literal_description"], evidence),
                }
            )
            continue

        location = clue.get("associated_location")
        spatialized = clue["spatial_status"] == "ESPACIALIZADA" and _location_is_complete(location)
        if clue["clue_type"] == "DIRECAO_OBSERVADA":
            direction_data = clue.get("direction_data")
            direction_structured = (
                clue["spatial_status"] == "ESPACIALIZADA"
                and isinstance(direction_data, Mapping)
                and (
                    direction_data.get("azimuth_deg") is not None
                    or direction_data.get("cardinal_direction") is not None
                )
            )
            statement = (
                "Direção observada autorizada possui origem, rumo, tolerância e método estruturados."
                if direction_structured
                else "Direção relatada permanece pendente até receber representação direcional estruturada."
            )
            spatialized = bool(direction_structured)
            effective_status = "ESPACIALIZADA" if direction_structured else "ESPACIALIZAVEL_PENDENTE"
            directional_allowed = bool(direction_structured)
        elif mapped_type == "DESTINO_OU_LUGAR_FAMILIAR":
            statement = (
                "Destino ou lugar familiar autorizado foi formalizado como hipótese espacial auditável."
                if spatialized
                else "Destino ou lugar familiar autorizado aguarda associação espacial."
            )
            effective_status = "ESPACIALIZADA" if spatialized else clue["spatial_status"]
            directional_allowed = False
        elif mapped_type == "AGUA_OU_PESCA":
            statement = (
                "A pista de água ou pesca foi formalizada como possível atrator, separada de acesso, "
                "travessia e barreira; nenhum desses efeitos é calculado nesta versão."
            )
            effective_status = "ESPACIALIZADA" if spatialized else clue["spatial_status"]
            directional_allowed = False
        elif mapped_type == "ISOLAMENTO_OU_ABRIGO":
            statement = (
                "A pista de isolamento ou abrigo foi formalizada sem converter traço pessoal em direção."
            )
            effective_status = "ESPACIALIZADA" if spatialized else clue["spatial_status"]
            directional_allowed = False
        else:
            statement = "Pista autorizada formalizada para análise espacial posterior."
            effective_status = "ESPACIALIZADA" if spatialized else clue["spatial_status"]
            directional_allowed = False

        pending_hypotheses.append(
            {
                "source_clue_id": clue["clue_id"],
                "hypothesis_type": mapped_type,
                "statement": statement,
                "spatial_status": effective_status,
                "spatialized": spatialized,
                "directional_preference_allowed": directional_allowed,
                "associated_location": deepcopy(location) if location is not None else None,
                "direction_data": deepcopy(clue.get("direction_data")),
                "supports": [_support(pointer, clue["literal_description"], evidence)],
            }
        )

    hypotheses: list[dict[str, Any]] = []
    for index, hypothesis in enumerate(pending_hypotheses, start=1):
        hypotheses.append(
            {
                "hypothesis_id": f"H{index:03d}",
                **hypothesis,
                "qualitative_only": True,
                "weight": None,
                "score_delta": None,
                "ranking_effect_applied": False,
                "requires_frozen_quantitative_rule_before_ranking": True,
                "evidence_nature_preserved": True,
            }
        )

    result: dict[str, Any] = {
        "compiler_id": COMPILER_ID,
        "schema_id": "urn:agtu:sar:perfil-vitima:v2-draft-2",
        "scenario_id": payload["scenario_id"],
        "protocol_version": payload["protocol_version"],
        "source_record_status": payload["record_status"],
        "source_operator_code": payload["operator_code"],
        "source_collected_at": payload["collected_at"],
        "source_freeze_metadata": deepcopy(payload["freeze_metadata"]),
        "freeze_validation": {
            "projection_id": FREEZE_HASH_PROJECTION_ID,
            "status": "VERIFIED" if payload["record_status"] == "CONGELADO" else "NOT_APPLICABLE",
        },
        "mode": "QUALITATIVO_SEM_PESOS_SEM_RANKING",
        "input_sha256": canonical_sha256(payload),
        "ground_truth_absent": True,
        "planning_point": deepcopy(payload["last_planning_point"]),
        "search_context": deepcopy(payload["search_context"]),
        "hypotheses": hypotheses,
        "non_spatializable_items": non_spatializable,
        "excluded_items": excluded,
        "summary": {
            "hypothesis_count": len(hypotheses),
            "spatialized_hypothesis_count": sum(1 for item in hypotheses if item["spatialized"]),
            "non_spatializable_item_count": len(non_spatializable),
            "excluded_item_count": len(excluded),
            "weights_applied": False,
            "ranking_produced": False,
        },
        "scope_guards": {
            "ground_truth_firewall_passed": True,
            "unknown_values_create_effect": False,
            "free_text_directly_converted_to_weight": False,
            "suspicion_upgraded_to_confirmation": False,
            "weights_or_ranking_implemented": False,
        },
        "firewall_manifest": {
            "policy_id": "PERFIL-V2-GT-FIREWALL-v1.1",
            "recursive_key_scan": True,
            "forbidden_alias_scan_pt_en": True,
            "explicit_text_marker_scan": True,
            "schema_disallows_free_objects_in_facts": True,
            "text_fields_sanitized_declared": payload["text_fields_sanitized"],
            "status": "PASS",
        },
    }
    result["compiled_sha256"] = canonical_sha256(result)
    return result


def load_input(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise InputValidationError("A raiz da entrada deve ser um objeto JSON.")
    return value


def write_output(path: Path, compiled: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(compiled))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Entrada JSON conforme o esquema V2.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Saída JSON compilada ou pacote congelado preparado.",
    )
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH)
    parser.add_argument(
        "--prepare-freeze",
        action="store_true",
        help="Transforma um RASCUNHO válido em pacote CONGELADO verificável.",
    )
    parser.add_argument(
        "--frozen-at",
        help="Data/hora RFC 3339 do congelamento; usada somente com --prepare-freeze.",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = load_input(args.input)
    if args.prepare_freeze:
        if args.output is None:
            parser.error("--prepare-freeze exige --output para não sobrescrever a entrada.")
        if args.frozen_at is None:
            parser.error("--prepare-freeze exige --frozen-at com fuso horário.")
        if args.output.resolve() == args.input.resolve():
            parser.error("--prepare-freeze exige arquivo de saída diferente da entrada.")
        frozen = prepare_frozen_payload(payload, args.frozen_at, args.schema)
        write_output(args.output, frozen)
        return 0
    if args.frozen_at is not None:
        parser.error("--frozen-at só pode ser usado com --prepare-freeze.")
    compiled = compile_profile(payload, args.schema)
    if args.output is not None:
        write_output(args.output, compiled)
    else:
        print(canonical_json_bytes(compiled).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
