from __future__ import annotations

import copy
import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("profile_integration", HERE / "profile_integration.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


SCENARIO = "TEST-001"
CANDIDATE = "TEST-001-C1"
CREATED = "2026-10-21T12:00:00-03:00"
FROZEN = "2026-10-21T12:01:00-03:00"
LOC_INPUT_SHA = "e" * 64


def canonical_write(path: Path, value: object) -> None:
    path.write_bytes(MODULE.ranker.canonical_json_bytes(value))


def make_compiled(hypotheses: list[dict] | None = None) -> dict:
    value = {
        "compiler_id": "PERFIL-V2-QUAL-COMPILER-v1.1",
        "schema_id": "urn:agtu:sar:perfil-vitima:v2-draft-2",
        "scenario_id": SCENARIO,
        "protocol_version": "PERFIL-V2-DRAFT.2",
        "source_record_status": "CONGELADO",
        "source_freeze_metadata": {
            "frozen_at": "2026-10-21T10:00:00-03:00",
            "operator_code": "OP-01",
            "schema_id": "urn:agtu:sar:perfil-vitima:v2-draft-2",
            "payload_sha256": "a" * 64,
        },
        "freeze_validation": {
            "projection_id": "PERFIL-V2-FREEZE-PROJECTION-v1",
            "status": "VERIFIED",
        },
        "mode": "QUALITATIVO_SEM_PESOS_SEM_RANKING",
        "input_sha256": "d" * 64,
        "ground_truth_absent": True,
        "hypotheses": hypotheses or [],
        "scope_guards": {
            "ground_truth_firewall_passed": True,
            "unknown_values_create_effect": False,
            "free_text_directly_converted_to_weight": False,
            "suspicion_upgraded_to_confirmation": False,
            "weights_or_ranking_implemented": False,
        },
        "firewall_manifest": {
            "policy_id": "PERFIL-V2-GT-FIREWALL-v1.1",
            "recursive_key_scan": True,
            "forbidden_alias_scan_pt_en": True,
            "explicit_text_marker_scan": True,
            "schema_disallows_free_objects_in_facts": True,
            "text_fields_sanitized_declared": True,
            "status": "PASS",
        },
    }
    value["compiled_sha256"] = MODULE.ranker.canonical_sha256(value)
    return value


def support() -> dict:
    return {
        "nature": "OBSERVADO",
        "confidence": "ALTA",
        "authorized_for_model": True,
    }


def destination_hypothesis() -> dict:
    return {
        "hypothesis_id": "H001",
        "source_clue_id": "CLUE-DEST-01",
        "hypothesis_type": "DESTINO_OU_LUGAR_FAMILIAR",
        "spatialized": True,
        "spatial_status": "ESPACIALIZADA",
        "associated_location": {"latitude": 0.0005, "longitude": 0.0005},
        "supports": [support()],
    }


def direction_hypothesis(origin_lat: float = 0.0, origin_lon: float = 0.0) -> dict:
    return {
        "hypothesis_id": "H002",
        "source_clue_id": "CLUE-DIR-01",
        "hypothesis_type": "DIRECAO_OBSERVADA",
        "spatialized": True,
        "spatial_status": "ESPACIALIZADA",
        "associated_location": {"latitude": origin_lat, "longitude": origin_lon},
        "direction_data": {
            "azimuth_deg": 45.0,
            "cardinal_direction": None,
            "angular_tolerance_deg": 22.5,
        },
        "supports": [support()],
    }


class Fixture:
    def __init__(self, root: Path, hypotheses: list[dict] | None = None, nonconfirmatory: bool = False):
        self.root = root
        self.profile = root / "compiled.json"
        self.ranking = root / "sector_ranking.csv"
        self.polygons = root / "sector_polygons.geojson"
        self.buffers = root / "buffer_results.json"
        self.manifest = root / "manifest.json"
        self.review = root / "review.json"
        self.output = root / "v3.json"
        self.report = root / "report.json"
        canonical_write(self.profile, make_compiled(hypotheses))
        classification = (
            "DIAGNOSTICO_LEGADO_NAO_CONFIRMATORIO"
            if nonconfirmatory
            else "ELEGIVEL_PARA_AVALIACAO_CONFIRMATORIA"
        )
        row_hash = "b" * 64
        self.buffer_value = {
            "protocol_id": "BUF-v1",
            "ground_truth_used": False,
            "results": [
                {
                    "protocol_id": "BUF-v1",
                    "scenario_id": SCENARIO,
                    "candidate_id": CANDIDATE,
                    "estimated_lat": 0.0,
                    "estimated_lon": 0.0,
                    "source_row_hash": row_hash,
                    "execution_classification": classification,
                    "confirmatory_eligible": not nonconfirmatory,
                    "ground_truth_used": False,
                }
            ],
        }
        canonical_write(self.buffers, self.buffer_value)
        self.geo_value = {
            "type": "FeatureCollection",
            "ground_truth_used": False,
            "features": [],
        }
        sectors = [
            ("SEC-N", 0.7, 315.0, 45.0, [[0, 0], [0.01, 0], [0, 0.01], [0, 0]]),
            ("SEC-S", 0.3, 135.0, 225.0, [[0, 0], [0, -0.01], [0.01, 0], [0, 0]]),
        ]
        headers = [
            "scenario_id", "candidate_id", "sector_id", "score_base", "priority_score",
            "azimuth_start_deg", "azimuth_end_deg", "ground_truth_used", "protocol_id",
            "source_buffer_geometry_sha256", "source_row_hash", "source_execution_classification",
        ]
        with self.ranking.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=headers)
            writer.writeheader()
            for sector_id, score, start, end, ring in sectors:
                writer.writerow(
                    {
                        "scenario_id": SCENARIO,
                        "candidate_id": CANDIDATE,
                        "sector_id": sector_id,
                        "score_base": score,
                        "priority_score": score,
                        "azimuth_start_deg": start,
                        "azimuth_end_deg": end,
                        "ground_truth_used": "false",
                        "protocol_id": "SET-v1",
                        "source_buffer_geometry_sha256": "c" * 64,
                        "source_row_hash": row_hash,
                        "source_execution_classification": classification,
                    }
                )
                self.geo_value["features"].append(
                    {
                        "type": "Feature",
                        "id": sector_id,
                        "properties": {
                            "scenario_id": SCENARIO,
                            "candidate_id": CANDIDATE,
                            "sector_id": sector_id,
                            "score_base": score,
                            "azimuth_start_deg": start,
                            "azimuth_end_deg": end,
                            "ground_truth_used": False,
                            "protocol_id": "SET-v1",
                            "source_buffer_geometry_sha256": "c" * 64,
                            "source_row_hash": row_hash,
                            "source_execution_classification": classification,
                        },
                        "geometry": {"type": "Polygon", "coordinates": [ring]},
                    }
                )
        canonical_write(self.polygons, self.geo_value)
        self.rebuild_manifest(nonconfirmatory)

    def rebuild_manifest(self, nonconfirmatory: bool = False) -> None:
        value = {
            "protocol_id": "SET-v1",
            "execution_classification": (
                "DESENVOLVIMENTO_NAO_CONFIRMATORIO"
                if nonconfirmatory
                else "ELEGIVEL_PARA_AVALIACAO_CONFIRMATORIA"
            ),
            "ground_truth_used": False,
            "firewall": "GROUND_TRUTH_PROHIBITED_AND_NOT_USED",
            "generated_at_utc": "2026-10-21T14:30:00+00:00",
            "sectors_per_buffer": 2,
            "files": [
                {"path": str(self.ranking), "role": "output", "sha256": MODULE.file_sha256(self.ranking)},
                {"path": str(self.polygons), "role": "output", "sha256": MODULE.file_sha256(self.polygons)},
                {"path": str(self.buffers), "role": "input_buffer_json", "sha256": MODULE.file_sha256(self.buffers)},
            ],
        }
        canonical_write(self.manifest, value)

    def review_draft(self, entries: list[dict]) -> dict:
        return {
            "protocol_version": MODULE.REVIEW_PROTOCOL,
            "scenario_id": SCENARIO,
            "candidate_id": CANDIDATE,
            "record_status": "RASCUNHO",
            "created_at": "2026-10-21T11:31:00-03:00",
            "ground_truth_absent": True,
            "source_profile_file_sha256": MODULE.file_sha256(self.profile),
            "source_territorial_manifest_sha256": MODULE.file_sha256(self.manifest),
            "reviewer_code": "REV-01",
            "entries": entries,
            "freeze_metadata": None,
        }

    def freeze_review(self, entries: list[dict]) -> None:
        frozen = MODULE.prepare_frozen_review(
            self.review_draft(entries), "2026-10-21T11:32:00-03:00"
        )
        canonical_write(self.review, frozen)

    def build(self, *, review: bool = True, allow_nonconfirmatory: bool = False):
        return MODULE.build_v3_input(
            profile_path=self.profile,
            territorial_manifest_path=self.manifest,
            ranking_path=self.ranking,
            polygons_path=self.polygons,
            buffers_path=self.buffers,
            spatial_review_path=self.review if review else None,
            scenario_id=SCENARIO,
            candidate_id=CANDIDATE,
            source_loc_input_sha256=LOC_INPUT_SHA,
            source_case_revision=1,
            created_at=CREATED,
            frozen_at=FROZEN,
            allow_nonconfirmatory=allow_nonconfirmatory,
        )


class IntegrationTest(unittest.TestCase):
    def test_no_review_excludes_spatial_hypothesis_without_invention(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory), [destination_hypothesis()])
            result, report = fixture.build(review=False)
            self.assertEqual(result["hypotheses"], [])
            self.assertEqual(report["excluded_spatial_hypotheses"][0]["reason"], "SEM_REVISAO_ESPACIAL_CONGELADA")
            MODULE.ranker.validate_input(result)

    def test_destination_uses_v2_coordinates_and_reviewed_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory), [destination_hypothesis()])
            fixture.freeze_review(
                [
                    {
                        "source_hypothesis_id": "H001",
                        "decision": "INCLUIR",
                        "reviewed_at": "2026-10-21T11:31:30-03:00",
                        "family": "DESTINO",
                        "hypothesis_type": "DESTINO_DECLARADO",
                        "location_uncertainty_m": 25.0,
                        "spatial_source": "Coordenada documentada na ficha operacional",
                    }
                ]
            )
            result, _ = fixture.build()
            hypothesis = result["hypotheses"][0]
            self.assertEqual(hypothesis["evidence_group_id"], "CLUE-DEST-01")
            self.assertEqual(hypothesis["destination"]["latitude"], 0.0005)
            self.assertEqual(hypothesis["destination"]["location_uncertainty_m"], 25.0)
            self.assertEqual(result["source_spatial_review_sha256"], MODULE.file_sha256(fixture.review))

    def test_direction_origin_mismatch_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory), [direction_hypothesis(0.000000001, 0.0)])
            fixture.freeze_review(
                [
                    {
                        "source_hypothesis_id": "H002",
                        "decision": "INCLUIR",
                        "reviewed_at": "2026-10-21T11:31:30-03:00",
                        "family": "DIRECAO",
                        "origin_candidate_id": CANDIDATE,
                        "spatial_source": "Origem documentada",
                    }
                ]
            )
            result, report = fixture.build()
            self.assertEqual(result["hypotheses"], [])
            self.assertEqual(report["excluded_spatial_hypotheses"][0]["reason"], "ORIGEM_DIRECAO_DIVERGE_DO_CANDIDATO")

    def test_direction_origin_exactly_equal_is_included(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory), [direction_hypothesis(0.0, 0.0)])
            fixture.freeze_review(
                [
                    {
                        "source_hypothesis_id": "H002",
                        "decision": "INCLUIR",
                        "reviewed_at": "2026-10-21T11:31:30-03:00",
                        "family": "DIRECAO",
                        "origin_candidate_id": CANDIDATE,
                        "spatial_source": "Origem documentada",
                    }
                ]
            )
            result, _ = fixture.build()
            self.assertEqual(result["hypotheses"][0]["direction"]["azimuth_deg"], 45.0)

    def test_tampered_v2_internal_hash_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            payload = json.loads(fixture.profile.read_text())
            payload["scenario_id"] = "OTHER-001"
            canonical_write(fixture.profile, payload)
            with self.assertRaises(MODULE.IntegrationError):
                fixture.build(review=False)

    def test_manifest_file_hash_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            fixture.ranking.write_text(fixture.ranking.read_text() + "\n", encoding="utf-8")
            with self.assertRaises(MODULE.IntegrationError):
                fixture.build(review=False)

    def test_self_intersecting_polygon_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            geo = json.loads(fixture.polygons.read_text())
            geo["features"][0]["geometry"]["coordinates"] = [
                [[0, 0], [0.01, 0.01], [0, 0.01], [0.01, 0], [0, 0]]
            ]
            canonical_write(fixture.polygons, geo)
            fixture.rebuild_manifest()
            with self.assertRaisesRegex(MODULE.IntegrationError, "auto-intersectante|área nula"):
                fixture.build(review=False)

    def test_nonconfirmatory_requires_explicit_flag_and_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory), nonconfirmatory=True)
            with self.assertRaisesRegex(MODULE.IntegrationError, "não confirmatório"):
                fixture.build(review=False)
            _, report = fixture.build(review=False, allow_nonconfirmatory=True)
            self.assertTrue(report["source_territorial"]["nonconfirmatory_explicitly_allowed"])

    def test_unknown_english_classification_cannot_bypass_positive_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            classification = "NOT_CONFIRMATORY"
            buffer_payload = json.loads(fixture.buffers.read_text())
            buffer_payload["results"][0]["execution_classification"] = classification
            buffer_payload["results"][0]["confirmatory_eligible"] = True
            canonical_write(fixture.buffers, buffer_payload)

            with fixture.ranking.open("r", encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                rows = list(reader)
                headers = list(reader.fieldnames or [])
            for row in rows:
                row["source_execution_classification"] = classification
            with fixture.ranking.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)

            geo = json.loads(fixture.polygons.read_text())
            for feature in geo["features"]:
                feature["properties"]["source_execution_classification"] = classification
            canonical_write(fixture.polygons, geo)
            fixture.rebuild_manifest()
            manifest = json.loads(fixture.manifest.read_text())
            manifest["execution_classification"] = classification
            canonical_write(fixture.manifest, manifest)

            with self.assertRaisesRegex(MODULE.IntegrationError, "não confirmatório"):
                fixture.build(review=False)
            _, report = fixture.build(review=False, allow_nonconfirmatory=True)
            self.assertFalse(report["source_territorial"]["confirmatory_package"])

    def test_review_must_bind_exact_source_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory), [destination_hypothesis()])
            draft = fixture.review_draft([])
            draft["source_profile_file_sha256"] = "f" * 64
            frozen = MODULE.prepare_frozen_review(draft, "2026-10-21T11:32:00-03:00")
            canonical_write(fixture.review, frozen)
            with self.assertRaisesRegex(MODULE.IntegrationError, "não está vinculada"):
                fixture.build()

    def test_review_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory), [destination_hypothesis()])
            fixture.freeze_review([])
            payload = json.loads(fixture.review.read_text())
            payload["reviewer_code"] = "REV-02"
            canonical_write(fixture.review, payload)
            with self.assertRaisesRegex(MODULE.IntegrationError, "Hash da revisão"):
                fixture.build()

    def test_review_runtime_matches_reason_length_and_chronology_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory), [destination_hypothesis()])
            base_entry = {
                "source_hypothesis_id": "H001",
                "decision": "EXCLUIR",
                "reviewed_at": "2026-10-21T11:31:30-03:00",
                "reason": "x" * 301,
            }
            with self.assertRaises(MODULE.IntegrationError):
                MODULE.prepare_frozen_review(
                    fixture.review_draft([base_entry]), "2026-10-21T11:32:00-03:00"
                )
            base_entry["reason"] = "Revisão documental"
            base_entry["reviewed_at"] = "2026-10-21T11:30:59-03:00"
            with self.assertRaisesRegex(MODULE.IntegrationError, "anteceder created_at"):
                MODULE.prepare_frozen_review(
                    fixture.review_draft([base_entry]), "2026-10-21T11:32:00-03:00"
                )

    def test_deterministic_bytes_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            first_result, first_report = fixture.build(review=False)
            second_result, second_report = fixture.build(review=False)
            self.assertEqual(MODULE.ranker.canonical_json_bytes(first_result), MODULE.ranker.canonical_json_bytes(second_result))
            self.assertEqual(MODULE.ranker.canonical_json_bytes(first_report), MODULE.ranker.canonical_json_bytes(second_report))

    def test_sidecar_cannot_supply_coordinates_or_evidence_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory), [destination_hypothesis()])
            entry = {
                "source_hypothesis_id": "H001",
                "decision": "INCLUIR",
                "reviewed_at": "2026-10-21T11:31:30-03:00",
                "family": "DESTINO",
                "hypothesis_type": "DESTINO_DECLARADO",
                "location_uncertainty_m": 25.0,
                "spatial_source": "Registro",
                "latitude": 9.0,
            }
            with self.assertRaises(MODULE.IntegrationError):
                MODULE.prepare_frozen_review(fixture.review_draft([entry]), "2026-10-21T11:32:00-03:00")

    def test_hidden_ground_truth_alias_in_geojson_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            geo = json.loads(fixture.polygons.read_text())
            geo["features"][0]["properties"]["victim_latitude"] = 0.1
            canonical_write(fixture.polygons, geo)
            fixture.rebuild_manifest()
            with self.assertRaisesRegex(MODULE.IntegrationError, "referência verdadeira"):
                fixture.build(review=False)

    def test_json_string_false_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            geo = json.loads(fixture.polygons.read_text())
            geo["ground_truth_used"] = "false"
            canonical_write(fixture.polygons, geo)
            fixture.rebuild_manifest()
            with self.assertRaisesRegex(MODULE.IntegrationError, "deve ser false"):
                fixture.build(review=False)

    def test_composite_ground_truth_alias_is_rejected_in_all_sources(self) -> None:
        for source in ("v2", "manifest", "geojson", "buffers", "csv"):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as directory:
                fixture = Fixture(Path(directory))
                if source == "v2":
                    payload = json.loads(fixture.profile.read_text())
                    payload["distance_to_ground_truth_m"] = 1.0
                    payload.pop("compiled_sha256")
                    payload["compiled_sha256"] = MODULE.ranker.canonical_sha256(payload)
                    canonical_write(fixture.profile, payload)
                elif source == "manifest":
                    payload = json.loads(fixture.manifest.read_text())
                    payload["distance_to_ground_truth_m"] = 1.0
                    canonical_write(fixture.manifest, payload)
                elif source == "geojson":
                    payload = json.loads(fixture.polygons.read_text())
                    payload["features"][0]["properties"]["distance_to_ground_truth_m"] = 1.0
                    canonical_write(fixture.polygons, payload)
                    fixture.rebuild_manifest()
                elif source == "buffers":
                    payload = json.loads(fixture.buffers.read_text())
                    payload["results"][0]["distance_to_ground_truth_m"] = 1.0
                    canonical_write(fixture.buffers, payload)
                    fixture.rebuild_manifest()
                else:
                    with fixture.ranking.open("r", encoding="utf-8", newline="") as stream:
                        reader = csv.DictReader(stream)
                        rows = list(reader)
                        headers = list(reader.fieldnames or []) + ["distance_to_ground_truth_m"]
                    rows[0]["distance_to_ground_truth_m"] = "1.0"
                    with fixture.ranking.open("w", encoding="utf-8", newline="") as stream:
                        writer = csv.DictWriter(stream, fieldnames=headers)
                        writer.writeheader()
                        writer.writerows(rows)
                    fixture.rebuild_manifest()
                with self.assertRaisesRegex(MODULE.IntegrationError, "referência verdadeira"):
                    fixture.build(review=False)

    def test_v2_declared_firewall_and_qualitative_guards_are_enforced(self) -> None:
        mutations = (
            ("firewall_manifest", "status", "FAIL"),
            ("scope_guards", "ground_truth_firewall_passed", False),
            (None, "mode", "QUANTITATIVO"),
            (None, "input_sha256", "invalid"),
        )
        for container, key, value in mutations:
            with self.subTest(container=container, key=key), tempfile.TemporaryDirectory() as directory:
                fixture = Fixture(Path(directory))
                payload = json.loads(fixture.profile.read_text())
                if container is None:
                    payload[key] = value
                else:
                    payload[container][key] = value
                payload.pop("compiled_sha256")
                payload["compiled_sha256"] = MODULE.ranker.canonical_sha256(payload)
                canonical_write(fixture.profile, payload)
                with self.assertRaises(MODULE.IntegrationError):
                    fixture.build(review=False)

    def test_ground_truth_control_values_are_checked_in_unselected_records(self) -> None:
        for source in ("geojson", "buffers", "csv"):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as directory:
                fixture = Fixture(Path(directory))
                if source == "geojson":
                    payload = json.loads(fixture.polygons.read_text())
                    other = copy.deepcopy(payload["features"][0])
                    other["id"] = "OTHER-SEC"
                    other["properties"]["scenario_id"] = "OTHER-001"
                    other["properties"]["ground_truth_used"] = True
                    payload["features"].append(other)
                    canonical_write(fixture.polygons, payload)
                elif source == "buffers":
                    payload = json.loads(fixture.buffers.read_text())
                    other = copy.deepcopy(payload["results"][0])
                    other["scenario_id"] = "OTHER-001"
                    other["candidate_id"] = "OTHER-001-C1"
                    other["ground_truth_used"] = True
                    payload["results"].append(other)
                    canonical_write(fixture.buffers, payload)
                else:
                    with fixture.ranking.open("r", encoding="utf-8", newline="") as stream:
                        reader = csv.DictReader(stream)
                        rows = list(reader)
                        headers = list(reader.fieldnames or [])
                    other = dict(rows[0])
                    other["scenario_id"] = "OTHER-001"
                    other["candidate_id"] = "OTHER-001-C1"
                    other["ground_truth_used"] = "true"
                    rows.append(other)
                    with fixture.ranking.open("w", encoding="utf-8", newline="") as stream:
                        writer = csv.DictWriter(stream, fieldnames=headers)
                        writer.writeheader()
                        writer.writerows(rows)
                fixture.rebuild_manifest()
                with self.assertRaisesRegex(MODULE.IntegrationError, "deve ser false"):
                    fixture.build(review=False)


if __name__ == "__main__":
    unittest.main()
