#!/usr/bin/env python3
"""Testes do contrato REP-S-SPATIAL-EVAL-v1.0 sem dados reais de campo."""

from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from common import (
    DEFAULT_CONFIG,
    ProtocolError,
    closed_polygon_membership,
    file_record,
    load_config,
    proportion_record,
    sha256_file,
    stable_hash,
    validate_dependencies,
    wilson_interval,
    write_csv,
    write_json,
)
from evaluate_post_t3 import evaluate_candidate, evaluate_post_t3, relevant_sector_set
from prepare_and_run_blind import _forbidden_headers, prepare_t1


ROOT = Path(__file__).resolve().parents[2]
FIELD_DIR = ROOT / "work" / "rep_s_field_pilot_v1"


class RepSSpatialEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config, self.config_hash = load_config(DEFAULT_CONFIG)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_gt(self, path: Path) -> None:
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
            writer.writerows(
                [
                    ["SITE-T01", "RSF-T01", "0.10000000", "-51.10000000", "Urbano"],
                    ["SITE-T02", "RSF-T02", "0.20000000", "-51.20000000", "Semirrural"],
                    ["SITE-T03", "RSF-T03", "-0.10000000", "-51.30000000", "Rural"],
                    ["SITE-T04", "RSF-T04", "-0.20000000", "-51.40000000", "Mata"],
                ]
            )

    def _field_package(self) -> tuple[Path, Path, Path]:
        gt = self.root / "ground_truth_reserved.csv"
        blind = self.root / "field_candidates_blind.csv"
        secure = self.root / "field_candidates_secure.csv"
        manifest = self.root / "field_candidates_manifest.json"
        self._write_gt(gt)
        completed = subprocess.run(
            [
                sys.executable,
                str(FIELD_DIR / "generate_field_candidates.py"),
                "--input-gt",
                str(gt),
                "--blind-output",
                str(blind),
                "--secure-output",
                str(secure),
                "--manifest-output",
                str(manifest),
            ],
            cwd=FIELD_DIR,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)
        return gt, blind, manifest

    def test_frozen_config_and_dependencies(self) -> None:
        self.assertEqual(self.config["protocol_id"], "REP-S-SPATIAL-EVAL-v1.0")
        verified = validate_dependencies(self.config, DEFAULT_CONFIG)
        self.assertEqual(len(verified), 7)

    def test_prepare_t1_accepts_untampered_field_candidate_package(self) -> None:
        gt, blind, field_manifest = self._field_package()
        output_csv = self.root / "buffer_input_t1.csv"
        output_manifest = self.root / "manifest_t1.json"
        result = prepare_t1(
            blind_csv=blind,
            generator_manifest_path=field_manifest,
            output_csv=output_csv,
            output_manifest=output_manifest,
        )
        self.assertEqual(result["milestone"], "T1")
        self.assertFalse(result["ground_truth_used"])
        self.assertEqual(result["candidate_count"], 12)
        self.assertEqual(result["ground_truth_sha256_commitment"], sha256_file(gt))
        with output_csv.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            self.assertNotIn("site_id", reader.fieldnames or [])
            self.assertNotIn("ground_truth_lat", reader.fieldnames or [])
            self.assertEqual(len(list(reader)), 12)

    def test_prepare_t1_rejects_changed_blind_file(self) -> None:
        _gt, blind, field_manifest = self._field_package()
        blind.write_text(blind.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ProtocolError, "diverge do hash"):
            prepare_t1(
                blind_csv=blind,
                generator_manifest_path=field_manifest,
                output_csv=self.root / "buffer.csv",
                output_manifest=self.root / "t1.json",
            )

    def test_forbidden_header_fragments_block_ground_truth_and_rank(self) -> None:
        violations = _forbidden_headers(
            ["candidate_id", "ground_truth_lat", "rank_against_truth"],
            self.config["blind_interface"]["forbidden_header_fragments"],
        )
        self.assertEqual(violations, ["ground_truth_lat", "rank_against_truth"])

    @staticmethod
    def _two_adjacent_polygons() -> dict[str, list[list[float]]]:
        # Aproximadamente 111 m por 0,001 grau no equador.
        return {
            "S-W": [[-0.001, -0.001], [0.0, -0.001], [0.0, 0.001], [-0.001, 0.001], [-0.001, -0.001]],
            "S-E": [[0.0, -0.001], [0.001, -0.001], [0.001, 0.001], [0.0, 0.001], [0.0, -0.001]],
        }

    def test_closed_polygon_boundary_is_set_valued(self) -> None:
        relevant, boundary, distance = relevant_sector_set(
            ground_truth_lat=0.0,
            ground_truth_lon=0.0,
            center_lat=0.0,
            center_lon=0.0,
            polygons=self._two_adjacent_polygons(),
            tolerance_m=0.25,
        )
        self.assertEqual(relevant, ["S-E", "S-W"])
        self.assertEqual(boundary, ["S-E", "S-W"])
        self.assertIsNotNone(distance)
        self.assertLessEqual(float(distance), 0.25)

    def test_point_outside_closed_polygon_is_not_member(self) -> None:
        member, boundary, distance = closed_polygon_membership(
            point_lat=0.01,
            point_lon=0.01,
            polygon_lon_lat=self._two_adjacent_polygons()["S-E"],
            center_lat=0.0,
            center_lon=0.0,
            tolerance_m=0.25,
        )
        self.assertFalse(member)
        self.assertFalse(boundary)
        self.assertGreater(distance, 1000.0)

    def test_boundary_metrics_report_primary_and_conservative_rank(self) -> None:
        polygons = self._two_adjacent_polygons()
        ranking = {
            "S-W": {"sector_id": "S-W", "rank": 1, "area_m2": 100.0, "geo_complete": True},
            "S-E": {"sector_id": "S-E", "rank": 4, "area_m2": 100.0, "geo_complete": True},
        }
        result = evaluate_candidate(
            site_id="SITE-T",
            environment_class="URBANO",
            ground_truth={"ground_truth_lat": 0.0, "ground_truth_lon": 0.0},
            buffer={
                "scenario_id": "RSF-T",
                "candidate_id": "RSF-T-C1",
                "estimated_lat": 0.0,
                "estimated_lon": 0.0,
                "adaptive_radius_m": 1000.0,
                "buffer_area_m2": math.pi * 1_000_000,
                "review_status": "CALCULADO",
                "confirmatory_eligible": True,
            },
            polygons=polygons,
            ranking=ranking,
            config=self.config,
        )
        self.assertEqual(result["relevant_sector_count"], 2)
        self.assertEqual(result["truth_rank_min"], 1)
        self.assertEqual(result["truth_rank_max"], 4)
        self.assertTrue(result["top1_primary"])
        self.assertFalse(result["top1_conservative"])
        self.assertEqual(result["reciprocal_rank_primary"], 1.0)
        self.assertEqual(result["reciprocal_rank_conservative"], 0.25)
        self.assertEqual(result["accumulated_area_primary_m2"], 100.0)
        self.assertEqual(result["accumulated_area_conservative_m2"], 200.0)

    def test_outside_buffer_gets_zero_rr_and_no_accumulated_area(self) -> None:
        polygons = self._two_adjacent_polygons()
        ranking = {
            sector_id: {"sector_id": sector_id, "rank": index, "area_m2": 100.0, "geo_complete": True}
            for index, sector_id in enumerate(polygons, start=1)
        }
        result = evaluate_candidate(
            site_id="SITE-T",
            environment_class="URBANO",
            ground_truth={"ground_truth_lat": 0.02, "ground_truth_lon": 0.02},
            buffer={
                "scenario_id": "RSF-T",
                "candidate_id": "RSF-T-C1",
                "estimated_lat": 0.0,
                "estimated_lon": 0.0,
                "adaptive_radius_m": 1000.0,
                "buffer_area_m2": math.pi * 1_000_000,
                "review_status": "CALCULADO",
                "confirmatory_eligible": True,
            },
            polygons=polygons,
            ranking=ranking,
            config=self.config,
        )
        self.assertFalse(result["adaptive_coverage"])
        self.assertEqual(result["reciprocal_rank_primary"], 0.0)
        self.assertIsNone(result["truth_rank_min"])
        self.assertIsNone(result["accumulated_area_primary_m2"])

    def test_wilson_interval_and_empty_denominator(self) -> None:
        low, high = wilson_interval(9, 10)
        self.assertLess(low or 1.0, 0.9)
        self.assertGreater(high or 0.0, 0.9)
        self.assertEqual(proportion_record(0, 0)["rate"], None)

    @staticmethod
    def _xy_to_lon_lat(x: float, y: float, lat0: float, lon0: float) -> list[float]:
        return [lon0 + x / (111_320.0 * math.cos(math.radians(lat0))), lat0 + y / 110_574.0]

    def _sector_ring(self, lat0: float, lon0: float, ring_index: int, direction_index: int) -> list[list[float]]:
        boundaries = [0.0, math.sqrt(1 / 3) * 1000.0, math.sqrt(2 / 3) * 1000.0, 1000.0]
        inner, outer = boundaries[ring_index - 1], boundaries[ring_index]
        center_deg = direction_index * 45.0
        start, end = center_deg - 22.5, center_deg + 22.5
        angles = [start + (end - start) * index / 4 for index in range(5)]

        def point(radius: float, bearing: float) -> list[float]:
            theta = math.radians(bearing)
            return self._xy_to_lon_lat(radius * math.sin(theta), radius * math.cos(theta), lat0, lon0)

        if inner == 0:
            ring = [self._xy_to_lon_lat(0.0, 0.0, lat0, lon0)]
            ring.extend(point(outer, angle) for angle in angles)
            ring.append(ring[0])
            return ring
        ring = [point(outer, angle) for angle in angles]
        ring.extend(point(inner, angle) for angle in reversed(angles))
        ring.append(ring[0])
        return ring

    def _fake_t2_package(self, ground_truth_path: Path) -> Path:
        coordinates = {
            "RSF-T01": (0.1, -51.1, "SITE-T01", "URBANO"),
            "RSF-T02": (0.2, -51.2, "SITE-T02", "MISTO"),
            "RSF-T03": (-0.1, -51.3, "SITE-T03", "RURAL/ABERTO"),
            "RSF-T04": (-0.2, -51.4, "SITE-T04", "MATA"),
        }
        candidate_map = []
        buffer_rows = []
        features = []
        ranking_rows = []
        directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        area = math.pi * 1_000_000 / 24.0
        for scenario, (truth_lat, truth_lon, site, environment) in coordinates.items():
            for slot in range(1, 4):
                candidate = f"{scenario}-C{slot}"
                # Centro 100 m a leste; o ground truth fica no setor R01::W.
                center_lat = truth_lat
                center_lon = truth_lon + 100.0 / (111_320.0 * math.cos(math.radians(truth_lat)))
                candidate_map.append(
                    {
                        "site_id": site,
                        "scenario_id": scenario,
                        "candidate_id": candidate,
                        "environment_class": environment,
                    }
                )
                buffer_rows.append(
                    {
                        "protocol_id": "EXT-ESP-BUF-v1.0",
                        "scenario_id": scenario,
                        "candidate_id": candidate,
                        "estimated_lat": center_lat,
                        "estimated_lon": center_lon,
                        "adaptive_radius_m": 1000.0,
                        "buffer_area_m2": math.pi * 1_000_000,
                        "review_status": "CALCULADO",
                        "confirmatory_eligible": True,
                        "ground_truth_used": False,
                    }
                )
                sector_ids = []
                for ring_index in range(1, 4):
                    for direction_index, direction in enumerate(directions):
                        sector_id = f"{scenario}::{candidate}::R{ring_index:02d}::{direction}"
                        sector_ids.append(sector_id)
                        features.append(
                            {
                                "type": "Feature",
                                "id": sector_id,
                                "properties": {
                                    "scenario_id": scenario,
                                    "candidate_id": candidate,
                                    "sector_id": sector_id,
                                    "ground_truth_used": False,
                                },
                                "geometry": {
                                    "type": "Polygon",
                                    "coordinates": [
                                        self._sector_ring(center_lat, center_lon, ring_index, direction_index)
                                    ],
                                },
                            }
                        )
                target = f"{scenario}::{candidate}::R01::W"
                ordered = [target] + [sector_id for sector_id in sector_ids if sector_id != target]
                for rank, sector_id in enumerate(ordered, start=1):
                    ranking_rows.append(
                        {
                            "scenario_id": scenario,
                            "candidate_id": candidate,
                            "sector_id": sector_id,
                            "rank_base_within_buffer": rank,
                            "sector_area_m2": area,
                            "geo_completeness": 1.0,
                            "geo02_score": 0.8,
                            "geo03_score": 0.8,
                            "geo04_score": 0.8,
                            "geo05_score": 0.8,
                            "ground_truth_used": "false",
                        }
                    )

        package = self.root / "fake_t2"
        package.mkdir()
        buffer_path = package / "buffer_results.json"
        geometry_path = package / "sector_polygons.geojson"
        ranking_path = package / "sector_ranking.csv"
        write_json(
            buffer_path,
            {
                "protocol_id": "EXT-ESP-BUF-v1.0",
                "ground_truth_used": False,
                "record_count": len(buffer_rows),
                "results": buffer_rows,
            },
        )
        write_json(
            geometry_path,
            {"type": "FeatureCollection", "ground_truth_used": False, "features": features},
        )
        write_csv(ranking_path, list(ranking_rows[0]), ranking_rows)
        t1_dummy = package / "manifest_t1.json"
        buffer_input_dummy = package / "buffer_input.csv"
        t1_dummy.write_text("{}\n", encoding="utf-8")
        buffer_input_dummy.write_text("scenario_id,candidate_id\n", encoding="utf-8")
        manifest = {
            "protocol_id": self.config["protocol_id"],
            "milestone": "T2",
            "state": "SAIDAS_CEGAS_CONGELADAS",
            "ground_truth_used": False,
            "ground_truth_sha256_commitment": sha256_file(ground_truth_path),
            "config_sha256": self.config_hash,
            "determinism": {"all_identical": True},
            "primary_files": [
                file_record(buffer_path, "buffer_json"),
                file_record(geometry_path, "sector_geojson"),
                file_record(ranking_path, "sector_ranking_csv"),
            ],
            "repeat_files": [],
            "source_files": [],
            "dependencies": [],
            "t1_manifest": file_record(t1_dummy, "t1_manifest"),
            "buffer_input": file_record(buffer_input_dummy, "buffer_input_t1"),
            "candidate_map": candidate_map,
            "state_history": [
                {"milestone": "T-1", "state": "PLANO_CONGELADO"},
                {"milestone": "T0", "state": "GROUND_TRUTH_LACRADO"},
                {"milestone": "T1", "state": "ENTRADA_CEGA_CONGELADA"},
                {"milestone": "T1.5", "state": "MOTORES_VERIFICADOS"},
                {"milestone": "T2", "state": "SAIDAS_CEGAS_CONGELADAS"},
            ],
        }
        manifest["manifest_payload_sha256"] = stable_hash(manifest)
        path = package / "manifest_t2.json"
        write_json(path, manifest)
        return path

    def test_post_t3_end_to_end_uses_only_committed_ground_truth(self) -> None:
        ground_truth = self.root / "ground_truth.csv"
        self._write_gt(ground_truth)
        t2_manifest = self._fake_t2_package(ground_truth)
        output = self.root / "t4"
        manifest = evaluate_post_t3(
            t2_manifest_path=t2_manifest,
            ground_truth_path=ground_truth,
            output_dir=output,
        )
        self.assertEqual(manifest["milestone"], "T4")
        summary = json.loads((output / "metrics_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["adaptive_candidate_coverage"]["successes"], 12)
        self.assertEqual(summary["ranking"]["top1_primary_unconditional"]["successes"], 12)
        self.assertAlmostEqual(summary["ranking"]["mrr_primary_unconditional"], 1.0)
        with (output / "candidate_sector_evaluation.csv").open(
            "r", encoding="utf-8", newline=""
        ) as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 12)
        self.assertNotIn("ground_truth_lat", rows[0])
        self.assertEqual({row["assignment_case"] for row in rows}, {"INTERIOR_SINGLETON"})

    def test_post_t3_rejects_a_different_ground_truth_file(self) -> None:
        ground_truth = self.root / "ground_truth.csv"
        self._write_gt(ground_truth)
        t2_manifest = self._fake_t2_package(ground_truth)
        changed = self.root / "changed_ground_truth.csv"
        changed.write_bytes(ground_truth.read_bytes() + b"\n")
        with self.assertRaisesRegex(ProtocolError, "compromisso SHA-256"):
            evaluate_post_t3(
                t2_manifest_path=t2_manifest,
                ground_truth_path=changed,
                output_dir=self.root / "should_not_exist",
            )
        self.assertFalse((self.root / "should_not_exist").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
