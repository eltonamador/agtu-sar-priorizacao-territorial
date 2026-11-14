from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import build_urbe01_visual_closure as module


GENERATED_AT = "2026-10-22T10:56:43-03:00"


class Urbe01VisualClosureTests(unittest.TestCase):
    def test_visual_subprocess_is_deterministic_and_non_discriminant(self) -> None:
        registry = module.load_json(module.REGISTRY_PATH)
        first = module.build_visual_artifacts(registry, GENERATED_AT)
        second = module.build_visual_artifacts(registry, GENERATED_AT)
        self.assertEqual(first, second)
        manifest, binding, summary = first
        self.assertFalse(manifest["reference_used_by_visual_audit"])
        self.assertFalse(binding["affects_loc"])
        self.assertEqual(summary["decoded_count"], 10)
        self.assertEqual(summary["qualified_visual_ids"], ["A05"])
        self.assertEqual(len(summary["contextual_visual_ids"]), 9)
        self.assertEqual(summary["a05_quality"], "APROXIMADO_METADADOS")
        self.assertEqual(summary["a05_sector_ids"], summary["expected_r01_sector_ids"])
        self.assertEqual(len(summary["a05_sector_ids"]), 8)

    def test_directional_divergences_remain_explicit(self) -> None:
        registry = module.load_json(module.REGISTRY_PATH)
        manifest, _binding, summary = module.build_visual_artifacts(registry, GENERATED_AT)
        self.assertTrue({"A02", "A03", "A07"}.issubset(summary["directional_review_ids"]))
        by_id = {record["visual_id"]: record for record in manifest["records"]}
        self.assertEqual(by_id["A02"]["directional_review"]["heading_status"], "REVISAR_DIVERGENCIA")
        self.assertEqual(by_id["A05"]["directional_review"]["heading_status"], "NAO_APLICAVEL_NADIR")

    def test_full_package_passes_and_does_not_expose_reference_in_visual_audit(self) -> None:
        before = module.verify_blind_package()["tree_sha256"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audit_dir = root / "audit"
            closure_dir = root / "closure"
            result = module.build_package(audit_dir, closure_dir, GENERATED_AT)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["photos_verified"], 10)
            self.assertEqual(result["blind_files_verified"], 35)
            self.assertEqual(result["post_opening_files_verified"], 10)
            self.assertEqual(result["qualified_visual_ids"], ["A05"])
            self.assertEqual(result["a05_sector_count"], 8)
            audit_text = b"\n".join(
                path.read_bytes() for path in sorted(audit_dir.rglob("*")) if path.is_file()
            )
            self.assertNotIn(b"0.0024809355844815323", audit_text)
            self.assertNotIn(b"-51.07092698392779", audit_text)
            visual_qa = json.loads(
                (audit_dir / "relatorio_qa_visual_urbe01_v1.json").read_text(encoding="utf-8")
            )
            closure_qa = json.loads(
                (closure_dir / "relatorio_qa_fechamento_urbe01_v1.json").read_text(encoding="utf-8")
            )
            self.assertEqual(visual_qa["status"], "PASS")
            self.assertEqual(closure_qa["status"], "PASS")
            self.assertTrue(all(visual_qa["gates"].values()))
            self.assertTrue(all(closure_qa["gates"].values()))
        after = module.verify_blind_package()["tree_sha256"]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
