"""Product-specific smoke: real journal/ledger + verified receipt queue."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod

core = load("jp_bookkeeping_smoke_core", "core.py")
receipts = load("jp_bookkeeping_smoke_receipts", "receipt_import.py")

class ProductSmoke(unittest.TestCase):
    def test_journal_reports_and_receipt_review_are_separate(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            store = core.Store(root / "books.sqlite3")
            store.post("2026-11-01", "入金", [("1100", "1200", ""), ("4000", "", "1200")])
            self.assertTrue(store.balance_check()["balanced"])
            self.assertEqual(store.pnl()["利益"], 1200)
            self.assertEqual(sum(row["debit"] for row in store.trial()), sum(row["credit"] for row in store.trial()))
            receipt = root / "invoice.pdf"
            receipt.write_bytes(b"%PDF-1.4\n" + b"test receipt")
            result = receipts.import_receipts_verified(store.conn, [receipt, receipt])
            self.assertEqual((result["added"], result["duplicates"], result["errors"]), (1, 1, 0))
            self.assertEqual(len(receipts.list_receipts_verified(store.conn)), 1)
            self.assertEqual(len({r["id"] for r in store.journal()}), 1)
            store.close()
            reopened = core.Store(root / "books.sqlite3")
            self.assertEqual(reopened.pnl()["利益"], 1200)
            self.assertEqual(len(receipts.list_receipts_verified(reopened.conn)), 1)
            reopened.close()

if __name__ == "__main__":
    unittest.main()
