from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import integrated_protocol as module


PROFILE_SPEC = importlib.util.spec_from_file_location(
    "integrated_protocol_profile_ranker", module.LOC_ENGINE_PATH
)
if PROFILE_SPEC is None or PROFILE_SPEC.loader is None:
    raise RuntimeError("Falha ao carregar o motor PERFIL V3 usado pelo contrato LOC.")
PROFILE_MODULE = importlib.util.module_from_spec(PROFILE_SPEC)
sys.modules[PROFILE_SPEC.name] = PROFILE_MODULE
PROFILE_SPEC.loader.exec_module(PROFILE_MODULE)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def evidence(
    evidence_id: str,
    *,
    authorized: bool = True,
    observed_at: str | None = "2026-10-21T08:00:00-03:00",
    valid_until: str | None = None,
    nature: str = "OBSERVADO",
) -> dict:
    if nature == "NAO_DISPONIVEL":
        return {
            "evidence_id": evidence_id,
            "source_type": "NAO_DISPONIVEL",
            "source_code": None,
            "nature": nature,
            "confidence": "NAO_AVALIADA",
            "observed_at": None,
            "time_precision": "NAO_DISPONIVEL",
            "valid_until": None,
            "authorized_for_model": False,
        }
    return {
        "evidence_id": evidence_id,
        "source_type": "OPERADOR",
        "source_code": "OP-01",
        "nature": nature,
        "confidence": "ALTA",
        "observed_at": observed_at,
        "time_precision": "EXATA",
        "valid_until": valid_until,
        "authorized_for_model": authorized,
    }


def urgency_obs(index: int, domain: str, availability: str = "AUSENTE", significance: str = "CONTEXTUAL") -> dict:
    return {
        "observation_id": f"URG-{index:02d}",
        "domain": domain,
        "availability": availability,
        "operational_significance": significance,
        "evidence": evidence(f"E-URG-{index:02d}"),
    }


def draft_case() -> dict:
    critical = [
        "TEMPO", "CONDICAO_CLINICA", "COGNICAO_ORIENTACAO", "MOBILIDADE",
        "MEDICACAO", "EXPOSICAO", "COMUNICACAO",
    ]
    return {
        "protocol_version": module.PROTOCOL_VERSION,
        "scenario_id": "TESTE-01",
        "case_revision": 1,
        "parent_payload_sha256": None,
        "study_mode": "PROSPECTIVO_CEGO",
        "record_status": "RASCUNHO",
        "created_at": "2026-10-21T08:00:00-03:00",
        "operator_code": "OP-01",
        "pseudonymized": True,
        "text_fields_sanitized": True,
        "blind_processing": True,
        "storage_segregated": True,
        "ground_truth_absent": True,
        "person_location_status": "DESCONHECIDA",
        "planning_point": {
            "point_id": "PT-001",
            "point_role": "PONTO_INICIAL_PLANEJAMENTO",
            "point_semantics": "REFERENCIA_DE_PLANEJAMENTO",
            "coordinate_source": "INFORMADO_PELA_FONTE",
            "latitude": 0.016,
            "longitude": -51.068,
            "position_observed_at": "2026-10-21T08:00:00-03:00",
            "current_presence_assertion": False,
            "horizontal_accuracy_m": None,
            "horizontal_accuracy_status": "NAO_DISPONIVEL",
            "horizontal_accuracy_source": None,
            "uncertainty_radius_m": 2500.0,
            "uncertainty_source": "INFORMADO_PELA_FONTE",
            "evidence": evidence("E-POINT-01"),
        },
        "search_context": {
            "assessment_at": "2026-10-21T09:00:00-03:00",
            "disappearance_at": "2026-10-21T08:00:00-03:00",
            "elapsed_minutes": 60.0,
            "elapsed_precision": "EXATA",
            "environment_type": "URBANO",
            "travel_mode": "A_PE",
            "maximum_plausible_travel_minutes": 60.0,
            "environment_observations": [
                {
                    "observation_id": "ENV-01",
                    "domain": "CLIMA",
                    "availability": "PRESENTE",
                    "value": "SECO",
                    "unit": None,
                    "evidence": evidence("E-ENV-01"),
                }
            ],
        },
        "profile_facts": [
            {
                "fact_id": "FACT-01",
                "domain": "MOBILIDADE",
                "availability": "PRESENTE",
                "value": "A_PE",
                "evidence": evidence("E-FACT-01", nature="RELATADO"),
            }
        ],
        "visual_evidence": [
            {
                "visual_id": "IMG-01",
                "file_sha256": SHA_A,
                "media_type": "IMAGE_JPEG",
                "platform": "DRONE_RGB",
                "capture_at": "2026-10-21T08:20:00-03:00",
                "capture_time_precision": "EXATA",
                "capture_time_source": "METADADO_ARQUIVO",
                "camera_position_relative_to_point": "NO_PONTO",
                "lens_aim_direction_cardinal": "NADIR",
                "lens_aim_azimuth_deg": None,
                "altitude_agl_m": 28.0,
                "altitude_agl_source": "TELEMETRIA",
                "target_visible": False,
                "incidental_people_present": False,
                "authorized_for_context": True,
                "numeric_model_input": False,
                "annotations": [
                    {"domain": "OBSTRUCAO_VISUAL", "category": "SEM_OBSTRUCAO_RELEVANTE", "evidence_nature": "OBSERVADO"},
                    {"domain": "VIAS_ACESSOS", "category": "VIA_VISIVEL", "evidence_nature": "OBSERVADO"},
                    {"domain": "RECURSO_OPERACIONAL", "category": "COMPATIVEL_COM_RGB", "evidence_nature": "OBSERVADO"},
                    {"domain": "TERRENO", "category": "PLANO", "evidence_nature": "OBSERVADO"},
                    {"domain": "QUALIDADE_IMAGEM", "category": "NITIDA_E_ATUAL", "evidence_nature": "OBSERVADO"},
                ],
            }
        ],
        "urgency_observations": [urgency_obs(index, domain) for index, domain in enumerate(critical, 1)],
        "detectability_assessments": [
            {
                "sector_id": "SETOR-N",
                "modality": "OBSERVACAO_AEREA_RGB",
                "assessed_at": "2026-10-21T09:00:00-03:00",
                "dimensions": [
                    {
                        "dimension": domain,
                        "category": "FAVORAVEL_OBSERVADO",
                        "source_type": "IMAGEM_DRONE",
                        "evidence_id": "IMG-01",
                    }
                    for index, domain in enumerate(sorted(module._DET_DIMENSIONS), 1)
                ],
            }
        ],
        "source_artifacts": {
            "profile_v2_compiled_sha256": SHA_A,
            "territorial_manifest_sha256": SHA_B,
            "spatial_review_manifest_sha256": SHA_C,
            "visual_manifest_sha256": SHA_D,
            "loc_result_sha256": SHA_B,
        },
        "search_event_hashes": [],
        "freeze_metadata": None,
    }


def draft_event() -> dict:
    return {
        "protocol_version": module.EVENT_PROTOCOL_VERSION,
        "scenario_id": "TESTE-01",
        "event_id": "EVT-001",
        "event_sequence": 1,
        "record_status": "RASCUNHO",
        "event_type": "BUSCA_EXECUTADA",
        "started_at": "2026-10-21T10:00:00-03:00",
        "ended_at": "2026-10-21T11:00:00-03:00",
        "recorded_at": "2026-10-21T11:10:00-03:00",
        "source_type": "EQUIPE_TERRESTRE",
        "source_code": "EQ-01",
        "authorized_for_model": True,
        "coverage_geometry_sha256": SHA_A,
        "track_sha256": SHA_B,
        "sector_ids": ["SETOR-N"],
        "modality": "BUSCA_TERRESTRE",
        "effort_minutes": 60.0,
        "coverage_status": "MEDIDA",
        "coverage_method_id": "COV-METHOD-01",
        "coverage_fraction": 0.7,
        "visibility_recorded": True,
        "visibility_class": "BOA",
        "limitations_recorded": True,
        "limitations": [],
        "pod": None,
        "result": "NAO_LOCALIZADO",
        "clue_coordinate": None,
        "prior_run_sha256": SHA_C,
        "previous_event_sha256": None,
        "source_event_sha256": None,
        "ground_truth_absent": True,
        "freeze_metadata": None,
    }


def valid_profile_run(
    case: dict,
    *,
    candidate_id: str = "C-01",
    sector_ids: tuple[str, str] = ("SETOR-N", "SETOR-S"),
    spatial_review_sha: str | None = SHA_C,
) -> dict:
    payload = {
        "protocol_version": "PERFIL-V3-QUANT-v1.0",
        "scenario_id": case["scenario_id"],
        "candidate_id": candidate_id,
        "record_status": "RASCUNHO",
        "created_at": case["created_at"],
        "ground_truth_absent": True,
        "source_loc_input_sha256": module.calculate_loc_input_sha256(case),
        "source_case_revision": case["case_revision"],
        "source_profile_compiled_sha256": case["source_artifacts"]["profile_v2_compiled_sha256"],
        "source_territorial_manifest_sha256": case["source_artifacts"]["territorial_manifest_sha256"],
        "source_spatial_review_sha256": spatial_review_sha,
        "sectors": [
            {
                "sector_id": sector_ids[0],
                "territorial_score": 0.5,
                "bearing_start_deg": 315.0,
                "bearing_end_deg": 135.0,
                "polygon": [[-51.08, 0.01], [-51.06, 0.01], [-51.06, 0.03], [-51.08, 0.03], [-51.08, 0.01]],
            },
            {
                "sector_id": sector_ids[1],
                "territorial_score": 0.5,
                "bearing_start_deg": 135.0,
                "bearing_end_deg": 315.0,
                "polygon": [[-51.08, -0.01], [-51.06, -0.01], [-51.06, 0.01], [-51.08, 0.01], [-51.08, -0.01]],
            },
        ],
        "hypotheses": [],
        "freeze_metadata": None,
    }
    frozen = PROFILE_MODULE.prepare_frozen_input(payload, "2026-10-21T08:05:00-03:00")
    result = PROFILE_MODULE.rank_profile(frozen)
    return {
        "candidate_id": candidate_id,
        "profile_input": frozen,
        "profile_result": result,
    }


def valid_profile_result(
    case: dict,
    *,
    candidate_id: str = "C-01",
    sector_ids: tuple[str, str] = ("SETOR-N", "SETOR-S"),
) -> dict:
    return valid_profile_run(
        case, candidate_id=candidate_id, sector_ids=sector_ids
    )["profile_result"]


def valid_loc_result(
    case: dict | None = None,
    *,
    profile_runs: list[dict] | None = None,
) -> dict:
    case = case or draft_case()
    runs = profile_runs or [valid_profile_run(case)]
    return module.build_loc_result_envelope(case, runs)


class IntegratedProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = json.loads(module.DEFAULT_RULES_PATH.read_text(encoding="utf-8"))

    def freeze(self, value: dict) -> dict:
        return module.prepare_frozen_case(value, "2026-10-21T10:00:00-03:00")

    def test_valid_case_freezes_and_compiles_deterministically(self) -> None:
        frozen_a = self.freeze(draft_case())
        frozen_b = self.freeze(draft_case())
        self.assertEqual(module.canonical_json_bytes(frozen_a), module.canonical_json_bytes(frozen_b))
        output_a = module.compile_case(frozen_a, self.rules)
        output_b = module.compile_case(frozen_b, self.rules)
        self.assertEqual(output_a, output_b)
        self.assertEqual(output_a["urgency"]["status"], "REVISAO_PADRAO")
        self.assertEqual(output_a["detectability"]["per_sector_modality"][0]["status"], "REVISAR")

    def test_tamper_after_freeze_is_rejected(self) -> None:
        frozen = self.freeze(draft_case())
        frozen["planning_point"]["latitude"] += 0.001
        with self.assertRaises(module.InputValidationError):
            module.compile_case(frozen, self.rules)

    def test_frozen_case_cannot_be_silently_refrozen(self) -> None:
        frozen = self.freeze(draft_case())
        with self.assertRaises(module.InputValidationError):
            module.prepare_frozen_case(frozen, "2026-10-21T10:05:00-03:00")

    def test_ground_truth_key_is_rejected_recursively(self) -> None:
        value = draft_case()
        value["profile_facts"][0]["ground_truth_lat"] = 0.0
        with self.assertRaises(module.GroundTruthFirewallError):
            module.validate_case(value)

    def test_unknown_does_not_become_low_urgency(self) -> None:
        value = draft_case()
        value["urgency_observations"] = []
        output = module.compile_case(self.freeze(value), self.rules)
        self.assertEqual(output["urgency"]["status"], "INDETERMINADA")
        self.assertTrue(output["urgency"]["missing_critical_domains"])

    def test_direct_risk_triggers_immediate_review(self) -> None:
        value = draft_case()
        value["urgency_observations"][0]["availability"] = "PRESENTE"
        value["urgency_observations"][0]["operational_significance"] = "DIRETA_A_VIDA"
        output = module.compile_case(self.freeze(value), self.rules)
        self.assertEqual(output["urgency"]["status"], "REVISAO_IMEDIATA")

    def test_vulnerability_triggers_priority_review(self) -> None:
        value = draft_case()
        value["urgency_observations"][2]["availability"] = "PRESENTE"
        value["urgency_observations"][2]["operational_significance"] = "AUMENTA_VULNERABILIDADE"
        output = module.compile_case(self.freeze(value), self.rules)
        self.assertEqual(output["urgency"]["status"], "REVISAO_PRIORITARIA")

    def test_conflict_forces_abstention(self) -> None:
        value = draft_case()
        value["urgency_observations"][1]["availability"] = "CONTRADITORIO"
        output = module.compile_case(self.freeze(value), self.rules)
        self.assertEqual(output["urgency"]["status"], "INDETERMINADA")
        self.assertTrue(output["urgency"]["conflict_observation_ids"])

    def test_expired_evidence_does_not_trigger(self) -> None:
        value = draft_case()
        observation = value["urgency_observations"][0]
        observation["availability"] = "PRESENTE"
        observation["operational_significance"] = "DIRETA_A_VIDA"
        observation["evidence"]["valid_until"] = "2026-10-21T08:30:00-03:00"
        output = module.compile_case(self.freeze(value), self.rules)
        self.assertEqual(output["urgency"]["status"], "INDETERMINADA")
        self.assertIn(observation["observation_id"], output["urgency"]["expired_observation_ids"])

    def test_suspected_evidence_does_not_trigger_urgency(self) -> None:
        value = draft_case()
        observation = value["urgency_observations"][0]
        observation["availability"] = "PRESENTE"
        observation["operational_significance"] = "DIRETA_A_VIDA"
        observation["evidence"]["nature"] = "SUSPEITO"
        output = module.compile_case(self.freeze(value), self.rules)
        self.assertEqual(output["urgency"]["status"], "INDETERMINADA")
        self.assertEqual(
            output["urgency"]["ineligible_observations"][0]["reason"],
            "NATUREZA_NAO_SUFICIENTE",
        )

    def test_future_evidence_does_not_trigger_urgency(self) -> None:
        value = draft_case()
        observation = value["urgency_observations"][0]
        observation["availability"] = "PRESENTE"
        observation["operational_significance"] = "DIRETA_A_VIDA"
        observation["evidence"]["observed_at"] = "2026-10-21T09:30:00-03:00"
        output = module.compile_case(self.freeze(value), self.rules)
        self.assertEqual(output["urgency"]["status"], "INDETERMINADA")
        reasons = {item["reason"] for item in output["urgency"]["ineligible_observations"]}
        self.assertIn("EVIDENCIA_FUTURA", reasons)

    def test_duplicate_evidence_does_not_accumulate(self) -> None:
        value = draft_case()
        value["urgency_observations"][0]["availability"] = "PRESENTE"
        value["urgency_observations"][0]["operational_significance"] = "AUMENTA_VULNERABILIDADE"
        duplicate = copy.deepcopy(value["urgency_observations"][0])
        duplicate["observation_id"] = "URG-DUP"
        value["urgency_observations"].append(duplicate)
        output = module.compile_case(self.freeze(value), self.rules)
        self.assertEqual(output["urgency"]["triggered_rules"], ["URG-R02-VULNERABILIDADE"])

    def test_disabled_rule_is_not_executed(self) -> None:
        value = draft_case()
        value["urgency_observations"][0]["availability"] = "PRESENTE"
        value["urgency_observations"][0]["operational_significance"] = "DIRETA_A_VIDA"
        rules = copy.deepcopy(self.rules)
        rules["rules"][0]["status"] = "DESABILITADA"
        output = module.compile_case(self.freeze(value), rules)
        self.assertEqual(output["urgency"]["status"], "INDETERMINADA")
        self.assertFalse(output["urgency"]["triggered_rules"])
        self.assertIn("URG-01", output["urgency"]["unhandled_priority_observation_ids"])

    def test_rule_semantic_drift_is_rejected(self) -> None:
        rules = copy.deepcopy(self.rules)
        rules["rules"][0]["result"] = "REVISAO_PADRAO"
        with self.assertRaises(module.InputValidationError):
            module.compile_case(self.freeze(draft_case()), rules)

    def test_restricted_rgb_does_not_change_loc(self) -> None:
        base = draft_case()
        frozen_base = self.freeze(base)
        output_base = module.compile_case(frozen_base, self.rules)
        restricted = draft_case()
        restricted["detectability_assessments"][0]["dimensions"][0]["category"] = "RESTRITO_OBSERVADO"
        next(
            annotation
            for annotation in restricted["visual_evidence"][0]["annotations"]
            if annotation["domain"] == "VIAS_ACESSOS"
        )["category"] = "SEM_ACESSO"
        output_restricted = module.compile_case(self.freeze(restricted), self.rules)
        self.assertEqual(output_base["location"]["logical_sha256"], output_restricted["location"]["logical_sha256"])
        verified_det = module.assess_detectability(
            self.freeze(restricted), {"visual:IMG-01"}, {"SETOR-N"}
        )
        self.assertEqual(verified_det["per_sector_modality"][0]["status"], "REVISAR")
        self.assertEqual(
            verified_det["per_sector_modality"][0]["spatially_unqualified_evidence_ids"],
            ["IMG-01"],
        )
        self.assertFalse(output_restricted["detectability"]["affects_loc"])

    def test_public_layer_alone_requires_review(self) -> None:
        value = draft_case()
        value["search_context"]["environment_observations"][0]["evidence"]["source_type"] = "CAMADA_PUBLICA"
        dimension = next(
            item
            for item in value["detectability_assessments"][0]["dimensions"]
            if item["dimension"] == "CONDICAO_AMBIENTAL"
        )
        dimension["source_type"] = "CAMADA_PUBLICA"
        dimension["category"] = "POTENCIAL_CAMADA_PUBLICA"
        dimension["evidence_id"] = "E-ENV-01"
        output = module.compile_case(self.freeze(value), self.rules)
        self.assertEqual(output["detectability"]["per_sector_modality"][0]["status"], "REVISAR")

    def test_detectability_rejects_nonexistent_evidence_reference(self) -> None:
        value = draft_case()
        value["detectability_assessments"][0]["dimensions"][0]["evidence_id"] = "E-NAO-EXISTE"
        with self.assertRaises(module.InputValidationError):
            module.validate_case(value)

    def test_visual_set_a_rejects_visible_target(self) -> None:
        value = draft_case()
        value["visual_evidence"][0]["target_visible"] = True
        with self.assertRaises(module.InputValidationError):
            module.validate_case(value)

    def test_visual_set_a_allows_incidental_people_with_target_absent(self) -> None:
        value = draft_case()
        value["visual_evidence"][0]["incidental_people_present"] = True
        module.validate_case(value)

    def test_visual_set_a_rejects_numeric_input(self) -> None:
        value = draft_case()
        value["visual_evidence"][0]["numeric_model_input"] = True
        with self.assertRaises(module.InputValidationError):
            module.validate_case(value)

    def test_upv_requires_time_and_observed_evidence(self) -> None:
        value = draft_case()
        value["planning_point"]["point_role"] = "ULTIMO_PONTO_VISTO"
        value["planning_point"]["point_semantics"] = "OBSERVACAO_DIRETA"
        value["planning_point"]["position_observed_at"] = None
        with self.assertRaises(module.InputValidationError):
            module.validate_case(value)

    def test_known_location_disables_loc_ranking(self) -> None:
        value = draft_case()
        value["person_location_status"] = "CONHECIDA_OPERACIONALMENTE"
        output = module.compile_case(self.freeze(value), self.rules)
        self.assertEqual(output["location"]["processing_route"], "REVISAR_EVENTO_POSITIVO")
        self.assertEqual(output["location"]["status"], "LOCALIZACAO_CONHECIDA_DECLARADA_NAO_VERIFICADA")

    def test_declared_loc_hash_is_not_called_verified_without_files(self) -> None:
        output = module.compile_case(self.freeze(draft_case()), self.rules)
        self.assertEqual(output["location"]["status"], "RESULTADO_EXTERNO_DECLARADO_NAO_VERIFICADO")
        self.assertEqual(output["artifact_verification"]["status"], "NOT_PERFORMED")

    def test_artifact_bindings_are_verified_against_files(self) -> None:
        value = draft_case()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_map: dict[str, str] = {}
            for key in value["source_artifacts"]:
                path = root / f"{key}.bin"
                content = f"conteudo::{key}".encode("utf-8")
                path.write_bytes(content)
                value["source_artifacts"][key] = hashlib.sha256(content).hexdigest()
                artifact_map[key] = path.name
            image_path = root / "IMG-01.jpg"
            image_content = b"\xff\xd8\xff\xe0JFIF\x00synthetic-test-image-x\xff\xd9"
            image_path.write_bytes(image_content)
            value["visual_evidence"][0]["file_sha256"] = hashlib.sha256(image_content).hexdigest()
            artifact_map["visual:IMG-01"] = image_path.name
            frozen = self.freeze(value)
            output = module.compile_case(frozen, self.rules, artifact_map, root)
            self.assertEqual(output["artifact_verification"]["status"], "VERIFIED")
            self.assertEqual(
                output["location"]["status"],
                "RESULTADO_EXTERNO_INTEGRIDADE_DE_BYTES_VERIFICADA_CONTEUDO_NAO_VALIDADO",
            )
            self.assertTrue(output["review_required"])

    def test_loc_result_contract_is_semantically_validated(self) -> None:
        value = draft_case()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_map: dict[str, str] = {}
            for key in value["source_artifacts"]:
                if key == "loc_result_sha256":
                    continue
                path = root / f"{key}.bin"
                content = f"conteudo::{key}".encode("utf-8")
                path.write_bytes(content)
                value["source_artifacts"][key] = hashlib.sha256(content).hexdigest()
                artifact_map[key] = path.name
            loc_path = root / "loc_result.json"
            loc_content = module.canonical_json_bytes(valid_loc_result(value))
            loc_path.write_bytes(loc_content)
            value["source_artifacts"]["loc_result_sha256"] = hashlib.sha256(loc_content).hexdigest()
            artifact_map["loc_result_sha256"] = loc_path.name
            image_path = root / "IMG-01.jpg"
            image_content = b"\xff\xd8\xff\xe0JFIF\x00synthetic-test-image-x\xff\xd9"
            image_path.write_bytes(image_content)
            value["visual_evidence"][0]["file_sha256"] = hashlib.sha256(image_content).hexdigest()
            artifact_map["visual:IMG-01"] = image_path.name
            output = module.compile_case(self.freeze(value), self.rules, artifact_map, root)

        self.assertEqual(
            output["location"]["status"],
            "RESULTADO_EXTERNO_CONTRATO_VALIDADO_CEGAMENTO_DECLARADO",
        )
        self.assertEqual(
            output["location"]["external_content_validation"],
            "LOC_CONTRACT_VALIDATED_DECLARED_BLIND",
        )
        self.assertEqual(output["location"]["valid_sector_ids"], ["SETOR-N", "SETOR-S"])
        self.assertEqual(output["location"]["valid_candidate_ids"], ["C-01"])
        self.assertEqual(
            output["detectability"]["per_sector_modality"][0]["loc_sector_link"],
            "VALIDATED",
        )
        self.assertEqual(
            output["detectability"]["per_sector_modality"][0]["status"],
            "REVISAR",
        )
        self.assertEqual(
            output["detectability"]["per_sector_modality"][0][
                "spatially_unqualified_evidence_ids"
            ],
            ["IMG-01"],
        )
        self.assertTrue(output["review_required"])

    def test_loc_envelope_uses_real_profile_output_and_accepts_competition_ties(self) -> None:
        value = draft_case()
        profile_run = valid_profile_run(value)
        profile_result = profile_run["profile_result"]
        self.assertEqual(
            [row["profile_rank"] for row in profile_result["operational_rows"]],
            [1, 1],
        )
        envelope = module.build_loc_result_envelope(value, [profile_run])
        self.assertFalse(envelope["cross_candidate_ranking"])
        self.assertEqual(
            envelope["profile_runs"][0]["profile_result"]["output_sha256"],
            profile_result["output_sha256"],
        )
        self.assertEqual(
            envelope["profile_runs"][0]["profile_result"]["input_sha256"],
            module.canonical_sha256(envelope["profile_runs"][0]["profile_input"]),
        )

    def test_loc_envelope_rejects_duplicate_candidates_and_sector_ids(self) -> None:
        value = draft_case()
        first = valid_profile_run(value)
        duplicate_candidate = valid_profile_run(value)
        with self.assertRaises(module.InputValidationError):
            module.build_loc_result_envelope(value, [first, duplicate_candidate])

        second = valid_profile_run(
            value,
            candidate_id="C-02",
            sector_ids=("SETOR-N", "SETOR-O"),
            spatial_review_sha=SHA_D,
        )
        with self.assertRaises(module.InputValidationError):
            module.build_loc_result_envelope(value, [first, second])

    def test_loc_envelope_sorts_candidates_but_never_ranks_them(self) -> None:
        value = draft_case()
        second = valid_profile_run(
            value,
            candidate_id="C-02",
            sector_ids=("C02-N", "C02-S"),
            spatial_review_sha=SHA_D,
        )
        first = valid_profile_run(
            value,
            candidate_id="C-01",
            sector_ids=("C01-N", "C01-S"),
        )
        envelope = module.build_loc_result_envelope(value, [second, first])
        self.assertEqual(
            [item["candidate_id"] for item in envelope["profile_runs"]],
            ["C-01", "C-02"],
        )
        self.assertNotIn("candidate_ranking", envelope)
        self.assertEqual(
            envelope["profile_runs"][1]["profile_input"]["source_spatial_review_sha256"],
            SHA_D,
        )

    def test_loc_envelope_rejects_tampered_profile_output_and_scope(self) -> None:
        value = draft_case()
        tampered = valid_profile_run(value)
        tampered["profile_result"]["operational_rows"][0]["profile_score"] = 0.9
        projected_tampered = copy.deepcopy(tampered["profile_result"])
        projected_tampered.pop("output_sha256")
        tampered["profile_result"]["output_sha256"] = module.canonical_sha256(
            projected_tampered
        )
        with self.assertRaises(module.InputValidationError):
            module.build_loc_result_envelope(value, [tampered])

        prohibited_scope = valid_profile_run(value)
        prohibited_scope["profile_result"]["scope_guards"]["mobility_weighted"] = True
        projected = copy.deepcopy(prohibited_scope["profile_result"])
        projected.pop("output_sha256")
        prohibited_scope["profile_result"]["output_sha256"] = module.canonical_sha256(projected)
        with self.assertRaises(module.InputValidationError):
            module.build_loc_result_envelope(value, [prohibited_scope])

    def test_loc_envelope_rejects_profile_input_changed_after_ranking(self) -> None:
        value = draft_case()
        run = valid_profile_run(value)
        run["profile_input"]["sectors"][0]["territorial_score"] = 0.4
        projected = copy.deepcopy(run["profile_input"])
        projected["freeze_metadata"] = dict(projected["freeze_metadata"])
        projected["freeze_metadata"].pop("payload_sha256")
        run["profile_input"]["freeze_metadata"]["payload_sha256"] = module.canonical_sha256(projected)
        with self.assertRaises(module.InputValidationError):
            module.build_loc_result_envelope(value, [run])

    def test_loc_envelope_rejects_profile_execution_after_case_cutoff(self) -> None:
        value = draft_case()
        future_input = copy.deepcopy(valid_profile_run(value)["profile_input"])
        future_input["record_status"] = "RASCUNHO"
        future_input["created_at"] = "2027-01-01T08:00:00-03:00"
        future_input["freeze_metadata"] = None
        future_input = PROFILE_MODULE.prepare_frozen_input(
            future_input, "2027-01-01T08:05:00-03:00"
        )
        future_result = PROFILE_MODULE.rank_profile(future_input)
        with self.assertRaises(module.InputValidationError):
            module.build_loc_result_envelope(
                value,
                [{
                    "candidate_id": future_input["candidate_id"],
                    "profile_input": future_input,
                    "profile_result": future_result,
                }],
            )

    def test_loc_envelope_rejects_profile_run_from_another_loc_context(self) -> None:
        original = draft_case()
        run = valid_profile_run(original)
        altered = draft_case()
        altered["planning_point"]["latitude"] = 10.0
        altered["planning_point"]["longitude"] = 100.0
        with self.assertRaises(module.InputValidationError):
            module.build_loc_result_envelope(altered, [run])

    def test_loc_envelope_enforces_same_hundred_run_limit_as_contract(self) -> None:
        value = draft_case()
        with self.assertRaises(module.InputValidationError):
            module.build_loc_result_envelope(value, [{} for _ in range(101)])

    def test_forged_verification_mapping_cannot_mark_files_verified(self) -> None:
        frozen = self.freeze(draft_case())
        forged = {
            "status": "VERIFIED",
            "artifact_root_not_embedded": True,
            "bindings": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(module.InputValidationError):
                module.compile_case(frozen, self.rules, forged, Path(directory))

    def test_revision_after_first_requires_parent_hash(self) -> None:
        value = draft_case()
        value["case_revision"] = 2
        with self.assertRaises(module.InputValidationError):
            module.validate_case(value)
        value["parent_payload_sha256"] = SHA_D
        module.validate_case(value)
        with self.assertRaises(module.InputValidationError):
            module.prepare_frozen_case(value, "2026-10-21T10:00:00-03:00")

    def test_negative_search_never_changes_loc(self) -> None:
        value = draft_event()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_map = {}
            prior_case = module.prepare_frozen_case(
                draft_case(), "2026-10-21T10:00:00-03:00"
            )
            prior_run = module.compile_case(prior_case, self.rules)
            prior_run["location"]["status"] = (
                "RESULTADO_EXTERNO_CONTRATO_VALIDADO_CEGAMENTO_DECLARADO"
            )
            prior_run["location"]["external_content_validation"] = (
                "LOC_CONTRACT_VALIDATED_DECLARED_BLIND"
            )
            prior_run["location"]["valid_sector_ids"] = ["SETOR-N"]
            prior_run["location"]["valid_candidate_ids"] = ["C-01"]
            location_projection = copy.deepcopy(prior_run["location"])
            location_projection.pop("logical_sha256", None)
            prior_run["location"]["logical_sha256"] = module.canonical_sha256(
                location_projection
            )
            prior_projection = copy.deepcopy(prior_run)
            prior_projection.pop("output_sha256", None)
            prior_run["output_sha256"] = module.canonical_sha256(prior_projection)
            artifacts = {
                "coverage_geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]],
                },
                "track": {
                    "type": "LineString",
                    "coordinates": [[0.0, 0.0], [1.0, 1.0]],
                },
                "prior_run": prior_run,
            }
            fields = {
                "coverage_geometry": "coverage_geometry_sha256",
                "track": "track_sha256",
                "prior_run": "prior_run_sha256",
            }
            for binding, document in artifacts.items():
                content = module.canonical_json_bytes(document)
                path = root / f"{binding}.json"
                path.write_bytes(content)
                value[fields[binding]] = hashlib.sha256(content).hexdigest()
                artifact_map[binding] = path.name
            frozen = module.prepare_frozen_event(value, "2026-10-21T11:20:00-03:00")
            output = module.compile_event(frozen, artifact_map, root)
        self.assertTrue(output["documentary_search_record_complete"])
        self.assertTrue(output["search_artifacts_structurally_validated"])
        self.assertFalse(output["search_artifacts_semantically_validated"])
        self.assertFalse(output["negative_evidence_eligible_for_human_review"])
        self.assertEqual(output["location_ranking_effect"], "NONE_V1")
        self.assertFalse(output["sector_elimination_allowed"])

    def test_incomplete_negative_search_is_only_warning(self) -> None:
        value = draft_event()
        value["coverage_geometry_sha256"] = None
        frozen = module.prepare_frozen_event(value, "2026-10-21T11:20:00-03:00")
        output = module.compile_event(frozen)
        self.assertFalse(output["negative_evidence_eligible_for_human_review"])
        self.assertEqual(output["location_ranking_effect"], "NONE_V1")

    def test_numeric_pod_is_rejected_in_v1(self) -> None:
        value = draft_event()
        value["pod"] = 0.8
        with self.assertRaises(module.InputValidationError):
            module.validate_event(value)

    def test_new_known_point_cannot_come_from_negative_event(self) -> None:
        value = draft_event()
        value["event_type"] = "NOVO_PONTO_CONHECIDO"
        value["clue_coordinate"] = {"latitude": 0.01, "longitude": -51.0}
        with self.assertRaises(module.InputValidationError):
            module.validate_event(value)

    def test_new_known_point_requires_and_preserves_source_event(self) -> None:
        source = draft_event()
        source["event_type"] = "VESTIGIO_ENCONTRADO"
        source["result"] = "POSITIVO"
        source["clue_coordinate"] = {"latitude": 0.01, "longitude": -51.0}
        frozen_source = module.prepare_frozen_event(source, "2026-10-21T11:20:00-03:00")
        source_hash = frozen_source["freeze_metadata"]["payload_sha256"]
        value = draft_event()
        value["event_id"] = "EVT-002"
        value["event_sequence"] = 2
        value["event_type"] = "NOVO_PONTO_CONHECIDO"
        value["result"] = "POSITIVO"
        value["clue_coordinate"] = {"latitude": 0.01, "longitude": -51.0}
        value["started_at"] = "2026-10-21T11:21:00-03:00"
        value["ended_at"] = "2026-10-21T11:22:00-03:00"
        value["recorded_at"] = "2026-10-21T11:23:00-03:00"
        value["event_type"] = "NOVO_PONTO_CONHECIDO"
        value["coverage_geometry_sha256"] = None
        value["track_sha256"] = None
        value["sector_ids"] = []
        value["modality"] = None
        value["effort_minutes"] = None
        value["coverage_status"] = "NAO_DISPONIVEL"
        value["coverage_method_id"] = None
        value["coverage_fraction"] = None
        value["visibility_recorded"] = False
        value["visibility_class"] = "NAO_DISPONIVEL"
        value["limitations_recorded"] = False
        value["prior_run_sha256"] = None
        value["previous_event_sha256"] = source_hash
        value["source_event_sha256"] = source_hash
        frozen = module.prepare_frozen_event(
            value,
            "2026-10-21T11:30:00-03:00",
            previous_event=frozen_source,
            source_event=frozen_source,
        )
        output = module.compile_event(frozen)
        self.assertEqual(output["next_action"], "REVISAR_VINCULOS_DO_NOVO_PONTO")
        self.assertEqual(output["origin_event_sha256"], source_hash)
        self.assertEqual(output["location_ranking_effect"], "NONE_V1")

    def test_frozen_event_tamper_is_rejected(self) -> None:
        frozen = module.prepare_frozen_event(draft_event(), "2026-10-21T11:20:00-03:00")
        frozen["effort_minutes"] = 61.0
        with self.assertRaises(module.InputValidationError):
            module.compile_event(frozen)

    def test_frozen_event_cannot_be_silently_refrozen(self) -> None:
        frozen = module.prepare_frozen_event(draft_event(), "2026-10-21T11:20:00-03:00")
        with self.assertRaises(module.InputValidationError):
            module.prepare_frozen_event(frozen, "2026-10-21T11:25:00-03:00")


if __name__ == "__main__":
    unittest.main()
