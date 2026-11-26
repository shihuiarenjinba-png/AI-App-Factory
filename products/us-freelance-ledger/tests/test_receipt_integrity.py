import hashlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from receipt_integrity import audit_receipts
from receipt_queue import list_receipts


class ReceiptIntegrityTests(unittest.TestCase):
    def make_db(self):
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE receipt_queue(id INTEGER PRIMARY KEY, source_path TEXT, sha256 TEXT, size_bytes INTEGER, status TEXT, transaction_id INTEGER)")
        return db

    def test_ok_changed_missing_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "receipt.pdf"
            p.write_bytes(b"%PDF-test")
            db = self.make_db()
            db.execute("INSERT INTO receipt_queue VALUES(1,?,?,?,?,NULL)",
                       (str(p), hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_size, "LINKED"))
            original = list_receipts(db)
            self.assertEqual(audit_receipts(db)[0]["status"], "OK")
            p.write_bytes(b"%PDF-other")
            self.assertEqual(audit_receipts(db)[0]["status"], "CHANGED")
            p.unlink()
            self.assertEqual(audit_receipts(db)[0]["status"], "MISSING")
            self.assertEqual(list_receipts(db), original)
            db.close()

    def test_empty_file_review(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "empty.pdf"
            p.write_bytes(b"")
            db = self.make_db()
            db.execute("INSERT INTO receipt_queue VALUES(1,?,?,?,?,NULL)",
                       (str(p), "0", 1, "PENDING_MANUAL_REVIEW"))
            self.assertEqual(audit_receipts(db)[0]["status"], "REVIEW")
            db.close()

    def test_no_receipts(self):
        db = self.make_db()
        self.assertEqual(audit_receipts(db), [])
        db.close()


if __name__ == "__main__":
    unittest.main()
