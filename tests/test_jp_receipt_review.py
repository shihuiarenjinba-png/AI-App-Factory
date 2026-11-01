"""Real SQLite fixtures for review-first JP receipt intake."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "products" / "jp-freelance-ledger"


def load(name):
    spec = importlib.util.spec_from_file_location("jp_receipt_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = load("core")
receipt = load("receipt_review")


class ReceiptReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "book.sqlite3"
        self.store = core.Store(self.db)
        self.addCleanup(self.store.close)

    def file(self, name, content=b"image bytes"):
        path = self.root / name
        path.write_bytes(content)
        return path

    def test_preview_is_read_only_and_batch_is_isolated(self):
        a = self.file("a.jpg", b"a")
        b = self.file("b.pdf", b"b")
        duplicate = self.file("copy.png", b"a")
        bad = self.file("unsupported.exe", b"x")
        preview = receipt.review_receipts([a, b, duplicate, bad, self.root / "missing.pdf"], self.store)
        self.assertEqual((len(preview["valid"]), len(preview["duplicates"]), len(preview["errors"])), (2, 1, 2))
        self.assertEqual(self.store.pending_receipts(), [])
        result = receipt.apply_receipt_review(self.store, preview)
        self.assertEqual(result, {"imported": 2, "duplicates": 0, "errors": 2})
        self.assertEqual(len(self.store.pending_receipts()), 2)
        self.assertEqual(self.store.conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='RECEIPT_QUEUE_ADD'"
        ).fetchone()[0], 2)

    def test_repeated_import_and_restart_are_idempotent(self):
        a = self.file("one.png")
        preview = receipt.review_receipts([a], self.store)
        self.assertEqual(receipt.apply_receipt_review(self.store, preview)["imported"], 1)
        self.assertEqual(receipt.apply_receipt_review(self.store, preview)["duplicates"], 1)
        self.assertEqual(len(receipt.review_receipts([a], self.store)["duplicates"]), 1)
        other = self.file("same.pdf")
        self.assertEqual(len(receipt.review_receipts([other], self.store)["duplicates"]), 1)
        self.store.close()
        self.store = core.Store(self.db)
        self.addCleanup(self.store.close)
        self.assertEqual(len(receipt.review_receipts([other], self.store)["duplicates"]), 1)

    def test_changed_file_rejected_without_partial_write(self):
        a = self.file("one.jpg", b"first")
        b = self.file("two.jpg", b"second")
        preview = receipt.review_receipts([a, b], self.store)
        b.write_bytes(b"changed")
        with self.assertRaises(receipt.ReceiptReviewError):
            receipt.apply_receipt_review(self.store, preview)
        self.assertEqual(len(self.store.pending_receipts()), 0)

    def test_transaction_rolls_back_on_database_failure(self):
        a = self.file("one.jpg", b"first")
        b = self.file("two.jpg", b"second")
        preview = receipt.review_receipts([a, b], self.store)
        self.store.conn.execute("""CREATE TRIGGER fail_second BEFORE INSERT ON receipt_queue
            WHEN NEW.file_path LIKE '%two.jpg'
            BEGIN SELECT RAISE(ABORT,'simulated disk/write failure'); END""")
        with self.assertRaises(Exception):
            receipt.apply_receipt_review(self.store, preview)
        self.assertEqual(len(self.store.pending_receipts()), 0)
        self.assertEqual(self.store.conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='RECEIPT_QUEUE_ADD'"
        ).fetchone()[0], 0)

    def test_limits_and_empty_file(self):
        empty = self.file("empty.png", b"")
        self.assertEqual(len(receipt.review_receipts([empty], self.store)["errors"]), 1)
        with self.assertRaises(receipt.ReceiptReviewError):
            receipt.review_receipts([empty] * 101, self.store)


if __name__ == "__main__":
    unittest.main()
