"""Integration: real JP Store enqueue/status writes, month-end replay and novice report."""
import ast
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / "products" / "jp-bookkeeping-desk"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core = load("jp_receipt_integrated_core", "core.py")
monthly = load("jp_receipt_integrated_monthly", "monthly_close.py")


class ReceiptHistoryIntegrationTests(unittest.TestCase):
    def test_store_restart_month_end_replay_and_manual_status(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "new.sqlite"
            s = core.Store(db)
            try:
                self.assertEqual(s.enqueue_receipts(["jan-one.pdf", "jan-two.png"],
                                                    at="2026-01-10T09:00:00+09:00"), 2)
                self.assertEqual(s.enqueue_receipts(["jan-one.pdf"],
                                                    at="2026-01-11T09:00:00+09:00"), 0)
                first = s.receipts()[0]["id"]
                self.assertEqual(s.receipt_month_end(2026, 1)["unprocessed_receipts_as_of_month_end"], 2)
                self.assertTrue(s.set_receipt_status(first, "POSTED",
                                                     at="2026-02-01T00:00:01+09:00"))
                self.assertFalse(s.set_receipt_status(first, "POSTED",
                                                      at="2026-02-02T09:00:00+09:00"))
                self.assertEqual(s.receipt_month_end(2026, 1)["unprocessed_receipts_as_of_month_end"], 2)
                self.assertEqual(s.receipt_month_end(2026, 2)["unprocessed_receipts_as_of_month_end"], 1)
                jan = monthly.export_month_end_package(s, 2026, 1, Path(td) / "jan")
                data = json.loads(Path(jan["json"]).read_text(encoding="utf-8"))
                self.assertEqual(data["unprocessed_receipts"], 1)
                self.assertEqual(data["unprocessed_receipts_as_of_month_end"], 2)
                self.assertEqual(data["receipt_history_status"], "VERIFIED_HISTORY_ONLY")
                self.assertFalse(data["tax_filing_or_deduction_approved"])
                html = Path(jan["html"]).read_text(encoding="utf-8")
                self.assertIn("現在の未処理証憑 1件", html)
                self.assertIn("月末時点の未処理証憑：2件", html)
                self.assertIn("現在の未処理証憑の詳細を見る", html)
                self.assertIn("jan-two.png", html)
                self.assertNotIn("jan-one.pdf</td><td>未処理", html)
            finally:
                s.close()
            s = core.Store(db)
            try:
                first = s.receipts()[0]["id"]
                self.assertEqual(s.receipt_month_end(2026, 2)["unprocessed_receipts_as_of_month_end"], 1)
                self.assertTrue(s.set_receipt_status(first, "PENDING",
                                                     at="2026-03-01T09:00:00+09:00"))
                self.assertEqual(s.enqueue_receipts(["future.png"],
                                                    at="2026-04-01T09:00:00+09:00"), 1)
                self.assertEqual(s.receipt_month_end(2026, 1)["unprocessed_receipts_as_of_month_end"], 2)
                self.assertEqual(s.receipt_month_end(2026, 2)["unprocessed_receipts_as_of_month_end"], 1)
                self.assertEqual(s.receipt_month_end(2026, 3)["unprocessed_receipts_as_of_month_end"], 2)
                self.assertEqual(s.receipt_month_end(2026, 4)["unprocessed_receipts_as_of_month_end"], 3)
                self.assertEqual(s.receipt_month_end(2026, 2), s.receipt_month_end(2026, 2))
            finally:
                s.close()

    def test_legacy_database_never_backfills_or_claims_as_of(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "legacy.sqlite"
            conn = sqlite3.connect(db)
            conn.execute("""CREATE TABLE receipt_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'PENDING',
                suggested_entry TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            conn.execute("INSERT INTO receipt_queue(file_path,status) VALUES('old.pdf','POSTED')")
            conn.commit()
            conn.close()
            s = core.Store(db)
            try:
                self.assertEqual(s.enqueue_receipts(["new.pdf"], at="2026-01-01T00:00:00Z"), 1)
                result = s.receipt_month_end(2026, 1)
                self.assertIsNone(result["unprocessed_receipts_as_of_month_end"])
                self.assertEqual(result["reason"], "LEGACY_HISTORY_UNKNOWN")
                report = monthly.export_month_end_package(s, 2026, 1, Path(td) / "legacy-out")
                data = json.loads(Path(report["json"]).read_text(encoding="utf-8"))
                self.assertIsNone(data["unprocessed_receipts_as_of_month_end"])
                self.assertEqual(data["receipt_history_status"], "HOLD")
                self.assertIn("算出不可（履歴不足・要確認）",
                              Path(report["html"]).read_text(encoding="utf-8"))
                with self.assertRaises(core.BookError):
                    s.set_receipt_status(s.receipts()[0]["id"], "PENDING",
                                         at="2026-02-01T00:00:00Z")
            finally:
                s.close()

    def test_bypassed_status_and_missing_source_hold(self):
        with tempfile.TemporaryDirectory() as td:
            s = core.Store(Path(td) / "x.sqlite")
            try:
                s.enqueue_receipts(["one.pdf"], at="2026-01-01T00:00:00Z")
                rid = s.receipts()[0]["id"]
                s.conn.execute("UPDATE receipt_queue SET status='POSTED' WHERE id=?", (rid,))
                s.conn.commit()
                self.assertEqual(s.receipt_month_end(2026, 1)["reason"], "UNLOGGED_STATUS_CHANGE")
                with self.assertRaises(core.BookError):
                    s.set_receipt_status(rid, "PENDING", at="2026-02-01T00:00:00Z")
                s.conn.execute("DELETE FROM receipt_queue WHERE id=?", (rid,))
                s.conn.commit()
                self.assertEqual(s.receipt_month_end(2026, 1)["reason"],
                                 "SOURCE_RECEIPT_MISSING_OR_CHANGED")
            finally:
                s.close()

    def test_novice_gui_source_is_syntactically_valid(self):
        ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("未処理証憑の一覧・処理状態を見る", source)
        self.assertIn("self.s.set_receipt_status", source)


if __name__ == "__main__":
    unittest.main()
