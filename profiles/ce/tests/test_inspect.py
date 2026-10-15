"""Synthetic helper tests, no model/AWS/runtime calls."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PACK = Path(__file__).resolve().parents[1]
SCRIPT = Path("skills/shared-evidence/scripts/evidence_read.py")
spec = importlib.util.spec_from_file_location("ce_evidence_inspect", PACK / "desk" / SCRIPT)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class InspectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_missing_is_not_healthy(self):
        self.assertEqual(helper.inspect(self.root, "catalog")["status"], "NOT_RUN")
        self.assertEqual(helper.inspect(self.root, "list", "receipts")["status"], "NOT_RUN")

    def test_catalog_preserved_not_interpreted(self):
        catalog = {"sources": [{"name": "synthetic-securitylake", "status": "ACCESS_DENIED"}]}
        (self.root / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
        result = helper.inspect(self.root, "catalog")
        self.assertEqual(result["catalog"], catalog)
        self.assertEqual(len(result["sha256"]), 64)

    def test_read_list_and_truncation(self):
        (self.root / "receipts").mkdir()
        (self.root / "receipts" / "example.json").write_text("line1\nline2", encoding="utf-8")
        result = helper.inspect(self.root, "list", "receipts")
        self.assertEqual(result["files"][0]["path"], "receipts/example.json")
        result = helper.inspect(self.root, "show", "receipts/example.json", limit=1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["text"], "line1")

    def test_path_escape_and_binary_denied(self):
        for name in ("../outside", "/proc/self/environ", "C:/secret", "receipts\\secret"):
            with self.assertRaises(ValueError):
                helper.read(self.root, name)
        (self.root / "binary").write_bytes(b"a\x00b")
        with self.assertRaises(ValueError):
            helper.read(self.root, "binary")



if __name__ == "__main__":
    unittest.main()
