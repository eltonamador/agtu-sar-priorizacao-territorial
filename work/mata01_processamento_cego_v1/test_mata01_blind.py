#!/usr/bin/env python3
"""Testes do contrato acrescentado pelo invólucro MATA-01."""

from __future__ import annotations

import importlib.util
import math
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "run_mata01_blind.py"
SPEC = importlib.util.spec_from_file_location("run_mata01_blind", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Falha ao carregar run_mata01_blind.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class Mata01ContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.motor = MODULE._load_motor()
        self.overlay = MODULE._load_json(MODULE.OVERLAY_CONFIG_PATH)
        self.config = MODULE.build_effective_config(self.motor, self.overlay)

    def test_frozen_input(self) -> None:
        upstream = self.overlay["upstream"]
        self.assertEqual(upstream["scenario_id"], "MATA-01")
        self.assertEqual(upstream["candidate_id"], "MATA-01-E0")
        self.assertAlmostEqual(upstream["estimated_lat"], -0.172222)
        self.assertAlmostEqual(upstream["estimated_lon"], -51.430278)
        self.assertAlmostEqual(upstream["source_radius_m"], 5000.0)
        self.assertEqual(upstream["radius_method"], "DOMINIO_OPERACIONAL_DIRETO_SEM_BUFFER_ADAPTATIVO")
        self.assertEqual(upstream["r0_semantics"], "source_declared_operational_domain")
        self.assertFalse(upstream["additional_factors_applied_by_engine"])
        self.assertFalse(upstream["detection_quality_available"])

    def test_no_contextual_or_missing_data_leakage(self) -> None:
        control = self.config["execution_control"]
        self.assertFalse(control["adaptive_buffer_engine_used"])
        self.assertFalse(control["missing_detection_quality_imputed"])
        self.assertFalse(control["profile_used_in_quantitative_ranking"])
        self.assertFalse(control["directional_preference_applied"])
        self.assertFalse(control["photographs_used_in_quantitative_ranking"])
        self.assertFalse(control["ground_truth_used"])

    def test_expected_local_tiles(self) -> None:
        self.assertTrue((MODULE.DEFAULT_GEO_DIR / "S01W052.hgt.gz").exists())
        self.assertTrue(
            (
                MODULE.DEFAULT_GEO_DIR
                / "worldcover_tiles/ESA_WorldCover_10m_2021_v200_S03W054_Map.tif"
            ).exists()
        )

    def test_top3_preserves_base_score(self) -> None:
        rows = []
        for index, score in enumerate((0.8, 0.7, 0.6, 0.5), start=1):
            rows.append(
                {
                    "scenario_id": "MATA-01",
                    "candidate_id": "MATA-01-E0",
                    "sector_id": f"MATA-01::MATA-01-E0::R01::T{index}",
                    "rank_base_available_within_buffer": index,
                    "score_base_available": score,
                    "ring_id": "R01",
                    "direction": "N",
                    "representative_lat": 0.0,
                    "representative_lon": 0.0,
                    "inner_radius_m": 0.0,
                    "outer_radius_m": 1.0,
                    "buffer_decision_status": "REVISAR",
                    "geo02_score": 0.1,
                    "geo03_score": None,
                    "geo04_score": 0.2,
                    "geo05_score": 0.3,
                }
            )
        top3 = MODULE._top3_rows(rows)
        self.assertEqual(len(top3), 3)
        self.assertEqual([row["score"] for row in top3], [0.8, 0.7, 0.6])
        self.assertTrue(all(row["ranking_mode"] == "BASE_DISPONIVEIS_DIAGNOSTICO" for row in top3))
        self.assertTrue(all(row["directional_preference_applied"] is False for row in top3))

    def test_sampling_override_is_dense_and_deterministic(self) -> None:
        sampling = self.config["feature_extraction"]["raster_sampling"]
        self.assertEqual(sampling["radial_samples"], 60)
        self.assertEqual(sampling["angular_samples"], 60)
        self.assertEqual(sampling["samples_per_sector"], 3600)

    def test_available_weights_are_exact_renormalization(self) -> None:
        weights = self.overlay["ranking"]["available_modules_weights"]
        self.assertAlmostEqual(weights["GEO02"], 0.30 / 0.75)
        self.assertAlmostEqual(weights["GEO04"], 0.20 / 0.75)
        self.assertAlmostEqual(weights["GEO05"], 0.25 / 0.75)
        self.assertEqual(weights["GEO03"], 0.0)
        self.assertAlmostEqual(sum(weights.values()), 1.0)

    def test_source_area_uses_declared_domain(self) -> None:
        radius = float(self.overlay["upstream"]["source_radius_m"])
        self.assertAlmostEqual(math.pi * radius * radius, 78_539_816.33974483, places=5)


if __name__ == "__main__":
    unittest.main()
