import json
import tempfile
import unittest
from pathlib import Path

from tools import intake_manifest


class IntakeManifestTests(unittest.TestCase):
    def test_scan_is_idempotent_and_classifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "inbound"
            (root / "materials").mkdir(parents=True)
            (root / "jd-batch").mkdir()
            (root / "materials" / "profile.txt").write_text("profile", encoding="utf-8")
            (root / "jd-batch" / "batch.txt").write_text("jd", encoding="utf-8")
            manifest = Path(tmp) / "manifest.json"
            first = intake_manifest.scan(root, manifest)
            second = intake_manifest.scan(root, manifest)
            self.assertEqual(len(first["entries"]), 2)
            self.assertEqual(len(second["entries"]), 2)
            self.assertEqual({entry["kind"] for entry in second["entries"]}, {"profile_material", "jd_batch"})
            self.assertEqual({entry["status"] for entry in second["entries"]}, {"skipped"})
            json.loads(manifest.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
