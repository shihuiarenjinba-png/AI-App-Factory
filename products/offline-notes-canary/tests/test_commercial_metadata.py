"""Commercial metadata regression tests: no Tk display required."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import App, find_matches, new_note, normalize_tags, read_notes, save_notes, search_notes, validate_notes


class CommercialMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "notes.json"
        self.note = new_note()
        self.note.update(title="Project", body="Draft text")

    def test_search_match_offsets_unicode_case_and_bounds(self):
        self.assertEqual(find_matches("alpha ALPHA alpha", "alpha"),
                         [(0, 5), (6, 11), (12, 17)])
        self.assertEqual(find_matches("メモで検索メモ", "メモ"), [(0, 2), (5, 7)])
        self.assertEqual(find_matches("abc", ""), [])
        self.assertEqual(find_matches("aaaaa", "a", limit=2), [(0, 1), (1, 2)])

    def test_body_highlights_are_visual_only_and_cleared(self):
        app = App.__new__(App)
        app.current = self.note["id"]
        app.body, app.query = Mock(), Mock()
        app.body.get.return_value = "Alpha alpha"
        app.query.get.return_value = "alpha"
        app.highlight_search()
        self.assertEqual(app.body.tag_add.call_count, 2)
        app.body.tag_add.assert_any_call("search_match", "1.0+0c", "1.0+5c")
        app.body.tag_add.assert_any_call("search_match", "1.0+6c", "1.0+11c")
        app.query.get.return_value = ""
        app.highlight_search()
        self.assertEqual(app.body.tag_remove.call_count, 2)
        self.assertEqual(app.body.tag_add.call_count, 2)

    def test_live_tag_search_uses_unsaved_editor_without_mutating_database(self):
        app = App.__new__(App)
        app.notes, app.current, app.loading = [dict(self.note)], self.note["id"], False
        app.recent_ids = []
        app.title, app.body, app.tag_text = Mock(), Mock(), Mock()
        app.title.get.return_value = self.note["title"]
        app.body.get.return_value = self.note["body"]
        app.tag_text.get.return_value = "研究,  urgent "
        app.query, app.listbox = Mock(), Mock()
        app.query.get.return_value = "研究"
        app.refresh_list()
        self.assertEqual(app.visible, [self.note["id"]])
        self.assertNotIn("tags", app.notes[0], "search preview must never save draft tags")
        app.tag_text.get.return_value = ""
        app.refresh_list()
        self.assertEqual(app.visible, [], "cleared draft tags must disappear from search")

    def test_live_tag_search_handles_incomplete_invalid_draft(self):
        app = App.__new__(App)
        app.notes, app.current, app.loading = [dict(self.note)], self.note["id"], False
        app.recent_ids = []
        app.title, app.body, app.tag_text = Mock(), Mock(), Mock()
        app.title.get.return_value = self.note["title"]
        app.body.get.return_value = self.note["body"]
        app.tag_text.get.return_value = "work,WORK,、"
        app.query, app.listbox = Mock(), Mock()
        app.query.get.return_value = "work"
        app.refresh_list()
        self.assertEqual(app.visible, [self.note["id"]])
        self.assertNotIn("tags", app.notes[0])

    def test_favorites_only_filters_without_mutating_notes(self):
        favorite = {**self.note, "favorite": True}
        other = new_note()
        other.update(title="Report two", body="Other report")
        favorite["title"] = "Report one"
        app = App.__new__(App)
        app.notes, app.current, app.loading = [favorite, other], None, False
        app.recent_ids = []
        app.query, app.listbox, app.favorites_only = Mock(), Mock(), Mock()
        app.query.get.return_value = "report"
        app.favorites_only.get.return_value = True
        app.refresh_list()
        self.assertEqual(app.visible, [favorite["id"]])
        app.favorites_only.get.return_value = False
        app.refresh_list()
        self.assertEqual(set(app.visible), {favorite["id"], other["id"]})
        self.assertEqual(app.notes, [favorite, other])

    def test_favorites_only_empty_state_and_bilingual_label(self):
        from main import STRINGS
        self.assertEqual(STRINGS["ja"][23], "お気に入りのみ")
        self.assertEqual(STRINGS["en"][23], "Favorites only")
        app = App.__new__(App)
        app.notes, app.current, app.loading = [], None, False
        app.query, app.listbox, app.favorites_only = Mock(), Mock(), Mock()
        app.query.get.return_value = ""
        app.favorites_only.get.return_value = True
        app.refresh_list()
        self.assertEqual(app.visible, [])

    def test_save_as_new_file_preserves_original_and_sets_current_path(self):
        original = self.path
        save_notes(original, [self.note])
        original_bytes = original.read_bytes()
        other = {**self.note, "title": "A different draft"}
        app = App.__new__(App)
        app.notes, app.path, app.dirty, app.lang = [other], original, True, "en"
        app.commit_editor, app.refresh_list, app.status = Mock(), Mock(), Mock()
        app.error = Mock()
        destination = Path(self.tmp.name) / "copy.json"
        with patch("main.filedialog.asksaveasfilename", return_value=str(destination)):
            self.assertTrue(app.save_as())
        self.assertEqual(original.read_bytes(), original_bytes)
        self.assertEqual(read_notes(destination), ([other], False))
        self.assertEqual(app.path, destination)
        self.assertFalse(app.dirty)
        app.error.assert_not_called()

    def test_save_as_existing_destination_is_fail_closed(self):
        existing = Path(self.tmp.name) / "existing.json"
        existing.write_bytes(b"FOREIGN CUSTOMER DATA")
        app = App.__new__(App)
        app.notes, app.path, app.dirty, app.lang = [self.note], self.path, True, "ja"
        app.commit_editor, app.refresh_list, app.status = Mock(), Mock(), Mock()
        app.error = Mock()
        with patch("main.filedialog.asksaveasfilename", return_value=str(existing)):
            self.assertFalse(app.save_as())
        self.assertEqual(existing.read_bytes(), b"FOREIGN CUSTOMER DATA")
        self.assertEqual(app.path, self.path)
        self.assertTrue(app.dirty)
        app.error.assert_called_once()
        from main import STRINGS
        self.assertEqual(STRINGS["ja"][24], "名前を付けて保存")
        self.assertEqual(STRINGS["en"][24], "Save As")

    def test_save_as_concurrent_create_preserves_other_process_file(self):
        original = self.path
        save_notes(original, [self.note])
        old_bytes = original.read_bytes()
        app = App.__new__(App)
        app.notes, app.path, app.dirty, app.lang = [self.note], original, True, "en"
        app.commit_editor, app.refresh_list, app.status = Mock(), Mock(), Mock()
        app.error = Mock()
        destination = Path(self.tmp.name) / "raced.json"
        actual_link = os.link

        def competing_create(src, dst):
            Path(dst).write_bytes(b"OTHER PROCESS DATA")
            return actual_link(src, dst)

        with patch("main.filedialog.asksaveasfilename", return_value=str(destination)),              patch("main.os.link", side_effect=competing_create):
            self.assertFalse(app.save_as())
        self.assertEqual(destination.read_bytes(), b"OTHER PROCESS DATA")
        self.assertEqual(original.read_bytes(), old_bytes)
        self.assertEqual(app.path, original)
        self.assertTrue(app.dirty)
        self.assertEqual(list(Path(self.tmp.name).glob(".notes-*")), [])
        app.error.assert_called_once()

    def test_exclusive_create_failure_leaves_no_partial_output(self):
        from main import save_notes_new
        destination = Path(self.tmp.name) / "denied.json"
        with patch("main.os.link", side_effect=PermissionError("Hardlinks unavailable")):
            with self.assertRaises(PermissionError):
                save_notes_new(destination, [self.note])
        self.assertFalse(destination.exists())
        self.assertEqual(list(Path(self.tmp.name).glob(".notes-*")), [])

    def test_restore_backup_concurrent_create_preserves_competing_file(self):
        backup = Path(self.tmp.name) / "source.json.bak"
        save_notes(backup, [self.note])
        destination = Path(self.tmp.name) / "restore-raced.json"
        app = App.__new__(App)
        app.notes, app.path, app.dirty, app.lang = [], self.path, True, "ja"
        app.confirm, app.error = Mock(return_value=True), Mock()
        actual_link = os.link

        def competing_create(src, dst):
            Path(dst).write_bytes(b"DO NOT REPLACE")
            return actual_link(src, dst)

        with patch("main.filedialog.askopenfilename", return_value=str(backup)),              patch("main.filedialog.asksaveasfilename", return_value=str(destination)),              patch("main.os.link", side_effect=competing_create):
            app.restore_backup()
        self.assertEqual(destination.read_bytes(), b"DO NOT REPLACE")
        self.assertEqual(app.notes, [])
        self.assertEqual(app.path, self.path)
        self.assertTrue(app.dirty)
        app.error.assert_called_once()

    def test_txt_export_to_unused_filename_preserves_notes_database(self):
        save_notes(self.path, [self.note])
        original = self.path.read_bytes()
        destination = Path(self.tmp.name) / "new-export.txt"
        app = App.__new__(App)
        app.notes, app.current, app.path = [self.note], self.note["id"], self.path
        app.lang, app.dirty = "en", True
        app.commit_editor, app.status, app.error = Mock(), Mock(), Mock()
        with patch("main.filedialog.asksaveasfilename", return_value=str(destination)):
            app.export()
        self.assertEqual(destination.read_text(encoding="utf-8"), "Project\n\nDraft text\n")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(app.dirty)
        app.error.assert_not_called()

    def test_txt_export_concurrent_create_cannot_clobber_foreign_file(self):
        destination = Path(self.tmp.name) / "race-export.txt"
        app = App.__new__(App)
        app.notes, app.current, app.path = [self.note], self.note["id"], self.path
        app.lang, app.dirty = "ja", True
        app.commit_editor, app.status, app.error = Mock(), Mock(), Mock()
        real_link = os.link

        def competing_create(src, dst):
            Path(dst).write_bytes(b"FOREIGN DATA")
            return real_link(src, dst)

        with patch("main.filedialog.asksaveasfilename", return_value=str(destination)), \
             patch("main.os.link", side_effect=competing_create):
            app.export()
        self.assertEqual(destination.read_bytes(), b"FOREIGN DATA")
        self.assertTrue(app.dirty)
        self.assertEqual(list(Path(self.tmp.name).glob(".notes-*")), [])
        app.error.assert_called_once()

    def test_txt_export_hardlink_unavailable_fails_closed(self):
        destination = Path(self.tmp.name) / "denied-export.txt"
        app = App.__new__(App)
        app.notes, app.current, app.path = [self.note], self.note["id"], self.path
        app.lang, app.dirty = "en", True
        app.commit_editor, app.status, app.error = Mock(), Mock(), Mock()
        with patch("main.filedialog.asksaveasfilename", return_value=str(destination)), \
             patch("main.os.link", side_effect=PermissionError("hardlink denied")):
            app.export()
        self.assertFalse(destination.exists())
        self.assertTrue(app.dirty)
        self.assertEqual(list(Path(self.tmp.name).glob(".notes-*")), [])
        app.error.assert_called_once()

    def test_schema1_backward_compatibility(self):
        save_notes(self.path, [self.note])
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["schema"], 1)
        self.assertEqual(read_notes(self.path), ([self.note], False))

    def test_tags_and_favorites_persist_with_schema2(self):
        decorated = {**self.note, "tags": ["Work", "研究"], "favorite": True}
        save_notes(self.path, [decorated])
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["schema"], 2)
        self.assertEqual(read_notes(self.path), ([decorated], False))
        self.assertEqual(search_notes([decorated], "研究"), [decorated])
        self.assertEqual(search_notes([decorated], "work"), [decorated])

    def test_schema1_metadata_injection_is_rejected(self):
        invalid = {**self.note, "favorite": True}
        self.path.write_text(json.dumps({"schema": 1, "notes": [invalid]}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Schema 1"):
            read_notes(self.path)

    def test_malformed_metadata_rejected_without_writing(self):
        invalid_values = [
            {"favorite": 1}, {"tags": "work"}, {"tags": ["work", "WORK"]},
            {"tags": [" " ]}, {"tags": ["a"] * 9}, {"tags": ["x" * 31]},
            {"tags": ["broken" + chr(0xD800)]},
        ]
        for metadata in invalid_values:
            with self.subTest(metadata=str(metadata).encode("ascii", "backslashreplace")):
                with self.assertRaises(ValueError):
                    save_notes(self.path, [{**self.note, **metadata}])
                self.assertFalse(self.path.exists())

    def test_tag_input_validation(self):
        self.assertEqual(normalize_tags("  Work, 研究 、 Personal  "), ["Work", "研究", "Personal"])
        for value in ("same,SAME", ",".join(str(i) for i in range(9)), "x" * 31):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalize_tags(value)

    def test_commit_editor_keeps_existing_content_and_marks_dirty(self):
        app = App.__new__(App)
        app.notes, app.current, app.dirty = [dict(self.note)], self.note["id"], False
        app.title, app.body, app.tag_text = Mock(), Mock(), Mock()
        app.title.get.return_value = self.note["title"]
        app.body.get.return_value = self.note["body"]
        app.tag_text.get.return_value = "Work, 研究"
        app.commit_editor()
        self.assertEqual(app.notes[0]["tags"], ["Work", "研究"])
        self.assertEqual(app.notes[0]["body"], self.note["body"])
        self.assertTrue(app.dirty)

    def test_favorite_toggle_is_persistent_and_reversible(self):
        app = App.__new__(App)
        app.notes, app.current, app.dirty = [dict(self.note)], self.note["id"], False
        app.lang, app.status, app.favorite_button = "en", Mock(), Mock()
        app.commit_editor = lambda: None
        app.refresh_list = Mock()
        app.toggle_favorite()
        self.assertTrue(app.notes[0]["favorite"])
        self.assertTrue(app.dirty)
        app.toggle_favorite()
        self.assertNotIn("favorite", app.notes[0])

    def test_favorites_then_recent_order(self):
        a, b, c = new_note(), new_note(), new_note()
        a["title"], b["title"], c["title"] = "Old", "Favorite", "Recent"
        b["favorite"] = True
        app = App.__new__(App)
        app.notes, app.current, app.loading = [a, b, c], None, False
        app.recent_ids = [c["id"], a["id"]]
        app.query, app.listbox = Mock(), Mock()
        app.query.get.return_value = ""
        app.refresh_list()
        self.assertEqual(app.visible, [b["id"], c["id"], a["id"]])
        self.assertEqual(app.listbox.insert.call_args_list[0].args, ("end", "★ Favorite"))


if __name__ == "__main__":
    unittest.main()
