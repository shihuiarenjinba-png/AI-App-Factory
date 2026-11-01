"""January/February accounting fixture: every displayed month-end figure ties to source journal lines."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Store
import monthly_close


class MonthEndDrilldownTests(unittest.TestCase):
    def test_jan_feb_and_future_journal_drilldown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "book.sqlite3")
            try:
                jan_sale = store.post("2026-01-05", "1月売上", [("1000", "10000", ""), ("4000", "", "10000")])
                store.post("2026-01-07", "1月家賃", [("5200", "3000", ""), ("1000", "", "3000")])
                feb_sale = store.post("2026-02-05", "2月売上", [("1000", "7000", ""), ("4000", "", "7000")])
                store.post("2026-02-07", "2月家賃", [("5200", "1000", ""), ("1000", "", "1000")])
                future = store.post("2026-03-01", "未来売上", [("1000", "5000", ""), ("4000", "", "5000")])
                with patch.object(monthly_close, "_edge_path", return_value=None):
                    jan_files = monthly_close.export_month_end_package(store, 2026, 1, root / "jan")
                    feb_files = monthly_close.export_month_end_package(store, 2026, 2, root / "feb")
                jan = json.loads(Path(jan_files["json"]).read_text(encoding="utf-8"))
                feb = json.loads(Path(feb_files["json"]).read_text(encoding="utf-8"))
                self.assertEqual(jan["pnl_month"]["利益"], 7000)
                self.assertEqual(jan["balance_sheet"]["資産"], 7000)
                self.assertEqual(feb["pnl_month"]["利益"], 6000)
                self.assertEqual(feb["pnl_year_to_date"]["利益"], 13000)
                self.assertEqual(feb["balance_sheet"]["資産"], 13000)
                self.assertTrue(feb["balance_check"]["bs_balanced"])
                self.assertTrue(feb["month_balance_check"]["balanced"])
                self.assertEqual(feb["unprocessed_receipts_scope"], "CURRENT_QUEUE_ALL_DATES_NOT_HISTORICAL_AS_OF")
                sales = next(x for x in feb["account_drilldown"] if x["code"] == "4000")
                self.assertEqual(sales["month_credit"], 7000)
                self.assertEqual(sales["ytd_credit"], 17000)
                self.assertEqual(sales["as_of_credit"], 17000)
                self.assertEqual({x["entry_id"] for x in sales["source_lines"]}, {jan_sale, feb_sale})
                self.assertNotIn(future, {x["entry_id"] for a in feb["account_drilldown"] for x in a["source_lines"]})
                for account in feb["account_drilldown"]:
                    self.assertEqual(sum(x["debit"] for x in account["source_lines"]), account["as_of_debit"])
                    self.assertEqual(sum(x["credit"] for x in account["source_lines"]), account["as_of_credit"])
                html = Path(feb_files["html"]).read_text(encoding="utf-8")
                self.assertIn("この数字の根拠を見る", html)
                self.assertIn('href="#account-', html)
                self.assertIn("勘定科目ごとの元仕訳", html)
                self.assertNotIn("未来売上", html)
                self.assertFalse(feb["tax_filing_or_deduction_approved"])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
