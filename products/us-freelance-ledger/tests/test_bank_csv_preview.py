"""Read-only bank CSV review regression fixtures; no synthetic buyer claims."""
import csv
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))
from core import Store
from bank_reconcile import match_transaction
from bank_csv_preview import BankCSVError, csv_headers, preview_bank_csv, save_review_report

MAPPING = {"date": "Posted", "amount": "USD amount", "direction": "Flow", "currency": "CCY"}


class BankCSVPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "ledger.sqlite3"
        self.store = Store(self.database)
        self.addCleanup(self.store.close)
        self.tid = self.store.add("2026-10-12", "income", "50.25", "Business income")
        self.source = self.root / "statement.csv"

    def write_rows(self, rows):
        with self.source.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(MAPPING.values())
            writer.writerows(rows)

    def preview(self):
        return preview_bank_csv(self.source, MAPPING, self.store.conn)

    def fingerprint(self):
        return (self.store.conn.execute("SELECT COUNT(*),SUM(amount_cents) FROM transactions").fetchone()[:],
                self.store.conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])

    def test_valid_explicit_usd_mapping_and_review_copy(self):
        self.write_rows([["2026-10-12", "50.25", "credit", "USD"]])
        before = self.fingerprint()
        self.assertEqual(csv_headers(self.source), list(MAPPING.values()))
        result = self.preview()
        self.assertEqual(result["review_required"], 0)
        self.assertEqual(result["rows"][0]["ledger_candidate_ids"], [self.tid])
        self.assertEqual(result["rows"][0]["amount_cents"], 5025)
        self.assertEqual(result["rows"][0]["status"], "CANDIDATE ONLY")
        path = self.root / "review.txt"
        self.assertEqual(save_review_report(result, path), str(path.resolve()))
        self.assertIn("NOT POSTED", path.read_text(encoding="utf-8"))
        self.assertIn("5025", path.read_text(encoding="utf-8"))
        self.assertEqual(self.fingerprint(), before)

    def test_duplicate_and_unmatched_are_review_required(self):
        self.write_rows([["2026-10-12", "50.25", "in", "USD"],
                         ["2026-10-12", "50.25", "in", "USD"],
                         ["2026-10-13", "19.01", "out", "USD"]])
        result = self.preview()
        self.assertEqual(result["review_required"], 3)
        self.assertEqual([r["review_bucket"] for r in result["rows"]], ["DUPLICATE", "DUPLICATE", "UNMATCHED"])
        self.assertIn("DUPLICATE_CSV_CANDIDATE", result["rows"][0]["issues"])
        self.assertIn("DUPLICATE_CSV_CANDIDATE", result["rows"][1]["issues"])
        self.assertIn("NO_LEDGER_CANDIDATE", result["rows"][2]["issues"])

    def test_same_day_difference_candidate_is_not_an_auto_match(self):
        self.write_rows([["2026-10-12", "50.26", "credit", "USD"]])
        before = self.fingerprint()
        result = self.preview()
        self.assertEqual(result["review_required"], 1)
        self.assertEqual(result["rows"][0]["ledger_candidate_ids"], [])
        self.assertEqual(result["rows"][0]["difference_candidates"],
                         [{"transaction_id": self.tid, "difference_cents": 1}])
        self.assertEqual(self.fingerprint(), before)

    def test_invalid_sign_date_and_missing_amount_never_post(self):
        self.write_rows([["2026-02-30", "10.00", "credit", "USD"],
                         ["2026-10-12", "-50.25", "credit", "USD"],
                         ["2026-10-12", "", "debit", "USD"],
                         ["2026-10-12", "1.001", "debit", "USD"]])
        before = self.fingerprint()
        result = self.preview()
        self.assertEqual(result["review_required"], 4)
        self.assertTrue(all("INVALID_ROW" in row["issues"][0] for row in result["rows"]))
        self.assertEqual(self.fingerprint(), before)

    def test_foreign_currency_and_missing_currency_fail_closed(self):
        for currency in ("EUR", "JPY", "", "GBP"):
            self.write_rows([["2026-10-12", "50.25", "in", currency]])
            with self.subTest(currency=currency), self.assertRaisesRegex(BankCSVError, "USD"):
                self.preview()

    def test_existing_manual_match_is_not_silently_reused(self):
        match_transaction(self.store.conn, self.tid, "Checking", "2026-10-31")
        self.write_rows([["2026-10-12", "50.25", "credit", "USD"]])
        before = self.fingerprint()
        result = self.preview()
        self.assertEqual(result["review_required"], 1)
        self.assertIn("LEDGER_ALREADY_MATCHED", result["rows"][0]["issues"])
        self.assertEqual(self.fingerprint(), before)

    def test_missing_or_reused_mapping_rejected(self):
        self.write_rows([["2026-10-12", "50.25", "in", "USD"]])
        for mapping in ({**MAPPING, "currency": "Flow"},
                        {**MAPPING, "date": "missing"}, {"date": "Posted"}):
            with self.subTest(mapping=mapping), self.assertRaises(BankCSVError):
                preview_bank_csv(self.source, mapping, self.store.conn)

    def test_corrupt_csv_and_extra_column_rejected(self):
        self.source.write_bytes(b"Posted,USD amount,Flow,CCY\n2026-10-12,50.25,in,USD,extra\n")
        with self.assertRaises(BankCSVError):
            self.preview()
        self.source.write_bytes(b"\xff\xfe")
        with self.assertRaises(BankCSVError):
            csv_headers(self.source)

    def test_restart_and_no_auto_matching_or_ledger_changes(self):
        self.write_rows([["2026-10-12", "50.25", "in", "USD"]])
        before = self.fingerprint()
        self.store.close()
        self.store = Store(self.database)
        self.addCleanup(self.store.close)
        result = self.preview()
        self.assertEqual(result["rows"][0]["ledger_candidate_ids"], [self.tid])
        self.assertEqual(self.fingerprint(), before)
        exists = self.store.conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='bank_matches'"
        ).fetchone()[0]
        self.assertEqual(exists, 0)

    def test_no_overwrite_or_false_success_after_source_edit(self):
        self.write_rows([["2026-10-12", "50.25", "in", "USD"]])
        result = self.preview()
        target = self.root / "review.txt"
        target.write_text("keep this", encoding="utf-8")
        with self.assertRaisesRegex(BankCSVError, "overwritten"):
            save_review_report(result, target)
        self.assertEqual(target.read_text(encoding="utf-8"), "keep this")
        self.source.write_text("Posted,USD amount,Flow,CCY\n2026-10-12,50.26,in,USD\n", encoding="utf-8")
        with self.assertRaisesRegex(BankCSVError, "changed"):
            save_review_report(result, self.root / "new.txt")
        self.assertFalse((self.root / "new.txt").exists())


    def test_same_amount_on_different_day_is_unmatched_not_auto_matched(self):
        self.write_rows([["2026-10-13", "50.25", "credit", "USD"]])
        before = self.database.read_bytes()
        report = self.preview()
        row = report["rows"][0]
        self.assertEqual(row["review_bucket"], "UNMATCHED")
        self.assertEqual(row["ledger_candidate_ids"], [])
        self.assertEqual(row["other_date_candidates"],
                         [{"transaction_id": self.tid, "ledger_date": "2026-10-12"}])
        self.assertIn("SAME_AMOUNT_DIFFERENT_DATE_REVIEW", row["issues"])
        self.assertEqual(self.database.read_bytes(), before)

    def test_multiple_exact_ledger_entries_are_review_required(self):
        second = self.store.add("2026-10-12", "income", "50.25", "Business income")
        self.write_rows([["2026-10-12", "50.25", "credit", "USD"]])
        report = self.preview()
        self.assertEqual(report["rows"][0]["review_bucket"], "REVIEW REQUIRED")
        self.assertEqual(report["rows"][0]["ledger_candidate_ids"], [self.tid, second])
        self.assertEqual(report["buckets"]["CANDIDATE"], 0)

    def test_stale_ledger_cannot_produce_successful_report(self):
        self.write_rows([["2026-10-12", "50.25", "credit", "USD"]])
        report = self.preview()
        target = self.root / "stale.txt"
        self.store.add("2026-10-14", "expense", "1.00", "Supplies")
        with self.assertRaisesRegex(BankCSVError, "Ledger changed"):
            save_review_report(report, target, self.store.conn)
        self.assertFalse(target.exists())

    def test_report_records_four_review_buckets_and_source_and_ledger_hash(self):
        self.write_rows([["2026-10-12", "50.25", "credit", "USD"],
                         ["2026-10-14", "12.00", "debit", "USD"]])
        before = self.database.read_bytes()
        report = self.preview()
        target = self.root / "evidence.txt"
        self.assertEqual(report["buckets"]["CANDIDATE"], 1)
        self.assertEqual(report["buckets"]["UNMATCHED"], 1)
        save_review_report(report, target, self.store.conn)
        text = target.read_text(encoding="utf-8")
        self.assertIn("Ledger snapshot SHA256:", text)
        self.assertIn("Generated UTC:", text)
        self.assertIn("CANDIDATE=1", text)
        self.assertIn("UNMATCHED=1", text)
        self.assertEqual(self.database.read_bytes(), before)

    def test_large_csv_refused_without_touching_ledger(self):
        self.source.write_bytes(b"Posted,USD amount,Flow,CCY\\n" + b"x" * (5 * 1024 * 1024 + 1))
        before = self.fingerprint()
        with self.assertRaisesRegex(BankCSVError, "5 MiB"):
            self.preview()
        self.assertEqual(self.fingerprint(), before)

    def test_2001_rows_refused_and_no_report_created(self):
        self.write_rows([["2026-10-12", "50.25", "credit", "USD"]] * 2001)
        with self.assertRaisesRegex(BankCSVError, "2000 records"):
            self.preview()
        self.assertFalse((self.root / "review.txt").exists())


if __name__ == "__main__":
    unittest.main()
