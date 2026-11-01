"""Offline receipt evidence fixtures; no tax or OCR claims."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "products" / "us-bookkeeping-desk"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core = load("us_receipt_core", "core.py")
vault_module = load("us_receipt_vault", "receipt_vault.py")


class ReceiptVaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.store = core.Store(self.dir / "books.sqlite3", "cash")
        self.first = self.store.post("2026-10-10", "Customer paid",
                                     [("1100", "100.00", ""), ("4000", "", "100.00")])
        self.second = self.store.post("2026-10-11", "Office supply",
                                      [("5500", "20.00", ""), ("1100", "", "20.00")])
        self.vault = vault_module.ReceiptVault(self.store)
        self.pdf = self.dir / "invoice.pdf"
        self.pdf.write_bytes(b"%PDF-1.7\n% local evidence\n")
        self.png = self.dir / "receipt.png"
        self.png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fixture")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def reports(self):
        return (self.store.journal(), self.store.ledger("1100"), self.store.trial(),
                self.store.pnl(), self.store.bs(), self.store.balance_check())

    def test_attach_multiple_duplicate_and_restart_without_changing_books(self):
        before = self.reports()
        result = self.vault.attach_many(self.first, [self.pdf, self.png, self.pdf])
        self.assertEqual([x["status"] for x in result],
                         ["attached", "attached", "duplicate"])
        self.assertEqual(len(self.vault.for_entry(self.first)), 2)
        self.assertEqual(before, self.reports())
        self.assertEqual(self.store.pnl()["net_income"], 8000)
        self.assertTrue(self.store.balance_check()["balanced"])
        self.assertEqual(self.store.bs()["assets"],
                         self.store.bs()["liabilities_and_equity"])
        self.assertEqual(self.store.conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='RECEIPT_ATTACH'"
        ).fetchone()[0], 2)
        self.assertEqual(self.vault.attach_many(self.second, [self.pdf])[0]["status"], "attached")
        self.assertEqual(self.store.conn.execute(
            "SELECT COUNT(*) FROM receipt_documents").fetchone()[0], 2)
        self.store.close()
        self.store = core.Store(self.dir / "books.sqlite3")
        self.vault = vault_module.ReceiptVault(self.store)
        self.assertEqual(len(self.vault.for_entry(self.first)), 2)
        self.assertEqual(before, self.reports())

    def test_reject_bad_file_without_stopping_good_files(self):
        fake = self.dir / "fake.pdf"
        fake.write_bytes(b"not a PDF")
        unsupported = self.dir / "file.exe"
        unsupported.write_bytes(b"MZ")
        huge = self.dir / "huge.pdf"
        with huge.open("wb") as out:
            out.truncate(vault_module.MAX_RECEIPT_BYTES + 1)
        results = self.vault.attach_many(self.first, [fake, self.pdf, unsupported, huge])
        self.assertEqual([x["status"] for x in results],
                         ["rejected", "attached", "rejected", "rejected"])
        self.assertEqual(len(self.vault.for_entry(self.first)), 1)
        with self.assertRaises(vault_module.ReceiptError):
            self.vault.attach_many(9999, [self.pdf])

    def test_save_copy_never_overwrites_and_checks_hash(self):
        row = self.vault.attach_many(self.first, [self.pdf])[0]
        target = self.dir / "saved.pdf"
        self.vault.save_copy(self.first, row["document_id"], target)
        self.assertEqual(target.read_bytes(), self.pdf.read_bytes())
        with self.assertRaises(FileExistsError):
            self.vault.save_copy(self.first, row["document_id"], target)
        with self.assertRaises(vault_module.ReceiptError):
            self.vault.save_copy(self.second, row["document_id"], self.dir / "bad.pdf")
        self.store.conn.execute("UPDATE receipt_documents SET content=? WHERE id=?",
                                (b"tampered", row["document_id"]))
        self.store.conn.commit()
        with self.assertRaises(vault_module.ReceiptError):
            self.vault.save_copy(self.first, row["document_id"], self.dir / "tampered.pdf")

    def test_reject_symlink_when_available(self):
        link = self.dir / "linked.pdf"
        try:
            link.symlink_to(self.pdf)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not permitted on this host")
        self.assertEqual(self.vault.attach_many(self.first, [link])[0]["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
