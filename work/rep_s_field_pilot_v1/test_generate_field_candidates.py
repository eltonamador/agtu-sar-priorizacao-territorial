#!/usr/bin/env python3
"""Testes do protocolo FIELD-CAND-v1.0 com coordenadas ficticias."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from generate_field_candidates import (
    DEFAULT_CONFIG,
    GenerationError,
    forbidden_headers,
    generate_candidates_for_site,
    load_config,
    run_generator,
    validate_config,
)


class SequenceRng:
    def __init__(self, values: list[float]):
        self.values = list(values)
        self.draw_count = 0

    def next_float(self) -> float:
        if self.draw_count >= len(self.values):
            raise AssertionError("Sequencia de teste esgotada.")
        value = self.values[self.draw_count]
        self.draw_count += 1
        return value


class FieldCandidateGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.input_gt = self.root / "ground_truth_reserved.csv"
        self._write_dummy_ground_truth(self.input_gt)
        self.config, _ = load_config(DEFAULT_CONFIG)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    @staticmethod
    def _write_dummy_ground_truth(path: Path) -> None:
        rows = [
            ["SITE-T01", "RSF-T01", "0.10000000", "-51.10000000", "Urbano"],
            ["SITE-T02", "RSF-T02", "0.20000000", "-51.20000000", "Semirrural"],
            ["SITE-T03", "RSF-T03", "-0.10000000", "-51.30000000", "Rural"],
            ["SITE-T04", "RSF-T04", "-0.20000000", "-51.40000000", "Mata"],
        ]
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(
                [
                    "site_id",
                    "scenario_id",
                    "ground_truth_lat",
                    "ground_truth_lon",
                    "planned_environment",
                ]
            )
            writer.writerows(rows)

    def _paths(self, label: str) -> tuple[Path, Path, Path]:
        directory = self.root / label
        return directory / "blind.csv", directory / "secure.csv", directory / "manifest.json"

    def _run(self, label: str):
        blind, secure, manifest = self._paths(label)
        result = run_generator(
            self.input_gt,
            blind,
            secure,
            manifest,
            config_path=DEFAULT_CONFIG,
        )
        return result, blind, secure, manifest

    @staticmethod
    def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            return list(reader.fieldnames or []), list(reader)

    def test_determinism_and_manifest_hashes(self) -> None:
        first, blind_1, secure_1, manifest_1 = self._run("run_1")
        second, blind_2, secure_2, manifest_2 = self._run("run_2")
        self.assertEqual(blind_1.read_bytes(), blind_2.read_bytes())
        self.assertEqual(secure_1.read_bytes(), secure_2.read_bytes())
        self.assertEqual(manifest_1.read_bytes(), manifest_2.read_bytes())
        self.assertEqual(first, second)
        self.assertEqual(first["draw_count"], 56)
        self.assertEqual(first["candidate_count"], 12)
        self.assertFalse(first["ground_truth_used_by_buffer_geo_or_ranking"])

    def test_three_candidates_and_one_distance_band_per_site(self) -> None:
        _, _, secure, _ = self._run("bands")
        _, rows = self._read_csv(secure)
        by_scenario: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            by_scenario.setdefault(row["scenario_id"], []).append(row)
        self.assertEqual(len(by_scenario), 4)
        expected_bands = {"PROXIMO", "INTERMEDIARIO", "DISTANTE"}
        bounds = {
            "PROXIMO": (250.0, 800.0),
            "INTERMEDIARIO": (800.0, 2000.0),
            "DISTANTE": (2000.0, 4500.0),
        }
        for rows_for_site in by_scenario.values():
            self.assertEqual(len(rows_for_site), 3)
            self.assertEqual(
                {row["distance_band_generator_only"] for row in rows_for_site},
                expected_bands,
            )
            for row in rows_for_site:
                minimum, maximum = bounds[row["distance_band_generator_only"]]
                distance = float(row["distance_m_generator_only"])
                self.assertGreaterEqual(distance, minimum)
                self.assertLess(distance, maximum)

    def test_blind_schema_has_no_reserved_or_derived_columns(self) -> None:
        _, blind, _, _ = self._run("schema")
        headers, rows = self._read_csv(blind)
        self.assertEqual(headers, self.config["blind_output_schema"])
        self.assertEqual(
            forbidden_headers(headers, self.config["blind_forbidden_column_fragments"]),
            [],
        )
        self.assertEqual(len(rows), 12)
        for row in rows:
            self.assertEqual(row["base_radius_m"], "2000")
            self.assertEqual(row["r0_semantics"], "nominal_base")
            self.assertEqual(row["position_dispersion_m"], "")
            self.assertEqual(row["factors_applied"], "")

    def test_quality_and_age_use_draws_independent_from_distance_draws(self) -> None:
        site = {
            "site_id": "SITE-X",
            "scenario_id": "RSF-X",
            "ground_truth_lat": "0.00000000",
            "ground_truth_lon": "-51.00000000",
            "ground_truth_lat_value": 0.0,
            "ground_truth_lon_value": -51.0,
            "planned_environment": "Urbano",
            "environment_class": "URBANO",
        }
        baseline = [
            0.10,
            0.10,
            0.20,
            0.30,
            0.40,
            0.50,
            0.20,
            0.30,
            0.40,
            0.50,
            0.20,
            0.30,
            0.40,
            0.50,
        ]
        altered_distances = list(baseline)
        for index in (2, 6, 10):
            altered_distances[index] = 0.90
        blind_a, secure_a = generate_candidates_for_site(site, self.config, SequenceRng(baseline))
        blind_b, secure_b = generate_candidates_for_site(
            site, self.config, SequenceRng(altered_distances)
        )
        self.assertNotEqual(
            [row["distance_m_generator_only"] for row in secure_a],
            [row["distance_m_generator_only"] for row in secure_b],
        )
        self.assertEqual(
            [row["detection_quality"] for row in blind_a],
            [row["detection_quality"] for row in blind_b],
        )
        self.assertEqual(
            [row["information_age_min"] for row in blind_a],
            [row["information_age_min"] for row in blind_b],
        )

    def test_all_generated_coordinates_are_valid(self) -> None:
        _, blind, _, manifest_path = self._run("coordinates")
        _, rows = self._read_csv(blind)
        for row in rows:
            latitude = float(row["estimated_lat"])
            longitude = float(row["estimated_lon"])
            self.assertGreaterEqual(latitude, -90.0)
            self.assertLessEqual(latitude, 90.0)
            self.assertGreaterEqual(longitude, -180.0)
            self.assertLessEqual(longitude, 180.0)
            self.assertGreaterEqual(float(row["detection_quality"]), 0.35)
            self.assertLess(float(row["detection_quality"]), 0.95)
            self.assertGreaterEqual(int(row["information_age_min"]), 5)
            self.assertLessEqual(int(row["information_age_min"]), 180)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["site_count"], 4)
        self.assertEqual(manifest["candidate_count"], 12)

    def test_same_blind_and_secure_path_is_rejected(self) -> None:
        same_path = self.root / "collision.csv"
        with self.assertRaisesRegex(GenerationError, "mesmo caminho"):
            run_generator(
                self.input_gt,
                same_path,
                same_path,
                self.root / "manifest_collision.json",
                config_path=DEFAULT_CONFIG,
            )

    def test_execution_rejects_tampered_config_by_integrity_hash(self) -> None:
        tampered = deepcopy(self.config)
        tampered["blind_output_schema"].append("ground_truth_lat")
        tampered_path = self.root / "tampered_config.json"
        tampered_path.write_text(
            json.dumps(tampered, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        blind, secure, manifest = self._paths("tampered")
        with self.assertRaisesRegex(GenerationError, "integridade"):
            run_generator(
                self.input_gt,
                blind,
                secure,
                manifest,
                config_path=tampered_path,
            )

    def test_schema_guard_directly_rejects_forbidden_column(self) -> None:
        tampered = deepcopy(self.config)
        tampered["blind_output_schema"].append("ground_truth_lat")
        with self.assertRaisesRegex(GenerationError, "colunas proibidas"):
            validate_config(tampered)

    def test_config_path_cannot_be_used_as_output_even_with_overwrite(self) -> None:
        _, secure, manifest = self._paths("config_collision")
        with self.assertRaisesRegex(GenerationError, "caminhos distintos"):
            run_generator(
                self.input_gt,
                DEFAULT_CONFIG,
                secure,
                manifest,
                config_path=DEFAULT_CONFIG,
                overwrite=True,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
