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

    def test_backup_failure_must_abort_save_without_overwriting_primary(self):
        save_notes(self.path, [self.note])
        original = self.path.read_bytes()
        with patch("main.atomic_write", side_effect=OSError("backup disk full")) as writer:
            with self.assertRaisesRegex(OSError, "backup disk full"):
                save_notes(self.path, [self.note, new_note()])
        self.assertEqual(writer.call_count, 1, "must not attempt primary write")
        self.assertEqual(writer.call_args.args[0], self.path.with_name("notes.json.bak"))
        self.assertEqual(self.path.read_bytes(), original)

    def test_txt_export_cannot_overwrite_open_notes_database(self):
        from main import App
        from unittest.mock import Mock
        save_notes(self.path, [self.note])
        original = self.path.read_bytes()
        app = App.__new__(App)
        app.notes, app.current, app.path = [dict(self.note)], self.note["id"], self.path
        app.lang, app.dirty = "en", True
        app.commit_editor, app.error = lambda: None, Mock()
        with (patch("main.filedialog.asksaveasfilename", return_value=str(self.path)),
              patch("main.messagebox.askyesno", return_value=True) as confirm):
            app.export()
        app.error.assert_called_once()
        confirm.assert_not_called()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(app.dirty)

    def test_txt_export_cannot_overwrite_database_backup_name(self):
        from main import App
        from unittest.mock import Mock
        save_notes(self.path, [self.note])
        backup = self.path.with_name("notes.json.bak")
        app = App.__new__(App)
        app.notes, app.current, app.path = [dict(self.note)], self.note["id"], self.path
        app.lang, app.dirty = "ja", True
        app.commit_editor, app.error = lambda: None, Mock()
        with patch("main.filedialog.asksaveasfilename", return_value=str(backup)):
            app.export()
        app.error.assert_called_once()
        self.assertFalse(backup.exists(), "export must not create/overwrite backup")

    def test_txt_export_cannot_overwrite_hardlinked_database(self):
        import os
        from main import App
        from unittest.mock import Mock
        save_notes(self.path, [self.note])
        alias = self.path.with_name("export.txt")
        try:
            os.link(self.path, alias)
        except (OSError, NotImplementedError):
            self.skipTest("hardlinks unavailable")
        original = self.path.read_bytes()
        app = App.__new__(App)
        app.notes, app.current, app.path = [dict(self.note)], self.note["id"], self.path
        app.lang, app.dirty = "en", True
        app.commit_editor, app.error = lambda: None, Mock()
        with patch("main.filedialog.asksaveasfilename", return_value=str(alias)):
            app.export()
        app.error.assert_called_once()
        self.assertEqual(alias.read_bytes(), original)
        self.assertEqual(self.path.read_bytes(), original)

    def test_existing_unrelated_json_is_not_overwritten(self):
        foreign = b'{"schema": 99, "private": "do not overwrite"}\\n'
        self.path.write_bytes(foreign)
        with self.assertRaisesRegex(ValueError, "choose another filename"):
            save_notes(self.path, [self.note])
        self.assertEqual(self.path.read_bytes(), foreign)
        self.assertFalse(self.path.with_name("notes.json.bak").exists())

    def test_damaged_primary_with_valid_backup_is_not_overwritten(self):
        save_notes(self.path, [self.note])
        good = self.path.read_bytes()
        backup = self.path.with_name("notes.json.bak")
        backup.write_bytes(good)
        damaged = b"not a notes database"
        self.path.write_bytes(damaged)
        with self.assertRaisesRegex(ValueError, "damaged"):
            save_notes(self.path, [new_note()])
        self.assertEqual(self.path.read_bytes(), damaged)
        self.assertEqual(backup.read_bytes(), good)

    def test_existing_unrelated_backup_is_not_overwritten(self):
        save_notes(self.path, [self.note])
        good = self.path.read_bytes()
        backup = self.path.with_name("notes.json.bak")
        foreign = b"foreign backup contents"
        backup.write_bytes(foreign)
        with self.assertRaisesRegex(ValueError, "Existing backup"):
            save_notes(self.path, [new_note()])
        self.assertEqual(self.path.read_bytes(), good)
        self.assertEqual(backup.read_bytes(), foreign)

    def test_existing_valid_notes_can_still_save_and_rotate_backup(self):
        save_notes(self.path, [self.note])
        old = self.path.read_bytes()
        second = new_note()
        save_notes(self.path, [self.note, second])
        self.assertEqual(self.path.with_name("notes.json.bak").read_bytes(), old)
        self.assertEqual(read_notes(self.path), ([self.note, second], False))

    def test_explicit_backup_restore_creates_new_database(self):
        from main import App
        from unittest.mock import Mock
        save_notes(self.path, [self.note])
        backup = self.path.with_name(self.path.name + ".bak")
        backup.write_bytes(self.path.read_bytes())
        target = Path(self.tmp.name) / "restored.json"
        app = App.__new__(App)
        app.confirm, app.show, app.error = Mock(return_value=True), Mock(), Mock()
        app.query, app.status = Mock(), Mock()
        app.lang = "en"
        with patch("main.filedialog.askopenfilename", return_value=str(backup)), \
             patch("main.filedialog.asksaveasfilename", return_value=str(target)):
            app.restore_backup()
        app.error.assert_not_called()
        self.assertEqual(read_notes(target), ([self.note], False))
        self.assertEqual(app.path, target)
        self.assertFalse(app.dirty)
        self.assertEqual(backup.read_bytes(), self.path.read_bytes())
        app.show.assert_called_once_with(self.note["id"])

    def test_backup_restore_refuses_existing_destination(self):
        from main import App
        from unittest.mock import Mock
        save_notes(self.path, [self.note])
        backup = self.path.with_name(self.path.name + ".bak")
        backup.write_bytes(self.path.read_bytes())
        target = Path(self.tmp.name) / "unrelated.json"
        target.write_bytes(b"foreign content")
        app = App.__new__(App)
        app.confirm, app.error = Mock(return_value=True), Mock()
        app.lang = "ja"
        with patch("main.filedialog.askopenfilename", return_value=str(backup)), \
             patch("main.filedialog.asksaveasfilename", return_value=str(target)):
            app.restore_backup()
        app.error.assert_called_once()
        self.assertEqual(target.read_bytes(), b"foreign content")

    def test_backup_restore_refuses_damaged_backup(self):
        from main import App
        from unittest.mock import Mock
        backup = self.path.with_name(self.path.name + ".bak")
        backup.write_text("corrupt", encoding="utf-8")
        app = App.__new__(App)
        app.confirm, app.error = Mock(return_value=True), Mock()
        app.lang = "en"
        with patch("main.filedialog.askopenfilename", return_value=str(backup)), \
             patch("main.filedialog.asksaveasfilename") as save_dialog:
            app.restore_backup()
        app.error.assert_called_once()
        save_dialog.assert_not_called()

    def test_roundtrip(self):
        save_notes(self.path, [self.note])
        self.assertEqual(read_notes(self.path), ([self.note], False))

    def test_search(self):
        self.assertEqual(search_notes([self.note], "hello"), [self.note])
        self.assertEqual(search_notes([self.note], "missing"), [])

    def test_search_includes_unsaved_editor_without_persisting(self):
        from main import App
        from unittest.mock import Mock
        app = App.__new__(App)
        app.notes = [dict(self.note)]
        app.current = self.note["id"]
        app.loading = False
        app.query = Mock()
        app.query.get.return_value = "draft text"
        app.title = Mock()
        app.title.get.return_value = "Draft title"
        app.body = Mock()
        app.body.get.return_value = "Draft text not yet saved"
        app.listbox = Mock()
        app.refresh_list()
        self.assertEqual(app.visible, [self.note["id"]])
        app.listbox.insert.assert_called_once_with("end", "Draft title")
        self.assertEqual(app.notes[0]["title"], self.note["title"])
        self.assertEqual(app.notes[0]["body"], self.note["body"])

    def test_duplicate(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_notes([self.note, self.note])

    def test_malformed(self):
        self.path.write_text("{broken")
        with self.assertRaisesRegex(ValueError, "Cannot read"):
            read_notes(self.path)

    def test_duplicate_json_keys_fail_closed_and_recover_backup(self):
        import json
        note_json = json.dumps(self.note, ensure_ascii=False)
        # A repeated notes key must not silently discard the user's data.
        self.path.write_text('{"schema":1,"notes":[' + note_json + '],"notes":[]}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            read_notes(self.path)
        # Duplicate fields inside individual notes must also be rejected.
        self.path.write_text('{"schema":1,"notes":[{' +
                             '"id":"' + self.note["id"] + '","title":"safe",' +
                             '"title":"overwritten","body":"data"}]}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            read_notes(self.path)
        backup = self.path.with_name(self.path.name + ".bak")
        save_notes(backup, [self.note])
        self.assertEqual(read_notes(self.path), ([self.note], True))

    def test_invalid_unicode_surrogate_rejected_and_backup_recovered(self):
        import json
        for field in ("title", "body"):
            with self.subTest(field=field):
                bad = dict(self.note)
                bad[field] = "broken" + chr(0xD800)
                with self.assertRaisesRegex(ValueError, "Unicode surrogate"):
                    save_notes(self.path, [bad])
                self.assertFalse(self.path.exists())
                self.path.write_text(json.dumps({"schema": 1, "notes": [bad]}), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Cannot read"):
                    read_notes(self.path)
                backup = self.path.with_name(self.path.name + ".bak")
                save_notes(backup, [self.note])
                self.assertEqual(read_notes(self.path), ([self.note], True))
                self.path.unlink()
                backup.unlink()

    def test_deeply_nested_json_rejected_and_backup_recovered(self):
        # The standard JSON decoder raises RecursionError on deeply nested
        # input; a damaged local file must not crash the GUI open action.
        self.path.write_text("[" * 10000 + "0" + "]" * 10000, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Cannot read notes or backup"):
            read_notes(self.path)
        backup = self.path.with_name(self.path.name + ".bak")
        save_notes(backup, [self.note])
        self.assertEqual(read_notes(self.path), ([self.note], True))

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

    def test_windows_superscript_reserved_device_names(self):
        # Windows treats COM¹/²/³ and LPT¹/²/³ as device names too.
        for title in ("COM¹", "COM².notes", "COM³", "LPT¹", "LPT².txt", "LPT³.notes"):
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

    def test_export_existing_file_is_rejected_in_both_languages(self):
        from main import App
        from unittest.mock import Mock
        for lang, expected in (
            ("ja", "TXT書き出しには未使用のファイル名を選択してください。"),
            ("en", "Choose a new, unused filename for TXT export."),
        ):
            with self.subTest(lang=lang):
                path = Path(self.tmp.name) / ("existing_" + lang + ".txt")
                path.write_text("OTHER CUSTOMER DATA", encoding="utf-8")
                app = App.__new__(App)
                app.notes = [self.note]
                app.current = self.note["id"]
                app.lang = lang
                app.dirty = True
                app.status = Mock()
                app.error = Mock()
                app.commit_editor = lambda: None
                with patch("main.filedialog.asksaveasfilename", return_value=str(path)), \
                     patch("main.messagebox.askyesno") as confirm:
                    app.export()
                confirm.assert_not_called()
                self.assertEqual(path.read_text(encoding="utf-8"), "OTHER CUSTOMER DATA")
                self.assertTrue(app.dirty)
                app.error.assert_called_once()
                self.assertEqual(str(app.error.call_args.args[0]), expected)

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
