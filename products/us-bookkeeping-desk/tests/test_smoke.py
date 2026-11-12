"""Product-owned smoke: a real local double-entry transaction and evidence link."""
import sys
import tempfile
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))
from core import Store
from receipt_vault import ReceiptVault


class ProductSmoke(unittest.TestCase):
    def test_local_journal_evidence_and_balance(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            store = Store(base / "book.sqlite3", "cash")
            try:
                entry = store.post("2026-10-01", "Customer invoice paid",
                                   [("1100", "125.00", ""), ("4000", "", "125.00")])
                receipt = base / "invoice.pdf"
                receipt.write_bytes(b"%PDF-1.7\n% local fixture\n")
                vault = ReceiptVault(store)
                self.assertEqual(vault.attach_many(entry, [receipt])[0]["status"], "attached")
                self.assertEqual(len(vault.for_entry(entry)), 1)
                self.assertTrue(store.balance_check()["balanced"])
                self.assertEqual(store.pnl()["net_income"], 12500)
                self.assertEqual(store.bs()["assets"], store.bs()["liabilities_and_equity"])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
