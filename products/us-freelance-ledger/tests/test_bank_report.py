import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import Store
from bank_reconcile import BankReviewError, match_transaction, finalize_statement, cancel_statement
from bank_report import export_bank_report


class BankReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.db = self.folder / "ledger.sqlite3"
        self.store = Store(self.db)
        self.addCleanup(self.store.close)
        self.account = "Business Checking"
        self.day = "2026-10-31"
        self.tid = self.store.add("2026-10-12", "income", "50.25", "Business income")
        match_transaction(self.store.conn, self.tid, self.account, self.day)

    def check(self, closing="150.25"):
        return finalize_statement(self.store.conn, self.account, self.day, "100.00", closing)

    def report(self, name="check.csv"):
        return export_bank_report(self.store.conn, self.account, self.day, self.folder / name)

    def test_checked_csv_txt_and_audit_reproduce(self):
        self.check()
        before = self.store.conn.execute("SELECT amount_cents FROM transactions WHERE id=?", (self.tid,)).fetchone()[0]
        receipt = self.report()
        self.assertEqual(receipt["status"], "CHECKED")
        self.assertEqual(receipt["transaction_ids"], [self.tid])
        self.assertEqual(receipt["difference_cents"], 0)
        self.assertTrue(Path(receipt["csv_path"]).exists())
        txt = Path(receipt["text_path"]).read_text(encoding="utf-8")
        self.assertIn("Opening USD: 100.00", txt)
        self.assertIn("Difference USD: 0.00", txt)
        self.assertIn("BANK_RECONCILE_MEMBERS", txt)
        self.assertIn("CSV: ", txt)
        with Path(receipt["csv_path"]).open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertTrue(any(r["field"] == "closing_usd" and r["value"] == "150.25" for r in rows))
        self.assertTrue(any(r["record_type"] == "member" and r["reference_id"] == str(self.tid) for r in rows))
        after = self.store.conn.execute("SELECT amount_cents FROM transactions WHERE id=?", (self.tid,)).fetchone()[0]
        self.assertEqual(before, after)

    def test_undo_historical_report_survives_restart(self):
        self.check()
        cancel_statement(self.store.conn, self.account, self.day)
        self.store.close()
        self.store = Store(self.db)
        self.addCleanup(self.store.close)
        receipt = self.report()
        self.assertEqual(receipt["status"], "UNDONE (historical receipt)")
        text = Path(receipt["text_path"]).read_text(encoding="utf-8")
        self.assertIn("BANK_RECONCILE_CANCEL", text)
        self.assertIn("Historical undo reports", text)
        self.assertEqual(self.store.conn.execute("SELECT amount_cents FROM transactions WHERE id=?", (self.tid,)).fetchone()[0], 5025)

    def test_nonzero_never_finalized_or_reported_as_checked(self):
        with self.assertRaises(BankReviewError):
            self.check("150.26")
        with self.assertRaises(BankReviewError):
            self.report()
        self.assertFalse((self.folder / "check.csv").exists())

    def test_tampered_transaction_is_fail_closed(self):
        self.check()
        self.store.conn.execute("UPDATE transactions SET amount_cents=5026 WHERE id=?", (self.tid,))
        self.store.conn.commit()
        with self.assertRaises(BankReviewError):
            self.report()
        self.assertFalse((self.folder / "check.csv").exists())

    def test_legacy_missing_snapshot_is_fail_closed(self):
        self.check()
        self.store.conn.execute("DELETE FROM audit_log WHERE action='BANK_RECONCILE_MEMBERS'")
        self.store.conn.commit()
        with self.assertRaises(BankReviewError):
            self.report()

    def test_corrupt_snapshot_balance_type_is_fail_closed(self):
        self.check()
        row = self.store.conn.execute(
            "SELECT id,detail FROM audit_log WHERE action='BANK_RECONCILE_MEMBERS'"
        ).fetchone()
        import json
        payload = json.loads(row[1])
        payload["opening_cents"] = "10000"
        self.store.conn.execute("UPDATE audit_log SET detail=? WHERE id=?", (json.dumps(payload), row[0]))
        self.store.conn.commit()
        with self.assertRaises(BankReviewError):
            self.report()

    def test_changed_reconcile_audit_is_fail_closed(self):
        self.check()
        self.store.conn.execute(
            "UPDATE audit_log SET detail='wrong' WHERE action='BANK_RECONCILE'"
        )
        self.store.conn.commit()
        with self.assertRaises(BankReviewError):
            self.report()

    def test_csv_existing_is_not_overwritten(self):
        self.check()
        target = self.folder / "check.csv"
        target.write_text("KEEP", encoding="utf-8")
        with self.assertRaises(BankReviewError):
            self.report()
        self.assertEqual(target.read_text(encoding="utf-8"), "KEEP")
        self.assertFalse((self.folder / "check.txt").exists())

    def test_txt_existing_rolls_back_new_csv(self):
        self.check()
        human = self.folder / "check.txt"
        human.write_text("KEEP", encoding="utf-8")
        with self.assertRaises(BankReviewError):
            self.report()
        self.assertEqual(human.read_text(encoding="utf-8"), "KEEP")
        self.assertFalse((self.folder / "check.csv").exists())

    def test_invalid_output_folder_never_reports_success(self):
        self.check()
        with self.assertRaises(BankReviewError):
            export_bank_report(self.store.conn, self.account, self.day, self.folder / "missing" / "check.csv")

    def test_invalid_statement_date_rejected(self):
        self.check()
        with self.assertRaises(BankReviewError):
            export_bank_report(self.store.conn, self.account, "not-a-date", self.folder / "bad.csv")

    def test_csv_formula_label_neutralized(self):
        account = "=HYPERLINK(1)"
        match_transaction(self.store.conn, self.store.add("2026-10-12", "income", "2.00", "Business income"), account, self.day)
        finalize_statement(self.store.conn, account, self.day, "0.00", "2.00")
        result = export_bank_report(self.store.conn, account, self.day, self.folder / "formula.csv")
        with Path(result["csv_path"]).open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        value = next(r["value"] for r in rows if r["field"] == "account")
        self.assertTrue(value.startswith("'="))

    def test_gui_wiring_and_safe_success_message(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn('command=self.export_bank_check', source)
        self.assertIn('except (BankReviewError,OSError) as exc:', source)
        self.assertIn('receipt["csv_path"]', source)
        self.assertIn('receipt["text_path"]', source)


if __name__ == "__main__":
    unittest.main()
