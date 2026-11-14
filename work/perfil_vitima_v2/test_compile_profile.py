#!/usr/bin/env python3
"""Testes do compilador qualitativo PERFIL V2."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "compile_profile.py"
SPEC = importlib.util.spec_from_file_location("compile_profile", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Falha ao carregar compile_profile.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def evidence(
    nature: str = "NAO_DISPONIVEL",
    source: str = "NAO_DISPONIVEL",
    confidence: str = "NAO_AVALIADA",
    authorized: bool = False,
) -> dict:
    return {
        "nature": nature,
        "source": source,
        "source_code": None if source == "NAO_DISPONIVEL" else "SRC-TESTE",
        "observed_at": None,
        "time_precision": "NAO_DISPONIVEL",
        "confidence": confidence,
        "authorized_for_model": authorized,
    }


def enum_fact(fact_id: str, value: str = "NAO_DISPONIVEL") -> dict:
    return {"fact_id": fact_id, "value": value, "evidence": evidence()}


def duration_fact(fact_id: str) -> dict:
    return {"fact_id": fact_id, "value_minutes": None, "evidence": evidence()}


def coded_fact(fact_id: str) -> dict:
    return {
        "fact_id": fact_id,
        "value_code": "NAO_DISPONIVEL",
        "description": None,
        "evidence": evidence(),
    }


def boolean_fact(fact_id: str) -> dict:
    return {"fact_id": fact_id, "value": None, "evidence": evidence()}


def clue(
    clue_id: str,
    clue_type: str,
    description: str,
    clue_evidence: dict,
    spatial_status: str,
    associated_location: dict | None = None,
    direction_data: dict | None = None,
) -> dict:
    return {
        "clue_id": clue_id,
        "clue_type": clue_type,
        "literal_description": description,
        "evidence": clue_evidence,
        "spatial_status": spatial_status,
        "associated_location": associated_location,
        "direction_data": direction_data,
    }


def base_payload() -> dict:
    return {
        "scenario_id": "TESTE-001",
        "protocol_version": "PERFIL-V2-DRAFT.2",
        "record_status": "RASCUNHO",
        "operator_code": "OP-TESTE",
        "collected_at": "2026-10-21T08:10:00-03:00",
        "last_planning_point": {
            "point_type": "ULTIMO_PONTO_CONHECIDO",
            "latitude": 0.01,
            "longitude": -51.07,
            "timestamp": "2026-10-21T08:00:00-03:00",
            "timestamp_precision": "EXATA",
            "timezone": "America/Belem",
            "coordinate_source": "GPS",
            "uncertainty_m": 1000.0,
            "uncertainty_status": "INFORMADA",
            "uncertainty_source": "FONTE_TESTE",
        },
        "search_context": {
            "environment": "URBANO",
            "elapsed_minutes": None,
            "elapsed_status": "NAO_DISPONIVEL",
            "elapsed_source": None,
            "travel_mode": "NAO_DISPONIVEL",
            "weather_summary": None,
        },
        "victim_profile": {
            "age_group": enum_fact("F-IDADE"),
            "mobility": enum_fact("F-MOBILIDADE"),
            "maximum_plausible_travel_time": duration_fact("F-TEMPO"),
            "cognitive_condition": enum_fact("F-COGNICAO"),
            "area_familiarity": enum_fact("F-FAMILIARIDADE"),
            "environment_experience": enum_fact("F-EXPERIENCIA"),
            "physical_or_sensory_limitations": [],
            "relevant_medication_effect": coded_fact("F-MEDICACAO"),
            "previous_disappearances": boolean_fact("F-ANTERIORES"),
        },
        "clues": [],
        "text_fields_sanitized": True,
        "ground_truth_absent": True,
        "freeze_metadata": None,
    }


class GroundTruthFirewallTest(unittest.TestCase):
    def test_rejects_ground_truth_even_when_nested(self) -> None:
        payload = base_payload()
        item = clue(
            "P-001",
            "OUTRA",
            "teste",
            evidence("RELATADO", "TESTEMUNHA", "MEDIA", True),
            "NAO_ESPACIALIZAVEL",
        )
        item["true_location"] = {"latitude": 0.0, "longitude": 0.0}
        payload["clues"].append(item)
        with self.assertRaises(MODULE.GroundTruthFirewallError):
            MODULE.compile_profile(payload)

    def test_requires_explicit_ground_truth_absence(self) -> None:
        payload = base_payload()
        payload["ground_truth_absent"] = False
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.compile_profile(payload)

    def test_rejects_explicit_ground_truth_marker_in_clue_text(self) -> None:
        payload = base_payload()
        payload["clues"].append(
            clue(
                "P-001",
                "OUTRA",
                "Posição verdadeira: 0.002, -51.071.",
                evidence("RELATADO", "OPERADOR", "ALTA", True),
                "NAO_ESPACIALIZAVEL",
            )
        )
        with self.assertRaises(MODULE.GroundTruthFirewallError):
            MODULE.compile_profile(payload)


class QualitativeCompilationTest(unittest.TestCase):
    def test_unknown_values_have_no_effect(self) -> None:
        compiled = MODULE.compile_profile(base_payload())
        self.assertEqual(compiled["hypotheses"], [])
        self.assertEqual(compiled["summary"]["hypothesis_count"], 0)
        self.assertFalse(compiled["summary"]["weights_applied"])
        self.assertFalse(compiled["summary"]["ranking_produced"])

    def test_generic_water_clue_is_not_directional(self) -> None:
        payload = base_payload()
        payload["clues"].append(
            clue(
                "P-AGUA",
                "AGUA_PESCA",
                "Relato genérico de interesse por pesca e ilhas.",
                evidence("RELATADO", "FAMILIAR", "MEDIA", True),
                "CONTEXTUAL_NAO_DIRECIONAL",
            )
        )
        compiled = MODULE.compile_profile(payload)
        hypothesis = compiled["hypotheses"][0]
        self.assertEqual(hypothesis["hypothesis_type"], "AGUA_OU_PESCA")
        self.assertEqual(hypothesis["spatial_status"], "CONTEXTUAL_NAO_DIRECIONAL")
        self.assertFalse(hypothesis["spatialized"])
        self.assertFalse(hypothesis["directional_preference_allowed"])

    def test_georeferenced_destination_is_spatializable(self) -> None:
        payload = base_payload()
        payload["clues"].append(
            clue(
                "P-DESTINO",
                "DESTINO_DECLARADO",
                "Disse que pretendia ir ao ponto de pesca habitual.",
                evidence("RELATADO", "FAMILIAR", "ALTA", True),
                "ESPACIALIZADA",
                associated_location={
                    "label": "Ponto de pesca habitual",
                    "feature_type": "MARGEM",
                    "latitude": 0.002,
                    "longitude": -51.071,
                    "geometry_reference": None,
                },
            )
        )
        compiled = MODULE.compile_profile(payload)
        hypothesis = compiled["hypotheses"][0]
        self.assertEqual(hypothesis["hypothesis_type"], "DESTINO_OU_LUGAR_FAMILIAR")
        self.assertTrue(hypothesis["spatialized"])
        self.assertEqual(hypothesis["spatial_status"], "ESPACIALIZADA")
        self.assertEqual(hypothesis["associated_location"]["latitude"], 0.002)
        self.assertFalse(hypothesis["ranking_effect_applied"])

    def test_structured_observed_direction_is_preserved(self) -> None:
        payload = base_payload()
        payload["clues"].append(
            clue(
                "P-DIRECAO",
                "DIRECAO_OBSERVADA",
                "Testemunha observou deslocamento em rumo aproximado.",
                evidence("OBSERVADO", "TESTEMUNHA", "ALTA", True),
                "ESPACIALIZADA",
                associated_location={
                    "label": "Origem da observação",
                    "feature_type": "PONTO_OBSERVACAO",
                    "latitude": 0.01,
                    "longitude": -51.07,
                    "geometry_reference": None,
                },
                direction_data={
                    "origin_role": "PONTO_INICIAL",
                    "azimuth_deg": 190.0,
                    "cardinal_direction": None,
                    "angular_tolerance_deg": 22.5,
                    "observation_method": "TESTEMUNHO",
                },
            )
        )
        hypothesis = MODULE.compile_profile(payload)["hypotheses"][0]
        self.assertEqual(hypothesis["hypothesis_type"], "DIRECAO_OBSERVADA")
        self.assertTrue(hypothesis["spatialized"])
        self.assertTrue(hypothesis["directional_preference_allowed"])
        self.assertEqual(hypothesis["direction_data"]["azimuth_deg"], 190.0)

    def test_frozen_record_preserves_verified_freeze_metadata(self) -> None:
        payload = base_payload()
        frozen = MODULE.prepare_frozen_payload(payload, "2026-10-21T09:00:00-03:00")
        compiled = MODULE.compile_profile(frozen)
        self.assertEqual(compiled["source_record_status"], "CONGELADO")
        self.assertEqual(compiled["freeze_validation"]["status"], "VERIFIED")
        self.assertEqual(
            compiled["source_freeze_metadata"]["payload_sha256"],
            MODULE.calculate_freeze_payload_sha256(frozen),
        )

    def test_tampering_after_freeze_is_rejected(self) -> None:
        frozen = MODULE.prepare_frozen_payload(
            base_payload(), "2026-10-21T09:00:00-03:00"
        )
        frozen["search_context"]["weather_summary"] = "Alterado após o congelamento"
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.compile_profile(frozen)

    def test_freeze_hash_projection_omits_only_its_own_digest(self) -> None:
        frozen = MODULE.prepare_frozen_payload(
            base_payload(), "2026-10-21T09:00:00-03:00"
        )
        expected = MODULE.calculate_freeze_payload_sha256(frozen)
        changed_digest = copy.deepcopy(frozen)
        changed_digest["freeze_metadata"]["payload_sha256"] = "f" * 64
        self.assertEqual(
            MODULE.calculate_freeze_payload_sha256(changed_digest), expected
        )
        projection = MODULE.freeze_payload_projection(frozen)
        self.assertNotIn("payload_sha256", projection["freeze_metadata"])
        self.assertEqual(projection["freeze_metadata"]["frozen_at"], "2026-10-21T09:00:00-03:00")

    def test_cli_prepares_separate_frozen_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "rascunho.json"
            output_path = Path(directory) / "congelado.json"
            input_path.write_text(
                json.dumps(base_payload(), ensure_ascii=False), encoding="utf-8"
            )
            result = MODULE.main(
                [
                    "--input",
                    str(input_path),
                    "--prepare-freeze",
                    "--frozen-at",
                    "2026-10-21T09:00:00-03:00",
                    "--output",
                    str(output_path),
                ]
            )
            self.assertEqual(result, 0)
            self.assertEqual(MODULE.load_input(input_path)["record_status"], "RASCUNHO")
            frozen = MODULE.load_input(output_path)
            self.assertEqual(frozen["record_status"], "CONGELADO")
            MODULE.validate_input(frozen)

    def test_duplicate_fact_or_clue_id_is_rejected(self) -> None:
        payload = base_payload()
        payload["victim_profile"]["mobility"]["fact_id"] = "F-IDADE"
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.compile_profile(payload)

    def test_suspicion_is_not_upgraded(self) -> None:
        payload = base_payload()
        payload["clues"].append(
            clue(
                "P-ISOLAMENTO",
                "ISOLAMENTO",
                "Há suspeita de procura por local isolado.",
                evidence("SUSPEITO", "FAMILIAR", "BAIXA", True),
                "CONTEXTUAL_NAO_DIRECIONAL",
            )
        )
        compiled = MODULE.compile_profile(payload)
        support = compiled["hypotheses"][0]["supports"][0]
        self.assertEqual(support["nature"], "SUSPEITO")
        self.assertEqual(support["confidence"], "BAIXA")
        self.assertTrue(compiled["hypotheses"][0]["evidence_nature_preserved"])

    def test_determinism(self) -> None:
        payload = base_payload()
        payload["clues"].append(
            clue(
                "P-ABRIGO",
                "ABRIGO",
                "Relato de possível procura por abrigo.",
                evidence("RELATADO", "TESTEMUNHA", "MEDIA", True),
                "ESPACIALIZAVEL_PENDENTE",
            )
        )
        first = MODULE.compile_profile(copy.deepcopy(payload))
        second = MODULE.compile_profile(copy.deepcopy(payload))
        self.assertEqual(MODULE.canonical_json_bytes(first), MODULE.canonical_json_bytes(second))
        self.assertEqual(first["compiled_sha256"], second["compiled_sha256"])


class EvidenceAndTemporalCoherenceTest(unittest.TestCase):
    def test_unavailable_value_cannot_be_authorized(self) -> None:
        payload = base_payload()
        payload["victim_profile"]["mobility"]["evidence"] = evidence(
            "RELATADO", "FAMILIAR", "MEDIA", True
        )
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.compile_profile(payload)

    def test_unavailable_value_cannot_have_high_confidence(self) -> None:
        payload = base_payload()
        payload["victim_profile"]["mobility"]["evidence"] = evidence(
            "RELATADO", "FAMILIAR", "ALTA", False
        )
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.compile_profile(payload)

    def test_known_authorized_value_requires_identified_source(self) -> None:
        payload = base_payload()
        payload["victim_profile"]["mobility"] = {
            "fact_id": "F-MOBILIDADE",
            "value": "NORMAL",
            "evidence": evidence("RELATADO", "NAO_DISPONIVEL", "MEDIA", True),
        }
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.compile_profile(payload)

    def test_planning_point_cannot_be_after_collection(self) -> None:
        payload = base_payload()
        payload["last_planning_point"]["timestamp"] = "2026-10-21T08:11:00-03:00"
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.compile_profile(payload)

    def test_freeze_cannot_precede_collection(self) -> None:
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.prepare_frozen_payload(
                base_payload(), "2026-10-21T08:09:00-03:00"
            )

    def test_calculated_elapsed_minutes_must_match_timestamps(self) -> None:
        payload = base_payload()
        payload["search_context"].update(
            {
                "elapsed_minutes": 20.0,
                "elapsed_status": "CALCULADO",
                "elapsed_source": "Diferença entre horários registrados",
            }
        )
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.compile_profile(payload)

    def test_calculated_elapsed_minutes_accept_exact_interval(self) -> None:
        payload = base_payload()
        payload["search_context"].update(
            {
                "elapsed_minutes": 10.0,
                "elapsed_status": "CALCULADO",
                "elapsed_source": "Diferença entre horários registrados",
            }
        )
        compiled = MODULE.compile_profile(payload)
        self.assertEqual(compiled["search_context"]["elapsed_minutes"], 10.0)

    def test_informed_elapsed_must_match_an_exact_point_with_minute_tolerance(self) -> None:
        payload = base_payload()
        payload["search_context"].update(
            {
                "elapsed_minutes": 20.0,
                "elapsed_status": "INFORMADO",
                "elapsed_source": "Operador da ocorrência",
            }
        )
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.compile_profile(payload)


if __name__ == "__main__":
    unittest.main()
