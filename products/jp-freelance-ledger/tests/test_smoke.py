"""Headless smoke contract for the Japan-only freelance cashbook."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))
import core
from reconciliation import preview, confirm, status


class Smoke(unittest.TestCase):
    def test_product_contract_is_japan_only(self):
        manifest = json.loads((PRODUCT / "manifest.json").read_text(encoding="utf-8"))
        market = json.loads((PRODUCT / "market-scope.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["slug"], manifest["kind"], manifest["entry"]), ("jp-freelance-ledger", "app", "main.py"))
        self.assertEqual((market["store_markets"], market["currency"], market["cross_market_sale"]), (["JP"], "JPY", False))

    def test_real_store_save_reopen_and_review(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cashbook.sqlite3"
            store = core.Store(path)
            store.add("2026-10-01", "収入", "15000", "売上高", memo="制作報酬")
            store.add("2026-10-12", "経費", "5000", "通信費", memo="通信")
            self.assertEqual(store.monthly(2026, 10)["差引"], 10000)
            x = preview(store.conn, "2026-10", 2000, 12000)
            self.assertEqual(x["difference_yen"], 0)
            self.assertTrue(confirm(store.conn, "2026-10", 2000, 12000, x["source_sha256"])["recorded"])
            store.close()
            reopened = core.Store(path)
            self.assertEqual(len(reopened.rows()), 2)
            self.assertEqual(status(reopened.conn, "2026-10"), "照合済み")
            reopened.close()


if __name__ == "__main__": unittest.main()
