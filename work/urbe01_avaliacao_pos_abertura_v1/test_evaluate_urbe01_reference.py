#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "evaluate_urbe01_reference.py"
SPEC = importlib.util.spec_from_file_location("evaluate_urbe01_reference", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Falha ao carregar módulo")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PostOpenEvaluationTest(unittest.TestCase):
    def test_two_independent_sector_methods_agree(self) -> None:
        result = MODULE.build_evaluation("2026-10-21T00:00:00-03:00")
        self.assertTrue(result["sector_identification"]["checks_agree"])
        self.assertEqual(
            result["sector_identification"]["geometry_check"]["primary_sector_conservative"],
            "URBE-01::URBE-01-E0::R02::S",
        )

    def test_frozen_ranks_and_top3_outcome(self) -> None:
        result = MODULE.build_evaluation("2026-10-21T00:00:00-03:00")
        modes = {item["ranking_mode"]: item for item in result["ranking_evaluation"]}
        self.assertEqual(modes["BASE"]["reference_rank_conservative"], 18)
        self.assertEqual(modes["PERFIL"]["reference_rank_conservative"], 19)
        self.assertFalse(modes["BASE"]["top3_covered"])
        self.assertFalse(modes["PERFIL"]["top3_covered"])

    def test_reference_is_inside_received_radius(self) -> None:
        result = MODULE.build_evaluation("2026-10-21T00:00:00-03:00")
        self.assertTrue(result["initial_point"]["reference_inside_source_radius"])
        self.assertGreater(result["initial_point"]["distance_to_reference_m"], 1400)
        self.assertLess(result["initial_point"]["distance_to_reference_m"], 1600)

    def test_boundary_distance_and_unknown_precision_are_explicit(self) -> None:
        result = MODULE.build_evaluation("2026-10-21T00:00:00-03:00")
        self.assertFalse(result["sector_identification"]["boundary_case"])
        boundary_distance = result["sector_identification"]["geometry_check"][
            "distance_to_nearest_sector_boundary_m"
        ]
        self.assertAlmostEqual(boundary_distance, 75.404, places=3)
        self.assertIsNone(result["reference"]["horizontal_precision_m"])
        self.assertEqual(result["reference"]["horizontal_precision_status"], "NAO_INFORMADA")
        self.assertEqual(
            result["sector_identification"]["precision_sensitivity_status"],
            "NAO_AVALIAVEL_SEM_PRECISAO_HORIZONTAL_DA_REFERENCIA",
        )

    def test_true_sector_diagnostics_are_copied_from_frozen_output(self) -> None:
        result = MODULE.build_evaluation("2026-10-21T00:00:00-03:00")
        diagnostic = result["true_sector_diagnostics_from_frozen_outputs"]
        self.assertAlmostEqual(diagnostic["geo02_road_trail_access_score"], 0.946207773)
        self.assertAlmostEqual(diagnostic["geo03_hydro_access_score"], 0.035359136)
        self.assertEqual(diagnostic["barrier_flags"], "BARREIRA_HIDRICA_POTENCIAL_ALTA")


if __name__ == "__main__":
    unittest.main()
