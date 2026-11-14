from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import build_mata01_profile_v3 as builder


class Mata01ProfileV3Test(unittest.TestCase):
    def test_build_is_blind_auditable_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = builder.build(Path(first_dir))
            second = builder.build(Path(second_dir))
            self.assertEqual(first["qa"]["status"], "PASS")
            self.assertEqual(second["qa"]["status"], "PASS")
            self.assertTrue(first["result"]["ground_truth_absent"])
            self.assertFalse(first["top3"]["equivalent_to_complete_base"])
            self.assertEqual(first["result"]["output_sha256"], second["result"]["output_sha256"])

            first_manifest = json.loads(Path(first["manifest_path"]).read_text(encoding="utf-8"))
            second_manifest = json.loads(Path(second["manifest_path"]).read_text(encoding="utf-8"))
            first_hashes = {row["path"]: row["sha256"] for row in first_manifest["published_files"]}
            second_hashes = {row["path"]: row["sha256"] for row in second_manifest["published_files"]}
            self.assertEqual(first_hashes, second_hashes)

    def test_north_clue_changes_only_north_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as output_dir:
            built = builder.build(Path(output_dir))
            primary = next(
                record for record in built["result"]["lambda_results"] if record["lambda"] == 0.1
            )
            north = [row for row in primary["rows"] if row["sector_id"].endswith("::N")]
            other = [row for row in primary["rows"] if not row["sector_id"].endswith("::N")]
            self.assertEqual(len(north), 3)
            self.assertTrue(all(row["profile_compatibility"] == 1.0 for row in north))
            self.assertTrue(all(row["profile_compatibility"] == 0.0 for row in other))


if __name__ == "__main__":
    unittest.main()
