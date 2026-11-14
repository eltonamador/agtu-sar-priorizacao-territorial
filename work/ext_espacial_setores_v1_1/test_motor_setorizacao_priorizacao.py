#!/usr/bin/env python3
"""Testes de aceitação do motor ``EXT-ESP-SET-v1.1``.

Os testes exercitam o contrato congelado de desenvolvimento sem abrir nem
derivar ground truth. Em especial, verificam que a geometria setorial é uma
partição do GeoJSON autoritativo recebido, que empates não são decididos pelo
identificador e que a ausência de um critério GEO não é mascarada por
renormalização dos pesos.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import motor_setorizacao_priorizacao as engine


EARTH_RADIUS_M = 6_371_008.8
CONFIG_PATH = Path(__file__).with_name("config_setorizacao_priorizacao_v1_1.json")
DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
WEIGHT_SETS = ("BASE", "IGUAIS", "SEM_BARREIRAS", "APENAS_ACESSO", "ENFASE_BARREIRAS")


def frozen_config() -> dict[str, Any]:
    """Lê uma cópia independente da configuração DEV-S congelada."""

    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def buffer_record(**updates: Any) -> dict[str, Any]:
    """Registro mínimo completo compatível com a saída do motor de buffer."""

    radius = 1_200.0
    record: dict[str, Any] = {
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


def buffer_payload(*records: Mapping[str, Any]) -> dict[str, Any]:
    rows = [dict(record) for record in (records or (buffer_record(),))]
    return {
        "protocol_id": "EXT-ESP-BUF-v1.0",
        "engine_version": "1.0.0",
        "ground_truth_used": False,
        "record_count": len(rows),
        "results": rows,
    }


def authoritative_ring(record: Mapping[str, Any], *, rotation_deg: float = 0.0) -> list[list[float]]:
    """Cria o polígono autoritativo coerente de 72 lados do motor a montante."""

    lat = float(record["estimated_lat"])
    lon = float(record["estimated_lon"])
    radius = float(record["adaptive_radius_m"])
    ring: list[list[float]] = []
    for index in range(72):
        p_lat, p_lon = engine.destination(lat, lon, radius, rotation_deg + index * 5.0)
        ring.append([p_lon, p_lat])
    ring.append(list(ring[0]))
    return ring


def buffer_geojson(*records: Mapping[str, Any], rotation_deg: float = 0.0) -> dict[str, Any]:
    """GeoJSON cego com exatamente um polígono autoritativo por candidato."""

    rows = [dict(record) for record in (records or (buffer_record(),))]
    features = []
    for row in rows:
        features.append(
            {
                "type": "Feature",
                "id": f"{row['scenario_id']}::{row['candidate_id']}",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [authoritative_ring(row, rotation_deg=rotation_deg)],
                },
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
    road: float | None,
    hydro: float | None,
    terrain: float | None,
    landcover: float | None,
    upstream_review_status: str = "CALCULADO",
    provenance: str = "FIXTURE_GEO_SINTETICA",
) -> dict[str, Any]:
    values = (road, hydro, terrain, landcover)
    return {
        "protocol_id": "EXT-ESP-SET-v1.1",
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
        "geo_completeness": sum(value is not None for value in values) / 4.0,
        "source_provenance": provenance,
        "upstream_review_status": upstream_review_status,
        "source_buffer_review_status": upstream_review_status,
        "source_execution_classification": "DESENVOLVIMENTO_NAO_CONFIRMATORIO",
        "source_confirmatory_eligible": False,
        "barrier_flags": "NAO_SINALIZADA",
        "ground_truth_used": False,
    }


def all_sector_ids() -> list[str]:
    return [
        f"T-001::T-001-C1::R{ring:02d}::{direction}"
        for ring in range(1, 4)
        for direction in DIRECTIONS
    ]


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def local_xy(lon: float, lat: float, lon0: float, lat0: float) -> tuple[float, float]:
    return (
        (lon - lon0) * 111_320.0 * math.cos(math.radians(lat0)),
        (lat - lat0) * 110_574.0,
    )


def planar_area(ring: Sequence[Sequence[float]], *, lon0: float, lat0: float) -> float:
    points = [local_xy(float(lon), float(lat), lon0, lat0) for lon, lat in ring]
    return abs(
        sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(points, points[1:]))
    ) / 2.0


def point_in_polygon_strict(point: Sequence[float], ring: Sequence[Sequence[float]]) -> bool:
    """Teste par-ímpar; os pontos de amostragem usados aqui não ficam na borda."""

    x, y = float(point[0]), float(point[1])
    inside = False
    for first, second in zip(ring, ring[1:]):
        x1, y1 = float(first[0]), float(first[1])
        x2, y2 = float(second[0]), float(second[1])
        if (y1 > y) != (y2 > y):
            x_cross = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < x_cross:
                inside = not inside
    return inside


def parsed_json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


class BufferContractTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.config = frozen_config()

    def validate(self, *records: Mapping[str, Any]) -> list[dict[str, Any]]:
        rows = tuple(records or (buffer_record(),))
        return engine.validate_buffer_contract(
            buffer_payload(*rows),
            buffer_geojson(*rows),
            config=copy.deepcopy(self.config),
        )

    def test_load_json_and_sha256_file(self) -> None:
        payload = buffer_payload()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "buffer.json"
            raw = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
            path.write_text(raw, encoding="utf-8")
            self.assertEqual(engine.load_json(path), payload)
            self.assertEqual(engine.sha256_file(path), hashlib.sha256(raw.encode()).hexdigest())

    def test_frozen_firewall_configuration_is_valid(self) -> None:
        engine.validate_firewall_config(copy.deepcopy(self.config))

    def test_valid_contract_normalizes_input_order(self) -> None:
        second = buffer_record(
            scenario_id="T-002",
            candidate_id="T-002-C1",
            source_row_hash=hashlib.sha256(b"fixture-T-002-C1").hexdigest(),
        )
        rows = self.validate(second, buffer_record())
        self.assertEqual(
            [(row["scenario_id"], row["candidate_id"]) for row in rows],
            [("T-001", "T-001-C1"), ("T-002", "T-002-C1")],
        )

    def test_authoritative_geometry_is_attached_to_normalized_record(self) -> None:
        rows = self.validate()
        attached = rows[0].get("_authoritative_buffer_ring")
        self.assertIsInstance(attached, list)
        self.assertEqual(attached[0], attached[-1])
        self.assertEqual(len(attached), 73)

    def test_root_and_record_ground_truth_flag_must_be_boolean_false(self) -> None:
        for value in (True, "false", 0, None):
            root = buffer_payload()
            root["ground_truth_used"] = value
            with self.subTest(place="root", value=value), self.assertRaises((ValueError, TypeError)):
                engine.validate_buffer_contract(root, buffer_geojson(), config=self.config)

            row = buffer_record(ground_truth_used=value)
            with self.subTest(place="record", value=value), self.assertRaises((ValueError, TypeError)):
                engine.validate_buffer_contract(
                    buffer_payload(row), buffer_geojson(row), config=self.config
                )

    def test_firewall_rejects_case_insensitive_compound_fragments_recursively(self) -> None:
        forbidden = (
            "analysis_Ground_Truth_Lat_estimate",
            "SOURCE_truth_longitude_value",
            "Current_REFERENCE_SECTOR_Code",
            "precomputed_Distance_To_Reference_m",
            "raw_Generator_Distance_km",
            "flag_Sector_Contains_Truth_v2",
            "candidate_REAL_LON_backup",
            "is_Relevant_Candidate_flag",
        )
        for field in forbidden:
            row = buffer_record()
            row["metadata"] = {"nested": [{field: 0.0}]}
            with self.subTest(field=field), self.assertRaises((ValueError, TypeError)):
                engine.validate_buffer_contract(
                    buffer_payload(row), buffer_geojson(row), config=self.config
                )

    def test_firewall_also_scans_authoritative_geojson(self) -> None:
        geojson = buffer_geojson()
        geojson["features"][0]["properties"]["analysis_Reference_Lat_source"] = 12.0
        with self.assertRaises((ValueError, TypeError)):
            engine.validate_buffer_contract(buffer_payload(), geojson, config=self.config)

    def test_firewall_allows_only_the_false_control_field(self) -> None:
        safe = {"metadata": {"ground_truth_used": False, "description": "controle cego"}}
        engine.enforce_ground_truth_firewall(safe, self.config)
        unsafe = {"metadata": {"ground_truth_used": True}}
        with self.assertRaises((ValueError, TypeError)):
            engine.enforce_ground_truth_firewall(unsafe, self.config)

    def test_record_count_and_duplicate_candidate_are_rejected(self) -> None:
        payload = buffer_payload()
        payload["record_count"] = 2
        with self.assertRaises((ValueError, TypeError)):
            engine.validate_buffer_contract(payload, buffer_geojson(), config=self.config)

        row = buffer_record()
        with self.assertRaises((ValueError, TypeError)):
            engine.validate_buffer_contract(
                buffer_payload(row, copy.deepcopy(row)),
                buffer_geojson(row, copy.deepcopy(row)),
                config=self.config,
            )

    def test_identifiers_cannot_embed_the_contract_separator(self) -> None:
        for update in ({"scenario_id": "T::001"}, {"candidate_id": "T-001::C1"}):
            row = buffer_record(**update)
            with self.subTest(update=update), self.assertRaises((ValueError, TypeError)):
                engine.validate_buffer_contract(
                    buffer_payload(row), buffer_geojson(row), config=self.config
                )

    def test_invalid_coordinates_radius_hash_and_numbers_are_rejected(self) -> None:
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
                engine.validate_buffer_contract(
                    buffer_payload(row), buffer_geojson(row), config=self.config
                )


class SectorGeometryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.config = frozen_config()
        self.source_record = buffer_record()
        self.source_geojson = buffer_geojson(self.source_record, rotation_deg=0.0)
        self.source_ring = self.source_geojson["features"][0]["geometry"]["coordinates"][0]
        self.records = engine.validate_buffer_contract(
            buffer_payload(self.source_record),
            copy.deepcopy(self.source_geojson),
            config=copy.deepcopy(self.config),
        )

    def sectors(self) -> list[dict[str, Any]]:
        return engine.make_sector_records(copy.deepcopy(self.records), copy.deepcopy(self.config))

    @staticmethod
    def ring(row: Mapping[str, Any]) -> list[list[float]]:
        if "geometry_coordinates" in row:
            return row["geometry_coordinates"]
        return row["geometry"]["coordinates"][0]

    def test_destination_uses_meters_and_returns_lat_lon(self) -> None:
        lat, lon = engine.destination(12.345678, -45.678901, 1_200.0, 0.0)
        self.assertAlmostEqual(haversine_m(12.345678, -45.678901, lat, lon), 1_200.0, delta=0.03)
        self.assertGreater(lat, 12.345678)

    def test_exactly_24_sectors_are_created_per_candidate(self) -> None:
        sectors = self.sectors()
        self.assertEqual(len(sectors), 24)
        self.assertEqual({row["scenario_id"] for row in sectors}, {"T-001"})
        self.assertEqual({row["candidate_id"] for row in sectors}, {"T-001-C1"})

    def test_sector_ids_are_unique_stable_and_ordered(self) -> None:
        first = self.sectors()
        second = self.sectors()
        self.assertEqual(first, second)
        ids = [row["sector_id"] for row in first]
        self.assertEqual(ids, all_sector_ids())
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual([row["sector_index"] for row in first], list(range(1, 25)))

    def test_three_equal_area_bands_and_eight_directions(self) -> None:
        sectors = self.sectors()
        self.assertEqual(sorted({row["ring_index"] for row in sectors}), [1, 2, 3])
        self.assertEqual(sorted({row["direction_index"] for row in sectors}), list(range(1, 9)))
        self.assertEqual({row["direction_label"] for row in sectors}, set(DIRECTIONS))
        for band in (1, 2, 3):
            self.assertEqual(sum(row["ring_index"] == band for row in sectors), 8)

    def test_outer_boundary_reuses_the_authoritative_72_vertex_buffer(self) -> None:
        outer_vertices = [
            coordinate
            for row in self.sectors()
            if row["ring_index"] == 3
            for coordinate in self.ring(row)
        ]
        lat0 = float(self.source_record["estimated_lat"])
        lon0 = float(self.source_record["estimated_lon"])
        for source_vertex in self.source_ring[:-1]:
            sx, sy = local_xy(source_vertex[0], source_vertex[1], lon0, lat0)
            nearest = min(
                math.hypot(
                    sx - local_xy(vertex[0], vertex[1], lon0, lat0)[0],
                    sy - local_xy(vertex[0], vertex[1], lon0, lat0)[1],
                )
                for vertex in outer_vertices
            )
            self.assertLess(nearest, 0.03)

    def test_sector_area_sum_matches_authoritative_parent_within_one_ppm(self) -> None:
        lat0 = float(self.source_record["estimated_lat"])
        lon0 = float(self.source_record["estimated_lon"])
        parent_area = planar_area(self.source_ring, lon0=lon0, lat0=lat0)
        sector_areas = [planar_area(self.ring(row), lon0=lon0, lat0=lat0) for row in self.sectors()]
        relative_error = abs(sum(sector_areas) - parent_area) / parent_area
        self.assertLessEqual(relative_error, 1e-6)

    def test_each_sector_has_one_twenty_four_of_authoritative_area(self) -> None:
        lat0 = float(self.source_record["estimated_lat"])
        lon0 = float(self.source_record["estimated_lon"])
        expected = planar_area(self.source_ring, lon0=lon0, lat0=lat0) / 24.0
        tolerance = float(self.config["geometry"]["area_equality_relative_tolerance"])
        for row in self.sectors():
            actual = planar_area(self.ring(row), lon0=lon0, lat0=lat0)
            self.assertLessEqual(abs(actual - expected) / expected, tolerance)

    def test_deterministic_interior_samples_do_not_overlap_other_sectors(self) -> None:
        sectors = self.sectors()
        rings = {row["sector_id"]: self.ring(row) for row in sectors}
        for owner in sectors:
            samples = owner.get("sample_points", [])
            self.assertEqual(len(samples), 9)
            for sample_lat, sample_lon in samples:
                point = [sample_lon, sample_lat]
                memberships = [
                    sector_id
                    for sector_id, ring in rings.items()
                    if point_in_polygon_strict(point, ring)
                ]
                self.assertEqual(memberships, [owner["sector_id"]])

    def test_sector_geometry_is_closed_finite_and_serializable(self) -> None:
        sectors = self.sectors()
        for row in sectors:
            geometry = row["geometry"]
            self.assertEqual(geometry["type"], "Polygon")
            self.assertEqual(len(geometry["coordinates"]), 1)
            ring = self.ring(row)
            self.assertGreaterEqual(len(ring), 4)
            self.assertEqual(ring[0], ring[-1])
            for lon, lat in ring:
                self.assertTrue(math.isfinite(lon) and math.isfinite(lat))
                self.assertTrue(-180.0 <= lon <= 180.0)
                self.assertTrue(-90.0 <= lat <= 90.0)
        encoded = json.dumps(sectors, ensure_ascii=False, sort_keys=True, allow_nan=False)
        decoded = json.loads(encoded)
        self.assertEqual(len(decoded), 24)
        self.assertEqual(
            json.dumps(decoded, ensure_ascii=False, sort_keys=True, allow_nan=False),
            encoded,
        )

    def test_sector_outputs_preserve_firewall_and_lineage(self) -> None:
        for row in self.sectors():
            self.assertIs(row["ground_truth_used"], False)
            self.assertEqual(row["source_row_hash"], self.records[0]["source_row_hash"])
            engine.enforce_ground_truth_firewall(row, self.config)


class SectorRankingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.config = frozen_config()
        self.s1, self.s2, self.s3, self.s4 = all_sector_ids()[:4]
        self.sector_ids = all_sector_ids()
        self.last_decisions: list[dict[str, Any]] = []

    def rank(self, *records: Mapping[str, Any]) -> list[dict[str, Any]]:
        supplied = {str(row["sector_id"]): copy.deepcopy(dict(row)) for row in records}
        complete = [
            supplied.get(
                sector_id,
                ranking_sector(sector_id, road=0.0, hydro=0.0, terrain=0.0, landcover=0.0),
            )
            for sector_id in self.sector_ids
        ]
        return self.rank_raw(complete)

    def rank_raw(self, records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        materialized = list(copy.deepcopy(list(records)))
        result = engine.rank_sector_records(materialized, copy.deepcopy(self.config))
        if isinstance(result, tuple):
            ranked, decisions = result
            self.last_decisions = list(decisions)
            return list(ranked)
        ranked = list(result)
        self.last_decisions = engine.summarize_buffer_decisions(ranked, copy.deepcopy(self.config))
        return ranked

    @staticmethod
    def score(row: Mapping[str, Any]) -> float | None:
        return row.get("priority_score", row.get("score_base"))

    @staticmethod
    def rank_number(row: Mapping[str, Any]) -> int | None:
        return row.get("sector_rank", row.get("rank_base_within_buffer"))

    def decision(self) -> dict[str, Any]:
        self.assertEqual(len(self.last_decisions), 1)
        return self.last_decisions[0]

    @staticmethod
    def scores_by_set(row: Mapping[str, Any]) -> Mapping[str, Any]:
        return row["scores_by_weight_set"]

    @staticmethod
    def ranks_by_set(row: Mapping[str, Any]) -> Mapping[str, Any]:
        return row["ranks_by_weight_set"]

    def test_all_frozen_weight_sets_sum_to_one(self) -> None:
        weight_fields = (
            "road_trail_weight",
            "hydro_weight",
            "terrain_weight",
            "landcover_weight",
        )
        sets = self.config["scoring"]["weight_sets"]
        self.assertEqual([item["weight_set"] for item in sets], list(WEIGHT_SETS))
        for item in sets:
            with self.subTest(weight_set=item["weight_set"]):
                self.assertAlmostEqual(sum(float(item[field]) for field in weight_fields), 1.0, places=12)

    def test_weighted_score_and_unique_selection(self) -> None:
        rows = self.rank(
            ranking_sector(self.s1, road=1.0, hydro=0.8, terrain=0.7, landcover=0.6),
            ranking_sector(self.s2, road=0.4, hydro=0.5, terrain=0.5, landcover=0.5),
            ranking_sector(self.s3, road=0.1, hydro=0.2, terrain=0.2, landcover=0.2),
        )
        by_id = {row["sector_id"]: row for row in rows}
        expected = 0.30 * 1.0 + 0.25 * 0.8 + 0.20 * 0.7 + 0.25 * 0.6
        self.assertAlmostEqual(self.score(by_id[self.s1]), expected, places=9)
        self.assertEqual(self.rank_number(by_id[self.s1]), 1)
        self.assertTrue(by_id[self.s1]["selected_sector"])
        self.assertEqual(self.decision()["top1_sector_id"], self.s1)
        self.assertEqual(set(self.scores_by_set(by_id[self.s1])), set(WEIGHT_SETS))
        self.assertEqual(set(self.ranks_by_set(by_id[self.s1])), set(WEIGHT_SETS))

    def test_competition_ranking_is_1_2_2_4(self) -> None:
        rows = self.rank(
            ranking_sector(self.s1, road=0.9, hydro=0.9, terrain=0.9, landcover=0.9),
            ranking_sector(self.s2, road=0.8, hydro=0.8, terrain=0.8, landcover=0.8),
            ranking_sector(self.s3, road=0.8, hydro=0.8, terrain=0.8, landcover=0.8),
            ranking_sector(self.s4, road=0.7, hydro=0.7, terrain=0.7, landcover=0.7),
        )
        by_id = {row["sector_id"]: row for row in rows}
        self.assertEqual(
            [self.rank_number(by_id[item]) for item in (self.s1, self.s2, self.s3, self.s4)],
            [1, 2, 2, 4],
        )

    def test_scores_are_quantized_to_nine_decimals_before_tie_comparison(self) -> None:
        rows = self.rank(
            ranking_sector(self.s1, road=0.8, hydro=0.8, terrain=0.8, landcover=0.8),
            ranking_sector(
                self.s2,
                road=0.8000000002,
                hydro=0.8000000002,
                terrain=0.8000000002,
                landcover=0.8000000002,
            ),
        )
        by_id = {row["sector_id"]: row for row in rows}
        self.assertEqual(self.rank_number(by_id[self.s1]), 1)
        self.assertEqual(self.rank_number(by_id[self.s2]), 1)

    def test_base_tie_has_no_selection_and_requires_review(self) -> None:
        rows = self.rank(
            ranking_sector(self.s2, road=0.8, hydro=0.8, terrain=0.8, landcover=0.8),
            ranking_sector(self.s1, road=0.8, hydro=0.8, terrain=0.8, landcover=0.8),
        )
        by_id = {row["sector_id"]: row for row in rows}
        self.assertEqual(self.rank_number(by_id[self.s1]), 1)
        self.assertEqual(self.rank_number(by_id[self.s2]), 1)
        self.assertFalse(any(row["selected_sector"] for row in rows))
        decision = self.decision()
        self.assertIsNone(decision["top1_sector_id"])
        self.assertEqual(decision["decision_status"], "REVISAR")
        # Sem vencedor único, a síntese não atribui a margem a um candidato;
        # cada linha ainda registra corretamente a diferença nula entre os
        # dois maiores escores BASE.
        self.assertIsNone(decision["base_margin"])
        self.assertEqual(by_id[self.s1]["rank_margin"], 0.0)
        self.assertEqual(by_id[self.s2]["rank_margin"], 0.0)
        self.assertIn("BASE_TOP_TIE", decision["warning_codes"])
        self.assertIn("NO_UNIQUE_TOP1", decision["warning_codes"])
        base_tops = parsed_json(decision["top1_sector_ids_base"])
        self.assertEqual(set(base_tops), {self.s1, self.s2})

    def test_sensitivity_tie_uses_fractional_support_and_unique_wins(self) -> None:
        rows = self.rank(
            ranking_sector(self.s1, road=0.5, hydro=1.0, terrain=1.0, landcover=1.0),
            ranking_sector(self.s2, road=0.5, hydro=0.0, terrain=0.0, landcover=0.0),
        )
        by_id = {row["sector_id"]: row for row in rows}
        winner = by_id[self.s1]
        runner = by_id[self.s2]
        self.assertEqual(winner["top1_membership_count"], 5)
        self.assertEqual(winner["top1_unique_win_count"], 4)
        self.assertAlmostEqual(winner["top1_support_points"], 4.5, places=9)
        self.assertAlmostEqual(winner["top1_stability"], 0.9, places=9)
        self.assertEqual(runner["top1_membership_count"], 1)
        self.assertEqual(runner["top1_unique_win_count"], 0)
        self.assertAlmostEqual(runner["top1_support_points"], 0.5, places=9)
        self.assertAlmostEqual(runner["top1_stability"], 0.1, places=9)
        decision = self.decision()
        top_by_set = parsed_json(decision["top1_by_weight_set"])
        self.assertEqual(set(top_by_set["APENAS_ACESSO"]), {self.s1, self.s2})
        self.assertIn("SENSITIVITY_TOP_TIE", decision["warning_codes"])
        self.assertEqual(decision["decision_status"], "PRIORIZADO")

    def test_tie_outcome_is_invariant_to_input_order_and_identifier_lexicon(self) -> None:
        a = ranking_sector(
            "T-001::T-001-C1::R01::ZETA", road=0.8, hydro=0.8, terrain=0.8, landcover=0.8
        )
        b = ranking_sector(
            "T-001::T-001-C1::R01::ALFA", road=0.8, hydro=0.8, terrain=0.8, landcover=0.8
        )
        first = self.rank_raw([a, b])
        first_decision = copy.deepcopy(self.decision())
        second = self.rank_raw([b, a])
        second_decision = copy.deepcopy(self.decision())
        self.assertEqual(first, second)
        self.assertEqual(first_decision, second_decision)
        self.assertFalse(any(row["selected_sector"] for row in first))
        self.assertEqual({self.rank_number(row) for row in first}, {1})

        renamed = [
            ranking_sector(
                "T-001::T-001-C1::R01::BETA", road=0.8, hydro=0.8, terrain=0.8, landcover=0.8
            ),
            ranking_sector(
                "T-001::T-001-C1::R01::GAMA", road=0.8, hydro=0.8, terrain=0.8, landcover=0.8
            ),
        ]
        renamed_rows = self.rank_raw(renamed)
        self.assertFalse(any(row["selected_sector"] for row in renamed_rows))
        self.assertEqual({self.rank_number(row) for row in renamed_rows}, {1})

    def test_margin_is_top_minus_second_and_low_margin_forces_review(self) -> None:
        clear = self.rank(
            ranking_sector(self.s1, road=1.0, hydro=1.0, terrain=1.0, landcover=1.0),
            ranking_sector(self.s2, road=0.5, hydro=0.5, terrain=0.5, landcover=0.5),
        )
        clear_top = next(row for row in clear if row["selected_sector"])
        self.assertAlmostEqual(clear_top["rank_margin"], 0.5, places=9)
        self.assertEqual(self.decision()["decision_status"], "PRIORIZADO")

        narrow = self.rank(
            ranking_sector(self.s1, road=0.80, hydro=0.80, terrain=0.80, landcover=0.80),
            ranking_sector(self.s2, road=0.77, hydro=0.77, terrain=0.77, landcover=0.77),
        )
        narrow_top = next(row for row in narrow if row["selected_sector"])
        self.assertAlmostEqual(narrow_top["rank_margin"], 0.03, places=9)
        self.assertEqual(self.decision()["decision_status"], "REVISAR")
        self.assertIn("LOW_MARGIN", self.decision()["warning_codes"])

    def test_missing_required_score_nulls_every_weight_set_without_renormalization(self) -> None:
        incomplete = ranking_sector(
            self.s1, road=1.0, hydro=1.0, terrain=None, landcover=1.0
        )
        complete = ranking_sector(
            self.s2, road=0.5, hydro=0.5, terrain=0.5, landcover=0.5
        )
        rows = self.rank(incomplete, complete)
        missing = next(row for row in rows if row["sector_id"] == self.s1)
        self.assertEqual(set(self.scores_by_set(missing)), set(WEIGHT_SETS))
        self.assertTrue(all(value is None for value in self.scores_by_set(missing).values()))
        self.assertTrue(all(value is None for value in self.ranks_by_set(missing).values()))
        self.assertIsNone(self.score(missing))
        self.assertIsNone(self.rank_number(missing))
        decision = self.decision()
        self.assertEqual(decision["decision_status"], "REVISAR")
        self.assertIn("INCOMPLETE_GEO", decision["warning_codes"])
        self.assertIn("MISSING_REQUIRED_GEO_SCORE", missing["warning_codes"])

    def test_missing_provenance_forces_review(self) -> None:
        self.rank(
            ranking_sector(
                self.s1,
                road=1.0,
                hydro=1.0,
                terrain=1.0,
                landcover=1.0,
                provenance="",
            )
        )
        self.assertEqual(self.decision()["decision_status"], "REVISAR")
        self.assertIn("MISSING_SOURCE_PROVENANCE", self.decision()["warning_codes"])

    def test_upstream_review_forces_downstream_review(self) -> None:
        self.rank(
            ranking_sector(
                self.s1,
                road=1.0,
                hydro=1.0,
                terrain=1.0,
                landcover=1.0,
                upstream_review_status="REVISAR",
            )
        )
        self.assertEqual(self.decision()["decision_status"], "REVISAR")
        self.assertIn("UPSTREAM_REVIEW_REQUIRED", self.decision()["warning_codes"])

    def test_invalid_geo_score_or_completeness_is_rejected(self) -> None:
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

    def test_ranking_is_deterministic_firewalled_and_json_serializable(self) -> None:
        source = [
            ranking_sector(self.s3, road=0.2, hydro=0.9, terrain=0.4, landcover=0.5),
            ranking_sector(self.s1, road=0.9, hydro=0.8, terrain=0.7, landcover=0.6),
            ranking_sector(self.s2, road=0.7, hydro=0.7, terrain=0.7, landcover=0.7),
        ]
        first = self.rank(*source)
        first_decisions = copy.deepcopy(self.last_decisions)
        second = self.rank(*reversed(source))
        second_decisions = copy.deepcopy(self.last_decisions)
        self.assertEqual(first, second)
        self.assertEqual(first_decisions, second_decisions)
        encoded = json.dumps(
            {"ranked": first, "decisions": first_decisions},
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
        self.assertEqual(json.loads(encoded)["ranked"], first)
        for row in [*first, *first_decisions]:
            self.assertIs(row["ground_truth_used"], False)
            engine.enforce_ground_truth_firewall(row, self.config)


class RecordingResult(unittest.TextTestResult):
    """Resultado estruturado para incorporar a evidência ao pacote técnico."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.records: list[dict[str, Any]] = []

    def addSuccess(self, test: unittest.TestCase) -> None:
        super().addSuccess(test)
        self.records.append({"test": test.id(), "status": "PASS"})

    def addFailure(self, test: unittest.TestCase, err: Any) -> None:
        super().addFailure(test, err)
        self.records.append(
            {"test": test.id(), "status": "FAIL", "detail": self._exc_info_to_string(err, test)}
        )

    def addError(self, test: unittest.TestCase, err: Any) -> None:
        super().addError(test, err)
        self.records.append(
            {"test": test.id(), "status": "ERROR", "detail": self._exc_info_to_string(err, test)}
        )

    def addSkip(self, test: unittest.TestCase, reason: str) -> None:
        super().addSkip(test, reason)
        self.records.append({"test": test.id(), "status": "SKIP", "detail": reason})


def run_with_optional_json_report(argv: Sequence[str] | None = None) -> int:
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
            "protocol_id": "EXT-ESP-SET-v1.1",
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
