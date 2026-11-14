#!/usr/bin/env python3
"""Protocolo prospectivo integrado para LOC, URG e DET.

O módulo funciona como envelope auditável. Ele não substitui os motores
TERRITORIAL/PERFIL, não soma as três saídas em um escore único e nunca recebe
ground truth. Imagens são evidência contextual anotada por pessoa; visão
computacional não é executada nesta versão.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib.util
import json
import math
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES_PATH = ROOT / "outputs" / "protocolo_integrado_v1" / "catalogo_regras_urg_v1.json"
PROTOCOL_VERSION = "PROTOCOLO-INTEGRADO-PROSPECTIVO-v1.0"
EVENT_PROTOCOL_VERSION = "EVENTO-BUSCA-v1.0"
LOC_RESULT_CONTRACT_VERSION = "LOC-RESULT-v1.1"
LOC_INPUT_PROJECTION_ID = "LOC-INPUT-PROJECTION-v1"
LOC_ENVELOPE_ENGINE_ID = "LOC-PERFIL-V3-ENVELOPE-v1.0"
LOC_ENGINE_ID = "PERFIL-V3-QUANT-RANKER-v1.1"
LOC_ENGINE_PATH = ROOT / "work" / "perfil_vitima_v3" / "profile_ranker.py"
LOC_ENGINE_CONFIG_PATH = (
    ROOT / "outputs" / "modulo_perfil_vitima_v3" / "config_perfil_quantitativo_v3.json"
)
LOC_ENGINE_LOCK_PATH = (
    ROOT / "outputs" / "protocolo_integrado_v1" / "loc_engine_lock_v1.json"
)
VISUAL_SPATIAL_ENGINE_PATH = (
    ROOT / "work" / "protocolo_integrado_v1" / "visual_spatial_binding.py"
)
ENGINE_ID = "PROTOCOLO-INTEGRADO-LOC-URG-DET-v1.0"
CASE_FREEZE_PROJECTION_ID = "PROTOCOLO-INTEGRADO-FREEZE-PROJECTION-v1"
EVENT_FREEZE_PROJECTION_ID = "EVENTO-BUSCA-FREEZE-PROJECTION-v1"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_GT_KEYS = {"groundtruthabsent", "groundtruthused"}
_FORBIDDEN_GT_FRAGMENTS = (
    "groundtruth", "truelocation", "truecoordinate", "truelat", "truelon",
    "victimlat", "victimlon", "targetlat", "targetlon", "posicaoverdadeira",
    "posicaoreal", "localizacaoverdadeira", "localizacaoreal", "coordenadareal",
    "latitudereal", "longitudereal", "referenciaverdadeira", "gabarito",
)
_FORBIDDEN_TEXT = (
    re.compile(r"\bground[\s_-]*truth\b", re.IGNORECASE),
    re.compile(r"\btrue[\s_-]*(?:location|coordinate|latitude|longitude|lat|lon)\b", re.IGNORECASE),
    re.compile(r"\b(?:posi[cç][aã]o|localiza[cç][aã]o)\s+(?:verdadeira|real)\b", re.IGNORECASE),
    re.compile(r"\bcoordenadas?\s+reais?\b", re.IGNORECASE),
    re.compile(r"\bgabarito\s*[:=]", re.IGNORECASE),
)
_PII_OR_COORDINATE_TEXT = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)"),
    re.compile(r"(?<!\d)(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?9?\d{4}[-\s]?\d{4}(?!\d)"),
    re.compile(r"(?<!\d)[+-]?\d{1,2}(?:[.,]\d{4,})\s*[,;/]\s*[+-]?\d{1,3}(?:[.,]\d{4,})(?!\d)"),
)

_POINT_ROLES = {
    "ULTIMO_PONTO_VISTO", "ULTIMO_PONTO_CONHECIDO", "PONTO_INICIAL_PLANEJAMENTO",
    "ESTIMATIVA_SISTEMA_AEROTRANSPORTADO",
}
_AVAILABILITY = {"PRESENTE", "AUSENTE", "NAO_DISPONIVEL", "CONTRADITORIO"}
_URGENCY_DOMAINS = {
    "TEMPO", "CONDICAO_CLINICA", "COGNICAO_ORIENTACAO", "MOBILIDADE",
    "MEDICACAO", "EXPOSICAO", "COMUNICACAO", "SUPRIMENTOS",
    "VESTUARIO_CALCADO", "PERIGO_AMBIENTAL",
}
_DET_DIMENSIONS = {
    "VISIBILIDADE", "ACESSIBILIDADE", "COMPATIBILIDADE_RECURSO",
    "CONDICAO_AMBIENTAL", "ATUALIDADE_QUALIDADE",
}
_DET_CATEGORIES = {
    "FAVORAVEL_OBSERVADO", "RESTRITO_OBSERVADO", "POTENCIAL_CAMADA_PUBLICA",
    "INDETERMINADO", "CONTRADITORIO",
}
_CARDINAL_AZIMUTH_CENTERS = {
    "N": 0.0, "NE": 45.0, "E": 90.0, "SE": 135.0,
    "S": 180.0, "SW": 225.0, "W": 270.0, "NW": 315.0,
}
_KNOWN_LOCATION_SOURCE_EVENT_TYPES = {
    "BUSCA_EXECUTADA", "VESTIGIO_ENCONTRADO", "NOVO_PONTO_CONHECIDO",
}
_DET_VISUAL_DOMAINS = {
    "VEGETACAO", "OBSTRUCAO_VISUAL", "VIAS_ACESSOS", "BARREIRAS",
    "ILUMINACAO", "TERRENO", "RECURSO_OPERACIONAL", "QUALIDADE_IMAGEM",
    "ATUALIDADE_FONTE", "OUTRO",
}
# Uma anotação visual só pode sustentar as dimensões abaixo. A matriz evita que
# uma observação de um único domínio (por exemplo, TERRENO=PLANO) seja
# indevidamente reutilizada para concluir todas as dimensões DET.
_DET_VISUAL_DOMAIN_TO_DIMENSIONS = {
    "VEGETACAO": {"VISIBILIDADE", "ACESSIBILIDADE", "CONDICAO_AMBIENTAL"},
    "OBSTRUCAO_VISUAL": {"VISIBILIDADE"},
    "VIAS_ACESSOS": {"ACESSIBILIDADE"},
    "BARREIRAS": {"VISIBILIDADE", "ACESSIBILIDADE"},
    "ILUMINACAO": {"VISIBILIDADE", "CONDICAO_AMBIENTAL"},
    "TERRENO": {"ACESSIBILIDADE", "CONDICAO_AMBIENTAL"},
    "RECURSO_OPERACIONAL": {"COMPATIBILIDADE_RECURSO"},
    "QUALIDADE_IMAGEM": {"ATUALIDADE_QUALIDADE"},
    "ATUALIDADE_FONTE": {"ATUALIDADE_QUALIDADE"},
    "OUTRO": set(),
}
_DET_ENVIRONMENT_DOMAIN_TO_DIMENSIONS = {
    "CLIMA": {"CONDICAO_AMBIENTAL"},
    "ILUMINACAO": {"VISIBILIDADE", "CONDICAO_AMBIENTAL"},
    "RELEVO": {"ACESSIBILIDADE", "CONDICAO_AMBIENTAL"},
    "VEGETACAO": {"VISIBILIDADE", "ACESSIBILIDADE", "CONDICAO_AMBIENTAL"},
    "HIDROGRAFIA": {"ACESSIBILIDADE", "CONDICAO_AMBIENTAL"},
    "VIAS_TRILHAS": {"ACESSIBILIDADE", "COMPATIBILIDADE_RECURSO"},
    "BARREIRA": {"VISIBILIDADE", "ACESSIBILIDADE"},
    "ACESSO": {"ACESSIBILIDADE", "COMPATIBILIDADE_RECURSO"},
    "SOLO": {"ACESSIBILIDADE", "COMPATIBILIDADE_RECURSO", "CONDICAO_AMBIENTAL"},
    "RISCO_AMBIENTAL": {"CONDICAO_AMBIENTAL"},
}
# Polaridade explícita para impedir que texto livre adverso seja reutilizado
# como sustentação de uma conclusão DET favorável. Categorias não listadas
# continuam arquiváveis, mas exigem revisão humana.
_DET_VISUAL_CATEGORY_POLARITY = {
    ("OBSTRUCAO_VISUAL", "SEMOBSTRUCAORELEVANTE"): "FAVORAVEL",
    ("VIAS_ACESSOS", "VIAVISIVEL"): "FAVORAVEL",
    ("VIAS_ACESSOS", "ESTRADAPRESENTE"): "FAVORAVEL",
    ("RECURSO_OPERACIONAL", "COMPATIVELCOMRGB"): "FAVORAVEL",
    ("TERRENO", "PLANO"): "FAVORAVEL",
    ("TERRENO", "SOLOPAVIMENTADO"): "FAVORAVEL",
    ("QUALIDADE_IMAGEM", "NITIDAEATUAL"): "FAVORAVEL",
    ("VEGETACAO", "SEMVEGETACAO"): "FAVORAVEL",
    ("CONDICAO_AMBIENTAL", "CLIMASECO"): "FAVORAVEL",
    ("OBSTRUCAO_VISUAL", "OBSTRUCAOTOTAL"): "RESTRITO",
    ("VIAS_ACESSOS", "SEMACESSO"): "RESTRITO",
    ("RECURSO_OPERACIONAL", "RECURSOINCOMPATIVEL"): "RESTRITO",
    ("TERRENO", "TERRENOINTRANSITAVEL"): "RESTRITO",
    ("QUALIDADE_IMAGEM", "IMAGEMINUTILIZAVEL"): "RESTRITO",
    ("BARREIRAS", "BARREIRAPRESENTE"): "RESTRITO",
    ("VEGETACAO", "VEGETACAODENSA"): "RESTRITO",
}
_CRITICAL_URGENCY_DOMAINS = (
    "TEMPO", "CONDICAO_CLINICA", "COGNICAO_ORIENTACAO", "MOBILIDADE",
    "MEDICACAO", "EXPOSICAO", "COMUNICACAO",
)
# Códigos estruturados e conservadores que exigem reconciliação com URG.
# Texto livre não é interpretado clinicamente: somente estes códigos explícitos
# produzem a guarda de consistência abaixo.
_PROFILE_URGENCY_RISK_CODES = {
    ("COGNICAO_ORIENTACAO", "DESORIENTADO"): "AUMENTA_VULNERABILIDADE",
    ("COGNICAO_ORIENTACAO", "DESORIENTACAO_CONFIRMADA"): "AUMENTA_VULNERABILIDADE",
    ("MOBILIDADE", "MOBILIDADE_REDUZIDA"): "AUMENTA_VULNERABILIDADE",
    ("MEDICACAO", "DEPENDENCIA_DE_MEDICACAO"): "AUMENTA_VULNERABILIDADE",
    ("CONDICAO_CLINICA", "RISCO_DIRETO_A_VIDA"): "DIRETA_A_VIDA",
}
_URGENCY_SIGNIFICANCE_RANK = {
    "NAO_AVALIADA": -1,
    "CONTEXTUAL": 0,
    "AUMENTA_VULNERABILIDADE": 1,
    "DIRETA_A_VIDA": 2,
}
_RULE_SEMANTICS = {
    "URG-R01-RISCO-DIRETO": {
        "rule_version": "1.0",
        "activation_scope": "TESTE_PROSPECTIVO_CANDIDATO",
        "precedence": 1,
        "required_availability": "PRESENTE",
        "required_operational_significance": "DIRETA_A_VIDA",
        "result": "REVISAO_IMEDIATA",
        "requires_authorized_current_evidence": True,
        "basis_type": "ENCAMINHAMENTO_DE_CLASSIFICACAO_EXPLICITA",
    },
    "URG-R02-VULNERABILIDADE": {
        "rule_version": "1.0",
        "activation_scope": "TESTE_PROSPECTIVO_CANDIDATO",
        "precedence": 2,
        "required_availability": "PRESENTE",
        "required_operational_significance": "AUMENTA_VULNERABILIDADE",
        "result": "REVISAO_PRIORITARIA",
        "requires_authorized_current_evidence": True,
        "basis_type": "ENCAMINHAMENTO_DE_CLASSIFICACAO_EXPLICITA",
    },
    "URG-R03-COBERTURA-MINIMA": {
        "rule_version": "1.0",
        "activation_scope": "TESTE_PROSPECTIVO_CANDIDATO",
        "precedence": 3,
        "result": "REVISAO_PADRAO",
        "requires_all_critical_domains_resolved": True,
        "basis_type": "GUARDA_DE_COMPLETUDE",
    },
}

_PROFILE_RESULT_KEYS = {
    "engine_id", "protocol_id", "config_status", "scenario_id", "candidate_id",
    "mode", "ground_truth_absent", "source_loc_input_sha256",
    "source_case_revision", "input_sha256", "config_sha256",
    "source_profile_compiled_sha256", "source_territorial_manifest_sha256",
    "source_spatial_review_sha256", "abstained", "abstention_reason", "warnings",
    "evidence_quality_policy", "aggregation_policy", "group_records", "family_records",
    "excluded_hypotheses", "lambda_results", "primary_lambda", "primary_rows",
    "operational_effect_applied", "operational_status", "operational_rows",
    "sector_order", "stability", "scope_guards", "firewall_manifest", "output_sha256",
}
_PROFILE_INPUT_KEYS = {
    "protocol_version", "scenario_id", "candidate_id", "record_status", "created_at",
    "ground_truth_absent", "source_loc_input_sha256", "source_case_revision",
    "source_profile_compiled_sha256",
    "source_territorial_manifest_sha256", "source_spatial_review_sha256", "sectors",
    "hypotheses", "freeze_metadata",
}
_PROFILE_INPUT_SECTOR_KEYS = {
    "sector_id", "territorial_score", "bearing_start_deg", "bearing_end_deg", "polygon",
}
_PROFILE_ROW_KEYS = {
    "sector_id", "territorial_score", "profile_compatibility", "evidence_strength",
    "effective_lambda", "profile_score", "profile_delta", "territorial_rank",
    "profile_rank",
}
_PROFILE_SCOPE_GUARD_KEYS = {
    "allowed_quantitative_families", "mobility_weighted", "cognition_weighted",
    "age_weighted", "personality_weighted", "urgency_weighted",
    "external_statistics_used_as_weights_or_distances",
    "destination_uncertainty_used_as_binary_geometry",
    "destination_uncertainty_converted_to_decay_or_weight",
    "destination_outside_domain_projected_to_edge", "direction_origin_bound_to_candidate",
    "cross_candidate_ranking", "score_is_probability", "source_hash_format_validated",
    "source_artifact_content_hash_recomputed",
}
_PROFILE_SCOPE_GUARD_EXPECTED = {
    "allowed_quantitative_families": ["DESTINO", "DIRECAO"],
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
}
_PROFILE_ENGINE_MODULE: Any | None = None
_VISUAL_SPATIAL_ENGINE_MODULE: Any | None = None
_INTEGRATED_OUTPUT_KEYS = {
    "engine_id", "protocol_version", "scenario_id", "case_revision",
    "source_case_frozen_at", "run_id", "source_input_sha256",
    "rules_catalog_sha256", "ground_truth_used", "ground_truth_scope",
    "blind_processing", "blind_processing_scope", "storage_segregated",
    "parent_chain_status", "artifact_verification", "location", "urgency",
    "detectability", "visual_evidence_policy", "cross_module_guard",
    "review_required", "output_sha256",
}


class ProtocolError(ValueError):
    """Falha-base do protocolo."""


class InputValidationError(ProtocolError):
    """Entrada inválida."""


class GroundTruthFirewallError(ProtocolError):
    """Entrada contaminada por informação reservada."""


def _normalized_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", ascii_text.lower())


def enforce_ground_truth_firewall(value: Any, path: str = "$") -> None:
    """Bloqueia chaves e marcadores textuais capazes de revelar a resposta."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = _normalized_key(str(key))
            if normalized not in _ALLOWED_GT_KEYS and any(
                fragment in normalized for fragment in _FORBIDDEN_GT_FRAGMENTS
            ):
                raise GroundTruthFirewallError(f"Chave proibida em {path}.{key}.")
            if normalized == "groundtruthabsent" and child is not True:
                raise GroundTruthFirewallError(f"{path}.{key} deve ser true.")
            if normalized == "groundtruthused" and child is not False:
                raise GroundTruthFirewallError(f"{path}.{key} deve ser false.")
            enforce_ground_truth_firewall(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            enforce_ground_truth_firewall(child, f"{path}[{index}]")
    elif isinstance(value, str) and any(pattern.search(value) for pattern in _FORBIDDEN_TEXT):
        raise GroundTruthFirewallError(f"Marcador textual reservado em {path}.")


def enforce_text_sanitization(value: Any, path: str = "$") -> None:
    """Bloqueio sintático conservador; não substitui revisão humana de anonimização."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            enforce_text_sanitization(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            enforce_text_sanitization(child, f"{path}[{index}]")
    elif isinstance(value, str) and any(pattern.search(value) for pattern in _PII_OR_COORDINATE_TEXT):
        raise InputValidationError(f"Possível PII ou coordenada livre em {path}; use campo estruturado/código.")


def canonical_json_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise InputValidationError("Conteúdo não serializável ou número não finito.") from exc
    return (encoded + "\n").encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_visual_media_signature(path: Path, media_type: str) -> str:
    """Confere assinatura mínima do contêiner; não faz interpretação visual."""
    with path.open("rb") as stream:
        head = stream.read(64)
        stream.seek(0, 2)
        size = stream.tell()
        tail = b""
        if size >= 16:
            stream.seek(-16, 2)
            tail = stream.read(16)
    is_iso_bmff = len(head) >= 12 and head[4:8] == b"ftyp"
    brand = head[8:12] if is_iso_bmff else b""
    image_brands = {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"avif", b"avis"}
    if media_type == "IMAGE_JPEG":
        valid = size >= 32 and head.startswith(b"\xff\xd8\xff") and tail.endswith(b"\xff\xd9")
    elif media_type == "IMAGE_PNG":
        valid = bool(
            size >= 45
            and head.startswith(b"\x89PNG\r\n\x1a\n")
            and head[12:16] == b"IHDR"
            and int.from_bytes(head[16:20], "big") > 0
            and int.from_bytes(head[20:24], "big") > 0
            and b"IEND" in tail
        )
    elif media_type == "IMAGE_HEIC":
        valid = size >= 24 and is_iso_bmff and brand in image_brands
    elif media_type == "VIDEO":
        valid = (
            size >= 24
            and (
                (is_iso_bmff and brand not in image_brands)
                or head.startswith(b"\x1aE\xdf\xa3")
                or (head.startswith(b"RIFF") and head[8:12] == b"AVI ")
            )
        )
    else:  # protegido também pelo contrato de entrada
        valid = False
    if not valid:
        raise InputValidationError(
            f"Arquivo visual incompatível com media_type={media_type}; assinatura não confere."
        )
    return "CONTAINER_STRUCTURE_ONLY"


def loc_input_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Projecao nao circular e estritamente limitada ao que pode alimentar LOC."""
    artifacts = payload.get("source_artifacts")
    if not isinstance(artifacts, Mapping):
        raise InputValidationError("case.source_artifacts: objeto esperado para projecao LOC.")
    required = {
        "protocol_version", "scenario_id", "case_revision", "study_mode",
        "planning_point", "search_context",
    }
    _require_keys(payload, required, "case")
    assessment_at = _datetime(
        payload["search_context"]["assessment_at"],
        "case.search_context.assessment_at",
    )
    loc_search_context = deepcopy(payload["search_context"])
    loc_search_context["environment_observations"] = sorted(
        (
            deepcopy(observation)
            for observation in payload["search_context"]["environment_observations"]
            if observation["availability"] == "PRESENTE"
            and _evidence_eligibility(observation["evidence"], assessment_at) == "ELEGIVEL"
        ),
        key=lambda observation: observation["observation_id"],
    )
    return {
        "projection_id": LOC_INPUT_PROJECTION_ID,
        "protocol_version": payload["protocol_version"],
        "scenario_id": payload["scenario_id"],
        "case_revision": payload["case_revision"],
        "study_mode": payload["study_mode"],
        "planning_point": deepcopy(payload["planning_point"]),
        "search_context": loc_search_context,
        "source_artifacts": {
            key: artifacts[key]
            for key in (
                "profile_v2_compiled_sha256", "territorial_manifest_sha256",
                "spatial_review_manifest_sha256",
            )
        },
    }


def calculate_loc_input_sha256(payload: Mapping[str, Any]) -> str:
    return canonical_sha256(loc_input_projection(payload))


def _profile_config_sha256() -> str:
    _profile_engine_lock()
    if not LOC_ENGINE_CONFIG_PATH.is_file():
        raise InputValidationError("Configuração autorizada do motor LOC não foi encontrada.")
    try:
        config = json.loads(LOC_ENGINE_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputValidationError("Configuração autorizada do motor LOC não contém JSON válido.") from exc
    if not isinstance(config, Mapping):
        raise InputValidationError("Configuração autorizada do motor LOC deve ser um objeto JSON.")
    return canonical_sha256(config)


def _profile_engine_lock() -> Mapping[str, str]:
    """Confere o motor/configuração locais contra hashes congelados no release."""
    if not LOC_ENGINE_LOCK_PATH.is_file():
        raise InputValidationError("Trava de versão do motor LOC não foi encontrada.")
    try:
        lock = json.loads(LOC_ENGINE_LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputValidationError("Trava de versão do motor LOC não contém JSON válido.") from exc
    expected_keys = {
        "lock_version", "profile_engine_id", "profile_engine_artifact_sha256",
        "profile_engine_config_file_sha256",
    }
    if not isinstance(lock, Mapping):
        raise InputValidationError("Trava de versão do motor LOC deve ser objeto JSON.")
    _require_keys(lock, expected_keys, "loc_engine_lock")
    _reject_extra_keys(lock, expected_keys, "loc_engine_lock")
    if lock["lock_version"] != "LOC-ENGINE-LOCK-v1":
        raise InputValidationError("loc_engine_lock.lock_version: versão inesperada.")
    if lock["profile_engine_id"] != LOC_ENGINE_ID:
        raise InputValidationError("loc_engine_lock.profile_engine_id: motor inesperado.")
    engine_sha = _sha_or_none(
        lock["profile_engine_artifact_sha256"],
        "loc_engine_lock.profile_engine_artifact_sha256",
    )
    config_file_sha = _sha_or_none(
        lock["profile_engine_config_file_sha256"],
        "loc_engine_lock.profile_engine_config_file_sha256",
    )
    if not LOC_ENGINE_PATH.is_file() or not LOC_ENGINE_CONFIG_PATH.is_file():
        raise InputValidationError("Motor ou configuração LOC autorizados não foram encontrados.")
    if engine_sha is None or not hmac.compare_digest(engine_sha, file_sha256(LOC_ENGINE_PATH)):
        raise InputValidationError("Motor LOC local diverge da versão congelada no release.")
    if config_file_sha is None or not hmac.compare_digest(
        config_file_sha, file_sha256(LOC_ENGINE_CONFIG_PATH)
    ):
        raise InputValidationError("Configuração LOC local diverge da versão congelada no release.")
    return lock


def _load_profile_engine_module() -> Any:
    """Carrega exatamente o motor autorizado para reexecução determinística."""
    global _PROFILE_ENGINE_MODULE
    if _PROFILE_ENGINE_MODULE is not None:
        return _PROFILE_ENGINE_MODULE
    _profile_engine_lock()
    module_name = "_agtupesquisa_profile_ranker_authorized"
    spec = importlib.util.spec_from_file_location(module_name, LOC_ENGINE_PATH)
    if spec is None or spec.loader is None:
        raise InputValidationError("Não foi possível carregar o motor LOC autorizado.")
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = loaded
    try:
        spec.loader.exec_module(loaded)
    except Exception as exc:  # erro do artefato externo é convertido no contrato local
        sys.modules.pop(module_name, None)
        raise InputValidationError("Falha ao carregar o motor LOC autorizado.") from exc
    _PROFILE_ENGINE_MODULE = loaded
    return loaded


def _load_visual_spatial_engine_module() -> Any:
    """Carrega o vínculo visual externo sem permitir que ele participe de LOC."""
    global _VISUAL_SPATIAL_ENGINE_MODULE
    if _VISUAL_SPATIAL_ENGINE_MODULE is not None:
        return _VISUAL_SPATIAL_ENGINE_MODULE
    if not VISUAL_SPATIAL_ENGINE_PATH.is_file():
        raise InputValidationError("Módulo visual-espacial não foi encontrado.")
    # Quando este arquivo é executado como script, o módulo visual importa
    # ``integrated_protocol``. O alias evita uma segunda carga com classes de
    # exceção distintas e mantém um único contrato em memória.
    sys.modules.setdefault("integrated_protocol", sys.modules[__name__])
    module_name = "_agtupesquisa_visual_spatial_binding_authorized"
    spec = importlib.util.spec_from_file_location(module_name, VISUAL_SPATIAL_ENGINE_PATH)
    if spec is None or spec.loader is None:
        raise InputValidationError("Não foi possível carregar o módulo visual-espacial.")
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = loaded
    try:
        spec.loader.exec_module(loaded)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise InputValidationError("Falha ao carregar o módulo visual-espacial.") from exc
    _VISUAL_SPATIAL_ENGINE_MODULE = loaded
    return loaded


def _validate_profile_ranked_row(row: Any, path: str) -> str:
    if not isinstance(row, Mapping):
        raise InputValidationError(f"{path}: objeto esperado.")
    _require_keys(row, _PROFILE_ROW_KEYS, path)
    _reject_extra_keys(row, _PROFILE_ROW_KEYS, path)
    sector_id = _identifier(row["sector_id"], f"{path}.sector_id")
    for field in (
        "territorial_score", "profile_compatibility", "evidence_strength",
        "effective_lambda", "profile_score",
    ):
        value = _finite(row[field], f"{path}.{field}")
        if not 0.0 <= value <= 1.0:
            raise InputValidationError(f"{path}.{field}: valor fora de [0,1].")
    delta = _finite(row["profile_delta"], f"{path}.profile_delta")
    if not -1.0 <= delta <= 1.0:
        raise InputValidationError(f"{path}.profile_delta: valor fora de [-1,1].")
    for field in ("territorial_rank", "profile_rank"):
        rank = row[field]
        if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
            raise InputValidationError(f"{path}.{field}: inteiro positivo esperado.")
    return sector_id


def _validate_profile_input(
    profile_input: Any,
    payload: Mapping[str, Any],
    path: str,
) -> tuple[str, list[str], str, str | None]:
    """Valida e autentica a entrada congelada que efetivamente alimentou o PERFIL V3."""
    if not isinstance(profile_input, Mapping):
        raise InputValidationError(f"{path}: objeto esperado.")
    enforce_ground_truth_firewall(profile_input, path)
    _require_keys(profile_input, _PROFILE_INPUT_KEYS, path)
    _reject_extra_keys(profile_input, _PROFILE_INPUT_KEYS, path)
    if profile_input["protocol_version"] != "PERFIL-V3-QUANT-v1.0":
        raise InputValidationError(f"{path}.protocol_version: versão inesperada.")
    if profile_input["scenario_id"] != payload["scenario_id"]:
        raise InputValidationError(f"{path}.scenario_id: cenário incompatível com o caso.")
    candidate_id = _identifier(profile_input["candidate_id"], f"{path}.candidate_id")
    if profile_input["record_status"] != "CONGELADO":
        raise InputValidationError(f"{path}.record_status: entrada PERFIL V3 deve estar congelada.")
    created_at = _datetime(profile_input["created_at"], f"{path}.created_at")
    if profile_input["ground_truth_absent"] is not True:
        raise GroundTruthFirewallError(f"{path}.ground_truth_absent deve ser true.")
    source_loc_input_sha = _sha_or_none(
        profile_input["source_loc_input_sha256"],
        f"{path}.source_loc_input_sha256",
    )
    expected_loc_input_sha = calculate_loc_input_sha256(payload)
    if source_loc_input_sha is None or not hmac.compare_digest(
        source_loc_input_sha, expected_loc_input_sha
    ):
        raise InputValidationError(
            f"{path}.source_loc_input_sha256: entrada PERFIL V3 pertence a outro contexto LOC."
        )
    if (
        not isinstance(profile_input["source_case_revision"], int)
        or isinstance(profile_input["source_case_revision"], bool)
        or profile_input["source_case_revision"] != payload["case_revision"]
    ):
        raise InputValidationError(
            f"{path}.source_case_revision: revisão incompatível com o caso."
        )

    artifacts = payload["source_artifacts"]
    for input_field, case_field in (
        ("source_profile_compiled_sha256", "profile_v2_compiled_sha256"),
        ("source_territorial_manifest_sha256", "territorial_manifest_sha256"),
    ):
        declared = _sha_or_none(profile_input[input_field], f"{path}.{input_field}")
        expected = _sha_or_none(artifacts[case_field], f"case.source_artifacts.{case_field}")
        if declared != expected:
            raise InputValidationError(f"{path}.{input_field}: origem incompatível com o caso.")
    spatial_review_sha = _sha_or_none(
        profile_input["source_spatial_review_sha256"],
        f"{path}.source_spatial_review_sha256",
    )

    sectors = _array(profile_input["sectors"], f"{path}.sectors", max_items=1000)
    if len(sectors) < 2:
        raise InputValidationError(f"{path}.sectors: ao menos dois setores esperados.")
    sector_ids: list[str] = []
    for index, sector in enumerate(sectors):
        sector_path = f"{path}.sectors[{index}]"
        if not isinstance(sector, Mapping):
            raise InputValidationError(f"{sector_path}: objeto esperado.")
        _require_keys(sector, _PROFILE_INPUT_SECTOR_KEYS, sector_path)
        _reject_extra_keys(sector, _PROFILE_INPUT_SECTOR_KEYS, sector_path)
        sector_ids.append(_identifier(sector["sector_id"], f"{sector_path}.sector_id"))
        score = _finite(sector["territorial_score"], f"{sector_path}.territorial_score")
        if not 0.0 <= score <= 1.0:
            raise InputValidationError(f"{sector_path}.territorial_score: valor fora de [0,1].")
        for field in ("bearing_start_deg", "bearing_end_deg"):
            bearing = _finite(sector[field], f"{sector_path}.{field}")
            if not 0.0 <= bearing <= 360.0:
                raise InputValidationError(f"{sector_path}.{field}: valor fora de [0,360].")
        polygon = sector["polygon"]
        if not _valid_geojson_polygon([polygon]):
            raise InputValidationError(f"{sector_path}.polygon: polígono WGS 84 válido esperado.")
    _unique(sector_ids, f"{path}.sectors.sector_id")
    _array(profile_input["hypotheses"], f"{path}.hypotheses", max_items=1000)

    freeze = profile_input["freeze_metadata"]
    freeze_path = f"{path}.freeze_metadata"
    if not isinstance(freeze, Mapping):
        raise InputValidationError(f"{freeze_path}: objeto esperado.")
    freeze_keys = {"frozen_at", "projection_id", "payload_sha256"}
    _require_keys(freeze, freeze_keys, freeze_path)
    _reject_extra_keys(freeze, freeze_keys, freeze_path)
    frozen_at = _datetime(freeze["frozen_at"], f"{freeze_path}.frozen_at")
    if frozen_at < created_at:
        raise InputValidationError(f"{freeze_path}.frozen_at: anterior à criação da entrada.")
    if freeze["projection_id"] != "PERFIL-V3-INPUT-FREEZE-PROJECTION-v1":
        raise InputValidationError(f"{freeze_path}.projection_id: valor inesperado.")
    case_freeze = payload.get("freeze_metadata")
    if payload.get("record_status") == "CONGELADO" and isinstance(case_freeze, Mapping):
        profile_cutoff = _datetime(
            case_freeze.get("frozen_at"), "case.freeze_metadata.frozen_at"
        )
    else:
        profile_cutoff = _datetime(
            payload["search_context"]["assessment_at"],
            "case.search_context.assessment_at",
        )
    if created_at > profile_cutoff or frozen_at > profile_cutoff:
        raise InputValidationError(
            f"{path}: entrada PERFIL V3 posterior ao corte temporal do caso."
        )
    declared_freeze_sha = _sha_or_none(freeze["payload_sha256"], f"{freeze_path}.payload_sha256")
    projected = deepcopy(dict(profile_input))
    projected["freeze_metadata"] = dict(projected["freeze_metadata"])
    projected["freeze_metadata"].pop("payload_sha256", None)
    expected_freeze_sha = canonical_sha256(projected)
    if declared_freeze_sha is None or not hmac.compare_digest(
        declared_freeze_sha, expected_freeze_sha
    ):
        raise InputValidationError(f"{freeze_path}.payload_sha256: entrada PERFIL V3 alterada.")
    return candidate_id, sector_ids, canonical_sha256(profile_input), spatial_review_sha


def _validate_profile_result(
    result: Any,
    payload: Mapping[str, Any],
    profile_input: Mapping[str, Any],
    path: str,
) -> tuple[str, list[str]]:
    """Valida uma saída real do PERFIL V3 sem criar ranking entre candidatos."""
    if not isinstance(result, Mapping):
        raise InputValidationError(f"{path}: objeto esperado.")
    enforce_ground_truth_firewall(result, path)
    _require_keys(result, _PROFILE_RESULT_KEYS, path)
    _reject_extra_keys(result, _PROFILE_RESULT_KEYS, path)

    if result["engine_id"] != LOC_ENGINE_ID:
        raise InputValidationError(f"{path}.engine_id: motor PERFIL V3 não autorizado.")
    if result["protocol_id"] != "PERFIL-V3-QUANT-v1.0":
        raise InputValidationError(f"{path}.protocol_id: protocolo inesperado.")
    if result["config_status"] not in {"CANDIDATO_A_CONGELAMENTO", "CONGELADO"}:
        raise InputValidationError(f"{path}.config_status: estado de configuração inválido.")
    if result["scenario_id"] != payload["scenario_id"]:
        raise InputValidationError(f"{path}.scenario_id: cenário incompatível com o caso.")
    candidate_id = _identifier(result["candidate_id"], f"{path}.candidate_id")
    if result["mode"] != "QUANTITATIVO_PROSPECTIVO_LIMITADO":
        raise InputValidationError(f"{path}.mode: modo inesperado.")
    if result["ground_truth_absent"] is not True:
        raise GroundTruthFirewallError(f"{path}.ground_truth_absent deve ser true.")
    if result["source_loc_input_sha256"] != profile_input["source_loc_input_sha256"]:
        raise InputValidationError(
            f"{path}.source_loc_input_sha256: diverge da entrada PERFIL V3."
        )
    if result["source_case_revision"] != profile_input["source_case_revision"]:
        raise InputValidationError(
            f"{path}.source_case_revision: diverge da entrada PERFIL V3."
        )
    if _sha_or_none(result["input_sha256"], f"{path}.input_sha256") is None:
        raise InputValidationError(f"{path}.input_sha256: SHA-256 obrigatório.")
    declared_config_sha = _sha_or_none(result["config_sha256"], f"{path}.config_sha256")
    if declared_config_sha is None or not hmac.compare_digest(
        declared_config_sha, _profile_config_sha256()
    ):
        raise InputValidationError(
            f"{path}.config_sha256: conteúdo canônico da configuração não confere."
        )

    input_path = (
        path.rsplit(".profile_result", 1)[0] + ".profile_input"
        if path.endswith(".profile_result")
        else f"{path}.source_input"
    )
    input_candidate_id, input_sector_ids, input_sha, input_spatial_sha = _validate_profile_input(
        profile_input, payload, input_path
    )
    if candidate_id != input_candidate_id:
        raise InputValidationError(f"{path}.candidate_id: diverge da entrada PERFIL V3.")
    if not hmac.compare_digest(result["input_sha256"], input_sha):
        raise InputValidationError(f"{path}.input_sha256: não corresponde à entrada PERFIL V3 embutida.")
    source_pairs = (
        ("source_profile_compiled_sha256", "source_profile_compiled_sha256"),
        ("source_territorial_manifest_sha256", "source_territorial_manifest_sha256"),
        ("source_spatial_review_sha256", "source_spatial_review_sha256"),
    )
    for result_field, input_field in source_pairs:
        declared = _sha_or_none(result[result_field], f"{path}.{result_field}")
        expected = _sha_or_none(profile_input[input_field], f"{input_path}.{input_field}")
        if declared != expected:
            raise InputValidationError(
                f"{path}.{result_field}: origem incompatível com a entrada PERFIL V3."
            )
    if _sha_or_none(result["source_spatial_review_sha256"], f"{path}.source_spatial_review_sha256") != input_spatial_sha:
        raise InputValidationError(f"{path}.source_spatial_review_sha256: revisão espacial divergente.")

    if not isinstance(result["abstained"], bool):
        raise InputValidationError(f"{path}.abstained: booleano esperado.")
    if result["abstention_reason"] is not None and not isinstance(
        result["abstention_reason"], str
    ):
        raise InputValidationError(f"{path}.abstention_reason: texto ou null esperado.")
    if result["abstained"] and not result["abstention_reason"]:
        raise InputValidationError(f"{path}.abstention_reason: obrigatório quando há abstenção.")
    if not result["abstained"] and result["abstention_reason"] is not None:
        raise InputValidationError(f"{path}.abstention_reason: deve ser null sem abstenção.")
    warnings = _array(result["warnings"], f"{path}.warnings", max_items=100)
    if any(not isinstance(item, str) or len(item) > 1000 for item in warnings):
        raise InputValidationError(f"{path}.warnings: textos de até 1000 caracteres esperados.")
    if warnings != sorted(set(warnings)):
        raise InputValidationError(f"{path}.warnings: lista ordenada e sem duplicatas esperada.")
    for field in ("evidence_quality_policy", "aggregation_policy"):
        if not isinstance(result[field], str) or not result[field] or len(result[field]) > 1000:
            raise InputValidationError(f"{path}.{field}: texto não vazio de até 1000 caracteres esperado.")
    for field in (
        "group_records", "family_records", "excluded_hypotheses", "lambda_results",
    ):
        _array(result[field], f"{path}.{field}", max_items=1000)
    if not result["lambda_results"]:
        raise InputValidationError(f"{path}.lambda_results: ao menos um resultado esperado.")
    primary_lambda = _finite(result["primary_lambda"], f"{path}.primary_lambda")
    if not 0.0 <= primary_lambda <= 1.0:
        raise InputValidationError(f"{path}.primary_lambda: valor fora de [0,1].")

    row_sets: dict[str, list[str]] = {}
    for field in ("primary_rows", "operational_rows"):
        rows = _array(result[field], f"{path}.{field}", max_items=1000)
        if not rows:
            raise InputValidationError(f"{path}.{field}: ao menos um setor esperado.")
        row_sector_ids = [
            _validate_profile_ranked_row(row, f"{path}.{field}[{index}]")
            for index, row in enumerate(rows)
        ]
        _unique(row_sector_ids, f"{path}.{field}.sector_id")
        row_sets[field] = row_sector_ids

    sector_order = _array(result["sector_order"], f"{path}.sector_order", max_items=1000)
    if not sector_order:
        raise InputValidationError(f"{path}.sector_order: ao menos um setor esperado.")
    for index, sector_id in enumerate(sector_order):
        _identifier(sector_id, f"{path}.sector_order[{index}]")
    _unique(sector_order, f"{path}.sector_order")
    sector_set = set(sector_order)
    if set(row_sets["primary_rows"]) != sector_set:
        raise InputValidationError(f"{path}.primary_rows: setores divergem de sector_order.")
    if set(row_sets["operational_rows"]) != sector_set:
        raise InputValidationError(f"{path}.operational_rows: setores divergem de sector_order.")
    if sector_set != set(input_sector_ids):
        raise InputValidationError(f"{path}.sector_order: setores divergem da entrada PERFIL V3.")

    if not isinstance(result["operational_effect_applied"], bool):
        raise InputValidationError(f"{path}.operational_effect_applied: booleano esperado.")
    if result["operational_status"] not in {
        "ABSTENCAO_PERFIL", "REVISAR_INSTABILIDADE", "EFEITO_PERFIL_APLICADO",
    }:
        raise InputValidationError(f"{path}.operational_status: valor inválido.")
    if not isinstance(result["stability"], Mapping):
        raise InputValidationError(f"{path}.stability: objeto esperado.")
    scope = result["scope_guards"]
    if not isinstance(scope, Mapping):
        raise InputValidationError(f"{path}.scope_guards: objeto esperado.")
    _require_keys(scope, _PROFILE_SCOPE_GUARD_KEYS, f"{path}.scope_guards")
    _reject_extra_keys(scope, _PROFILE_SCOPE_GUARD_KEYS, f"{path}.scope_guards")
    if dict(scope) != _PROFILE_SCOPE_GUARD_EXPECTED:
        raise InputValidationError(
            f"{path}.scope_guards: guardas divergem da saída autorizada do PERFIL V3."
        )

    firewall = result["firewall_manifest"]
    if not isinstance(firewall, Mapping):
        raise InputValidationError(f"{path}.firewall_manifest: objeto esperado.")
    firewall_keys = {"recursive_key_scan", "explicit_text_marker_scan", "freeze_hash_verified", "status"}
    _require_keys(firewall, firewall_keys, f"{path}.firewall_manifest")
    _reject_extra_keys(firewall, firewall_keys, f"{path}.firewall_manifest")
    if (
        firewall["recursive_key_scan"] is not True
        or firewall["explicit_text_marker_scan"] is not True
        or firewall["freeze_hash_verified"] is not True
        or firewall["status"] != "PASS"
    ):
        raise InputValidationError(f"{path}.firewall_manifest: verificação PERFIL V3 incompleta.")

    declared_output_sha = _sha_or_none(result["output_sha256"], f"{path}.output_sha256")
    projected = deepcopy(dict(result))
    projected.pop("output_sha256", None)
    expected_output_sha = canonical_sha256(projected)
    if declared_output_sha is None or not hmac.compare_digest(
        declared_output_sha, expected_output_sha
    ):
        raise InputValidationError(f"{path}.output_sha256: resultado PERFIL V3 alterado.")
    try:
        recomputed_result = _load_profile_engine_module().rank_profile(
            deepcopy(dict(profile_input))
        )
    except Exception as exc:
        raise InputValidationError(
            f"{path}: não foi possível reexecutar deterministicamente o PERFIL V3."
        ) from exc
    if canonical_json_bytes(recomputed_result) != canonical_json_bytes(result):
        raise InputValidationError(
            f"{path}: saída não corresponde à reexecução do motor PERFIL V3 autorizado."
        )
    return candidate_id, list(row_sets["operational_rows"])


def build_loc_result_envelope(
    payload: Mapping[str, Any],
    profile_runs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Adapta pares entrada/saída PERFIL V3 ao LOC, sem comparar candidatos."""
    _require_keys(payload, {"scenario_id", "case_revision", "source_artifacts"}, "case")
    if not isinstance(payload["case_revision"], int) or isinstance(payload["case_revision"], bool):
        raise InputValidationError("case.case_revision: inteiro esperado.")
    if not profile_runs:
        raise InputValidationError("profile_runs: ao menos uma execução PERFIL V3 é obrigatória.")
    if len(profile_runs) > 100:
        raise InputValidationError("profile_runs: máximo de 100 execuções por envelope.")
    ordered_runs = sorted(
        (deepcopy(dict(run)) for run in profile_runs),
        key=lambda item: str(item.get("candidate_id", "")),
    )
    candidate_ids: list[str] = []
    sector_ids: list[str] = []
    for index, run in enumerate(ordered_runs):
        path = f"loc_result.profile_runs[{index}]"
        if not isinstance(run, Mapping):
            raise InputValidationError(f"{path}: objeto esperado.")
        run_keys = {"candidate_id", "profile_input", "profile_result"}
        _require_keys(run, run_keys, path)
        _reject_extra_keys(run, run_keys, path)
        run_candidate_id = _identifier(run["candidate_id"], f"{path}.candidate_id")
        candidate_id, result_sector_ids = _validate_profile_result(
            run["profile_result"], payload, run["profile_input"], f"{path}.profile_result"
        )
        if run_candidate_id != candidate_id:
            raise InputValidationError(f"{path}.candidate_id: diverge da entrada/saída PERFIL V3.")
        candidate_ids.append(candidate_id)
        sector_ids.extend(result_sector_ids)
    _unique(candidate_ids, "loc_result.profile_runs.candidate_id")
    _unique(sector_ids, "loc_result.profile_runs.operational_rows.sector_id")
    engine_lock = _profile_engine_lock()
    return {
        "loc_result_contract_version": LOC_RESULT_CONTRACT_VERSION,
        "envelope_engine_id": LOC_ENVELOPE_ENGINE_ID,
        "profile_engine_id": LOC_ENGINE_ID,
        "profile_engine_artifact_sha256": engine_lock["profile_engine_artifact_sha256"],
        "profile_engine_config_file_sha256": engine_lock["profile_engine_config_file_sha256"],
        "scenario_id": payload["scenario_id"],
        "case_revision": payload["case_revision"],
        "loc_input_sha256": calculate_loc_input_sha256(payload),
        "ground_truth_used": False,
        "blind_processing": True,
        "cross_candidate_ranking": False,
        "profile_runs": ordered_runs,
    }


def _inspect_loc_result_artifact(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Distingue integridade dos bytes de validade semantica do resultado LOC.

    Arquivos legados ou binarios podem ter os bytes autenticados, mas nao sao
    promovidos a resultado cego validado. Um JSON que se apresenta como
    contrato LOC deve satisfazer integralmente o envelope abaixo.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {
            "content_validation": "INTEGRITY_ONLY_NON_JSON",
            "loc_sector_ids": [],
            "loc_candidate_ids": [],
        }
    try:
        document = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "content_validation": "INTEGRITY_ONLY_NON_JSON",
            "loc_sector_ids": [],
            "loc_candidate_ids": [],
        }

    # JSON externo tambem atravessa a barreira de ground truth antes de qualquer
    # afirmacao sobre cegamento ou validade do conteudo.
    enforce_ground_truth_firewall(document, "$loc_result")
    if not isinstance(document, Mapping):
        return {
            "content_validation": "INTEGRITY_ONLY_UNCONTRACTED_JSON",
            "loc_sector_ids": [],
            "loc_candidate_ids": [],
        }

    required = {
        "loc_result_contract_version", "envelope_engine_id", "profile_engine_id",
        "profile_engine_artifact_sha256", "profile_engine_config_file_sha256",
        "scenario_id", "case_revision", "loc_input_sha256", "ground_truth_used",
        "blind_processing", "cross_candidate_ranking", "profile_runs",
    }
    contract_markers = required & set(document)
    if not contract_markers:
        return {
            "content_validation": "INTEGRITY_ONLY_UNCONTRACTED_JSON",
            "loc_sector_ids": [],
            "loc_candidate_ids": [],
        }
    missing = sorted(required - set(document))
    if missing:
        raise InputValidationError(
            "loc_result: contrato declarado incompleto; ausentes=" + ", ".join(missing) + "."
        )
    _reject_extra_keys(document, required, "loc_result")
    if document["loc_result_contract_version"] != LOC_RESULT_CONTRACT_VERSION:
        raise InputValidationError("loc_result.loc_result_contract_version: versao inesperada.")
    if document["envelope_engine_id"] != LOC_ENVELOPE_ENGINE_ID:
        raise InputValidationError("loc_result.envelope_engine_id: envelope não autorizado.")
    if document["profile_engine_id"] != LOC_ENGINE_ID:
        raise InputValidationError("loc_result.profile_engine_id: motor não autorizado.")
    declared_engine_sha = _sha_or_none(
        document["profile_engine_artifact_sha256"],
        "loc_result.profile_engine_artifact_sha256",
    )
    engine_lock = _profile_engine_lock()
    expected_engine_sha = engine_lock["profile_engine_artifact_sha256"]
    if declared_engine_sha is None or not hmac.compare_digest(
        declared_engine_sha, expected_engine_sha
    ):
        raise InputValidationError(
            "loc_result.profile_engine_artifact_sha256: motor produtor incompatível com a versão autorizada."
        )
    declared_config_sha = _sha_or_none(
        document["profile_engine_config_file_sha256"],
        "loc_result.profile_engine_config_file_sha256",
    )
    expected_config_sha = engine_lock["profile_engine_config_file_sha256"]
    if declared_config_sha is None or not hmac.compare_digest(
        declared_config_sha, expected_config_sha
    ):
        raise InputValidationError(
            "loc_result.profile_engine_config_file_sha256: arquivo de configuração incompatível."
        )
    if document["scenario_id"] != payload["scenario_id"]:
        raise InputValidationError("loc_result.scenario_id: cenario incompatível com o caso.")
    if document["case_revision"] != payload["case_revision"]:
        raise InputValidationError("loc_result.case_revision: revisao obsoleta ou incompatível.")
    if not isinstance(document["case_revision"], int) or isinstance(document["case_revision"], bool):
        raise InputValidationError("loc_result.case_revision: inteiro esperado.")
    declared_input_sha = _sha_or_none(document["loc_input_sha256"], "loc_result.loc_input_sha256")
    expected_input_sha = calculate_loc_input_sha256(payload)
    if declared_input_sha is None or not hmac.compare_digest(declared_input_sha, expected_input_sha):
        raise InputValidationError("loc_result.loc_input_sha256: nao corresponde a projecao LOC deste caso.")
    if document["ground_truth_used"] is not False:
        raise GroundTruthFirewallError("loc_result.ground_truth_used deve ser false.")
    if document["blind_processing"] is not True:
        raise InputValidationError("loc_result.blind_processing deve ser true.")
    if document["cross_candidate_ranking"] is not False:
        raise InputValidationError("loc_result.cross_candidate_ranking deve ser false.")

    profile_runs = _array(document["profile_runs"], "loc_result.profile_runs", max_items=100)
    if not profile_runs:
        raise InputValidationError("loc_result.profile_runs: ao menos uma execução é obrigatória.")
    candidate_ids: list[str] = []
    sector_ids: list[str] = []
    for index, run in enumerate(profile_runs):
        run_path = f"loc_result.profile_runs[{index}]"
        if not isinstance(run, Mapping):
            raise InputValidationError(f"{run_path}: objeto esperado.")
        run_keys = {"candidate_id", "profile_input", "profile_result"}
        _require_keys(run, run_keys, run_path)
        _reject_extra_keys(run, run_keys, run_path)
        run_candidate_id = _identifier(run["candidate_id"], f"{run_path}.candidate_id")
        candidate_id, result_sector_ids = _validate_profile_result(
            run["profile_result"], payload, run["profile_input"],
            f"{run_path}.profile_result",
        )
        if run_candidate_id != candidate_id:
            raise InputValidationError(f"{run_path}.candidate_id: divergente da execução PERFIL V3.")
        candidate_ids.append(candidate_id)
        sector_ids.extend(result_sector_ids)
    _unique(candidate_ids, "loc_result.profile_runs.candidate_id")
    if candidate_ids != sorted(candidate_ids):
        raise InputValidationError(
            "loc_result.profile_runs: ordem determinística por candidate_id esperada."
        )
    _unique(sector_ids, "loc_result.profile_runs.operational_rows.sector_id")

    return {
        "content_validation": "LOC_CONTRACT_VALIDATED_DECLARED_BLIND",
        "loc_sector_ids": sorted(sector_ids),
        "loc_candidate_ids": sorted(candidate_ids),
    }


def _require_keys(obj: Mapping[str, Any], required: Iterable[str], path: str) -> None:
    missing = sorted(set(required) - set(obj))
    if missing:
        raise InputValidationError(f"{path}: campos obrigatórios ausentes: {', '.join(missing)}")


def _reject_extra_keys(obj: Mapping[str, Any], allowed: Iterable[str], path: str) -> None:
    extras = sorted(set(obj) - set(allowed))
    if extras:
        raise InputValidationError(f"{path}: campos não permitidos: {', '.join(extras)}")


def _identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise InputValidationError(f"{path}: identificador inválido.")
    return value


def _sha_or_none(value: Any, path: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise InputValidationError(f"{path}: SHA-256 minúsculo esperado.")
    return value


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputValidationError(f"{path}: número esperado.")
    number = float(value)
    if not math.isfinite(number):
        raise InputValidationError(f"{path}: número finito esperado.")
    return number


def _scalar(value: Any, path: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str) and len(value) > 1000:
            raise InputValidationError(f"{path}: texto excede 1000 caracteres.")
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _finite(value, path)
    raise InputValidationError(f"{path}: valor escalar esperado.")


def _datetime(value: Any, path: str, *, nullable: bool = False) -> datetime | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise InputValidationError(f"{path}: data/hora textual obrigatória.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputValidationError(f"{path}: data/hora inválida.") from exc
    if parsed.utcoffset() is None:
        raise InputValidationError(f"{path}: fuso horário obrigatório.")
    return parsed


def _unique(values: Iterable[str], path: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise InputValidationError(f"{path}: identificador duplicado: {value}")
        seen.add(value)


def _array(value: Any, path: str, *, max_items: int | None = None) -> list[Any]:
    if not isinstance(value, list):
        raise InputValidationError(f"{path}: lista esperada.")
    if max_items is not None and len(value) > max_items:
        raise InputValidationError(f"{path}: excede o máximo de {max_items} itens.")
    return value


def _validate_evidence(evidence: Any, path: str) -> None:
    if not isinstance(evidence, Mapping):
        raise InputValidationError(f"{path}: objeto esperado.")
    keys = {
        "evidence_id", "source_type", "source_code", "nature", "confidence",
        "observed_at", "time_precision", "valid_until", "authorized_for_model",
    }
    _require_keys(evidence, keys, path)
    _reject_extra_keys(evidence, keys, path)
    _identifier(evidence["evidence_id"], f"{path}.evidence_id")
    allowed_sources = {
        "VITIMA", "FAMILIAR", "TESTEMUNHA", "OPERADOR", "REGISTRO", "FOTO_SOLO",
        "IMAGEM_DRONE", "CAMADA_PUBLICA", "SENSOR", "DOCUMENTO_OPERACIONAL", "OUTRA",
        "NAO_DISPONIVEL",
    }
    if evidence["source_type"] not in allowed_sources:
        raise InputValidationError(f"{path}.source_type: valor inválido.")
    if evidence["source_code"] is not None and (
        not isinstance(evidence["source_code"], str) or len(evidence["source_code"]) > 128
    ):
        raise InputValidationError(f"{path}.source_code: texto curto ou null esperado.")
    enforce_text_sanitization(evidence["source_code"], f"{path}.source_code")
    allowed_natures = {"CONFIRMADO", "OBSERVADO", "RELATADO", "SUSPEITO", "INFERIDO", "NAO_DISPONIVEL"}
    if evidence["nature"] not in allowed_natures:
        raise InputValidationError(f"{path}.nature: valor inválido.")
    if evidence["confidence"] not in {"ALTA", "MEDIA", "BAIXA", "NAO_AVALIADA"}:
        raise InputValidationError(f"{path}.confidence: valor inválido.")
    if evidence["time_precision"] not in {"EXATA", "APROXIMADA", "NAO_DISPONIVEL"}:
        raise InputValidationError(f"{path}.time_precision: valor inválido.")
    observed = _datetime(evidence["observed_at"], f"{path}.observed_at", nullable=True)
    valid_until = _datetime(evidence["valid_until"], f"{path}.valid_until", nullable=True)
    if evidence["time_precision"] == "NAO_DISPONIVEL" and observed is not None:
        raise InputValidationError(f"{path}: horário deve ser null quando a precisão é indisponível.")
    if evidence["time_precision"] != "NAO_DISPONIVEL" and observed is None:
        raise InputValidationError(f"{path}: horário obrigatório quando a precisão é conhecida.")
    if valid_until is not None and observed is not None and valid_until < observed:
        raise InputValidationError(f"{path}: valid_until anterior a observed_at.")
    if not isinstance(evidence["authorized_for_model"], bool):
        raise InputValidationError(f"{path}.authorized_for_model: booleano esperado.")
    if evidence["nature"] == "NAO_DISPONIVEL":
        expected = {
            "source_type": "NAO_DISPONIVEL", "source_code": None, "confidence": "NAO_AVALIADA",
            "observed_at": None, "time_precision": "NAO_DISPONIVEL", "valid_until": None,
            "authorized_for_model": False,
        }
        for key, value in expected.items():
            if evidence[key] != value:
                raise InputValidationError(f"{path}.{key}: incoerente com natureza NAO_DISPONIVEL.")


def _validate_freeze(metadata: Any, path: str, projection_id: str) -> None:
    if not isinstance(metadata, Mapping):
        raise InputValidationError(f"{path}: objeto de congelamento esperado.")
    keys = {"frozen_at", "projection_id", "payload_sha256"}
    _require_keys(metadata, keys, path)
    _reject_extra_keys(metadata, keys, path)
    _datetime(metadata["frozen_at"], f"{path}.frozen_at")
    if metadata["projection_id"] != projection_id:
        raise InputValidationError(f"{path}.projection_id: valor inesperado.")
    if _sha_or_none(metadata["payload_sha256"], f"{path}.payload_sha256") is None:
        raise InputValidationError(f"{path}.payload_sha256: SHA-256 obrigatório.")


def case_freeze_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    projected = deepcopy(dict(payload))
    metadata = projected.get("freeze_metadata")
    if not isinstance(metadata, Mapping):
        raise InputValidationError("freeze_metadata ausente.")
    projected["freeze_metadata"] = dict(metadata)
    projected["freeze_metadata"].pop("payload_sha256", None)
    return projected


def calculate_case_freeze_sha256(payload: Mapping[str, Any]) -> str:
    return canonical_sha256(case_freeze_projection(payload))


def event_freeze_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    projected = deepcopy(dict(payload))
    metadata = projected.get("freeze_metadata")
    if not isinstance(metadata, Mapping):
        raise InputValidationError("freeze_metadata ausente.")
    projected["freeze_metadata"] = dict(metadata)
    projected["freeze_metadata"].pop("payload_sha256", None)
    return projected


def calculate_event_freeze_sha256(payload: Mapping[str, Any]) -> str:
    return canonical_sha256(event_freeze_projection(payload))


def validate_case(payload: Mapping[str, Any]) -> None:
    enforce_ground_truth_firewall(payload)
    keys = {
        "protocol_version", "scenario_id", "case_revision", "parent_payload_sha256", "study_mode",
        "record_status", "created_at", "operator_code", "pseudonymized",
        "text_fields_sanitized", "blind_processing", "storage_segregated",
        "ground_truth_absent", "person_location_status", "planning_point", "search_context",
        "profile_facts", "visual_evidence", "urgency_observations",
        "detectability_assessments", "source_artifacts", "search_event_hashes",
        "freeze_metadata",
    }
    _require_keys(payload, keys, "case")
    _reject_extra_keys(payload, keys, "case")
    if payload["protocol_version"] != PROTOCOL_VERSION:
        raise InputValidationError("case.protocol_version: versão inesperada.")
    _identifier(payload["scenario_id"], "case.scenario_id")
    _identifier(payload["operator_code"], "case.operator_code")
    if not isinstance(payload["case_revision"], int) or isinstance(payload["case_revision"], bool) or payload["case_revision"] < 1:
        raise InputValidationError("case.case_revision deve ser inteiro positivo.")
    parent_sha = _sha_or_none(payload["parent_payload_sha256"], "case.parent_payload_sha256")
    if payload["case_revision"] == 1 and parent_sha is not None:
        raise InputValidationError("case.parent_payload_sha256 deve ser null na primeira revisão.")
    if payload["case_revision"] > 1 and parent_sha is None:
        raise InputValidationError("case.parent_payload_sha256 é obrigatório após a primeira revisão.")
    if payload["study_mode"] != "PROSPECTIVO_CEGO":
        raise InputValidationError("case.study_mode deve ser PROSPECTIVO_CEGO.")
    for control in ("pseudonymized", "text_fields_sanitized", "blind_processing", "storage_segregated"):
        if payload[control] is not True:
            raise InputValidationError(f"case.{control} deve ser true.")
    created_at = _datetime(payload["created_at"], "case.created_at")
    if payload["record_status"] not in {"RASCUNHO", "CONGELADO"}:
        raise InputValidationError("case.record_status: valor inválido.")
    if payload["ground_truth_absent"] is not True:
        raise InputValidationError("case.ground_truth_absent deve ser true.")
    if payload["person_location_status"] not in {"DESCONHECIDA", "CONHECIDA_OPERACIONALMENTE"}:
        raise InputValidationError("case.person_location_status: valor inválido.")

    point = payload["planning_point"]
    if not isinstance(point, Mapping):
        raise InputValidationError("case.planning_point: objeto esperado.")
    point_keys = {
        "point_id", "point_role", "point_semantics", "coordinate_source",
        "latitude", "longitude", "position_observed_at", "current_presence_assertion",
        "horizontal_accuracy_m", "horizontal_accuracy_status", "horizontal_accuracy_source",
        "uncertainty_radius_m", "uncertainty_source", "evidence",
    }
    _require_keys(point, point_keys, "case.planning_point")
    _reject_extra_keys(point, point_keys, "case.planning_point")
    _identifier(point["point_id"], "case.planning_point.point_id")
    if point["point_role"] not in _POINT_ROLES:
        raise InputValidationError("case.planning_point.point_role: valor inválido.")
    expected_semantics = {
        "ULTIMO_PONTO_VISTO": "OBSERVACAO_DIRETA",
        "ULTIMO_PONTO_CONHECIDO": "REGISTRO_INDIRETO",
        "PONTO_INICIAL_PLANEJAMENTO": "REFERENCIA_DE_PLANEJAMENTO",
        "ESTIMATIVA_SISTEMA_AEROTRANSPORTADO": "ESTIMATIVA_TECNICA",
    }
    if point["point_semantics"] != expected_semantics[point["point_role"]]:
        raise InputValidationError("case.planning_point.point_semantics incoerente com point_role.")
    allowed_coordinate_sources = {
        "OBSERVACAO_DIRETA", "REGISTRO_OPERACIONAL", "INFORMADO_PELA_FONTE",
        "SISTEMA_AEROTRANSPORTADO",
    }
    if point["coordinate_source"] not in allowed_coordinate_sources:
        raise InputValidationError("case.planning_point.coordinate_source: valor inválido.")
    if (
        point["point_role"] == "ESTIMATIVA_SISTEMA_AEROTRANSPORTADO"
        and point["coordinate_source"] != "SISTEMA_AEROTRANSPORTADO"
    ):
        raise InputValidationError("Estimativa aerotransportada exige coordinate_source correspondente.")
    expected_coordinate_source = {
        "ULTIMO_PONTO_VISTO": "OBSERVACAO_DIRETA",
        "ULTIMO_PONTO_CONHECIDO": "REGISTRO_OPERACIONAL",
    }
    if (
        point["point_role"] in expected_coordinate_source
        and point["coordinate_source"] != expected_coordinate_source[point["point_role"]]
    ):
        raise InputValidationError(
            "case.planning_point.coordinate_source incoerente com o papel do ponto."
        )
    if point["current_presence_assertion"] is not False:
        raise InputValidationError("case.planning_point.current_presence_assertion deve ser false.")
    lat = _finite(point["latitude"], "case.planning_point.latitude")
    lon = _finite(point["longitude"], "case.planning_point.longitude")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise InputValidationError("case.planning_point: coordenada fora do WGS 84.")
    point_at = _datetime(point["position_observed_at"], "case.planning_point.position_observed_at", nullable=True)
    accuracy = point["horizontal_accuracy_m"]
    if accuracy is not None and _finite(accuracy, "case.planning_point.horizontal_accuracy_m") <= 0:
        raise InputValidationError("case.planning_point.horizontal_accuracy_m deve ser positivo.")
    if point["horizontal_accuracy_status"] not in {"INFORMADA", "CALCULADA_DOCUMENTADA", "NAO_DISPONIVEL"}:
        raise InputValidationError("case.planning_point.horizontal_accuracy_status: valor inválido.")
    if point["horizontal_accuracy_status"] == "NAO_DISPONIVEL":
        if accuracy is not None or point["horizontal_accuracy_source"] is not None:
            raise InputValidationError("Precisão horizontal indisponível exige valor e fonte null.")
    elif (
        accuracy is None
        or not isinstance(point["horizontal_accuracy_source"], str)
        or not point["horizontal_accuracy_source"].strip()
    ):
        raise InputValidationError("Precisão horizontal disponível exige valor e fonte.")
    elif len(point["horizontal_accuracy_source"]) > 160:
        raise InputValidationError("case.planning_point.horizontal_accuracy_source excede 160 caracteres.")
    enforce_text_sanitization(
        point["horizontal_accuracy_source"],
        "case.planning_point.horizontal_accuracy_source",
    )
    radius = point["uncertainty_radius_m"]
    if radius is not None and _finite(radius, "case.planning_point.uncertainty_radius_m") <= 0:
        raise InputValidationError("case.planning_point.uncertainty_radius_m deve ser positivo.")
    if point["uncertainty_source"] not in {"INFORMADO_PELA_FONTE", "CALCULADO_DOCUMENTADO", "NAO_DISPONIVEL"}:
        raise InputValidationError("case.planning_point.uncertainty_source: valor inválido.")
    if (point["uncertainty_source"] == "NAO_DISPONIVEL") != (radius is None):
        raise InputValidationError("case.planning_point: raio e origem de incerteza incoerentes.")
    _validate_evidence(point["evidence"], "case.planning_point.evidence")
    if point["evidence"]["nature"] not in {"CONFIRMADO", "OBSERVADO", "RELATADO"}:
        raise InputValidationError(
            "case.planning_point.evidence exige natureza confirmada, observada ou relatada."
        )
    if (
        not isinstance(point["evidence"]["source_code"], str)
        or not point["evidence"]["source_code"].strip()
    ):
        raise InputValidationError("case.planning_point.evidence exige source_code identificado.")
    if point["point_role"] == "ULTIMO_PONTO_VISTO":
        if point_at is None or point["evidence"]["nature"] not in {"OBSERVADO", "CONFIRMADO"}:
            raise InputValidationError("UPV exige horário e evidência observada/confirmada.")
    if (
        point["point_role"] in {"ULTIMO_PONTO_VISTO", "ULTIMO_PONTO_CONHECIDO"}
        and point_at is not None
        and point["evidence"]["time_precision"] == "EXATA"
        and _datetime(
            point["evidence"]["observed_at"],
            "case.planning_point.evidence.observed_at",
        ) != point_at
    ):
        raise InputValidationError(
            "case.planning_point: horário exato do ponto diverge do horário exato da evidência."
        )

    context = payload["search_context"]
    if not isinstance(context, Mapping):
        raise InputValidationError("case.search_context: objeto esperado.")
    context_keys = {
        "assessment_at", "disappearance_at", "elapsed_minutes", "elapsed_precision",
        "environment_type", "travel_mode", "maximum_plausible_travel_minutes",
        "environment_observations",
    }
    _require_keys(context, context_keys, "case.search_context")
    _reject_extra_keys(context, context_keys, "case.search_context")
    assessment_at = _datetime(context["assessment_at"], "case.search_context.assessment_at")
    disappearance_at = _datetime(context["disappearance_at"], "case.search_context.disappearance_at", nullable=True)
    if assessment_at < created_at:
        raise InputValidationError("case.search_context.assessment_at anterior a created_at.")
    if disappearance_at is not None and disappearance_at > assessment_at:
        raise InputValidationError("case.search_context.disappearance_at posterior à avaliação.")
    if point_at is not None and point_at > assessment_at:
        raise InputValidationError("case.planning_point.position_observed_at posterior à avaliação.")
    point_provenance = _evidence_provenance_status(point["evidence"], assessment_at)
    if point_provenance in {"NAO_AUTORIZADA", "FONTE_NAO_IDENTIFICADA", "EVIDENCIA_FUTURA"}:
        raise InputValidationError(
            f"case.planning_point.evidence não pode ser aceita: {point_provenance}."
        )
    elapsed = context["elapsed_minutes"]
    if elapsed is not None and _finite(elapsed, "case.search_context.elapsed_minutes") < 0:
        raise InputValidationError("case.search_context.elapsed_minutes deve ser não negativo.")
    if context["elapsed_precision"] not in {"EXATA", "APROXIMADA", "NAO_DISPONIVEL"}:
        raise InputValidationError("case.search_context.elapsed_precision: valor inválido.")
    if (context["elapsed_precision"] == "NAO_DISPONIVEL") != (elapsed is None):
        raise InputValidationError("case.search_context: tempo transcorrido e precisão incoerentes.")
    if context["elapsed_precision"] == "EXATA":
        if disappearance_at is None:
            raise InputValidationError("Tempo transcorrido exato exige disappearance_at.")
        calculated_elapsed = (assessment_at - disappearance_at).total_seconds() / 60.0
        if not math.isclose(float(elapsed), calculated_elapsed, rel_tol=0.0, abs_tol=1 / 60):
            raise InputValidationError("Tempo transcorrido exato diverge dos timestamps.")
    if context["environment_type"] not in {"URBANO", "PERIURBANO", "RURAL", "MATA", "MISTO", "NAO_DISPONIVEL"}:
        raise InputValidationError("case.search_context.environment_type: valor inválido.")
    if context["travel_mode"] not in {"A_PE", "VEICULO", "EMBARCACAO", "MISTO", "DESCONHECIDO"}:
        raise InputValidationError("case.search_context.travel_mode: valor inválido.")
    max_travel = context["maximum_plausible_travel_minutes"]
    if max_travel is not None and _finite(max_travel, "case.search_context.maximum_plausible_travel_minutes") < 0:
        raise InputValidationError("case.search_context.maximum_plausible_travel_minutes inválido.")
    if max_travel is not None and elapsed is not None and float(max_travel) > float(elapsed):
        raise InputValidationError(
            "case.search_context.maximum_plausible_travel_minutes não pode exceder elapsed_minutes."
        )
    environment_ids: list[str] = []
    environment_observations = _array(
        context["environment_observations"],
        "case.search_context.environment_observations",
        max_items=200,
    )
    for index, observation in enumerate(environment_observations):
        path = f"case.search_context.environment_observations[{index}]"
        if not isinstance(observation, Mapping):
            raise InputValidationError(f"{path}: objeto esperado.")
        allowed = {"observation_id", "domain", "availability", "value", "unit", "evidence"}
        _require_keys(observation, allowed, path)
        _reject_extra_keys(observation, allowed, path)
        environment_ids.append(_identifier(observation["observation_id"], f"{path}.observation_id"))
        if observation["domain"] not in {"CLIMA", "ILUMINACAO", "RELEVO", "VEGETACAO", "HIDROGRAFIA", "VIAS_TRILHAS", "BARREIRA", "ACESSO", "SOLO", "RISCO_AMBIENTAL"}:
            raise InputValidationError(f"{path}.domain: valor inválido.")
        if observation["availability"] not in _AVAILABILITY:
            raise InputValidationError(f"{path}.availability: valor inválido.")
        if observation["availability"] == "NAO_DISPONIVEL" and observation["value"] is not None:
            raise InputValidationError(f"{path}.value deve ser null quando indisponível.")
        _scalar(observation["value"], f"{path}.value")
        enforce_text_sanitization(observation["value"], f"{path}.value")
        if observation["unit"] is not None and not isinstance(observation["unit"], str):
            raise InputValidationError(f"{path}.unit: texto ou null esperado.")
        if isinstance(observation["unit"], str) and len(observation["unit"]) > 40:
            raise InputValidationError(f"{path}.unit excede 40 caracteres.")
        enforce_text_sanitization(observation["unit"], f"{path}.unit")
        _validate_evidence(observation["evidence"], f"{path}.evidence")
        if observation["availability"] != "NAO_DISPONIVEL":
            provenance = _evidence_provenance_status(observation["evidence"], assessment_at)
            if provenance not in {"ELEGIVEL", "EXPIRADA"}:
                raise InputValidationError(f"{path}.evidence sem proveniência utilizável: {provenance}.")
    _unique(environment_ids, "case.search_context.environment_observations")

    fact_ids: list[str] = []
    fact_domains = {
        "FAIXA_ETARIA", "MOBILIDADE", "COGNICAO_ORIENTACAO", "CONDICAO_CLINICA",
        "MEDICACAO", "EXPERIENCIA_AMBIENTE", "FAMILIARIDADE_LOCAL", "COMPORTAMENTO",
        "DESTINO_DECLARADO", "DIRECAO_OBSERVADA", "ATIVIDADE_HABITUAL", "VESTUARIO",
        "CALCADO", "CARGA_EQUIPAMENTO", "AGUA_ALIMENTO_ABRIGO", "SINALIZACAO",
        "COMUNICACAO_BATERIA", "OUTRO",
    }
    profile_facts = _array(payload["profile_facts"], "case.profile_facts", max_items=100)
    for index, fact in enumerate(profile_facts):
        path = f"case.profile_facts[{index}]"
        if not isinstance(fact, Mapping):
            raise InputValidationError(f"{path}: objeto esperado.")
        allowed = {"fact_id", "domain", "availability", "value", "evidence"}
        _require_keys(fact, allowed, path)
        _reject_extra_keys(fact, allowed, path)
        fact_ids.append(_identifier(fact["fact_id"], f"{path}.fact_id"))
        if fact["domain"] not in fact_domains or fact["availability"] not in _AVAILABILITY:
            raise InputValidationError(f"{path}: domínio ou disponibilidade inválidos.")
        if fact["availability"] == "NAO_DISPONIVEL" and fact["value"] is not None:
            raise InputValidationError(f"{path}.value deve ser null quando indisponível.")
        _scalar(fact["value"], f"{path}.value")
        enforce_text_sanitization(fact["value"], f"{path}.value")
        _validate_evidence(fact["evidence"], f"{path}.evidence")
        if fact["availability"] != "NAO_DISPONIVEL":
            provenance = _evidence_provenance_status(fact["evidence"], assessment_at)
            if provenance not in {"ELEGIVEL", "EXPIRADA"}:
                raise InputValidationError(f"{path}.evidence sem proveniência utilizável: {provenance}.")
    _unique(fact_ids, "case.profile_facts")

    recognized_travel_modes: set[str] = set()
    mobility_aliases = {
        "APE": "A_PE",
        "PE": "A_PE",
        "VEICULO": "VEICULO",
        "CARRO": "VEICULO",
        "MOTO": "VEICULO",
        "EMBARCACAO": "EMBARCACAO",
        "BARCO": "EMBARCACAO",
        "MISTO": "MISTO",
        "DESCONHECIDO": "DESCONHECIDO",
    }
    for fact in profile_facts:
        if (
            fact["domain"] == "MOBILIDADE"
            and fact["availability"] == "PRESENTE"
            and _evidence_eligibility(fact["evidence"], assessment_at) == "ELEGIVEL"
            and isinstance(fact["value"], str)
        ):
            normalized = _normalized_key(fact["value"]).upper()
            recognized = mobility_aliases.get(normalized)
            if recognized is not None:
                recognized_travel_modes.add(recognized)
    declared_travel_mode = context["travel_mode"]
    specific_profile_modes = recognized_travel_modes - {"DESCONHECIDO", "MISTO"}
    if (
        len(specific_profile_modes) > 1
        and declared_travel_mode not in {"MISTO", "DESCONHECIDO"}
    ):
        raise InputValidationError(
            "case.search_context.travel_mode não reconcilia fatos elegíveis e contraditórios de MOBILIDADE; use MISTO com suporte ou DESCONHECIDO para revisão."
        )
    if (
        declared_travel_mode == "MISTO"
        and "MISTO" not in recognized_travel_modes
        and len(specific_profile_modes) < 2
    ):
        raise InputValidationError(
            "case.search_context.travel_mode=MISTO requer fato explícito ou ao menos dois modos específicos elegíveis."
        )
    if (
        declared_travel_mode not in {"DESCONHECIDO", "MISTO"}
        and specific_profile_modes
        and declared_travel_mode not in specific_profile_modes
    ):
        raise InputValidationError(
            "case.search_context.travel_mode contradiz fato estruturado e elegível de MOBILIDADE."
        )

    visual_ids: list[str] = []
    visual_hashes: list[str] = []
    visual_evidence = _array(payload["visual_evidence"], "case.visual_evidence", max_items=100)
    for index, visual in enumerate(visual_evidence):
        path = f"case.visual_evidence[{index}]"
        if not isinstance(visual, Mapping):
            raise InputValidationError(f"{path}: objeto esperado.")
        allowed = {
            "visual_id", "file_sha256", "media_type", "platform", "capture_at",
            "capture_time_precision", "capture_time_source",
            "camera_position_relative_to_point", "lens_aim_direction_cardinal",
            "lens_aim_azimuth_deg", "altitude_agl_m", "altitude_agl_source",
            "target_visible", "incidental_people_present", "authorized_for_context",
            "numeric_model_input", "annotations",
        }
        _require_keys(visual, allowed, path)
        _reject_extra_keys(visual, allowed, path)
        visual_ids.append(_identifier(visual["visual_id"], f"{path}.visual_id"))
        visual_sha = _sha_or_none(visual["file_sha256"], f"{path}.file_sha256")
        if visual_sha is None:
            raise InputValidationError(f"{path}.file_sha256: SHA-256 obrigatório.")
        visual_hashes.append(visual_sha)
        if visual["media_type"] not in {"IMAGE_JPEG", "IMAGE_HEIC", "IMAGE_PNG", "VIDEO"}:
            raise InputValidationError(f"{path}.media_type: valor inválido.")
        if visual["platform"] not in {"SOLO", "DRONE_RGB", "DRONE_TERMICO", "OUTRA"}:
            raise InputValidationError(f"{path}.platform: valor inválido.")
        if visual["capture_time_precision"] not in {"EXATA", "APROXIMADA", "NAO_DISPONIVEL"}:
            raise InputValidationError(f"{path}.capture_time_precision: valor inválido.")
        if visual["capture_time_source"] not in {
            "METADADO_ARQUIVO", "REGISTRO_OPERADOR", "ESTIMATIVA_OPERADOR", "NAO_DISPONIVEL"
        }:
            raise InputValidationError(f"{path}.capture_time_source: valor inválido.")
        capture_at = _datetime(visual["capture_at"], f"{path}.capture_at", nullable=True)
        time_unavailable = visual["capture_time_precision"] == "NAO_DISPONIVEL"
        source_unavailable = visual["capture_time_source"] == "NAO_DISPONIVEL"
        if time_unavailable != (capture_at is None) or source_unavailable != (capture_at is None):
            raise InputValidationError(
                f"{path}: horário, precisão temporal e origem temporal incoerentes."
            )
        if capture_at is not None and capture_at > assessment_at:
            raise InputValidationError(f"{path}.capture_at posterior à avaliação do caso.")
        if visual["camera_position_relative_to_point"] not in {"NO_PONTO", "NORTE", "LESTE", "SUL", "OESTE", "NAO_DISPONIVEL", "OUTRA"}:
            raise InputValidationError(f"{path}.camera_position_relative_to_point: valor inválido.")
        if visual["lens_aim_direction_cardinal"] not in {"NADIR", "N", "NE", "E", "SE", "S", "SW", "W", "NW", "NAO_DISPONIVEL", "OUTRA"}:
            raise InputValidationError(f"{path}.lens_aim_direction_cardinal: valor inválido.")
        azimuth = visual["lens_aim_azimuth_deg"]
        if azimuth is not None:
            azimuth = _finite(azimuth, f"{path}.lens_aim_azimuth_deg")
            if not 0 <= azimuth < 360:
                raise InputValidationError(f"{path}.lens_aim_azimuth_deg: valor fora de [0, 360).")
        if visual["lens_aim_direction_cardinal"] in {"NADIR", "NAO_DISPONIVEL"} and azimuth is not None:
            raise InputValidationError(f"{path}: direção NADIR/indisponível exige azimute null.")
        direction = visual["lens_aim_direction_cardinal"]
        if direction in _CARDINAL_AZIMUTH_CENTERS and azimuth is not None:
            center = _CARDINAL_AZIMUTH_CENTERS[direction]
            circular_difference = abs((azimuth - center + 180.0) % 360.0 - 180.0)
            if circular_difference > 22.5:
                raise InputValidationError(
                    f"{path}: azimute incompatível com a direção cardinal informada."
                )
        if visual["altitude_agl_source"] not in {
            "TELEMETRIA", "INFORMADO_PELO_OPERADOR", "ESTIMATIVA_OPERADOR", "NAO_DISPONIVEL"
        }:
            raise InputValidationError(f"{path}.altitude_agl_source: valor inválido.")
        if visual["altitude_agl_m"] is not None and _finite(visual["altitude_agl_m"], f"{path}.altitude_agl_m") < 0:
            raise InputValidationError(f"{path}.altitude_agl_m: valor inválido.")
        if (visual["altitude_agl_source"] == "NAO_DISPONIVEL") != (visual["altitude_agl_m"] is None):
            raise InputValidationError(f"{path}: altitude AGL e origem da altitude incoerentes.")
        if visual["target_visible"] is not False:
            raise InputValidationError(f"{path}.target_visible deve ser false no Conjunto A.")
        if visual["incidental_people_present"] not in {True, False, None}:
            raise InputValidationError(
                f"{path}.incidental_people_present deve ser booleano ou null."
            )
        if not isinstance(visual["authorized_for_context"], bool):
            raise InputValidationError(f"{path}.authorized_for_context: booleano esperado.")
        if visual["numeric_model_input"] is not False:
            raise InputValidationError(f"{path}.numeric_model_input deve ser false nesta versão.")
        annotations = _array(visual["annotations"], f"{path}.annotations", max_items=30)
        for ann_index, annotation in enumerate(annotations):
            ann_path = f"{path}.annotations[{ann_index}]"
            if not isinstance(annotation, Mapping) or set(annotation) != {"domain", "category", "evidence_nature"}:
                raise InputValidationError(f"{ann_path}: anotação inválida.")
            if annotation["domain"] not in _DET_VISUAL_DOMAINS:
                raise InputValidationError(f"{ann_path}.domain: valor inválido.")
            if not isinstance(annotation["category"], str) or not annotation["category"].strip():
                raise InputValidationError(f"{ann_path}.category: texto obrigatório.")
            if len(annotation["category"]) > 160:
                raise InputValidationError(f"{ann_path}.category excede 160 caracteres.")
            enforce_text_sanitization(annotation["category"], f"{ann_path}.category")
            if annotation["evidence_nature"] != "OBSERVADO":
                raise InputValidationError(f"{ann_path}.evidence_nature deve ser OBSERVADO.")
    _unique(visual_ids, "case.visual_evidence.visual_id")
    _unique(visual_hashes, "case.visual_evidence.file_sha256")

    urgency_ids: list[str] = []
    urgency_observations = _array(
        payload["urgency_observations"], "case.urgency_observations", max_items=100
    )
    for index, observation in enumerate(urgency_observations):
        path = f"case.urgency_observations[{index}]"
        if not isinstance(observation, Mapping):
            raise InputValidationError(f"{path}: objeto esperado.")
        allowed = {"observation_id", "domain", "availability", "operational_significance", "evidence"}
        _require_keys(observation, allowed, path)
        _reject_extra_keys(observation, allowed, path)
        urgency_ids.append(_identifier(observation["observation_id"], f"{path}.observation_id"))
        if observation["domain"] not in _URGENCY_DOMAINS or observation["availability"] not in _AVAILABILITY:
            raise InputValidationError(f"{path}: domínio ou disponibilidade inválidos.")
        if observation["operational_significance"] not in {"DIRETA_A_VIDA", "AUMENTA_VULNERABILIDADE", "CONTEXTUAL", "NAO_AVALIADA"}:
            raise InputValidationError(f"{path}.operational_significance: valor inválido.")
        _validate_evidence(observation["evidence"], f"{path}.evidence")
    _unique(urgency_ids, "case.urgency_observations")

    evidence_registry: dict[str, tuple[str, Mapping[str, Any]]] = {}
    evidence_entries: list[tuple[str, Mapping[str, Any]]] = [
        ("case.planning_point.evidence", point["evidence"]),
    ]
    evidence_entries.extend(
        (f"case.search_context.environment_observations[{index}].evidence", item["evidence"])
        for index, item in enumerate(environment_observations)
    )
    evidence_entries.extend(
        (f"case.profile_facts[{index}].evidence", item["evidence"])
        for index, item in enumerate(profile_facts)
    )
    evidence_entries.extend(
        (f"case.urgency_observations[{index}].evidence", item["evidence"])
        for index, item in enumerate(urgency_observations)
    )
    for evidence_path, evidence_value in evidence_entries:
        evidence_id = evidence_value["evidence_id"]
        fingerprint = canonical_sha256(evidence_value)
        if evidence_id in evidence_registry and evidence_registry[evidence_id][0] != fingerprint:
            raise InputValidationError(
                f"{evidence_path}: evidence_id repetido com conteúdo divergente: {evidence_id}"
            )
        evidence_registry[evidence_id] = (fingerprint, evidence_value)

    # Conserva o domínio do registro que originou a evidência. O identificador
    # e o hash comprovam identidade/integridade, mas não tornam uma evidência
    # semanticamente adequada a qualquer dimensão DET.
    evidence_det_dimensions: dict[str, set[str]] = {}
    evidence_det_domains: dict[str, set[str]] = {}
    point_evidence_id = point["evidence"]["evidence_id"]
    evidence_det_dimensions.setdefault(point_evidence_id, set()).add(
        "ATUALIDADE_QUALIDADE"
    )
    evidence_det_domains.setdefault(point_evidence_id, set()).add(
        "PONTO_PLANEJAMENTO"
    )
    for observation in environment_observations:
        evidence_id = observation["evidence"]["evidence_id"]
        domain = observation["domain"]
        evidence_det_dimensions.setdefault(evidence_id, set()).update(
            _DET_ENVIRONMENT_DOMAIN_TO_DIMENSIONS.get(domain, set())
        )
        evidence_det_domains.setdefault(evidence_id, set()).add(domain)

    visual_by_id = {item["visual_id"]: item for item in visual_evidence}

    det_keys: list[str] = []
    det_assessments = _array(
        payload["detectability_assessments"],
        "case.detectability_assessments",
        max_items=1000,
    )
    for index, assessment in enumerate(det_assessments):
        path = f"case.detectability_assessments[{index}]"
        if not isinstance(assessment, Mapping):
            raise InputValidationError(f"{path}: objeto esperado.")
        allowed = {"sector_id", "modality", "assessed_at", "dimensions"}
        _require_keys(assessment, allowed, path)
        _reject_extra_keys(assessment, allowed, path)
        sector = _identifier(assessment["sector_id"], f"{path}.sector_id")
        modality = assessment["modality"]
        if modality not in {"BUSCA_TERRESTRE", "OBSERVACAO_AEREA_RGB", "CAMERA_TERMICA", "BUSCA_FLUVIAL"}:
            raise InputValidationError(f"{path}.modality: valor inválido.")
        det_keys.append(f"{sector}::{modality}")
        det_assessed_at = _datetime(assessment["assessed_at"], f"{path}.assessed_at")
        if det_assessed_at > assessment_at:
            raise InputValidationError(f"{path}.assessed_at posterior à avaliação congelada do caso.")
        dimension_names: list[str] = []
        dimensions = _array(assessment["dimensions"], f"{path}.dimensions", max_items=5)
        for dim_index, dimension in enumerate(dimensions):
            dim_path = f"{path}.dimensions[{dim_index}]"
            if not isinstance(dimension, Mapping) or set(dimension) != {"dimension", "category", "source_type", "evidence_id"}:
                raise InputValidationError(f"{dim_path}: dimensão inválida.")
            if dimension["dimension"] not in _DET_DIMENSIONS or dimension["category"] not in _DET_CATEGORIES:
                raise InputValidationError(f"{dim_path}: dimensão ou categoria inválida.")
            if dimension["source_type"] not in {"CAMPO", "FOTO_SOLO", "IMAGEM_DRONE", "CAMADA_PUBLICA", "REGISTRO_OPERACIONAL", "NAO_DISPONIVEL"}:
                raise InputValidationError(f"{dim_path}.source_type: valor inválido.")
            reference_id = _identifier(dimension["evidence_id"], f"{dim_path}.evidence_id")
            if reference_id not in evidence_registry and reference_id not in visual_by_id:
                raise InputValidationError(f"{dim_path}.evidence_id: referência inexistente.")
            source_type = dimension["source_type"]
            if source_type in {"FOTO_SOLO", "IMAGEM_DRONE"}:
                visual = visual_by_id.get(reference_id)
                if visual is None:
                    raise InputValidationError(f"{dim_path}: fonte visual exige referência a visual_id.")
                if source_type == "FOTO_SOLO" and visual["platform"] != "SOLO":
                    raise InputValidationError(f"{dim_path}: FOTO_SOLO exige imagem de plataforma SOLO.")
                if source_type == "IMAGEM_DRONE" and not visual["platform"].startswith("DRONE_"):
                    raise InputValidationError(f"{dim_path}: IMAGEM_DRONE exige plataforma de drone.")
                if not visual["authorized_for_context"]:
                    raise InputValidationError(f"{dim_path}: imagem não autorizada não pode sustentar DET.")
                if not visual["annotations"]:
                    raise InputValidationError(f"{dim_path}: imagem sem anotação humana não pode sustentar DET.")
                compatible_annotations = [
                    annotation
                    for annotation in visual["annotations"]
                    if dimension["dimension"]
                    in _DET_VISUAL_DOMAIN_TO_DIMENSIONS.get(annotation["domain"], set())
                ]
                if not compatible_annotations:
                    annotated_domains = sorted({
                        annotation["domain"] for annotation in visual["annotations"]
                    })
                    raise InputValidationError(
                        f"{dim_path}: nenhuma anotação visual compatível com "
                        f"{dimension['dimension']}; domínios anotados: {annotated_domains}."
                    )
                capture_at = _datetime(
                    visual["capture_at"], f"{dim_path}.capture_at", nullable=True
                )
                if capture_at is not None and capture_at > det_assessed_at:
                    raise InputValidationError(f"{dim_path}: imagem capturada após a avaliação DET.")
                if modality == "OBSERVACAO_AEREA_RGB" and visual["platform"] != "DRONE_RGB":
                    raise InputValidationError(f"{dim_path}: observação aérea RGB exige DRONE_RGB.")
                if modality == "CAMERA_TERMICA" and visual["platform"] != "DRONE_TERMICO":
                    raise InputValidationError(f"{dim_path}: câmera térmica exige DRONE_TERMICO.")
            elif source_type == "CAMADA_PUBLICA":
                evidence_record = evidence_registry.get(reference_id)
                if evidence_record is None or evidence_record[1]["source_type"] != "CAMADA_PUBLICA":
                    raise InputValidationError(f"{dim_path}: CAMADA_PUBLICA exige evidência dessa fonte.")
                if dimension["category"] in {"FAVORAVEL_OBSERVADO", "RESTRITO_OBSERVADO"}:
                    raise InputValidationError(
                        f"{dim_path}: camada pública só pode registrar potencial, indeterminação ou contradição."
                    )
                eligibility = _evidence_eligibility(evidence_record[1], det_assessed_at)
                if eligibility != "ELEGIVEL":
                    raise InputValidationError(f"{dim_path}: camada pública não elegível: {eligibility}.")
                if dimension["dimension"] not in evidence_det_dimensions.get(reference_id, set()):
                    domains = sorted(evidence_det_domains.get(reference_id, set()))
                    raise InputValidationError(
                        f"{dim_path}: domínio da camada pública incompatível com "
                        f"{dimension['dimension']}; domínios: {domains}."
                    )
            elif source_type in {"CAMPO", "REGISTRO_OPERACIONAL"}:
                evidence_record = evidence_registry.get(reference_id)
                if evidence_record is None:
                    raise InputValidationError(f"{dim_path}: fonte exige evidence_id registrado.")
                evidence_value = evidence_record[1]
                eligibility = _evidence_eligibility(evidence_value, det_assessed_at)
                if eligibility != "ELEGIVEL" or evidence_value["nature"] not in {"CONFIRMADO", "OBSERVADO"}:
                    raise InputValidationError(f"{dim_path}: evidência de campo/registro não elegível.")
                if source_type == "CAMPO" and evidence_value["source_type"] not in {"OPERADOR", "SENSOR"}:
                    raise InputValidationError(f"{dim_path}: tipo de evidência de campo incompatível.")
                if (
                    source_type == "REGISTRO_OPERACIONAL"
                    and evidence_value["source_type"] not in {"REGISTRO", "DOCUMENTO_OPERACIONAL", "OPERADOR", "SENSOR"}
                ):
                    raise InputValidationError(f"{dim_path}: tipo de registro operacional incompatível.")
                if dimension["dimension"] not in evidence_det_dimensions.get(reference_id, set()):
                    domains = sorted(evidence_det_domains.get(reference_id, set()))
                    raise InputValidationError(
                        f"{dim_path}: domínio da evidência incompatível com "
                        f"{dimension['dimension']}; domínios: {domains}."
                    )
            elif source_type == "NAO_DISPONIVEL" and dimension["category"] != "INDETERMINADO":
                raise InputValidationError(f"{dim_path}: fonte indisponível exige categoria INDETERMINADO.")
            dimension_names.append(dimension["dimension"])
        _unique(dimension_names, f"{path}.dimensions")
    _unique(det_keys, "case.detectability_assessments")

    artifacts = payload["source_artifacts"]
    artifact_keys = {
        "profile_v2_compiled_sha256", "territorial_manifest_sha256",
        "spatial_review_manifest_sha256", "visual_manifest_sha256", "loc_result_sha256",
    }
    if not isinstance(artifacts, Mapping):
        raise InputValidationError("case.source_artifacts: objeto esperado.")
    _require_keys(artifacts, artifact_keys, "case.source_artifacts")
    _reject_extra_keys(artifacts, artifact_keys, "case.source_artifacts")
    for key in artifact_keys:
        _sha_or_none(artifacts[key], f"case.source_artifacts.{key}")
    search_event_hashes = _array(payload["search_event_hashes"], "case.search_event_hashes", max_items=1000)
    event_hashes: list[str] = []
    for index, value in enumerate(search_event_hashes):
        parsed_hash = _sha_or_none(value, f"case.search_event_hashes[{index}]")
        if parsed_hash is None:
            raise InputValidationError(f"case.search_event_hashes[{index}]: SHA-256 obrigatório.")
        event_hashes.append(parsed_hash)
    _unique(event_hashes, "case.search_event_hashes")

    if payload["record_status"] == "CONGELADO":
        _validate_freeze(payload["freeze_metadata"], "case.freeze_metadata", CASE_FREEZE_PROJECTION_ID)
        calculated = calculate_case_freeze_sha256(payload)
        if not hmac.compare_digest(payload["freeze_metadata"]["payload_sha256"], calculated):
            raise InputValidationError("case.freeze_metadata.payload_sha256 não confere.")
        frozen_at = _datetime(payload["freeze_metadata"]["frozen_at"], "case.freeze_metadata.frozen_at")
        if frozen_at < assessment_at:
            raise InputValidationError("case.freeze_metadata.frozen_at anterior à avaliação.")
    elif payload["freeze_metadata"] is not None:
        raise InputValidationError("case.freeze_metadata deve ser null em rascunho.")


def prepare_frozen_case(
    payload: Mapping[str, Any],
    frozen_at: str,
    parent_case: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    draft = deepcopy(dict(payload))
    if draft.get("record_status") != "RASCUNHO" or draft.get("freeze_metadata") is not None:
        raise InputValidationError(
            "freeze-case aceita somente rascunho sem metadados; revisão congelada exige novo artefato e case_revision incrementada."
        )
    validate_case(draft)
    if draft["case_revision"] == 1:
        if parent_case is not None:
            raise InputValidationError("A primeira revisão não pode receber parent_case.")
    else:
        if parent_case is None:
            raise InputValidationError("Revisão posterior exige o artefato parent_case para conferência.")
        validate_case(parent_case)
        if parent_case["record_status"] != "CONGELADO":
            raise InputValidationError("parent_case deve estar congelado.")
        if parent_case["scenario_id"] != draft["scenario_id"]:
            raise InputValidationError("parent_case pertence a outro cenário.")
        if parent_case["case_revision"] + 1 != draft["case_revision"]:
            raise InputValidationError("case_revision não sucede imediatamente o parent_case.")
        parent_hash = parent_case["freeze_metadata"]["payload_sha256"]
        if not hmac.compare_digest(draft["parent_payload_sha256"], parent_hash):
            raise InputValidationError("parent_payload_sha256 não confere com parent_case.")
        if _datetime(parent_case["freeze_metadata"]["frozen_at"], "parent_case.frozen_at") > _datetime(
            draft["created_at"], "case.created_at"
        ):
            raise InputValidationError("case.created_at anterior ao congelamento da revisão pai.")
    _datetime(frozen_at, "frozen_at")
    frozen = deepcopy(draft)
    frozen["record_status"] = "CONGELADO"
    frozen["freeze_metadata"] = {
        "frozen_at": frozen_at,
        "projection_id": CASE_FREEZE_PROJECTION_ID,
        "payload_sha256": "0" * 64,
    }
    frozen["freeze_metadata"]["payload_sha256"] = calculate_case_freeze_sha256(frozen)
    validate_case(frozen)
    return frozen


def _is_evidence_current(evidence: Mapping[str, Any], assessment_at: datetime) -> bool:
    return _evidence_eligibility(evidence, assessment_at) == "ELEGIVEL"


def _evidence_provenance_status(evidence: Mapping[str, Any], assessment_at: datetime) -> str:
    if not evidence["authorized_for_model"]:
        return "NAO_AUTORIZADA"
    if not isinstance(evidence["source_code"], str) or not evidence["source_code"].strip():
        return "FONTE_NAO_IDENTIFICADA"
    observed_at = _datetime(evidence["observed_at"], "evidence.observed_at", nullable=True)
    if observed_at is None:
        return "HORARIO_NAO_DISPONIVEL"
    if observed_at > assessment_at:
        return "EVIDENCIA_FUTURA"
    valid_until = _datetime(evidence["valid_until"], "evidence.valid_until", nullable=True)
    if valid_until is not None and valid_until < assessment_at:
        return "EXPIRADA"
    return "ELEGIVEL"


def _evidence_eligibility(evidence: Mapping[str, Any], assessment_at: datetime) -> str:
    provenance = _evidence_provenance_status(evidence, assessment_at)
    if provenance != "ELEGIVEL":
        return provenance
    if evidence["nature"] not in {"CONFIRMADO", "OBSERVADO", "RELATADO"}:
        return "NATUREZA_NAO_SUFICIENTE"
    if evidence["confidence"] == "NAO_AVALIADA":
        return "CONFIANCA_NAO_AVALIADA"
    return "ELEGIVEL"


def validate_rules_catalog(rules: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    expected_top = {"catalog_version", "status", "description", "rules", "critical_domains", "guards"}
    _require_keys(rules, expected_top, "catalog")
    _reject_extra_keys(rules, expected_top, "catalog")
    if rules["catalog_version"] != "URG-RULES-v1.0" or rules["status"] != "CANDIDATO_PROSPECTIVO":
        raise InputValidationError("Catálogo URG inesperado.")
    if not isinstance(rules["description"], str) or not rules["description"].strip():
        raise InputValidationError("Catálogo URG sem descrição.")
    critical = _array(rules["critical_domains"], "catalog.critical_domains")
    if len(critical) != len(set(critical)) or set(critical) != set(_CRITICAL_URGENCY_DOMAINS):
        raise InputValidationError("Catálogo URG: conjunto de domínios críticos alterado.")
    expected_guards = {
        "unknown_never_means_low_urgency": True,
        "conflict_forces_abstention": True,
        "duplicate_evidence_does_not_accumulate": True,
        "expired_evidence_does_not_trigger": True,
        "urgency_never_changes_loc": True,
        "ground_truth_prohibited": True,
    }
    if rules["guards"] != expected_guards:
        raise InputValidationError("Guardas do catálogo URG ausentes ou alteradas.")
    rule_entries = _array(rules["rules"], "catalog.rules")
    rules_by_id: dict[str, Mapping[str, Any]] = {}
    for index, rule in enumerate(rule_entries):
        path = f"catalog.rules[{index}]"
        if not isinstance(rule, Mapping) or not isinstance(rule.get("rule_id"), str):
            raise InputValidationError(f"{path}: regra inválida.")
        rule_id = rule["rule_id"]
        if rule_id in rules_by_id:
            raise InputValidationError(f"Catálogo URG: rule_id duplicado: {rule_id}")
        expected = _RULE_SEMANTICS.get(rule_id)
        if expected is None:
            raise InputValidationError(f"Catálogo URG: regra não reconhecida: {rule_id}")
        allowed_keys = {"rule_id", "status", "justification", *expected.keys()}
        _require_keys(rule, allowed_keys, path)
        _reject_extra_keys(rule, allowed_keys, path)
        if rule["status"] not in {"ATIVA", "EXPERIMENTAL", "DESABILITADA"}:
            raise InputValidationError(f"{path}.status: valor inválido.")
        if not isinstance(rule["justification"], str) or not rule["justification"].strip():
            raise InputValidationError(f"{path}.justification: texto obrigatório.")
        for key, expected_value in expected.items():
            if rule[key] != expected_value:
                raise InputValidationError(f"Catálogo URG: semântica alterada em {rule_id}.{key}.")
        rules_by_id[rule_id] = rule
    if set(rules_by_id) != set(_RULE_SEMANTICS):
        raise InputValidationError("Catálogo URG: conjunto de regras obrigatório alterado.")
    return rules_by_id


def assess_urgency(payload: Mapping[str, Any], rules: Mapping[str, Any]) -> dict[str, Any]:
    assessment_at = _datetime(payload["search_context"]["assessment_at"], "assessment_at")
    observations = list(payload["urgency_observations"])
    rules_by_id = validate_rules_catalog(rules)
    critical_domains = set(_CRITICAL_URGENCY_DOMAINS)
    eligible: list[Mapping[str, Any]] = []
    expired: list[str] = []
    ineligible: list[dict[str, str]] = []
    for observation in observations:
        evidence = observation["evidence"]
        eligibility = _evidence_eligibility(evidence, assessment_at)
        if eligibility == "EXPIRADA":
            expired.append(observation["observation_id"])
        elif eligibility == "ELEGIVEL":
            eligible.append(observation)
        else:
            ineligible.append({
                "observation_id": observation["observation_id"],
                "reason": eligibility,
            })

    by_domain: dict[str, list[Mapping[str, Any]]] = {}
    by_evidence: dict[str, list[Mapping[str, Any]]] = {}
    for observation in eligible:
        by_domain.setdefault(observation["domain"], []).append(observation)
        by_evidence.setdefault(observation["evidence"]["evidence_id"], []).append(observation)
    conflict_ids: set[str] = {
        obs["observation_id"] for obs in eligible if obs["availability"] == "CONTRADITORIO"
    }
    conflicting_domains: set[str] = set()
    for domain, domain_items in by_domain.items():
        availabilities = {item["availability"] for item in domain_items}
        if "CONTRADITORIO" in availabilities or {"PRESENTE", "AUSENTE"}.issubset(availabilities):
            conflicting_domains.add(domain)
            conflict_ids.update(item["observation_id"] for item in domain_items)

    # Uma condição de risco estruturada e sustentada por evidência elegível não
    # pode coexistir silenciosamente com URG ausente ou subestimada. Não há
    # interpretação clínica de prosa: a guarda atua apenas sobre o codebook
    # explícito acima e encaminha a divergência à revisão humana.
    profile_consistency_conflicts: list[dict[str, Any]] = []
    for fact in payload["profile_facts"]:
        raw_value = fact["value"]
        if fact["availability"] != "PRESENTE" or not isinstance(raw_value, str):
            continue
        value_code = re.sub(r"[^A-Z0-9]+", "_", raw_value.strip().upper()).strip("_")
        expected_significance = _PROFILE_URGENCY_RISK_CODES.get((fact["domain"], value_code))
        if expected_significance is None:
            continue
        if _evidence_eligibility(fact["evidence"], assessment_at) != "ELEGIVEL":
            continue
        domain_items = by_domain.get(fact["domain"], [])
        compatible = any(
            item["availability"] == "PRESENTE"
            and _URGENCY_SIGNIFICANCE_RANK[item["operational_significance"]]
            >= _URGENCY_SIGNIFICANCE_RANK[expected_significance]
            for item in domain_items
        )
        if compatible:
            continue
        affected_ids = sorted(item["observation_id"] for item in domain_items)
        profile_consistency_conflicts.append({
            "fact_id": fact["fact_id"],
            "domain": fact["domain"],
            "value_code": value_code,
            "expected_minimum_significance": expected_significance,
            "urgency_observation_ids": affected_ids,
            "reason": "FATO_ESTRUTURADO_DE_RISCO_NAO_RECONCILIADO_COM_URG",
        })
        conflicting_domains.add(fact["domain"])
        conflict_ids.update(affected_ids)
    duplicate_evidence_groups: list[dict[str, Any]] = []
    for evidence_id, evidence_items in sorted(by_evidence.items()):
        if len(evidence_items) < 2:
            continue
        semantics = {
            (item["domain"], item["availability"], item["operational_significance"])
            for item in evidence_items
        }
        observation_ids = sorted(item["observation_id"] for item in evidence_items)
        duplicate_evidence_groups.append({
            "evidence_id": evidence_id,
            "observation_ids": observation_ids,
            "semantics_identical": len(semantics) == 1,
        })
        if len(semantics) > 1:
            conflict_ids.update(observation_ids)
            conflicting_domains.update(item["domain"] for item in evidence_items)
    conflicts = sorted(conflict_ids)
    unassessed_significance_ids = sorted(
        item["observation_id"]
        for item in eligible
        if item["domain"] in critical_domains
        and item["operational_significance"] == "NAO_AVALIADA"
    )
    unassessed_significance_domains = {
        item["domain"]
        for item in eligible
        if item["domain"] in critical_domains
        and item["operational_significance"] == "NAO_AVALIADA"
    }
    resolved_domains = {
        domain
        for domain, domain_items in by_domain.items()
        if domain not in conflicting_domains
        and domain not in unassessed_significance_domains
        and {item["availability"] for item in domain_items} & {"PRESENTE", "AUSENTE"}
    }
    missing_critical = sorted(critical_domains - resolved_domains)
    direct = [
        obs for obs in eligible
        if obs["availability"] == "PRESENTE" and obs["operational_significance"] == "DIRETA_A_VIDA"
    ]
    vulnerable = [
        obs for obs in eligible
        if obs["availability"] == "PRESENTE" and obs["operational_significance"] == "AUMENTA_VULNERABILIDADE"
    ]
    direct_active = rules_by_id.get("URG-R01-RISCO-DIRETO", {}).get("status") == "ATIVA"
    vulnerability_active = rules_by_id.get("URG-R02-VULNERABILIDADE", {}).get("status") == "ATIVA"
    baseline_active = rules_by_id.get("URG-R03-COBERTURA-MINIMA", {}).get("status") == "ATIVA"
    unhandled_priority = sorted(
        obs["observation_id"]
        for obs in (direct if not direct_active else []) + (vulnerable if not vulnerability_active else [])
    )
    if conflicts or profile_consistency_conflicts:
        status = "INDETERMINADA"
        triggered: list[str] = []
        reason = "Há informação contraditória ou perfil de risco não reconciliado; revisão humana obrigatória."
    elif unassessed_significance_ids:
        status = "INDETERMINADA"
        triggered = []
        reason = "Existe domínio crítico com significado operacional não avaliado."
    elif unhandled_priority:
        status = "INDETERMINADA"
        triggered = []
        reason = "Existe fator prioritário cuja regra não está ativa; o módulo deve se abster."
    elif direct and direct_active:
        status = "REVISAO_IMEDIATA"
        triggered = ["URG-R01-RISCO-DIRETO"]
        reason = "Existe fator autorizado, atual e explicitamente marcado como risco direto à vida."
    elif vulnerable and vulnerability_active:
        status = "REVISAO_PRIORITARIA"
        triggered = ["URG-R02-VULNERABILIDADE"]
        reason = "Existe fator autorizado, atual e explicitamente marcado como aumento de vulnerabilidade."
    elif missing_critical:
        status = "INDETERMINADA"
        triggered = []
        reason = "A cobertura mínima de informação não foi atingida; ausência de dado não equivale a baixa urgência."
    elif baseline_active:
        status = "REVISAO_PADRAO"
        triggered = ["URG-R03-COBERTURA-MINIMA"]
        reason = "Domínios críticos resolvidos, sem regra de maior precedência acionada."
    else:
        status = "INDETERMINADA"
        triggered = []
        reason = "A regra de cobertura mínima não está ativa; o módulo deve se abster."
    return {
        "status": status,
        "meaning": "PRIORIDADE_DE_REVISAO_OPERACIONAL_NAO_CLINICA",
        "triggered_rules": triggered,
        "observed_factor_ids": sorted(obs["observation_id"] for obs in eligible),
        "missing_critical_domains": missing_critical,
        "conflict_observation_ids": conflicts,
        "conflict_domains": sorted(conflicting_domains),
        "profile_consistency_conflicts": profile_consistency_conflicts,
        "unassessed_significance_observation_ids": unassessed_significance_ids,
        "duplicate_evidence_groups": duplicate_evidence_groups,
        "expired_observation_ids": sorted(expired),
        "ineligible_observations": sorted(ineligible, key=lambda item: item["observation_id"]),
        "unhandled_priority_observation_ids": unhandled_priority,
        "reason": reason,
        "affects_loc": False,
    }


def _visual_supports_modality(visual: Mapping[str, Any], modality: str) -> bool:
    """Restringe uma observação visual à modalidade que ela documenta."""
    return modality in {
        "DRONE_RGB": {"OBSERVACAO_AEREA_RGB"},
        "DRONE_TERMICO": {"CAMERA_TERMICA"},
        "SOLO": {"BUSCA_TERRESTRE"},
        "OUTRA": set(),
    }.get(visual["platform"], set())


def assess_detectability(
    payload: Mapping[str, Any],
    verified_binding_ids: set[str] | None = None,
    valid_loc_sector_ids: set[str] | None = None,
    visual_sector_pairs: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    verified_binding_ids = verified_binding_ids or set()
    visual_sector_pairs = visual_sector_pairs or {}
    if not isinstance(visual_sector_pairs, Mapping) or any(
        not isinstance(pair, str)
        or quality not in {"APROXIMADO_METADADOS", "VERIFICADO_CALIBRADO"}
        for pair, quality in visual_sector_pairs.items()
    ):
        raise InputValidationError("Vínculos visuais verificados possuem estrutura inválida.")
    visual_by_id = {
        item["visual_id"]: item for item in payload["visual_evidence"]
    }
    rows: list[dict[str, Any]] = []
    for assessment in sorted(
        payload["detectability_assessments"], key=lambda item: (item["sector_id"], item["modality"])
    ):
        by_dimension = {item["dimension"]: item for item in assessment["dimensions"]}
        missing = sorted(_DET_DIMENSIONS - set(by_dimension))
        categories = {item["category"] for item in assessment["dimensions"]}
        public_only = bool(assessment["dimensions"]) and all(
            item["source_type"] == "CAMADA_PUBLICA" for item in assessment["dimensions"]
        )
        unverified_visual_ids = sorted({
            item["evidence_id"]
            for item in assessment["dimensions"]
            if item["source_type"] in {"FOTO_SOLO", "IMAGEM_DRONE"}
            and f"visual:{item['evidence_id']}" not in verified_binding_ids
        })
        temporally_unqualified_visual_ids = sorted({
            item["evidence_id"]
            for item in assessment["dimensions"]
            if item["source_type"] in {"FOTO_SOLO", "IMAGEM_DRONE"}
            and item["evidence_id"] in visual_by_id
            and (
                visual_by_id[item["evidence_id"]]["capture_at"] is None
                or visual_by_id[item["evidence_id"]]["capture_time_precision"]
                == "NAO_DISPONIVEL"
                or visual_by_id[item["evidence_id"]]["capture_time_source"]
                == "NAO_DISPONIVEL"
            )
        })
        spatially_unqualified_evidence_ids: set[str] = set()
        modality_unqualified_visual_ids: set[str] = set()
        binding_quality_by_evidence_id: dict[str, str] = {}
        for item in assessment["dimensions"]:
            evidence_id = item["evidence_id"]
            if item["source_type"] in {"CAMPO", "REGISTRO_OPERACIONAL"}:
                spatially_unqualified_evidence_ids.add(evidence_id)
                continue
            if item["source_type"] not in {"FOTO_SOLO", "IMAGEM_DRONE"}:
                continue
            visual = visual_by_id.get(evidence_id)
            pair_key = f"{evidence_id}::{assessment['sector_id']}"
            pair_quality = visual_sector_pairs.get(pair_key)
            if pair_quality is None:
                spatially_unqualified_evidence_ids.add(evidence_id)
            elif visual is None or not _visual_supports_modality(
                visual, assessment["modality"]
            ):
                spatially_unqualified_evidence_ids.add(evidence_id)
                modality_unqualified_visual_ids.add(evidence_id)
            else:
                binding_quality_by_evidence_id[evidence_id] = pair_quality
        spatially_unqualified_evidence_ids_sorted = sorted(
            spatially_unqualified_evidence_ids
        )
        approximate_spatial_evidence_ids = sorted(
            evidence_id
            for evidence_id, quality in binding_quality_by_evidence_id.items()
            if quality == "APROXIMADO_METADADOS"
        )
        calibrated_spatial_evidence_ids = sorted(
            evidence_id
            for evidence_id, quality in binding_quality_by_evidence_id.items()
            if quality == "VERIFICADO_CALIBRADO"
        )
        unsupported_visual_claims: list[dict[str, Any]] = []
        for dimension in assessment["dimensions"]:
            if dimension["source_type"] not in {"FOTO_SOLO", "IMAGEM_DRONE"}:
                continue
            visual = visual_by_id.get(dimension["evidence_id"])
            if visual is None:
                continue
            compatible_annotations = [
                annotation
                for annotation in visual["annotations"]
                if dimension["dimension"]
                in _DET_VISUAL_DOMAIN_TO_DIMENSIONS.get(annotation["domain"], set())
            ]
            polarities = {
                _DET_VISUAL_CATEGORY_POLARITY.get((
                    annotation["domain"],
                    _normalized_key(annotation["category"]).upper(),
                ), "NAO_ESTRUTURADA")
                for annotation in compatible_annotations
            }
            declared_category = dimension["category"]
            coherent = bool(
                declared_category == "FAVORAVEL_OBSERVADO"
                and polarities == {"FAVORAVEL"}
                or declared_category == "RESTRITO_OBSERVADO"
                and "RESTRITO" in polarities
                or declared_category in {
                    "POTENCIAL_CAMADA_PUBLICA", "INDETERMINADO", "CONTRADITORIO"
                }
            )
            if not coherent:
                unsupported_visual_claims.append({
                    "dimension": dimension["dimension"],
                    "evidence_id": dimension["evidence_id"],
                    "declared_category": declared_category,
                    "annotation_polarities": sorted(polarities),
                })
        if valid_loc_sector_ids is None:
            loc_sector_link = "LOC_CONTRACT_NOT_VALIDATED"
        elif assessment["sector_id"] not in valid_loc_sector_ids:
            loc_sector_link = "SECTOR_NOT_IN_VALIDATED_LOC_RESULT"
        else:
            loc_sector_link = "VALIDATED"
        if not assessment["dimensions"]:
            status = "NAO_AVALIADO"
            reason = "Nenhuma dimensão foi avaliada."
        elif loc_sector_link != "VALIDATED":
            status = "REVISAR"
            reason = "O setor DET não está vinculado a um resultado LOC semanticamente validado."
        elif "CONTRADITORIO" in categories:
            status = "REVISAR"
            reason = "Há evidência contraditória."
        elif (
            missing
            or "INDETERMINADO" in categories
            or "POTENCIAL_CAMADA_PUBLICA" in categories
            or public_only
            or unverified_visual_ids
            or temporally_unqualified_visual_ids
            or unsupported_visual_claims
            or spatially_unqualified_evidence_ids_sorted
        ):
            status = "REVISAR"
            reason = (
                "Avaliação incompleta, indeterminada, não verificada, semanticamente "
                "incompatível, sem vínculo espacial autenticado ao setor ou apoiada em "
                "potencial de camada pública."
            )
        elif "RESTRITO_OBSERVADO" in categories or approximate_spatial_evidence_ids:
            status = "APTO_COM_RESTRICOES"
            reason = (
                "Ao menos uma dimensão apresenta restrição observada."
                if "RESTRITO_OBSERVADO" in categories
                else (
                    "As dimensões são favoráveis, mas o vínculo imagem--setor "
                    "deriva de footprint aproximado e exige supervisão humana."
                )
            )
        else:
            status = "APTO_A_PLANEJAMENTO"
            reason = "Todas as dimensões requeridas possuem avaliação observada favorável."
        rows.append({
            "sector_id": assessment["sector_id"],
            "modality": assessment["modality"],
            "assessed_at": assessment["assessed_at"],
            "status": status,
            "dimensions": [by_dimension[key] for key in sorted(by_dimension)],
            "missing_dimensions": missing,
            "unverified_visual_ids": unverified_visual_ids,
            "temporally_unqualified_visual_ids": temporally_unqualified_visual_ids,
            "spatially_unqualified_evidence_ids": spatially_unqualified_evidence_ids_sorted,
            "modality_unqualified_visual_ids": sorted(modality_unqualified_visual_ids),
            "spatial_binding_quality_by_evidence_id": dict(
                sorted(binding_quality_by_evidence_id.items())
            ),
            "approximate_spatial_evidence_ids": approximate_spatial_evidence_ids,
            "calibrated_spatial_evidence_ids": calibrated_spatial_evidence_ids,
            "unsupported_visual_claims": unsupported_visual_claims,
            "loc_sector_link": loc_sector_link,
            "reason": reason,
            "affects_loc": False,
        })
    return {
        "unit": "SETOR_X_MODALIDADE_X_INSTANTE",
        "per_sector_modality": rows,
        "aggregate_score": None,
        "affects_loc": False,
    }


def verify_artifact_bindings(
    payload: Mapping[str, Any], artifact_map: Mapping[str, Any], artifact_root: Path
) -> dict[str, Any]:
    """Confere os hashes declarados contra arquivos externos ao envelope cego."""
    enforce_ground_truth_firewall(artifact_map, "$artifact_map")
    expected: dict[str, str] = {
        key: value
        for key, value in payload["source_artifacts"].items()
        if value is not None
    }
    if payload["case_revision"] > 1:
        expected["parent_case"] = payload["parent_payload_sha256"]
    expected.update({
        f"visual:{visual['visual_id']}": visual["file_sha256"]
        for visual in payload["visual_evidence"]
    })
    expected.update({f"event:{event_hash}": event_hash for event_hash in payload["search_event_hashes"]})
    if set(artifact_map) != set(expected):
        missing = sorted(set(expected) - set(artifact_map))
        extras = sorted(set(artifact_map) - set(expected))
        raise InputValidationError(
            f"Mapa de artefatos não coincide com as declarações; ausentes={missing}, extras={extras}."
        )
    root_resolved = artifact_root.resolve()
    verified: list[dict[str, Any]] = []
    linked_events_by_hash: dict[str, Mapping[str, Any]] = {}
    visual_by_binding_id = {
        f"visual:{visual['visual_id']}": visual
        for visual in payload["visual_evidence"]
    }
    for binding_id in sorted(expected):
        relative = artifact_map[binding_id]
        if not isinstance(relative, str) or not relative.strip():
            raise InputValidationError(f"artifact_map.{binding_id}: caminho relativo textual esperado.")
        relative_path = Path(relative)
        if relative_path.is_absolute():
            raise InputValidationError(f"artifact_map.{binding_id}: caminho absoluto não permitido.")
        path = (root_resolved / relative_path).resolve()
        try:
            path.relative_to(root_resolved)
        except ValueError as exc:
            raise InputValidationError(f"artifact_map.{binding_id}: caminho sai da raiz autorizada.") from exc
        if not path.is_file():
            raise InputValidationError(f"artifact_map.{binding_id}: arquivo não encontrado.")
        if binding_id == "parent_case":
            linked_parent = _load_json(path)
            if not isinstance(linked_parent, Mapping):
                raise InputValidationError("artifact_map.parent_case: caso-pai JSON inválido.")
            validate_case(linked_parent)
            if (
                linked_parent["record_status"] != "CONGELADO"
                or linked_parent["scenario_id"] != payload["scenario_id"]
                or linked_parent["case_revision"] + 1 != payload["case_revision"]
            ):
                raise InputValidationError("artifact_map.parent_case: revisão-pai incompatível.")
            if _datetime(
                linked_parent["freeze_metadata"]["frozen_at"],
                "parent_case.freeze_metadata.frozen_at",
            ) > _datetime(payload["created_at"], "case.created_at"):
                raise InputValidationError("artifact_map.parent_case: pai congelado após a criação da revisão.")
            calculated = linked_parent["freeze_metadata"]["payload_sha256"]
        elif binding_id.startswith("event:"):
            linked_event = _load_json(path)
            if not isinstance(linked_event, Mapping):
                raise InputValidationError(f"artifact_map.{binding_id}: evento JSON inválido.")
            validate_event(linked_event)
            if linked_event["record_status"] != "CONGELADO" or linked_event["scenario_id"] != payload["scenario_id"]:
                raise InputValidationError(f"artifact_map.{binding_id}: evento incompatível.")
            if _datetime(linked_event["recorded_at"], f"artifact_map.{binding_id}.recorded_at") > _datetime(
                payload["search_context"]["assessment_at"], "case.search_context.assessment_at"
            ):
                raise InputValidationError(f"artifact_map.{binding_id}: evento posterior à avaliação do caso.")
            if _datetime(
                linked_event["freeze_metadata"]["frozen_at"],
                f"artifact_map.{binding_id}.freeze_metadata.frozen_at",
            ) > _datetime(payload["freeze_metadata"]["frozen_at"], "case.freeze_metadata.frozen_at"):
                raise InputValidationError(f"artifact_map.{binding_id}: evento congelado após o caso.")
            calculated = linked_event["freeze_metadata"]["payload_sha256"]
            linked_events_by_hash[calculated] = linked_event
        else:
            calculated = file_sha256(path)
        if not hmac.compare_digest(calculated, expected[binding_id]):
            raise InputValidationError(f"artifact_map.{binding_id}: SHA-256 não confere.")
        content = {
            "content_validation": "NOT_APPLICABLE",
            "loc_sector_ids": [],
            "loc_candidate_ids": [],
        }
        media_validation = "NOT_APPLICABLE"
        if binding_id == "loc_result_sha256":
            content = _inspect_loc_result_artifact(path, payload)
        elif binding_id.startswith("visual:"):
            media_validation = _validate_visual_media_signature(
                path, visual_by_binding_id[binding_id]["media_type"]
            )
        verified.append({
            "binding_id": binding_id,
            "relative_path": relative_path.as_posix(),
            "sha256": calculated,
            "bytes": path.stat().st_size,
            "qualifies_known_location": False,
            "media_validation": media_validation,
            **content,
        })
    event_ids = [event["event_id"] for event in linked_events_by_hash.values()]
    event_sequences = [event["event_sequence"] for event in linked_events_by_hash.values()]
    _unique(event_ids, "artifact_map.events.event_id")
    _unique(event_sequences, "artifact_map.events.event_sequence")

    # Fechar a cadeia até a sequência 1 é indispensável quando um evento pode
    # encerrar LOC. Conferir apenas o predecessor imediato permitiria que uma
    # sequência 3 herdasse um ancestral inexistente ou adulterado.
    chain_cache: dict[str, bool] = {}

    def event_chain_complete(event_hash: str, visiting: set[str] | None = None) -> bool:
        if event_hash in chain_cache:
            return chain_cache[event_hash]
        event = linked_events_by_hash.get(event_hash)
        if event is None:
            return False
        visiting = set() if visiting is None else set(visiting)
        if event_hash in visiting:
            chain_cache[event_hash] = False
            return False
        visiting.add(event_hash)
        if event["event_sequence"] == 1:
            complete = event["previous_event_sha256"] is None
        else:
            previous_hash = event["previous_event_sha256"]
            previous = linked_events_by_hash.get(previous_hash)
            complete = bool(
                previous_hash is not None
                and previous is not None
                and previous["event_sequence"] + 1 == event["event_sequence"]
                and _datetime(previous["recorded_at"], "previous_event.recorded_at")
                <= _datetime(event["started_at"], "linked_event.started_at")
                and event_chain_complete(previous_hash, visiting)
            )
        chain_cache[event_hash] = complete
        return complete

    source_chain_cache: dict[str, bool] = {}

    def source_chain_complete(event_hash: str, visiting: set[str] | None = None) -> bool:
        """Comprova que cada ponto derivado chega a uma fonte primária positiva."""
        if event_hash in source_chain_cache:
            return source_chain_cache[event_hash]
        event = linked_events_by_hash.get(event_hash)
        if event is None:
            return False
        visiting = set() if visiting is None else set(visiting)
        if event_hash in visiting:
            source_chain_cache[event_hash] = False
            return False
        visiting.add(event_hash)
        if event["event_type"] != "NOVO_PONTO_CONHECIDO":
            complete = bool(
                event["source_event_sha256"] is None
                and event["result"] == "POSITIVO"
                and event["authorized_for_model"]
                and event["clue_coordinate"] is not None
                and event_chain_complete(event_hash)
            )
        else:
            source_hash = event["source_event_sha256"]
            source = linked_events_by_hash.get(source_hash)
            complete = bool(
                source_hash is not None
                and source is not None
                and source["event_sequence"] < event["event_sequence"]
                and source["result"] == "POSITIVO"
                and source["authorized_for_model"]
                and source["clue_coordinate"] is not None
                and source["clue_coordinate"] == event["clue_coordinate"]
                and _datetime(source["recorded_at"], "source_event.recorded_at")
                <= _datetime(event["started_at"], "linked_event.started_at")
                and event_chain_complete(event_hash)
                and source_chain_complete(source_hash, visiting)
            )
        source_chain_cache[event_hash] = complete
        return complete

    base_known_location_by_hash: dict[str, bool] = {}
    known_coordinates: set[tuple[float, float]] = set()
    for event_hash, linked_event in linked_events_by_hash.items():
        source_hash = linked_event["source_event_sha256"]
        previous_hash = linked_event["previous_event_sha256"]
        source_event = linked_events_by_hash.get(source_hash)
        previous_event = linked_events_by_hash.get(previous_hash)
        base_qualifies = bool(
            linked_event["event_type"] == "NOVO_PONTO_CONHECIDO"
            and linked_event["result"] == "POSITIVO"
            and linked_event["authorized_for_model"]
            and linked_event["clue_coordinate"] is not None
            and source_event is not None
            and source_event["event_type"] in _KNOWN_LOCATION_SOURCE_EVENT_TYPES
            and source_event["result"] == "POSITIVO"
            and source_event["authorized_for_model"]
            and source_event["clue_coordinate"] is not None
            and source_event["clue_coordinate"] == linked_event["clue_coordinate"]
            and source_event["event_sequence"] < linked_event["event_sequence"]
            and previous_event is not None
            and previous_event["event_sequence"] + 1 == linked_event["event_sequence"]
            and event_chain_complete(event_hash)
            and event_chain_complete(source_hash)
            and source_chain_complete(event_hash)
            and _datetime(previous_event["recorded_at"], "previous_event.recorded_at")
            <= _datetime(linked_event["started_at"], "linked_event.started_at")
            and _datetime(source_event["recorded_at"], "source_event.recorded_at")
            <= _datetime(linked_event["started_at"], "linked_event.started_at")
        )
        base_known_location_by_hash[event_hash] = base_qualifies
        if base_qualifies:
            known_coordinates.add((
                float(linked_event["clue_coordinate"]["latitude"]),
                float(linked_event["clue_coordinate"]["longitude"]),
            ))
    known_location_conflict = len(known_coordinates) > 1

    for binding in verified:
        if not binding["binding_id"].startswith("event:"):
            continue
        linked_event = linked_events_by_hash[binding["sha256"]]
        source_event = linked_events_by_hash.get(linked_event["source_event_sha256"])
        binding["qualifies_known_location"] = bool(
            base_known_location_by_hash[binding["sha256"]]
            and not known_location_conflict
            and linked_event["clue_coordinate"] == {
                "latitude": payload["planning_point"]["latitude"],
                "longitude": payload["planning_point"]["longitude"],
            }
            and payload["planning_point"]["point_role"] in {
                "ULTIMO_PONTO_VISTO", "ULTIMO_PONTO_CONHECIDO"
            }
            and payload["planning_point"]["position_observed_at"] is not None
            and payload["planning_point"]["evidence"]["authorized_for_model"]
            and payload["planning_point"]["evidence"]["nature"] in {"OBSERVADO", "CONFIRMADO"}
            and payload["planning_point"]["evidence"]["source_code"] == linked_event["event_id"]
            and _datetime(source_event["started_at"], "source_event.started_at")
            <= _datetime(
                payload["planning_point"]["position_observed_at"],
                "case.planning_point.position_observed_at",
            )
            <= _datetime(linked_event["recorded_at"], "linked_event.recorded_at")
        )
    return {
        "status": "VERIFIED",
        "artifact_root_not_embedded": True,
        "known_location_conflict": known_location_conflict,
        "bindings": verified,
    }


def _validate_artifact_verification(
    payload: Mapping[str, Any], verification: Mapping[str, Any]
) -> set[str]:
    if set(verification) != {
        "status", "artifact_root_not_embedded", "known_location_conflict", "bindings"
    }:
        raise InputValidationError("Estrutura de verificação de artefatos inválida.")
    if verification["status"] not in {"VERIFIED", "NOT_PERFORMED"}:
        raise InputValidationError("Estado de verificação de artefatos inválido.")
    if verification["artifact_root_not_embedded"] is not True:
        raise InputValidationError("A raiz local de artefatos não pode ser embutida na saída.")
    if not isinstance(verification["known_location_conflict"], bool):
        raise InputValidationError("known_location_conflict deve ser booleano.")
    bindings = _array(verification["bindings"], "artifact_verification.bindings")
    expected: dict[str, str] = {
        key: value for key, value in payload["source_artifacts"].items() if value is not None
    }
    if payload["case_revision"] > 1:
        expected["parent_case"] = payload["parent_payload_sha256"]
    expected.update({
        f"visual:{visual['visual_id']}": visual["file_sha256"]
        for visual in payload["visual_evidence"]
    })
    expected.update({f"event:{event_hash}": event_hash for event_hash in payload["search_event_hashes"]})
    if verification["status"] == "NOT_PERFORMED":
        if bindings:
            raise InputValidationError("Verificação não executada não pode conter bindings.")
        if verification["known_location_conflict"]:
            raise InputValidationError("Conflito de localização não pode existir sem verificação.")
        return set()
    binding_ids: list[str] = []
    for index, binding in enumerate(bindings):
        path = f"artifact_verification.bindings[{index}]"
        if not isinstance(binding, Mapping) or set(binding) != {
            "binding_id", "relative_path", "sha256", "bytes", "qualifies_known_location",
            "content_validation", "loc_sector_ids", "loc_candidate_ids", "media_validation",
        }:
            raise InputValidationError(f"{path}: binding inválido.")
        binding_id = binding["binding_id"]
        if binding_id not in expected:
            raise InputValidationError(f"{path}.binding_id: declaração inexistente.")
        if not isinstance(binding["relative_path"], str) or not binding["relative_path"].strip():
            raise InputValidationError(f"{path}.relative_path: texto obrigatório.")
        if not isinstance(binding["bytes"], int) or isinstance(binding["bytes"], bool) or binding["bytes"] < 0:
            raise InputValidationError(f"{path}.bytes: inteiro não negativo esperado.")
        if not isinstance(binding["qualifies_known_location"], bool):
            raise InputValidationError(f"{path}.qualifies_known_location: booleano esperado.")
        if binding["qualifies_known_location"] and not binding["binding_id"].startswith("event:"):
            raise InputValidationError(f"{path}: somente evento pode qualificar localização conhecida.")
        if binding["media_validation"] not in {"NOT_APPLICABLE", "CONTAINER_STRUCTURE_ONLY"}:
            raise InputValidationError(f"{path}.media_validation: valor inválido.")
        if binding_id.startswith("visual:"):
            if binding["media_validation"] != "CONTAINER_STRUCTURE_ONLY":
                raise InputValidationError(f"{path}: mídia visual sem assinatura compatível.")
        elif binding["media_validation"] != "NOT_APPLICABLE":
            raise InputValidationError(f"{path}: media_validation em binding não visual.")
        if not isinstance(binding["sha256"], str) or not hmac.compare_digest(binding["sha256"], expected[binding_id]):
            raise InputValidationError(f"{path}.sha256 não coincide com a declaração congelada.")
        allowed_content_validation = {
            "NOT_APPLICABLE", "INTEGRITY_ONLY_NON_JSON",
            "INTEGRITY_ONLY_UNCONTRACTED_JSON", "LOC_CONTRACT_VALIDATED_DECLARED_BLIND",
        }
        if binding["content_validation"] not in allowed_content_validation:
            raise InputValidationError(f"{path}.content_validation: valor invalido.")
        if not isinstance(binding["loc_sector_ids"], list) or not isinstance(binding["loc_candidate_ids"], list):
            raise InputValidationError(f"{path}: listas de identificadores LOC esperadas.")
        for field in ("loc_sector_ids", "loc_candidate_ids"):
            for item_index, item in enumerate(binding[field]):
                _identifier(item, f"{path}.{field}[{item_index}]")
            _unique(binding[field], f"{path}.{field}")
        if binding_id == "loc_result_sha256":
            if binding["content_validation"] == "NOT_APPLICABLE":
                raise InputValidationError(f"{path}: resultado LOC exige classificacao do conteudo.")
            if binding["content_validation"] != "LOC_CONTRACT_VALIDATED_DECLARED_BLIND" and (
                binding["loc_sector_ids"] or binding["loc_candidate_ids"]
            ):
                raise InputValidationError(f"{path}: IDs LOC exigem contrato semantico validado.")
        elif binding["content_validation"] != "NOT_APPLICABLE" or binding["loc_sector_ids"] or binding["loc_candidate_ids"]:
            raise InputValidationError(f"{path}: metadados de conteudo LOC em binding incompativel.")
        binding_ids.append(binding_id)
    _unique(binding_ids, "artifact_verification.bindings")
    if set(binding_ids) != set(expected):
        raise InputValidationError("Verificação marcada como completa não abrange todos os artefatos declarados.")
    return set(binding_ids)


def compile_case(
    payload: Mapping[str, Any],
    rules: Mapping[str, Any],
    artifact_map: Mapping[str, Any] | None = None,
    artifact_root: Path | None = None,
    visual_metadata_manifest: Mapping[str, Any] | None = None,
    visual_sector_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validate_case(payload)
    if payload["record_status"] != "CONGELADO":
        raise InputValidationError("Somente entrada congelada pode ser compilada.")
    validate_rules_catalog(rules)

    input_sha = payload["freeze_metadata"]["payload_sha256"]
    rules_sha = canonical_sha256(rules)
    if (artifact_map is None) != (artifact_root is None):
        raise InputValidationError("artifact_map e artifact_root devem ser informados juntos.")
    if (visual_metadata_manifest is None) != (visual_sector_binding is None):
        raise InputValidationError(
            "visual_metadata_manifest e visual_sector_binding devem ser informados juntos."
        )
    if visual_metadata_manifest is not None and (
        artifact_map is None or artifact_root is None
    ):
        raise InputValidationError(
            "O pacote visual exige artifact_map e artifact_root para reextração dos originais."
        )
    verification = (
        verify_artifact_bindings(payload, artifact_map, artifact_root)
        if artifact_map is not None and artifact_root is not None
        else {
            "status": "NOT_PERFORMED",
            "artifact_root_not_embedded": True,
            "known_location_conflict": False,
            "bindings": [],
        }
    )
    verified_binding_ids = _validate_artifact_verification(payload, verification)
    immediate_parent_verified = "parent_case" in verified_binding_ids
    parent_chain_verified = (
        payload["case_revision"] == 1
        or (payload["case_revision"] == 2 and immediate_parent_verified)
    )
    point_eligibility = _evidence_eligibility(
        payload["planning_point"]["evidence"],
        _datetime(payload["search_context"]["assessment_at"], "assessment_at"),
    )
    if payload["planning_point"]["position_observed_at"] is None:
        point_eligibility = "HORARIO_DO_PONTO_NAO_DISPONIVEL"
    known_location_event_verified = any(
        binding["qualifies_known_location"] for binding in verification["bindings"]
    )
    if (
        known_location_event_verified
        and payload["person_location_status"] != "CONHECIDA_OPERACIONALMENTE"
    ):
        raise InputValidationError(
            "case.person_location_status: evento positivo de localização foi verificado, mas o status permanece DESCONHECIDA; crie nova revisão coerente antes de compilar."
        )
    if payload["person_location_status"] == "CONHECIDA_OPERACIONALMENTE" and known_location_event_verified:
        loc_status = "NAO_APLICAVEL_ACESSO_E_RESGATE"
        loc_route = "ACESSO_E_RESGATE"
    elif payload["person_location_status"] == "CONHECIDA_OPERACIONALMENTE":
        loc_status = "LOCALIZACAO_CONHECIDA_DECLARADA_NAO_VERIFICADA"
        loc_route = "REVISAR_EVENTO_POSITIVO"
    elif point_eligibility != "ELEGIVEL":
        loc_status = "PONTO_DE_PLANEJAMENTO_NAO_ELEGIVEL"
        loc_route = "REVISAR_ENTRADA"
    elif payload["source_artifacts"]["loc_result_sha256"] is None:
        loc_status = "AGUARDANDO_PROCESSAMENTO"
        loc_route = "RANQUEAR_HIPOTESES"
    elif "loc_result_sha256" in verified_binding_ids:
        loc_binding = next(
            binding for binding in verification["bindings"]
            if binding["binding_id"] == "loc_result_sha256"
        )
        if loc_binding["content_validation"] == "LOC_CONTRACT_VALIDATED_DECLARED_BLIND":
            loc_status = "RESULTADO_EXTERNO_CONTRATO_VALIDADO_CEGAMENTO_DECLARADO"
        else:
            loc_status = "RESULTADO_EXTERNO_INTEGRIDADE_DE_BYTES_VERIFICADA_CONTEUDO_NAO_VALIDADO"
        loc_route = "RANQUEAR_HIPOTESES"
    else:
        loc_status = "RESULTADO_EXTERNO_DECLARADO_NAO_VERIFICADO"
        loc_route = "RANQUEAR_HIPOTESES"
    urgency = assess_urgency(payload, rules)
    loc_binding_for_det = next(
        (
            binding for binding in verification["bindings"]
            if binding["binding_id"] == "loc_result_sha256"
            and binding["content_validation"] == "LOC_CONTRACT_VALIDATED_DECLARED_BLIND"
        ),
        None,
    )
    valid_loc_sector_ids = (
        set(loc_binding_for_det["loc_sector_ids"])
        if loc_binding_for_det is not None
        else None
    )
    visual_package_validation: dict[str, Any] = {
        "status": "NOT_PROVIDED",
        "source_case_payload_sha256": input_sha,
        "loc_result_sha256": None,
        "metadata_manifest_sha256": None,
        "visual_sector_binding_sha256": None,
        "verified_pairs": {},
        "decoded_visual_ids": [],
        "contextual_visual_ids": sorted(
            visual["visual_id"] for visual in payload["visual_evidence"]
        ),
        "ground_truth_used": False,
        "affects_loc": False,
    }
    if visual_metadata_manifest is not None and visual_sector_binding is not None:
        if not isinstance(visual_metadata_manifest, Mapping) or not isinstance(
            visual_sector_binding, Mapping
        ):
            raise InputValidationError("Os artefatos visuais externos devem ser objetos JSON.")
        if loc_binding_for_det is None:
            raise InputValidationError(
                "O vínculo imagem--setor exige resultado LOC semanticamente validado."
            )
        assert artifact_map is not None and artifact_root is not None
        loc_relative = artifact_map.get("loc_result_sha256")
        if not isinstance(loc_relative, str):
            raise InputValidationError(
                "artifact_map.loc_result_sha256 é obrigatório para o pacote visual."
            )
        loc_document = _load_json((artifact_root.resolve() / Path(loc_relative)).resolve())
        if not isinstance(loc_document, Mapping):
            raise InputValidationError("O resultado LOC deve ser um objeto JSON.")
        visual_engine = _load_visual_spatial_engine_module()
        visual_package_validation = visual_engine.validate_visual_package(
            payload,
            loc_document,
            visual_metadata_manifest,
            visual_sector_binding,
            artifact_map,
            artifact_root,
        )
        expected_visual_validation_keys = {
            "status", "source_case_payload_sha256", "loc_result_sha256",
            "metadata_manifest_sha256", "visual_sector_binding_sha256",
            "verified_pairs", "decoded_visual_ids", "contextual_visual_ids",
            "ground_truth_used", "affects_loc",
        }
        if (
            not isinstance(visual_package_validation, Mapping)
            or set(visual_package_validation) != expected_visual_validation_keys
            or visual_package_validation["status"] != "VERIFIED"
            or visual_package_validation["ground_truth_used"] is not False
            or visual_package_validation["affects_loc"] is not False
            or visual_package_validation["source_case_payload_sha256"] != input_sha
            or visual_package_validation["loc_result_sha256"]
            != payload["source_artifacts"]["loc_result_sha256"]
        ):
            raise InputValidationError("Validação do pacote visual devolveu contrato inválido.")
        if not isinstance(visual_package_validation["verified_pairs"], Mapping):
            raise InputValidationError("Pacote visual devolveu pares verificados inválidos.")
        for field in ("decoded_visual_ids", "contextual_visual_ids"):
            values = visual_package_validation[field]
            if not isinstance(values, list) or len(values) != len(set(values)):
                raise InputValidationError(f"Pacote visual devolveu {field} inválido.")
            for index, visual_id in enumerate(values):
                _identifier(visual_id, f"visual_package_validation.{field}[{index}]")
    det_verified_binding_ids = {
        binding["binding_id"]
        for binding in verification["bindings"]
        if binding["binding_id"].startswith("visual:")
        and binding["media_validation"] == "PIXELS_DECODED_AND_DIMENSIONS_VALIDATED"
    }
    det_verified_binding_ids.update(
        f"visual:{visual_id}"
        for visual_id in visual_package_validation["decoded_visual_ids"]
    )
    detectability = assess_detectability(
        payload,
        det_verified_binding_ids,
        valid_loc_sector_ids,
        visual_package_validation["verified_pairs"],
    )
    det_statuses = {item["status"] for item in detectability["per_sector_modality"]}
    review_required = (
        loc_status == "AGUARDANDO_PROCESSAMENTO"
        or loc_status == "RESULTADO_EXTERNO_DECLARADO_NAO_VERIFICADO"
        or loc_status == "RESULTADO_EXTERNO_CONTRATO_VALIDADO_CEGAMENTO_DECLARADO"
        or loc_status == "RESULTADO_EXTERNO_INTEGRIDADE_DE_BYTES_VERIFICADA_CONTEUDO_NAO_VALIDADO"
        or loc_status == "LOCALIZACAO_CONHECIDA_DECLARADA_NAO_VERIFICADA"
        or loc_status == "PONTO_DE_PLANEJAMENTO_NAO_ELEGIVEL"
        or not parent_chain_verified
        or verification["known_location_conflict"]
        or urgency["status"] in {"REVISAO_IMEDIATA", "REVISAO_PRIORITARIA", "INDETERMINADA"}
        or not det_statuses
        or bool(det_statuses & {"REVISAR", "NAO_AVALIADO", "APTO_COM_RESTRICOES"})
    )
    loc_binding = next(
        (binding for binding in verification["bindings"] if binding["binding_id"] == "loc_result_sha256"),
        None,
    )
    location = {
        "status": loc_status,
        "processing_route": loc_route,
        "result_sha256": payload["source_artifacts"]["loc_result_sha256"],
        "engine_scope": "PERFIL_V3_SETORES_POR_CANDIDATO_SEM_RANKING_CRUZADO",
        "affected_by_urgency": False,
        "affected_by_detectability": False,
        "planning_point_eligibility": point_eligibility,
        "known_location_event_verified": known_location_event_verified,
        "known_location_conflict": verification["known_location_conflict"],
        "external_content_validation": (
            loc_binding["content_validation"] if loc_binding is not None else "NOT_VERIFIED"
        ),
        "valid_sector_ids": loc_binding["loc_sector_ids"] if loc_binding is not None else [],
        "valid_candidate_ids": loc_binding["loc_candidate_ids"] if loc_binding is not None else [],
    }
    location["logical_sha256"] = canonical_sha256(location)
    visual_quality_counts = {
        "APROXIMADO_METADADOS": 0,
        "VERIFICADO_CALIBRADO": 0,
        "CONTEXTUAL_INSUFICIENTE": 0,
    }
    qualified_visual_ids: list[str] = []
    if visual_sector_binding is not None:
        for item in visual_sector_binding["bindings"]:
            quality = item["quality"]
            visual_quality_counts[quality] += 1
            if item["spatially_qualified"] and item["applicable_sector_ids"]:
                qualified_visual_ids.append(item["visual_id"])
    output: dict[str, Any] = {
        "engine_id": ENGINE_ID,
        "protocol_version": PROTOCOL_VERSION,
        "scenario_id": payload["scenario_id"],
        "case_revision": payload["case_revision"],
        "source_case_frozen_at": payload["freeze_metadata"]["frozen_at"],
        "run_id": (
            f"{payload['scenario_id']}:r{payload['case_revision']}:"
            f"{input_sha[:12]}:{rules_sha[:12]}"
        ),
        "source_input_sha256": input_sha,
        "rules_catalog_sha256": rules_sha,
        "ground_truth_used": False,
        "ground_truth_scope": "MOTOR_INTEGRADO_SOMENTE",
        "blind_processing": True,
        "blind_processing_scope": "ENTRADA_E_MOTOR_INTEGRADO; ARTEFATO_LOC_CONFORME_EXTERNAL_CONTENT_VALIDATION",
        "storage_segregated": True,
        "parent_chain_status": (
            "NOT_APPLICABLE_FIRST_REVISION"
            if payload["case_revision"] == 1
            else (
                "FULL_CHAIN_VERIFIED"
                if parent_chain_verified
                else (
                    "IMMEDIATE_PARENT_VERIFIED_FULL_CHAIN_NOT_VERIFIED"
                    if immediate_parent_verified
                    else "NOT_VERIFIED"
                )
            )
        ),
        "artifact_verification": verification,
        "location": location,
        "urgency": urgency,
        "detectability": detectability,
        "visual_evidence_policy": {
            "files_count": len(payload["visual_evidence"]),
            "use": (
                "CONTEXTO_ANOTADO_E_VINCULO_ESPACIAL_DET"
                if visual_package_validation["status"] == "VERIFIED"
                else "CONTEXTO_ANOTADO_POR_HUMANO"
            ),
            "computer_vision_used": False,
            "numeric_model_input": False,
            "numeric_loc_input": False,
            "pixel_values_used_as_numeric_model_input": False,
            "metadata_used_for_det_spatial_binding": (
                visual_package_validation["status"] == "VERIFIED"
            ),
            "affects_loc": False,
            "file_validation": (
                "HASH_PIXELS_DIMENSOES_E_METADADOS_REEXTRAIDOS"
                if visual_package_validation["status"] == "VERIFIED"
                else "HASH_E_ESTRUTURA_DE_CONTÊINER; PIXELS_NAO_DECODIFICADOS"
            ),
            "metadata_manifest_validation": visual_package_validation["status"],
            "metadata_manifest_sha256": visual_package_validation[
                "metadata_manifest_sha256"
            ],
            "sector_binding_validation": visual_package_validation["status"],
            "sector_binding_sha256": visual_package_validation[
                "visual_sector_binding_sha256"
            ],
            "sector_binding_verified": (
                visual_package_validation["status"] == "VERIFIED"
            ),
            "sector_binding_usable_pair_count": len(
                visual_package_validation["verified_pairs"]
            ),
            "verified_sector_pairs": dict(
                sorted(visual_package_validation["verified_pairs"].items())
            ),
            "decoded_visual_ids": sorted(
                visual_package_validation["decoded_visual_ids"]
            ),
            "contextual_visual_ids": sorted(
                visual_package_validation["contextual_visual_ids"]
            ),
            "qualified_visual_ids": sorted(set(qualified_visual_ids)),
            "binding_quality_counts": visual_quality_counts,
            "metadata_and_operator_values_kept_separate": True,
            "camera_gps_role": "CONTEXTO_DE_CAPTURA_NAO_REFERENCIA_DE_AVALIACAO",
        },
        "cross_module_guard": {
            "single_combined_score": False,
            "loc_urg_det_kept_separate": True,
            "negative_search_changes_loc": False,
        },
        "review_required": review_required,
        "output_sha256": "0" * 64,
    }
    projected = deepcopy(output)
    projected.pop("output_sha256", None)
    output["output_sha256"] = canonical_sha256(projected)
    return output


def validate_event(payload: Mapping[str, Any]) -> None:
    enforce_ground_truth_firewall(payload)
    keys = {
        "protocol_version", "scenario_id", "event_id", "event_sequence", "record_status",
        "event_type", "started_at", "ended_at", "recorded_at", "source_type", "source_code",
        "authorized_for_model", "coverage_geometry_sha256", "track_sha256", "sector_ids",
        "modality", "effort_minutes", "coverage_status", "coverage_method_id", "coverage_fraction",
        "visibility_recorded", "visibility_class", "limitations_recorded", "limitations", "pod", "result",
        "clue_coordinate", "prior_run_sha256", "ground_truth_absent", "freeze_metadata",
        "previous_event_sha256", "source_event_sha256",
    }
    _require_keys(payload, keys, "event")
    _reject_extra_keys(payload, keys, "event")
    if payload["protocol_version"] != EVENT_PROTOCOL_VERSION:
        raise InputValidationError("event.protocol_version: versão inesperada.")
    _identifier(payload["scenario_id"], "event.scenario_id")
    _identifier(payload["event_id"], "event.event_id")
    _identifier(payload["source_code"], "event.source_code")
    if not isinstance(payload["event_sequence"], int) or isinstance(payload["event_sequence"], bool) or payload["event_sequence"] < 1:
        raise InputValidationError("event.event_sequence deve ser inteiro positivo.")
    if payload["record_status"] not in {"RASCUNHO", "CONGELADO"}:
        raise InputValidationError("event.record_status: valor inválido.")
    if payload["event_type"] not in {"BUSCA_EXECUTADA", "VESTIGIO_ENCONTRADO", "ATUALIZACAO_AMBIENTAL", "NOVO_PONTO_CONHECIDO", "OUTRO"}:
        raise InputValidationError("event.event_type: valor inválido.")
    started = _datetime(payload["started_at"], "event.started_at")
    ended = _datetime(payload["ended_at"], "event.ended_at")
    recorded = _datetime(payload["recorded_at"], "event.recorded_at")
    if started > ended or ended > recorded:
        raise InputValidationError("event: ordem temporal deve ser started_at <= ended_at <= recorded_at.")
    if payload["source_type"] not in {"EQUIPE_TERRESTRE", "EQUIPE_AEREA", "EQUIPE_FLUVIAL", "TESTEMUNHA", "SENSOR", "OUTRA"}:
        raise InputValidationError("event.source_type: valor inválido.")
    if not isinstance(payload["authorized_for_model"], bool):
        raise InputValidationError("event.authorized_for_model: booleano esperado.")
    for key in (
        "coverage_geometry_sha256", "track_sha256", "prior_run_sha256",
        "previous_event_sha256", "source_event_sha256",
    ):
        _sha_or_none(payload[key], f"event.{key}")
    if payload["event_sequence"] == 1 and payload["previous_event_sha256"] is not None:
        raise InputValidationError("event.previous_event_sha256 deve ser null na sequência 1.")
    if payload["event_sequence"] > 1 and payload["previous_event_sha256"] is None:
        raise InputValidationError("event.previous_event_sha256 é obrigatório após a sequência 1.")
    if payload["event_sequence"] == 1 and payload["source_event_sha256"] is not None:
        raise InputValidationError("event.source_event_sha256 deve ser null na sequência 1.")
    if payload["event_type"] != "NOVO_PONTO_CONHECIDO" and payload["source_event_sha256"] is not None:
        raise InputValidationError(
            "event.source_event_sha256 é reservado a NOVO_PONTO_CONHECIDO."
        )
    sector_values = _array(payload["sector_ids"], "event.sector_ids", max_items=1000)
    sectors = [_identifier(value, f"event.sector_ids[{index}]") for index, value in enumerate(sector_values)]
    _unique(sectors, "event.sector_ids")
    modalities = {"BUSCA_TERRESTRE", "OBSERVACAO_AEREA_RGB", "CAMERA_TERMICA", "BUSCA_FLUVIAL", None}
    if payload["modality"] not in modalities:
        raise InputValidationError("event.modality: valor inválido.")
    if payload["effort_minutes"] is not None and _finite(payload["effort_minutes"], "event.effort_minutes") <= 0:
        raise InputValidationError("event.effort_minutes deve ser positivo.")
    duration_minutes = (ended - started).total_seconds() / 60.0
    if payload["event_type"] == "BUSCA_EXECUTADA":
        if duration_minutes <= 0:
            raise InputValidationError("Busca executada exige duração temporal positiva.")
        if payload["effort_minutes"] is not None and float(payload["effort_minutes"]) > duration_minutes + 1 / 60:
            raise InputValidationError("event.effort_minutes excede a duração registrada.")
    if payload["coverage_status"] not in {"MEDIDA", "DERIVADA", "RELATADA", "NAO_DISPONIVEL"}:
        raise InputValidationError("event.coverage_status: valor inválido.")
    if payload["coverage_method_id"] is not None:
        _identifier(payload["coverage_method_id"], "event.coverage_method_id")
    fraction = payload["coverage_fraction"]
    if fraction is not None:
        fraction = _finite(fraction, "event.coverage_fraction")
        if not 0 <= fraction <= 1:
            raise InputValidationError("event.coverage_fraction deve estar em [0, 1].")
    if payload["coverage_status"] == "NAO_DISPONIVEL" and (
        payload["coverage_method_id"] is not None or fraction is not None
    ):
        raise InputValidationError("Cobertura indisponível exige método e fração null.")
    if payload["coverage_status"] in {"MEDIDA", "DERIVADA"} and (
        payload["coverage_method_id"] is None or fraction is None
    ):
        raise InputValidationError("Cobertura medida/derivada exige método e fração.")
    if not isinstance(payload["visibility_recorded"], bool) or not isinstance(payload["limitations_recorded"], bool):
        raise InputValidationError("event: controles de visibilidade/limitações devem ser booleanos.")
    if payload["visibility_class"] not in {"BOA", "MODERADA", "RESTRITA", "NAO_DISPONIVEL"}:
        raise InputValidationError("event.visibility_class: valor inválido.")
    if payload["visibility_recorded"] != (payload["visibility_class"] != "NAO_DISPONIVEL"):
        raise InputValidationError("event: visibility_recorded incoerente com visibility_class.")
    limitations = _array(payload["limitations"], "event.limitations", max_items=50)
    if any(
        not isinstance(item, str) or not item.strip() or len(item) > 240
        for item in limitations
    ):
        raise InputValidationError("event.limitations: lista de textos curtos esperada.")
    enforce_text_sanitization(limitations, "event.limitations")
    if payload["pod"] is not None:
        raise InputValidationError("event.pod deve ser null na V1; POD numérica ainda não foi calibrada.")
    if payload["result"] not in {"POSITIVO", "NAO_LOCALIZADO", "INCONCLUSIVO", "NAO_APLICAVEL"}:
        raise InputValidationError("event.result: valor inválido.")
    coordinate = payload["clue_coordinate"]
    if coordinate is not None:
        if not isinstance(coordinate, Mapping) or set(coordinate) != {"latitude", "longitude"}:
            raise InputValidationError("event.clue_coordinate: objeto inválido.")
        lat = _finite(coordinate["latitude"], "event.clue_coordinate.latitude")
        lon = _finite(coordinate["longitude"], "event.clue_coordinate.longitude")
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise InputValidationError("event.clue_coordinate: fora do WGS 84.")
    if payload["event_type"] == "NOVO_PONTO_CONHECIDO" and (
        payload["event_sequence"] == 1
        or payload["result"] != "POSITIVO"
        or coordinate is None
        or not payload["authorized_for_model"]
        or payload["source_event_sha256"] is None
    ):
        raise InputValidationError(
            "Novo ponto conhecido exige sequência posterior à primeira, resultado positivo, coordenada, autorização e evento-fonte."
        )
    if payload["event_type"] == "VESTIGIO_ENCONTRADO" and (
        payload["result"] != "POSITIVO" or coordinate is None
    ):
        raise InputValidationError("Vestígio encontrado exige resultado positivo e coordenada.")
    if payload["ground_truth_absent"] is not True:
        raise InputValidationError("event.ground_truth_absent deve ser true.")
    if payload["record_status"] == "CONGELADO":
        _validate_freeze(payload["freeze_metadata"], "event.freeze_metadata", EVENT_FREEZE_PROJECTION_ID)
        calculated = calculate_event_freeze_sha256(payload)
        if not hmac.compare_digest(payload["freeze_metadata"]["payload_sha256"], calculated):
            raise InputValidationError("event.freeze_metadata.payload_sha256 não confere.")
        frozen_at = _datetime(payload["freeze_metadata"]["frozen_at"], "event.freeze_metadata.frozen_at")
        if frozen_at < recorded:
            raise InputValidationError("event.freeze_metadata.frozen_at anterior ao registro.")
    elif payload["freeze_metadata"] is not None:
        raise InputValidationError("event.freeze_metadata deve ser null em rascunho.")


def prepare_frozen_event(
    payload: Mapping[str, Any],
    frozen_at: str,
    previous_event: Mapping[str, Any] | None = None,
    source_event: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    draft = deepcopy(dict(payload))
    if draft.get("record_status") != "RASCUNHO" or draft.get("freeze_metadata") is not None:
        raise InputValidationError(
            "freeze-event aceita somente rascunho sem metadados; evento congelado é imutável."
        )
    validate_event(draft)
    if draft["event_sequence"] == 1:
        if previous_event is not None:
            raise InputValidationError("A sequência 1 não pode receber previous_event.")
    else:
        if previous_event is None:
            raise InputValidationError("Evento posterior exige previous_event para conferência.")
        validate_event(previous_event)
        if previous_event["record_status"] != "CONGELADO":
            raise InputValidationError("previous_event deve estar congelado.")
        if previous_event["scenario_id"] != draft["scenario_id"]:
            raise InputValidationError("previous_event pertence a outro cenário.")
        if previous_event["event_sequence"] + 1 != draft["event_sequence"]:
            raise InputValidationError("previous_event não é o predecessor imediato.")
        previous_hash = previous_event["freeze_metadata"]["payload_sha256"]
        if not hmac.compare_digest(draft["previous_event_sha256"], previous_hash):
            raise InputValidationError("previous_event_sha256 não confere com previous_event.")
        if _datetime(previous_event["recorded_at"], "previous_event.recorded_at") > _datetime(
            draft["started_at"], "event.started_at"
        ):
            raise InputValidationError("Evento iniciado antes do registro do predecessor.")
    if draft["source_event_sha256"] is None:
        if source_event is not None:
            raise InputValidationError("source_event fornecido sem source_event_sha256.")
    else:
        if source_event is None:
            raise InputValidationError("source_event_sha256 exige o artefato source_event.")
        validate_event(source_event)
        if source_event["record_status"] != "CONGELADO":
            raise InputValidationError("source_event deve estar congelado.")
        if source_event["scenario_id"] != draft["scenario_id"]:
            raise InputValidationError("source_event pertence a outro cenário.")
        if source_event["event_sequence"] >= draft["event_sequence"]:
            raise InputValidationError("source_event deve anteceder o evento derivado.")
        source_hash = source_event["freeze_metadata"]["payload_sha256"]
        if not hmac.compare_digest(draft["source_event_sha256"], source_hash):
            raise InputValidationError("source_event_sha256 não confere com source_event.")
        if (
            source_event["event_type"] not in _KNOWN_LOCATION_SOURCE_EVENT_TYPES
            or source_event["result"] != "POSITIVO"
            or source_event["authorized_for_model"] is not True
            or source_event["clue_coordinate"] is None
        ):
            raise InputValidationError(
                "source_event deve ser elegível, positivo, autorizado e possuir coordenada."
            )
        if _datetime(source_event["recorded_at"], "source_event.recorded_at") > _datetime(
            draft["started_at"], "event.started_at"
        ):
            raise InputValidationError("source_event foi registrado após o início do evento derivado.")
        if draft["event_type"] == "NOVO_PONTO_CONHECIDO" and source_event["clue_coordinate"] != draft["clue_coordinate"]:
            raise InputValidationError("Coordenada do novo ponto diverge do source_event positivo.")
    _datetime(frozen_at, "frozen_at")
    frozen = deepcopy(draft)
    frozen["record_status"] = "CONGELADO"
    frozen["freeze_metadata"] = {
        "frozen_at": frozen_at,
        "projection_id": EVENT_FREEZE_PROJECTION_ID,
        "payload_sha256": "0" * 64,
    }
    frozen["freeze_metadata"]["payload_sha256"] = calculate_event_freeze_sha256(frozen)
    validate_event(frozen)
    return frozen


def _valid_geojson_position(value: Any) -> bool:
    return bool(
        isinstance(value, list)
        and len(value) >= 2
        and all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(float(item))
            for item in value[:2]
        )
        and -180 <= float(value[0]) <= 180
        and -90 <= float(value[1]) <= 90
    )


def _valid_geojson_line(value: Any) -> bool:
    return bool(
        isinstance(value, list)
        and len(value) >= 2
        and all(_valid_geojson_position(position) for position in value)
        and any(position[:2] != value[0][:2] for position in value[1:])
    )


def _ring_has_positive_area(ring: Sequence[Any]) -> bool:
    longitudes: list[float] = []
    latitudes: list[float] = []
    for position in ring:
        longitude = float(position[0])
        if longitudes:
            while longitude - longitudes[-1] > 180.0:
                longitude -= 360.0
            while longitude - longitudes[-1] < -180.0:
                longitude += 360.0
        longitudes.append(longitude)
        latitudes.append(float(position[1]))
    twice_area = sum(
        longitudes[index] * latitudes[index + 1]
        - longitudes[index + 1] * latitudes[index]
        for index in range(len(ring) - 1)
    )
    return not math.isclose(twice_area, 0.0, rel_tol=0.0, abs_tol=1e-15)


def _valid_geojson_polygon(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for ring in value:
        if (
            not isinstance(ring, list)
            or len(ring) < 4
            or not all(_valid_geojson_position(position) for position in ring)
            or ring[0][:2] != ring[-1][:2]
            or not _ring_has_positive_area(ring)
        ):
            return False
    return True


def _geojson_polygons(value: Any) -> list[list[list[list[float]]]]:
    """Extrai polígonos completos, preservando anéis internos (buracos)."""
    if not isinstance(value, Mapping):
        return []
    object_type = value.get("type")
    if object_type == "FeatureCollection":
        return [
            polygon
            for feature in value.get("features", [])
            for polygon in _geojson_polygons(feature)
        ] if isinstance(value.get("features"), list) else []
    if object_type == "Feature":
        return _geojson_polygons(value.get("geometry"))
    if object_type == "GeometryCollection":
        return [
            polygon
            for geometry in value.get("geometries", [])
            for polygon in _geojson_polygons(geometry)
        ] if isinstance(value.get("geometries"), list) else []
    coordinates = value.get("coordinates")
    if object_type == "Polygon" and _valid_geojson_polygon(coordinates):
        return [[
            [list(map(float, point[:2])) for point in ring]
            for ring in coordinates
        ]]
    if object_type == "MultiPolygon" and isinstance(coordinates, list):
        return [
            [
                [list(map(float, point[:2])) for point in ring]
                for ring in polygon
            ]
            for polygon in coordinates
            if _valid_geojson_polygon(polygon)
        ]
    return []


def _geojson_lines(value: Any) -> list[list[list[float]]]:
    if not isinstance(value, Mapping):
        return []
    object_type = value.get("type")
    if object_type == "FeatureCollection":
        return [
            line
            for feature in value.get("features", [])
            for line in _geojson_lines(feature)
        ] if isinstance(value.get("features"), list) else []
    if object_type == "Feature":
        return _geojson_lines(value.get("geometry"))
    if object_type == "GeometryCollection":
        return [
            line
            for geometry in value.get("geometries", [])
            for line in _geojson_lines(geometry)
        ] if isinstance(value.get("geometries"), list) else []
    coordinates = value.get("coordinates")
    if object_type == "LineString" and _valid_geojson_line(coordinates):
        return [[list(map(float, point[:2])) for point in coordinates]]
    if object_type == "MultiLineString" and isinstance(coordinates, list):
        return [
            [list(map(float, point[:2])) for point in line]
            for line in coordinates
            if _valid_geojson_line(line)
        ]
    return []


def _gpx_lines(path: Path) -> list[list[list[float]]]:
    try:
        raw = path.read_text(encoding="utf-8")
        enforce_ground_truth_firewall(raw, "$track.gpx")
        root = ET.fromstring(raw)
    except (ET.ParseError, OSError, UnicodeDecodeError):
        return []
    lines: list[list[list[float]]] = []

    def points(container: ET.Element, point_name: str) -> list[list[float]]:
        current: list[list[float]] = []
        for element in list(container):
            name = element.tag.rsplit("}", 1)[-1].lower()
            if name != point_name:
                continue
            try:
                latitude = float(element.attrib["lat"])
                longitude = float(element.attrib["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            if (
                math.isfinite(latitude)
                and math.isfinite(longitude)
                and -90 <= latitude <= 90
                and -180 <= longitude <= 180
            ):
                current.append([longitude, latitude])
        return current

    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1].lower()
        if name == "trkseg":
            current = points(element, "trkpt")
        elif name == "rte":
            current = points(element, "rtept")
        else:
            continue
        if _valid_geojson_line(current):
            lines.append(current)
    return lines


def _orientation(a: Sequence[float], b: Sequence[float], c: Sequence[float]) -> float:
    return (float(b[0]) - float(a[0])) * (float(c[1]) - float(a[1])) - (
        float(b[1]) - float(a[1])
    ) * (float(c[0]) - float(a[0]))


def _point_on_segment(point: Sequence[float], a: Sequence[float], b: Sequence[float]) -> bool:
    return bool(
        math.isclose(_orientation(a, b, point), 0.0, rel_tol=0.0, abs_tol=1e-12)
        and min(float(a[0]), float(b[0])) - 1e-12 <= float(point[0]) <= max(float(a[0]), float(b[0])) + 1e-12
        and min(float(a[1]), float(b[1])) - 1e-12 <= float(point[1]) <= max(float(a[1]), float(b[1])) + 1e-12
    )


def _segments_intersect(
    a: Sequence[float], b: Sequence[float], c: Sequence[float], d: Sequence[float]
) -> bool:
    orientations = (_orientation(a, b, c), _orientation(a, b, d), _orientation(c, d, a), _orientation(c, d, b))
    if (orientations[0] > 0) != (orientations[1] > 0) and (orientations[2] > 0) != (orientations[3] > 0):
        return True
    return any((
        math.isclose(orientations[0], 0.0, abs_tol=1e-12) and _point_on_segment(c, a, b),
        math.isclose(orientations[1], 0.0, abs_tol=1e-12) and _point_on_segment(d, a, b),
        math.isclose(orientations[2], 0.0, abs_tol=1e-12) and _point_on_segment(a, c, d),
        math.isclose(orientations[3], 0.0, abs_tol=1e-12) and _point_on_segment(b, c, d),
    ))


def _point_in_ring(point: Sequence[float], ring: Sequence[Sequence[float]]) -> bool:
    inside = False
    x, y = float(point[0]), float(point[1])
    for index in range(len(ring) - 1):
        a, b = ring[index], ring[index + 1]
        if _point_on_segment(point, a, b):
            return True
        ax, ay = float(a[0]), float(a[1])
        bx, by = float(b[0]), float(b[1])
        if (ay > y) != (by > y):
            intersection_x = (bx - ax) * (y - ay) / (by - ay) + ax
            if x < intersection_x:
                inside = not inside
    return inside


def _point_on_ring(point: Sequence[float], ring: Sequence[Sequence[float]]) -> bool:
    return any(
        _point_on_segment(point, ring[index], ring[index + 1])
        for index in range(len(ring) - 1)
    )


def _point_in_polygon(
    point: Sequence[float], polygon: Sequence[Sequence[Sequence[float]]]
) -> bool:
    if not polygon or not _point_in_ring(point, polygon[0]):
        return False
    for hole in polygon[1:]:
        if _point_on_ring(point, hole):
            return True
        if _point_in_ring(point, hole):
            return False
    return True


def _track_intersects_coverage(
    coverage_path: Path, track_path: Path
) -> bool:
    try:
        coverage_document = json.loads(coverage_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    polygons = _geojson_polygons(coverage_document)
    if not polygons:
        return False
    try:
        track_document = json.loads(track_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        lines = _gpx_lines(track_path)
    else:
        lines = _geojson_lines(track_document)
    for line in lines:
        for polygon in polygons:
            if any(_point_in_polygon(point, polygon) for point in line):
                return True
            for ring in polygon:
                for line_index in range(len(line) - 1):
                    for ring_index in range(len(ring) - 1):
                        if _segments_intersect(
                            line[line_index], line[line_index + 1],
                            ring[ring_index], ring[ring_index + 1],
                        ):
                            return True
    return False


def _geojson_geometry_types(value: Any) -> set[str]:
    """Retorna apenas tipos com coordenadas geográficas minimamente válidas."""
    if not isinstance(value, Mapping):
        return set()
    object_type = value.get("type")
    if object_type == "FeatureCollection":
        features = value.get("features")
        if not isinstance(features, list) or not features:
            return set()
        found: set[str] = set()
        for feature in features:
            found.update(_geojson_geometry_types(feature))
        return found
    if object_type == "Feature":
        return _geojson_geometry_types(value.get("geometry"))
    if object_type == "GeometryCollection":
        geometries = value.get("geometries")
        if not isinstance(geometries, list) or not geometries:
            return set()
        found: set[str] = set()
        for geometry in geometries:
            found.update(_geojson_geometry_types(geometry))
        return found
    coordinates = value.get("coordinates")
    valid = bool(
        (object_type == "Point" and _valid_geojson_position(coordinates))
        or (
            object_type == "MultiPoint"
            and isinstance(coordinates, list)
            and bool(coordinates)
            and all(_valid_geojson_position(position) for position in coordinates)
        )
        or (object_type == "LineString" and _valid_geojson_line(coordinates))
        or (
            object_type == "MultiLineString"
            and isinstance(coordinates, list)
            and bool(coordinates)
            and all(_valid_geojson_line(line) for line in coordinates)
        )
        or (object_type == "Polygon" and _valid_geojson_polygon(coordinates))
        or (
            object_type == "MultiPolygon"
            and isinstance(coordinates, list)
            and bool(coordinates)
            and all(_valid_geojson_polygon(polygon) for polygon in coordinates)
        )
    )
    if valid:
        return {object_type}
    return set()


def _inspect_event_operational_artifact(
    binding_id: str, path: Path, payload: Mapping[str, Any]
) -> str:
    """Valida conteúdo mínimo antes de chamar um registro negativo de completo.

    O hash continua provando identidade dos bytes. Esta função acrescenta uma
    verificação estrutural conservadora; formatos não reconhecidos permanecem
    arquiváveis, mas não promovem o evento a evidência negativa documentada.
    """
    if binding_id in {"coverage_geometry", "track"}:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            document = None
        if document is not None:
            enforce_ground_truth_firewall(document, f"${binding_id}")
        geometry_types = _geojson_geometry_types(document)
        if binding_id == "coverage_geometry":
            if geometry_types & {"Polygon", "MultiPolygon"}:
                return "GEOJSON_COVERAGE_VALIDATED"
            return "BYTES_VERIFIED_CONTENT_UNVALIDATED"
        if geometry_types & {"LineString", "MultiLineString"}:
            return "GEOJSON_TRACK_VALIDATED"
        try:
            raw = path.read_text(encoding="utf-8")
            enforce_ground_truth_firewall(raw, "$track.gpx")
            root = ET.fromstring(raw)
            root_name = root.tag.rsplit("}", 1)[-1].lower()
        except (ET.ParseError, OSError, UnicodeDecodeError):
            root_name = ""
        if root_name == "gpx" and _gpx_lines(path):
            return "GPX_TRACK_VALIDATED"
        return "BYTES_VERIFIED_CONTENT_UNVALIDATED"

    if binding_id == "prior_run":
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "BYTES_VERIFIED_CONTENT_UNVALIDATED"
        if not isinstance(document, Mapping):
            return "BYTES_VERIFIED_CONTENT_UNVALIDATED"
        if document.get("ground_truth_scope") != "MOTOR_INTEGRADO_SOMENTE":
            return "BYTES_VERIFIED_CONTENT_UNVALIDATED"
        firewall_projection = deepcopy(dict(document))
        firewall_projection.pop("ground_truth_scope", None)
        enforce_ground_truth_firewall(firewall_projection, "$prior_run")
        declared_sha = document.get("output_sha256")
        try:
            prior_case_frozen_at = _datetime(
                document.get("source_case_frozen_at"),
                "prior_run.source_case_frozen_at",
            )
        except InputValidationError:
            return "BYTES_VERIFIED_CONTENT_UNVALIDATED"
        location = document.get("location")
        if not isinstance(location, Mapping):
            return "BYTES_VERIFIED_CONTENT_UNVALIDATED"
        declared_location_sha = location.get("logical_sha256")
        projected_location = deepcopy(dict(location))
        projected_location.pop("logical_sha256", None)
        valid_sector_ids = location.get("valid_sector_ids")
        if (
            set(document) != _INTEGRATED_OUTPUT_KEYS
            or document.get("scenario_id") != payload["scenario_id"]
            or document.get("engine_id") != ENGINE_ID
            or document.get("protocol_version") != PROTOCOL_VERSION
            or not isinstance(document.get("case_revision"), int)
            or isinstance(document.get("case_revision"), bool)
            or not isinstance(document.get("run_id"), str)
            or not document["run_id"].startswith(
                f"{payload['scenario_id']}:r{document['case_revision']}:"
            )
            or prior_case_frozen_at > _datetime(payload["started_at"], "event.started_at")
            or not isinstance(document.get("urgency"), Mapping)
            or not isinstance(document.get("detectability"), Mapping)
            or not isinstance(document.get("cross_module_guard"), Mapping)
            or document.get("ground_truth_used") is not False
            or document.get("blind_processing") is not True
            or document.get("storage_segregated") is not True
            or not isinstance(document.get("review_required"), bool)
            or not all(
                isinstance(document.get(key), str) and _SHA_RE.fullmatch(document[key])
                for key in ("source_input_sha256", "rules_catalog_sha256")
            )
            or not isinstance(declared_location_sha, str)
            or not _SHA_RE.fullmatch(declared_location_sha)
            or not hmac.compare_digest(
                declared_location_sha, canonical_sha256(projected_location)
            )
            or location.get("external_content_validation")
            != "LOC_CONTRACT_VALIDATED_DECLARED_BLIND"
            or not isinstance(valid_sector_ids, list)
            or not valid_sector_ids
            or len(valid_sector_ids) != len(set(valid_sector_ids))
            or any(
                not isinstance(sector_id, str) or _ID_RE.fullmatch(sector_id) is None
                for sector_id in valid_sector_ids
            )
            or document.get("run_id")
            != (
                f"{payload['scenario_id']}:r{document['case_revision']}:"
                f"{document['source_input_sha256'][:12]}:"
                f"{document['rules_catalog_sha256'][:12]}"
            )
            or not isinstance(declared_sha, str)
            or not _SHA_RE.fullmatch(declared_sha)
        ):
            return "BYTES_VERIFIED_CONTENT_UNVALIDATED"
        projected = deepcopy(dict(document))
        projected.pop("output_sha256", None)
        if not hmac.compare_digest(declared_sha, canonical_sha256(projected)):
            return "BYTES_VERIFIED_CONTENT_UNVALIDATED"
        return "PRIOR_RUN_LOGICAL_OUTPUT_VALIDATED"
    return "NOT_APPLICABLE"


def _prior_run_valid_sector_ids(path: Path) -> list[str]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(document, Mapping) or not isinstance(document.get("location"), Mapping):
        return []
    sectors = document["location"].get("valid_sector_ids")
    return list(sectors) if isinstance(sectors, list) else []


def verify_event_artifact_bindings(
    payload: Mapping[str, Any], artifact_map: Mapping[str, Any], artifact_root: Path
) -> dict[str, Any]:
    """Verifica bytes operacionais e vínculos lógicos entre eventos congelados."""
    expected: dict[str, str] = {}
    for binding_id, field in (
        ("coverage_geometry", "coverage_geometry_sha256"),
        ("track", "track_sha256"),
        ("prior_run", "prior_run_sha256"),
        ("previous_event", "previous_event_sha256"),
        ("source_event", "source_event_sha256"),
    ):
        if payload[field] is not None:
            expected[binding_id] = payload[field]
    if set(artifact_map) != set(expected):
        missing = sorted(set(expected) - set(artifact_map))
        extras = sorted(set(artifact_map) - set(expected))
        raise InputValidationError(
            f"Mapa de artefatos do evento não coincide; ausentes={missing}, extras={extras}."
        )
    root_resolved = artifact_root.resolve()
    bindings: list[dict[str, Any]] = []
    resolved_paths: dict[str, Path] = {}
    for binding_id in sorted(expected):
        relative = artifact_map[binding_id]
        if not isinstance(relative, str) or not relative.strip():
            raise InputValidationError(f"event_artifact_map.{binding_id}: caminho relativo esperado.")
        relative_path = Path(relative)
        if relative_path.is_absolute():
            raise InputValidationError(f"event_artifact_map.{binding_id}: caminho absoluto não permitido.")
        path = (root_resolved / relative_path).resolve()
        try:
            path.relative_to(root_resolved)
        except ValueError as exc:
            raise InputValidationError(f"event_artifact_map.{binding_id}: caminho sai da raiz.") from exc
        if not path.is_file():
            raise InputValidationError(f"event_artifact_map.{binding_id}: arquivo não encontrado.")
        resolved_paths[binding_id] = path
        if binding_id in {"previous_event", "source_event"}:
            linked = _load_json(path)
            if not isinstance(linked, Mapping):
                raise InputValidationError(f"event_artifact_map.{binding_id}: JSON de evento inválido.")
            validate_event(linked)
            if linked["record_status"] != "CONGELADO":
                raise InputValidationError(f"event_artifact_map.{binding_id}: evento não congelado.")
            linked_hash = linked["freeze_metadata"]["payload_sha256"]
            if not hmac.compare_digest(linked_hash, expected[binding_id]):
                raise InputValidationError(f"event_artifact_map.{binding_id}: hash lógico não confere.")
            if linked["scenario_id"] != payload["scenario_id"]:
                raise InputValidationError(f"event_artifact_map.{binding_id}: cenário divergente.")
            if binding_id == "previous_event":
                if linked["event_sequence"] + 1 != payload["event_sequence"]:
                    raise InputValidationError("previous_event verificado não é o predecessor imediato.")
                if _datetime(linked["recorded_at"], "previous_event.recorded_at") > _datetime(
                    payload["started_at"], "event.started_at"
                ):
                    raise InputValidationError(
                        "previous_event verificado foi registrado após o início do evento."
                    )
            if binding_id == "source_event":
                if (
                    linked["event_sequence"] >= payload["event_sequence"]
                    or linked["event_type"] not in _KNOWN_LOCATION_SOURCE_EVENT_TYPES
                    or linked["result"] != "POSITIVO"
                    or linked["authorized_for_model"] is not True
                    or linked["clue_coordinate"] is None
                ):
                    raise InputValidationError(
                        "source_event verificado não é um evento anterior, positivo, autorizado e georreferenciado."
                    )
                if _datetime(linked["recorded_at"], "source_event.recorded_at") > _datetime(
                    payload["started_at"], "event.started_at"
                ):
                    raise InputValidationError(
                        "source_event verificado foi registrado após o início do evento derivado."
                    )
                if payload["event_type"] == "NOVO_PONTO_CONHECIDO" and linked["clue_coordinate"] != payload["clue_coordinate"]:
                    raise InputValidationError("source_event verificado possui coordenada divergente.")
            verification_kind = "EVENT_LOGICAL_SHA256"
            calculated = linked_hash
        else:
            calculated = file_sha256(path)
            if not hmac.compare_digest(calculated, expected[binding_id]):
                raise InputValidationError(f"event_artifact_map.{binding_id}: SHA-256 dos bytes não confere.")
            verification_kind = "FILE_BYTES_SHA256"
        content_validation = (
            _inspect_event_operational_artifact(binding_id, path, payload)
            if binding_id in {"coverage_geometry", "track", "prior_run"}
            else "NOT_APPLICABLE"
        )
        validated_sector_ids = (
            _prior_run_valid_sector_ids(path)
            if binding_id == "prior_run"
            and content_validation == "PRIOR_RUN_LOGICAL_OUTPUT_VALIDATED"
            else []
        )
        bindings.append({
            "binding_id": binding_id,
            "relative_path": relative_path.as_posix(),
            "sha256": calculated,
            "verification_kind": verification_kind,
            "content_validation": content_validation,
            "validated_sector_ids": validated_sector_ids,
        })
    content_by_id = {item["binding_id"]: item["content_validation"] for item in bindings}
    if (
        content_by_id.get("coverage_geometry") == "GEOJSON_COVERAGE_VALIDATED"
        and content_by_id.get("track") in {"GEOJSON_TRACK_VALIDATED", "GPX_TRACK_VALIDATED"}
        and not _track_intersects_coverage(
            resolved_paths["coverage_geometry"], resolved_paths["track"]
        )
    ):
        for binding in bindings:
            if binding["binding_id"] in {"coverage_geometry", "track"}:
                binding["content_validation"] = "GEOMETRY_VALIDATED_NO_TRACK_INTERSECTION"
    return {
        "status": "VERIFIED",
        "artifact_root_not_embedded": True,
        "bindings": bindings,
    }


def compile_event(
    payload: Mapping[str, Any],
    artifact_map: Mapping[str, Any] | None = None,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    validate_event(payload)
    if payload["record_status"] != "CONGELADO":
        raise InputValidationError("Somente evento congelado pode ser compilado.")
    if (artifact_map is None) != (artifact_root is None):
        raise InputValidationError("artifact_map e artifact_root devem ser informados juntos.")
    verification = (
        verify_event_artifact_bindings(payload, artifact_map, artifact_root)
        if artifact_map is not None and artifact_root is not None
        else {"status": "NOT_PERFORMED", "artifact_root_not_embedded": True, "bindings": []}
    )
    verified_ids = {item["binding_id"] for item in verification["bindings"]}
    content_validation_by_id = {
        item["binding_id"]: item.get("content_validation", "NOT_APPLICABLE")
        for item in verification["bindings"]
    }
    search_artifacts_structurally_validated = all((
        content_validation_by_id.get("coverage_geometry") == "GEOJSON_COVERAGE_VALIDATED",
        content_validation_by_id.get("track")
        in {"GEOJSON_TRACK_VALIDATED", "GPX_TRACK_VALIDATED"},
        content_validation_by_id.get("prior_run") == "PRIOR_RUN_LOGICAL_OUTPUT_VALIDATED",
    ))
    # A versão atual ainda não recebe geometria autenticada dos setores nem
    # proveniência temporal executável da trilha. Logo, a coerência interna dos
    # três arquivos é documental/estrutural, mas não comprova que a cobertura
    # ocorreu nos setores declarados e dentro da janela deste evento.
    coverage_linked_to_sector_geometry = False
    track_temporal_provenance_verified = False
    search_artifacts_semantically_validated = bool(
        search_artifacts_structurally_validated
        and coverage_linked_to_sector_geometry
        and track_temporal_provenance_verified
    )
    prior_run_binding = next(
        (
            item for item in verification["bindings"]
            if item["binding_id"] == "prior_run"
        ),
        None,
    )
    prior_run_sector_ids = set(
        prior_run_binding.get("validated_sector_ids", [])
        if prior_run_binding is not None
        else []
    )
    sectors_linked_to_prior_loc = bool(payload["sector_ids"]) and set(
        payload["sector_ids"]
    ).issubset(prior_run_sector_ids)
    started = _datetime(payload["started_at"], "event.started_at")
    ended = _datetime(payload["ended_at"], "event.ended_at")
    positive_duration = ended > started
    documentary_search_record_complete = all((
        payload["event_type"] == "BUSCA_EXECUTADA",
        {"coverage_geometry", "track", "prior_run"}.issubset(verified_ids),
        search_artifacts_structurally_validated,
        sectors_linked_to_prior_loc,
        bool(payload["sector_ids"]),
        payload["modality"] is not None,
        payload["effort_minutes"] is not None,
        positive_duration,
        payload["coverage_status"] in {"MEDIDA", "DERIVADA"},
        payload["coverage_method_id"] is not None,
        payload["coverage_fraction"] is not None and payload["coverage_fraction"] > 0,
        payload["visibility_recorded"],
        payload["limitations_recorded"],
        payload["authorized_for_model"],
    ))
    complete_search_record = bool(
        documentary_search_record_complete
        and search_artifacts_semantically_validated
    )
    negative_eligible_for_review = payload["result"] == "NAO_LOCALIZADO" and complete_search_record
    immediate_predecessor_verified = (
        payload["event_sequence"] == 1
        or "previous_event" in verified_ids
    )
    chain_verified = (
        payload["event_sequence"] == 1
        or (
            payload["event_sequence"] == 2
            and "previous_event" in verified_ids
        )
    )
    source_verified = (
        payload["source_event_sha256"] is None
        or "source_event" in verified_ids
    )
    if payload["event_type"] == "NOVO_PONTO_CONHECIDO" and chain_verified and source_verified:
        next_action = "REPROCESSAR_COM_NOVO_PONTO"
    elif payload["event_type"] == "NOVO_PONTO_CONHECIDO":
        next_action = "REVISAR_VINCULOS_DO_NOVO_PONTO"
    elif payload["result"] == "POSITIVO":
        next_action = "REVISAO_HUMANA_DA_PISTA"
    else:
        next_action = "MANTER_RANKING_E_REVISAR"
    output: dict[str, Any] = {
        "engine_id": ENGINE_ID,
        "scenario_id": payload["scenario_id"],
        "event_id": payload["event_id"],
        "event_payload_sha256": payload["freeze_metadata"]["payload_sha256"],
        "previous_event_sha256": payload["previous_event_sha256"],
        "origin_event_sha256": payload["source_event_sha256"],
        "artifact_verification": verification,
        "chain_verified": chain_verified,
        "immediate_predecessor_verified": immediate_predecessor_verified,
        "source_event_verified": source_verified,
        "ground_truth_used": False,
        "result": payload["result"],
        "documentary_search_record_complete": documentary_search_record_complete,
        "search_record_complete": complete_search_record,
        "search_artifacts_structurally_validated": search_artifacts_structurally_validated,
        "search_artifacts_semantically_validated": search_artifacts_semantically_validated,
        "coverage_linked_to_sector_geometry": coverage_linked_to_sector_geometry,
        "track_temporal_provenance_verified": track_temporal_provenance_verified,
        "sectors_linked_to_prior_loc": sectors_linked_to_prior_loc,
        "coverage_status": payload["coverage_status"],
        "coverage_fraction": payload["coverage_fraction"],
        "visibility_class": payload["visibility_class"],
        "limitations": list(payload["limitations"]),
        "pod": None,
        "negative_evidence_eligible_for_human_review": negative_eligible_for_review,
        "location_ranking_effect": "NONE_V1",
        "sector_elimination_allowed": False,
        "next_action": next_action,
        "warnings": [],
        "output_sha256": "0" * 64,
    }
    if payload["result"] == "NAO_LOCALIZADO" and not complete_search_record:
        output["warnings"].append("Resultado negativo sem documentação suficiente de cobertura/detectabilidade.")
    if payload["result"] == "NAO_LOCALIZADO" and documentary_search_record_complete:
        output["warnings"].append(
            "Documentação estrutural presente, mas sem vínculo geográfico autenticado "
            "cobertura-setor e sem proveniência temporal verificável da trilha."
        )
    if payload["event_sequence"] > 1 and not immediate_predecessor_verified:
        output["warnings"].append("Predecessor imediato declarado, mas não verificado.")
    elif payload["event_sequence"] > 2 and not chain_verified:
        output["warnings"].append(
            "Predecessor imediato verificado; a cadeia completa até a sequência 1 não foi comprovada nesta compilação."
        )
    if payload["source_event_sha256"] is not None and not source_verified:
        output["warnings"].append("Evento positivo de origem declarado, mas não verificado.")
    if payload["result"] == "NAO_LOCALIZADO":
        output["warnings"].append("Não localizado não demonstra ausência e não altera LOC na V1.")
    projected = deepcopy(output)
    projected.pop("output_sha256", None)
    output["output_sha256"] = canonical_sha256(projected)
    return output


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"Não foi possível ler JSON válido: {path}") from exc


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze_case_parser = subparsers.add_parser("freeze-case")
    freeze_case_parser.add_argument("input", type=Path)
    freeze_case_parser.add_argument("output", type=Path)
    freeze_case_parser.add_argument("--frozen-at", required=True)
    freeze_case_parser.add_argument("--parent-case", type=Path)
    freeze_event_parser = subparsers.add_parser("freeze-event")
    freeze_event_parser.add_argument("input", type=Path)
    freeze_event_parser.add_argument("output", type=Path)
    freeze_event_parser.add_argument("--frozen-at", required=True)
    freeze_event_parser.add_argument("--previous-event", type=Path)
    freeze_event_parser.add_argument("--source-event", type=Path)
    compile_case_parser = subparsers.add_parser("compile-case")
    compile_case_parser.add_argument("input", type=Path)
    compile_case_parser.add_argument("output", type=Path)
    compile_case_parser.add_argument("--rules", type=Path, default=DEFAULT_RULES_PATH)
    compile_case_parser.add_argument("--artifact-root", type=Path)
    compile_case_parser.add_argument("--artifact-map", type=Path)
    compile_case_parser.add_argument("--visual-metadata-manifest", type=Path)
    compile_case_parser.add_argument("--visual-sector-binding", type=Path)
    build_loc_parser = subparsers.add_parser("build-loc-envelope")
    build_loc_parser.add_argument("input", type=Path, help="Caso integrado associado")
    build_loc_parser.add_argument("output", type=Path)
    build_loc_parser.add_argument(
        "--profile-input",
        dest="profile_inputs",
        type=Path,
        action="append",
        required=True,
        help="Entrada congelada do PERFIL V3; repetir uma vez por candidato",
    )
    build_loc_parser.add_argument(
        "--profile-result",
        dest="profile_results",
        type=Path,
        action="append",
        required=True,
        help="Saída correspondente do PERFIL V3; repetir na mesma quantidade",
    )
    compile_event_parser = subparsers.add_parser("compile-event")
    compile_event_parser.add_argument("input", type=Path)
    compile_event_parser.add_argument("output", type=Path)
    compile_event_parser.add_argument("--artifact-root", type=Path)
    compile_event_parser.add_argument("--artifact-map", type=Path)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        source = _load_json(args.input)
        if not isinstance(source, Mapping):
            raise InputValidationError("A raiz do arquivo deve ser um objeto JSON.")
        if args.command == "freeze-case":
            parent_case = _load_json(args.parent_case) if args.parent_case is not None else None
            if parent_case is not None and not isinstance(parent_case, Mapping):
                raise InputValidationError("parent_case deve ser objeto JSON.")
            result = prepare_frozen_case(source, args.frozen_at, parent_case)
        elif args.command == "compile-case":
            rules = _load_json(args.rules)
            if not isinstance(rules, Mapping):
                raise InputValidationError("Catálogo de regras deve ser objeto JSON.")
            if (args.artifact_root is None) != (args.artifact_map is None):
                raise InputValidationError("--artifact-root e --artifact-map devem ser informados juntos.")
            if (args.visual_metadata_manifest is None) != (
                args.visual_sector_binding is None
            ):
                raise InputValidationError(
                    "--visual-metadata-manifest e --visual-sector-binding devem ser informados juntos."
                )
            artifact_map = None
            if args.artifact_map is not None:
                artifact_map = _load_json(args.artifact_map)
                if not isinstance(artifact_map, Mapping):
                    raise InputValidationError("Mapa de artefatos deve ser objeto JSON.")
            visual_manifest = (
                _load_json(args.visual_metadata_manifest)
                if args.visual_metadata_manifest is not None
                else None
            )
            visual_binding = (
                _load_json(args.visual_sector_binding)
                if args.visual_sector_binding is not None
                else None
            )
            if visual_manifest is not None and not isinstance(visual_manifest, Mapping):
                raise InputValidationError("Manifesto visual deve ser objeto JSON.")
            if visual_binding is not None and not isinstance(visual_binding, Mapping):
                raise InputValidationError("Vínculo visual deve ser objeto JSON.")
            result = compile_case(
                source,
                rules,
                artifact_map,
                args.artifact_root,
                visual_manifest,
                visual_binding,
            )
        elif args.command == "build-loc-envelope":
            if len(args.profile_inputs) != len(args.profile_results):
                raise InputValidationError(
                    "Cada --profile-input deve possuir exatamente um --profile-result correspondente."
                )
            inputs_by_candidate: dict[str, Mapping[str, Any]] = {}
            for input_path in args.profile_inputs:
                profile_input = _load_json(input_path)
                if not isinstance(profile_input, Mapping):
                    raise InputValidationError(
                        f"Entrada PERFIL V3 deve ser objeto JSON: {input_path}"
                    )
                candidate_id = _identifier(
                    profile_input.get("candidate_id"),
                    f"{input_path}.candidate_id",
                )
                if candidate_id in inputs_by_candidate:
                    raise InputValidationError(
                        f"Entrada PERFIL V3 duplicada para candidate_id={candidate_id}."
                    )
                inputs_by_candidate[candidate_id] = profile_input
            results_by_candidate: dict[str, Mapping[str, Any]] = {}
            for result_path in args.profile_results:
                profile_result = _load_json(result_path)
                if not isinstance(profile_result, Mapping):
                    raise InputValidationError(
                        f"Resultado PERFIL V3 deve ser objeto JSON: {result_path}"
                    )
                candidate_id = _identifier(
                    profile_result.get("candidate_id"),
                    f"{result_path}.candidate_id",
                )
                if candidate_id in results_by_candidate:
                    raise InputValidationError(
                        f"Resultado PERFIL V3 duplicado para candidate_id={candidate_id}."
                    )
                results_by_candidate[candidate_id] = profile_result
            if set(inputs_by_candidate) != set(results_by_candidate):
                raise InputValidationError(
                    "Os candidate_id das entradas e saídas PERFIL V3 devem coincidir exatamente."
                )
            profile_runs = [
                {
                    "candidate_id": candidate_id,
                    "profile_input": inputs_by_candidate[candidate_id],
                    "profile_result": results_by_candidate[candidate_id],
                }
                for candidate_id in sorted(inputs_by_candidate)
            ]
            result = build_loc_result_envelope(source, profile_runs)
        elif args.command == "freeze-event":
            previous_event = _load_json(args.previous_event) if args.previous_event is not None else None
            source_event = _load_json(args.source_event) if args.source_event is not None else None
            if previous_event is not None and not isinstance(previous_event, Mapping):
                raise InputValidationError("previous_event deve ser objeto JSON.")
            if source_event is not None and not isinstance(source_event, Mapping):
                raise InputValidationError("source_event deve ser objeto JSON.")
            result = prepare_frozen_event(source, args.frozen_at, previous_event, source_event)
        else:
            if (args.artifact_root is None) != (args.artifact_map is None):
                raise InputValidationError("--artifact-root e --artifact-map devem ser informados juntos.")
            artifact_map = None
            if args.artifact_map is not None:
                artifact_map = _load_json(args.artifact_map)
                if not isinstance(artifact_map, Mapping):
                    raise InputValidationError("Mapa de artefatos deve ser objeto JSON.")
            result = compile_event(source, artifact_map, args.artifact_root)
        _write_json(args.output, result)
    except ProtocolError as exc:
        print(f"ERRO: {exc}")
        return 2
    print(f"OK: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
