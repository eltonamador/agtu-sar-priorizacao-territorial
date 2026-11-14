from __future__ import annotations

import base64
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import integrated_protocol as protocol
import test_integrated_protocol as fixtures
import visual_spatial_binding as visual
from test_schema_contracts import schema_errors


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZlKsAAAAASUVORK5CYII="
)


def decoded_inspection() -> dict:
    return {
        "inspection_version": visual.INSPECTION_VERSION,
        "decode_status": visual.DECODED,
        "pixel_width": 4000,
        "pixel_height": 2250,
        "metadata": {
            "camera": {"make": "DJI", "model": "Mini 3"},
            "timestamps": {
                "datetime_original": "2026:10:21 08:20:00",
                "offset_time_original": "-03:00",
                "subsec_time_original": "206",
            },
            "gps": {
                "latitude": 0.015,
                "longitude": -51.07,
                "horizontal_positioning_error_m": 3.3,
            },
            "optics": {"focal_length_35mm": 24.0},
            "dji_xmp": {
                "relative_altitude_m": 28.0,
                "gimbal_pitch_deg": 0.0,
                "gps_latitude": 0.015,
                "gps_longitude": -51.07,
            },
        },
        "inspection_error": None,
    }


class VisualSpatialBindingTests(unittest.TestCase):
    def build_fixture(
        self, directory: str, *, platform: str = "DRONE_RGB", direction: str = "NADIR",
    ) -> tuple[dict, dict, dict[str, str], Path]:
        root = Path(directory)
        image = root / "IMG-01.jpg"
        image.write_bytes(b"visual-test-bytes")
        case = fixtures.draft_case()
        case["visual_evidence"][0]["file_sha256"] = hashlib.sha256(image.read_bytes()).hexdigest()
        case["visual_evidence"][0]["platform"] = platform
        case["visual_evidence"][0]["lens_aim_direction_cardinal"] = direction
        case["visual_evidence"][0]["lens_aim_azimuth_deg"] = 0.0 if direction == "N" else None
        if platform == "SOLO":
            case["detectability_assessments"][0]["modality"] = "BUSCA_TERRESTRE"
            for dimension in case["detectability_assessments"][0]["dimensions"]:
                dimension["source_type"] = "FOTO_SOLO"
        loc_result = fixtures.valid_loc_result(case)
        case["source_artifacts"]["loc_result_sha256"] = protocol.canonical_sha256(loc_result)
        frozen = protocol.prepare_frozen_case(case, "2026-10-21T10:00:00-03:00")
        return frozen, loc_result, {"visual:IMG-01": image.name}, root

    def test_approximate_binding_and_full_revalidation(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            visual, "inspect_visual_file", return_value=decoded_inspection()
        ):
            case, loc_result, artifact_map, root = self.build_fixture(directory)
            manifest = visual.extract_visual_metadata_manifest(case, artifact_map, root)
            binding = visual.build_visual_sector_binding(case, loc_result, manifest)
            package = visual.validate_visual_package(
                case, loc_result, manifest, binding, artifact_map, root
            )
            manifest_schema = json.loads(
                (
                    visual.ROOT / "outputs" / "protocolo_integrado_v1"
                    / "visual_metadata_manifest_v1.schema.json"
                ).read_text(encoding="utf-8")
            )
            binding_schema = json.loads(
                (
                    visual.ROOT / "outputs" / "protocolo_integrado_v1"
                    / "visual_sector_binding_v1.schema.json"
                ).read_text(encoding="utf-8")
            )
        self.assertEqual(binding["bindings"][0]["quality"], visual.APPROXIMATE)
        self.assertEqual(binding["bindings"][0]["applicable_sector_ids"], ["SETOR-N"])
        self.assertEqual(
            package["verified_pairs"], {"IMG-01::SETOR-N": visual.APPROXIMATE}
        )
        self.assertFalse(binding["affects_loc"])
        self.assertFalse(binding["ground_truth_used"])
        self.assertIn(
            "PITCH_DJI_NAO_UTILIZADO_COMO_DISCRIMINANTE",
            binding["bindings"][0]["reason_codes"],
        )
        self.assertEqual(
            schema_errors(manifest, manifest_schema, manifest_schema), []
        )
        self.assertEqual(
            schema_errors(binding, binding_schema, binding_schema), []
        )

    def test_verified_package_is_consumed_by_det_without_changing_loc(self) -> None:
        rules = json.loads(protocol.DEFAULT_RULES_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            visual, "inspect_visual_file", return_value=decoded_inspection()
        ):
            root = Path(directory)
            value = fixtures.draft_case()
            value["visual_evidence"][0]["media_type"] = "IMAGE_PNG"
            image = root / "IMG-01.png"
            image.write_bytes(PNG_1X1)
            value["visual_evidence"][0]["file_sha256"] = hashlib.sha256(
                PNG_1X1
            ).hexdigest()
            artifact_map: dict[str, str] = {"visual:IMG-01": image.name}
            for key in value["source_artifacts"]:
                if key == "loc_result_sha256":
                    continue
                content = f"visual-package::{key}".encode("utf-8")
                path = root / f"{key}.bin"
                path.write_bytes(content)
                value["source_artifacts"][key] = hashlib.sha256(content).hexdigest()
                artifact_map[key] = path.name
            loc_result = fixtures.valid_loc_result(value)
            loc_path = root / "loc_result.json"
            loc_bytes = protocol.canonical_json_bytes(loc_result)
            loc_path.write_bytes(loc_bytes)
            value["source_artifacts"]["loc_result_sha256"] = hashlib.sha256(
                loc_bytes
            ).hexdigest()
            artifact_map["loc_result_sha256"] = loc_path.name
            frozen = protocol.prepare_frozen_case(
                value, "2026-10-21T10:00:00-03:00"
            )
            manifest = visual.extract_visual_metadata_manifest(
                frozen, artifact_map, root
            )
            binding = visual.build_visual_sector_binding(
                frozen, loc_result, manifest
            )
            previous_engine = protocol._VISUAL_SPATIAL_ENGINE_MODULE
            protocol._VISUAL_SPATIAL_ENGINE_MODULE = visual
            try:
                baseline = protocol.compile_case(
                    frozen, rules, artifact_map, root
                )
                integrated = protocol.compile_case(
                    frozen,
                    rules,
                    artifact_map,
                    root,
                    manifest,
                    binding,
                )
            finally:
                protocol._VISUAL_SPATIAL_ENGINE_MODULE = previous_engine
        self.assertEqual(
            baseline["location"]["logical_sha256"],
            integrated["location"]["logical_sha256"],
        )
        self.assertEqual(
            integrated["detectability"]["per_sector_modality"][0]["status"],
            "APTO_COM_RESTRICOES",
        )
        self.assertTrue(
            integrated["visual_evidence_policy"]["sector_binding_verified"]
        )
        self.assertEqual(
            integrated["visual_evidence_policy"]["sector_binding_usable_pair_count"],
            1,
        )
        self.assertFalse(integrated["visual_evidence_policy"]["affects_loc"])

    def test_ground_and_oblique_images_never_receive_automatic_footprint(self) -> None:
        for platform, direction in (("SOLO", "N"), ("DRONE_RGB", "N")):
            with self.subTest(platform=platform, direction=direction):
                with tempfile.TemporaryDirectory() as directory, mock.patch.object(
                    visual, "inspect_visual_file", return_value=decoded_inspection()
                ):
                    case, loc_result, artifact_map, root = self.build_fixture(
                        directory, platform=platform, direction=direction
                    )
                    manifest = visual.extract_visual_metadata_manifest(case, artifact_map, root)
                    binding = visual.build_visual_sector_binding(case, loc_result, manifest)
                row = binding["bindings"][0]
                self.assertEqual(row["quality"], visual.CONTEXTUAL)
                self.assertIsNone(row["footprint_geojson"])
                self.assertEqual(row["applicable_sector_ids"], [])

    def test_manifest_and_binding_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            visual, "inspect_visual_file", return_value=decoded_inspection()
        ):
            case, loc_result, artifact_map, root = self.build_fixture(directory)
            manifest_a = visual.extract_visual_metadata_manifest(case, artifact_map, root)
            manifest_b = visual.extract_visual_metadata_manifest(case, artifact_map, root)
            binding_a = visual.build_visual_sector_binding(case, loc_result, manifest_a)
            binding_b = visual.build_visual_sector_binding(case, loc_result, manifest_b)
        self.assertEqual(manifest_a, manifest_b)
        self.assertEqual(binding_a, binding_b)

    def test_tampered_sector_list_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            visual, "inspect_visual_file", return_value=decoded_inspection()
        ):
            case, loc_result, artifact_map, root = self.build_fixture(directory)
            manifest = visual.extract_visual_metadata_manifest(case, artifact_map, root)
            binding = visual.build_visual_sector_binding(case, loc_result, manifest)
            tampered = copy.deepcopy(binding)
            tampered["bindings"][0]["applicable_sector_ids"] = ["SETOR-S"]
            with self.assertRaises(protocol.InputValidationError):
                visual.validate_visual_package(
                    case, loc_result, manifest, tampered, artifact_map, root
                )

    def test_manifest_cannot_inject_a_manual_sector_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            visual, "inspect_visual_file", return_value=decoded_inspection()
        ):
            case, loc_result, artifact_map, root = self.build_fixture(directory)
            manifest = visual.extract_visual_metadata_manifest(case, artifact_map, root)
            injected = copy.deepcopy(manifest)
            record = injected["records"][0]
            record["operator_sector_ids"] = ["SETOR-S"]
            record["record_sha256"] = protocol.canonical_sha256({
                key: value for key, value in record.items() if key != "record_sha256"
            })
            injected["output_sha256"] = protocol.canonical_sha256({
                key: value for key, value in injected.items() if key != "output_sha256"
            })
            with self.assertRaises(protocol.InputValidationError):
                visual.build_visual_sector_binding(case, loc_result, injected)

    def test_insufficient_metadata_is_contextual(self) -> None:
        insufficient = {
            "inspection_version": visual.INSPECTION_VERSION,
            "decode_status": visual.DECODED,
            "pixel_width": 4000,
            "pixel_height": 2250,
            "metadata": {},
            "inspection_error": None,
        }
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            visual, "inspect_visual_file", return_value=insufficient
        ):
            case, loc_result, artifact_map, root = self.build_fixture(directory)
            manifest = visual.extract_visual_metadata_manifest(case, artifact_map, root)
            binding = visual.build_visual_sector_binding(case, loc_result, manifest)
        row = binding["bindings"][0]
        self.assertEqual(row["quality"], visual.CONTEXTUAL)
        self.assertIn("GPS_METADADO_INSUFICIENTE", row["reason_codes"])

    def test_loc_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            visual, "inspect_visual_file", return_value=decoded_inspection()
        ):
            case, loc_result, artifact_map, root = self.build_fixture(directory)
            manifest = visual.extract_visual_metadata_manifest(case, artifact_map, root)
            tampered = copy.deepcopy(loc_result)
            tampered["cross_candidate_ranking"] = True
            with self.assertRaises(protocol.InputValidationError):
                visual.build_visual_sector_binding(case, tampered, manifest)

    def test_reserved_ground_truth_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            visual, "inspect_visual_file", return_value=decoded_inspection()
        ):
            case, loc_result, artifact_map, root = self.build_fixture(directory)
            manifest = visual.extract_visual_metadata_manifest(case, artifact_map, root)
            manifest["ground_truth_lat"] = 0.0
            with self.assertRaises(protocol.GroundTruthFirewallError):
                visual.build_visual_sector_binding(case, loc_result, manifest)

    @unittest.skipUnless(
        visual.SWIFT_EXECUTABLE.is_file() and visual.SWIFT_HELPER_PATH.is_file(),
        "Swift/ImageIO indisponível",
    )
    def test_real_imageio_pixel_decode_returns_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "one.png"
            path.write_bytes(PNG_1X1)
            result = visual.inspect_visual_file(path, "IMAGE_PNG")
        self.assertEqual(result["decode_status"], visual.DECODED)
        self.assertEqual((result["pixel_width"], result["pixel_height"]), (1, 1))
        self.assertIsNone(result["inspection_error"])

    def test_invalid_image_has_explicit_nondecoded_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jpg"
            path.write_bytes(b"not-an-image")
            result = visual.inspect_visual_file(path, "IMAGE_JPEG")
        self.assertEqual(result["decode_status"], visual.NOT_DECODED)
        self.assertIsNone(result["pixel_width"])
        self.assertIsInstance(result["inspection_error"], str)

    def test_contract_files_are_parseable_and_pitch_policy_is_conservative(self) -> None:
        policy = json.loads(visual.POLICY_PATH.read_text(encoding="utf-8"))
        self.assertFalse(policy["metadata_gimbal_pitch_required"])
        self.assertFalse(policy["metadata_gimbal_pitch_is_discriminant"])
        for name in (
            "visual_metadata_manifest_v1.schema.json",
            "visual_sector_binding_v1.schema.json",
        ):
            schema = json.loads(
                (visual.ROOT / "outputs" / "protocolo_integrado_v1" / name).read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
