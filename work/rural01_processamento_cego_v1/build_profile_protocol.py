#!/usr/bin/env python3
"""Monta os artefatos PERFIL V2/V3 e URG/DET do cenário RURAL-01.

O script consome somente o ranking territorial já congelado e os polígonos
correspondentes. As pistas "Norte provável", seguimento de cercas/cursos
d'água e permanência em sombra são preservadas como contexto inferido, sem
serem convertidas em direção observada, azimute, peso ou preferência espacial.
Por isso, o PERFIL V3 deve abster-se e devolver exatamente o ranking
territorial. A condição clínica aciona apenas a rota de revisão prioritária do
URG; nenhum diagnóstico clínico ou dado de medicação/alimentação é criado.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import sys
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
PROFILE_V2_PATH = PROJECT_ROOT / "work/perfil_vitima_v2/compile_profile.py"
INTEGRATED_PATH = PROJECT_ROOT / "work/protocolo_integrado_v1/integrated_protocol.py"
DEFAULT_RANKING = PROJECT_ROOT / "outputs/campo_rural01/processamento_cego_v1/ranking_base_rural01.csv"
DEFAULT_POLYGONS = PROJECT_ROOT / "outputs/campo_rural01/processamento_cego_v1/setores_rural01.geojson"
DEFAULT_VISUAL_MANIFEST = (
    PROJECT_ROOT
    / "outputs/campo_rural01/entrada_cega_v1/manifesto_metadados_visuais.json"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs/campo_rural01/perfil_v2_v3"
POINT_AT = "2026-10-21T14:20:00-03:00"
POINT_LAT = 0.188611
POINT_LON = -51.155556
SOURCE_RADIUS_M = 1500.0
SCENARIO_ID = "RURAL-01"
OPERATOR_CODE = "PESQUISADOR-01"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Não foi possível importar {path}.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    """Prefere caminho reprodutível relativo ao projeto, inclusive em fixtures."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _artifact_map(
    bindings: Mapping[str, Path],
) -> tuple[dict[str, str], Path]:
    """Cria mapa relativo para verificação externa sem copiar os artefatos."""
    resolved = {key: path.resolve() for key, path in bindings.items()}
    common_root = Path(
        os.path.commonpath([str(path.parent) for path in resolved.values()])
    ).resolve()
    return (
        {
            key: path.relative_to(common_root).as_posix()
            for key, path in sorted(resolved.items())
        },
        common_root,
    )


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("Data/hora deve conter fuso horário.")
    return parsed


def _time_after(value: str, seconds: int) -> str:
    return (_parse_time(value) + timedelta(seconds=seconds)).isoformat(timespec="seconds")


def _v2_evidence(
    *,
    nature: str = "RELATADO",
    source: str = "OPERADOR",
    confidence: str = "MEDIA",
    authorized: bool = True,
) -> dict[str, Any]:
    return {
        "nature": nature,
        "source": source,
        "source_code": "FICHA_RURAL01" if source != "NAO_DISPONIVEL" else None,
        "observed_at": None,
        "time_precision": "NAO_DISPONIVEL",
        "confidence": confidence,
        "authorized_for_model": authorized,
    }


def _v2_unavailable() -> dict[str, Any]:
    return _v2_evidence(
        nature="NAO_DISPONIVEL",
        source="NAO_DISPONIVEL",
        confidence="NAO_AVALIADA",
        authorized=False,
    )


def build_profile_v2_draft(created_at: str) -> dict[str, Any]:
    point_time = _parse_time(POINT_AT)
    collected_time = _parse_time(created_at)
    elapsed_minutes = (collected_time - point_time).total_seconds() / 60.0
    if elapsed_minutes < 840.0:
        raise ValueError(
            "O horário de coleta deve ser posterior ao intervalo máximo informado de 14 horas."
        )

    known_high = _v2_evidence(confidence="ALTA")
    known_medium = _v2_evidence(confidence="MEDIA")
    inferred_low = _v2_evidence(nature="INFERIDO", confidence="BAIXA")
    return {
        "scenario_id": SCENARIO_ID,
        "protocol_version": "PERFIL-V2-DRAFT.2",
        "record_status": "RASCUNHO",
        "operator_code": OPERATOR_CODE,
        "collected_at": created_at,
        "last_planning_point": {
            "point_type": "PONTO_INICIAL_PLANEJAMENTO",
            "latitude": POINT_LAT,
            "longitude": POINT_LON,
            "timestamp": POINT_AT,
            "timestamp_precision": "EXATA",
            "timezone": "America/Belem",
            "coordinate_source": "CELULAR",
            "uncertainty_m": SOURCE_RADIUS_M,
            "uncertainty_status": "INFORMADA",
            "uncertainty_source": (
                "Ficha RURAL-01: referência de smartphone e último registro de ERB; "
                "raio direto informado pela fonte."
            ),
        },
        "search_context": {
            "environment": "RURAL",
            "elapsed_minutes": elapsed_minutes,
            "elapsed_status": "CALCULADO",
            "elapsed_source": "Diferença entre o horário do ponto e o registro do perfil.",
            "travel_mode": "A_PE",
            "weather_summary": None,
        },
        "victim_profile": {
            "age_group": {
                "fact_id": "F-RURAL01-IDADE",
                "value": "ADULTO",
                "evidence": deepcopy(known_high),
            },
            "mobility": {
                "fact_id": "F-RURAL01-MOBILIDADE",
                "value": "NORMAL",
                "evidence": deepcopy(known_high),
            },
            "maximum_plausible_travel_time": {
                "fact_id": "F-RURAL01-TEMPO-MAXIMO",
                "value_minutes": 840.0,
                "evidence": deepcopy(known_medium),
            },
            "cognitive_condition": {
                "fact_id": "F-RURAL01-COGNICAO",
                "value": "SEM_ALTERACAO_RELATADA",
                "evidence": deepcopy(known_medium),
            },
            "area_familiarity": {
                "fact_id": "F-RURAL01-FAMILIARIDADE",
                "value": "ALTA",
                "evidence": deepcopy(known_high),
            },
            "environment_experience": {
                "fact_id": "F-RURAL01-EXPERIENCIA",
                "value": "FREQUENTE",
                "evidence": deepcopy(known_high),
            },
            "physical_or_sensory_limitations": [
                {
                    "fact_id": "F-RURAL01-DIABETES",
                    "value_code": "PRESENTE",
                    "description": (
                        "Diabetes tipo 2 relatada; risco de hipoglicemia após período prolongado "
                        "sem alimentação adequada."
                    ),
                    "evidence": deepcopy(known_high),
                }
            ],
            "relevant_medication_effect": {
                "fact_id": "F-RURAL01-MEDICACAO",
                "value_code": "NAO_DISPONIVEL",
                "description": None,
                "evidence": _v2_unavailable(),
            },
            "previous_disappearances": {
                "fact_id": "F-RURAL01-DESAPARECIMENTOS-ANTERIORES",
                "value": None,
                "evidence": _v2_unavailable(),
            },
        },
        "clues": [
            {
                "clue_id": "P-RURAL01-NORTE-PROVAVEL",
                "clue_type": "OUTRA",
                "literal_description": (
                    "Norte foi informado como direção provável, sem observação direta, azimute, "
                    "tolerância angular ou origem espacial formalizada."
                ),
                "evidence": deepcopy(inferred_low),
                "spatial_status": "CONTEXTUAL_NAO_DIRECIONAL",
                "associated_location": None,
                "direction_data": None,
            },
            {
                "clue_id": "P-RURAL01-TENDENCIA-LINEAR",
                "clue_type": "OUTRA",
                "literal_description": (
                    "Há hipótese comportamental de seguimento de cercas, linhas de transmissão "
                    "ou cursos d'água, sem feição específica espacializada."
                ),
                "evidence": deepcopy(inferred_low),
                "spatial_status": "CONTEXTUAL_NAO_DIRECIONAL",
                "associated_location": None,
                "direction_data": None,
            },
            {
                "clue_id": "P-RURAL01-PEGADAS-CERCA",
                "clue_type": "OUTRA",
                "literal_description": (
                    "Pegadas compatíveis com botina foram relatadas próximas a uma cerca rompida, "
                    "mas a ocorrência ainda não possui coordenada ou geometria documentada."
                ),
                "evidence": deepcopy(known_medium),
                "spatial_status": "ESPACIALIZAVEL_PENDENTE",
                "associated_location": None,
                "direction_data": None,
            },
            {
                "clue_id": "P-RURAL01-VULNERABILIDADE",
                "clue_type": "VULNERABILIDADE",
                "literal_description": (
                    "A condição clínica aumenta a vulnerabilidade, mas não constitui pista espacial."
                ),
                "evidence": deepcopy(known_high),
                "spatial_status": "NAO_ESPACIALIZAVEL",
                "associated_location": None,
                "direction_data": None,
            },
            {
                "clue_id": "P-RURAL01-VESTUARIO-EQUIPAMENTO",
                "clue_type": "OUTRA",
                "literal_description": (
                    "Vestia camisa camuflada, calça jeans, botina marrom e chapéu de palha; "
                    "carregava facão e garrafa térmica vermelha de dois litros."
                ),
                "evidence": deepcopy(known_high),
                "spatial_status": "NAO_ESPACIALIZAVEL",
                "associated_location": None,
                "direction_data": None,
            },
        ],
        "text_fields_sanitized": True,
        "ground_truth_absent": True,
        "freeze_metadata": None,
    }


def _integrated_evidence(
    evidence_id: str,
    created_at: str,
    *,
    nature: str = "RELATADO",
    confidence: str = "ALTA",
    source_type: str = "OPERADOR",
    source_code: str = "FICHA-RURAL01",
    observed_at: str | None = None,
    time_precision: str = "EXATA",
    authorized: bool = True,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "source_type": source_type,
        "source_code": source_code,
        "nature": nature,
        "confidence": confidence,
        "observed_at": observed_at or created_at,
        "time_precision": time_precision,
        "valid_until": None,
        "authorized_for_model": authorized,
    }


def _integrated_unavailable(evidence_id: str) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "source_type": "NAO_DISPONIVEL",
        "source_code": None,
        "nature": "NAO_DISPONIVEL",
        "confidence": "NAO_AVALIADA",
        "observed_at": None,
        "time_precision": "NAO_DISPONIVEL",
        "valid_until": None,
        "authorized_for_model": False,
    }


def _fact(
    fact_id: str,
    domain: str,
    value: str | int | float | bool | None,
    evidence: Mapping[str, Any],
    availability: str = "PRESENTE",
) -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "domain": domain,
        "availability": availability,
        "value": value,
        "evidence": deepcopy(dict(evidence)),
    }


def _urgency_observation(
    observation_id: str,
    domain: str,
    availability: str,
    significance: str,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "observation_id": observation_id,
        "domain": domain,
        "availability": availability,
        "operational_significance": significance,
        "evidence": deepcopy(dict(evidence)),
    }


def build_integrated_case_draft(
    created_at: str,
    profile_compiled_sha256: str,
    territorial_manifest_sha256: str,
    visual_manifest_sha256: str,
    sector_ids: Sequence[str],
) -> dict[str, Any]:
    point_time = _parse_time(POINT_AT)
    # O corte do caso inclui o congelamento da entrada PERFIL V3 (+2 s), sem
    # alterar os horários relatados das evidências de origem.
    assessment_at = _time_after(created_at, 2)
    assessment_time = _parse_time(assessment_at)
    elapsed_minutes = (assessment_time - point_time).total_seconds() / 60.0
    if elapsed_minutes < 840.0:
        raise ValueError("Tempo transcorrido incompatível com o máximo de deslocamento informado.")

    profile_evidence = lambda suffix, **kwargs: _integrated_evidence(
        f"E-RURAL01-{suffix}", created_at, **kwargs
    )
    unavailable_med = _integrated_unavailable("E-RURAL01-MEDICACAO-NA")
    unavailable_comm = _integrated_unavailable("E-RURAL01-COMUNICACAO-NA")
    det_unavailable = _integrated_unavailable("E-RURAL01-DET-NA")

    profile_facts = [
        _fact("F-RURAL01-IDADE", "FAIXA_ETARIA", "ADULTO_42_ANOS", profile_evidence("IDADE")),
        _fact("F-RURAL01-MOBILIDADE", "MOBILIDADE", "A_PE", profile_evidence("MOBILIDADE")),
        _fact(
            "F-RURAL01-COGNICAO",
            "COGNICAO_ORIENTACAO",
            "SEM_ALTERACAO_RELATADA; CONFUSAO_APENAS_COMO_RISCO_CLINICO_CONDICIONAL",
            profile_evidence("COGNICAO", confidence="MEDIA"),
        ),
        _fact(
            "F-RURAL01-CONDICAO-CLINICA",
            "CONDICAO_CLINICA",
            "DIABETES_TIPO_2; RISCO_DE_HIPOGLICEMIA_APOS_PERIODO_PROLONGADO_SEM_ALIMENTACAO",
            profile_evidence("CONDICAO-CLINICA"),
        ),
        _fact("F-RURAL01-MEDICACAO", "MEDICACAO", None, unavailable_med, "NAO_DISPONIVEL"),
        _fact(
            "F-RURAL01-EXPERIENCIA",
            "EXPERIENCIA_AMBIENTE",
            "EXPERIENCIA_NO_MATO",
            profile_evidence("EXPERIENCIA"),
        ),
        _fact(
            "F-RURAL01-FAMILIARIDADE",
            "FAMILIARIDADE_LOCAL",
            "CONHECE_A_TOPOGRAFIA_LOCAL",
            profile_evidence("FAMILIARIDADE"),
        ),
        _fact(
            "F-RURAL01-COMPORTAMENTO",
            "COMPORTAMENTO",
            "TENDE_A_SEGUIR_FEICOES_LINEARES; PODE_PERMANECER_PARADO_SE_LESIONADO",
            profile_evidence("COMPORTAMENTO", nature="INFERIDO", confidence="BAIXA"),
        ),
        _fact(
            "F-RURAL01-ATIVIDADE",
            "ATIVIDADE_HABITUAL",
            "VERIFICACAO_DE_CERCAS_APOS_DEIXAR_MOTOCICLETA_NA_PORTEIRA",
            profile_evidence("ATIVIDADE"),
        ),
        _fact(
            "F-RURAL01-DIRECAO-CONTEXTUAL",
            "OUTRO",
            "NORTE_PROVAVEL; HIPOTESE_CONTEXTUAL_NAO_OBSERVADA_E_SEM_AZIMUTE",
            profile_evidence("DIRECAO-CONTEXTUAL", nature="INFERIDO", confidence="BAIXA"),
        ),
        _fact(
            "F-RURAL01-PEGADAS",
            "OUTRO",
            "PEGADAS_COMPATIVEIS_COM_BOTINA_RELATADAS_PROXIMAS_A_CERCA_ROMPIDA; SEM_GEOMETRIA",
            profile_evidence("PEGADAS", confidence="MEDIA"),
        ),
        _fact(
            "F-RURAL01-VESTUARIO",
            "VESTUARIO",
            "CAMISA_CAMUFLADA_MANGA_LONGA; CALCA_JEANS; CHAPEU_DE_PALHA",
            profile_evidence("VESTUARIO"),
        ),
        _fact("F-RURAL01-CALCADO", "CALCADO", "BOTINA_DE_COURO_MARROM", profile_evidence("CALCADO")),
        _fact(
            "F-RURAL01-EQUIPAMENTO",
            "CARGA_EQUIPAMENTO",
            "FACAO; GARRAFA_TERMICA_VERMELHA_DE_2_LITROS; CONTEUDO_NAO_INFORMADO",
            profile_evidence("EQUIPAMENTO"),
        ),
    ]

    urgency = [
        _urgency_observation(
            "URG-RURAL01-TEMPO", "TEMPO", "PRESENTE", "CONTEXTUAL", profile_evidence("URG-TEMPO")
        ),
        _urgency_observation(
            "URG-RURAL01-CLINICA",
            "CONDICAO_CLINICA",
            "PRESENTE",
            "AUMENTA_VULNERABILIDADE",
            profile_evidence("CONDICAO-CLINICA"),
        ),
        _urgency_observation(
            "URG-RURAL01-COGNICAO",
            "COGNICAO_ORIENTACAO",
            "AUSENTE",
            "CONTEXTUAL",
            profile_evidence("COGNICAO", confidence="MEDIA"),
        ),
        _urgency_observation(
            "URG-RURAL01-MOBILIDADE",
            "MOBILIDADE",
            "PRESENTE",
            "CONTEXTUAL",
            profile_evidence("MOBILIDADE"),
        ),
        _urgency_observation(
            "URG-RURAL01-MEDICACAO",
            "MEDICACAO",
            "NAO_DISPONIVEL",
            "NAO_AVALIADA",
            unavailable_med,
        ),
        _urgency_observation(
            "URG-RURAL01-EXPOSICAO",
            "EXPOSICAO",
            "PRESENTE",
            "CONTEXTUAL",
            profile_evidence("URG-EXPOSICAO", confidence="MEDIA"),
        ),
        _urgency_observation(
            "URG-RURAL01-COMUNICACAO",
            "COMUNICACAO",
            "NAO_DISPONIVEL",
            "NAO_AVALIADA",
            unavailable_comm,
        ),
        _urgency_observation(
            "URG-RURAL01-SUPRIMENTOS",
            "SUPRIMENTOS",
            "NAO_DISPONIVEL",
            "NAO_AVALIADA",
            _integrated_unavailable("E-RURAL01-SUPRIMENTOS-NA"),
        ),
        _urgency_observation(
            "URG-RURAL01-VESTUARIO",
            "VESTUARIO_CALCADO",
            "PRESENTE",
            "CONTEXTUAL",
            profile_evidence("VESTUARIO"),
        ),
        _urgency_observation(
            "URG-RURAL01-PERIGO-AMBIENTAL",
            "PERIGO_AMBIENTAL",
            "PRESENTE",
            "CONTEXTUAL",
            profile_evidence("URG-PERIGO", confidence="MEDIA"),
        ),
    ]

    dimensions = sorted(
        {
            "VISIBILIDADE",
            "ACESSIBILIDADE",
            "COMPATIBILIDADE_RECURSO",
            "CONDICAO_AMBIENTAL",
            "ATUALIDADE_QUALIDADE",
        }
    )
    det_assessments = []
    for sector_id in sorted(sector_ids):
        for modality in ("BUSCA_TERRESTRE", "OBSERVACAO_AEREA_RGB"):
            det_assessments.append(
                {
                    "sector_id": sector_id,
                    "modality": modality,
                    "assessed_at": created_at,
                    "dimensions": [
                        {
                            "dimension": dimension,
                            "category": "INDETERMINADO",
                            "source_type": "NAO_DISPONIVEL",
                            "evidence_id": "E-RURAL01-DET-NA",
                        }
                        for dimension in dimensions
                    ],
                }
            )

    return {
        "protocol_version": "PROTOCOLO-INTEGRADO-PROSPECTIVO-v1.0",
        "scenario_id": SCENARIO_ID,
        "case_revision": 1,
        "parent_payload_sha256": None,
        "study_mode": "PROSPECTIVO_CEGO",
        "record_status": "RASCUNHO",
        "created_at": created_at,
        "operator_code": OPERATOR_CODE,
        "pseudonymized": True,
        "text_fields_sanitized": True,
        "blind_processing": True,
        "storage_segregated": True,
        "ground_truth_absent": True,
        "person_location_status": "DESCONHECIDA",
        "planning_point": {
            "point_id": "PT-RURAL01-INICIAL",
            "point_role": "PONTO_INICIAL_PLANEJAMENTO",
            "point_semantics": "REFERENCIA_DE_PLANEJAMENTO",
            "coordinate_source": "INFORMADO_PELA_FONTE",
            "latitude": POINT_LAT,
            "longitude": POINT_LON,
            "position_observed_at": POINT_AT,
            "current_presence_assertion": False,
            "horizontal_accuracy_m": None,
            "horizontal_accuracy_status": "NAO_DISPONIVEL",
            "horizontal_accuracy_source": None,
            "uncertainty_radius_m": SOURCE_RADIUS_M,
            "uncertainty_source": "INFORMADO_PELA_FONTE",
            "evidence": _integrated_evidence(
                "E-RURAL01-PONTO",
                created_at,
                source_type="REGISTRO",
                source_code="ERB-IPHONE-FICHA-RURAL01",
                observed_at=POINT_AT,
            ),
        },
        "search_context": {
            "assessment_at": assessment_at,
            "disappearance_at": POINT_AT,
            "elapsed_minutes": elapsed_minutes,
            "elapsed_precision": "EXATA",
            "environment_type": "RURAL",
            "travel_mode": "A_PE",
            "maximum_plausible_travel_minutes": 840.0,
            "environment_observations": [
                {
                    "observation_id": "ENV-RURAL01-DET-DADOS",
                    "domain": "ACESSO",
                    "availability": "NAO_DISPONIVEL",
                    "value": None,
                    "unit": None,
                    "evidence": det_unavailable,
                }
            ],
        },
        "profile_facts": profile_facts,
        "visual_evidence": [],
        "urgency_observations": urgency,
        "detectability_assessments": det_assessments,
        "source_artifacts": {
            "profile_v2_compiled_sha256": profile_compiled_sha256,
            "territorial_manifest_sha256": territorial_manifest_sha256,
            "spatial_review_manifest_sha256": None,
            # Vínculo de proveniência somente. Sem visual_evidence, capture_at,
            # footprint ou qualquer efeito em LOC/DET nesta execução.
            "visual_manifest_sha256": visual_manifest_sha256,
            "loc_result_sha256": None,
        },
        "search_event_hashes": [],
        "freeze_metadata": None,
    }


def _load_territorial_sectors(
    ranking_path: Path, polygons_path: Path
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str, str]:
    with ranking_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        raise ValueError("O ranking territorial precisa conter ao menos dois setores.")
    required = {
        "scenario_id",
        "candidate_id",
        "sector_id",
        "score_base",
        "rank_base_within_buffer",
        "azimuth_start_deg",
        "azimuth_end_deg",
    }
    missing = sorted(required - set(rows[0]))
    if missing:
        raise ValueError(f"Colunas ausentes no ranking territorial: {missing}")
    scenario_ids = {row["scenario_id"] for row in rows}
    candidate_ids = {row["candidate_id"] for row in rows}
    if scenario_ids != {SCENARIO_ID} or len(candidate_ids) != 1:
        raise ValueError(
            f"Ranking incompatível: scenario_id={sorted(scenario_ids)}, candidate_id={sorted(candidate_ids)}"
        )

    geojson = json.loads(polygons_path.read_text(encoding="utf-8"))
    by_sector: dict[str, list[list[float]]] = {}
    for feature in geojson.get("features", []):
        props = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        sector_id = props.get("sector_id")
        if not isinstance(sector_id, str) or geometry.get("type") != "Polygon":
            continue
        rings = geometry.get("coordinates")
        if not isinstance(rings, list) or not rings or not isinstance(rings[0], list):
            continue
        by_sector[sector_id] = [[float(pair[0]), float(pair[1])] for pair in rings[0]]

    sectors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        sector_id = row["sector_id"]
        if sector_id in seen:
            raise ValueError(f"Setor duplicado no ranking: {sector_id}")
        seen.add(sector_id)
        polygon = by_sector.get(sector_id)
        if polygon is None:
            raise ValueError(f"Polígono ausente para o setor {sector_id}.")
        if polygon[0] != polygon[-1]:
            polygon.append(deepcopy(polygon[0]))
        score = float(row["score_base"])
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError(f"score_base inválido em {sector_id}: {score}")
        sectors.append(
            {
                "sector_id": sector_id,
                "territorial_score": score,
                "bearing_start_deg": float(row["azimuth_start_deg"]),
                "bearing_end_deg": float(row["azimuth_end_deg"]),
                "polygon": polygon,
            }
        )
    if set(by_sector) != seen:
        extras = sorted(set(by_sector) - seen)
        raise ValueError(f"GeoJSON contém setores sem linha correspondente: {extras}")
    return sectors, rows, SCENARIO_ID, next(iter(candidate_ids))


def _write_profile_ranking_csv(
    path: Path,
    original_rows: Sequence[Mapping[str, str]],
    profile_result: Mapping[str, Any],
) -> None:
    by_sector = {row["sector_id"]: row for row in profile_result["operational_rows"]}
    fields = list(original_rows[0].keys()) + [
        "perfil_v3_territorial_score",
        "perfil_v3_territorial_rank",
        "perfil_v3_score",
        "perfil_v3_rank",
        "perfil_v3_delta",
        "perfil_v3_effect_applied",
        "perfil_v3_status",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for original in original_rows:
            row = dict(original)
            profile = by_sector[row["sector_id"]]
            row.update(
                {
                    "perfil_v3_territorial_score": profile["territorial_score"],
                    "perfil_v3_territorial_rank": profile["territorial_rank"],
                    "perfil_v3_score": profile["profile_score"],
                    "perfil_v3_rank": profile["profile_rank"],
                    "perfil_v3_delta": profile["profile_delta"],
                    "perfil_v3_effect_applied": profile_result["operational_effect_applied"],
                    "perfil_v3_status": profile_result["operational_status"],
                }
            )
            writer.writerow(row)


def _top3(
    original_rows: Sequence[Mapping[str, str]], profile_result: Mapping[str, Any]
) -> list[dict[str, Any]]:
    original_by_sector = {row["sector_id"]: row for row in original_rows}
    ordered = sorted(
        profile_result["operational_rows"],
        key=lambda row: (int(row["profile_rank"]), row["sector_id"]),
    )[:3]
    result: list[dict[str, Any]] = []
    for position, row in enumerate(ordered, start=1):
        source = original_by_sector[row["sector_id"]]
        result.append(
            {
                "area_label": f"AP{position}",
                "presentation_order": position,
                "scenario_id": SCENARIO_ID,
                "candidate_id": profile_result["candidate_id"],
                "sector_id": row["sector_id"],
                "territorial_rank": row["territorial_rank"],
                "profile_rank": row["profile_rank"],
                "territorial_score": row["territorial_score"],
                "profile_score": row["profile_score"],
                "profile_delta": row["profile_delta"],
                "ring_id": source.get("ring_id"),
                "direction": source.get("direction"),
                "representative_lat": float(source["representative_lat"])
                if source.get("representative_lat")
                else None,
                "representative_lon": float(source["representative_lon"])
                if source.get("representative_lon")
                else None,
                "interpretation": "AREA_ANALITICA_PARA_REVISAO_HUMANA",
            }
        )
    return result


def build_package(
    ranking_path: Path,
    polygons_path: Path,
    visual_manifest_path: Path,
    output_dir: Path,
    created_at: str,
) -> dict[str, Any]:
    created_at = _parse_time(created_at).isoformat(timespec="seconds")
    if _parse_time(created_at) <= _parse_time(POINT_AT):
        raise ValueError("created_at deve ser posterior ao horário do ponto.")
    if not ranking_path.is_file():
        raise FileNotFoundError(f"Ranking territorial não encontrado: {ranking_path}")
    if not polygons_path.is_file():
        raise FileNotFoundError(f"GeoJSON de setores não encontrado: {polygons_path}")
    if not visual_manifest_path.is_file():
        raise FileNotFoundError(
            f"Manifesto de metadados visuais não encontrado: {visual_manifest_path}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    profile_v2 = _load_module("rural01_profile_v2", PROFILE_V2_PATH)
    integrated = _load_module("rural01_integrated_protocol", INTEGRATED_PATH)
    # O protocolo integrado confere a trava criptográfica antes de carregar o
    # motor PERFIL V3; evita uma segunda importação independente do mesmo motor.
    profile_v3 = integrated._load_profile_engine_module()

    sectors, ranking_rows, scenario_id, candidate_id = _load_territorial_sectors(
        ranking_path, polygons_path
    )
    if scenario_id != SCENARIO_ID:
        raise ValueError("Cenário territorial incompatível.")

    v2_draft_path = output_dir / "perfil_v2_rural01_rascunho.json"
    v2_frozen_path = output_dir / "perfil_v2_rural01_congelado.json"
    v2_compiled_path = output_dir / "perfil_v2_rural01_compilado.json"
    v2_draft = build_profile_v2_draft(created_at)
    profile_v2.validate_input(v2_draft)
    _write_json(v2_draft_path, v2_draft)
    v2_frozen = profile_v2.prepare_frozen_payload(v2_draft, _time_after(created_at, 1))
    _write_json(v2_frozen_path, v2_frozen)
    v2_compiled = profile_v2.compile_profile(v2_frozen)
    _write_json(v2_compiled_path, v2_compiled)
    if v2_compiled["summary"]["spatialized_hypothesis_count"] != 0:
        raise AssertionError("O PERFIL V2 não pode espacializar as pistas contextuais deste caso.")

    territorial_manifest_path = output_dir / "manifesto_territorial_para_perfil_rural01.json"
    territorial_manifest = {
        "manifest_version": "RURAL01-TERRITORIAL-BINDING-v1",
        "scenario_id": SCENARIO_ID,
        "candidate_id": candidate_id,
        "sector_count": len(sectors),
        "ranking_path": _display_path(ranking_path),
        "ranking_sha256": _sha256(ranking_path),
        "polygons_path": _display_path(polygons_path),
        "polygons_sha256": _sha256(polygons_path),
        "ranking_field": "score_base",
        "quantitative_profile_effect_authorized": False,
        "reason": "Nenhuma pista espacial quantitativa elegível foi formalizada.",
    }
    _write_json(territorial_manifest_path, territorial_manifest)

    case_draft = build_integrated_case_draft(
        created_at,
        _sha256(v2_compiled_path),
        _sha256(territorial_manifest_path),
        _sha256(visual_manifest_path),
        [sector["sector_id"] for sector in sectors],
    )
    integrated.validate_case(case_draft)
    case_draft_path = output_dir / "protocolo_integrado_rural01_rascunho.json"

    v3_draft = {
        "protocol_version": "PERFIL-V3-QUANT-v1.0",
        "scenario_id": SCENARIO_ID,
        "candidate_id": candidate_id,
        "record_status": "RASCUNHO",
        "created_at": created_at,
        "ground_truth_absent": True,
        "source_loc_input_sha256": integrated.calculate_loc_input_sha256(case_draft),
        "source_case_revision": 1,
        "source_profile_compiled_sha256": _sha256(v2_compiled_path),
        "source_territorial_manifest_sha256": _sha256(territorial_manifest_path),
        "source_spatial_review_sha256": None,
        "sectors": sectors,
        "hypotheses": [],
        "freeze_metadata": None,
    }
    v3_draft_path = output_dir / "perfil_v3_rural01_entrada_rascunho.json"
    v3_frozen_path = output_dir / "perfil_v3_rural01_entrada_congelada.json"
    v3_result_path = output_dir / "perfil_v3_rural01_resultado.json"
    _write_json(v3_draft_path, v3_draft)
    v3_frozen = profile_v3.prepare_frozen_input(v3_draft, _time_after(created_at, 2))
    _write_json(v3_frozen_path, v3_frozen)
    v3_result = profile_v3.rank_profile(v3_frozen)
    _write_json(v3_result_path, v3_result)
    if not v3_result["abstained"] or v3_result["operational_effect_applied"]:
        raise AssertionError("PERFIL V3 deveria abster-se sem pista espacial elegível.")
    for row in v3_result["operational_rows"]:
        if (
            row["profile_score"] != row["territorial_score"]
            or row["profile_delta"] != 0.0
            or row["profile_rank"] != row["territorial_rank"]
        ):
            raise AssertionError(
                f"Abstenção não preservou exatamente o ranking territorial em {row['sector_id']}."
            )

    loc_result_path = output_dir / "loc_result_v1.json"
    loc_result = integrated.build_loc_result_envelope(
        case_draft,
        [
            {
                "candidate_id": candidate_id,
                "profile_input": v3_frozen,
                "profile_result": v3_result,
            }
        ],
    )
    _write_json(loc_result_path, loc_result)
    case_draft["source_artifacts"]["loc_result_sha256"] = _sha256(loc_result_path)
    # O hash LOC não integra a projeção de entrada LOC; portanto este vínculo
    # posterior não altera o contexto que produziu a execução PERFIL V3.
    integrated.validate_case(case_draft)
    _write_json(case_draft_path, case_draft)

    case_frozen = integrated.prepare_frozen_case(case_draft, _time_after(created_at, 3))
    case_frozen_path = output_dir / "protocolo_integrado_rural01_congelado.json"
    _write_json(case_frozen_path, case_frozen)
    rules = json.loads(integrated.DEFAULT_RULES_PATH.read_text(encoding="utf-8"))
    artifact_map, artifact_root = _artifact_map(
        {
            "profile_v2_compiled_sha256": v2_compiled_path,
            "territorial_manifest_sha256": territorial_manifest_path,
            "visual_manifest_sha256": visual_manifest_path,
            "loc_result_sha256": loc_result_path,
        }
    )
    integrated_result = integrated.compile_case(
        case_frozen,
        rules,
        artifact_map=artifact_map,
        artifact_root=artifact_root,
    )
    integrated_result_path = output_dir / "resultado_urg_det_rural01.json"
    _write_json(integrated_result_path, integrated_result)
    if integrated_result["urgency"]["status"] != "REVISAO_PRIORITARIA":
        raise AssertionError(
            f"URG inesperado: {integrated_result['urgency']['status']}"
        )
    det_statuses = {
        row["status"] for row in integrated_result["detectability"]["per_sector_modality"]
    }
    if det_statuses != {"REVISAR"}:
        raise AssertionError(f"DET deveria permanecer em revisão: {sorted(det_statuses)}")
    location = integrated_result["location"]
    if location["status"] != "RESULTADO_EXTERNO_CONTRATO_VALIDADO_CEGAMENTO_DECLARADO":
        raise AssertionError(f"LOC integrado inesperado: {location['status']}")
    if set(location["valid_sector_ids"]) != {
        sector["sector_id"] for sector in sectors
    }:
        raise AssertionError("LOC integrado não contém exatamente os setores do ranking.")

    ranking_profile_path = output_dir / "ranking_perfil_v3_rural01.csv"
    _write_profile_ranking_csv(ranking_profile_path, ranking_rows, v3_result)
    top3 = _top3(ranking_rows, v3_result)
    top3_path = output_dir / "top3_perfil_v3_rural01.json"
    _write_json(top3_path, top3)

    report_path = output_dir / "relatorio_perfil_urg_det_rural01.json"
    report = {
        "scenario_id": SCENARIO_ID,
        "created_at": created_at,
        "sector_count": len(sectors),
        "profile_v2": {
            "spatialized_hypothesis_count": v2_compiled["summary"]["spatialized_hypothesis_count"],
            "non_spatializable_item_count": v2_compiled["summary"]["non_spatializable_item_count"],
            "ranking_produced": v2_compiled["summary"]["ranking_produced"],
        },
        "profile_v3": {
            "abstained": v3_result["abstained"],
            "abstention_reason": v3_result["abstention_reason"],
            "operational_effect_applied": v3_result["operational_effect_applied"],
            "operational_status": v3_result["operational_status"],
            "territorial_ranking_preserved_exactly": True,
            "north_hypothesis_weighted": False,
        },
        "urg": {
            "status": integrated_result["urgency"]["status"],
            "triggered_rules": integrated_result["urgency"]["triggered_rules"],
            "meaning": integrated_result["urgency"]["meaning"],
            "affects_loc": integrated_result["urgency"]["affects_loc"],
        },
        "det": {
            "input_category": "INDETERMINADO",
            "compiled_statuses": sorted(det_statuses),
            "affects_loc": integrated_result["detectability"]["affects_loc"],
        },
        "loc": {
            "status": location["status"],
            "external_content_validation": location["external_content_validation"],
            "valid_sector_count": len(location["valid_sector_ids"]),
            "valid_candidate_ids": location["valid_candidate_ids"],
            "ranking_preserved_exactly": True,
        },
        "visual_manifest_linkage": {
            "path": _display_path(visual_manifest_path),
            "sha256": _sha256(visual_manifest_path),
            "reference_only": True,
            "visual_evidence_count": 0,
            "capture_at_invented": False,
            "footprint_invented": False,
            "affects_loc": False,
            "affects_det": False,
        },
        "data_boundaries": {
            "medication_timing_available": False,
            "last_meal_time_available": False,
            "direction_observed_authorized": False,
            "profile_can_change_location_ranking": False,
        },
        "top3": top3,
    }
    _write_json(report_path, report)

    artifact_paths = [
        v2_draft_path,
        v2_frozen_path,
        v2_compiled_path,
        territorial_manifest_path,
        case_draft_path,
        case_frozen_path,
        v3_draft_path,
        v3_frozen_path,
        v3_result_path,
        loc_result_path,
        integrated_result_path,
        ranking_profile_path,
        top3_path,
        report_path,
    ]
    manifest_path = output_dir / "manifesto_perfil_urg_det_rural01.json"
    manifest = {
        "manifest_version": "RURAL01-PERFIL-URG-DET-v1",
        "scenario_id": SCENARIO_ID,
        "created_at": created_at,
        "status": "CONGELADO_DIAGNOSTICO_SUJEITO_A_REVISAO_HUMANA",
        "files": [
            {
                "path": _display_path(path),
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in artifact_paths
        ],
        "checks": {
            "profile_v3_abstained": True,
            "territorial_ranking_preserved_exactly": True,
            "urgency_status": "REVISAO_PRIORITARIA",
            "detectability_status": "REVISAR",
            "loc_contract_validated": True,
            "loc_valid_sector_count": len(sectors),
            "directional_preference_applied": False,
            "medication_or_meal_timing_invented": False,
            "visual_manifest_reference_only": True,
            "visual_capture_or_footprint_invented": False,
        },
        "source_bindings": {
            "visual_manifest_path": _display_path(visual_manifest_path),
            "visual_manifest_sha256": _sha256(visual_manifest_path),
            "loc_result_path": _display_path(loc_result_path),
            "loc_result_sha256": _sha256(loc_result_path),
        },
    }
    _write_json(manifest_path, manifest)
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ranking", type=Path, default=DEFAULT_RANKING)
    parser.add_argument("--sectors-geojson", type=Path, default=DEFAULT_POLYGONS)
    parser.add_argument(
        "--visual-manifest", type=Path, default=DEFAULT_VISUAL_MANIFEST
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--created-at",
        required=True,
        help="Instante RFC 3339 de registro/congelamento, com fuso horário.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = build_package(
        args.ranking.resolve(),
        args.sectors_geojson.resolve(),
        args.visual_manifest.resolve(),
        args.output_dir.resolve(),
        args.created_at,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
