import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("book_core", HERE / "core.py")
core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = core
SPEC.loader.exec_module(core)

class BookTests(unittest.TestCase):
    def test_balanced_entry_and_reports(self):
        with tempfile.TemporaryDirectory() as td:
            store = core.BookStore(Path(td) / "books.db", "USD")
            store.post_entry("2026-10-31", "Client work", [
                ("1100", "1000.00", ""),
                ("4000", "", "1000.00"),
            ])
            store.post_entry("2026-10-31", "Supplies", [
                ("5000", "125.00", ""),
                ("1100", "", "125.00"),
            ])
            pnl = store.income_statement()
            self.assertEqual(pnl["revenue"], 100000)
            self.assertEqual(pnl["expense"], 12500)
            self.assertEqual(pnl["net_income"], 87500)
            bs = store.balance_sheet()
            self.assertEqual(bs["assets"], 87500)
            self.assertEqual(bs["liabilities_and_equity"], 87500)
            store.close()

    def test_unbalanced_entry_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            store = core.BookStore(Path(td) / "books.db", "JPY")
            with self.assertRaises(core.BookError):
                store.post_entry("2026-10-31", "bad", [
                    ("1000", "1000", ""), ("4000", "", "900")
                ])
            store.close()

    def test_period_lock(self):
        with tempfile.TemporaryDirectory() as td:
            store = core.BookStore(Path(td) / "books.db", "JPY")
            store.set_lock("2026-09-30")
            with self.assertRaises(core.BookError):
                store.post_entry("2026-09-30", "old", [
                    ("1000", "100", ""), ("4000", "", "100")
                ])
            store.close()

if __name__ == "__main__":
    unittest.main()
