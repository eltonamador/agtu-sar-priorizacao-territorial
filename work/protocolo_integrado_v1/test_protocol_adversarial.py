from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import integrated_protocol as module
from test_integrated_protocol import draft_case, draft_event, valid_loc_result


class ProtocolAdversarialTests(unittest.TestCase):
    """Regressões para falhas capazes de produzir uma conclusão operacional indevida."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = json.loads(module.DEFAULT_RULES_PATH.read_text(encoding="utf-8"))

    @staticmethod
    def freeze_case(value: dict) -> dict:
        return module.prepare_frozen_case(value, "2026-10-21T10:00:00-03:00")

    def compile_case(self, value: dict, rules: dict | None = None) -> dict:
        return module.compile_case(self.freeze_case(value), rules or self.rules)

    def assert_rejected_or_not_apt(self, value: dict) -> None:
        try:
            output = self.compile_case(value)
        except module.InputValidationError:
            return
        statuses = {
            row["status"] for row in output["detectability"]["per_sector_modality"]
        }
        self.assertNotIn("APTO_A_PLANEJAMENTO", statuses)

    def materialize_case_artifacts(
        self, value: dict, root: Path, events: list[dict] | None = None
    ) -> dict[str, str]:
        artifact_map: dict[str, str] = {}
        for key in value["source_artifacts"]:
            content = f"case::{key}".encode("utf-8")
            path = root / f"{key}.bin"
            path.write_bytes(content)
            value["source_artifacts"][key] = hashlib.sha256(content).hexdigest()
            artifact_map[key] = path.name
        image_content = b"\xff\xd8\xff\xe0JFIF\x00verified-context-image\xff\xd9"
        image_path = root / "IMG-01.jpg"
        image_path.write_bytes(image_content)
        value["visual_evidence"][0]["file_sha256"] = hashlib.sha256(image_content).hexdigest()
        artifact_map["visual:IMG-01"] = image_path.name
        for event in events or []:
            event_hash = event["freeze_metadata"]["payload_sha256"]
            event_path = root / f"{event['event_id']}.json"
            event_path.write_bytes(module.canonical_json_bytes(event))
            artifact_map[f"event:{event_hash}"] = event_path.name
        return artifact_map

    def test_urgency_is_order_independent_with_shared_evidence(self) -> None:
        value = draft_case()
        absent = value["urgency_observations"][0]
        absent["availability"] = "AUSENTE"
        absent["operational_significance"] = "CONTEXTUAL"
        present = copy.deepcopy(absent)
        present["observation_id"] = "URG-CONFLICT-PRESENT"
        present["availability"] = "PRESENTE"
        present["operational_significance"] = "DIRETA_A_VIDA"
        value["urgency_observations"].append(present)

        reversed_value = copy.deepcopy(value)
        reversed_value["urgency_observations"].reverse()
        first = self.compile_case(value)["urgency"]
        second = self.compile_case(reversed_value)["urgency"]

        self.assertEqual(first["status"], "INDETERMINADA")
        self.assertEqual(first["status"], second["status"])
        self.assertEqual(first["conflict_observation_ids"], second["conflict_observation_ids"])

    def test_present_and_absent_in_same_domain_force_abstention(self) -> None:
        value = draft_case()
        present = copy.deepcopy(value["urgency_observations"][0])
        present["observation_id"] = "URG-TEMPO-PRESENT"
        present["evidence"]["evidence_id"] = "E-URG-TEMPO-PRESENT"
        present["availability"] = "PRESENTE"
        present["operational_significance"] = "DIRETA_A_VIDA"
        value["urgency_observations"].append(present)

        urgency = self.compile_case(value)["urgency"]
        self.assertEqual(urgency["status"], "INDETERMINADA")
        self.assertIn("TEMPO", urgency["conflict_domains"])

    def test_empty_critical_domain_catalog_is_rejected(self) -> None:
        rules = copy.deepcopy(self.rules)
        rules["critical_domains"] = []
        with self.assertRaises(module.InputValidationError):
            self.compile_case(draft_case(), rules)

    def test_rule_precedence_drift_is_rejected(self) -> None:
        rules = copy.deepcopy(self.rules)
        rules["rules"][0]["precedence"] = 99
        with self.assertRaises(module.InputValidationError):
            self.compile_case(draft_case(), rules)

    def test_nan_in_free_value_is_rejected(self) -> None:
        value = draft_case()
        value["profile_facts"][0]["value"] = float("nan")
        with self.assertRaises(module.InputValidationError):
            module.validate_case(value)

    def test_future_planning_point_is_rejected(self) -> None:
        value = draft_case()
        value["planning_point"]["position_observed_at"] = "2026-10-21T09:30:00-03:00"
        with self.assertRaises(module.InputValidationError):
            module.validate_case(value)

    def test_unauthorized_planning_point_is_rejected(self) -> None:
        value = draft_case()
        value["planning_point"]["evidence"]["authorized_for_model"] = False
        with self.assertRaises(module.InputValidationError):
            module.validate_case(value)

    def test_unauthorized_visual_never_yields_apt(self) -> None:
        value = draft_case()
        value["visual_evidence"][0]["authorized_for_context"] = False
        self.assert_rejected_or_not_apt(value)

    def test_future_visual_never_yields_apt(self) -> None:
        value = draft_case()
        value["visual_evidence"][0]["capture_at"] = "2026-10-21T09:30:00-03:00"
        self.assert_rejected_or_not_apt(value)

    def test_unannotated_visual_never_yields_apt(self) -> None:
        value = draft_case()
        value["visual_evidence"][0]["annotations"] = []
        self.assert_rejected_or_not_apt(value)

    def test_single_terrain_annotation_cannot_support_all_det_dimensions(self) -> None:
        value = draft_case()
        value["visual_evidence"][0]["annotations"] = [
            {"domain": "TERRENO", "category": "PLANO", "evidence_nature": "OBSERVADO"}
        ]
        with self.assertRaisesRegex(
            module.InputValidationError, "nenhuma anotação visual compatível"
        ):
            module.validate_case(value)

    def test_adverse_visual_annotations_cannot_support_favorable_det(self) -> None:
        value = draft_case()
        adverse_by_domain = {
            "OBSTRUCAO_VISUAL": "OBSTRUCAO_TOTAL",
            "VIAS_ACESSOS": "SEM_ACESSO",
            "RECURSO_OPERACIONAL": "RECURSO_INCOMPATIVEL",
            "TERRENO": "TERRENO_INTRANSITAVEL",
            "QUALIDADE_IMAGEM": "IMAGEM_INUTILIZAVEL",
        }
        for annotation in value["visual_evidence"][0]["annotations"]:
            annotation["category"] = adverse_by_domain[annotation["domain"]]
        module.validate_case(value)
        result = module.assess_detectability(
            value, {"visual:IMG-01"}, {"SETOR-N"}
        )["per_sector_modality"][0]
        self.assertEqual(result["status"], "REVISAR")
        self.assertTrue(result["unsupported_visual_claims"])

    def test_environment_evidence_cannot_support_unrelated_det_dimension(self) -> None:
        value = draft_case()
        dimension = next(
            item
            for item in value["detectability_assessments"][0]["dimensions"]
            if item["dimension"] == "VISIBILIDADE"
        )
        dimension["source_type"] = "CAMPO"
        dimension["evidence_id"] = "E-ENV-01"  # E-ENV-01 descreve CLIMA, não visibilidade.
        with self.assertRaisesRegex(
            module.InputValidationError, "domínio da evidência incompatível"
        ):
            module.validate_case(value)

    def test_public_layer_cannot_claim_favorable_observed(self) -> None:
        value = draft_case()
        public_evidence = value["search_context"]["environment_observations"][0]["evidence"]
        public_evidence["source_type"] = "CAMADA_PUBLICA"
        dimension = value["detectability_assessments"][0]["dimensions"][0]
        dimension["source_type"] = "CAMADA_PUBLICA"
        dimension["evidence_id"] = public_evidence["evidence_id"]
        dimension["category"] = "FAVORAVEL_OBSERVADO"
        self.assert_rejected_or_not_apt(value)

    def test_unauthorized_field_evidence_never_yields_apt(self) -> None:
        value = draft_case()
        field_evidence = value["search_context"]["environment_observations"][0]["evidence"]
        field_evidence["authorized_for_model"] = False
        for dimension in value["detectability_assessments"][0]["dimensions"]:
            dimension["source_type"] = "CAMPO"
            dimension["evidence_id"] = field_evidence["evidence_id"]
        self.assert_rejected_or_not_apt(value)

    def test_post_assessment_detectability_never_yields_apt(self) -> None:
        value = draft_case()
        value["detectability_assessments"][0]["assessed_at"] = (
            "2026-10-21T09:30:00-03:00"
        )
        self.assert_rejected_or_not_apt(value)

    def test_loc_result_with_ground_truth_payload_is_rejected(self) -> None:
        value = draft_case()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_map = self.materialize_case_artifacts(value, root)
            loc_result = valid_loc_result(value)
            loc_result["ground_truth_latitude"] = 0.002
            loc_path = root / "loc_result_tainted.json"
            loc_bytes = module.canonical_json_bytes(loc_result)
            loc_path.write_bytes(loc_bytes)
            value["source_artifacts"]["loc_result_sha256"] = hashlib.sha256(loc_bytes).hexdigest()
            artifact_map["loc_result_sha256"] = loc_path.name
            with self.assertRaises(module.GroundTruthFirewallError):
                module.compile_case(
                    self.freeze_case(value), self.rules, artifact_map, root
                )

    def test_incomplete_declared_loc_contract_is_rejected(self) -> None:
        value = draft_case()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_map = self.materialize_case_artifacts(value, root)
            loc_result = valid_loc_result(value)
            del loc_result["profile_runs"]
            loc_path = root / "loc_result_incomplete.json"
            loc_bytes = module.canonical_json_bytes(loc_result)
            loc_path.write_bytes(loc_bytes)
            value["source_artifacts"]["loc_result_sha256"] = hashlib.sha256(loc_bytes).hexdigest()
            artifact_map["loc_result_sha256"] = loc_path.name
            with self.assertRaises(module.InputValidationError):
                module.compile_case(
                    self.freeze_case(value), self.rules, artifact_map, root
                )

    def test_loc_contract_rejects_unauthorized_engine_and_extra_payload(self) -> None:
        variants = []
        unauthorized_engine = valid_loc_result()
        unauthorized_engine["profile_engine_id"] = "MOTOR-NAO-AUTORIZADO-v1"
        variants.append(unauthorized_engine)
        unauthorized_config = valid_loc_result()
        unauthorized_config["profile_engine_config_file_sha256"] = "0" * 64
        variants.append(unauthorized_config)
        extra_payload = valid_loc_result()
        extra_payload["answer"] = {"latitude": 0.0, "longitude": -51.0}
        variants.append(extra_payload)

        for loc_result in variants:
            with self.subTest(loc_result=loc_result):
                value = draft_case()
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    artifact_map = self.materialize_case_artifacts(value, root)
                    loc_path = root / "loc_result_invalid.json"
                    loc_bytes = module.canonical_json_bytes(loc_result)
                    loc_path.write_bytes(loc_bytes)
                    value["source_artifacts"]["loc_result_sha256"] = hashlib.sha256(loc_bytes).hexdigest()
                    artifact_map["loc_result_sha256"] = loc_path.name
                    with self.assertRaises(module.InputValidationError):
                        module.compile_case(
                            self.freeze_case(value), self.rules, artifact_map, root
                        )

    def test_loc_result_from_previous_case_revision_is_rejected(self) -> None:
        value = draft_case()
        value["case_revision"] = 2
        value["parent_payload_sha256"] = "d" * 64
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_map = self.materialize_case_artifacts(value, root)
            stale_case = copy.deepcopy(value)
            stale_case["case_revision"] = 1
            stale_case["parent_payload_sha256"] = None
            loc_result = valid_loc_result(stale_case)
            loc_path = root / "loc_result_stale.json"
            loc_bytes = module.canonical_json_bytes(loc_result)
            loc_path.write_bytes(loc_bytes)
            value["source_artifacts"]["loc_result_sha256"] = hashlib.sha256(loc_bytes).hexdigest()
            artifact_map["loc_result_sha256"] = loc_path.name
            with self.assertRaises(module.InputValidationError):
                module.compile_case(
                    self.freeze_case(value), self.rules, artifact_map, root
                )

    def test_det_sector_must_exist_in_validated_loc_result(self) -> None:
        value = draft_case()
        value["detectability_assessments"][0]["sector_id"] = "SETOR-X"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_map = self.materialize_case_artifacts(value, root)
            loc_result = valid_loc_result(value)
            loc_path = root / "loc_result_valid.json"
            loc_bytes = module.canonical_json_bytes(loc_result)
            loc_path.write_bytes(loc_bytes)
            value["source_artifacts"]["loc_result_sha256"] = hashlib.sha256(loc_bytes).hexdigest()
            artifact_map["loc_result_sha256"] = loc_path.name
            output = module.compile_case(
                self.freeze_case(value), self.rules, artifact_map, root
            )
        det = output["detectability"]["per_sector_modality"][0]
        self.assertEqual(det["status"], "REVISAR")
        self.assertEqual(det["loc_sector_link"], "SECTOR_NOT_IN_VALIDATED_LOC_RESULT")

    def test_zero_coverage_is_never_eligible_negative_evidence(self) -> None:
        value = draft_event()
        value["coverage_fraction"] = 0.0
        try:
            frozen = module.prepare_frozen_event(
                value, "2026-10-21T11:20:00-03:00"
            )
            output = module.compile_event(frozen)
        except module.InputValidationError:
            return
        self.assertFalse(output["search_record_complete"])
        self.assertFalse(output["negative_evidence_eligible_for_human_review"])

    def test_zero_duration_search_is_never_complete(self) -> None:
        value = draft_event()
        value["ended_at"] = value["started_at"]
        try:
            frozen = module.prepare_frozen_event(
                value, "2026-10-21T11:20:00-03:00"
            )
            output = module.compile_event(frozen)
        except module.InputValidationError:
            return
        self.assertFalse(output["search_record_complete"])
        self.assertFalse(output["negative_evidence_eligible_for_human_review"])

    def test_arbitrary_bytes_do_not_make_negative_search_documentarily_complete(self) -> None:
        value = draft_event()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_map: dict[str, str] = {}
            for binding, field in (
                ("coverage_geometry", "coverage_geometry_sha256"),
                ("track", "track_sha256"),
                ("prior_run", "prior_run_sha256"),
            ):
                content = b"x"
                path = root / f"{binding}.bin"
                path.write_bytes(content)
                value[field] = hashlib.sha256(content).hexdigest()
                artifact_map[binding] = path.name
            frozen = module.prepare_frozen_event(
                value, "2026-10-21T11:20:00-03:00"
            )
            output = module.compile_event(frozen, artifact_map, root)
        self.assertFalse(output["search_artifacts_semantically_validated"])
        self.assertFalse(output["search_record_complete"])
        self.assertFalse(output["negative_evidence_eligible_for_human_review"])

    def test_malformed_geospatial_artifacts_are_not_semantically_validated(self) -> None:
        event = draft_event()
        malformed = {
            "coverage_geometry": {"type": "Polygon", "coordinates": ["not-coordinates"]},
            "track": {"type": "LineString", "coordinates": ["x"]},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for binding, document in malformed.items():
                path = root / f"{binding}.json"
                path.write_bytes(module.canonical_json_bytes(document))
                self.assertEqual(
                    module._inspect_event_operational_artifact(binding, path, event),
                    "BYTES_VERIFIED_CONTENT_UNVALIDATED",
                )
            invalid_gpx = root / "track.gpx"
            invalid_gpx.write_text(
                '<gpx version="1.1"><trk><trkseg><trkpt/><trkpt lat="999" lon="0"/></trkseg></trk></gpx>',
                encoding="utf-8",
            )
            self.assertEqual(
                module._inspect_event_operational_artifact("track", invalid_gpx, event),
                "BYTES_VERIFIED_CONTENT_UNVALIDATED",
            )

            zero_area = root / "zero_area.json"
            zero_area.write_bytes(module.canonical_json_bytes({
                "type": "Polygon",
                "coordinates": [[[10.0, 10.0], [10.0, 10.0], [10.0, 10.0], [10.0, 10.0]]],
            }))
            zero_length = root / "zero_length.json"
            zero_length.write_bytes(module.canonical_json_bytes({
                "type": "LineString",
                "coordinates": [[10.0, 10.0], [10.0, 10.0]],
            }))
            self.assertEqual(
                module._inspect_event_operational_artifact("coverage_geometry", zero_area, event),
                "BYTES_VERIFIED_CONTENT_UNVALIDATED",
            )
            self.assertEqual(
                module._inspect_event_operational_artifact("track", zero_length, event),
                "BYTES_VERIFIED_CONTENT_UNVALIDATED",
            )

    def test_track_must_intersect_declared_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coverage = root / "coverage.json"
            track = root / "track.json"
            coverage.write_bytes(module.canonical_json_bytes({
                "type": "Polygon",
                "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]],
            }))
            track.write_bytes(module.canonical_json_bytes({
                "type": "LineString",
                "coordinates": [[10.0, 10.0], [11.0, 11.0]],
            }))
            self.assertFalse(module._track_intersects_coverage(coverage, track))

    def test_geospatial_artifact_with_ground_truth_marker_is_blocked(self) -> None:
        event = draft_event()
        document = {
            "type": "Feature",
            "properties": {"ground_truth_latitude": 0.01},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]],
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coverage.json"
            path.write_bytes(module.canonical_json_bytes(document))
            with self.assertRaises(module.GroundTruthFirewallError):
                module._inspect_event_operational_artifact(
                    "coverage_geometry", path, event
                )

    def test_ground_truth_scope_cannot_hide_reserved_coordinates(self) -> None:
        with self.assertRaises(module.GroundTruthFirewallError):
            module.enforce_ground_truth_firewall({
                "ground_truth_scope": {
                    "latitude": 0.0024809355844815323,
                    "longitude": -51.07092698392779,
                }
            })

    def test_gpx_ground_truth_marker_is_blocked(self) -> None:
        event = draft_event()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "track.gpx"
            path.write_text(
                '<gpx version="1.1"><desc>ground_truth: reservado</desc>'
                '<trk><trkseg><trkpt lat="0" lon="0"/>'
                '<trkpt lat="0.1" lon="0.1"/></trkseg></trk></gpx>',
                encoding="utf-8",
            )
            with self.assertRaises(module.GroundTruthFirewallError):
                module._inspect_event_operational_artifact("track", path, event)

    def test_disconnected_gpx_segments_are_not_joined_artificially(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coverage = root / "coverage.json"
            track = root / "track.gpx"
            coverage.write_bytes(module.canonical_json_bytes({
                "type": "Polygon",
                "coordinates": [[[4.5, -0.5], [5.5, -0.5], [5.5, 0.5], [4.5, -0.5]]],
            }))
            track.write_text(
                '<gpx version="1.1"><trk>'
                '<trkseg><trkpt lat="0" lon="0"/><trkpt lat="0" lon="0.1"/></trkseg>'
                '<trkseg><trkpt lat="0" lon="10"/><trkpt lat="0" lon="10.1"/></trkseg>'
                '</trk></gpx>',
                encoding="utf-8",
            )
            self.assertFalse(module._track_intersects_coverage(coverage, track))

    def test_track_inside_polygon_hole_is_not_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coverage = root / "coverage.json"
            track = root / "track.json"
            coverage.write_bytes(module.canonical_json_bytes({
                "type": "Polygon",
                "coordinates": [
                    [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]],
                    [[4.0, 4.0], [6.0, 4.0], [6.0, 6.0], [4.0, 6.0], [4.0, 4.0]],
                ],
            }))
            track.write_bytes(module.canonical_json_bytes({
                "type": "LineString",
                "coordinates": [[4.5, 5.0], [5.5, 5.0]],
            }))
            self.assertFalse(module._track_intersects_coverage(coverage, track))

    def test_tiny_jpeg_magic_bytes_are_not_operational_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tiny.jpg"
            path.write_bytes(b"\xff\xd8\xff\xd9")
            with self.assertRaises(module.InputValidationError):
                module._validate_visual_media_signature(path, "IMAGE_JPEG")

    def test_sequence_two_rejects_unverified_predecessor_hash(self) -> None:
        value = draft_event()
        value.setdefault("previous_event_sha256", None)
        value["event_id"] = "EVT-002"
        value["event_sequence"] = 2
        value["previous_event_sha256"] = "d" * 64
        with self.assertRaises(module.InputValidationError):
            module.prepare_frozen_event(
                value, "2026-10-21T11:20:00-03:00"
            )

    def test_new_point_chain_preserves_own_previous_and_origin_hashes(self) -> None:
        source = draft_event()
        source.setdefault("previous_event_sha256", None)
        source["event_type"] = "VESTIGIO_ENCONTRADO"
        source["result"] = "POSITIVO"
        source["clue_coordinate"] = {"latitude": 0.01, "longitude": -51.0}
        frozen_source = module.prepare_frozen_event(
            source, "2026-10-21T11:20:00-03:00"
        )
        source_hash = frozen_source["freeze_metadata"]["payload_sha256"]

        next_event = draft_event()
        next_event.setdefault("previous_event_sha256", None)
        next_event["event_id"] = "EVT-002"
        next_event["event_sequence"] = 2
        next_event["event_type"] = "NOVO_PONTO_CONHECIDO"
        next_event["result"] = "POSITIVO"
        next_event["clue_coordinate"] = copy.deepcopy(source["clue_coordinate"])
        next_event["started_at"] = "2026-10-21T11:21:00-03:00"
        next_event["ended_at"] = "2026-10-21T11:22:00-03:00"
        next_event["recorded_at"] = "2026-10-21T11:23:00-03:00"
        next_event["coverage_geometry_sha256"] = None
        next_event["track_sha256"] = None
        next_event["sector_ids"] = []
        next_event["modality"] = None
        next_event["effort_minutes"] = None
        next_event["coverage_status"] = "NAO_DISPONIVEL"
        next_event["coverage_method_id"] = None
        next_event["coverage_fraction"] = None
        next_event["visibility_recorded"] = False
        next_event["visibility_class"] = "NAO_DISPONIVEL"
        next_event["limitations_recorded"] = False
        next_event["limitations"] = []
        next_event["prior_run_sha256"] = None
        next_event["previous_event_sha256"] = source_hash
        next_event["source_event_sha256"] = source_hash
        frozen_next = module.prepare_frozen_event(
            next_event,
            "2026-10-21T11:30:00-03:00",
            previous_event=frozen_source,
            source_event=frozen_source,
        )
        output = module.compile_event(frozen_next)

        self.assertEqual(
            output["event_payload_sha256"],
            frozen_next["freeze_metadata"]["payload_sha256"],
        )
        self.assertEqual(output["previous_event_sha256"], source_hash)
        self.assertEqual(output["origin_event_sha256"], source_hash)
        self.assertNotEqual(output["event_payload_sha256"], output["origin_event_sha256"])
        self.assertNotEqual(output["next_action"], "REPROCESSAR_COM_NOVO_PONTO")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "EVT-001.json"
            source_path.write_bytes(module.canonical_json_bytes(frozen_source))
            verified = module.compile_event(
                frozen_next,
                {
                    "previous_event": source_path.name,
                    "source_event": source_path.name,
                },
                root,
            )
        self.assertEqual(verified["next_action"], "REPROCESSAR_COM_NOVO_PONTO")
        self.assertEqual(verified["origin_event_sha256"], source_hash)

    def test_loc_logical_hash_is_invariant_to_det(self) -> None:
        base = self.compile_case(draft_case())
        altered = draft_case()
        altered["detectability_assessments"][0]["dimensions"][0][
            "category"
        ] = "RESTRITO_OBSERVADO"
        changed = self.compile_case(altered)
        self.assertEqual(
            base["location"]["logical_sha256"],
            changed["location"]["logical_sha256"],
        )

    def test_null_search_event_hash_is_rejected(self) -> None:
        value = draft_case()
        value["search_event_hashes"] = [None]
        with self.assertRaises(module.InputValidationError):
            module.validate_case(value)

    def test_verified_negative_event_cannot_disable_loc(self) -> None:
        negative = module.prepare_frozen_event(
            draft_event(), "2026-10-21T11:20:00-03:00"
        )
        negative_hash = negative["freeze_metadata"]["payload_sha256"]
        value = draft_case()
        value["person_location_status"] = "CONHECIDA_OPERACIONALMENTE"
        value["search_event_hashes"] = [negative_hash]
        value["search_context"]["assessment_at"] = "2026-10-21T12:00:00-03:00"
        value["search_context"]["elapsed_minutes"] = 240.0
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_map = self.materialize_case_artifacts(value, root, [negative])
            output = module.compile_case(
                module.prepare_frozen_case(value, "2026-10-21T12:30:00-03:00"),
                self.rules,
                artifact_map,
                root,
            )
        self.assertEqual(
            output["location"]["status"],
            "LOCALIZACAO_CONHECIDA_DECLARADA_NAO_VERIFICADA",
        )
        self.assertFalse(output["location"]["known_location_event_verified"])

    def test_verified_positive_chain_can_switch_to_access_and_rescue(self) -> None:
        source = draft_event()
        source["event_type"] = "VESTIGIO_ENCONTRADO"
        source["result"] = "POSITIVO"
        source["clue_coordinate"] = {"latitude": 0.01, "longitude": -51.0}
        frozen_source = module.prepare_frozen_event(
            source, "2026-10-21T11:20:00-03:00"
        )
        source_hash = frozen_source["freeze_metadata"]["payload_sha256"]
        known = draft_event()
        known.update({
            "event_id": "EVT-002",
            "event_sequence": 2,
            "event_type": "NOVO_PONTO_CONHECIDO",
            "started_at": "2026-10-21T11:21:00-03:00",
            "ended_at": "2026-10-21T11:22:00-03:00",
            "recorded_at": "2026-10-21T11:23:00-03:00",
            "coverage_geometry_sha256": None,
            "track_sha256": None,
            "sector_ids": [],
            "modality": None,
            "effort_minutes": None,
            "coverage_status": "NAO_DISPONIVEL",
            "coverage_method_id": None,
            "coverage_fraction": None,
            "visibility_recorded": False,
            "visibility_class": "NAO_DISPONIVEL",
            "limitations_recorded": False,
            "prior_run_sha256": None,
            "result": "POSITIVO",
            "clue_coordinate": copy.deepcopy(source["clue_coordinate"]),
            "previous_event_sha256": source_hash,
            "source_event_sha256": source_hash,
        })
        frozen_known = module.prepare_frozen_event(
            known,
            "2026-10-21T11:30:00-03:00",
            previous_event=frozen_source,
            source_event=frozen_source,
        )
        value = draft_case()
        value["person_location_status"] = "CONHECIDA_OPERACIONALMENTE"
        value["planning_point"].update({
            "point_role": "ULTIMO_PONTO_CONHECIDO",
            "point_semantics": "REGISTRO_INDIRETO",
            "coordinate_source": "REGISTRO_OPERACIONAL",
            "latitude": 0.01,
            "longitude": -51.0,
            "position_observed_at": "2026-10-21T11:00:00-03:00",
        })
        value["planning_point"]["evidence"].update({
            "source_type": "DOCUMENTO_OPERACIONAL",
            "source_code": "EVT-002",
            "nature": "CONFIRMADO",
            "observed_at": "2026-10-21T11:00:00-03:00",
        })
        value["search_context"]["assessment_at"] = "2026-10-21T12:00:00-03:00"
        value["search_context"]["elapsed_minutes"] = 240.0
        value["search_event_hashes"] = [
            source_hash,
            frozen_known["freeze_metadata"]["payload_sha256"],
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_map = self.materialize_case_artifacts(
                value, root, [frozen_source, frozen_known]
            )
            output = module.compile_case(
                module.prepare_frozen_case(value, "2026-10-21T12:30:00-03:00"),
                self.rules,
                artifact_map,
                root,
            )
            inconsistent = copy.deepcopy(value)
            inconsistent["person_location_status"] = "DESCONHECIDA"
            with self.assertRaises(module.InputValidationError):
                module.compile_case(
                    module.prepare_frozen_case(
                        inconsistent, "2026-10-21T12:30:00-03:00"
                    ),
                    self.rules,
                    artifact_map,
                    root,
                )
        self.assertEqual(output["location"]["status"], "NAO_APLICAVEL_ACESSO_E_RESGATE")
        self.assertTrue(output["location"]["known_location_event_verified"])

    def test_broken_ancestral_event_chain_cannot_disable_loc(self) -> None:
        source = draft_event()
        source["event_type"] = "VESTIGIO_ENCONTRADO"
        source["result"] = "POSITIVO"
        source["clue_coordinate"] = {"latitude": 0.01, "longitude": -51.0}
        frozen_source = module.prepare_frozen_event(
            source, "2026-10-21T11:20:00-03:00"
        )
        source_hash = frozen_source["freeze_metadata"]["payload_sha256"]

        broken_middle = draft_event()
        broken_middle.update({
            "event_id": "EVT-002",
            "event_sequence": 2,
            "started_at": "2026-10-21T11:21:00-03:00",
            "ended_at": "2026-10-21T11:25:00-03:00",
            "recorded_at": "2026-10-21T11:26:00-03:00",
            "effort_minutes": 4.0,
            "previous_event_sha256": "f" * 64,
        })
        broken_middle["record_status"] = "CONGELADO"
        broken_middle["freeze_metadata"] = {
            "frozen_at": "2026-10-21T11:27:00-03:00",
            "projection_id": module.EVENT_FREEZE_PROJECTION_ID,
            "payload_sha256": "0" * 64,
        }
        broken_middle["freeze_metadata"]["payload_sha256"] = (
            module.calculate_event_freeze_sha256(broken_middle)
        )
        module.validate_event(broken_middle)
        middle_hash = broken_middle["freeze_metadata"]["payload_sha256"]

        known = draft_event()
        known.update({
            "event_id": "EVT-003",
            "event_sequence": 3,
            "event_type": "NOVO_PONTO_CONHECIDO",
            "started_at": "2026-10-21T11:31:00-03:00",
            "ended_at": "2026-10-21T11:32:00-03:00",
            "recorded_at": "2026-10-21T11:33:00-03:00",
            "coverage_geometry_sha256": None,
            "track_sha256": None,
            "sector_ids": [],
            "modality": None,
            "effort_minutes": None,
            "coverage_status": "NAO_DISPONIVEL",
            "coverage_method_id": None,
            "coverage_fraction": None,
            "visibility_recorded": False,
            "visibility_class": "NAO_DISPONIVEL",
            "limitations_recorded": False,
            "limitations": [],
            "prior_run_sha256": None,
            "result": "POSITIVO",
            "clue_coordinate": copy.deepcopy(source["clue_coordinate"]),
            "previous_event_sha256": middle_hash,
            "source_event_sha256": source_hash,
        })
        frozen_known = module.prepare_frozen_event(
            known,
            "2026-10-21T11:40:00-03:00",
            previous_event=broken_middle,
            source_event=frozen_source,
        )

        value = draft_case()
        value["person_location_status"] = "CONHECIDA_OPERACIONALMENTE"
        value["planning_point"].update({
            "point_role": "ULTIMO_PONTO_CONHECIDO",
            "point_semantics": "REGISTRO_INDIRETO",
            "coordinate_source": "REGISTRO_OPERACIONAL",
            "latitude": 0.01,
            "longitude": -51.0,
            "position_observed_at": "2026-10-21T11:00:00-03:00",
        })
        value["planning_point"]["evidence"].update({
            "source_type": "DOCUMENTO_OPERACIONAL",
            "source_code": "EVT-003",
            "nature": "CONFIRMADO",
            "observed_at": "2026-10-21T11:00:00-03:00",
        })
        value["search_context"]["assessment_at"] = "2026-10-21T12:00:00-03:00"
        value["search_context"]["elapsed_minutes"] = 240.0
        value["search_event_hashes"] = [
            source_hash,
            middle_hash,
            frozen_known["freeze_metadata"]["payload_sha256"],
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_map = self.materialize_case_artifacts(
                value, root, [frozen_source, broken_middle, frozen_known]
            )
            output = module.compile_case(
                module.prepare_frozen_case(value, "2026-10-21T12:30:00-03:00"),
                self.rules,
                artifact_map,
                root,
            )
        self.assertFalse(output["location"]["known_location_event_verified"])
        self.assertEqual(
            output["location"]["status"],
            "LOCALIZACAO_CONHECIDA_DECLARADA_NAO_VERIFICADA",
        )


if __name__ == "__main__":
    unittest.main()
