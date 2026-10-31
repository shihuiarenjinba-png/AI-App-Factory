"""US book roll-forward fixtures: journal -> ledger -> trial -> P&L/B/S."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "products" / "us-bookkeeping-desk"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core = load("us_rollforward_core", "core.py")
roll = load("us_rollforward_module", "rollforward.py")


class AccountRollforwardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "books.sqlite3"
        self.s = core.Store(self.path, "accrual")
        self.s.post("2026-09-30", "Opening capital", [("1100", "2000.00", ""), ("3000", "", "2000.00")])
        self.s.post("2026-10-02", "Invoice", [("1200", "1200.00", ""), ("4000", "", "1200.00")])
        self.s.post("2026-10-03", "Partial receipt", [("1100", "500.00", ""), ("1200", "", "500.00")])
        self.s.post("2026-10-04", "Rent", [("5200", "200.00", ""), ("1100", "", "200.00")])
        self.s.post("2026-10-05", "Split expense", [("5500", "100.00", ""), ("5400", "50.00", ""), ("1100", "", "150.00")])
        self.s.post("2026-10-10", "Rent reversal", [("1100", "200.00", ""), ("5200", "", "200.00")])

    def tearDown(self):
        self.s.close()
        self.tmp.cleanup()

    def test_rollforward_balances_and_drills_to_source(self):
        before = (self.s.journal(), self.s.trial(), self.s.pnl(), self.s.bs(), self.s.balance_check())
        report = roll.account_rollforward(self.s, "2026-10-01", "2026-10-31")
        self.assertTrue(report["balanced"])
        self.assertTrue(report["book_only"])
        self.assertFalse(report["tax_decision"])
        self.assertEqual(report["accounting_method"], "accrual")
        by_code = {r["code"]: r for r in report["accounts"]}
        bank = by_code["1100"]
        self.assertEqual(bank["opening_debit_minus_credit_cents"], 200000)
        self.assertEqual(bank["period_debit_cents"], 70000)
        self.assertEqual(bank["period_credit_cents"], 35000)
        self.assertEqual(bank["closing_debit_minus_credit_cents"], 235000)
        self.assertEqual(by_code["1200"]["closing_debit_minus_credit_cents"], 70000)
        self.assertEqual(by_code["5200"]["closing_debit_minus_credit_cents"], 0)
        self.assertEqual(by_code["4000"]["closing_normal_cents"], 120000)
        self.assertEqual(by_code["3000"]["opening_normal_cents"], 200000)
        self.assertEqual(report["totals"]["opening_debit_minus_credit_cents"], 0)
        self.assertEqual(report["totals"]["closing_debit_minus_credit_cents"], 0)
        self.assertEqual(report["totals"]["period_debit_cents"], report["totals"]["period_credit_cents"])
        drill = roll.account_drilldown(self.s, "1100", "2026-10-01", "2026-10-31")
        self.assertEqual(len(drill["lines"]), 4)
        self.assertEqual(drill["lines"][-1]["running_debit_minus_credit_cents"], 235000)
        self.assertEqual(sum(x["debit_cents"] - x["credit_cents"] for x in drill["lines"]), 35000)
        self.assertEqual(self.s.pnl()["net_income"], 105000)
        self.assertEqual(self.s.bs()["assets"], self.s.bs()["liabilities_and_equity"])
        self.assertEqual(before, (self.s.journal(), self.s.trial(), self.s.pnl(), self.s.bs(), self.s.balance_check()))
        self.s.close()
        self.s = core.Store(self.path)
        self.assertEqual(roll.account_rollforward(self.s, "2026-10-01", "2026-10-31"), report)

    def test_boundaries_filters_and_invalid_inputs(self):
        september = roll.account_rollforward(self.s, "2026-09-01", "2026-09-30")
        self.assertTrue(september["balanced"])
        self.assertEqual(september["totals"]["period_debit_cents"], 200000)
        filtered = roll.account_rollforward(self.s, "2026-10-01", "2026-10-31", ["1100", "1200"])
        self.assertIsNone(filtered["balanced"])
        self.assertFalse(filtered["complete_chart"])
        self.assertEqual(len(filtered["accounts"]), 2)
        for start, end in [("2026-11-01", "2026-10-01"), ("2026-02-30", "2026-10-01"),
                           ("20261001", "2026-10-31"), (None, "2026-10-31")]:
            with self.subTest(start=start), self.assertRaises(roll.RollforwardError):
                roll.account_rollforward(self.s, start, end)
        for codes in (["1100", "1100"], ["9999"], [], "1100", [" 1100"]):
            with self.subTest(codes=codes), self.assertRaises(roll.RollforwardError):
                roll.account_rollforward(self.s, "2026-10-01", "2026-10-31", codes)
        with self.assertRaises(roll.RollforwardError):
            roll.account_drilldown(self.s, "9999", "2026-10-01", "2026-10-31")


if __name__ == "__main__":
    unittest.main()
