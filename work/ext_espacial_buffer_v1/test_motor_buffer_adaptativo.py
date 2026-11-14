#!/usr/bin/env python3
"""Testes de aceitação do motor EXT-ESP-BUF-v1.0."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import motor_buffer_adaptativo as engine


def valid_row(**updates):
    row = {
        "scenario_id": "T-001",
        "candidate_id": "T-001-C1",
        # Coordenadas deliberadamente sintéticas: servem apenas como fixture.
        "estimated_lat": "12.345678",
        "estimated_lon": "-45.678901",
        "base_radius_m": "2000",
        "detection_quality": "0.8",
        "environment_class": "MATA",
        "position_dispersion_m": "25",
        "information_age_min": "90",
        "r0_semantics": "nominal_base",
        "factors_applied": "none",
        "r0_provenance": "PROTOCOLO_CONGELADO",
        "data_origin": "TESTE_UNITARIO",
        "source_row_hash": "abc123",
        "execution_phase": "REP_S_INDEPENDENTE",
    }
    row.update(updates)
    return row


def haversine_m(lat1, lon1, lat2, lon2):
    radius = engine.EARTH_RADIUS_M
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


class BufferEngineTestCase(unittest.TestCase):
    def setUp(self):
        self.config = engine.frozen_config_copy()

    def calculate(self, **updates):
        return engine.compute_record(valid_row(**updates), self.config)

    def test_nominal_formula_exact(self):
        result = self.calculate()
        expected_fq = 1 + 0.5 * (1 - 0.8)
        expected_fe = 1.25
        expected_fs = 1 + 0.5 * (25 / 50)
        expected_ft = 1 + 0.5 * (90 / 180)
        expected_radius = 2000 * expected_fq * expected_fe * expected_fs * expected_ft
        self.assertAlmostEqual(result["f_q"], expected_fq, places=9)
        self.assertAlmostEqual(result["f_s"], expected_fs, places=9)
        self.assertAlmostEqual(result["f_t"], expected_ft, places=9)
        self.assertAlmostEqual(result["raw_radius_m"], expected_radius, places=6)
        self.assertEqual(result["adaptive_radius_m"], result["raw_radius_m"])
        self.assertEqual(result["clamp_status"], "NONE")
        self.assertFalse(result["ground_truth_used"])

    def test_quality_monotonicity(self):
        high_quality = self.calculate(detection_quality="0.95")
        low_quality = self.calculate(detection_quality="0.20")
        self.assertGreater(low_quality["adaptive_radius_m"], high_quality["adaptive_radius_m"])

    def test_age_monotonicity_and_saturation(self):
        age_zero = self.calculate(information_age_min="0")
        age_90 = self.calculate(information_age_min="90")
        age_180 = self.calculate(information_age_min="180")
        age_500 = self.calculate(information_age_min="500")
        self.assertLess(age_zero["adaptive_radius_m"], age_90["adaptive_radius_m"])
        self.assertLess(age_90["adaptive_radius_m"], age_180["adaptive_radius_m"])
        self.assertEqual(age_180["f_t"], 1.5)
        self.assertEqual(age_500["f_t"], 1.5)

    def test_dispersion_monotonicity_and_saturation(self):
        sigma_zero = self.calculate(position_dispersion_m="0")
        sigma_25 = self.calculate(position_dispersion_m="25")
        sigma_50 = self.calculate(position_dispersion_m="50")
        sigma_500 = self.calculate(position_dispersion_m="500")
        self.assertLess(sigma_zero["adaptive_radius_m"], sigma_25["adaptive_radius_m"])
        self.assertLess(sigma_25["adaptive_radius_m"], sigma_50["adaptive_radius_m"])
        self.assertEqual(sigma_50["f_s"], 1.5)
        self.assertEqual(sigma_500["f_s"], 1.5)

    def test_environment_factors(self):
        expected = {
            "RURAL/ABERTO": 1.0,
            "MISTO": 1.1,
            "URBANO": 1.2,
            "MATA": 1.25,
            "ÁREA ALAGADA": 1.15,
            "DESCONHECIDO": 1.15,
        }
        for environment, factor in expected.items():
            with self.subTest(environment=environment):
                result = self.calculate(environment_class=environment)
                self.assertEqual(result["f_e"], factor)

    def test_environment_aliases_are_normalized(self):
        self.assertEqual(self.calculate(environment_class="area alagada")["environment_class"], "ÁREA ALAGADA")
        self.assertEqual(self.calculate(environment_class="floresta")["environment_class"], "MATA")
        self.assertEqual(self.calculate(environment_class="rural")["environment_class"], "RURAL/ABERTO")

    def test_unrecognized_environment_is_rejected(self):
        with self.assertRaises(engine.InputValueError):
            self.calculate(environment_class="litoral rochoso")

    def test_missing_optional_values_use_frozen_policies(self):
        row = valid_row(position_dispersion_m="", information_age_min="")
        row.pop("environment_class")
        result = engine.compute_record(row, self.config)
        self.assertEqual(result["f_e"], 1.15)
        self.assertEqual(result["f_s"], 1.0)
        self.assertEqual(result["f_t"], 1.0)
        self.assertEqual(result["missing_optional_count"], 3)
        self.assertEqual(result["review_status"], "REVISAR")
        for warning in (
            "ENVIRONMENT_MISSING_DEFAULT_APPLIED",
            "POSITION_DISPERSION_MISSING_NEUTRAL_APPLIED",
            "INFORMATION_AGE_MISSING_NEUTRAL_APPLIED",
            "MULTIPLE_OPTIONAL_INPUTS_MISSING",
        ):
            self.assertIn(warning, result["warning_codes"])

    def test_explicit_unknown_environment_forces_review(self):
        result = self.calculate(environment_class="DESCONHECIDO")
        self.assertEqual(result["review_status"], "REVISAR")
        self.assertIn("ENVIRONMENT_DESCONHECIDO", result["warning_codes"])

    def test_minimum_clamp(self):
        result = self.calculate(
            base_radius_m="1",
            r0_semantics="source_adjusted",
            factors_applied="f_q",
            environment_class="RURAL/ABERTO",
            position_dispersion_m="0",
            information_age_min="0",
        )
        self.assertEqual(result["adaptive_radius_m"], 250.0)
        self.assertEqual(result["clamp_status"], "MIN")
        self.assertIn("RADIUS_CLAMPED_TO_MINIMUM", result["warning_codes"])

    def test_maximum_clamp(self):
        result = self.calculate(
            base_radius_m="10000",
            r0_semantics="source_adjusted",
            factors_applied="f_q",
        )
        self.assertEqual(result["adaptive_radius_m"], 7500.0)
        self.assertEqual(result["clamp_status"], "MAX")
        self.assertIn("RADIUS_CLAMPED_TO_MAXIMUM", result["warning_codes"])

    def test_source_adjusted_neutralizes_only_declared_factors(self):
        result = self.calculate(
            base_radius_m="1000",
            r0_semantics="source_adjusted",
            factors_applied="f_q;environment",
        )
        self.assertEqual(result["effective_f_q"], 1.0)
        self.assertEqual(result["effective_f_e"], 1.0)
        self.assertEqual(result["effective_f_s"], result["f_s"])
        self.assertEqual(result["effective_f_t"], result["f_t"])
        self.assertEqual(result["factors_applied_by_engine"], "f_s;f_t")

    def test_source_adjusted_without_factors_is_rejected(self):
        with self.assertRaises(engine.InputValueError):
            self.calculate(
                base_radius_m="1000",
                r0_semantics="source_adjusted",
                factors_applied="",
            )

    def test_diagnostic_legacy_applies_all_factors_and_is_not_confirmatory(self):
        result = self.calculate(
            base_radius_m="1000",
            r0_semantics="diagnostic_legacy",
            factors_applied="",
            r0_provenance="SEMI_SINTETICO_DERIVADO_DO_GERADOR_DEV_V2",
            execution_phase="DEV_DRY_RUN",
        )
        self.assertEqual(result["factors_applied_by_engine"], "f_q;f_e;f_s;f_t")
        self.assertFalse(result["confirmatory_eligible"])
        self.assertEqual(
            result["execution_classification"],
            "DIAGNOSTICO_LEGADO_NAO_CONFIRMATORIO",
        )
        self.assertIn("R0_ENTANGLED_WITH_GENERATOR_AND_INFORMATION_AGE", result["warning_codes"])
        self.assertIn("R0_FACTORS_APPLIED_UNKNOWN", result["warning_codes"])

    def test_nominal_semantics_require_frozen_radius_and_no_prior_factors(self):
        with self.assertRaises(engine.InputValueError):
            self.calculate(base_radius_m="1999")
        with self.assertRaises(engine.InputValueError):
            self.calculate(factors_applied="f_q")

    def test_quality_is_mandatory(self):
        with self.assertRaises(engine.InputValueError):
            self.calculate(detection_quality="")

    def test_numeric_domains_are_enforced(self):
        invalid_cases = (
            {"estimated_lat": "90.1"},
            {"estimated_lon": "-180.1"},
            {"base_radius_m": "0"},
            {"detection_quality": "-0.01"},
            {"detection_quality": "1.01"},
            {"position_dispersion_m": "-1"},
            {"information_age_min": "-1"},
            {"estimated_lat": "nan"},
            {"estimated_lon": "inf"},
        )
        for updates in invalid_cases:
            with self.subTest(updates=updates), self.assertRaises(engine.InputValueError):
                self.calculate(**updates)

    def test_ground_truth_and_derived_fields_are_rejected(self):
        forbidden_fields = (
            "ground_truth_lat",
            "reference_lon",
            "true_lat",
            "base_lon",
            "generator_distance_m",
            "distance_to_reference_m",
            "relevant_candidate",
            "latitude_real",
        )
        for field in forbidden_fields:
            row = valid_row()
            row[field] = "0"
            with self.subTest(field=field), self.assertRaises(engine.InputSchemaError):
                engine.compute_record(row, self.config)

    def test_duplicate_candidate_key_is_rejected(self):
        with self.assertRaises(engine.InputValueError):
            engine.process_records([valid_row(), valid_row()], self.config)

    def test_processing_order_and_content_are_deterministic(self):
        rows = [
            valid_row(scenario_id="T-002", candidate_id="T-002-C1"),
            valid_row(scenario_id="T-001", candidate_id="T-001-C2"),
        ]
        first = engine.process_records(copy.deepcopy(rows), self.config)
        second = engine.process_records(copy.deepcopy(rows), self.config)
        self.assertEqual(first, second)
        self.assertEqual(first[0]["scenario_id"], "T-001")

    def test_circle_ring_is_closed_and_has_72_segments(self):
        ring = engine.circle_ring(12.345678, -45.678901, 2000.0)
        self.assertEqual(len(ring), 73)
        self.assertEqual(ring[0], ring[-1])
        for lon, lat in ring[:-1]:
            self.assertAlmostEqual(
                haversine_m(12.345678, -45.678901, lat, lon), 2000.0, delta=0.02
            )

    def test_circle_ring_supports_southern_hemisphere(self):
        latitude, longitude, radius = -10.246810, -44.135790, 1464.1
        ring = engine.circle_ring(latitude, longitude, radius)
        self.assertEqual(ring[0], ring[-1])
        for lon, lat in ring[:-1]:
            self.assertAlmostEqual(
                haversine_m(latitude, longitude, lat, lon), radius, delta=0.02
            )

    def test_analytical_buffer_area_and_four_factor_case(self):
        result = self.calculate(
            detection_quality="0.8",
            environment_class="MISTO",
            position_dispersion_m="10",
            information_age_min="36",
        )
        self.assertAlmostEqual(result["raw_radius_m"], 2928.2, places=6)
        self.assertAlmostEqual(
            result["buffer_area_m2"],
            math.pi * result["adaptive_radius_m"] ** 2,
            delta=0.001,
        )

    def test_geojson_contains_safe_closed_polygons(self):
        result = self.calculate()
        geojson = engine.to_geojson([result], self.config)
        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertFalse(geojson["ground_truth_used"])
        feature = geojson["features"][0]
        ring = feature["geometry"]["coordinates"][0]
        self.assertEqual(feature["geometry"]["type"], "Polygon")
        self.assertEqual(len(ring), 73)
        self.assertEqual(ring[0], ring[-1])
        self.assertNotIn("ground_truth_lat", feature["properties"])
        self.assertNotIn("reference_lat", feature["properties"])

    def test_rich_normative_config_loads_and_tampering_is_rejected(self):
        config_path = Path(__file__).with_name("config_buffer_v1.json")
        loaded = engine.load_config(config_path)
        self.assertEqual(loaded["radius"]["min_m"], 250.0)
        tampered = engine.frozen_config_copy()
        tampered["radius"]["max_m"] = 8000
        with self.assertRaises(engine.ProtocolConfigError):
            engine.compute_record(valid_row(), tampered)

    def test_pipeline_writes_hashes_and_no_ground_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "input.csv"
            config_path = root / "config.json"
            output_csv = root / "result.csv"
            output_json = root / "result.json"
            output_geojson = root / "result.geojson"
            manifest_path = root / "manifest.json"
            config_path.write_text(
                json.dumps(engine.frozen_config_copy(), ensure_ascii=False), encoding="utf-8"
            )
            with input_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(valid_row().keys()))
                writer.writeheader()
                writer.writerow(valid_row())

            manifest = engine.run_pipeline(
                input_path=input_path,
                config_path=config_path,
                output_csv_path=output_csv,
                output_json_path=output_json,
                output_geojson_path=output_geojson,
                manifest_path=manifest_path,
            )
            self.assertFalse(manifest["ground_truth_used"])
            self.assertEqual(manifest["record_count"], 1)
            for item in manifest["files"]:
                path = Path(item["path"])
                self.assertTrue(path.exists())
                self.assertEqual(
                    item["sha256"], hashlib.sha256(path.read_bytes()).hexdigest()
                )

            result_payload = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertFalse(result_payload["ground_truth_used"])
            self.assertNotIn("ground_truth_lat", output_json.read_text(encoding="utf-8"))
            geo_payload = json.loads(output_geojson.read_text(encoding="utf-8"))
            self.assertEqual(len(geo_payload["features"]), 1)

    def test_repeat_pipeline_has_identical_data_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "input.csv"
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(engine.frozen_config_copy(), ensure_ascii=False), encoding="utf-8"
            )
            with input_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(valid_row().keys()))
                writer.writeheader()
                writer.writerow(valid_row())
            hashes = []
            for run in (1, 2):
                csv_path = root / f"result_{run}.csv"
                json_path = root / f"result_{run}.json"
                geo_path = root / f"result_{run}.geojson"
                engine.run_pipeline(
                    input_path=input_path,
                    config_path=config_path,
                    output_csv_path=csv_path,
                    output_json_path=json_path,
                    output_geojson_path=geo_path,
                    manifest_path=root / f"manifest_{run}.json",
                )
                hashes.append(
                    tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in (csv_path, json_path, geo_path))
                )
            self.assertEqual(hashes[0], hashes[1])

    def test_input_and_output_paths_must_be_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "same.csv"
            with self.assertRaises(engine.BufferEngineError):
                engine.run_pipeline(
                    input_path=path,
                    config_path=Path(tmp) / "config.json",
                    output_csv_path=path,
                    output_json_path=Path(tmp) / "result.json",
                    output_geojson_path=Path(tmp) / "result.geojson",
                    manifest_path=Path(tmp) / "manifest.json",
                )


class RecordingResult(unittest.TextTestResult):
    """Resultado textual com registros estruturados para o relatório do pacote."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.append({"test": test.id(), "status": "PASS"})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.records.append({"test": test.id(), "status": "FAIL", "detail": self._exc_info_to_string(err, test)})

    def addError(self, test, err):
        super().addError(test, err)
        self.records.append({"test": test.id(), "status": "ERROR", "detail": self._exc_info_to_string(err, test)})

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.records.append({"test": test.id(), "status": "SKIP", "detail": reason})


def run_with_optional_json_report(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    report_path = None
    if "--json-report" in args:
        index = args.index("--json-report")
        try:
            report_path = Path(args[index + 1])
        except IndexError as exc:
            raise SystemExit("--json-report exige um caminho.") from exc
        del args[index : index + 2]
    verbosity = 2 if "-v" in args or "--verbose" in args else 1
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=verbosity, resultclass=RecordingResult)
    result = runner.run(suite)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "protocol_id": engine.PROTOCOL_ID,
            "tests_run": result.testsRun,
            "passed": sum(item["status"] == "PASS" for item in result.records),
            "failed": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "successful": result.wasSuccessful(),
            "records": result.records,
        }
        report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(run_with_optional_json_report())
