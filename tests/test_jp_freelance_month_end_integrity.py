"""Month-end accounting integrity and human-first entrypoint regression."""
import ast
import csv
import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PRODUCT=ROOT/"products"/"jp-freelance-ledger"

def load(name,filename):
    spec=importlib.util.spec_from_file_location(name,PRODUCT/filename)
    mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod
    spec.loader.exec_module(mod)
    return mod

core=load("jp_freelance_monthend_integrity_core","core.py")
close=load("jp_freelance_monthend_integrity_export","monthly_close.py")

class MonthEndIntegrity(unittest.TestCase):
    def test_full_month_not_limited_by_ui_preview(self):
        with tempfile.TemporaryDirectory() as td:
            store=core.Store(Path(td)/"book.db")
            with store.conn:
                store.conn.executemany(
                    "INSERT INTO transactions(txn_date,kind,amount_yen,category) VALUES(?,?,?,?)",
                    [("2026-11-01","収入",1,"売上高")]*10005
                )
            result=close.export_month_end_package(store,2026,11,Path(td)/"out")
            payload=json.loads(Path(result["json"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["transaction_count"],10005)
            self.assertEqual(payload["summary"]["収入"],10005)
            with Path(result["csv"]).open(encoding="utf-8-sig",newline="") as f:
                self.assertEqual(sum(1 for _ in csv.reader(f)),10006)
            store.close()

    def test_kind_separated_and_unlimited_pending_receipts(self):
        with tempfile.TemporaryDirectory() as td:
            store=core.Store(Path(td)/"book.db")
            store.add("2026-11-01","収入","100","その他")
            store.add("2026-11-01","経費","30","その他",memo="<script>alert(1)</script>")
            with store.conn:
                store.conn.executemany(
                    "INSERT INTO receipt_queue(file_path) VALUES(?)",
                    [(f"/review/receipt-{i}.pdf",) for i in range(1001)]
                )
            result=close.export_month_end_package(store,2026,11,Path(td)/"out")
            data=json.loads(Path(result["json"]).read_text(encoding="utf-8"))
            self.assertEqual(data["categories"]["収入 / その他"],100)
            self.assertEqual(data["categories"]["経費 / その他"],30)
            self.assertEqual(data["pending_receipt_count"],1001)
            self.assertEqual(len(data["pending_receipts"]),1001)
            html=Path(result["html"]).read_text(encoding="utf-8")
            self.assertIn("&lt;script&gt;",html)
            self.assertNotIn("<script>",html)
            store.close()

    def test_invalid_month_rejected_before_creating_files(self):
        with tempfile.TemporaryDirectory() as td:
            store=core.Store(Path(td)/"book.db")
            dest=Path(td)/"bad"
            with self.assertRaises(ValueError):
                close.export_month_end_package(store,2026,13,dest)
            self.assertFalse(dest.exists())
            store.close()

    def test_month_end_action_is_reachable_from_main_menu(self):
        source=(PRODUCT/"main.py").read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn('command=self.month_end_pack',source)
        self.assertIn("月末の帳簿パックを作成",source)

if __name__=="__main__":
    unittest.main()
