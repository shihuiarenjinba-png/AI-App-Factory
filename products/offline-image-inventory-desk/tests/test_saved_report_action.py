"""Saved customer report action: local-only, fail-closed, bilingual."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main as app


def desk_stub():
    desk = app.Desk.__new__(app.Desk)
    desk.root = None
    desk.language = "en"
    desk.comparison = {"summary": {}}
    desk.last_html_report_path = None
    desk.status = MagicMock()
    desk.error = MagicMock()
    desk.open_report_button = MagicMock()
    desk.report_path_label = MagicMock()
    desk.comparison_open_report_button = MagicMock()
    desk.comparison_report_path_label = MagicMock()
    desk.close_comparison_window = MagicMock()
    desk.t = lambda key: app.LABELS[desk.language][key]
    return desk


class SavedReportTests(unittest.TestCase):
    def test_success_opens_only_local_html_and_shows_location_in_both_languages(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "納品書.html"
            desk = desk_stub()
            def write_report(path, *args):
                Path(path).write_text("<html>client</html>", encoding="utf-8")
            with patch.object(app.filedialog, "asksaveasfilename", return_value=str(report)), \
                 patch.object(app.snapshots, "write_html_delivery", side_effect=write_report):
                desk.export_delivery_html()
            self.assertEqual(desk.last_html_report_path, report)
            desk.open_report_button.configure.assert_called_with(state="normal")
            desk.comparison_open_report_button.configure.assert_called_with(state="normal")
            self.assertIn(report.name, desk.report_path_label.configure.call_args.kwargs["text"])
            self.assertIn(report.name, desk.comparison_report_path_label.configure.call_args.kwargs["text"])
            with patch.object(app.webbrowser, "open", return_value=True) as opener:
                desk.open_saved_report()
            uri = opener.call_args.args[0]
            self.assertTrue(uri.startswith("file:///"))
            self.assertNotIn("http:", uri)
            self.assertNotIn("https:", uri)
            desk.language = "ja"
            desk._update_saved_report_ui()
            self.assertIn("保存先", desk.report_path_label.configure.call_args.kwargs["text"])
            report.unlink()
            desk.open_saved_report()
            self.assertIsNone(desk.last_html_report_path)
            desk.open_report_button.configure.assert_called_with(state="disabled")
            desk.comparison_open_report_button.configure.assert_called_with(state="disabled")
            self.assertIn("見つからない", desk.status.set.call_args.args[0])

    def test_failed_write_clears_previous_success_and_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            desk = desk_stub()
            old = Path(tmp) / "old.html"
            old.write_text("old", encoding="utf-8")
            desk.last_html_report_path = old
            target = Path(tmp) / "denied.html"
            with patch.object(app.filedialog, "asksaveasfilename", return_value=str(target)), \
                 patch.object(app.snapshots, "write_html_delivery", side_effect=PermissionError("denied")):
                desk.export_delivery_html()
            self.assertIsNone(desk.last_html_report_path)
            self.assertIsNone(desk.comparison)
            desk.open_report_button.configure.assert_called_with(state="disabled")
            self.assertEqual(desk.status.set.call_args.args[0], desk.t("snap_html_failed"))
            desk.error.assert_called_once()
            self.assertFalse(target.exists())

    def test_local_uri_rejects_missing_non_html_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            valid = folder / "client.html"
            valid.write_text("ok", encoding="utf-8")
            self.assertTrue(app.local_report_uri(valid).startswith("file:///"))
            with self.assertRaises(ValueError):
                app.local_report_uri(folder / "missing.html")
            with self.assertRaises(ValueError):
                app.local_report_uri(folder / "client.txt")
            alias = folder / "alias.html"
            try:
                alias.symlink_to(valid)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises(ValueError):
                app.local_report_uri(alias)

    def test_restart_starts_with_no_stale_report(self):
        desk = desk_stub()
        desk._update_saved_report_ui()
        self.assertIsNone(desk.last_html_report_path)
        desk.open_report_button.configure.assert_called_with(state="disabled")
        with patch.object(app.webbrowser, "open") as opener:
            desk.open_saved_report()
        opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
