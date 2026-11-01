"""Receipt import cap and collection input validation; source stays unchanged."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "products" / "jp-bookkeeping-desk"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core = load("jp_receipt_limit_core", "core.py")
receipts = load("jp_receipt_limit_import", "receipt_import.py")


class ReceiptLimitTests(unittest.TestCase):
    def test_invalid_caps_and_collection_are_rejected_before_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            file = root / "r.png"
            payload = b"\x89PNG\r\n\x1a\n" + b"valid-bytes"
            file.write_bytes(payload)
            store = core.Store(root / "books.db")
            try:
                for cap in (0, -1, 1.5, "20", True, 200 * 1024 * 1024 + 1):
                    with self.subTest(cap=cap), self.assertRaises(ValueError):
                        receipts.import_receipts_verified(store.conn, [file], max_bytes=cap)
                for paths in (None, str(file), file, b"bad"):
                    with self.subTest(paths=paths), self.assertRaises(ValueError):
                        receipts.import_receipts_verified(store.conn, paths)
                self.assertEqual(store.conn.execute("SELECT COUNT(*) FROM receipt_queue").fetchone()[0], 0)
                too_small = receipts.import_receipts_verified(store.conn, [file], max_bytes=len(payload)-1)
                self.assertEqual(too_small["errors"], 1)
                accepted = receipts.import_receipts_verified(store.conn, [file], max_bytes=len(payload))
                self.assertEqual(accepted["added"], 1)
                self.assertEqual(receipts.import_receipts_verified(store.conn, [file])["duplicates"], 1)
                self.assertEqual(file.read_bytes(), payload)
                self.assertTrue(store.balance_check()["balanced"])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
