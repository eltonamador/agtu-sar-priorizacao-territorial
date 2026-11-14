#!/usr/bin/env python3
"""Motor reprodutível do buffer adaptativo EXT-ESP-BUF-v1.0.

O módulo recebe apenas dados cegos do candidato, calcula um raio adaptativo e
produz resultados tabulares e polígonos GeoJSON. Coordenadas de referência,
campos de *ground truth* e indicadores derivados deles são rejeitados antes de
qualquer cálculo.

O motor usa exclusivamente a biblioteca-padrão do Python. A geometria circular
é aproximada por 72 segmentos de grande círculo sobre uma esfera de raio médio
WGS84 (6 371 008,8 m). Essa aproximação é adequada aos raios congelados neste
protocolo (250 m a 7 500 m), mas não substitui uma geometria geodésica de alta
precisão para emprego operacional.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


PROTOCOL_ID = "EXT-ESP-BUF-v1.0"
ENGINE_VERSION = "1.0.0"
EARTH_RADIUS_M = 6_371_008.8

FROZEN_CONFIG: dict[str, Any] = {
    "protocol_id": PROTOCOL_ID,
    "radius": {"min_m": 250.0, "max_m": 7_500.0, "baseline_fixed_m": 2_000.0},
    "quality": {"alpha": 0.5},
    "environment_factors": {
        "RURAL/ABERTO": 1.00,
        "MISTO": 1.10,
        "URBANO": 1.20,
        "MATA": 1.25,
        "ÁREA ALAGADA": 1.15,
        "DESCONHECIDO": 1.15,
    },
    "stability": {"alpha": 0.5, "reference_m": 50.0},
    "time": {"alpha": 0.5, "reference_min": 180.0},
    "geometry": {"vertices": 72, "earth_radius_m": EARTH_RADIUS_M},
}

R0_SEMANTICS = {"nominal_base", "source_adjusted", "diagnostic_legacy"}
FACTOR_ORDER = ("f_q", "f_e", "f_s", "f_t")
FACTOR_ALIASES = {
    "f_q": "f_q",
    "fq": "f_q",
    "quality": "f_q",
    "detection_quality": "f_q",
    "qualidade": "f_q",
    "f_e": "f_e",
    "fe": "f_e",
    "environment": "f_e",
    "environment_class": "f_e",
    "ambiente": "f_e",
    "f_s": "f_s",
    "fs": "f_s",
    "stability": "f_s",
    "position_dispersion": "f_s",
    "dispersion": "f_s",
    "estabilidade": "f_s",
    "f_t": "f_t",
    "ft": "f_t",
    "time": "f_t",
    "information_age": "f_t",
    "age": "f_t",
    "tempo": "f_t",
}

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "scenario_id": ("scenario_id",),
    "candidate_id": ("candidate_id",),
    "latitude": ("estimated_lat", "candidate_lat", "latitude"),
    "longitude": ("estimated_lon", "candidate_lon", "longitude"),
    "r0": ("base_radius_m", "r0_m", "uncertainty_radius_m"),
    "quality": ("detection_quality", "confidence_score", "q_det"),
    "environment": ("environment_class", "environment", "ambiente"),
    "dispersion": (
        "position_dispersion_m",
        "sigma_pos_m",
        "position_stability_m",
    ),
    "age": ("information_age_min", "age_min", "data_age_min"),
    "r0_semantics": ("r0_semantics",),
    "factors_applied": ("factors_applied",),
}

REQUIRED_CANONICAL_FIELDS = (
    "scenario_id",
    "candidate_id",
    "latitude",
    "longitude",
    "r0",
    "quality",
    "r0_semantics",
)

FORBIDDEN_EXACT = {
    "ground_truth",
    "ground_truth_lat",
    "ground_truth_lon",
    "ground_truth_used",
    "gt_lat",
    "gt_lon",
    "reference_lat",
    "reference_lon",
    "true_lat",
    "true_lon",
    "base_lat",
    "base_lon",
    "generator_distance",
    "generator_distance_m",
    "distance_to_reference",
    "distance_to_reference_m",
    "relevant_candidate",
    "latitude_real",
    "longitude_real",
    "posicao_real",
    "position_real",
}

FORBIDDEN_FRAGMENTS = (
    "ground_truth",
    "reference_lat",
    "reference_lon",
    "true_lat",
    "true_lon",
    "generator_distance",
    "distance_to_reference",
    "relevant_candidate",
    "latitude_real",
    "longitude_real",
    "posicao_real",
    "position_real",
)

OUTPUT_FIELDS = (
    "protocol_id",
    "engine_version",
    "scenario_id",
    "candidate_id",
    "estimated_lat",
    "estimated_lon",
    "base_radius_m",
    "r0_semantics",
    "factors_applied_source",
    "factors_applied_by_engine",
    "detection_quality",
    "environment_class",
    "position_dispersion_m",
    "information_age_min",
    "f_q",
    "f_e",
    "f_s",
    "f_t",
    "effective_f_q",
    "effective_f_e",
    "effective_f_s",
    "effective_f_t",
    "raw_radius_m",
    "adaptive_radius_m",
    "clamp_status",
    "expansion_ratio",
    "buffer_area_m2",
    "baseline_fixed_m",
    "adaptive_minus_baseline_m",
    "adaptive_to_baseline_ratio",
    "missing_optional_count",
    "review_status",
    "execution_classification",
    "warning_codes",
    "confirmatory_eligible",
    "ground_truth_used",
    "source_row_hash",
    "r0_provenance",
    "data_origin",
    "execution_phase",
)


class BufferEngineError(ValueError):
    """Erro controlado de configuração, esquema ou conteúdo de entrada."""


class ProtocolConfigError(BufferEngineError):
    """A configuração não corresponde ao protocolo congelado."""


class InputSchemaError(BufferEngineError):
    """O esquema de entrada é inválido ou contém informação proibida."""


class InputValueError(BufferEngineError):
    """Um registro contém valor ausente ou fora do domínio permitido."""


def _normalized_token(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _display_environment(value: Any, row_label: str) -> tuple[str, str]:
    """Normaliza a classe e retorna (classe, estado).

    O estado distingue uma ausência real da categoria explícita
    ``DESCONHECIDO``. Classes não reconhecidas são rejeitadas, pois convertê-las
    automaticamente poderia alterar o raio sem base no protocolo.
    """

    token = _normalized_token(value)
    aliases = {
        "rural_aberto": "RURAL/ABERTO",
        "rural": "RURAL/ABERTO",
        "aberto": "RURAL/ABERTO",
        "misto": "MISTO",
        "urbano": "URBANO",
        "mata": "MATA",
        "floresta": "MATA",
        "area_alagada": "ÁREA ALAGADA",
        "alagada": "ÁREA ALAGADA",
        "desconhecido": "DESCONHECIDO",
        "unknown": "DESCONHECIDO",
    }
    if token == "":
        return "DESCONHECIDO", "missing"
    if token in aliases:
        normalized = aliases[token]
        return normalized, "explicit_unknown" if normalized == "DESCONHECIDO" else "known"
    raise InputValueError(
        f"{row_label}: environment_class não reconhecido: {value!r}. "
        "Use RURAL/ABERTO, MISTO, URBANO, MATA, ÁREA ALAGADA ou DESCONHECIDO."
    )


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _as_float(
    value: Any,
    *,
    field: str,
    row_label: str,
    allow_blank: bool = False,
) -> float | None:
    if _is_blank(value):
        if allow_blank:
            return None
        raise InputValueError(f"{row_label}: '{field}' é obrigatório.")
    try:
        number = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise InputValueError(
            f"{row_label}: '{field}' deve ser numérico; recebido {value!r}."
        ) from exc
    if not math.isfinite(number):
        raise InputValueError(f"{row_label}: '{field}' deve ser finito.")
    return number


def _get_value(row: Mapping[str, Any], canonical: str, *, required: bool = True) -> Any:
    for alias in FIELD_ALIASES[canonical]:
        if alias in row:
            return row[alias]
    if required:
        raise InputSchemaError(
            f"Campo obrigatório ausente para '{canonical}'. Aceitos: "
            + ", ".join(FIELD_ALIASES[canonical])
        )
    return None


def _parse_factors_applied(value: Any, semantics: str, row_label: str) -> tuple[set[str], bool]:
    """Retorna fatores já embutidos no r0 e indicador de origem desconhecida."""

    if isinstance(value, (list, tuple, set)):
        raw_items = [str(item) for item in value]
    else:
        raw = "" if value is None else str(value).strip()
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise InputValueError(
                    f"{row_label}: 'factors_applied' contém JSON inválido."
                ) from exc
            if not isinstance(parsed, list):
                raise InputValueError(
                    f"{row_label}: 'factors_applied' em JSON deve ser uma lista."
                )
            raw_items = [str(item) for item in parsed]
        else:
            raw_items = [item for item in re.split(r"[;,|\s]+", raw) if item]

    normalized_items = [_normalized_token(item) for item in raw_items]
    none_tokens = {"", "none", "nenhum", "na", "n_a", "not_applicable"}
    unknown_tokens = {"unknown", "desconhecido", "incerto", "legacy_unknown"}
    has_unknown = any(item in unknown_tokens for item in normalized_items)
    # Nas linhas legadas, a lista vazia significa que não é possível provar
    # quais ajustes já foram incorporados pelo gerador. O cálculo prossegue
    # apenas como diagnóstico e mantém explícito o risco de dupla contagem.
    if semantics == "diagnostic_legacy" and not normalized_items:
        has_unknown = True
    normalized_items = [item for item in normalized_items if item not in none_tokens | unknown_tokens]

    parsed_factors: set[str] = set()
    invalid: list[str] = []
    for item in normalized_items:
        factor = FACTOR_ALIASES.get(item)
        if factor is None:
            invalid.append(item)
        else:
            parsed_factors.add(factor)
    if invalid:
        raise InputValueError(
            f"{row_label}: fatores desconhecidos em 'factors_applied': "
            + ", ".join(sorted(invalid))
        )

    if semantics == "nominal_base" and (parsed_factors or has_unknown):
        raise InputValueError(
            f"{row_label}: r0_semantics='nominal_base' exige factors_applied='none'."
        )
    if semantics == "source_adjusted" and (not parsed_factors or has_unknown):
        raise InputValueError(
            f"{row_label}: r0_semantics='source_adjusted' exige lista explícita de fatores já aplicados."
        )
    if semantics == "diagnostic_legacy" and not parsed_factors and not has_unknown:
        has_unknown = True
    return parsed_factors, has_unknown


def validate_headers(headers: Sequence[str] | None) -> dict[str, str]:
    """Valida a barreira cega e devolve o mapeamento canônico → cabeçalho."""

    if not headers:
        raise InputSchemaError("Arquivo de entrada sem cabeçalho.")
    raw_headers = [str(header).strip() for header in headers]
    normalized = [_normalized_token(header) for header in raw_headers]
    if len(set(normalized)) != len(normalized):
        raise InputSchemaError("Há cabeçalhos duplicados após normalização.")

    forbidden = []
    for raw, token in zip(raw_headers, normalized):
        if token in FORBIDDEN_EXACT or any(fragment in token for fragment in FORBIDDEN_FRAGMENTS):
            forbidden.append(raw)
    if forbidden:
        raise InputSchemaError(
            "Barreira cega acionada: campos de ground truth ou derivados são proibidos: "
            + ", ".join(forbidden)
        )

    header_by_token = dict(zip(normalized, raw_headers))
    mapping: dict[str, str] = {}
    missing: list[str] = []
    for canonical in REQUIRED_CANONICAL_FIELDS:
        found = next(
            (header_by_token[alias] for alias in FIELD_ALIASES[canonical] if alias in header_by_token),
            None,
        )
        if found is None:
            missing.append(f"{canonical} ({'/'.join(FIELD_ALIASES[canonical])})")
        else:
            mapping[canonical] = found
    if missing:
        raise InputSchemaError("Campos obrigatórios ausentes: " + "; ".join(missing))

    for optional in ("environment", "dispersion", "age", "factors_applied"):
        found = next(
            (header_by_token[alias] for alias in FIELD_ALIASES[optional] if alias in header_by_token),
            None,
        )
        if found is not None:
            mapping[optional] = found
    return mapping


def _internal_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Converte a configuração documental extensa para a forma de cálculo.

    A forma curta existe apenas para facilitar testes unitários. O arquivo
    normativo do pacote usa a forma documental, com ``factors`` e
    ``spatial_reference``.
    """

    if "factors" not in config:
        internal = json.loads(json.dumps(config, ensure_ascii=False))
        internal.setdefault("radius", {}).setdefault("baseline_fixed_m", 2_000.0)
        internal.setdefault(
            "policies",
            {
                "environment_missing_warning": "ENVIRONMENT_MISSING_DEFAULT_APPLIED",
                "environment_unknown_warning": "ENVIRONMENT_DESCONHECIDO",
                "dispersion_missing_warning": "POSITION_DISPERSION_MISSING_NEUTRAL_APPLIED",
                "age_missing_warning": "INFORMATION_AGE_MISSING_NEUTRAL_APPLIED",
                "review_threshold": 2,
                "multiple_missing_warning": "MULTIPLE_OPTIONAL_INPUTS_MISSING",
                "default_status": "CALCULADO",
                "review_status": "REVISAR",
                "minimum_clamp_warning": "RADIUS_CLAMPED_TO_MINIMUM",
                "maximum_clamp_warning": "RADIUS_CLAMPED_TO_MAXIMUM",
                "diagnostic_warning": "R0_ENTANGLED_WITH_GENERATOR_AND_INFORMATION_AGE",
                "diagnostic_classification": "DIAGNOSTICO_LEGADO_NAO_CONFIRMATORIO",
            },
        )
        return internal

    try:
        radius = config["radius"]
        factors = config["factors"]
        spatial = config["spatial_reference"]
        missing = config["missing_data_policy"]
        r0_rules = config["r0_semantics"]["allowed_values"]["diagnostic_legacy"]
    except (KeyError, TypeError) as exc:
        raise ProtocolConfigError(
            "Configuração documental incompleta para o protocolo congelado."
        ) from exc
    return {
        "protocol_id": config.get("protocol_id"),
        "radius": {
            "min_m": radius.get("r_min_m"),
            "max_m": radius.get("r_max_m"),
            "baseline_fixed_m": radius.get("baseline_fixed_m"),
        },
        "quality": {"alpha": factors["quality"].get("alpha")},
        "environment_factors": dict(factors["environment"].get("multipliers", {})),
        "stability": {
            "alpha": factors["position_dispersion"].get("alpha"),
            "reference_m": factors["position_dispersion"].get("reference_m"),
        },
        "time": {
            "alpha": factors["information_age"].get("alpha"),
            "reference_min": factors["information_age"].get("reference_min"),
        },
        "geometry": {
            "vertices": spatial.get("polygon_vertices"),
            "earth_radius_m": spatial.get("earth_radius_m"),
        },
        "policies": {
            "environment_missing_warning": factors["environment"].get(
                "missing_warning", "ENVIRONMENT_MISSING_DEFAULT_APPLIED"
            ),
            "environment_unknown_warning": factors["environment"].get(
                "explicit_unknown_warning", "ENVIRONMENT_DESCONHECIDO"
            ),
            "dispersion_missing_warning": factors["position_dispersion"].get(
                "missing_warning", "POSITION_DISPERSION_MISSING_NEUTRAL_APPLIED"
            ),
            "age_missing_warning": factors["information_age"].get(
                "missing_warning", "INFORMATION_AGE_MISSING_NEUTRAL_APPLIED"
            ),
            "review_threshold": missing.get("review_threshold", 2),
            "multiple_missing_warning": missing.get(
                "warning_when_threshold_reached", "MULTIPLE_OPTIONAL_INPUTS_MISSING"
            ),
            "default_status": missing.get(
                "default_status_when_no_review_rule_is_triggered", "CALCULADO"
            ),
            "review_status": missing.get("status_when_threshold_reached", "REVISAR"),
            "minimum_clamp_warning": radius.get(
                "minimum_clamp_flag", "RADIUS_CLAMPED_TO_MINIMUM"
            ),
            "maximum_clamp_warning": radius.get(
                "maximum_clamp_flag", "RADIUS_CLAMPED_TO_MAXIMUM"
            ),
            "diagnostic_warning": r0_rules.get(
                "forced_warning", "R0_ENTANGLED_WITH_GENERATOR_AND_INFORMATION_AGE"
            ),
            "diagnostic_classification": r0_rules.get(
                "forced_execution_classification",
                "DIAGNOSTICO_LEGADO_NAO_CONFIRMATORIO",
            ),
        },
    }


def _deep_compare_frozen(config: Mapping[str, Any]) -> dict[str, Any]:
    """Impede alteração silenciosa dos parâmetros congelados."""

    internal = _internal_config(config)

    def expect_number(path: tuple[str, ...], expected: float) -> None:
        cursor: Any = internal
        try:
            for part in path:
                cursor = cursor[part]
        except (KeyError, TypeError) as exc:
            raise ProtocolConfigError(f"Configuração sem o parâmetro {'.'.join(path)}.") from exc
        try:
            actual = float(cursor)
        except (TypeError, ValueError) as exc:
            raise ProtocolConfigError(f"Parâmetro {'.'.join(path)} deve ser numérico.") from exc
        if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12):
            raise ProtocolConfigError(
                f"Parâmetro congelado divergente em {'.'.join(path)}: {actual} != {expected}."
            )

    if internal.get("protocol_id") != PROTOCOL_ID:
        raise ProtocolConfigError(
            f"protocol_id deve ser {PROTOCOL_ID!r}; recebido {internal.get('protocol_id')!r}."
        )
    expect_number(("radius", "min_m"), 250.0)
    expect_number(("radius", "max_m"), 7_500.0)
    expect_number(("radius", "baseline_fixed_m"), 2_000.0)
    expect_number(("quality", "alpha"), 0.5)
    expect_number(("stability", "alpha"), 0.5)
    expect_number(("stability", "reference_m"), 50.0)
    expect_number(("time", "alpha"), 0.5)
    expect_number(("time", "reference_min"), 180.0)
    expect_number(("geometry", "vertices"), 72.0)
    expect_number(("geometry", "earth_radius_m"), EARTH_RADIUS_M)

    supplied = internal.get("environment_factors")
    if not isinstance(supplied, Mapping):
        raise ProtocolConfigError("environment_factors deve ser um objeto.")
    for label, expected in FROZEN_CONFIG["environment_factors"].items():
        try:
            actual = float(supplied[label])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProtocolConfigError(f"Fator ambiental ausente ou inválido: {label}.") from exc
        if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12):
            raise ProtocolConfigError(
                f"Fator ambiental congelado divergente para {label}: {actual} != {expected}."
            )
    return internal


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProtocolConfigError(f"Arquivo de configuração não encontrado: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ProtocolConfigError(f"JSON de configuração inválido: {exc}") from exc
    if not isinstance(config, dict):
        raise ProtocolConfigError("A raiz da configuração deve ser um objeto JSON.")
    return _deep_compare_frozen(config)


def frozen_config_copy() -> dict[str, Any]:
    """Devolve uma cópia independente dos parâmetros congelados."""

    return json.loads(json.dumps(FROZEN_CONFIG, ensure_ascii=False))


def _row_label(row: Mapping[str, Any], row_number: int | None = None) -> str:
    scenario = row.get("scenario_id") or row.get("scenario") or "?"
    candidate = row.get("candidate_id") or row.get("candidate") or "?"
    prefix = f"linha {row_number}" if row_number is not None else "registro"
    return f"{prefix} [{scenario}/{candidate}]"


def compute_record(
    row: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    row_number: int | None = None,
) -> dict[str, Any]:
    """Calcula um registro, sem acessar qualquer dado de referência."""

    config = _deep_compare_frozen(config)
    validate_headers(list(row.keys()))
    label = _row_label(row, row_number)

    scenario_id = str(_get_value(row, "scenario_id")).strip()
    candidate_id = str(_get_value(row, "candidate_id")).strip()
    if not scenario_id or not candidate_id:
        raise InputValueError(f"{label}: scenario_id e candidate_id não podem ser vazios.")

    latitude = _as_float(_get_value(row, "latitude"), field="estimated_lat", row_label=label)
    longitude = _as_float(_get_value(row, "longitude"), field="estimated_lon", row_label=label)
    base_radius = _as_float(_get_value(row, "r0"), field="base_radius_m", row_label=label)
    quality = _as_float(_get_value(row, "quality"), field="detection_quality", row_label=label)
    dispersion = _as_float(
        _get_value(row, "dispersion", required=False),
        field="position_dispersion_m",
        row_label=label,
        allow_blank=True,
    )
    age = _as_float(
        _get_value(row, "age", required=False),
        field="information_age_min",
        row_label=label,
        allow_blank=True,
    )

    assert latitude is not None
    assert longitude is not None
    assert base_radius is not None
    assert quality is not None
    if not -90.0 <= latitude <= 90.0:
        raise InputValueError(f"{label}: latitude fora de [-90, 90].")
    if not -180.0 <= longitude <= 180.0:
        raise InputValueError(f"{label}: longitude fora de [-180, 180].")
    if base_radius <= 0.0:
        raise InputValueError(f"{label}: base_radius_m deve ser > 0.")
    if not 0.0 <= quality <= 1.0:
        raise InputValueError(f"{label}: detection_quality deve estar em [0, 1].")
    if dispersion is not None and dispersion < 0.0:
        raise InputValueError(f"{label}: position_dispersion_m deve ser >= 0.")
    if age is not None and age < 0.0:
        raise InputValueError(f"{label}: information_age_min deve ser >= 0.")

    semantics = _normalized_token(_get_value(row, "r0_semantics"))
    if semantics not in R0_SEMANTICS:
        raise InputValueError(
            f"{label}: r0_semantics inválido; use {', '.join(sorted(R0_SEMANTICS))}."
        )
    already_applied, factors_unknown = _parse_factors_applied(
        _get_value(row, "factors_applied", required=False), semantics, label
    )

    environment, environment_state = _display_environment(
        _get_value(row, "environment", required=False), label
    )
    warnings: list[str] = []
    force_review = False
    if environment_state == "missing":
        warnings.append(config["policies"]["environment_missing_warning"])
        force_review = True
    elif environment_state == "explicit_unknown":
        warnings.append(config["policies"]["environment_unknown_warning"])
        force_review = True
    if dispersion is None:
        warnings.append(config["policies"]["dispersion_missing_warning"])
    if age is None:
        warnings.append(config["policies"]["age_missing_warning"])
    if semantics == "diagnostic_legacy":
        warnings.append(config["policies"]["diagnostic_warning"])
    if factors_unknown:
        warnings.append("R0_FACTORS_APPLIED_UNKNOWN")

    if semantics == "nominal_base":
        expected_nominal = float(config["radius"]["baseline_fixed_m"])
        if not math.isclose(base_radius, expected_nominal, rel_tol=0.0, abs_tol=1e-9):
            raise InputValueError(
                f"{label}: nominal_base exige base_radius_m={expected_nominal:g}."
            )

    f_q = 1.0 + float(config["quality"]["alpha"]) * (1.0 - quality)
    f_e = float(config["environment_factors"][environment])
    f_s = (
        1.0
        if dispersion is None
        else 1.0
        + float(config["stability"]["alpha"])
        * min(dispersion / float(config["stability"]["reference_m"]), 1.0)
    )
    f_t = (
        1.0
        if age is None
        else 1.0
        + float(config["time"]["alpha"])
        * min(age / float(config["time"]["reference_min"]), 1.0)
    )
    factors = {"f_q": f_q, "f_e": f_e, "f_s": f_s, "f_t": f_t}

    effective: dict[str, float] = {}
    for factor in FACTOR_ORDER:
        if semantics != "diagnostic_legacy" and factor in already_applied:
            effective[factor] = 1.0
            warnings.append(f"FACTOR_ALREADY_APPLIED_{factor.upper()}")
        else:
            effective[factor] = factors[factor]

    raw_radius = base_radius * math.prod(effective.values())
    min_radius = float(config["radius"]["min_m"])
    max_radius = float(config["radius"]["max_m"])
    adaptive_radius = min(max_radius, max(min_radius, raw_radius))
    if raw_radius < min_radius:
        clamp_status = "MIN"
        warnings.append(config["policies"]["minimum_clamp_warning"])
    elif raw_radius > max_radius:
        clamp_status = "MAX"
        warnings.append(config["policies"]["maximum_clamp_warning"])
    else:
        clamp_status = "NONE"

    provenance = str(row.get("r0_provenance", "") or "").strip()
    data_origin = str(row.get("data_origin", "") or "").strip()
    execution_phase = str(row.get("execution_phase", "") or "").strip()
    eligibility_text = " ".join((provenance, data_origin, execution_phase)).upper()
    ineligible_marker = any(
        marker in eligibility_text
        for marker in ("SEMI", "SYNTH", "SINTET", "LEGACY", "GERADOR", "DEV_DRY", "DESENVOLV")
    )
    confirmatory_eligible = semantics != "diagnostic_legacy" and not ineligible_marker
    if not confirmatory_eligible:
        warnings.append("NOT_CONFIRMATORY_ELIGIBLE")

    missing_optional_count = sum(
        (
            environment_state == "missing",
            dispersion is None,
            age is None,
        )
    )
    if missing_optional_count >= int(config["policies"]["review_threshold"]):
        warnings.append(config["policies"]["multiple_missing_warning"])
        force_review = True
    review_status = (
        config["policies"]["review_status"]
        if force_review
        else config["policies"]["default_status"]
    )
    if semantics == "diagnostic_legacy":
        execution_classification = config["policies"]["diagnostic_classification"]
    elif confirmatory_eligible:
        execution_classification = "ELEGIVEL_PARA_AVALIACAO_CONFIRMATORIA"
    else:
        execution_classification = "DESENVOLVIMENTO_NAO_CONFIRMATORIO"

    source_factors = "unknown" if factors_unknown else ";".join(
        factor for factor in FACTOR_ORDER if factor in already_applied
    )
    if not source_factors:
        source_factors = "none"
    engine_factors = ";".join(
        factor
        for factor in FACTOR_ORDER
        if semantics == "diagnostic_legacy" or factor not in already_applied
    )

    baseline_fixed = float(config["radius"]["baseline_fixed_m"])
    return {
        "protocol_id": PROTOCOL_ID,
        "engine_version": ENGINE_VERSION,
        "scenario_id": scenario_id,
        "candidate_id": candidate_id,
        "estimated_lat": round(latitude, 8),
        "estimated_lon": round(longitude, 8),
        "base_radius_m": round(base_radius, 6),
        "r0_semantics": semantics,
        "factors_applied_source": source_factors,
        "factors_applied_by_engine": engine_factors or "none",
        "detection_quality": round(quality, 6),
        "environment_class": environment,
        "position_dispersion_m": None if dispersion is None else round(dispersion, 6),
        "information_age_min": None if age is None else round(age, 6),
        "f_q": round(f_q, 9),
        "f_e": round(f_e, 9),
        "f_s": round(f_s, 9),
        "f_t": round(f_t, 9),
        "effective_f_q": round(effective["f_q"], 9),
        "effective_f_e": round(effective["f_e"], 9),
        "effective_f_s": round(effective["f_s"], 9),
        "effective_f_t": round(effective["f_t"], 9),
        "raw_radius_m": round(raw_radius, 6),
        "adaptive_radius_m": round(adaptive_radius, 6),
        "clamp_status": clamp_status,
        "expansion_ratio": round(adaptive_radius / base_radius, 9),
        "buffer_area_m2": round(math.pi * adaptive_radius**2, 3),
        "baseline_fixed_m": round(baseline_fixed, 6),
        "adaptive_minus_baseline_m": round(adaptive_radius - baseline_fixed, 6),
        "adaptive_to_baseline_ratio": round(adaptive_radius / baseline_fixed, 9),
        "missing_optional_count": int(missing_optional_count),
        "review_status": review_status,
        "execution_classification": execution_classification,
        "warning_codes": ";".join(dict.fromkeys(warnings)),
        "confirmatory_eligible": confirmatory_eligible,
        "ground_truth_used": False,
        "source_row_hash": str(row.get("source_row_hash", "") or "").strip(),
        "r0_provenance": provenance,
        "data_origin": data_origin,
        "execution_phase": execution_phase,
    }


def process_records(
    rows: Iterable[Mapping[str, Any]], config: Mapping[str, Any]
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for row_number, row in enumerate(rows, start=2):
        result = compute_record(row, config, row_number=row_number)
        key = (result["scenario_id"], result["candidate_id"])
        if key in seen_keys:
            raise InputValueError(
                f"linha {row_number}: chave scenario_id/candidate_id duplicada: {key[0]}/{key[1]}."
            )
        seen_keys.add(key)
        results.append(result)
    if not results:
        raise InputValueError("O arquivo de entrada não contém registros.")
    return sorted(results, key=lambda item: (item["scenario_id"], item["candidate_id"]))


def destination_point(
    latitude_deg: float,
    longitude_deg: float,
    distance_m: float,
    bearing_deg: float,
    *,
    earth_radius_m: float = EARTH_RADIUS_M,
) -> tuple[float, float]:
    """Retorna (longitude, latitude) após deslocamento por grande círculo."""

    lat1 = math.radians(latitude_deg)
    lon1 = math.radians(longitude_deg)
    bearing = math.radians(bearing_deg)
    angular_distance = distance_m / earth_radius_m
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )
    lon2 = (lon2 + 3.0 * math.pi) % (2.0 * math.pi) - math.pi
    return round(math.degrees(lon2), 10), round(math.degrees(lat2), 10)


def circle_ring(
    latitude_deg: float,
    longitude_deg: float,
    radius_m: float,
    *,
    vertices: int = 72,
    earth_radius_m: float = EARTH_RADIUS_M,
) -> list[list[float]]:
    if vertices < 4:
        raise ValueError("vertices deve ser >= 4.")
    ring = [
        list(
            destination_point(
                latitude_deg,
                longitude_deg,
                radius_m,
                index * 360.0 / vertices,
                earth_radius_m=earth_radius_m,
            )
        )
        for index in range(vertices)
    ]
    ring.append(ring[0].copy())
    return ring


def to_geojson(results: Sequence[Mapping[str, Any]], config: Mapping[str, Any]) -> dict[str, Any]:
    vertices = int(config["geometry"]["vertices"])
    earth_radius = float(config["geometry"]["earth_radius_m"])
    features = []
    for result in results:
        safe_properties = {key: result.get(key) for key in OUTPUT_FIELDS if key not in {"estimated_lat", "estimated_lon"}}
        features.append(
            {
                "type": "Feature",
                "id": f"{result['scenario_id']}::{result['candidate_id']}",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        circle_ring(
                            float(result["estimated_lat"]),
                            float(result["estimated_lon"]),
                            float(result["adaptive_radius_m"]),
                            vertices=vertices,
                            earth_radius_m=earth_radius,
                        )
                    ],
                },
                "properties": safe_properties,
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "EXT_ESPACIAL_Buffer_Adaptativo_v1",
        "coordinate_reference_system": "EPSG:4326",
        "protocol_id": PROTOCOL_ID,
        "ground_truth_used": False,
        "features": features,
    }


def _atomic_text_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def write_csv(path: str | Path, results: Sequence[Mapping[str, Any]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(output_path.name + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for result in results:
            record = dict(result)
            for key in ("confirmatory_eligible", "ground_truth_used"):
                record[key] = str(bool(record[key])).lower()
            writer.writerow(record)
    temp.replace(output_path)


def write_json(path: str | Path, results: Sequence[Mapping[str, Any]]) -> None:
    payload = {
        "protocol_id": PROTOCOL_ID,
        "engine_version": ENGINE_VERSION,
        "ground_truth_used": False,
        "record_count": len(results),
        "results": list(results),
    }
    _atomic_text_write(
        Path(path), json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    )


def write_geojson(
    path: str | Path, results: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> None:
    _atomic_text_write(
        Path(path),
        json.dumps(to_geojson(results, config), ensure_ascii=False, indent=2) + "\n",
    )


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    *,
    input_path: str | Path,
    config_path: str | Path,
    output_paths: Sequence[str | Path],
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    engine_path = Path(__file__).resolve()
    files = [Path(input_path), Path(config_path), engine_path, *(Path(path) for path in output_paths)]
    return {
        "protocol_id": PROTOCOL_ID,
        "engine_version": ENGINE_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python_version": platform.python_version(),
        "ground_truth_used": False,
        "record_count": len(results),
        "confirmatory_eligible_records": sum(
            1 for result in results if bool(result["confirmatory_eligible"])
        ),
        "coordinate_reference_system": "EPSG:4326",
        "geometry": {
            "method": "great_circle_spherical",
            "vertices": 72,
            "earth_radius_m": EARTH_RADIUS_M,
        },
        "files": [
            {
                "role": (
                    "input"
                    if path.resolve() == Path(input_path).resolve()
                    else "config"
                    if path.resolve() == Path(config_path).resolve()
                    else "engine"
                    if path.resolve() == engine_path
                    else "output"
                ),
                "path": str(path),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in files
        ],
    }


def read_input_csv(path: str | Path) -> tuple[list[dict[str, str]], list[str]]:
    input_path = Path(path)
    try:
        with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = list(reader.fieldnames or [])
            validate_headers(headers)
            rows = [dict(row) for row in reader]
    except FileNotFoundError as exc:
        raise InputSchemaError(f"Arquivo de entrada não encontrado: {input_path}") from exc
    return rows, headers


def run_pipeline(
    *,
    input_path: str | Path,
    config_path: str | Path,
    output_csv_path: str | Path,
    output_json_path: str | Path,
    output_geojson_path: str | Path,
    manifest_path: str | Path,
) -> dict[str, Any]:
    paths = [
        Path(input_path).resolve(),
        Path(config_path).resolve(),
        Path(output_csv_path).resolve(),
        Path(output_json_path).resolve(),
        Path(output_geojson_path).resolve(),
        Path(manifest_path).resolve(),
    ]
    if len(set(paths)) != len(paths):
        raise BufferEngineError("Entradas, saídas e manifesto devem usar caminhos distintos.")

    config = load_config(config_path)
    rows, _headers = read_input_csv(input_path)
    results = process_records(rows, config)
    write_csv(output_csv_path, results)
    write_json(output_json_path, results)
    write_geojson(output_geojson_path, results, config)
    manifest = build_manifest(
        input_path=input_path,
        config_path=config_path,
        output_paths=(output_csv_path, output_json_path, output_geojson_path),
        results=results,
    )
    _atomic_text_write(
        Path(manifest_path),
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Executa o motor congelado do buffer adaptativo EXT-ESP-BUF-v1.0."
    )
    parser.add_argument("--input", required=True, help="CSV cego de candidatos.")
    parser.add_argument("--config", required=True, help="JSON do protocolo congelado.")
    parser.add_argument("--output-csv", required=True, help="CSV de resultados.")
    parser.add_argument("--output-json", required=True, help="JSON de resultados.")
    parser.add_argument("--output-geojson", required=True, help="GeoJSON dos buffers.")
    parser.add_argument("--manifest", required=True, help="Manifesto de hashes e proveniência.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = run_pipeline(
            input_path=args.input,
            config_path=args.config,
            output_csv_path=args.output_csv,
            output_json_path=args.output_json,
            output_geojson_path=args.output_geojson,
            manifest_path=args.manifest,
        )
    except BufferEngineError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "ok",
                "protocol_id": PROTOCOL_ID,
                "record_count": manifest["record_count"],
                "ground_truth_used": False,
                "manifest": str(args.manifest),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
