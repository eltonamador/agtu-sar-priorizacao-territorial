#!/usr/bin/env python3
"""Testes prospectivos do rankeador PERFIL V3."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "profile_ranker.py"
SPEC = importlib.util.spec_from_file_location("profile_ranker", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Falha ao carregar profile_ranker.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def sectors() -> list[dict]:
    return [
        {
            "sector_id": "SEC-N",
            "territorial_score": 0.60,
            "bearing_start_deg": 315.0,
            "bearing_end_deg": 45.0,
            "polygon": [[-1.0, 0.0], [0.0, 0.0], [1.0, 1.0], [-1.0, 1.0], [-1.0, 0.0]],
        },
        {
            "sector_id": "SEC-E",
            "territorial_score": 0.55,
            "bearing_start_deg": 45.0,
            "bearing_end_deg": 135.0,
            "polygon": [[0.0, -1.0], [1.0, -1.0], [1.0, 1.0], [0.0, 0.0], [0.0, -1.0]],
        },
        {
            "sector_id": "SEC-S",
            "territorial_score": 0.50,
            "bearing_start_deg": 135.0,
            "bearing_end_deg": 225.0,
            "polygon": [[-1.0, -1.0], [1.0, -1.0], [0.0, 0.0], [-1.0, -1.0]],
        },
        {
            "sector_id": "SEC-W",
            "territorial_score": 0.45,
            "bearing_start_deg": 225.0,
            "bearing_end_deg": 315.0,
            "polygon": [[-1.0, -1.0], [0.0, 0.0], [-1.0, 1.0], [-1.0, -1.0]],
        },
    ]


def draft_payload() -> dict:
    return {
        "protocol_version": "PERFIL-V3-QUANT-v1.0",
        "scenario_id": "TESTE-001",
        "candidate_id": "CAND-01",
        "record_status": "RASCUNHO",
        "created_at": "2026-10-21T10:00:00-03:00",
        "ground_truth_absent": True,
        "source_loc_input_sha256": "d" * 64,
        "source_case_revision": 1,
        "source_profile_compiled_sha256": "a" * 64,
        "source_territorial_manifest_sha256": "b" * 64,
        "source_spatial_review_sha256": "c" * 64,
        "sectors": sectors(),
        "hypotheses": [],
        "freeze_metadata": None,
    }


def direction(
    hypothesis_id: str = "H-DIR-01",
    group: str = "G-DIR-01",
    azimuth: float = 90.0,
    tolerance: float = 20.0,
    nature: str = "OBSERVADO",
    confidence: str = "ALTA",
    spatialized: bool = True,
    authorized: bool = True,
    origin_candidate_id: str = "CAND-01",
) -> dict:
    return {
        "hypothesis_id": hypothesis_id,
        "evidence_group_id": group,
        "family": "DIRECAO",
        "hypothesis_type": "DIRECAO_OBSERVADA",
        "spatialized": spatialized,
        "authorized_for_model": authorized,
        "nature": nature,
        "confidence": confidence,
        "direction": {
            "origin_candidate_id": origin_candidate_id,
            "azimuth_deg": azimuth,
            "tolerance_deg": tolerance,
        },
    }


def destination(
    hypothesis_id: str = "H-DST-01",
    group: str = "G-DST-01",
    latitude: float = -0.5,
    longitude: float = 0.5,
    nature: str = "RELATADO",
    confidence: str = "MEDIA",
    uncertainty_m: float = 25.0,
) -> dict:
    return {
        "hypothesis_id": hypothesis_id,
        "evidence_group_id": group,
        "family": "DESTINO",
        "hypothesis_type": "DESTINO_DECLARADO",
        "spatialized": True,
        "authorized_for_model": True,
        "nature": nature,
        "confidence": confidence,
        "destination": {
            "latitude": latitude,
            "longitude": longitude,
            "location_uncertainty_m": uncertainty_m,
            "spatial_source": "registro_teste",
        },
    }


def frozen(payload: dict) -> dict:
    return MODULE.prepare_frozen_input(payload, "2026-10-21T10:05:00-03:00")


def primary(result: dict) -> dict[str, dict]:
    return {row["sector_id"]: row for row in result["primary_rows"]}


class FirewallAndFreezeTest(unittest.TestCase):
    def test_rejects_ground_truth_nested(self) -> None:
        payload = draft_payload()
        payload["metadata"] = {"true_location": [0.0, 0.0]}
        with self.assertRaises(MODULE.GroundTruthFirewallError):
            MODULE.prepare_frozen_input(payload, "2026-10-21T10:05:00-03:00")

    def test_rejects_composite_ground_truth_alias(self) -> None:
        payload = draft_payload()
        payload["sectors"][0]["distance_to_ground_truth_m"] = 1.0
        with self.assertRaises(MODULE.GroundTruthFirewallError):
            MODULE.prepare_frozen_input(payload, "2026-10-21T10:05:00-03:00")

    def test_ground_truth_absent_control_must_be_true_at_every_depth(self) -> None:
        payload = draft_payload()
        payload["sectors"][0]["ground_truth_absent"] = False
        with self.assertRaises(MODULE.GroundTruthFirewallError):
            MODULE.prepare_frozen_input(payload, "2026-10-21T10:05:00-03:00")

    def test_rejects_textual_truth_marker(self) -> None:
        payload = draft_payload()
        payload["candidate_id"] = "ground_truth:teste"
        with self.assertRaises(MODULE.GroundTruthFirewallError):
            MODULE.prepare_frozen_input(payload, "2026-10-21T10:05:00-03:00")

    def test_tampering_after_freeze_is_rejected(self) -> None:
        payload = frozen(draft_payload())
        payload["sectors"][0]["territorial_score"] = 0.99
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.rank_profile(payload)

    def test_unknown_extra_field_is_rejected(self) -> None:
        payload = draft_payload()
        payload["unexpected_note"] = "conteúdo não previsto"
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.prepare_frozen_input(payload, "2026-10-21T10:05:00-03:00")

    def test_freeze_cannot_precede_creation(self) -> None:
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.prepare_frozen_input(draft_payload(), "2026-10-21T09:59:00-03:00")

    def test_deterministic_output_and_hash(self) -> None:
        payload = draft_payload()
        payload["hypotheses"] = [direction()]
        package = frozen(payload)
        first = MODULE.rank_profile(copy.deepcopy(package))
        second = MODULE.rank_profile(copy.deepcopy(package))
        self.assertEqual(MODULE.canonical_json_bytes(first), MODULE.canonical_json_bytes(second))
        self.assertEqual(first["output_sha256"], second["output_sha256"])

    def test_runtime_rejects_identifier_outside_schema_pattern(self) -> None:
        payload = draft_payload()
        payload["scenario_id"] = "identificador com espaços"
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.prepare_frozen_input(payload, "2026-10-21T10:05:00-03:00")

    def test_runtime_requires_source_hashes_as_strings(self) -> None:
        for field in (
            "source_loc_input_sha256",
            "source_profile_compiled_sha256",
            "source_territorial_manifest_sha256",
            "source_spatial_review_sha256",
        ):
            with self.subTest(field=field):
                payload = draft_payload()
                payload[field] = int("1" * 64)
                with self.assertRaises(MODULE.InputValidationError):
                    MODULE.prepare_frozen_input(payload, "2026-10-21T10:05:00-03:00")

    def test_source_case_revision_must_be_positive_integer(self) -> None:
        for invalid in (True, 0, -1, "1"):
            with self.subTest(invalid=invalid):
                payload = draft_payload()
                payload["source_case_revision"] = invalid
                with self.assertRaises(MODULE.InputValidationError):
                    MODULE.prepare_frozen_input(payload, "2026-10-21T10:05:00-03:00")

    def test_hypothesis_requires_spatial_review_hash(self) -> None:
        payload = draft_payload()
        payload["source_spatial_review_sha256"] = None
        payload["hypotheses"] = [direction()]
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.prepare_frozen_input(payload, "2026-10-21T10:05:00-03:00")

    def test_runtime_enforces_spatial_source_string_contract(self) -> None:
        for invalid_source in (123, " ", "x" * 257):
            with self.subTest(invalid_source=invalid_source):
                payload = draft_payload()
                hypothesis = destination()
                hypothesis["destination"]["spatial_source"] = invalid_source
                payload["hypotheses"] = [hypothesis]
                with self.assertRaises(MODULE.InputValidationError):
                    MODULE.prepare_frozen_input(
                        payload, "2026-10-21T10:05:00-03:00"
                    )

    def test_frozen_config_status_is_accepted_and_reported(self) -> None:
        config = json.loads(MODULE.DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
        config["status"] = "CONGELADO"
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.json"
            config_path.write_text(
                json.dumps(config, ensure_ascii=False), encoding="utf-8"
            )
            result = MODULE.rank_profile(frozen(draft_payload()), config_path)
        self.assertEqual(result["config_status"], "CONGELADO")

    def test_runtime_rejects_changed_ranking_governance(self) -> None:
        mutations = (
            ("method", "DENSE_RANK"),
            ("score_comparison_decimals", 0),
            ("tie_break_is_substantive", True),
            ("low_margin_threshold_diagnostic", 0.20),
            ("low_margin_is_validated", True),
            ("unstable_top_set_status", "APLICAR"),
            ("unstable_top_set_operational_effect", True),
            ("unstable_top_set_operational_rows", "PRIMARY"),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                config = json.loads(
                    MODULE.DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
                )
                config["ranking"][field] = value
                with tempfile.TemporaryDirectory() as temporary_directory:
                    config_path = Path(temporary_directory) / "config.json"
                    config_path.write_text(
                        json.dumps(config, ensure_ascii=False), encoding="utf-8"
                    )
                    with self.assertRaises(MODULE.InputValidationError):
                        MODULE.rank_profile(frozen(draft_payload()), config_path)


class QuantitativeRulesTest(unittest.TestCase):
    def test_no_profile_abstains_and_returns_territorial_exactly(self) -> None:
        result = MODULE.rank_profile(frozen(draft_payload()))
        self.assertTrue(result["abstained"])
        for sensitivity in result["lambda_results"]:
            for row in sensitivity["rows"]:
                self.assertEqual(row["profile_score"], row["territorial_score"])
                self.assertEqual(row["profile_delta"], 0.0)

    def test_unknown_evidence_has_no_effect(self) -> None:
        payload = draft_payload()
        payload["hypotheses"] = [direction(nature="NAO_DISPONIVEL", confidence="NAO_AVALIADA")]
        result = MODULE.rank_profile(frozen(payload))
        self.assertTrue(result["abstained"])
        self.assertEqual(result["excluded_hypotheses"][0]["reason"], "QUALIDADE_SEM_EFEITO")

    def test_observed_direction_favors_overlapping_sector(self) -> None:
        payload = draft_payload()
        payload["hypotheses"] = [direction()]
        result = MODULE.rank_profile(frozen(payload))
        rows = primary(result)
        self.assertFalse(result["abstained"])
        self.assertGreater(rows["SEC-E"]["profile_delta"], rows["SEC-N"]["profile_delta"])
        self.assertGreater(rows["SEC-E"]["profile_compatibility"], 0.0)
        self.assertGreater(
            rows["SEC-E"]["profile_compatibility"], rows["SEC-N"]["profile_compatibility"]
        )

    def test_low_quality_evidence_has_smaller_effect(self) -> None:
        strong_payload = draft_payload()
        strong_payload["hypotheses"] = [direction()]
        weak_payload = draft_payload()
        weak_payload["hypotheses"] = [
            direction(nature="SUSPEITO", confidence="BAIXA")
        ]
        strong = primary(MODULE.rank_profile(frozen(strong_payload)))["SEC-E"]
        weak = primary(MODULE.rank_profile(frozen(weak_payload)))["SEC-E"]
        self.assertGreater(abs(strong["profile_delta"]), abs(weak["profile_delta"]))
        self.assertAlmostEqual(weak["effective_lambda"], strong["effective_lambda"] / 3.0)

    def test_duplicate_evidence_group_does_not_stack(self) -> None:
        single_payload = draft_payload()
        single_payload["hypotheses"] = [direction()]
        duplicate_payload = draft_payload()
        duplicate_payload["hypotheses"] = [
            direction(),
            direction(hypothesis_id="H-DIR-02", group="G-DIR-01"),
        ]
        single = MODULE.rank_profile(frozen(single_payload))
        duplicate = MODULE.rank_profile(frozen(duplicate_payload))
        self.assertEqual(single["primary_rows"], duplicate["primary_rows"])
        self.assertEqual(
            duplicate["group_records"][0]["duplicates_or_alternatives_collapsed"], 1
        )

    def test_same_evidence_group_cannot_stack_across_families(self) -> None:
        payload = draft_payload()
        payload["hypotheses"] = [direction(group="G-SHARED"), destination(group="G-SHARED")]
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.prepare_frozen_input(payload, "2026-10-21T10:05:00-03:00")

    def test_destination_inside_sector_is_spatialized(self) -> None:
        payload = draft_payload()
        payload["hypotheses"] = [destination()]
        result = MODULE.rank_profile(frozen(payload))
        rows = primary(result)
        self.assertFalse(result["abstained"])
        self.assertEqual(rows["SEC-E"]["profile_compatibility"], 1.0)
        self.assertEqual(rows["SEC-W"]["profile_compatibility"], 0.0)

    def test_large_destination_uncertainty_abstains_when_all_sectors_overlap(self) -> None:
        payload = draft_payload()
        payload["hypotheses"] = [destination(uncertainty_m=500_000.0)]
        result = MODULE.rank_profile(frozen(payload))
        self.assertTrue(result["abstained"])
        self.assertEqual(result["operational_status"], "ABSTENCAO_PERFIL")
        self.assertIn("INCERTEZA_DESTINO_NAO_DISCRIMINANTE_REVISAR", result["warnings"])
        self.assertEqual(
            result["excluded_hypotheses"][0]["reason"],
            "INCERTEZA_DESTINO_NAO_DISCRIMINANTE",
        )
        for row in result["operational_rows"]:
            self.assertEqual(row["profile_score"], row["territorial_score"])

    def test_destination_outside_domain_abstains_without_edge_projection(self) -> None:
        payload = draft_payload()
        payload["hypotheses"] = [destination(latitude=10.0, longitude=10.0)]
        result = MODULE.rank_profile(frozen(payload))
        self.assertTrue(result["abstained"])
        self.assertIn("DESTINO_FORA_DO_DOMINIO_SEM_PROJECAO_A_BORDA", result["warnings"])
        for row in result["primary_rows"]:
            self.assertEqual(row["profile_score"], row["territorial_score"])

    def test_non_spatialized_hypothesis_abstains(self) -> None:
        payload = draft_payload()
        payload["hypotheses"] = [direction(spatialized=False)]
        result = MODULE.rank_profile(frozen(payload))
        self.assertTrue(result["abstained"])
        self.assertEqual(result["excluded_hypotheses"][0]["reason"], "NAO_ESPACIALIZADA")

    def test_conflicting_directions_are_flagged(self) -> None:
        payload = draft_payload()
        payload["hypotheses"] = [
            direction(group="G-1", azimuth=0.0, tolerance=10.0),
            direction(hypothesis_id="H-DIR-02", group="G-2", azimuth=180.0, tolerance=10.0),
        ]
        result = MODULE.rank_profile(frozen(payload))
        self.assertIn("DIRECOES_INDEPENDENTES_CONFLITANTES_REVISAR", result["warnings"])

    def test_ineligible_directions_do_not_create_conflict_warning(self) -> None:
        variants = (
            {"authorized": False},
            {"spatialized": False},
            {"nature": "NAO_DISPONIVEL", "confidence": "NAO_AVALIADA"},
        )
        for index, variant in enumerate(variants, start=1):
            with self.subTest(variant=variant):
                payload = draft_payload()
                payload["hypotheses"] = [
                    direction(group="G-1", azimuth=0.0, tolerance=10.0),
                    direction(
                        hypothesis_id=f"H-DIR-X{index}",
                        group=f"G-X{index}",
                        azimuth=180.0,
                        tolerance=10.0,
                        **variant,
                    ),
                ]
                result = MODULE.rank_profile(frozen(payload))
                self.assertNotIn(
                    "DIRECOES_INDEPENDENTES_CONFLITANTES_REVISAR",
                    result["warnings"],
                )

    def test_direction_origin_must_match_candidate(self) -> None:
        payload = draft_payload()
        payload["hypotheses"] = [direction(origin_candidate_id="OUTRO-CANDIDATO")]
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.prepare_frozen_input(payload, "2026-10-21T10:05:00-03:00")

    def test_unstable_top1_returns_exact_territorial_operational_rows(self) -> None:
        payload = draft_payload()
        payload["sectors"][0]["territorial_score"] = 0.53
        payload["sectors"][1]["territorial_score"] = 0.50
        payload["sectors"][2]["territorial_score"] = 0.10
        payload["sectors"][3]["territorial_score"] = 0.10
        payload["hypotheses"] = [direction(azimuth=90.0, tolerance=20.0)]
        result = MODULE.rank_profile(frozen(payload))
        lambda_005 = next(item for item in result["lambda_results"] if item["lambda"] == 0.05)
        lambda_010 = next(item for item in result["lambda_results"] if item["lambda"] == 0.10)
        self.assertEqual(lambda_005["top_set"], ["SEC-N"])
        self.assertEqual(lambda_010["top_set"], ["SEC-E"])
        self.assertFalse(result["operational_effect_applied"])
        self.assertEqual(result["operational_status"], "REVISAR_INSTABILIDADE")
        for row in result["operational_rows"]:
            self.assertEqual(row["profile_score"], row["territorial_score"])
            self.assertEqual(row["profile_delta"], 0.0)

    def test_lambda_zero_is_exact_territorial_ablation(self) -> None:
        payload = draft_payload()
        payload["hypotheses"] = [direction()]
        result = MODULE.rank_profile(frozen(payload))
        zero = next(item for item in result["lambda_results"] if item["lambda"] == 0.0)
        for row in zero["rows"]:
            self.assertEqual(row["profile_score"], row["territorial_score"])
            self.assertEqual(row["effective_lambda"], 0.0)

    def test_primary_lambda_and_operational_ceiling_are_ten_percent(self) -> None:
        result = MODULE.rank_profile(frozen(draft_payload()))
        self.assertEqual(result["primary_lambda"], 0.10)
        stress = next(item for item in result["lambda_results"] if item["lambda"] == 0.15)
        self.assertEqual(stress["role"], "ESTRESSE_FORA_DO_TETO_OPERACIONAL")

    def test_disallowed_family_is_rejected(self) -> None:
        payload = draft_payload()
        item = direction()
        item["family"] = "COGNICAO"
        payload["hypotheses"] = [item]
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.prepare_frozen_input(payload, "2026-10-21T10:05:00-03:00")


class GeometryTest(unittest.TestCase):
    def test_direction_wrap_around(self) -> None:
        north = sectors()[0]
        value = MODULE.direction_compatibility(
            north, {"azimuth_deg": 0.0, "tolerance_deg": 20.0}
        )
        self.assertGreater(value, 0.0)

    def test_boundary_destination_can_match_multiple_sectors(self) -> None:
        matches = [
            sector["sector_id"]
            for sector in sectors()
            if MODULE.destination_compatibility(
                sector,
                {"latitude": 0.0, "longitude": 0.0},
            )
            > 0
        ]
        self.assertGreaterEqual(len(matches), 2)

    def test_positive_uncertainty_intersects_sector_edge(self) -> None:
        sector = {
            "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
        }
        outside = {
            "latitude": 0.5,
            "longitude": -0.0001,
            "location_uncertainty_m": 0.0,
        }
        uncertain = dict(outside, location_uncertainty_m=20.0)
        self.assertEqual(MODULE.destination_compatibility(sector, outside), 0.0)
        self.assertEqual(MODULE.destination_compatibility(sector, uncertain), 1.0)

    def test_destination_geometry_handles_antimeridian(self) -> None:
        sector = {
            "polygon": [
                [179.8, -0.2],
                [-179.8, -0.2],
                [-179.8, 0.2],
                [179.8, 0.2],
                [179.8, -0.2],
            ]
        }
        destination_value = {
            "latitude": 0.0,
            "longitude": 179.9,
            "location_uncertainty_m": 0.0,
        }
        self.assertEqual(
            MODULE.destination_compatibility(sector, destination_value), 1.0
        )

    def test_zero_width_sector_is_rejected(self) -> None:
        payload = draft_payload()
        payload["sectors"][0]["bearing_start_deg"] = 0.0
        payload["sectors"][0]["bearing_end_deg"] = 360.0
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.prepare_frozen_input(payload, "2026-10-21T10:05:00-03:00")

    def test_destination_at_pole_is_rejected_by_local_projection_contract(self) -> None:
        payload = draft_payload()
        payload["hypotheses"] = [destination(latitude=90.0, uncertainty_m=0.0)]
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.prepare_frozen_input(payload, "2026-10-21T10:05:00-03:00")

    def test_zero_area_sector_polygon_is_rejected(self) -> None:
        payload = draft_payload()
        payload["sectors"][0]["polygon"] = [
            [0.0, 0.0],
            [1.0, 0.0],
            [2.0, 0.0],
            [0.0, 0.0],
        ]
        with self.assertRaises(MODULE.InputValidationError):
            MODULE.prepare_frozen_input(payload, "2026-10-21T10:05:00-03:00")


if __name__ == "__main__":
    unittest.main()

