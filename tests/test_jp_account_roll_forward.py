"""Regression fixtures: journal -> ledger -> trial -> P/L -> B/S -> roll-forward."""
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


core = load("jp_rollforward_core", "core.py")
reporting = load("jp_rollforward_reporting", "reporting.py")


class RollForwardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "books.sqlite3"
        self.store = core.Store(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def post(self, day, name, *lines):
        return self.store.post(day, name, list(lines))

    def sample(self):
        self.post("2026-09-30", "元入金", ("1100", 5000, 0), ("3000", 0, 5000))
        sale = self.post("2026-10-01", "売上", ("1100", 10000, 0), ("4000", 0, 10000))
        self.post("2026-10-02", "家賃", ("5200", 3000, 0), ("1100", 0, 3000))
        self.post("2026-10-03", "分割支払", ("1000", 2000, 0), ("5500", 1000, 0), ("1100", 0, 3000))
        return sale

    def test_opening_movements_closing_and_source_drilldown(self):
        sale = self.sample()
        r = reporting.account_roll_forward(self.store, "1100", "2026-10-01", "2026-10-31")
        self.assertEqual(r["opening_balance_yen"], 5000)
        self.assertEqual(r["period_debits_yen"], 10000)
        self.assertEqual(r["period_credits_yen"], 6000)
        self.assertEqual(r["closing_balance_yen"], 9000)
        self.assertTrue(r["reconciles"])
        self.assertEqual([x["running_balance_yen"] for x in r["movements"]], [15000, 12000, 9000])
        self.assertEqual(r["movements"][0]["entry_id"], sale)
        self.assertTrue(all(x["line_id"] > 0 for x in r["movements"]))
        self.assertEqual(sum(x["debit_yen"] - x["credit_yen"] for x in self.store.ledger("1100")), 9000)

    def test_period_totals_and_balance_sheet_reconcile(self):
        self.sample()
        r = reporting.period_roll_forward(self.store, "2026-10-01", "2026-10-31")
        self.assertTrue(r["journal_balanced"])
        self.assertTrue(r["all_accounts_reconcile"])
        self.assertEqual((r["period_debits_yen"], r["period_credits_yen"]), (16000, 16000))
        self.assertEqual(r["period_net_income_yen"], 6000)
        self.assertEqual(self.store.pnl()["利益"], 6000)
        self.assertEqual(self.store.bs()["資産"], self.store.bs()["負債純資産合計"])
        self.assertTrue(self.store.balance_check()["balanced"])

    def test_reversing_entry_changes_reports_consistently(self):
        self.sample()
        self.post("2026-10-04", "売上訂正", ("4000", 1000, 0), ("1100", 0, 1000))
        r = reporting.period_roll_forward(self.store, "2026-10-01", "2026-10-31")
        self.assertEqual(r["period_net_income_yen"], 5000)
        self.assertEqual(self.store.pnl()["利益"], 5000)
        self.assertEqual(self.store.bs()["資産"], self.store.bs()["負債純資産合計"])
        self.assertEqual(reporting.account_roll_forward(self.store, "1100", "2026-10-01", "2026-10-31")["closing_balance_yen"], 8000)

    def test_contra_asset_negative_balance_is_preserved(self):
        self.post("2026-10-01", "減価償却の帳簿仕訳", ("5600", 400, 0), ("1590", 0, 400))
        r = reporting.account_roll_forward(self.store, "1590", "2026-10-01", "2026-10-31")
        self.assertEqual(r["closing_balance_yen"], -400)
        self.assertEqual(self.store.bs()["資産"], -400)
        self.assertEqual(self.store.pnl()["利益"], -400)

    def test_restart_is_deterministic(self):
        self.sample()
        first = reporting.period_roll_forward(self.store, "2026-10-01", "2026-10-31")
        self.store.close()
        self.store = core.Store(self.path)
        second = reporting.period_roll_forward(self.store, "2026-10-01", "2026-10-31")
        self.assertEqual(first, second)

    def test_empty_period_and_read_only(self):
        self.sample()
        count = self.store.conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        r = reporting.period_roll_forward(self.store, "2026-11-01", "2026-11-30")
        self.assertEqual(r["period_debits_yen"], 0)
        self.assertEqual(r["period_net_income_yen"], 0)
        self.assertEqual(count, self.store.conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])

    def test_invalid_period_and_unknown_account_rejected(self):
        for a, b in (("2026-10-31", "2026-10-01"), ("2026-02-30", "2026-03-01"), ("20261001", "2026-10-31")):
            with self.subTest(start=a):
                with self.assertRaises(reporting.ReportError):
                    reporting.period_roll_forward(self.store, a, b)
        with self.assertRaises(reporting.ReportError):
            reporting.account_roll_forward(self.store, "999999", "2026-10-01", "2026-10-31")


if __name__ == "__main__":
    unittest.main()
