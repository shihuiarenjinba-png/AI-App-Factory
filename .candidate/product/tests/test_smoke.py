"""18 headless functional regression tests."""
import json
import os
from unittest import mock
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import main as app

class DiffTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.dir=Path(t.name)
        self.left=self.dir/"left.txt"
        self.right=self.dir/"right.txt"
        self.left.write_text("alpha\nbeta\n",encoding="utf-8")
        self.right.write_text("alpha\ngamma\n",encoding="utf-8")

    def test_crlf_normalized_on_windows(self):
        self.left.write_bytes(b"alpha\r\nbeta\r\n")
        self.assertEqual(app.read_text(self.left),"alpha\nbeta\n")

    def test_utf8_read(self):
        self.assertEqual(app.read_text(self.left),"alpha\nbeta\n")

    def test_bom_read(self):
        self.left.write_bytes(b"\xef\xbb\xbfhello\n")
        self.assertEqual(app.read_text(self.left),"hello\n")

    def test_binary_rejected(self):
        self.left.write_bytes(b"hello\x00")
        with self.assertRaises(ValueError): app.read_text(self.left)

    def test_bad_encoding_rejected(self):
        self.left.write_bytes(b"\xff")
        with self.assertRaises(UnicodeError): app.read_text(self.left)

    def test_oversize_rejected(self):
        self.left.write_bytes(b"x"*(app.LIMIT+1))
        with self.assertRaises(ValueError): app.read_text(self.left)

    def test_missing_rejected(self):
        with self.assertRaises(FileNotFoundError): app.read_text(self.dir/"missing.txt")

    def test_symlink_rejected(self):
        link=self.dir/"link.txt"
        try: link.symlink_to(self.left)
        except (OSError,NotImplementedError): return
        with self.assertRaises(ValueError): app.read_text(link)

    def test_many_lines_rejected(self):
        self.left.write_text("x\n"*(app.LINES+1),encoding="utf-8")
        with self.assertRaises(ValueError): app.read_text(self.left)

    def test_equal(self):
        self.assertTrue(app.compare("a\n","a\n")["same"])

    def test_change(self):
        result=app.compare("a\nb\n","a\nc\n")
        self.assertEqual(result["changes"],1)
        self.assertIn("-b",result["diff"])
        self.assertIn("+c",result["diff"])

    def test_insert(self):
        self.assertIn("+b",app.compare("a\n","a\nb\n")["diff"])

    def test_delete(self):
        self.assertIn("-b",app.compare("a\nb\n","a\n")["diff"])

    def test_ignore_whitespace(self):
        self.assertTrue(app.compare("a  b\n","a b\n",True)["same"])
        self.assertFalse(app.compare("a  b\n","a b\n")["same"])

    def test_context_validation(self):
        for v in (-1,11,True,"3"):
            with self.assertRaises(ValueError): app.compare("a","b",context=v)

    def test_export_backup_name_cannot_clobber_source(self):
        source = self.dir / "report.diff.bak"
        source.write_text("ORIGINAL SOURCE", encoding="utf-8")
        output = self.dir / "report.diff"
        output.write_text("old report", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source document"):
            app.export_diff(output, app.compare("a", "b"), source, self.right)
        self.assertEqual(source.read_text(encoding="utf-8"), "ORIGINAL SOURCE")
        self.assertEqual(output.read_text(encoding="utf-8"), "old report")

    def test_export_rejects_hardlinked_backup_alias(self):
        source = self.dir / "protected.txt"
        source.write_text("PRIVATE SOURCE", encoding="utf-8")
        output = self.dir / "report.diff"
        output.write_text("old report", encoding="utf-8")
        try:
            os.link(source, self.dir / "report.diff.bak")
        except (OSError, NotImplementedError):
            self.skipTest("hardlinks unavailable")
        with self.assertRaisesRegex(ValueError, "source document"):
            app.export_diff(output, app.compare("a", "b"), source, self.right)
        self.assertEqual(source.read_text(encoding="utf-8"), "PRIVATE SOURCE")

    def test_failed_backup_replacement_preserves_previous_versions(self):
        output = self.dir / "report.diff"
        backup = self.dir / "report.diff.bak"
        output.write_text("CURRENT", encoding="utf-8")
        backup.write_text("PREVIOUS", encoding="utf-8")
        with mock.patch.object(app.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                app.export_diff(output, app.compare("a", "b"), self.left, self.right)
        self.assertEqual(output.read_text(encoding="utf-8"), "CURRENT")
        self.assertEqual(backup.read_text(encoding="utf-8"), "PREVIOUS")

    def test_session_roundtrip(self):
        s=app.make_session(self.left,self.right,True)
        p=self.dir/"session.json"
        app.save_session(p,s)
        self.assertEqual(app.load_session(p),s)

    def test_session_backup(self):
        p=self.dir/"session.json"
        s=app.make_session(self.left,self.right)
        app.save_session(p,s)
        app.save_session(p,app.make_session(self.left,self.right,True))
        p.write_text("{broken",encoding="utf-8")
        self.assertEqual(app.recover_session(p),s)

    def test_reject_schema_and_source_overwrite(self):
        s=app.make_session(self.left,self.right)
        with self.assertRaises(ValueError): app.validate_session(dict(s,extra=1))
        with self.assertRaises(ValueError): app.save_session(self.left,s)
        self.assertEqual(app.read_text(self.left),"alpha\nbeta\n")

    def test_export_and_bilingual(self):
        result=app.compare("a\n","b\n")
        out=self.dir/"report.diff"
        app.export_diff(out,result,self.left,self.right)
        self.assertIn("+b",out.read_text(encoding="utf-8"))
        self.assertIn("title",app.LABELS["ja"])
        self.assertIn("title",app.LABELS["en"])
        self.assertTrue(callable(app.main))
if __name__=="__main__":
    unittest.main()
