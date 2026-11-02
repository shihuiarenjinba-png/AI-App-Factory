"""Regression: finalized JP bank statements lock historical bank postings."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1] / "products" / "jp-bookkeeping-desk"

def load(name, file):
    spec = importlib.util.spec_from_file_location(name, PRODUCT / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

core = load("jp_bank_lock_core", "core.py")
recon = load("jp_bank_lock_reconciliation", "reconciliation.py")

class ReconciliationLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = core.Store(Path(self.temp.name) / "ledger.sqlite3")
        self.bank = recon.BankReconciler(self.store)
        self.store.post("2026-09-30", "opening", [
            ("1100", 1000, 0), ("3000", 0, 1000)])
        self.bank_line = self.store.conn.execute(
            "SELECT l.id FROM lines l JOIN accounts a ON a.id=l.account_id "
            "WHERE a.code='1100'").fetchone()[0]

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_finalized_bank_period_rejects_backdated_bank_entry(self):
        statement = self.bank.start("1100", "2026-09-30", 0, 1000)
        self.bank.mark(statement, self.bank_line)
        self.bank.finalize(statement)
        before = len(self.store.journal())
        with self.assertRaisesRegex(core.BookError, "照合確定済み"):
            self.store.post("2026-09-29", "backdated bank deposit", [
                ("1100", 100, 0), ("4000", 0, 100)])
        with self.assertRaisesRegex(core.BookError, "照合確定済み"):
            self.store.post("2026-09-30", "backdated bank withdrawal", [
                ("5200", 100, 0), ("1100", 0, 100)])
        self.assertEqual(len(self.store.journal()), before)
        self.assertEqual(self.bank.report(statement)["difference_yen"], 0)
        self.assertTrue(self.store.balance_check()["balanced"])

    def test_post_statement_correction_and_nonbank_history_remain_allowed(self):
        statement = self.bank.start("1100", "2026-09-30", 0, 1000)
        self.bank.mark(statement, self.bank_line)
        self.bank.finalize(statement)
        self.store.post("2026-10-01", "current-period correction", [
            ("1100", 200, 0), ("4000", 0, 200)])
        self.store.post("2026-09-29", "non-bank adjustment", [
            ("1000", 50, 0), ("4000", 0, 50)])
        self.assertTrue(self.store.balance_check()["balanced"])
        self.assertEqual(self.store.pnl()["利益"], 250)
        self.assertEqual(self.store.bs()["資産"], self.store.bs()["負債純資産合計"])
        self.assertEqual(self.bank.report(statement)["status"], "FINALIZED")

    def test_mark_unmark_audit_is_idempotent_and_persistent(self):
        statement = self.bank.start("1100", "2026-09-30", 0, 1000)
        self.assertTrue(self.bank.mark(statement, self.bank_line))
        self.assertFalse(self.bank.mark(statement, self.bank_line))
        self.assertTrue(self.bank.unmark(statement, self.bank_line))
        self.assertFalse(self.bank.unmark(statement, self.bank_line))
        events = [row[0] for row in self.store.conn.execute(
            "SELECT action FROM audit_log WHERE action IN ('RECON_MARK','RECON_UNMARK') ORDER BY id")]
        self.assertEqual(events, ["RECON_MARK", "RECON_UNMARK"])
        self.assertTrue(self.bank.mark(statement, self.bank_line))
        self.assertEqual(self.bank.finalize(statement)["difference_yen"], 0)
        self.assertEqual(self.store.conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='RECON_MARK'").fetchone()[0], 2)

if __name__ == "__main__":
    unittest.main()
