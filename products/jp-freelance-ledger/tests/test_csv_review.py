import csv
import tempfile
import unittest
from pathlib import Path
import sys

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))
from core import Store
from csv_review import CSV_FIELDS, CSVReviewError, apply_csv_import, review_csv


class CSVReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "transactions.csv"
        self.store = Store(Path(self.tmp.name) / "ledger.sqlite3")
        self.addCleanup(self.store.close)

    def write(self, rows):
        with self.path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(CSV_FIELDS)
            writer.writerows(rows)

    def row(self, date="2026-11-01", kind="経費", amount="1200", category="通信費"):
        return [date, kind, amount, category, "通信会社", "領収書", "", "ネット回線"]

    def test_preview_then_import_and_repeat_idempotently(self):
        a = self.row()
        b = self.row("2026-11-02", "収入", "10000", "売上高")
        self.write([a, b, a, self.row("bad-date")])
        preview = review_csv(self.path, self.store)
        self.assertEqual((len(preview["valid"]), len(preview["duplicates"]), len(preview["errors"])), (2, 1, 1))
        self.assertEqual(len(self.store.rows()), 0, "preview must not post")
        self.assertEqual(apply_csv_import(self.store, preview)["imported"], 2)
        self.assertEqual(self.store.monthly(2026, 11)["差引"], 8800)
        self.assertEqual(self.store.annual_summary(2026)["差引"], 8800)
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='CSV_IMPORT'").fetchone()[0], 2)
        repeat = review_csv(self.path, self.store)
        self.assertEqual(len(repeat["valid"]), 0)
        self.assertEqual(apply_csv_import(self.store, repeat)["imported"], 0)
        self.assertEqual(len(self.store.rows()), 2)

    def test_manual_existing_transaction_is_not_duplicated(self):
        self.store.add("2026-11-01", "経費", "1200", "通信費", "通信会社", "領収書", "", "ネット回線")
        self.write([self.row()])
        preview = review_csv(self.path, self.store)
        self.assertEqual(len(preview["duplicates"]), 1)
        self.assertEqual(len(preview["valid"]), 0)

    def test_changed_file_rejected_before_posting(self):
        self.write([self.row()])
        preview = review_csv(self.path, self.store)
        self.write([self.row("2026-11-02")])
        with self.assertRaises(CSVReviewError):
            apply_csv_import(self.store, preview)
        self.assertEqual(len(self.store.rows()), 0)

    def test_invalid_rows_are_excluded(self):
        self.write([
            self.row(amount="=100+100"),
            self.row(amount="1.5"),
            self.row(category="税額自動確定"),
            self.row(kind="米国"),
            self.row(amount="0"),
            self.row(amount="999999999999999999999"),
            self.row(),
        ])
        preview = review_csv(self.path, self.store)
        self.assertEqual(len(preview["errors"]), 6)
        self.assertEqual(len(preview["valid"]), 1)
        self.assertEqual(apply_csv_import(self.store, preview)["imported"], 1)

    def test_header_and_encoding_rejected(self):
        self.path.write_text("date,amount\n2026-11-01,100\n", encoding="utf-8")
        with self.assertRaises(CSVReviewError):
            review_csv(self.path, self.store)
        self.path.write_bytes(b"\xff\xfe\xff")
        with self.assertRaises(CSVReviewError):
            review_csv(self.path, self.store)

    def test_transaction_rollback_if_second_insert_fails(self):
        self.write([self.row(), self.row("2026-11-02")])
        preview = review_csv(self.path, self.store)
        self.store.conn.execute("""CREATE TRIGGER fail_second BEFORE INSERT ON transactions
            WHEN NEW.txn_date='2026-11-02' BEGIN SELECT RAISE(ABORT,'simulated failure'); END""")
        self.store.conn.commit()
        with self.assertRaises(Exception):
            apply_csv_import(self.store, preview)
        self.assertEqual(len(self.store.rows()), 0)
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM csv_import_history").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
