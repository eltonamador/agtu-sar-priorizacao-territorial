#!/usr/bin/env python3
"""Testes unitários do motor cego RURAL-01 MOV v2."""

from __future__ import annotations

import copy
import importlib.util
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "motor_movimento_v2.py"
SPEC = importlib.util.spec_from_file_location("motor_movimento_v2_tested", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Falha ao carregar motor_movimento_v2.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def minimal_config() -> dict:
    return {
        "protocol_id": "TEST-MOV-v2",
        "engine_version": "test",
        "guardrails": {
            "development_only": True,
            "confirmatory_eligible": False,
            "parameter_change_after_truth_opening": "FORBIDDEN",
        },
        "blind_control": {
            "blind_processing": True,
            "ground_truth_used": False,
            "reference_package_accessible_to_engine": False,
            "reference_opening_allowed_only_after_T4": True,
        },
        "scope": {
            "output_unit": "cost_m_equivalent",
            "output_is_probability": False,
        },
        "source": {
            "scenario_id": "RURAL-01",
            "candidate_id": "RURAL-01-E0",
            "point": {"latitude": 0.188611, "longitude": -51.155556},
            "radius_m": 1500.0,
            "elapsed_hours": 14.0,
            "elapsed_time_role": "CONTEXTO_SEM_CONVERSAO_AUTOMATICA_EM_DISTANCIA_OU_CUSTO",
            "ground_truth_available_to_engine": False,
        },
        "grid": {"resolution_m": 30.0, "movement_budget_cost_m": 1500.0},
        "scenario_selection": {
            "base_profile_id": "BASE",
            "selected_cost_scenario_id": None,
            "implicit_selection_forbidden": True,
        },
        "reference_cost_scenario": {
            "cost_scenario_id": "H_REDE_DISPONIVEL__BASE",
            "role": "REFERENCIAL_NAO_SELECIONADO",
            "selected": False,
        },
        "hypotheses": [
            {"id": "H_REDE_DISPONIVEL", "apply_network_discount": True},
            {"id": "H_FORA_REDE", "apply_network_discount": False},
        ],
        "sensitivity_profiles": [
            {
                "id": "BASE",
                "landcover_exponent": 1.0,
                "hydro_max_factor": 6.0,
                "slope_a": 4.0,
                "slope_b": 8.0,
                "slope_cap": 8.0,
            }
        ],
        "resistance": {
            "status": "HEURISTICA_DESENVOLVIMENTO_SUJEITA_A_SENSIBILIDADE",
            "landcover": {
                "landcover_by_code": {
                    "10": 2.8,
                    "20": 2.4,
                    "30": 1.2,
                    "40": 1.3,
                    "50": 1.1,
                    "60": 1.05,
                    "70": 4.0,
                    "80": 12.0,
                    "90": 5.0,
                    "95": 8.0,
                    "100": 2.0,
                },
            },
            "network": {
                "rasterization_tolerance_m": 22.0,
                "road_factor": 0.45,
                "trail_factor": 0.65,
                "landcover_overlap_policy": MODULE.NETWORK_OVERLAP_POLICY,
                "diagnostic_conflict_landcover_codes": [10, 20, 95],
            },
            "hydro": {
                "overlap_policy": MODULE.HYDRO_OVERLAP_POLICY,
                "deduplicate_with_landcover_codes": [80, 90, 95],
            },
            "field_obstacle": {"multipliers": {"DIFICIL": 3.0, "QUASE_INTRANSPONIVEL": 8.0}},
            "slope": {"diagnostic_slope_thresholds_deg": [20.0, 35.0]},
        },
        "known_limitations": [],
        "counterfactual_runs": [MODULE.HYDRO_DUPLICATION_COUNTERFACTUAL_ID],
        "outputs": {"include_ground_truth_payload": False},
        "freeze": {
            "freeze_before_ground_truth_opening": True,
            "configuration_change_requires_new_version": True,
        },
        "post_freeze_evaluation": {
            "enabled_before_reference_opening": False,
            "retuning_after_reference_opening": False,
        },
        "firewall": {
            "enabled": True,
            "recursive": True,
            "case_insensitive": True,
            "ground_truth_used_required_value": False,
            "open_reference_only_after_output_freeze": True,
            "violation_policy": "ABORT_EXECUTION",
            "scan_excludes": [
                "firewall.forbidden_fragments",
                "firewall.allowed_control_field",
                "firewall.scan_excludes",
            ],
            "allowed_control_field": "blind_control.ground_truth_used",
            "forbidden_fragments": sorted(MODULE.MANDATORY_FORBIDDEN_FRAGMENTS),
        },
    }


def make_cell(row: int, col: int, elevation: float, road: bool = False) -> MODULE.Cell:
    return MODULE.Cell(
        row=row,
        col=col,
        x_m=float(col * 30),
        y_m=float(-row * 30),
        lat=0.0,
        lon=0.0,
        radial_distance_m=math.hypot(row * 30, col * 30),
        elevation_m=elevation,
        slope_deg=0.0,
        relief_3x3_m=0.0,
        worldcover_code=30,
        road=road,
        sector_id="RURAL-01::RURAL-01-E0::R01::N",
    )


class MovementV2UnitTest(unittest.TestCase):
    def test_config_contract(self) -> None:
        MODULE.validate_config(minimal_config())

    def test_firewall_rejects_protected_coordinate(self) -> None:
        with self.assertRaises(MODULE.MovementContractError):
            MODULE.enforce_blind_firewall({"victim_lat": 0.1, "ground_truth_used": False})

    def test_firewall_rejects_aliases_in_keys_nested_strings_and_paths(self) -> None:
        config = minimal_config()
        cases = (
            ({"ground_truth_sector": "R01::N"}, ()),
            ({"nested": [{"note": "truth_coordinate=0.1,-51.1"}]}, ()),
            ({"evaluation_longitude": -51.1}, ()),
            ({"safe": True}, (Path("/tmp/reference_lat.csv"),)),
        )
        for payload, paths in cases:
            with self.subTest(payload=payload, paths=paths):
                with self.assertRaises(MODULE.MovementContractError):
                    MODULE.enforce_blind_firewall(payload, config, source_paths=paths)

    def test_firewall_rejects_invalid_blind_flags(self) -> None:
        mutations = (
            ("blind_processing", False),
            ("ground_truth_used", True),
            ("reference_package_accessible_to_engine", True),
            ("reference_opening_allowed_only_after_T4", False),
        )
        for key, value in mutations:
            config = minimal_config()
            config["blind_control"][key] = value
            with self.subTest(key=key):
                with self.assertRaises(MODULE.MovementContractError):
                    MODULE.validate_config(config)

    def test_config_rejects_disabled_safety_controls(self) -> None:
        mutations = (
            ("firewall", "enabled", False),
            ("firewall", "recursive", False),
            ("firewall", "case_insensitive", False),
            ("outputs", "include_ground_truth_payload", True),
            ("freeze", "freeze_before_ground_truth_opening", False),
            ("post_freeze_evaluation", "enabled_before_reference_opening", True),
            ("guardrails", "confirmatory_eligible", True),
        )
        for section, key, value in mutations:
            config = minimal_config()
            config[section][key] = value
            with self.subTest(section=section, key=key):
                with self.assertRaises(MODULE.MovementContractError):
                    MODULE.validate_config(config)

    def test_firewall_rejects_broad_scan_exclusion(self) -> None:
        config = minimal_config()
        config["firewall"]["scan_excludes"].append("source")
        with self.assertRaises(MODULE.MovementContractError):
            MODULE.validate_config(config)

    def test_legacy_primary_scenario_is_rejected(self) -> None:
        config = minimal_config()
        config["primary_cost_scenario_id"] = "H_REDE_DISPONIVEL__BASE"
        with self.assertRaises(MODULE.MovementContractError):
            MODULE.validate_config(config)

    def test_slope_is_symmetric_until_directional_calibration_exists(self) -> None:
        scenario = MODULE.cost_scenarios(minimal_config())[0]
        low = make_cell(0, 0, 10.0)
        high = make_cell(0, 1, 16.0)
        uphill = MODULE.slope_edge_multiplier(low, high, scenario)
        downhill = MODULE.slope_edge_multiplier(high, low, scenario)
        self.assertAlmostEqual(uphill, downhill)
        self.assertGreater(downhill, 1.0)

    def test_network_hypothesis_reduces_road_resistance(self) -> None:
        config = minimal_config()
        scenarios = {item["hypothesis_id"]: item for item in MODULE.cost_scenarios(config)}
        cell = make_cell(0, 0, 10.0, road=True)
        on_network = MODULE.cell_base_resistance(cell, config, scenarios["H_REDE_DISPONIVEL"])
        off_network = MODULE.cell_base_resistance(cell, config, scenarios["H_FORA_REDE"])
        self.assertAlmostEqual(on_network, 1.2 * 0.45)
        self.assertAlmostEqual(off_network, 1.2)

    def test_dijkstra_prefers_low_resistance_detour(self) -> None:
        config = minimal_config()
        scenario = MODULE.cost_scenarios(config)[0]
        cells = {(r, c): make_cell(r, c, 10.0) for r in range(3) for c in range(3)}
        # O centro direto é água; a rota diagonal pela faixa superior deve ser
        # mais barata que atravessar a célula de água.
        cells[(1, 1)].worldcover_code = 80
        distances, predecessors = MODULE.dijkstra_cost_surface(cells, (1, 0), config, scenario)
        path = MODULE.reconstruct_path((1, 2), predecessors)
        self.assertNotIn((1, 1), path)
        self.assertTrue(math.isfinite(distances[(1, 2)]))

    def test_transverse_barrier_with_gap_forces_path_through_opening(self) -> None:
        config = minimal_config()
        scenario = MODULE.cost_scenarios(config)[1]  # H_FORA_REDE__BASE
        cells = {(r, c): make_cell(r, c, 10.0) for r in range(5) for c in range(5)}
        barrier_cells = {(r, 2) for r in range(1, 5)}
        for key in barrier_cells:
            cells[key].worldcover_code = 80
        _, predecessors = MODULE.dijkstra_cost_surface(cells, (2, 0), config, scenario)
        path = MODULE.reconstruct_path((2, 4), predecessors)
        self.assertIn((0, 2), path)
        self.assertTrue(barrier_cells.isdisjoint(path))

    def test_network_corridor_is_preferred_only_when_hypothesis_enables_it(self) -> None:
        config = minimal_config()
        scenarios = {item["scenario_id"]: item for item in MODULE.cost_scenarios(config)}
        network_cells = {(r, c): make_cell(r, c, 10.0, road=(r == 1)) for r in range(5) for c in range(5)}
        off_cells = copy.deepcopy(network_cells)
        network_costs, network_predecessors = MODULE.dijkstra_cost_surface(
            network_cells, (2, 0), config, scenarios["H_REDE_DISPONIVEL__BASE"]
        )
        off_costs, off_predecessors = MODULE.dijkstra_cost_surface(
            off_cells, (2, 0), config, scenarios["H_FORA_REDE__BASE"]
        )
        network_path = MODULE.reconstruct_path((2, 4), network_predecessors)
        off_path = MODULE.reconstruct_path((2, 4), off_predecessors)
        self.assertGreaterEqual(sum(network_cells[key].road for key in network_path), 2)
        self.assertFalse(any(off_cells[key].road for key in off_path))
        self.assertLess(network_costs[(2, 4)], off_costs[(2, 4)])

    def test_uniform_surface_distance_is_proportional(self) -> None:
        config = minimal_config()
        scenario = MODULE.cost_scenarios(config)[1]  # H_FORA_REDE__BASE
        cells = {(r, c): make_cell(r, c, 10.0) for r in range(3) for c in range(3)}
        distances, _ = MODULE.dijkstra_cost_surface(cells, (1, 1), config, scenario)
        orthogonal = distances[(1, 2)]
        diagonal = distances[(0, 2)]
        self.assertAlmostEqual(diagonal / orthogonal, math.sqrt(2.0), places=6)

    def test_hydro_increases_cost_without_absolute_veto(self) -> None:
        config = minimal_config()
        scenario = MODULE.cost_scenarios(config)[1]
        clear = {(0, 0): make_cell(0, 0, 10.0), (0, 1): make_cell(0, 1, 10.0)}
        wet = {(0, 0): make_cell(0, 0, 10.0), (0, 1): make_cell(0, 1, 10.0)}
        wet[(0, 1)].hydro_severity = 1.0
        clear_cost, _ = MODULE.dijkstra_cost_surface(clear, (0, 0), config, scenario)
        wet_cost, _ = MODULE.dijkstra_cost_surface(wet, (0, 0), config, scenario)
        self.assertGreater(wet_cost[(0, 1)], clear_cost[(0, 1)])
        self.assertTrue(math.isfinite(wet_cost[(0, 1)]))

    def test_hydro_is_not_multiplied_twice_on_worldcover_water(self) -> None:
        config = minimal_config()
        scenarios = {item["scenario_id"]: item for item in MODULE.cost_scenarios(config)}
        cell = make_cell(0, 0, 10.0)
        cell.worldcover_code = 80
        cell.hydro_severity = 1.0
        base = MODULE.cell_component_factors(cell, config, scenarios["H_REDE_DISPONIVEL__BASE"])
        old_rule = MODULE.cell_component_factors(
            cell,
            config,
            scenarios["SENS__COM_DUPLICACAO_HIDRO_COBERTURA"],
        )
        self.assertEqual(base["hydro_factor"], 1.0)
        self.assertTrue(base["hydro_deduplication_applied"])
        self.assertEqual(old_rule["hydro_factor"], 6.0)
        self.assertFalse(old_rule["hydro_deduplication_applied"])

    def test_missing_dem_is_not_treated_as_favorable(self) -> None:
        scenario = MODULE.cost_scenarios(minimal_config())[0]
        valid = make_cell(0, 0, 10.0)
        missing = make_cell(0, 1, 10.0)
        missing.elevation_m = None
        with self.assertRaises(MODULE.MovementContractError):
            MODULE.slope_edge_multiplier(valid, missing, scenario)

    def test_missing_worldcover_is_invalid_and_requires_review(self) -> None:
        config = minimal_config()
        scenario = MODULE.cost_scenarios(config)[0]
        missing = make_cell(0, 0, 10.0)
        missing.worldcover_code = None
        with self.assertRaisesRegex(MODULE.MovementContractError, "WorldCover"):
            MODULE.landcover_resistance(missing, config, scenario)

    def test_strong_profile_cell_resistance_not_below_soft(self) -> None:
        config = minimal_config()
        soft = dict(MODULE.cost_scenarios(config)[0], landcover_exponent=0.75, hydro_max_factor=4.0)
        strong = dict(MODULE.cost_scenarios(config)[0], landcover_exponent=1.25, hydro_max_factor=9.0)
        cell = make_cell(0, 0, 10.0)
        cell.worldcover_code = 10
        cell.hydro_severity = 0.65
        self.assertGreaterEqual(
            MODULE.cell_base_resistance(cell, config, strong),
            MODULE.cell_base_resistance(cell, config, soft),
        )

    def test_reconstruct_path_reaches_origin(self) -> None:
        predecessors = {(0, 0): None, (0, 1): (0, 0), (1, 1): (0, 1)}
        self.assertEqual(MODULE.reconstruct_path((1, 1), predecessors), [(0, 0), (0, 1), (1, 1)])

    def test_top3_rank_band_includes_all_ties_at_cutoff(self) -> None:
        rows = [
            {"sector_id": "A", "mobility_rank_within_buffer": 1},
            {"sector_id": "B", "mobility_rank_within_buffer": 2},
            {"sector_id": "C", "mobility_rank_within_buffer": 3},
            {"sector_id": "D", "mobility_rank_within_buffer": 3},
            {"sector_id": "E", "mobility_rank_within_buffer": 5},
        ]
        selected = MODULE.select_rank_band(rows, 3)
        self.assertEqual([row["sector_id"] for row in selected], ["A", "B", "C", "D"])

    def test_manifest_integrity_positive_and_tamper_detection(self) -> None:
        config = minimal_config()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            protocol_path = root / "protocol.md"
            input_path = root / "input.json"
            output_path = root / "output.json"
            config_path.write_text(json.dumps(config, sort_keys=True), encoding="utf-8")
            protocol_path.write_text("protocolo de teste", encoding="utf-8")
            input_path.write_text('{"safe": true}', encoding="utf-8")
            output_path.write_text('{"result": "safe"}', encoding="utf-8")
            manifest = MODULE.build_manifest(
                config,
                config_path,
                protocol_path,
                [("input", input_path)],
                [("output", output_path)],
            )
            receipt = MODULE.verify_manifest_integrity(manifest, root)
            self.assertEqual(receipt["status"], "PASS")
            output_path.write_text('{"result": "altered"}', encoding="utf-8")
            with self.assertRaises(MODULE.MovementContractError):
                MODULE.verify_manifest_integrity(manifest, root)


if __name__ == "__main__":
    unittest.main()
