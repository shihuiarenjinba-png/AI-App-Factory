"""Commercial metadata regression tests: no Tk display required."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import App, new_note, normalize_tags, read_notes, save_notes, search_notes, validate_notes


class CommercialMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "notes.json"
        self.note = new_note()
        self.note.update(title="Project", body="Draft text")

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
