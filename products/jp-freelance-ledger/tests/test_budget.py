"""Budget-vs-actual fixtures against the real local SQLite cashbook."""
import tempfile
import unittest
from pathlib import Path

from budgets import BudgetError, monthly_budget_report, set_budget
from core import Store


class MonthlyBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "cashbook.sqlite3"
        self.store = Store(self.path)
        self.store.add("2026-10-02", "収入", "15000", "売上高", memo="制作報酬")
        self.store.add("2026-10-12", "経費", "5000", "通信費", memo="通信")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_monthly_budget_matches_cashbook_net(self):
        set_budget(self.store.conn, "2026-10", "収入", "売上高", 20000)
        set_budget(self.store.conn, "2026-10", "経費", "通信費", 4000)
        r = monthly_budget_report(self.store.conn, "2026-10")
        self.assertEqual((r["income_yen"], r["expense_yen"], r["net_yen"]), (15000, 5000, 10000))
        self.assertEqual(r["net_yen"], self.store.monthly(2026, 10)["差引"])
        by_name = {x["category"]: x for x in r["rows"]}
        self.assertEqual(by_name["売上高"]["difference_yen"], -5000)
        self.assertEqual(by_name["通信費"]["difference_yen"], 1000)
        self.assertEqual(r["unbudgeted_categories"], 0)

    def test_unbudgeted_is_not_zero_budget(self):
        set_budget(self.store.conn, "2026-10", "経費", "通信費", 0)
        r = monthly_budget_report(self.store.conn, "2026-10")
        by_name = {x["category"]: x for x in r["rows"]}
        self.assertEqual((by_name["通信費"]["budget_yen"], by_name["通信費"]["difference_yen"]), (0, 5000))
        self.assertIsNone(by_name["売上高"]["budget_yen"])
        self.assertIsNone(by_name["売上高"]["difference_yen"])
        self.assertEqual(r["unbudgeted_categories"], 1)

    def test_idempotent_save_and_audit(self):
        self.assertTrue(set_budget(self.store.conn, "2026-10", "経費", "通信費", 6000)["saved"])
        self.assertFalse(set_budget(self.store.conn, "2026-10", "経費", "通信費", 6000)["saved"])
        count = self.store.conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='MONTH_BUDGET_SET'").fetchone()[0]
        self.assertEqual(count, 1)

    def test_budget_update_is_audited_without_posting_transactions(self):
        before = len(self.store.rows())
        set_budget(self.store.conn, "2026-10", "経費", "通信費", 6000)
        set_budget(self.store.conn, "2026-10", "経費", "通信費", 4000)
        self.assertEqual(len(self.store.rows()), before)
        self.assertEqual(self.store.conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='MONTH_BUDGET_SET'").fetchone()[0], 2)
        self.assertEqual(next(x for x in monthly_budget_report(
            self.store.conn, "2026-10")["rows"] if x["category"] == "通信費")["difference_yen"], 1000)

    def test_invalid_month_kind_category_and_money_fail_closed(self):
        for month in ("2026-00", "2026-13", "2026-10 OR 1=1", "0000-10"):
            with self.subTest(month=month), self.assertRaises(BudgetError):
                monthly_budget_report(self.store.conn, month)
        for amount in ("-1", "1.2", "1,000", "nan", True, "10000000000000"):
            with self.subTest(amount=amount), self.assertRaises(BudgetError):
                set_budget(self.store.conn, "2026-10", "経費", "通信費", amount)
        for kind, category in (("収入", "通信費"), ("経費", "売上高"), ("経費", "架空科目")):
            with self.subTest(kind=kind, category=category), self.assertRaises(BudgetError):
                set_budget(self.store.conn, "2026-10", kind, category, 10)
        self.assertEqual(self.store.conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='MONTH_BUDGET_SET'").fetchone()[0], 0)

    def test_corrupt_transaction_rejected_without_budget_write(self):
        self.store.conn.execute("PRAGMA ignore_check_constraints=ON")
        self.store.conn.execute("UPDATE transactions SET amount_yen=-1 WHERE category='通信費'")
        self.store.conn.commit()
        self.store.conn.execute("PRAGMA ignore_check_constraints=OFF")
        with self.assertRaises(BudgetError):
            monthly_budget_report(self.store.conn, "2026-10")
        self.assertEqual(self.store.conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='MONTH_BUDGET_SET'").fetchone()[0], 0)

    def test_month_boundaries_and_source_change(self):
        before = monthly_budget_report(self.store.conn, "2026-10")
        self.store.add("2026-11-01", "経費", "300", "通信費")
        self.assertEqual(monthly_budget_report(self.store.conn, "2026-10")["source_sha256"],
                         before["source_sha256"])
        self.store.add("2026-10-31", "経費", "700", "通信費")
        after = monthly_budget_report(self.store.conn, "2026-10")
        self.assertNotEqual(after["source_sha256"], before["source_sha256"])
        self.assertEqual(after["net_yen"], self.store.monthly(2026, 10)["差引"])
        self.assertEqual(after["net_yen"], 9300)

    def test_restart_persists_budget_and_audit(self):
        set_budget(self.store.conn, "2026-10", "経費", "通信費", 8000)
        self.store.close()
        self.store = Store(self.path)
        r = monthly_budget_report(self.store.conn, "2026-10")
        line = next(x for x in r["rows"] if x["category"] == "通信費")
        self.assertEqual((line["budget_yen"], line["actual_yen"], line["difference_yen"]),
                         (8000, 5000, -3000))
        self.assertEqual(self.store.conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='MONTH_BUDGET_SET'").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
