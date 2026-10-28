"""Headless functional regression for File Integrity Ledger."""
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main as ledger


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / "sample.txt"
        self.file.write_bytes(b"hello\n")

    def entry(self):
        return ledger.make_entry(self.file)

    def test_sha256_matches_bytes(self):
        self.assertEqual(self.entry()["sha256"], hashlib.sha256(b"hello\n").hexdigest())

    def test_entry_is_absolute_and_sized(self):
        e = self.entry()
        self.assertEqual(e["size"], 6)
        self.assertTrue(os.path.isabs(e["path"]))

    def test_verify_unchanged(self):
        self.assertEqual(ledger.verify_snapshot(ledger.snapshot([self.entry()]))[0]["status"], "UNCHANGED")

    def test_verify_modified_same_size(self):
        original = self.entry()
        self.file.write_bytes(b"HELLO\n")
        self.assertEqual(ledger.verify_snapshot(ledger.snapshot([original]))[0]["status"], "MODIFIED")

    def test_verify_missing(self):
        original = self.entry()
        self.file.unlink()
        self.assertEqual(ledger.verify_snapshot(ledger.snapshot([original]))[0]["status"], "MISSING")

    def test_verify_unreadable_or_symlink(self):
        original = self.entry()
        self.file.unlink()
        try:
            self.file.symlink_to(self.root / "another")
        except (OSError, NotImplementedError):
            self.file.mkdir()
        self.assertEqual(ledger.verify_snapshot(ledger.snapshot([original]))[0]["status"], "ERROR")

    def test_reject_symlink_at_capture(self):
        link = self.root / "link.txt"
        try:
            link.symlink_to(self.file)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not supported on this host")
        with self.assertRaises(ValueError):
            ledger.make_entry(link)

    def test_reject_oversized_input(self):
        with self.assertRaises(ValueError):
            ledger.hash_file(self.file, limit=2)

    def test_reject_duplicate_paths(self):
        e = self.entry()
        with self.assertRaises(ValueError):
            ledger.snapshot([e, dict(e)])

    def test_reject_invalid_digest(self):
        e = self.entry()
        e["sha256"] = "not-a-digest"
        with self.assertRaises(ValueError):
            ledger.snapshot([e])

    def test_reject_extra_snapshot_field(self):
        s = ledger.snapshot([self.entry()])
        s["unexpected"] = 1
        with self.assertRaises(ValueError):
            ledger.validate_snapshot(s)

    def test_reject_too_many_entries(self):
        e = self.entry()
        many = [dict(e, path=str(self.root / ("f" + str(i)))) for i in range(101)]
        with self.assertRaises(ValueError):
            ledger.snapshot(many)

    def test_save_and_reload(self):
        s = ledger.snapshot([self.entry()])
        out = self.root / "baseline.json"
        ledger.save_snapshot(out, s)
        self.assertEqual(ledger.load_snapshot(out), s)

    def test_valid_previous_backup(self):
        out = self.root / "baseline.json"
        original = ledger.snapshot([self.entry()])
        ledger.save_snapshot(out, original)
        self.file.write_bytes(b"updated")
        ledger.save_snapshot(out, ledger.snapshot([self.entry()]))
        self.assertEqual(ledger.recover_snapshot(out), original)

    def test_corrupt_current_preserves_backup(self):
        out = self.root / "baseline.json"
        original = ledger.snapshot([self.entry()])
        ledger.save_snapshot(out, original)
        ledger.save_snapshot(out, original)
        out.write_text("{corrupt", encoding="utf-8")
        self.assertEqual(ledger.recover_snapshot(out), original)
        with self.assertRaises(json.JSONDecodeError):
            ledger.load_snapshot(out)

    def test_export_csv_and_formula_escape(self):
        e = self.entry()
        out = self.root / "results.csv"
        ledger.export_csv(out, ledger.snapshot([e]),
                          [{"path": e["path"], "status": "UNCHANGED"}])
        with out.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], ["path", "bytes", "sha256", "status"])
        self.assertEqual(rows[1][3], "UNCHANGED")
        self.assertEqual(ledger.csv_safe(" =2+2"), "' =2+2")
        self.assertEqual(ledger.csv_safe("@SUM(1)"), "'@SUM(1)")

    def test_no_snapshot_symlink_destination(self):
        out = self.root / "linked.json"
        try:
            out.symlink_to(self.file)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not supported on this host")
        with self.assertRaises(ValueError):
            ledger.save_snapshot(out, ledger.snapshot([self.entry()]))

    def test_bilingual_labels_and_entrypoint(self):
        self.assertIn("add", ledger.TEXT["en"])
        self.assertIn("add", ledger.TEXT["ja"])
        self.assertTrue(callable(ledger.main))
        self.assertTrue(hasattr(ledger.LedgerApp, "verify"))


if __name__ == "__main__":
    unittest.main()
