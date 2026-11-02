"""Real-byte receipt custody regression, JP-only. No real personal receipts."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "products" / "jp-bookkeeping-desk"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core = load("jp_original_custody_core", "core.py")
monthly = load("jp_original_custody_monthly", "monthly_close.py")
custody_module = sys.modules[core.ReceiptCustody.__module__]


class ReceiptOriginalCustodyTests(unittest.TestCase):
    def test_bytes_pinned_duplicate_restart_and_month_end(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "invoice.pdf"
            content = b"%PDF-1.4\nSynthetic original receipt\n%%EOF\n"
            source.write_bytes(content)
            db = root / "db" / "books.sqlite3"
            s = core.Store(db)
            try:
                self.assertEqual(s.enqueue_receipts([source], at="2026-01-10T09:00:00+09:00",
                                                    preserve_source=True), 1)
                self.assertEqual(s.enqueue_receipts([source], preserve_source=True), 0)
                rid = s.receipts()[0]["id"]
                info = s.receipt_custody_status(rid)
                self.assertEqual(info["status"], "VERIFIED")
                self.assertEqual(info["sha256"], hashlib.sha256(content).hexdigest())
                self.assertEqual(info["size_bytes"], len(content))
                self.assertEqual(Path(info["stored_original"]).read_bytes(), content)
                self.assertIn("+00:00", info["captured_utc"])
                self.assertEqual(source.read_bytes(), content)
                s.post("2026-01-15", "synthetic sale", [("1100", 1000, 0), ("4000", 0, 1000)])
                jan = monthly.export_month_end_package(s, 2026, 1, root / "out")
                data = json.loads(Path(jan["json"]).read_text(encoding="utf-8"))
                self.assertEqual(data["unprocessed_receipts_as_of_month_end"], 1)
                self.assertEqual(data["original_custody_verified"], 1)
                self.assertEqual(data["original_custody_review_required"], 0)
                self.assertEqual(data["original_custody_status"], "VERIFIED")
                self.assertEqual(data["balance_check"]["balanced"], True)
                self.assertEqual(data["pnl"]["利益"], 1000)
                self.assertFalse(data["tax_filing_or_deduction_approved"])
                self.assertIn("原本を確認できる", Path(jan["html"]).read_text(encoding="utf-8"))
                self.assertTrue(s.set_receipt_status(rid, "POSTED",
                                                     at="2026-02-01T00:00:01+09:00"))
                self.assertEqual(s.receipt_month_end(2026, 1)["unprocessed_receipts_as_of_month_end"], 1)
                self.assertEqual(s.receipt_month_end(2026, 2)["unprocessed_receipts_as_of_month_end"], 0)
            finally:
                s.close()
            s = core.Store(db)
            try:
                self.assertEqual(s.receipt_custody_summary()["verified"], 1)
                self.assertEqual(s.receipt_month_end(2026, 1)["unprocessed_receipts_as_of_month_end"], 1)
                self.assertEqual(s.receipt_month_end(2026, 2)["unprocessed_receipts_as_of_month_end"], 0)
            finally:
                s.close()

    def test_same_name_changed_source_and_missing_renamed_source_review(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / "bill.pdf"
            p.write_bytes(b"%PDF-1.4\noriginal\n")
            s = core.Store(root / "books.sqlite3")
            try:
                s.enqueue_receipts([p], preserve_source=True)
                rid = s.receipts()[0]["id"]
                p.write_bytes(b"%PDF-1.4\nchanged!\n")
                self.assertEqual(s.receipt_custody_status(rid)["reason"], "SOURCE_ORIGINAL_CHANGED")
                with self.assertRaises(core.BookError):
                    s.enqueue_receipts([p], preserve_source=True)
                p.rename(root / "renamed.pdf")
                self.assertEqual(s.receipt_custody_status(rid)["status"], "REVIEW_REQUIRED")
                self.assertEqual(s.receipt_custody_summary()["review_required"], 1)
                report = monthly.export_month_end_package(s, 2026, 1, root / "report")
                data = json.loads(Path(report["json"]).read_text(encoding="utf-8"))
                self.assertEqual(data["original_custody_status"], "REVIEW_REQUIRED")
                self.assertFalse(data["tax_filing_or_deduction_approved"])
            finally:
                s.close()

    def test_preserved_copy_modified_or_missing_is_review_required(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / "receipt.png"
            p.write_bytes(b"\x89PNG\r\n\x1a\nsynthetic")
            s = core.Store(root / "books.sqlite3")
            try:
                s.enqueue_receipts([p], preserve_source=True)
                rid = s.receipts()[0]["id"]
                stored = Path(s.receipt_custody_status(rid)["stored_original"])
                stored.write_bytes(b"tampered")
                self.assertEqual(s.receipt_custody_status(rid)["reason"], "PRESERVED_ORIGINAL_CHANGED")
                stored.unlink()
                self.assertEqual(s.receipt_custody_status(rid)["reason"],
                                 "PRESERVED_ORIGINAL_MISSING_OR_UNREADABLE")
            finally:
                s.close()

    def test_legacy_and_denied_read_fail_closed_without_queue_claim(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / "new.pdf"
            p.write_bytes(b"%PDF-1.4\nSynthetic")
            s = core.Store(root / "books.sqlite3")
            try:
                self.assertEqual(s.enqueue_receipts(["legacy.pdf"]), 1)
                legacy_id = s.receipts()[0]["id"]
                self.assertEqual(s.receipt_custody_status(legacy_id)["reason"],
                                 "LEGACY_ORIGINAL_NOT_CAPTURED")
                with patch.object(custody_module, "_safe_read",
                                  side_effect=core.CustodyError("REVIEW_REQUIRED_SOURCE_UNREADABLE")):
                    with self.assertRaises(core.BookError):
                        s.enqueue_receipts([p], preserve_source=True)
                self.assertEqual(len(s.receipts()), 1)
                self.assertFalse(list((root / "receipt-originals").glob(".capture-*")))
                self.assertFalse(list((root / "receipt-originals").glob("*.bin")))
            finally:
                s.close()

    def test_symlink_and_invalid_extension_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            s = core.Store(root / "books.sqlite3")
            try:
                unsafe = root / "unsafe.exe"
                unsafe.write_bytes(b"MZ")
                with self.assertRaises(core.BookError):
                    s.enqueue_receipts([unsafe], preserve_source=True)
                source = root / "ok.pdf"
                source.write_bytes(b"%PDF-1.4\nsynthetic")
                link = root / "link.pdf"
                try:
                    link.symlink_to(source)
                except (OSError, NotImplementedError):
                    pass  # Windows runners may prohibit creating symbolic links.
                else:
                    with self.assertRaises(core.BookError):
                        s.enqueue_receipts([link], preserve_source=True)
                self.assertEqual(s.receipts(), [])
            finally:
                s.close()

    def test_append_only_metadata_and_novice_ui(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / "receipt.pdf"
            p.write_bytes(b"%PDF-1.4\nsynthetic")
            s = core.Store(root / "books.sqlite3")
            try:
                s.enqueue_receipts([p], preserve_source=True)
                rid = s.receipts()[0]["id"]
                with self.assertRaises(sqlite3.DatabaseError):
                    with s.conn:
                        s.conn.execute("UPDATE receipt_originals SET size_bytes=1 WHERE receipt_id=?", (rid,))
                self.assertEqual(s.receipt_custody_status(rid)["status"], "VERIFIED")
            finally:
                s.close()
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn("原本の保存状態を確認", source)
        self.assertIn("preserve_source=True", source)
        self.assertIn("確認が必要", source)


if __name__ == "__main__":
    unittest.main()
