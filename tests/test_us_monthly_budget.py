"""Functional fixtures for monthly budget review, not a tax-budget engine."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1] / "products" / "us-bookkeeping-desk"
sys.path.insert(0, str(PRODUCT))
from core import BookError, Store
from budget import MonthlyBudgets


class BudgetTests(unittest.TestCase):
    def test_monthly_split_and_journal_report_invariants(self):
        with tempfile.TemporaryDirectory() as d:
            s = Store(Path(d) / "books.sqlite3")
            b = MonthlyBudgets(s)
            b.set_budget("2026-11", "5200", "100.00")
            b.set_budget("2026-11", "5300", "40.00")
            # One balanced split transaction with two expense accounts.
            s.post("2026-11-01", "rent and utilities",
                   [("5200", "75.20", ""), ("5300", "10.00", ""),
                    ("1100", "", "85.20")])
            s.post("2026-11-15", "rent refund",
                   [("1100", "5.20", ""), ("5200", "", "5.20")])
            s.post("2026-10-31", "prior period rent",
                   [("5200", "99.00", ""), ("1100", "", "99.00")])
            s.post("2026-12-01", "next period rent",
                   [("5200", "50.00", ""), ("1100", "", "50.00")])
            report = b.report("2026-11")
            by_code = {r["code"]: r for r in report["rows"]}
            self.assertEqual(by_code["5200"]["actual_cents"], 7000)
            self.assertEqual(by_code["5200"]["remaining_cents"], 3000)
            self.assertEqual(by_code["5300"]["actual_cents"], 1000)
            self.assertEqual(report["actual_cents"], 8000)
            self.assertEqual(report["planned_cents"], 14000)
            self.assertEqual(report["unbudgeted_actual_cents"], 0)
            self.assertTrue(s.balance_check()["balanced"])
            self.assertEqual(s.bs()["assets"], s.bs()["liabilities_and_equity"])
            self.assertEqual(s.pnl()["expense"], 22900)
            self.assertEqual(sum(r["debit"]-r["credit"] for r in s.trial()), 0)
            self.assertTrue(report["book_only"])
            self.assertFalse(report["tax_decision"])
            s.close()

    def test_unbudgeted_expense_and_persistence_without_journal_changes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "books.sqlite3"
            s = Store(path)
            b = MonthlyBudgets(s)
            s.post("2026-11-30", "software", [("5280", "19.99", ""), ("1100", "", "19.99")])
            original = list(s.journal())
            b.set_budget("2026-11", "5200", "50.00")
            b.set_budget("2026-11", "5200", "55.00")  # update, never duplicate
            self.assertEqual(s.journal(), original)
            self.assertEqual(b.report("2026-11")["unbudgeted_actual_cents"], 1999)
            s.close()
            s = Store(path)
            b = MonthlyBudgets(s)
            report = b.report("2026-11")
            self.assertEqual(report["planned_cents"], 5500)
            self.assertEqual(report["actual_cents"], 1999)
            self.assertEqual(len([r for r in report["rows"] if r["code"] == "5200"]), 1)
            self.assertEqual(s.journal(), original)
            s.close()

    def test_bad_input_and_closed_month_boundaries(self):
        with tempfile.TemporaryDirectory() as d:
            s = Store(Path(d) / "books.sqlite3")
            b = MonthlyBudgets(s)
            for month in ("2026-00", "2026-13", "2026-1", "bad", "2026-11-01"):
                with self.subTest(month=month), self.assertRaises(BookError):
                    b.report(month)
            for code, value in (("9999", "20"), ("1000", "20"), ("5200", "-1"),
                                ("5200", "NaN"), ("5200", "Infinity")):
                with self.subTest(code=code, value=value), self.assertRaises(BookError):
                    b.set_budget("2026-11", code, value)
            s.post("2026-12-31", "year end", [("5300", "1.00", ""), ("1100", "", "1.00")])
            self.assertEqual(b.report("2026-12")["actual_cents"], 100)
            self.assertEqual(b.report("2027-01")["actual_cents"], 0)
            s.close()


if __name__ == "__main__":
    unittest.main()
