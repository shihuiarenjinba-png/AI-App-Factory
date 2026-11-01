"""Receipt queue validation, idempotency and no-impact accounting fixtures."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "products" / "jp-bookkeeping-desk"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core = load("jp_receipt_core", "core.py")
receipts = load("jp_receipt_ingest", "receipt_ingest.py")


class ReceiptIngestTests(unittest.TestCase):
    def test_mixed_batch_duplicate_bytes_restart_and_accounting(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            a = root / "receipt.png"
            copy = root / "renamed.png"
            pdf = root / "invoice.pdf"
            empty = root / "empty.jpg"
            unsupported = root / "note.txt"
            a.write_bytes(b"image-contents")
            copy.write_bytes(a.read_bytes())
            pdf.write_bytes(b"%PDF-1.4\nfixture")
            empty.write_bytes(b"")
            unsupported.write_text("not a receipt")
            store = core.Store(root / "book.sqlite3")
            try:
                result = receipts.ingest_receipts(
                    store, [root / "missing.png", a, copy, pdf, empty, unsupported, a]
                )
                self.assertEqual((result["added"], result["duplicates"], result["rejected"]), (2, 2, 3))
                self.assertEqual(len(receipts.list_receipts(store)), 2)
                self.assertEqual(a.read_bytes(), b"image-contents")
                self.assertEqual(store.conn.execute(
                    "SELECT COUNT(*) FROM receipt_fingerprints").fetchone()[0], 2)
                store.post("2026-11-01", "売上", [("1000", 500, 0), ("4000", 0, 500)])
                self.assertTrue(store.balance_check()["balanced"])
                self.assertEqual(store.pnl()["利益"], 500)
                self.assertEqual(store.bs()["資産"], store.bs()["負債純資産合計"])
            finally:
                store.close()
            reopened = core.Store(root / "book.sqlite3")
            try:
                self.assertEqual(receipts.ingest_receipts(reopened, [a, pdf])["duplicates"], 2)
                self.assertEqual(len(receipts.list_receipts(reopened)), 2)
            finally:
                reopened.close()

    def test_file_size_and_limit_guards(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            large = root / "large.pdf"
            good = root / "small.PNG"
            large.write_bytes(b"123456")
            good.write_bytes(b"12")
            store = core.Store(root / "book.sqlite3")
            try:
                result = receipts.ingest_receipts(store, [large, good], max_bytes=5)
                self.assertEqual((result["added"], result["rejected"]), (1, 1))
                self.assertEqual(receipts.list_receipts(store)[0]["name"], "small.PNG")
                for bad in (0, -1, 1.5, "5"):
                    with self.assertRaises(ValueError):
                        receipts.ingest_receipts(store, [], max_bytes=bad)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
