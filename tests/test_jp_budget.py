"""JP budget fixtures: split postings, reversals, restart, validation."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1] / "products" / "jp-bookkeeping-desk"

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

core = load("jp_budget_core", PRODUCT / "core.py")
budget_module = load("jp_monthly_budget", PRODUCT / "budget.py")

class MonthlyBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "books.sqlite3"
        self.store = core.Store(self.path)
        self.budget = budget_module.MonthlyBudget(self.store)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_split_refund_and_journal_reconciliation(self):
        self.store.post("2026-10-03", "家賃・通信費", [("5200", 1000, 0), ("5300", 500, 0), ("1100", 0, 1500)])
        self.store.post("2026-10-05", "家賃返金", [("1100", 200, 0), ("5200", 0, 200)])
        self.assertTrue(self.budget.set_budget("2026-10", "5200", 1000))
        self.budget.set_budget("2026-10", "5300", 400)
        result = self.budget.report("2026-10")
        rows = {r["code"]: r for r in result["rows"]}
        self.assertEqual(rows["5200"]["actual_yen"], 800)
        self.assertEqual(rows["5200"]["remaining_yen"], 200)
        self.assertEqual(rows["5300"]["actual_yen"], 500)
        self.assertEqual(rows["5300"]["remaining_yen"], -100)
        self.assertEqual(rows["5300"]["status"], "超過")
        self.assertEqual(result["actual_total_yen"], 1300)
        self.assertEqual(result["actual_total_yen"], self.store.pnl()["費用"])
        self.assertTrue(self.store.balance_check()["balanced"])
        self.assertEqual(self.store.bs()["資産"], self.store.bs()["負債純資産合計"])
        self.assertFalse(result["taxable_income_claim"])

    def test_unbudgeted_expenses_and_month_isolation(self):
        self.store.post("2026-09-30", "前月通信費", [("5300", 600, 0), ("1100", 0, 600)])
        self.store.post("2026-10-01", "通信費", [("5300", 300, 0), ("1100", 0, 300)])
        report = self.budget.report("2026-10")
        self.assertEqual(report["actual_total_yen"], 300)
        self.assertEqual(report["unbudgeted_actual_yen"], 300)
        self.assertIsNone(report["total_remaining_yen"])
        self.assertFalse(report["all_active_expenses_budgeted"])
        self.budget.set_budget("2026-10", "5300", 0)
        self.assertEqual(self.budget.report("2026-10")["rows"][0]["status"], "超過")
        self.assertEqual(self.budget.report("2026-09")["actual_total_yen"], 600)

    def test_persistence_and_idempotent_update_audit(self):
        self.assertTrue(self.budget.set_budget("2026-11", "5200", 5000))
        before = self.store.conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='BUDGET_SET'").fetchone()[0]
        self.assertFalse(self.budget.set_budget("2026-11", "5200", "5000"))
        after = self.store.conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='BUDGET_SET'").fetchone()[0]
        self.assertEqual(before, after)
        self.assertTrue(self.budget.set_budget("2026-11", "5200", 6000))
        self.store.close()
        self.store = core.Store(self.path)
        self.budget = budget_module.MonthlyBudget(self.store)
        self.assertEqual(self.budget.report("2026-11")["rows"][0]["budget_yen"], 6000)

    def test_invalid_inputs_rejected_without_partial_write(self):
        for value in ("-1", "1.1", "NaN", "Infinity", True, "", str(2**63)):
            with self.subTest(value=value), self.assertRaises(budget_module.BudgetError):
                self.budget.set_budget("2026-10", "5200", value)
        for month in ("2026-13", "2026-00", "2026-1", "1999-12", "2101-01", "2026/10"):
            with self.subTest(month=month), self.assertRaises(budget_module.BudgetError):
                self.budget.report(month)
        for code in ("1000", "4000", "9999"):
            with self.subTest(code=code), self.assertRaises(budget_module.BudgetError):
                self.budget.set_budget("2026-10", code, 100)
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM monthly_expense_budgets").fetchone()[0], 0)

if __name__ == "__main__":
    unittest.main()
