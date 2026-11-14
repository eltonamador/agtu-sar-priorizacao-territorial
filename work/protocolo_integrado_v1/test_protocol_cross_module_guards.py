from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import integrated_protocol as module
from test_integrated_protocol import draft_case, draft_event


class CrossModuleGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = json.loads(module.DEFAULT_RULES_PATH.read_text(encoding="utf-8"))

    @staticmethod
    def freeze_case(value: dict) -> dict:
        return module.prepare_frozen_case(value, "2026-10-21T10:00:00-03:00")

    def test_confirmed_structured_profile_risk_cannot_coexist_with_absent_urgency(self) -> None:
        value = draft_case()
        value["profile_facts"].append({
            "fact_id": "FACT-COGNICAO-01",
            "domain": "COGNICAO_ORIENTACAO",
            "availability": "PRESENTE",
            "value": "DESORIENTADO",
            "evidence": {
                "evidence_id": "E-FACT-COGNICAO-01",
                "source_type": "OPERADOR",
                "source_code": "OP-01",
                "nature": "CONFIRMADO",
                "confidence": "ALTA",
                "observed_at": "2026-10-21T08:00:00-03:00",
                "time_precision": "EXATA",
                "valid_until": None,
                "authorized_for_model": True,
            },
        })
        output = module.compile_case(self.freeze_case(value), self.rules)
        self.assertEqual(output["urgency"]["status"], "INDETERMINADA")
        self.assertIn("COGNICAO_ORIENTACAO", output["urgency"]["conflict_domains"])
        self.assertEqual(
            output["urgency"]["profile_consistency_conflicts"][0]["fact_id"],
            "FACT-COGNICAO-01",
        )

    def test_compatible_structured_profile_risk_is_reconciled(self) -> None:
        value = draft_case()
        value["profile_facts"].append({
            "fact_id": "FACT-COGNICAO-01",
            "domain": "COGNICAO_ORIENTACAO",
            "availability": "PRESENTE",
            "value": "DESORIENTADO",
            "evidence": {
                "evidence_id": "E-FACT-COGNICAO-01",
                "source_type": "OPERADOR",
                "source_code": "OP-01",
                "nature": "CONFIRMADO",
                "confidence": "ALTA",
                "observed_at": "2026-10-21T08:00:00-03:00",
                "time_precision": "EXATA",
                "valid_until": None,
                "authorized_for_model": True,
            },
        })
        cognition = next(
            item for item in value["urgency_observations"]
            if item["domain"] == "COGNICAO_ORIENTACAO"
        )
        cognition["availability"] = "PRESENTE"
        cognition["operational_significance"] = "AUMENTA_VULNERABILIDADE"
        output = module.compile_case(self.freeze_case(value), self.rules)
        self.assertEqual(output["urgency"]["status"], "REVISAO_PRIORITARIA")
        self.assertFalse(output["urgency"]["profile_consistency_conflicts"])

    def test_cardinal_direction_and_azimuth_must_agree(self) -> None:
        value = draft_case()
        visual = value["visual_evidence"][0]
        visual["lens_aim_direction_cardinal"] = "N"
        visual["lens_aim_azimuth_deg"] = 180.0
        with self.assertRaises(module.InputValidationError):
            module.validate_case(value)

    def test_runtime_enforces_schema_text_limits(self) -> None:
        variants = []
        accuracy_source = draft_case()
        accuracy_source["planning_point"]["horizontal_accuracy_m"] = 4.0
        accuracy_source["planning_point"]["horizontal_accuracy_status"] = "INFORMADA"
        accuracy_source["planning_point"]["horizontal_accuracy_source"] = "x" * 161
        variants.append(accuracy_source)

        unit = draft_case()
        unit["search_context"]["environment_observations"][0]["unit"] = "x" * 41
        variants.append(unit)

        annotation = draft_case()
        annotation["visual_evidence"][0]["annotations"][0]["category"] = "x" * 161
        variants.append(annotation)

        for value in variants:
            with self.subTest(value=value):
                with self.assertRaises(module.InputValidationError):
                    module.validate_case(value)

    def test_coordinate_cannot_leak_through_evidence_source_code(self) -> None:
        value = draft_case()
        value["planning_point"]["evidence"]["source_code"] = (
            "0.0024809355844815323, -51.07092698392779"
        )
        with self.assertRaises(module.InputValidationError):
            module.validate_case(value)

    def test_maximum_travel_time_cannot_exceed_elapsed_time(self) -> None:
        value = draft_case()
        value["search_context"]["maximum_plausible_travel_minutes"] = 61.0
        with self.assertRaises(module.InputValidationError):
            module.validate_case(value)

    def test_travel_mode_cannot_contradict_eligible_mobility_fact(self) -> None:
        value = draft_case()
        value["search_context"]["travel_mode"] = "VEICULO"
        with self.assertRaises(module.InputValidationError):
            module.validate_case(value)

    def test_conflicting_specific_mobility_requires_safe_reconciliation(self) -> None:
        value = draft_case()
        vehicle = copy.deepcopy(value["profile_facts"][0])
        vehicle["fact_id"] = "FACT-MOB-VEICULO"
        vehicle["value"] = "VEICULO"
        vehicle["evidence"]["evidence_id"] = "E-FACT-MOB-VEICULO"
        value["profile_facts"].append(vehicle)
        with self.assertRaises(module.InputValidationError):
            module.validate_case(value)

        value["search_context"]["travel_mode"] = "MISTO"
        module.validate_case(value)
        value["search_context"]["travel_mode"] = "DESCONHECIDO"
        module.validate_case(value)

    def test_mixed_travel_mode_requires_supporting_evidence(self) -> None:
        value = draft_case()
        value["search_context"]["travel_mode"] = "MISTO"
        with self.assertRaises(module.InputValidationError):
            module.validate_case(value)

    def test_approximate_operator_time_is_preserved_without_inventing_metadata(self) -> None:
        value = draft_case()
        visual = value["visual_evidence"][0]
        visual["capture_time_precision"] = "APROXIMADA"
        visual["capture_time_source"] = "ESTIMATIVA_OPERADOR"
        module.validate_case(value)

    def test_visual_without_capture_time_is_archivable_but_cannot_make_det_apt(self) -> None:
        value = draft_case()
        visual = value["visual_evidence"][0]
        visual["capture_at"] = None
        visual["capture_time_precision"] = "NAO_DISPONIVEL"
        visual["capture_time_source"] = "NAO_DISPONIVEL"
        module.validate_case(value)
        det = module.assess_detectability(value, {"visual:IMG-01"}, {"SETOR-N"})
        row = det["per_sector_modality"][0]
        self.assertEqual(row["status"], "REVISAR")
        self.assertEqual(row["temporally_unqualified_visual_ids"], ["IMG-01"])

    def test_visual_without_authenticated_sector_scope_never_makes_det_apt(self) -> None:
        value = draft_case()
        value["detectability_assessments"][0]["sector_id"] = "SETOR-S"
        result = module.assess_detectability(
            value, {"visual:IMG-01"}, {"SETOR-N", "SETOR-S"}
        )["per_sector_modality"][0]
        self.assertEqual(result["status"], "REVISAR")
        self.assertEqual(result["spatially_unqualified_evidence_ids"], ["IMG-01"])

    def test_approximate_visual_sector_binding_caps_det_with_restrictions(self) -> None:
        value = draft_case()
        result = module.assess_detectability(
            value,
            {"visual:IMG-01"},
            {"SETOR-N"},
            {"IMG-01::SETOR-N": "APROXIMADO_METADADOS"},
        )["per_sector_modality"][0]
        self.assertEqual(result["status"], "APTO_COM_RESTRICOES")
        self.assertEqual(result["spatially_unqualified_evidence_ids"], [])
        self.assertEqual(result["approximate_spatial_evidence_ids"], ["IMG-01"])
        self.assertEqual(
            result["spatial_binding_quality_by_evidence_id"],
            {"IMG-01": "APROXIMADO_METADADOS"},
        )

    def test_only_calibrated_visual_sector_binding_can_reach_full_det_aptitude(self) -> None:
        value = draft_case()
        result = module.assess_detectability(
            value,
            {"visual:IMG-01"},
            {"SETOR-N"},
            {"IMG-01::SETOR-N": "VERIFICADO_CALIBRADO"},
        )["per_sector_modality"][0]
        self.assertEqual(result["status"], "APTO_A_PLANEJAMENTO")
        self.assertEqual(result["calibrated_spatial_evidence_ids"], ["IMG-01"])

    def test_visual_sector_binding_cannot_cross_search_modalities(self) -> None:
        value = draft_case()
        value["detectability_assessments"][0]["modality"] = "BUSCA_TERRESTRE"
        result = module.assess_detectability(
            value,
            {"visual:IMG-01"},
            {"SETOR-N"},
            {"IMG-01::SETOR-N": "VERIFICADO_CALIBRADO"},
        )["per_sector_modality"][0]
        self.assertEqual(result["status"], "REVISAR")
        self.assertEqual(result["modality_unqualified_visual_ids"], ["IMG-01"])

    def test_environment_without_authenticated_sector_scope_never_makes_det_apt(self) -> None:
        value = draft_case()
        environment = value["search_context"]["environment_observations"][0]
        environment["value"] = "TEMPESTADE_SEVERA"
        dimension = next(
            item for item in value["detectability_assessments"][0]["dimensions"]
            if item["dimension"] == "CONDICAO_AMBIENTAL"
        )
        dimension.update({
            "source_type": "CAMPO",
            "evidence_id": environment["evidence"]["evidence_id"],
            "category": "FAVORAVEL_OBSERVADO",
        })
        module.validate_case(value)
        result = module.assess_detectability(
            value, {"visual:IMG-01"}, {"SETOR-N"}
        )["per_sector_modality"][0]
        self.assertEqual(result["status"], "REVISAR")
        self.assertIn(
            environment["evidence"]["evidence_id"],
            result["spatially_unqualified_evidence_ids"],
        )

    def test_rgb_annotation_cannot_qualify_unrelated_search_modality(self) -> None:
        value = draft_case()
        value["detectability_assessments"][0]["modality"] = "BUSCA_TERRESTRE"
        result = module.assess_detectability(
            value, {"visual:IMG-01"}, {"SETOR-N"}
        )["per_sector_modality"][0]
        self.assertEqual(result["status"], "REVISAR")
        self.assertEqual(result["spatially_unqualified_evidence_ids"], ["IMG-01"])

    def test_unassessed_significance_in_critical_domain_forces_abstention(self) -> None:
        value = draft_case()
        observation = value["urgency_observations"][0]
        observation["availability"] = "PRESENTE"
        observation["operational_significance"] = "NAO_AVALIADA"
        output = module.compile_case(self.freeze_case(value), self.rules)
        self.assertEqual(output["urgency"]["status"], "INDETERMINADA")
        self.assertIn(
            observation["observation_id"],
            output["urgency"]["unassessed_significance_observation_ids"],
        )

    def test_loc_input_ignores_non_loc_profile_facts_and_search_events(self) -> None:
        base = draft_case()
        altered = copy.deepcopy(base)
        altered["profile_facts"][0]["value"] = "MOBILIDADE_REVISADA"
        altered["search_event_hashes"] = ["e" * 64]
        self.assertEqual(
            module.calculate_loc_input_sha256(base),
            module.calculate_loc_input_sha256(altered),
        )

    def test_run_id_is_bound_to_rules_catalog_hash(self) -> None:
        frozen = self.freeze_case(draft_case())
        changed_rules = copy.deepcopy(self.rules)
        changed_rules["description"] += " Revisão documental controlada."
        base = module.compile_case(frozen, self.rules)
        changed = module.compile_case(frozen, changed_rules)
        self.assertNotEqual(base["rules_catalog_sha256"], changed["rules_catalog_sha256"])
        self.assertNotEqual(base["run_id"], changed["run_id"])

    def test_invalid_jpeg_signature_is_not_accepted_as_verified_visual(self) -> None:
        value = draft_case()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_map: dict[str, str] = {}
            for key in value["source_artifacts"]:
                content = f"case::{key}".encode("utf-8")
                path = root / f"{key}.bin"
                path.write_bytes(content)
                value["source_artifacts"][key] = hashlib.sha256(content).hexdigest()
                artifact_map[key] = path.name
            fake_jpeg = b"not-a-jpeg"
            image_path = root / "IMG-01.jpg"
            image_path.write_bytes(fake_jpeg)
            value["visual_evidence"][0]["file_sha256"] = hashlib.sha256(fake_jpeg).hexdigest()
            artifact_map["visual:IMG-01"] = image_path.name
            with self.assertRaises(module.InputValidationError):
                module.compile_case(
                    self.freeze_case(value), self.rules, artifact_map, root
                )

    def test_unauthorized_positive_source_cannot_create_known_point(self) -> None:
        source = draft_event()
        source["event_type"] = "VESTIGIO_ENCONTRADO"
        source["result"] = "POSITIVO"
        source["clue_coordinate"] = {"latitude": 0.01, "longitude": -51.0}
        source["authorized_for_model"] = False
        frozen_source = module.prepare_frozen_event(
            source, "2026-10-21T11:20:00-03:00"
        )
        source_hash = frozen_source["freeze_metadata"]["payload_sha256"]

        known = draft_event()
        known.update({
            "event_id": "EVT-002",
            "event_sequence": 2,
            "event_type": "NOVO_PONTO_CONHECIDO",
            "started_at": "2026-10-21T11:21:00-03:00",
            "ended_at": "2026-10-21T11:22:00-03:00",
            "recorded_at": "2026-10-21T11:23:00-03:00",
            "coverage_geometry_sha256": None,
            "track_sha256": None,
            "sector_ids": [],
            "modality": None,
            "effort_minutes": None,
            "coverage_status": "NAO_DISPONIVEL",
            "coverage_method_id": None,
            "coverage_fraction": None,
            "visibility_recorded": False,
            "visibility_class": "NAO_DISPONIVEL",
            "limitations_recorded": False,
            "limitations": [],
            "prior_run_sha256": None,
            "result": "POSITIVO",
            "clue_coordinate": copy.deepcopy(source["clue_coordinate"]),
            "previous_event_sha256": source_hash,
            "source_event_sha256": source_hash,
        })
        with self.assertRaises(module.InputValidationError):
            module.prepare_frozen_event(
                known,
                "2026-10-21T11:30:00-03:00",
                previous_event=frozen_source,
                source_event=frozen_source,
            )

        # Mesmo um evento derivado montado fora da rotina oficial não passa na
        # conferência dos vínculos lógicos.
        forged = copy.deepcopy(known)
        forged["record_status"] = "CONGELADO"
        forged["freeze_metadata"] = {
            "frozen_at": "2026-10-21T11:30:00-03:00",
            "projection_id": module.EVENT_FREEZE_PROJECTION_ID,
            "payload_sha256": "0" * 64,
        }
        forged["freeze_metadata"]["payload_sha256"] = module.calculate_event_freeze_sha256(forged)
        module.validate_event(forged)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.json"
            source_path.write_bytes(module.canonical_json_bytes(frozen_source))
            with self.assertRaises(module.InputValidationError):
                module.verify_event_artifact_bindings(
                    forged,
                    {"previous_event": source_path.name, "source_event": source_path.name},
                    root,
                )

    def test_sequence_one_cannot_claim_an_orphan_known_location_source(self) -> None:
        value = draft_event()
        value.update({
            "event_type": "NOVO_PONTO_CONHECIDO",
            "result": "POSITIVO",
            "clue_coordinate": {"latitude": 0.01, "longitude": -51.0},
            "source_event_sha256": "f" * 64,
        })
        with self.assertRaises(module.InputValidationError):
            module.validate_event(value)


if __name__ == "__main__":
    unittest.main()
