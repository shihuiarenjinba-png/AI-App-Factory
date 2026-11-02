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


class ReceiptBackupRecoveryTests(unittest.TestCase):
    """Synthetic-only backup, restart, negative archive and no-overwrite tests."""

    def _book(self, root):
        source = root / "original.pdf"
        source.write_bytes(b"%PDF-1.4\\nSynthetic local receipt\\n%%EOF\\n")
        store = core.Store(root / "live" / "books.sqlite3")
        store.enqueue_receipts([source], at="2026-01-10T09:00:00+09:00",
                               preserve_source=True)
        store.post("2026-01-11", "synthetic", [("1100", 800, 0), ("4000", 0, 800)])
        return store, source

    def test_atomic_backup_preview_new_book_restore_and_restart(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            s, source = self._book(root)
            archive = root / "backup.zip"
            try:
                result = s.create_receipt_backup(archive)
                self.assertEqual(result["status"], "VERIFIED_BACKUP")
                self.assertEqual(result["receipt_count"], 1)
                self.assertEqual(s.inspect_receipt_backup(archive)["ledger_id"],
                                 result["ledger_id"])
                self.assertEqual(s.journal()[0]["description"], "synthetic")
                restore = s.restore_receipt_backup(archive, root / "recovered")
            except Exception:
                s.close()
                raise
            else:
                s.close()
            self.assertEqual(restore["status"], "RESTORED_NEW_BOOK")
            recovered = core.Store(restore["database"])
            try:
                self.assertEqual(recovered.pnl()["利益"], 800)
                self.assertEqual(recovered.receipt_month_end(2026, 1)
                                 ["unprocessed_receipts_as_of_month_end"], 1)
                self.assertEqual(recovered.receipt_custody_summary()["verified"], 1)
                self.assertEqual(source.read_bytes(),
                                 next(Path(restore["originals"]).glob("*.bin")).read_bytes())
            finally:
                recovered.close()
            again = core.Store(restore["database"])
            try:
                self.assertEqual(again.receipt_custody_summary()["verified"], 1)
            finally:
                again.close()

    def test_no_overwrite_and_separate_restore_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            s, _ = self._book(root)
            try:
                target = root / "backup.zip"
                target.write_bytes(b"do-not-overwrite")
                with self.assertRaises(core.BookError):
                    s.create_receipt_backup(target)
                self.assertEqual(target.read_bytes(), b"do-not-overwrite")
                target.unlink()
                s.create_receipt_backup(target)
                with self.assertRaises(core.BookError):
                    s.create_receipt_backup(target)
                self.assertEqual(s.inspect_receipt_backup(target)["receipt_count"], 1)
                recovered_parent = root / "recovered"
                recovered_parent.mkdir()
                keep = recovered_parent / "books.sqlite3"
                keep.write_bytes(b"existing unrelated ledger")
                result = s.restore_receipt_backup(target, recovered_parent)
                self.assertEqual(keep.read_bytes(), b"existing unrelated ledger")
                self.assertNotEqual(Path(result["database"]), keep)
            finally:
                s.close()

    def test_corrupt_missing_and_legacy_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            s, _ = self._book(root)
            try:
                stored = Path(s.receipt_custody_status(s.receipts()[0]["id"])
                              ["stored_original"])
                stored.unlink()
                with self.assertRaises(core.BookError):
                    s.create_receipt_backup(root / "missing.zip")
                self.assertFalse((root / "missing.zip").exists())
            finally:
                s.close()
            legacy = core.Store(root / "legacy" / "books.sqlite3")
            try:
                legacy.enqueue_receipts(["legacy.pdf"])
                with self.assertRaises(core.BookError):
                    legacy.create_receipt_backup(root / "legacy.zip")
            finally:
                legacy.close()
            corrupt = root / "corrupt.zip"
            corrupt.write_bytes(b"not a zip")
            check = core.Store(root / "new" / "books.sqlite3")
            try:
                with self.assertRaises(core.BookError):
                    check.inspect_receipt_backup(corrupt)
                with self.assertRaises(core.BookError):
                    check.restore_receipt_backup(corrupt, root)
            finally:
                check.close()

    def test_duplicate_traversal_symlink_and_missing_zip_entries_rejected(self):
        import io
        import stat
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            s, _ = self._book(root)
            try:
                archive = root / "valid.zip"
                s.create_receipt_backup(archive)
                original = zipfile.ZipFile(archive)
                with original:
                    files = [(i, original.read(i.filename)) for i in original.infolist()]
                for label, bad_entry in (
                    ("traversal", "../escape.bin"),
                    ("duplicate", "books.sqlite3"),
                    ("missing", None),
                    ("symlink", "receipt-originals/link.bin"),
                ):
                    out = root / (label + ".zip")
                    with zipfile.ZipFile(out, "w") as z:
                        for info, data in files:
                            if label == "missing" and info.filename == "books.sqlite3":
                                continue
                            z.writestr(info.filename, data)
                        if bad_entry is not None:
                            if label == "symlink":
                                info = zipfile.ZipInfo(bad_entry)
                                info.create_system = 3
                                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                                z.writestr(info, "books.sqlite3")
                            else:
                                z.writestr(bad_entry, b"attack")
                    with self.assertRaises(core.BookError, msg=label):
                        s.inspect_receipt_backup(out)
                    self.assertFalse((root / "escape.bin").exists())
            finally:
                s.close()

    def test_other_ledger_id_and_novice_controls(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            s, _ = self._book(root)
            other = core.Store(root / "other" / "books.sqlite3")
            try:
                archive = root / "valid.zip"
                s.create_receipt_backup(archive)
                other_archive = root / "other.zip"
                other.create_receipt_backup(other_archive)
                backup = load("jp_receipt_backup_negative", "receipt_backup.py")
                with self.assertRaises(backup.BackupError):
                    backup.inspect_backup(archive, expected_ledger_id=
                                          other.inspect_receipt_backup(other_archive)
                                          ["ledger_id"])
                with self.assertRaises(backup.BackupError):
                    backup.restore_backup(archive, root,
                                          expected_ledger_id=
                                          other.inspect_receipt_backup(other_archive)
                                          ["ledger_id"])
                self.assertEqual(other.receipts(), [])
            finally:
                s.close()
                other.close()
        ui = (ROOT / "main.py").read_text(encoding="utf-8")
        ast.parse(ui)
        for label in ("バックアップを作成", "復元前の確認",
                      "復旧できない理由", "別の帳簿として復元"):
            self.assertIn(label, ui)


if __name__ == "__main__":
    unittest.main()
