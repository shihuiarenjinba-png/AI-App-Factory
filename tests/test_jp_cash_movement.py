"""Cash movement fixtures: transfers, split entries, reversals, dates and restart."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "products" / "jp-bookkeeping-desk"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core = load("jp_cash_core", "core.py")
cash = load("jp_cash_movement", "cash_movement.py")


class CashMovementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.store = core.Store(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def post(self, day, label, *lines):
        return self.store.post(day, label, list(lines))

    def report(self, start="2026-10-01", end="2026-10-31"):
        return cash.cash_movement_report(self.store, start, end)

    def sample(self):
        self.post("2026-09-30", "元入金", ("1100", 10000, 0), ("3000", 0, 10000))
        sale = self.post("2026-10-01", "売上", ("1100", 5000, 0), ("4000", 0, 5000))
        self.post("2026-10-02", "預金から現金へ", ("1000", 2000, 0), ("1100", 0, 2000))
        self.post("2026-10-03", "現金で備品", ("5500", 700, 0), ("1000", 0, 700))
        self.post("2026-10-04", "返品返金", ("1100", 100, 0), ("5500", 0, 100))
        return sale

    def test_opening_receipts_payments_and_journal_ledger_balance(self):
        sale = self.sample()
        result = self.report()
        self.assertEqual(result["opening_yen"], 10000)
        self.assertEqual(result["receipts_yen"], 5100)
        self.assertEqual(result["payments_yen"], 700)
        self.assertEqual(result["closing_yen"], 14400)
        self.assertEqual(result["net_change_yen"], 4400)
        self.assertTrue(result["reconciles"])
        self.assertTrue(result["journal_balanced"])
        self.assertEqual(result["movements"][0]["entry_id"], sale)
        self.assertEqual(result["movements"][1]["net_change_yen"], 0)
        self.assertEqual(self.store.pnl()["利益"], 4400)
        self.assertEqual(self.store.bs()["資産"], self.store.bs()["負債純資産合計"])
        self.assertFalse(result["taxable_income_claim"])
        self.assertFalse(result["statutory_cash_flow_statement_claim"])

    def test_split_journal_counted_once_and_zero_transfer_not_income(self):
        self.post("2026-10-01", "分割売上", ("1100", 1200, 0), ("1000", 300, 0), ("4000", 0, 1500))
        self.post("2026-10-02", "預金振替", ("1000", 500, 0), ("1100", 0, 500))
        result = self.report()
        self.assertEqual((result["receipts_yen"], result["payments_yen"]), (1500, 0))
        self.assertEqual(len(result["movements"]), 2)
        self.assertEqual(result["movements"][1]["kind"], "口座間移動等（増減なし）")
        self.assertEqual(result["closing_yen"], 1500)
        self.assertEqual(self.store.pnl()["利益"], 1500)

    def test_read_only_empty_period_and_restart(self):
        self.sample()
        audit_before = self.store.conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        first = self.report()
        empty = self.report("2026-11-01", "2026-11-30")
        self.assertEqual(empty["receipts_yen"], 0)
        self.assertEqual(empty["closing_yen"], 14400)
        self.assertEqual(audit_before, self.store.conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])
        self.store.close()
        self.store = core.Store(self.path)
        self.assertEqual(first, self.report())

    def test_selected_account_scope_and_negative_balance_preserved(self):
        self.post("2026-10-01", "預金から現金", ("1000", 500, 0), ("1100", 0, 500))
        cash_only = cash.cash_movement_report(self.store, "2026-10-01", "2026-10-31", ["1000"])
        bank_only = cash.cash_movement_report(self.store, "2026-10-01", "2026-10-31", ["1100"])
        self.assertEqual(cash_only["closing_yen"], 500)
        self.assertEqual(bank_only["closing_yen"], -500)
        self.assertEqual(self.report()["net_change_yen"], 0)

    def test_invalid_inputs_and_nonasset_account_rejected(self):
        for a, b in [("2026-10-31", "2026-10-01"), ("2026-02-30", "2026-03-01"), ("20261001", "2026-10-31")]:
            with self.subTest(a=a), self.assertRaises(cash.CashMovementError):
                self.report(a, b)
        for codes in [[], ["1000", "1000"], ["4000"], ["9999"]]:
            with self.subTest(codes=codes), self.assertRaises(cash.CashMovementError):
                cash.cash_movement_report(self.store, "2026-10-01", "2026-10-31", codes)


if __name__ == "__main__":
    unittest.main()
