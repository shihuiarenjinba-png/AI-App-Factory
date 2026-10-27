import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import new_note, save_notes, read_notes, search_notes, safe_filename, validate_notes

class Smoke(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "notes.json"
        self.note = new_note()
        self.note.update(title="研究", body="Hello 日本語")

    def test_roundtrip(self):
        save_notes(self.path, [self.note])
        self.assertEqual(read_notes(self.path), ([self.note], False))

    def test_search(self):
        self.assertEqual(search_notes([self.note], "hello"), [self.note])
        self.assertEqual(search_notes([self.note], "missing"), [])

    def test_duplicate(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_notes([self.note, self.note])

    def test_malformed(self):
        self.path.write_text("{broken")
        with self.assertRaisesRegex(ValueError, "Cannot read"):
            read_notes(self.path)

    def test_backup(self):
        save_notes(self.path, [self.note])
        save_notes(self.path, [new_note()])
        self.path.write_text("broken")
        self.assertEqual(read_notes(self.path), ([self.note], True))

    def test_interrupted_write(self):
        save_notes(self.path, [self.note])
        before = self.path.read_bytes()
        with patch("main.os.replace", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                save_notes(self.path, [self.note, new_note()])
        self.assertEqual(self.path.read_bytes(), before)

    def test_empty(self):
        save_notes(self.path, [])
        self.assertEqual(read_notes(self.path), ([], False))

    def test_filename(self):
        self.assertEqual(safe_filename("CON"), "note_CON.txt")
        self.assertEqual(safe_filename(""), "untitled.txt")

    def test_windows_reserved_device_name_with_extension(self):
        for title in ("CON.txt", "con.log", "PRN.backup", "COM1.notes", "LPT9.notes"):
            with self.subTest(title=title):
                self.assertTrue(safe_filename(title).startswith("note_"), title)

    def test_export_preserves_unsaved_status(self):
        from main import App
        from unittest.mock import Mock
        for lang in ("ja", "en"):
            with self.subTest(lang=lang):
                export_path = Path(self.tmp.name) / ("export_" + lang + ".txt")
                app = App.__new__(App)
                app.notes = [self.note]
                app.current = self.note["id"]
                app.lang = lang
                app.dirty = True
                app.status = Mock()
                app.commit_editor = lambda: None
                with patch("main.filedialog.asksaveasfilename", return_value=str(export_path)):
                    app.export()
                self.assertTrue(app.dirty, "TXT export must not mark the notes database saved")
                self.assertTrue(export_path.is_file())
                self.assertTrue(app.status.set.call_args.args[0].startswith("TXT書き出し完了" if lang == "ja" else "TXT exported"))

    def test_export_overwrite_confirmation_localized(self):
        from main import App
        from unittest.mock import Mock
        for lang, expected in (("ja", "既存ファイルを上書きしますか？"), ("en", "Overwrite existing file?")):
            with self.subTest(lang=lang):
                path = Path(self.tmp.name) / ("existing_" + lang + ".txt")
                path.write_text("original", encoding="utf-8")
                app = App.__new__(App)
                app.notes = [self.note]
                app.current = self.note["id"]
                app.lang = lang
                app.dirty = True
                app.status = Mock()
                app.commit_editor = lambda: None
                with patch("main.filedialog.asksaveasfilename", return_value=str(path)), \
                     patch("main.messagebox.askyesno", return_value=False) as confirm:
                    app.export()
                self.assertEqual(confirm.call_count, 1)
                self.assertEqual(confirm.call_args.args[1], expected)
                self.assertEqual(path.read_text(encoding="utf-8"), "original")
                self.assertTrue(app.dirty)

    def test_error_guidance_localized(self):
        from main import App
        from unittest.mock import Mock
        for lang, guidance in (("ja", "入力内容とファイルの保存先を確認"),
                               ("en", "Check your input and file location")):
            with self.subTest(lang=lang):
                app = App.__new__(App)
                app.lang = lang
                app.status = Mock()
                with patch("main.messagebox.showerror") as dialog:
                    app.error(ValueError("broken JSON"))
                self.assertIn(guidance, dialog.call_args.args[1])
                self.assertIn("broken JSON", dialog.call_args.args[1])
                self.assertIn(guidance, app.status.set.call_args.args[0])

    def test_symlink(self):
        target = Path(self.tmp.name) / "target"
        target.write_text("safe")
        link = Path(self.tmp.name) / "link"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unsupported")
        with self.assertRaisesRegex(ValueError, "symbolic link"):
            save_notes(link, [self.note])
        self.assertEqual(target.read_text(), "safe")

if __name__ == "__main__":
    unittest.main()
