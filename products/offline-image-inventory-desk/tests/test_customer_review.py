"""Headless regression for customer-facing review, without fabricating buyer responses."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main as app
import demo_samples
import snapshot_compare as snapshots


class ReviewTests(unittest.TestCase):
    def test_bilingual_changed_only_and_full_evidence_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            before, after = demo_samples.populate_demo(Path(tmp))
            baseline = snapshots.capture_folder(before, app.inspect_image)
            current = snapshots.capture_folder(after, app.inspect_image)
            report = snapshots.compare_snapshots(baseline, current)
            en = app.comparison_view_rows(report, "en", changes_only=True)
            ja = app.comparison_view_rows(report, "ja", changes_only=True)
            self.assertEqual(len(en), 3)
            self.assertEqual(len(ja), 3)
            self.assertEqual({r[1] for r in en}, {"Added", "Removed", "Changed"})
            self.assertEqual({r[1] for r in ja}, {"追加", "削除", "変更"})
            self.assertEqual(len(app.comparison_view_rows(report, "ja")), 4)
            self.assertTrue(any(r[1] == "変更なし" for r in app.comparison_view_rows(report, "ja")))
            self.assertEqual(report["summary"], dict(ADDED=1, REMOVED=1, MODIFIED=1, UNCHANGED=1))
            self.assertTrue(all(len(r["old_sha256"]) in (0, 64) for r in report["changes"]))
            self.assertTrue(all(len(r["new_sha256"]) in (0, 64) for r in report["changes"]))
            with self.assertRaises(ValueError):
                app.comparison_view_rows(report, "unknown")

    def test_failed_scan_invalidates_old_report_and_closes_old_window(self):
        desk = app.Desk.__new__(app.Desk)
        desk.root = None
        desk.language = "ja"
        desk.baseline = {"schema": 1}
        desk.comparison = {"stale": True}
        desk.comparison_window = MagicMock()
        window = desk.comparison_window
        window.winfo_exists.return_value = True
        desk.status = MagicMock()
        desk.error = MagicMock()
        desk.t = lambda key: {"snap_compare": "比較", "snap_failed": "読取失敗"}[key]
        failed = {"errors": [{"relative_path": "invalid.png", "error": "ValueError"}]}
        with patch.object(app.filedialog, "askdirectory", return_value="C:/fixture"), \
             patch.object(app.snapshots, "capture_folder", return_value=failed):
            desk.compare_folder()
        window.destroy.assert_called_once()
        self.assertIsNone(desk.comparison_window)
        self.assertIsNone(desk.comparison)
        desk.status.set.assert_called_with("読取失敗")
        desk.error.assert_called_once()
        self.assertIn("invalid.png", desk.error.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
