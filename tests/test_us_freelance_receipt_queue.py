import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "products" / "us-freelance-ledger" / "receipt_queue.py"
SPEC = importlib.util.spec_from_file_location("usfl_receipt_queue", MODULE_PATH)
queue = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = queue
SPEC.loader.exec_module(queue)


class ReceiptQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.conn = sqlite3.connect(self.root / "ledger.sqlite3")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_batch_duplicate_and_partial_failure(self):
        a = self.root / "a.pdf"
        b = self.root / "b.pdf"
        a.write_bytes(b"%PDF-1.7\\nunique content")
        b.write_bytes(a.read_bytes())
        result = queue.enqueue_receipts(self.conn, [a, self.root / "missing.jpg", b])
        self.assertEqual([r["status"] for r in result], ["QUEUED", "REJECTED", "DUPLICATE"])
        self.assertEqual(len(queue.list_receipts(self.conn)), 1)
        self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_manual_link_refuses_changed_file_and_reuse(self):
        a = self.root / "receipt.png"
        a.write_bytes(b"original")
        self.assertEqual(queue.enqueue_receipts(self.conn, [a])[0]["status"], "QUEUED")
        a.write_bytes(b"changed")
        self.assertFalse(queue.link_receipt(self.conn, str(a), 5))
        a.write_bytes(b"original")
        self.assertTrue(queue.link_receipt(self.conn, str(a), 5))
        self.assertFalse(queue.link_receipt(self.conn, str(a), 6))
        self.assertEqual(queue.list_receipts(self.conn)[0]["transaction_id"], 5)

    def test_unsupported_empty_symlink_and_batch_cap(self):
        empty = self.root / "empty.pdf"
        empty.touch()
        wrong = self.root / "file.txt"
        wrong.write_text("text")
        statuses = [r["status"] for r in queue.enqueue_receipts(self.conn, [empty, wrong])]
        self.assertEqual(statuses, ["REJECTED", "REJECTED"])
        target = self.root / "target.jpg"
        target.write_bytes(b"image")
        link = self.root / "link.jpg"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            pass
        else:
            self.assertEqual(queue.enqueue_receipts(self.conn, [link])[0]["status"], "REJECTED")
        results = queue.enqueue_receipts(self.conn, [target] * (queue.MAX_RECEIPTS_PER_BATCH + 1))
        self.assertEqual(results[-1]["status"], "REJECTED")
        self.assertEqual(results[-1]["reason"], "Batch limit is 100 files")


if __name__ == "__main__":
    unittest.main()
