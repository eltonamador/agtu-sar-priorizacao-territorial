#!/usr/bin/env python3
"""Testes do contrato acrescentado pelo invólucro RURAL-01."""

from __future__ import annotations

import importlib.util
import math
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "run_rural01_blind.py"
SPEC = importlib.util.spec_from_file_location("run_rural01_blind", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Falha ao carregar run_rural01_blind.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class Rural01ContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.motor = MODULE._load_motor()
        self.overlay = MODULE._load_json(MODULE.OVERLAY_CONFIG_PATH)
        self.config = MODULE.build_effective_config(self.motor, self.overlay)

    def test_frozen_input(self) -> None:
        upstream = self.overlay["upstream"]
        self.assertEqual(upstream["scenario_id"], "RURAL-01")
        self.assertEqual(upstream["candidate_id"], "RURAL-01-E0")
        self.assertAlmostEqual(upstream["estimated_lat"], 0.188611)
        self.assertAlmostEqual(upstream["estimated_lon"], -51.155556)
        self.assertAlmostEqual(upstream["source_radius_m"], 1500.0)
        self.assertEqual(upstream["radius_method"], "RAIO_DIRETO_SEM_BUFFER_ADAPTATIVO")
        self.assertEqual(upstream["r0_semantics"], "source_adjusted_final")
        self.assertFalse(upstream["additional_factors_applied_by_engine"])

    def test_no_contextual_leakage(self) -> None:
        control = self.config["execution_control"]
        self.assertFalse(control["adaptive_buffer_engine_used"])
        self.assertFalse(control["profile_used_in_quantitative_ranking"])
        self.assertFalse(control["directional_preference_applied"])
        self.assertFalse(control["photographs_used_in_quantitative_ranking"])
        self.assertFalse(control["ground_truth_used"])

    def test_top3_preserves_base_score(self) -> None:
        rows = []
        for index, score in enumerate((0.8, 0.7, 0.6, 0.5), start=1):
            rows.append(
                {
                    "scenario_id": "RURAL-01",
                    "candidate_id": "RURAL-01-E0",
                    "sector_id": f"RURAL-01::RURAL-01-E0::R01::T{index}",
                    "rank_base_within_buffer": index,
                    "score_base": score,
                    "ring_id": "R01",
                    "direction": "N",
                    "representative_lat": 0.0,
                    "representative_lon": 0.0,
                    "inner_radius_m": 0.0,
                    "outer_radius_m": 1.0,
                    "buffer_decision_status": "REVISAR",
                }
            )
        top3 = MODULE._top3_rows(rows)
        self.assertEqual(len(top3), 3)
        self.assertEqual([row["score"] for row in top3], [0.8, 0.7, 0.6])
        self.assertTrue(all(row["ranking_mode"] == "BASE" for row in top3))
        self.assertTrue(all(row["directional_preference_applied"] is False for row in top3))

    def test_source_area_uses_declared_radius(self) -> None:
        radius = float(self.overlay["upstream"]["source_radius_m"])
        self.assertAlmostEqual(math.pi * radius * radius, 7_068_583.470577034, places=6)


if __name__ == "__main__":
    unittest.main()
