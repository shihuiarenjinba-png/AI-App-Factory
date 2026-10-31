import importlib.util
import tempfile
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("freelance_core", HERE / "core.py")
core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = core
SPEC.loader.exec_module(core)

class LedgerTests(unittest.TestCase):
    def test_jp_and_us_minor_units(self):
        self.assertEqual(core.amount_to_minor("1234", "JPY"), 1234)
        self.assertEqual(core.amount_to_minor("12.34", "USD"), 1234)

    def test_add_summary_and_export(self):
        with tempfile.TemporaryDirectory() as td:
            store = core.LedgerStore(Path(td) / "books.db", "US")
            store.add_transaction("2026-10-01", "income", "1000.00", "Business income", "Client A")
            store.add_transaction("2026-10-02", "expense", "125.25", "Supplies", "Shop")
            summary = store.monthly_summary(2026, 10)
            self.assertEqual(summary["income"], 100000)
            self.assertEqual(summary["expense"], 12525)
            self.assertEqual(summary["net"], 87475)
            out = store.export_csv(Path(td) / "out.csv")
            self.assertTrue(out.exists())
            store.close()

    def test_profile_locks_after_first_transaction(self):
        with tempfile.TemporaryDirectory() as td:
            store = core.LedgerStore(Path(td) / "books.db", "JP")
            store.add_transaction("2026-10-01", "income", "1000", "売上高")
            with self.assertRaises(core.LedgerError):
                store.set_profile("US")
            store.close()

    def test_invalid_values_rejected(self):
        self.assertRaises(core.LedgerError, core.amount_to_minor, "0", "USD")
        self.assertRaises(core.LedgerError, core.validate_date, "10/31/2026")

if __name__ == "__main__":
    unittest.main()
