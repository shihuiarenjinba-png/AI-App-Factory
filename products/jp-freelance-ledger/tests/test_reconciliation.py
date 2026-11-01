import sqlite3
import unittest
from reconciliation import ReconciliationError, preview, confirm, status


class MonthlyBalanceCheckTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript("""CREATE TABLE transactions (
            id INTEGER PRIMARY KEY, txn_date TEXT, kind TEXT, amount_yen INTEGER,
            category TEXT, counterparty TEXT, document_type TEXT, document_path TEXT, memo TEXT);
            CREATE TABLE audit_log (id INTEGER PRIMARY KEY,action TEXT,entity_id INTEGER,detail TEXT);
            INSERT INTO transactions VALUES(1,'2026-10-01','収入',15000,'売上高','','','','');
            INSERT INTO transactions VALUES(2,'2026-10-12','経費',5000,'通信費','','','','');""")

    def tearDown(self):
        self.conn.close()

    def test_preview_is_read_only_and_balances(self):
        x = preview(self.conn, "2026-10", 2000, 12000)
        self.assertEqual((x["income_yen"], x["expense_yen"], x["calculated_yen"], x["difference_yen"]), (15000, 5000, 12000, 0))
        self.assertEqual(status(self.conn, "2026-10"), "未照合")

    def test_confirm_is_idempotent_and_audited(self):
        x = preview(self.conn, "2026-10", 2000, 12000)
        self.assertTrue(confirm(self.conn, "2026-10", 2000, 12000, x["source_sha256"])["recorded"])
        self.assertFalse(confirm(self.conn, "2026-10", 2000, 12000, x["source_sha256"])["recorded"])
        self.assertEqual(status(self.conn, "2026-10"), "照合済み")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0], 1)

    def test_difference_refused_without_write(self):
        x = preview(self.conn, "2026-10", 2000, 13000)
        with self.assertRaises(ReconciliationError):
            confirm(self.conn, "2026-10", 2000, 13000, x["source_sha256"])
        self.assertEqual(status(self.conn, "2026-10"), "未照合")

    def test_mutation_invalidates_preview_and_previous_check(self):
        x = preview(self.conn, "2026-10", 2000, 12000)
        confirm(self.conn, "2026-10", 2000, 12000, x["source_sha256"])
        self.conn.execute("INSERT INTO transactions VALUES(3,'2026-10-30','経費',1000,'消耗品費','','','','')")
        self.assertEqual(status(self.conn, "2026-10"), "再確認が必要")
        with self.assertRaises(ReconciliationError):
            confirm(self.conn, "2026-10", 2000, 11000, x["source_sha256"])

    def test_invalid_month_and_amount(self):
        for month in ["2026-00", "2026-13", "2026-10 OR 1=1"]:
            with self.assertRaises(ReconciliationError): preview(self.conn, month, 0, 0)
        for amount in ["1,000", "1.2", "nan", True, "999999999999999999"]:
            with self.assertRaises(ReconciliationError): preview(self.conn, "2026-10", amount, 0)

    def test_empty_month_and_cross_month_exclusion(self):
        x = preview(self.conn, "2026-11", -100, -100)
        self.assertEqual((x["transaction_count"], x["difference_yen"]), (0, 0))


if __name__ == "__main__": unittest.main()
