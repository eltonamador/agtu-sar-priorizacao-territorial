#!/usr/bin/env python3
"""Testes de aceitação do motor de setorização e priorização EXT-ESP.

Contrato público esperado de ``motor_setorizacao_priorizacao.py``::

    load_json(path) -> object
    validate_buffer_contract(payload) -> list[dict]
    make_sector_records(buffer_records, config) -> list[dict]
    rank_sector_records(sector_records, config) -> list[dict]
    sha256_file(path) -> str
    destination(lat, lon, distance_m, bearing_deg, ...) -> (lat, lon)

O teste fixa o grão ``scenario_id + candidate_id + sector_id``. O método
principal gera três faixas radiais de área equivalente por oito direções,
totalizando 24 setores por buffer de candidato. Nenhum teste acessa ground truth.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import sys
import tempfile
import unittest
from pathlib import Path

import motor_setorizacao_priorizacao as engine


EARTH_RADIUS_M = 6_371_008.8
CONFIG_PATH = Path(__file__).with_name("config_setorizacao_priorizacao_v1.json")


def frozen_config() -> dict:
    """Lê uma cópia independente da configuração DEV-S congelada."""

    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def buffer_record(**updates) -> dict:
    """Registro completo compatível com a saída JSON do motor de buffer."""

    radius = 1_200.0
    record = {
        "protocol_id": "EXT-ESP-BUF-v1.0",
        "engine_version": "1.0.0",
        "scenario_id": "T-001",
        "candidate_id": "T-001-C1",
        "estimated_lat": 12.345678,
        "estimated_lon": -45.678901,
        "base_radius_m": radius,
        "r0_semantics": "source_adjusted",
        "factors_applied_source": "f_q",
        "factors_applied_by_engine": "f_e;f_s;f_t",
        "detection_quality": 1.0,
        "environment_class": "RURAL/ABERTO",
        "position_dispersion_m": 0.0,
        "information_age_min": 0.0,
        "f_q": 1.0,
        "f_e": 1.0,
        "f_s": 1.0,
        "f_t": 1.0,
        "effective_f_q": 1.0,
        "effective_f_e": 1.0,
        "effective_f_s": 1.0,
        "effective_f_t": 1.0,
        "raw_radius_m": radius,
        "adaptive_radius_m": radius,
        "clamp_status": "NONE",
        "expansion_ratio": 1.0,
        "buffer_area_m2": math.pi * radius**2,
        "baseline_fixed_m": 2_000.0,
        "adaptive_minus_baseline_m": radius - 2_000.0,
        "adaptive_to_baseline_ratio": radius / 2_000.0,
        "missing_optional_count": 0,
        "review_status": "CALCULADO",
        "execution_classification": "DESENVOLVIMENTO_NAO_CONFIRMATORIO",
        "warning_codes": "NOT_CONFIRMATORY_ELIGIBLE",
        "confirmatory_eligible": False,
        "ground_truth_used": False,
        "source_row_hash": hashlib.sha256(b"fixture-T-001-C1").hexdigest(),
        "r0_provenance": "FIXTURE_SINTETICA",
        "data_origin": "TESTE_UNITARIO_SINTETICO",
        "execution_phase": "DEV-S",
    }
    record.update(updates)
    if "adaptive_radius_m" in updates and "buffer_area_m2" not in updates:
        record["buffer_area_m2"] = math.pi * float(record["adaptive_radius_m"]) ** 2
    return record


def buffer_payload(*records: dict) -> dict:
    rows = list(records or (buffer_record(),))
    return {
        "protocol_id": "EXT-ESP-BUF-v1.0",
        "engine_version": "1.0.0",
        "ground_truth_used": False,
        "record_count": len(rows),
        "results": rows,
    }


def buffer_geojson(*records: dict) -> dict:
    """GeoJSON mínimo, cego e chaveado como a saída oficial do buffer."""

    rows = list(records or (buffer_record(),))
    features = []
    for row in rows:
        lat = float(row["estimated_lat"])
        lon = float(row["estimated_lon"])
        delta = 0.001
        ring = [
            [lon, lat + delta],
            [lon + delta, lat],
            [lon, lat - delta],
            [lon - delta, lat],
            [lon, lat + delta],
        ]
        features.append(
            {
                "type": "Feature",
                "id": f"{row['scenario_id']}::{row['candidate_id']}",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {
                    "scenario_id": row["scenario_id"],
                    "candidate_id": row["candidate_id"],
                    "ground_truth_used": False,
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "coordinate_reference_system": "EPSG:4326",
        "protocol_id": "EXT-ESP-BUF-v1.0",
        "ground_truth_used": False,
        "features": features,
    }


def ranking_sector(
    sector_id: str,
    *,
    road: float,
    hydro: float,
    terrain: float,
    landcover: float,
    upstream_review_status: str = "CALCULADO",
) -> dict:
    return {
        "protocol_id": "EXT-ESP-SET-v1.0",
        "scenario_id": "T-001",
        "candidate_id": "T-001-C1",
        "sector_id": sector_id,
        "road_trail_access_score": road,
        "hydro_access_score": hydro,
        "terrain_access_score": terrain,
        "landcover_access_score": landcover,
        "geo02_score": road,
        "geo03_score": hydro,
        "geo04_score": terrain,
        "geo05_score": landcover,
        "geo_completeness": 1.0,
        "source_provenance": "FIXTURE_GEO_SINTETICA",
        "upstream_review_status": upstream_review_status,
        "source_buffer_review_status": upstream_review_status,
        "source_execution_classification": "DESENVOLVIMENTO_NAO_CONFIRMATORIO",
        "source_confirmatory_eligible": False,
        "barrier_flags": "NAO_SINALIZADA",
        "ground_truth_used": False,
    }


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


class BufferContractTestCase(unittest.TestCase):
    def validate(self, *records: dict):
        rows = tuple(records or (buffer_record(),))
        return engine.validate_buffer_contract(buffer_payload(*rows), buffer_geojson(*rows))

    def test_load_json_and_sha256_file(self):
        payload = buffer_payload()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "buffer.json"
            raw = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
            path.write_text(raw, encoding="utf-8")
            self.assertEqual(engine.load_json(path), payload)
            self.assertEqual(engine.sha256_file(path), hashlib.sha256(raw.encode()).hexdigest())

    def test_valid_contract_preserves_deterministic_order(self):
        second = buffer_record(
            scenario_id="T-002",
            candidate_id="T-002-C1",
            source_row_hash=hashlib.sha256(b"fixture-T-002-C1").hexdigest(),
        )
        first = buffer_record()
        rows = self.validate(first, second)
        self.assertEqual(
            [(row["scenario_id"], row["candidate_id"]) for row in rows],
            [("T-001", "T-001-C1"), ("T-002", "T-002-C1")],
        )

    def test_nondeterministic_input_order_is_normalized_without_content_change(self):
        second = buffer_record(
            scenario_id="T-002",
            candidate_id="T-002-C1",
            source_row_hash=hashlib.sha256(b"fixture-T-002-C1").hexdigest(),
        )
        first = buffer_record()
        rows = self.validate(second, first)
        self.assertEqual(
            [(row["scenario_id"], row["candidate_id"]) for row in rows],
            [("T-001", "T-001-C1"), ("T-002", "T-002-C1")],
        )

    def test_root_ground_truth_flag_must_be_boolean_false(self):
        for value in (True, "false", 0, None):
            payload = buffer_payload()
            payload["ground_truth_used"] = value
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                engine.validate_buffer_contract(payload, buffer_geojson())

    def test_record_ground_truth_flag_must_be_boolean_false(self):
        for value in (True, "false", 0, None):
            payload = buffer_payload(buffer_record(ground_truth_used=value))
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                engine.validate_buffer_contract(payload, buffer_geojson())

    def test_forbidden_ground_truth_or_derived_fields_are_rejected_recursively(self):
        forbidden = (
            "ground_truth_lat",
            "reference_lon",
            "true_lat",
            "distance_to_truth_m",
            "distance_to_reference_m",
            "inside_buffer",
            "relevant_candidate",
        )
        for field in forbidden:
            record = buffer_record()
            record["metadata"] = {field: 0.0}
            with self.subTest(field=field), self.assertRaises((ValueError, TypeError)):
                engine.validate_buffer_contract(buffer_payload(record), buffer_geojson(record))

    def test_record_count_mismatch_is_rejected(self):
        payload = buffer_payload()
        payload["record_count"] = 2
        with self.assertRaises((ValueError, TypeError)):
            engine.validate_buffer_contract(payload, buffer_geojson())

    def test_duplicate_candidate_key_is_rejected(self):
        row = buffer_record()
        with self.assertRaises((ValueError, TypeError)):
            engine.validate_buffer_contract(
                buffer_payload(row, copy.deepcopy(row)),
                buffer_geojson(row, copy.deepcopy(row)),
            )

    def test_invalid_coordinates_radius_hash_and_numbers_are_rejected(self):
        invalid = (
            {"estimated_lat": 90.1},
            {"estimated_lon": -180.1},
            {"adaptive_radius_m": 0.0},
            {"adaptive_radius_m": 7_500.1},
            {"adaptive_radius_m": float("nan")},
            {"source_row_hash": "not-a-sha256"},
        )
        for update in invalid:
            row = buffer_record(**update)
            with self.subTest(update=update), self.assertRaises((ValueError, TypeError)):
                engine.validate_buffer_contract(buffer_payload(row), buffer_geojson(row))


class SectorGeometryTestCase(unittest.TestCase):
    def setUp(self):
        self.config = frozen_config()
        self.records = engine.validate_buffer_contract(buffer_payload(), buffer_geojson())

    def sectors(self):
        return engine.make_sector_records(copy.deepcopy(self.records), copy.deepcopy(self.config))

    def test_destination_uses_meters_and_returns_lat_lon(self):
        lat, lon = engine.destination(12.345678, -45.678901, 1_200.0, 0.0)
        self.assertAlmostEqual(
            haversine_m(12.345678, -45.678901, lat, lon), 1_200.0, delta=0.03
        )
        self.assertGreater(lat, 12.345678)

    def test_exactly_24_sectors_are_created_per_candidate(self):
        sectors = self.sectors()
        self.assertEqual(len(sectors), 24)
        self.assertEqual({row["scenario_id"] for row in sectors}, {"T-001"})
        self.assertEqual({row["candidate_id"] for row in sectors}, {"T-001-C1"})

    def test_sector_ids_are_unique_stable_and_ordered(self):
        first = self.sectors()
        second = self.sectors()
        self.assertEqual(first, second)
        ids = [row["sector_id"] for row in first]
        self.assertEqual(len(ids), len(set(ids)))
        expected_ids = [
            f"T-001::T-001-C1::R{ring:02d}::{direction}"
            for ring in range(1, 4)
            for direction in ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
        ]
        self.assertEqual(ids, expected_ids)
        self.assertEqual([row["sector_index"] for row in first], list(range(1, 25)))

    def test_three_equal_area_radial_bands_and_eight_directions(self):
        sectors = self.sectors()
        self.assertEqual(sorted({row["ring_index"] for row in sectors}), [1, 2, 3])
        self.assertEqual(sorted({row["direction_index"] for row in sectors}), list(range(1, 9)))
        self.assertEqual(
            {row["direction_label"] for row in sectors},
            {"N", "NE", "E", "SE", "S", "SW", "W", "NW"},
        )
        for band in (1, 2, 3):
            self.assertEqual(sum(row["ring_index"] == band for row in sectors), 8)
        radius = 1_200.0
        expected_outer = {
            1: radius * math.sqrt(1 / 3),
            2: radius * math.sqrt(2 / 3),
            3: radius,
        }
        for band, expected in expected_outer.items():
            actual = {row["outer_radius_m"] for row in sectors if row["ring_index"] == band}
            self.assertEqual(len(actual), 1)
            self.assertAlmostEqual(actual.pop(), expected, places=6)

    def test_sector_areas_are_equal_and_sum_to_buffer_area(self):
        sectors = self.sectors()
        expected = math.pi * 1_200.0**2 / 24.0
        for row in sectors:
            self.assertAlmostEqual(row["sector_area_m2"], expected, delta=0.05)
        self.assertAlmostEqual(
            sum(row["sector_area_m2"] for row in sectors),
            math.pi * 1_200.0**2,
            delta=0.5,
        )

    def test_sector_geometry_is_closed_finite_polygon_in_lon_lat_order(self):
        for row in self.sectors():
            geometry = row["geometry"]
            self.assertEqual(geometry["type"], "Polygon")
            self.assertEqual(len(geometry["coordinates"]), 1)
            ring = geometry["coordinates"][0]
            self.assertGreaterEqual(len(ring), 4)
            self.assertEqual(ring[0], ring[-1])
            for lon, lat in ring:
                self.assertTrue(math.isfinite(lon) and math.isfinite(lat))
                self.assertTrue(-180.0 <= lon <= 180.0)
                self.assertTrue(-90.0 <= lat <= 90.0)

    def test_sector_outputs_preserve_firewall_and_lineage(self):
        forbidden = re.compile(
            r"ground_truth_(?:lat|lon)|reference_(?:lat|lon)|true_(?:lat|lon)|"
            r"distance_to_(?:truth|reference)|inside_buffer|relevant_candidate",
            re.IGNORECASE,
        )
        for row in self.sectors():
            self.assertIs(row["ground_truth_used"], False)
            self.assertEqual(row["source_row_hash"], self.records[0]["source_row_hash"])
            self.assertIsNone(forbidden.search(json.dumps(row, ensure_ascii=False)))


class SectorRankingTestCase(unittest.TestCase):
    def setUp(self):
        self.config = frozen_config()
        self.s1 = "T-001::T-001-C1::R01::N"
        self.s2 = "T-001::T-001-C1::R01::NE"
        self.s3 = "T-001::T-001-C1::R01::E"
        self.sector_ids = [
            f"T-001::T-001-C1::R{ring:02d}::{direction}"
            for ring in range(1, 4)
            for direction in ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
        ]
        self.last_decisions = []

    def rank(self, *records):
        supplied = {row["sector_id"]: copy.deepcopy(row) for row in records}
        complete = [
            supplied.get(
                sector_id,
                ranking_sector(sector_id, road=0.0, hydro=0.0, terrain=0.0, landcover=0.0),
            )
            for sector_id in self.sector_ids
        ]
        result = engine.rank_sector_records(complete, copy.deepcopy(self.config))
        if isinstance(result, tuple):
            ranked, self.last_decisions = result
            return ranked
        self.last_decisions = []
        return result

    @staticmethod
    def score(row):
        return row.get("priority_score", row.get("score_base"))

    @staticmethod
    def rank_number(row):
        return row.get("sector_rank", row.get("rank_base_within_buffer"))

    def decision(self, top_row):
        if self.last_decisions:
            return self.last_decisions[0]
        return top_row

    def margin(self, top_row):
        decision = self.decision(top_row)
        return decision.get("rank_margin", decision.get("base_margin", top_row.get("buffer_base_margin")))

    def status(self, top_row):
        decision = self.decision(top_row)
        return decision.get("decision_status", top_row.get("buffer_decision_status"))

    def warnings(self, top_row):
        decision = self.decision(top_row)
        return decision.get("warning_codes", top_row.get("buffer_warning_codes", ""))

    def stability(self, top_row):
        return self.decision(top_row).get("top1_stability", top_row.get("top1_stability"))

    @staticmethod
    def scores_by_set(row):
        if "scores_by_weight_set" in row:
            return row["scores_by_weight_set"]
        return {
            name: row.get(f"score_{name.lower()}")
            for name in ("BASE", "IGUAIS", "SEM_BARREIRAS", "APENAS_ACESSO", "ENFASE_BARREIRAS")
        }

    @staticmethod
    def ranks_by_set(row):
        if "ranks_by_weight_set" in row:
            return row["ranks_by_weight_set"]
        return {
            name: row.get(f"rank_{name.lower()}_within_buffer")
            for name in ("BASE", "IGUAIS", "SEM_BARREIRAS", "APENAS_ACESSO", "ENFASE_BARREIRAS")
        }

    def test_all_frozen_weight_sets_sum_to_one(self):
        weight_fields = (
            "road_trail_weight",
            "hydro_weight",
            "terrain_weight",
            "landcover_weight",
        )
        sets = self.config["scoring"]["weight_sets"]
        self.assertEqual(len(sets), 5)
        for item in sets:
            with self.subTest(weight_set=item["weight_set"]):
                self.assertAlmostEqual(sum(float(item[field]) for field in weight_fields), 1.0, places=12)

    def test_weighted_score_rank_and_selected_sector(self):
        rows = self.rank(
            ranking_sector(self.s1, road=1.0, hydro=0.8, terrain=0.7, landcover=0.6),
            ranking_sector(self.s2, road=0.4, hydro=0.5, terrain=0.5, landcover=0.5),
            ranking_sector(self.s3, road=0.1, hydro=0.2, terrain=0.2, landcover=0.2),
        )
        by_id = {row["sector_id"]: row for row in rows}
        expected = 0.30 * 1.0 + 0.25 * 0.8 + 0.20 * 0.7 + 0.25 * 0.6
        self.assertAlmostEqual(self.score(by_id[self.s1]), expected, places=9)
        self.assertEqual(self.rank_number(by_id[self.s1]), 1)
        self.assertEqual(self.rank_number(by_id[self.s2]), 2)
        self.assertTrue(all(0.0 <= self.score(row) <= 1.0 for row in rows))
        self.assertEqual(
            set(self.scores_by_set(by_id[self.s1])),
            {"BASE", "IGUAIS", "SEM_BARREIRAS", "APENAS_ACESSO", "ENFASE_BARREIRAS"},
        )
        self.assertEqual(set(self.ranks_by_set(by_id[self.s1])), set(self.scores_by_set(by_id[self.s1])))

    def test_invalid_geo_score_or_completeness_is_rejected(self):
        invalid = (
            {"road_trail_access_score": -0.01},
            {"hydro_access_score": 1.01},
            {"terrain_access_score": float("nan")},
            {"geo_completeness": -0.01},
            {"geo_completeness": 1.01},
        )
        for update in invalid:
            row = ranking_sector(self.s1, road=0.5, hydro=0.5, terrain=0.5, landcover=0.5)
            row.update(update)
            with self.subTest(update=update), self.assertRaises((ValueError, TypeError)):
                self.rank(row)

    def test_tie_break_is_sector_id_and_zero_margin_forces_review(self):
        rows = self.rank(
            ranking_sector(self.s2, road=0.8, hydro=0.8, terrain=0.8, landcover=0.8),
            ranking_sector(self.s1, road=0.8, hydro=0.8, terrain=0.8, landcover=0.8),
        )
        top = next(row for row in rows if self.rank_number(row) == 1)
        self.assertEqual(top["sector_id"], self.s1)
        self.assertAlmostEqual(self.margin(top), 0.0, places=12)
        self.assertIn(self.status(top), {"REVISAR", "ABSTER_REVISAO_HUMANA"})
        self.assertRegex(self.warnings(top), r"(?:TOP_SCORE_TIE|TIE)")

    def test_margin_is_top_minus_second_and_controls_review(self):
        clear = self.rank(
            ranking_sector(self.s1, road=1.0, hydro=1.0, terrain=1.0, landcover=1.0),
            ranking_sector(self.s2, road=0.5, hydro=0.5, terrain=0.5, landcover=0.5),
        )
        clear_top = next(row for row in clear if self.rank_number(row) == 1)
        self.assertAlmostEqual(self.margin(clear_top), 0.5, places=9)
        self.assertIn(self.status(clear_top), {"PRIORIZADO", "PRIORIZACAO_EMITIDA"})

        narrow = self.rank(
            ranking_sector(self.s1, road=0.80, hydro=0.80, terrain=0.80, landcover=0.80),
            ranking_sector(self.s2, road=0.77, hydro=0.77, terrain=0.77, landcover=0.77),
        )
        narrow_top = next(row for row in narrow if self.rank_number(row) == 1)
        self.assertAlmostEqual(self.margin(narrow_top), 0.03, places=9)
        self.assertIn(self.status(narrow_top), {"REVISAR", "ABSTER_REVISAO_HUMANA"})
        self.assertIn("LOW_MARGIN", self.warnings(narrow_top))

    def test_instability_across_weight_sets_forces_review(self):
        rows = self.rank(
            ranking_sector(self.s1, road=1.0, hydro=0.0, terrain=0.0, landcover=0.0),
            ranking_sector(self.s2, road=0.0, hydro=1.0, terrain=0.0, landcover=1.0),
        )
        top = next(row for row in rows if self.rank_number(row) == 1)
        self.assertEqual(top["sector_id"], self.s2)
        self.assertAlmostEqual(self.stability(top), 3 / 5, places=9)
        self.assertGreater(self.margin(top), 0.05)
        self.assertIn(self.status(top), {"REVISAR", "ABSTER_REVISAO_HUMANA"})
        self.assertRegex(self.warnings(top), r"(?:RANKING_UNSTABLE|UNSTABLE_TOP1)")

    def test_upstream_review_status_forces_downstream_review(self):
        rows = self.rank(
            ranking_sector(
                self.s1,
                road=1.0,
                hydro=1.0,
                terrain=1.0,
                landcover=1.0,
                upstream_review_status="REVISAR",
            ),
            ranking_sector(
                self.s2,
                road=0.0,
                hydro=0.0,
                terrain=0.0,
                landcover=0.0,
                upstream_review_status="REVISAR",
            ),
        )
        top = next(row for row in rows if self.rank_number(row) == 1)
        self.assertGreater(self.margin(top), 0.05)
        self.assertIn(self.status(top), {"REVISAR", "ABSTER_REVISAO_HUMANA"})
        self.assertRegex(self.warnings(top), r"(?:UPSTREAM_REVIEW_REQUIRED|SOURCE_BUFFER_REVIEW)")

    def test_missing_criterion_never_creates_silent_automatic_priority(self):
        incomplete = ranking_sector(
            self.s1,
            road=1.0,
            hydro=1.0,
            terrain=1.0,
            landcover=1.0,
        )
        del incomplete["terrain_access_score"]
        complete = ranking_sector(
            self.s2,
            road=0.5,
            hydro=0.5,
            terrain=0.5,
            landcover=0.5,
        )
        rows = self.rank(incomplete, complete)
        missing = next(row for row in rows if row["sector_id"] == self.s1)
        self.assertIsNone(self.score(missing))
        self.assertIsNone(self.rank_number(missing))
        decision = self.decision(next(row for row in rows if self.rank_number(row) == 1))
        self.assertIn(decision["decision_status"], {"REVISAR", "ABSTER_REVISAO_HUMANA"})
        self.assertRegex(decision.get("warning_codes", ""), r"(?:MISSING_REQUIRED_GEO_SCORE|INCOMPLETE_GEO)")

    def test_ranking_is_deterministic_and_preserves_firewall(self):
        source = [
            ranking_sector(self.s3, road=0.2, hydro=0.9, terrain=0.4, landcover=0.5),
            ranking_sector(self.s1, road=0.9, hydro=0.8, terrain=0.7, landcover=0.6),
            ranking_sector(self.s2, road=0.7, hydro=0.7, terrain=0.7, landcover=0.7),
        ]
        first = engine.rank_sector_records(copy.deepcopy(source), copy.deepcopy(self.config))
        second = engine.rank_sector_records(copy.deepcopy(source), copy.deepcopy(self.config))
        self.assertEqual(first, second)
        self.assertEqual(
            [(self.rank_number(row), row["sector_id"]) for row in first],
            sorted((self.rank_number(row), row["sector_id"]) for row in first),
        )
        for row in first:
            self.assertIs(row["ground_truth_used"], False)
            serialized = json.dumps(row, ensure_ascii=False).lower()
            self.assertNotIn("ground_truth_lat", serialized)
            self.assertNotIn("distance_to_truth", serialized)


class RecordingResult(unittest.TextTestResult):
    """Resultado estruturado para incorporar a evidência ao pacote técnico."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records: list[dict] = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.append({"test": test.id(), "status": "PASS"})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.records.append(
            {
                "test": test.id(),
                "status": "FAIL",
                "detail": self._exc_info_to_string(err, test),
            }
        )

    def addError(self, test, err):
        super().addError(test, err)
        self.records.append(
            {
                "test": test.id(),
                "status": "ERROR",
                "detail": self._exc_info_to_string(err, test),
            }
        )

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.records.append({"test": test.id(), "status": "SKIP", "detail": reason})


def run_with_optional_json_report(argv=None) -> int:
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
            "protocol_id": "EXT-ESP-SET-v1.0",
            "tests_run": result.testsRun,
            "passed": sum(item["status"] == "PASS" for item in result.records),
            "failed": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "successful": result.wasSuccessful(),
            "records": result.records,
        }
        report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(run_with_optional_json_report())
