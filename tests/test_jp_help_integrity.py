"""Search candidates must map to real, active JP account codes."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "products" / "jp-bookkeeping-desk" / "core.py"
spec = importlib.util.spec_from_file_location("jp_help_integrity_core", CORE)
core = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = core
spec.loader.exec_module(core)

class HelpIntegrityTests(unittest.TestCase):
    def test_help_codes_exist_and_advanced_only_when_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            store = core.Store(Path(temp) / "book.sqlite3")
            try:
                valid = {a["code"] for a in store.accounts()}
                for query in ("家賃", "パソコン", "原状回復", "減価償却", "資産除去債務", "個人カード"):
                    with self.subTest(query=query):
                        results = store.search_help(query, limit=30, include_advanced=True)
                        self.assertTrue(all(item["code"] in valid or item["audience"] == "advanced" for item in results))
                self.assertIn("5200", [r["code"] for r in store.search_help("家賃")])
                self.assertIn("2150", [r["code"] for r in store.search_help("資産除去債務")])
                self.assertNotIn("2150", valid)  # reference-only, never an automatic journal candidate
                self.assertIn("1590", [r["code"] for r in store.search_help("減価償却累計額", include_advanced=True)])
                self.assertNotIn("1590", [r["code"] for r in store.search_help("減価償却累計額", include_advanced=False)])
                for sample in ("家賃", "電車", "売上", "仕入"):
                    candidate = core.suggest_entry(sample)
                    self.assertIn(candidate["debit_code"], valid)
                    self.assertIn(candidate["credit_code"], valid)
            finally:
                store.close()

if __name__ == "__main__":
    unittest.main()
