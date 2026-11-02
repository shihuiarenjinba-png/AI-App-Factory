"""Historical receipt count fixtures: Jan/Feb, future, replay, legacy HOLD."""
import importlib.util
from pathlib import Path
import sqlite3
import unittest

MODULE = (Path(__file__).resolve().parents[1] / "products" /
          "jp-bookkeeping-desk" / "receipt_event_history.py")
spec = importlib.util.spec_from_file_location("jp_receipt_event_history", MODULE)
history_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history_module)
ReceiptHistory = history_module.ReceiptHistory


class ReceiptEventHistoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""CREATE TABLE receipt_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'PENDING',
            suggested_entry TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")

    def tearDown(self):
        self.conn.close()

    def test_january_february_reopen_future_and_repeat(self):
        h = ReceiptHistory(self.conn)
        a, added = h.add("jan-01.pdf", "2026-01-10T10:00:00+09:00")
        self.assertTrue(added)
        b, added = h.add("jan-02.png", "2026-01-20T10:00:00+09:00")
        self.assertTrue(added)
        self.assertEqual(h.add("jan-01.pdf", "2026-01-21T00:00:00Z"), (a, False))
        self.assertEqual(h.replay(2026, 1)["unprocessed_receipts_as_of_month_end"], 2)
        self.assertTrue(h.transition(a, "POSTED", "2026-02-01T10:00:00+09:00"))
        self.assertFalse(h.transition(a, "POSTED", "2026-02-02T10:00:00+09:00"))
        feb = h.replay(2026, 2)
        self.assertEqual(feb["unprocessed_receipts_as_of_month_end"], 1)
        self.assertEqual(feb["status"], "VERIFIED_HISTORY_ONLY")
        self.assertEqual(feb, h.replay(2026, 2))  # repeat is deterministic
        self.assertTrue(h.transition(a, "PENDING", "2026-03-01T10:00:00+09:00"))
        h.add("future.pdf", "2026-04-02T10:00:00+09:00")
        self.assertEqual(h.replay(2026, 1)["unprocessed_receipts_as_of_month_end"], 2)
        self.assertEqual(h.replay(2026, 2)["unprocessed_receipts_as_of_month_end"], 1)
        self.assertEqual(h.replay(2026, 3)["unprocessed_receipts_as_of_month_end"], 2)
        self.assertEqual(h.replay(2026, 4)["unprocessed_receipts_as_of_month_end"], 3)
        self.assertFalse(h.replay(2026, 2)["tax_filing_or_deduction_approved"])

    def test_jst_month_end_boundary_excludes_next_day(self):
        h = ReceiptHistory(self.conn)
        a, _ = h.add("cutoff.png", "2026-01-31T23:59:59+09:00")
        h.transition(a, "POSTED", "2026-02-01T00:00:01+09:00")
        self.assertEqual(h.replay(2026, 1)["unprocessed_receipts_as_of_month_end"], 1)
        self.assertEqual(h.replay(2026, 2)["unprocessed_receipts_as_of_month_end"], 0)

    def test_legacy_data_never_inferred_from_current_status(self):
        self.conn.execute("INSERT INTO receipt_queue(file_path,status) VALUES('old.pdf','POSTED')")
        h = ReceiptHistory(self.conn)
        h.add("new.pdf", "2026-02-02T00:00:00Z")
        r = h.replay(2026, 2)
        self.assertIsNone(r["unprocessed_receipts_as_of_month_end"])
        self.assertEqual(r["reason"], "LEGACY_HISTORY_UNKNOWN")

    def test_bypassed_insert_and_unlogged_change_fail_closed(self):
        h = ReceiptHistory(self.conn)
        rid, _ = h.add("safe.pdf", "2026-01-02T00:00:00Z")
        self.conn.execute("INSERT INTO receipt_queue(file_path) VALUES('bypass.pdf')")
        self.assertEqual(h.replay(2026, 1)["reason"], "UNLOGGED_RECEIPT")
        self.conn.execute("DELETE FROM receipt_queue WHERE file_path='bypass.pdf'")
        self.conn.execute("UPDATE receipt_queue SET status='POSTED' WHERE id=?", (rid,))
        self.assertEqual(h.replay(2026, 1)["reason"], "UNLOGGED_STATUS_CHANGE")
        with self.assertRaisesRegex(ValueError, "RECEIPT_HISTORY_INCOMPLETE_HOLD"):
            h.transition(rid, "PENDING", "2026-02-01T00:00:00Z")

    def test_missing_source_and_append_only(self):
        h = ReceiptHistory(self.conn)
        rid, _ = h.add("original.png", "2026-01-01T00:00:00Z")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM receipt_status_events WHERE receipt_id=?", (rid,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE receipt_status_events SET status='POSTED' WHERE receipt_id=?", (rid,))
        self.conn.execute("DELETE FROM receipt_queue WHERE id=?", (rid,))
        self.assertEqual(h.replay(2026, 1)["reason"], "SOURCE_RECEIPT_MISSING_OR_CHANGED")
        self.assertIsNone(h.replay(2026, 1)["unprocessed_receipts_as_of_month_end"])

    def test_timestamp_and_sequence_validation(self):
        h = ReceiptHistory(self.conn)
        rid, _ = h.add("one.pdf", "2026-01-02T00:00:00Z")
        with self.assertRaises(ValueError):
            h.transition(rid, "POSTED", "2026-01-01T00:00:00Z")
        with self.assertRaises(ValueError):
            h.transition(rid, "POSTED", "2026-01-03T00:00:00")  # no TZ
        with self.assertRaises(ValueError):
            h.transition(rid, "UNKNOWN", "2026-01-03T00:00:00Z")
        self.assertEqual(h.replay(2026, 1)["unprocessed_receipts_as_of_month_end"], 1)


if __name__ == "__main__":
    unittest.main()
