#!/usr/bin/env python3
"""Testes unitários do MATA-01 MOV-V v1."""

from __future__ import annotations

import copy
import importlib.util
import json
import math
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "motor_movimento_mata01_v1.py"
SPEC = importlib.util.spec_from_file_location("mata01_mov_tested", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Falha ao carregar o motor")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def config() -> dict:
    return json.loads((HERE / "config_mata01_mov_v1.json").read_text(encoding="utf-8"))


class DummyCell:
    def __init__(self, x: float, y: float) -> None:
        self.x_m = x
        self.y_m = y
        self.radial_distance_m = math.hypot(x, y)


class MataMovementTests(unittest.TestCase):
    def test_valid_configuration_passes(self) -> None:
        receipt = MODULE.validate_config(config())
        self.assertEqual(receipt["status"], "PASS")
        self.assertGreater(receipt["scanned_field_count"], 0)

    def test_forbidden_evaluation_coordinate_fails_recursively(self) -> None:
        altered = config()
        altered["nested"] = {"victim_lat": -0.2}
        with self.assertRaises(MODULE.MataMovementError):
            MODULE.validate_config(altered)

    def test_time_cannot_be_converted_to_distance(self) -> None:
        altered = config()
        altered["time_policy"]["convert_elapsed_to_distance"] = True
        with self.assertRaises(MODULE.MataMovementError):
            MODULE.validate_config(altered)

    def test_domain_is_not_a_movement_budget(self) -> None:
        current = config()
        self.assertFalse(current["grid"]["movement_budget_enabled"])
        self.assertFalse(current["grid"]["isochrone_enabled"])
        self.assertIn("NAO_DISTANCIA_PERCORRIDA", current["source"]["radius_semantics"])

    def test_water_and_wetland_are_labeled_as_proxy(self) -> None:
        current = config()
        landcover = current["resistance"]["landcover"]
        self.assertEqual(set(landcover["water_wet_proxy_codes"]), {80, 90})
        self.assertIn("NAO_IGARAPE_CONFIRMADO", landcover["water_wet_proxy_semantics"])
        self.assertGreater(landcover["landcover_by_code"]["80"], 1.0)
        self.assertGreater(landcover["landcover_by_code"]["90"], 1.0)

    def test_osm_hydro_absence_is_not_favorable(self) -> None:
        current = config()
        hydro = current["resistance"]["hydro"]
        self.assertFalse(hydro["use_in_numeric_cost"])
        self.assertIn("NAO_E_EVIDENCIA_FAVORAVEL", hydro["absence_policy"])

    def test_field_obstacles_remain_unspatialized(self) -> None:
        field = config()["resistance"]["field_obstacle"]
        self.assertFalse(field["records_available"])
        self.assertEqual(field["default_factor"], 1.0)

    def test_sector_assignment_is_clockwise_from_north(self) -> None:
        current = config()
        cases = [
            (DummyCell(0.0, 1000.0), "R01::N"),
            (DummyCell(1000.0, 1000.0), "R01::NE"),
            (DummyCell(1000.0, 0.0), "R01::E"),
            (DummyCell(0.0, -2500.0), "R02::S"),
            (DummyCell(-4000.0, 0.0), "R03::W"),
        ]
        for cell, suffix in cases:
            self.assertTrue(MODULE.sector_id_for_cell(cell, current).endswith(suffix))

    def test_representative_targets_cover_24_units(self) -> None:
        current = config()
        cells = {}
        resolution = 30.0
        half = 167
        for row in range(335):
            y = (half - row) * resolution
            for col in range(335):
                x = (col - half) * resolution
                if math.hypot(x, y) <= 5000.0:
                    cells[(row, col)] = DummyCell(x, y)
        targets = MODULE.representative_targets(cells, current)
        self.assertEqual(len(targets), 24)
        self.assertEqual(len({item["sector_id"] for item in targets}), 24)

    def test_hypotheses_remain_separate_and_unselected(self) -> None:
        current = config()
        self.assertIsNone(current["scenario_selection"]["selected_cost_scenario_id"])
        self.assertEqual(
            {item["id"] for item in current["hypotheses"]},
            {"H_REDE_DISPONIVEL", "H_FORA_REDE"},
        )

    def test_behavioral_clues_do_not_change_physical_cost(self) -> None:
        clues = config()["behavioral_clues"]
        self.assertTrue(clues["northbound_boot_marks"]["available"])
        self.assertFalse(clues["northbound_boot_marks"]["numeric_effect_in_mov_v"])
        self.assertFalse(clues["habit_follow_edges_and_streams"]["numeric_effect_in_mov_v"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
