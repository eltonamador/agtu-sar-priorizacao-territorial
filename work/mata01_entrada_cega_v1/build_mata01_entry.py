#!/usr/bin/env python3
"""Constrói e audita a entrada cega do cenário MATA-01.

O script preserva os quatro arquivos autorizados, registra somente metadados
necessários e materializa duas revisões temporais encadeadas. Não recebe nem
procura posição de alvo e não converte o raio informado em resultado do motor
de buffer adaptativo.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "work/mata01_metadados_mzg1_v1/originais_preservados"
METADATA_REPORT = ROOT / "work/mata01_metadados_mzg1_v1/RELATORIO_METADADOS_MZG1_v1.md"
METADATA_RAW = ROOT / "work/mata01_metadados_mzg1_v1/metadados_imageio.json"
OUT = ROOT / "outputs/campo_mata01/entrada_cega_v1"
RESERVED = ROOT / "outputs/campo_mata01/reservado_originais"

SCENARIO_ID = "MATA-01"
POINT_AT = "2026-10-21T14:20:00-03:00"
REV1_AT = "2026-10-22T16:40:00-03:00"
REV2_AT = "2026-10-23T15:41:00-03:00"
POINT_LAT = -0.172222
POINT_LON = -51.430278
SOURCE_RADIUS_M = 5000.0

FILES = {
    "MZG1Solo_0442.HEIC": {
        "sha256": "1e90f923ba1316d7b74a6ec6980294c0a0c0701c9e253b80494afd4cce1e42c5",
        "bytes": 4319656,
        "media_type": "image/heic",
        "width_px": 5712,
        "height_px": 4284,
        "device": "Apple iPhone 16",
        "capture_at": "2026-10-22T16:39:08.399-03:00",
        "camera_position": {
            "latitude": -0.172270,
            "longitude": -51.430175,
            "gps_altitude_m": 9.338,
            "horizontal_error_m": 4.749,
        },
        "view": {
            "type": "SOLO_DIRECIONAL",
            "azimuth_deg_true": 81.644,
            "gimbal_pitch_deg": None,
        },
        "spatial_link_quality": "CONTEXTUAL_INSUFICIENTE",
        "objective_annotation": (
            "Vista a partir da borda da vegetação para área herbácea aberta; "
            "a vegetação em primeiro plano reduz a visibilidade próxima ao solo."
        ),
    },
    "MZG1Drone261022162156_0001_V.JPG": {
        "sha256": "1e24427afd174941309870933fd12cb99146aa7363dd87545e2a8467b37fc200",
        "bytes": 9707520,
        "media_type": "image/jpeg",
        "width_px": 4000,
        "height_px": 3000,
        "device": "DJI M3T WideCamera RGB",
        "capture_at": "2026-10-22T16:21:56-03:00",
        "camera_position": {
            "latitude": -0.172111149,
            "longitude": -51.430561242,
            "absolute_altitude_raw_m": 195.865,
            "relative_altitude_raw_m": 199.953,
            "horizontal_error_m": None,
        },
        "view": {
            "type": "AEREA_NADIRAL",
            "azimuth_deg_true": 4.9,
            "gimbal_pitch_deg": -89.9,
        },
        "spatial_link_quality": "APROXIMADO_METADADOS",
        "objective_annotation": (
            "Mosaico de dossel fechado e área aberta; uma edificação e uma via "
            "não pavimentada são discerníveis."
        ),
    },
    "MZG1Drone261022162223_0006_V.JPG": {
        "sha256": "d9ac19ac9526022360696d49ccecdba736924a29b276b84bc4fd16ff636ca44d",
        "bytes": 5214208,
        "media_type": "image/jpeg",
        "width_px": 4000,
        "height_px": 3000,
        "device": "DJI M3T WideCamera RGB",
        "capture_at": "2026-10-22T16:22:23-03:00",
        "camera_position": {
            "latitude": -0.172110246,
            "longitude": -51.430563450,
            "absolute_altitude_raw_m": 195.790,
            "relative_altitude_raw_m": 199.879,
            "horizontal_error_m": None,
        },
        "view": {
            "type": "AEREA_OBLIQUA",
            "azimuth_deg_true": 269.2,
            "gimbal_pitch_deg": -19.1,
        },
        "spatial_link_quality": "CONTEXTUAL_INSUFICIENTE",
        "objective_annotation": (
            "Área aberta sinuosa entre blocos de vegetação; superfícies claras e "
            "escuras são visualmente compatíveis com umidade ou água superficial, "
            "sem comprovação de profundidade ou passabilidade."
        ),
    },
    "MZG1Drone261022162239_0011_V.JPG": {
        "sha256": "64eb991ac17f4376638c90d5152b8e53417ed951b6a845dd8ef671dca71fe26e",
        "bytes": 7131136,
        "media_type": "image/jpeg",
        "width_px": 4000,
        "height_px": 3000,
        "device": "DJI M3T WideCamera RGB",
        "capture_at": "2026-10-22T16:22:39-03:00",
        "camera_position": {
            "latitude": -0.172112206,
            "longitude": -51.430561712,
            "absolute_altitude_raw_m": 195.660,
            "relative_altitude_raw_m": 199.748,
            "horizontal_error_m": None,
        },
        "view": {
            "type": "AEREA_OBLIQUA",
            "azimuth_deg_true": 131.2,
            "gimbal_pitch_deg": -19.1,
        },
        "spatial_link_quality": "CONTEXTUAL_INSUFICIENTE",
        "objective_annotation": (
            "Floresta contínua intercalada por aberturas alongadas; a imagem não "
            "permite classificar essas feições como trilha, drenagem ou área transitável."
        ),
    },
}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def elapsed_minutes(start: str, end: str) -> float:
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60.0


def build_revision(revision: int, evaluated_at: str, parent_sha256: str | None) -> dict[str, Any]:
    return {
        "protocol_id": "MATA01-CEGO-ENTRADA-v1.0",
        "scenario_id": SCENARIO_ID,
        "case_revision": revision,
        "mode": "PROSPECTIVO_CEGO",
        "record_status": "CONGELADO",
        "evaluated_at": evaluated_at,
        "parent_payload_sha256": parent_sha256,
        "ground_truth_absent": True,
        "planning_point": {
            "point_id": "MATA-01-E0",
            "point_type": "PONTO_INICIAL_PLANEJAMENTO",
            "semantic_role": "REFERENCIA_DE_PLANEJAMENTO",
            "latitude": POINT_LAT,
            "longitude": POINT_LON,
            "reference_event_at": POINT_AT,
            "coordinate_capture_at": "2026-10-22T16:39:08.399-03:00",
            "coordinate_source": "REGISTRO_OPERACIONAL_RECONSTRUIDO_COM_BUSSOLA_IPHONE",
            "horizontal_accuracy_m": None,
            "current_presence_assertion": False,
            "note": (
                "A coordenada foi registrada no dia seguinte ao evento e não é tratada como "
                "observação contemporânea da pessoa no local."
            ),
        },
        "spatial_domain": {
            "uncertainty_radius_m": SOURCE_RADIUS_M,
            "radius_origin": "INFORMADO_PELO_PESQUISADOR",
            "radius_method": "RAIO_DIRETO_SEM_BUFFER_ADAPTATIVO",
            "radius_status": "REVISAR",
            "adaptive_buffer_engine_used": False,
            "detection_quality": None,
            "environment_type": "MISTO",
            "area_km2": round(math.pi * (SOURCE_RADIUS_M / 1000.0) ** 2, 6),
        },
        "temporal_context": {
            "elapsed_minutes": elapsed_minutes(POINT_AT, evaluated_at),
            "elapsed_status": "CALCULADO",
            "automatic_radius_expansion_from_elapsed_time": False,
        },
        "person_profile": {
            "age_years": 42,
            "occupation_context": "AGRICULTOR",
            "physical_condition": "BOM_PREPARO_FISICO_RELATADO",
            "area_familiarity": "ALTA_RELATADA",
            "travel_mode": "A_PE",
            "maximum_plausible_travel_minutes": None,
            "clothing_and_equipment": [
                "camisa laranja",
                "calça de trabalho",
                "botas de borracha",
                "boné",
                "terçado",
                "garrafa térmica",
            ],
        },
        "authorized_spatial_clues": [
            {
                "clue_id": "MATA01-P1-MARCAS-NORTE",
                "description": "Marcas de botas relatadas saindo do roçado em direção ao Norte.",
                "family": "DIRECAO",
                "nature": "RELATADO",
                "confidence": "MEDIA",
                "origin_candidate_id": "MATA-01-E0",
                "azimuth_deg": 0.0,
                "tolerance_deg": 22.5,
                "eligible_for_profile_v3": True,
            }
        ],
        "contextual_clues_without_direct_loc_weight": [
            "Ferramentas deixadas na roça e almoço não consumido.",
            "Relato de que a pessoa conhecia trilhas, bordas de mata e cursos d'água.",
            "Costume de buscar água em igarapé não georreferenciado.",
            "Fumaça distante sem posição nem vínculo comprovado com o desaparecimento.",
            "Vestuário laranja afeta detectabilidade, não plausibilidade espacial.",
        ],
        "urgency_context": {
            "water_supply_status": "PROVAVELMENTE_ESGOTADO_SEGUNDO_CENARIO",
            "fatigue_and_dehydration_concern": "CRESCENTE",
            "loc_effect": "NENHUM",
            "requires_human_review": True,
        },
        "image_set": {
            "manifest_file": "manifesto_metadados_visuais.json",
            "target_visible": False,
            "incidental_people_present": None,
            "numeric_model_input": False,
            "role": "EVIDENCIA_CONTEXTUAL_PARA_REVISAO_DE_DETECTABILIDADE",
        },
        "revision_effect": (
            "LOC_TERRITORIAL_E_PERFIL" if revision == 1 else "SEM_NOVA_PISTA_ESPACIAL_LOC_INALTERADO_ATUALIZA_URG_E_ATUALIDADE"
        ),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    RESERVED.mkdir(parents=True, exist_ok=True)
    manifest_files: list[dict[str, Any]] = []
    for name, declared in FILES.items():
        source = SOURCE_DIR / name
        target = RESERVED / name
        if not source.exists():
            raise FileNotFoundError(source)
        if file_hash(source) != declared["sha256"] or source.stat().st_size != declared["bytes"]:
            raise RuntimeError(f"Integridade divergente no arquivo {name}")
        if not target.exists() or file_hash(target) != declared["sha256"]:
            shutil.copy2(source, target)
        if file_hash(target) != declared["sha256"]:
            raise RuntimeError(f"Falha de preservação no arquivo {name}")
        manifest_files.append(
            {
                "file_id": name,
                "path": f"outputs/campo_mata01/reservado_originais/{name}",
                "sha256": declared["sha256"],
                "bytes": declared["bytes"],
            }
        )

    visual_records = []
    for name, data in FILES.items():
        record = {"file_id": name, **data}
        record["target_visible"] = False
        record["incidental_people_present"] = None
        record["numeric_model_input"] = False
        record["altitude_use_restriction"] = (
            "Metadado bruto; não interpretar como elevação do terreno ou altura AGL."
            if name.endswith(".JPG")
            else "Altitude GPS da posição da câmera; não representa a pessoa ou o terreno inteiro."
        )
        visual_records.append(record)

    visual_manifest = {
        "protocol_id": "MATA01-VISUAL-MANIFEST-v1.0",
        "scenario_id": SCENARIO_ID,
        "ground_truth_absent": True,
        "source_files_authorized": 4,
        "computer_vision_used": False,
        "thermal_imagery_used": False,
        "privacy_review_status": "PENDENTE_CONFERENCIA_HUMANA",
        "records": visual_records,
        "global_caveats": [
            "As coordenadas das fotos identificam a câmera ou a aeronave, não uma pessoa ou feição observada.",
            "A série aérea cobre 43 segundos e não representa todo o domínio circular de 5 km.",
            "Fotografia RGB do dossel não comprova transitabilidade do sub-bosque.",
            "Nenhuma figura humana é discernível nas imagens; isso não comprova ausência no terreno.",
            "O horário operacional aproximado de 16h28 foi substituído, para estes arquivos, pelos horários individuais dos metadados.",
        ],
    }
    write_json(OUT / "manifesto_metadados_visuais.json", visual_manifest)
    write_json(
        OUT / "manifesto_sha256_conjunto_mata01.json",
        {
            "scenario_id": SCENARIO_ID,
            "ground_truth_absent": True,
            "files": manifest_files,
            "metadata_report": {
                "path": "work/mata01_metadados_mzg1_v1/RELATORIO_METADADOS_MZG1_v1.md",
                "sha256": file_hash(METADATA_REPORT),
            },
            "metadata_raw": {
                "path": "work/mata01_metadados_mzg1_v1/metadados_imageio.json",
                "sha256": file_hash(METADATA_RAW),
            },
        },
    )

    revision1 = build_revision(1, REV1_AT, None)
    revision1_sha = canonical_hash(revision1)
    revision1["payload_sha256"] = revision1_sha
    write_json(OUT / "registro_cenario_mata01_revisao1.json", revision1)

    revision2 = build_revision(2, REV2_AT, revision1_sha)
    revision2_sha = canonical_hash(revision2)
    revision2["payload_sha256"] = revision2_sha
    write_json(OUT / "registro_cenario_mata01_revisao2.json", revision2)

    checks = {
        "four_authorized_files_preserved": len(manifest_files) == 4,
        "all_hashes_match": all(file_hash(RESERVED / row["file_id"]) == row["sha256"] for row in manifest_files),
        "revision_chain_valid": revision2["parent_payload_sha256"] == revision1_sha,
        "point_is_planning_reference": revision1["planning_point"]["point_type"] == "PONTO_INICIAL_PLANEJAMENTO",
        "current_presence_not_asserted": revision1["planning_point"]["current_presence_assertion"] is False,
        "source_radius_is_5000_m": revision1["spatial_domain"]["uncertainty_radius_m"] == 5000.0,
        "adaptive_buffer_not_used": revision1["spatial_domain"]["adaptive_buffer_engine_used"] is False,
        "detection_quality_remains_missing": revision1["spatial_domain"]["detection_quality"] is None,
        "no_automatic_time_expansion": revision2["temporal_context"]["automatic_radius_expansion_from_elapsed_time"] is False,
        "revision1_elapsed_is_1580_min": revision1["temporal_context"]["elapsed_minutes"] == 1580.0,
        "revision2_elapsed_is_2961_min": revision2["temporal_context"]["elapsed_minutes"] == 2961.0,
        "profile_direction_is_conservative": revision1["authorized_spatial_clues"][0]["confidence"] == "MEDIA",
        "imagery_not_numeric_loc_input": visual_manifest["computer_vision_used"] is False and all(r["numeric_model_input"] is False for r in visual_records),
    }
    qa = {
        "protocol_id": "MATA01-CEGO-ENTRADA-v1.0",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "passed": sum(bool(value) for value in checks.values()),
        "total": len(checks),
        "ground_truth_absent": True,
    }
    write_json(OUT / "relatorio_qa_entrada_mata01.json", qa)
    if qa["status"] != "PASS":
        raise RuntimeError("Falha no QA da entrada MATA-01")
    print(json.dumps(qa, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
