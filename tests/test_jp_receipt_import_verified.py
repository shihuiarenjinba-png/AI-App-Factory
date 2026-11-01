import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "products" / "jp-bookkeeping-desk" / "receipt_import.py"
S = importlib.util.spec_from_file_location("jp_receipt_verified", P)
m = importlib.util.module_from_spec(S)
S.loader.exec_module(m)

class ReceiptImportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "test.sqlite3"
        self.conn = sqlite3.connect(self.db)
        self.conn.executescript("""
          CREATE TABLE receipt_queue(id INTEGER PRIMARY KEY AUTOINCREMENT,file_path TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'PENDING',suggested_entry TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
          CREATE TABLE audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT,action TEXT NOT NULL,
            detail TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
          CREATE TABLE entries(id INTEGER PRIMARY KEY AUTOINCREMENT,description TEXT);
        """)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def write(self, name, content):
        p = self.root / name
        p.write_bytes(content)
        return p

    def test_mixed_batch_duplicates_invalid_and_restart(self):
        a = self.write("receipt.png", b"\x89PNG\r\n\x1a\n" + b"a" * 30)
        b = self.write("copy.png", a.read_bytes())
        c = self.write("bill.pdf", b"%PDF-1.4\n" + b"b" * 30)
        bad = self.write("fake.pdf", b"not a pdf")
        missing = self.root / "missing.jpg"
        r = m.import_receipts_verified(self.conn, [a, b, c, bad, missing, a])
        self.assertEqual((r["added"], r["duplicates"], r["errors"]), (2, 2, 2))
        self.assertEqual(len(m.list_receipts_verified(self.conn)), 2)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM entries").fetchone()[0], 0)
        self.conn.close()
        self.conn = sqlite3.connect(self.db)
        self.assertEqual(m.import_receipts_verified(self.conn, [c])["duplicates"], 1)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM audit_log").fetchone()[0], 2)

    def test_size_zero_and_extension_rejections(self):
        empty = self.write("empty.png", b"")
        huge = self.write("huge.png", b"\x89PNG\r\n\x1a\n" + b"x" * 100)
        badext = self.write("receipt.exe", b"\x89PNG\r\n\x1a\n")
        result = m.import_receipts_verified(self.conn, [empty, huge, badext], max_bytes=64)
        self.assertEqual(result["errors"], 3)
        self.assertEqual(result["added"], 0)

    def test_legacy_rows_not_mistaken_for_verified(self):
        self.conn.execute("INSERT INTO receipt_queue(file_path) VALUES(?)", ("/old/unverified.pdf",))
        self.conn.commit()
        valid = self.write("real.jpg", b"\xff\xd8\xff" + b"a" * 30)
        self.assertEqual(m.import_receipts_verified(self.conn, [valid])["added"], 1)
        self.assertEqual(len(m.list_receipts_verified(self.conn)), 1)

    def test_format_checks(self):
        a = self.write("receipt.webp", b"RIFF" + b"1234" + b"WEBP" + b"x" * 10)
        b = self.write("photo.jpeg", b"\xff\xd8\xff" + b"x" * 10)
        self.assertEqual(m.import_receipts_verified(self.conn, [a, b])["added"], 2)

if __name__ == "__main__":
    unittest.main()
