"""Per-user bilingual preference regression: restart, corruption, atomic failure."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import user_preferences as prefs
import main as app


class LanguagePreferenceTests(unittest.TestCase):
    def test_restart_and_user_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "person-a"
            second = Path(tmp) / "person-b"
            with patch.dict(os.environ, {"OFFLINE_IMAGE_INVENTORY_CONFIG_DIR": str(first)}):
                self.assertEqual(app.load_language(), "en")
                app.save_language("ja")
                self.assertEqual(app.load_language(), "ja")
                self.assertEqual(json.loads(prefs.preference_path().read_text())["version"], 1)
                self.assertEqual(sorted(p.name for p in first.iterdir()), ["preferences.json"])
            with patch.dict(os.environ, {"OFFLINE_IMAGE_INVENTORY_CONFIG_DIR": str(second)}):
                self.assertEqual(app.load_language(), "en")
                app.save_language("en")
                self.assertEqual(app.load_language(), "en")
            with patch.dict(os.environ, {"OFFLINE_IMAGE_INVENTORY_CONFIG_DIR": str(first)}):
                self.assertEqual(app.load_language(), "ja", "Restart lost user preference")

    def test_corruption_schema_oversize_and_invalid_utf8_default_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"OFFLINE_IMAGE_INVENTORY_CONFIG_DIR": tmp}):
                path = prefs.preference_path()
                path.parent.mkdir(parents=True, exist_ok=True)
                for raw in (b"{bad", b"[]", b'{"version":1,"language":"xx"}',
                            b'{"version":true,"language":"ja"}',
                            b'{"version":1,"language":"ja"}' + b" " * 4096,
                            bytes([255])):
                    path.write_bytes(raw)
                    self.assertEqual(app.load_language(), "en")
                app.save_language("ja")
                self.assertEqual(app.load_language(), "ja")
                with self.assertRaises(ValueError):
                    app.save_language("fr")

    def test_atomic_write_failure_preserves_previous_setting(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"OFFLINE_IMAGE_INVENTORY_CONFIG_DIR": tmp}):
                app.save_language("ja")
                original = prefs.preference_path().read_bytes()
                with patch.object(prefs.os, "replace", side_effect=PermissionError("denied")):
                    with self.assertRaises(PermissionError):
                        app.save_language("en")
                self.assertEqual(prefs.preference_path().read_bytes(), original)
                self.assertEqual(app.load_language(), "ja")
                self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["preferences.json"])

    def test_linked_preferences_are_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = base / "target.json"
            target.write_text('{"version":1,"language":"ja"}', encoding="utf-8")
            settings = base / "settings"
            settings.mkdir()
            link = settings / "preferences.json"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks not available on this host")
            with patch.dict(os.environ, {"OFFLINE_IMAGE_INVENTORY_CONFIG_DIR": str(settings)}):
                self.assertEqual(app.load_language(), "en")
                with self.assertRaises(OSError):
                    app.save_language("en")
            self.assertEqual(json.loads(target.read_text())["language"], "ja")

    def test_toggle_reports_failed_save_without_crashing(self):
        from unittest.mock import MagicMock
        desk = app.Desk.__new__(app.Desk)
        desk.language = "en"
        desk.demo_mode = False
        desk.localize = MagicMock()
        desk.status = MagicMock()
        with patch.object(app, "save_language", side_effect=PermissionError("denied")):
            desk.toggle()
        self.assertEqual(desk.language, "ja")
        self.assertIn("保存できません", desk.status.set.call_args.args[0])
        desk.localize.assert_called_once()


if __name__ == "__main__":
    unittest.main()
