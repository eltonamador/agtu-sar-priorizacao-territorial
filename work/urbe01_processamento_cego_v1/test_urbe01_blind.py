#!/usr/bin/env python3
"""Testes unitários das regras acrescentadas pelo invólucro URBE-01."""

from __future__ import annotations

import importlib.util
import math
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "run_urbe01_blind.py"
SPEC = importlib.util.spec_from_file_location("run_urbe01_blind", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Falha ao carregar run_urbe01_blind.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ProfileFormulaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.motor = MODULE._load_motor()
        self.overlay = MODULE._load_json(MODULE.OVERLAY_CONFIG_PATH)
        self.config = MODULE.build_effective_config(self.motor, self.overlay)

    def _row(self, sector_id: str, ring: int, direction: str) -> dict:
        return {
            "protocol_id": "URBE-BLIND-SET-v1.0",
            "scenario_id": "URBE-01",
            "candidate_id": "URBE-01-E0",
            "sector_id": sector_id,
            "ring_id": f"R{ring:02d}",
            "ring_index": ring,
            "direction": direction,
            "direction_index": 1,
            "representative_lat": 0.0,
            "representative_lon": 0.0,
            "inner_radius_m": 0.0,
            "outer_radius_m": 1.0,
            "geo02_score": 0.8,
            "geo03_score": 0.6,
            "geo04_score": 0.7,
            "geo05_score": 0.9,
            "water_distance_m": 750.0,
            "water_wetland_prop": 0.25,
            "road_density_km_km2": 1.0,
            "geo_completeness": 1.0,
            "score_base": 0.75,
            "rank_base_within_buffer": 1,
            "base_top_member": True,
            "buffer_decision_status": "REVISAR",
            "barrier_flags": "NAO_SINALIZADA",
            "ground_truth_used": False,
        }

    def test_formula_is_literal(self) -> None:
        row = self._row("URBE-01::URBE-01-E0::R01::N", 1, "N")
        result = MODULE.calculate_profile_ranking([row], self.config)[0]
        expected_base = 0.35 * 0.8 + 0.20 * 0.6 + 0.25 * 0.7 + 0.20 * 0.9
        expected_awater = math.exp(-1.0) * 0.6 * 0.75
        expected_isolation = 0.8 * 0.75
        expected_context = 0.60 * expected_awater + 0.40 * expected_isolation
        expected_final = 0.90 * expected_base + 0.10 * expected_context
        self.assertAlmostEqual(result["profile_base_score"], expected_base, places=8)
        self.assertAlmostEqual(result["profile_awater"], expected_awater, places=8)
        self.assertAlmostEqual(result["profile_aisolation"], expected_isolation, places=8)
        self.assertAlmostEqual(result["profile_context_score"], expected_context, places=8)
        self.assertAlmostEqual(result["profile_final_score"], expected_final, places=8)

    def test_ring_and_direction_do_not_change_score(self) -> None:
        first = self._row("URBE-01::URBE-01-E0::R01::N", 1, "N")
        second = self._row("URBE-01::URBE-01-E0::R03::SW", 3, "SW")
        second["base_top_member"] = False
        results = MODULE.calculate_profile_ranking([first, second], self.config)
        self.assertEqual(results[0]["profile_final_score"], results[1]["profile_final_score"])
        self.assertEqual(results[0]["profile_rank_within_buffer"], 1)
        self.assertEqual(results[1]["profile_rank_within_buffer"], 1)
        self.assertFalse(results[0]["profile_directional_preference_applied"])
        self.assertFalse(results[0]["profile_ring_penalty_applied"])

    def test_profile_context_is_bounded(self) -> None:
        row = self._row("URBE-01::URBE-01-E0::R01::N", 1, "N")
        result = MODULE.calculate_profile_ranking([row], self.config)[0]
        delta = abs(result["profile_final_score"] - 0.90 * result["profile_base_score"])
        self.assertLessEqual(delta, 0.10 + 1e-9)


if __name__ == "__main__":
    unittest.main()
