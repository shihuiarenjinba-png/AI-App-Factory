"""Headless US bank review tests: no IRS tax treatment is inferred."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1] / "products" / "us-freelance-ledger"


def load(name):
    spec = importlib.util.spec_from_file_location(name, PRODUCT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core = load("core")
bank = load("bank_reconcile")


class BankReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = core.Store(Path(self.tmp.name) / "book.sqlite3", "cash")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def add(self, kind, amount, day="2026-10-01"):
        return self.store.add(day, kind, amount,
                              "Business income" if kind == "income" else "Supplies")

    def test_reconcile_exact_cents_and_ledger_unchanged(self):
        incoming = self.add("income", "100.25")
        outgoing = self.add("expense", "20.10")
        before = self.store.monthly(2026, 10)
        bank.match_transaction(self.store.conn, incoming, "Checking", "2026-10-31")
        bank.match_transaction(self.store.conn, outgoing, "Checking", "2026-10-31")
        preview = bank.statement_preview(self.store.conn, "Checking", "2026-10-31",
                                         "50.00", "130.15")
        self.assertEqual(preview["movement_cents"], 8015)
        self.assertEqual(preview["difference_cents"], 0)
        bank.finalize_statement(self.store.conn, "Checking", "2026-10-31",
                                "50.00", "130.15")
        self.assertEqual(bank.match_statuses(self.store.conn),
                         {incoming: "RECONCILED", outgoing: "RECONCILED"})
        self.assertEqual(self.store.monthly(2026, 10), before)
        actions = [r[0] for r in self.store.conn.execute("SELECT action FROM audit_log")]
        self.assertIn("BANK_RECONCILE", actions)
        with self.assertRaises(bank.BankReviewError):
            bank.unmatch_transaction(self.store.conn, incoming)

    def test_difference_blocks_finalize_and_preserves_unfinalized_state(self):
        incoming = self.add("income", "10")
        bank.match_transaction(self.store.conn, incoming, "Business bank", "2026-10-31")
        self.assertEqual(bank.statement_preview(
            self.store.conn, "Business bank", "2026-10-31", "0", "9.99"
        )["difference_cents"], -1)
        with self.assertRaises(bank.BankReviewError):
            bank.finalize_statement(self.store.conn, "Business bank",
                                    "2026-10-31", "0", "9.99")
        self.assertEqual(bank.match_statuses(self.store.conn)[incoming], "CLEARED")
        self.assertEqual(self.store.conn.execute(
            "SELECT COUNT(*) FROM bank_reconciliations").fetchone()[0], 0)

    def test_duplicate_match_unmatch_and_unknown_transaction(self):
        incoming = self.add("income", "1")
        bank.match_transaction(self.store.conn, incoming, "A", "2026-10-31")
        with self.assertRaises(bank.BankReviewError):
            bank.match_transaction(self.store.conn, incoming, "B", "2026-10-31")
        bank.unmatch_transaction(self.store.conn, incoming)
        self.assertNotIn(incoming, bank.match_statuses(self.store.conn))
        with self.assertRaises(bank.BankReviewError):
            bank.unmatch_transaction(self.store.conn, incoming)
        with self.assertRaises(bank.BankReviewError):
            bank.match_transaction(self.store.conn, 999999, "A", "2026-10-31")

    def test_account_isolation_prior_balance_and_restart(self):
        first = self.add("income", "10")
        second = self.add("expense", "2", "2026-11-02")
        bank.match_transaction(self.store.conn, first, "Checking", "2026-10-31")
        bank.finalize_statement(self.store.conn, "Checking", "2026-10-31", "0", "10")
        bank.match_transaction(self.store.conn, second, "Checking", "2026-11-30")
        with self.assertRaises(bank.BankReviewError):
            bank.finalize_statement(self.store.conn, "Checking", "2026-11-30",
                                    "0", "-2")
        bank.finalize_statement(self.store.conn, "Checking", "2026-11-30", "10", "8")
        self.store.close()
        self.store = core.Store(Path(self.tmp.name) / "book.sqlite3", "cash")
        self.assertEqual(bank.match_statuses(self.store.conn)[second], "RECONCILED")
        self.assertEqual(self.store.annual_summary(2026)["net"], 800)

    def test_accrual_books_cannot_masquerade_as_cash_statement(self):
        self.store.close()
        self.store = core.Store(Path(self.tmp.name) / "accrual.sqlite3", "accrual")
        txn = self.add("income", "100")
        with self.assertRaises(bank.BankReviewError):
            bank.match_transaction(self.store.conn, txn, "Bank", "2026-10-31")
        with self.assertRaises(bank.BankReviewError):
            bank.statement_preview(self.store.conn, "Bank", "2026-10-31", "0", "100")

    def test_invalid_inputs_and_backdated_statement(self):
        transaction = self.add("income", "10", "2026-10-15")
        for account, day in [("", "2026-10-31"), ("A", "2026-02-30"),
                             ("A", "2026-10-14")]:
            with self.assertRaises(bank.BankReviewError):
                bank.match_transaction(self.store.conn, transaction, account, day)
        bank.match_transaction(self.store.conn, transaction, "A", "2026-10-31")
        for amount in ("NaN", "1.001", "Infinity", "99999999999999999999"):
            with self.assertRaises(bank.BankReviewError):
                bank.statement_preview(self.store.conn, "A", "2026-10-31",
                                       amount, "10")
        bank.finalize_statement(self.store.conn, "A", "2026-10-31", "0", "10")
        with self.assertRaises(bank.BankReviewError):
            bank.match_transaction(self.store.conn, self.add("income", "1"),
                                   "A", "2026-10-31")


    def test_cancel_last_statement_reopens_only_matches_with_audit_and_restart(self):
        income = self.add("income", "100.25")
        expense = self.add("expense", "20.10")
        before = self.store.monthly(2026, 10)
        for txn in (income, expense):
            bank.match_transaction(self.store.conn, txn, "Checking", "2026-10-31")
        bank.finalize_statement(self.store.conn, "Checking", "2026-10-31",
                                "50.00", "130.15")
        result = bank.cancel_statement(self.store.conn, "Checking", "2026-10-31")
        self.assertEqual(result["transaction_ids"], [income, expense])
        self.assertTrue(result["review_required"])
        self.assertEqual(bank.match_statuses(self.store.conn),
                         {income: "CLEARED", expense: "CLEARED"})
        self.assertEqual(self.store.monthly(2026, 10), before)
        self.assertEqual(self.store.conn.execute(
            "SELECT COUNT(*) FROM bank_reconciliations").fetchone()[0], 0)
        self.assertEqual(self.store.conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='BANK_RECONCILE_CANCEL'"
        ).fetchone()[0], 1)
        with self.assertRaises(bank.BankReviewError):
            bank.cancel_statement(self.store.conn, "Checking", "2026-10-31")
        self.store.close()
        self.store = core.Store(Path(self.tmp.name) / "book.sqlite3", "cash")
        self.assertEqual(bank.match_statuses(self.store.conn)[income], "CLEARED")
        bank.finalize_statement(self.store.conn, "Checking", "2026-10-31",
                                "50.00", "130.15")
        self.assertEqual(bank.match_statuses(self.store.conn)[income], "RECONCILED")

    def test_cancel_latest_first_preserves_month_to_month_balance(self):
        oct_txn = self.add("income", "10.00")
        nov_txn = self.add("expense", "2.00", "2026-11-02")
        bank.match_transaction(self.store.conn, oct_txn, "Checking", "2026-10-31")
        bank.finalize_statement(self.store.conn, "Checking", "2026-10-31", "0", "10")
        bank.match_transaction(self.store.conn, nov_txn, "Checking", "2026-11-30")
        bank.finalize_statement(self.store.conn, "Checking", "2026-11-30", "10", "8")
        with self.assertRaises(bank.BankReviewError):
            bank.cancel_statement(self.store.conn, "Checking", "2026-10-31")
        self.assertEqual(bank.match_statuses(self.store.conn)[oct_txn], "RECONCILED")
        bank.cancel_statement(self.store.conn, "Checking", "2026-11-30")
        bank.cancel_statement(self.store.conn, "Checking", "2026-10-31")
        self.assertEqual(bank.match_statuses(self.store.conn)[nov_txn], "CLEARED")

    def test_cancel_rejects_corrupt_membership_and_does_not_lose_statement(self):
        first = self.add("income", "10")
        second = self.add("expense", "10")
        for txn in (first, second):
            bank.match_transaction(self.store.conn, txn, "Checking", "2026-10-31")
        bank.finalize_statement(self.store.conn, "Checking", "2026-10-31", "5", "5")
        # Removing a zero-net pair would pass a movement-only integrity check.
        self.store.conn.execute("DELETE FROM bank_matches WHERE transaction_id=?", (first,))
        self.store.conn.execute("DELETE FROM bank_matches WHERE transaction_id=?", (second,))
        self.store.conn.commit()
        with self.assertRaises(bank.BankReviewError):
            bank.cancel_statement(self.store.conn, "Checking", "2026-10-31")
        self.assertEqual(self.store.conn.execute(
            "SELECT COUNT(*) FROM bank_reconciliations").fetchone()[0], 1)
        self.assertEqual(self.store.conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='BANK_RECONCILE_CANCEL'"
        ).fetchone()[0], 0)

    def test_cancel_rejects_legacy_missing_evidence_and_corrupt_snapshot(self):
        txn = self.add("income", "1")
        bank.match_transaction(self.store.conn, txn, "A", "2026-10-31")
        bank.finalize_statement(self.store.conn, "A", "2026-10-31", "0", "1")
        self.store.conn.execute(
            "UPDATE audit_log SET detail='not json' "
            "WHERE action='BANK_RECONCILE_MEMBERS'"
        )
        self.store.conn.commit()
        with self.assertRaises(bank.BankReviewError):
            bank.cancel_statement(self.store.conn, "A", "2026-10-31")
        self.store.conn.execute(
            "DELETE FROM audit_log WHERE action='BANK_RECONCILE_MEMBERS'"
        )
        self.store.conn.commit()
        with self.assertRaises(bank.BankReviewError):
            bank.cancel_statement(self.store.conn, "A", "2026-10-31")
        self.assertEqual(bank.match_statuses(self.store.conn)[txn], "RECONCILED")



if __name__ == "__main__":
    unittest.main()
