import hashlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1] / "products" / "us-freelance-ledger"
sys.path.insert(0, str(PRODUCT))
from receipt_queue import enqueue_receipts, list_receipts
from receipt_integrity import audit_receipts


class ReceiptIntegrityRegression(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.conn = sqlite3.connect(self.root / "ledger.sqlite3")

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def test_detects_content_change_and_missing_without_mutation(self):
        receipt = self.root / "invoice.pdf"
        receipt.write_bytes(b"%PDF-1.7 original")
        self.assertEqual(enqueue_receipts(self.conn, [receipt])[0]["status"], "QUEUED")
        before = list_receipts(self.conn)
        self.assertEqual(audit_receipts(self.conn)[0]["status"], "OK")
        receipt.write_bytes(b"%PDF-1.7 modified")
        self.assertEqual(audit_receipts(self.conn)[0]["status"], "CHANGED")
        receipt.unlink()
        self.assertEqual(audit_receipts(self.conn)[0]["status"], "MISSING")
        self.assertEqual(list_receipts(self.conn), before)

    def test_rejects_symlink_after_intake(self):
        receipt = self.root / "receipt.jpg"
        receipt.write_bytes(b"original")
        enqueue_receipts(self.conn, [receipt])
        target = self.root / "other.jpg"
        target.write_bytes(b"original")
        receipt.unlink()
        try:
            receipt.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        self.assertEqual(audit_receipts(self.conn)[0]["status"], "REVIEW")

    def test_empty_and_no_receipts(self):
        self.assertEqual(audit_receipts(self.conn), [])
        receipt = self.root / "receipt.png"
        receipt.write_bytes(b"data")
        enqueue_receipts(self.conn, [receipt])
        receipt.write_bytes(b"")
        self.assertEqual(audit_receipts(self.conn)[0]["status"], "REVIEW")


if __name__ == "__main__":
    unittest.main()
