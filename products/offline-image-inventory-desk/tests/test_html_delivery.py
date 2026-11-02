"""Client HTML delivery report: safe offline previews and fail-closed evidence."""
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main as app
import snapshot_compare as snap
import html_delivery as customer
from buyer_validation_evidence import make_png


class HTMLDeliveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.old = self.base / "before"
        self.new = self.base / "after"
        self.old.mkdir()
        self.new.mkdir()

    def picture(self, folder, name, rgb=(2, 4, 6)):
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        make_png(path, rgb)
        return path

    def report(self):
        return snap.compare_snapshots(
            snap.capture_folder(self.old, app.inspect_image),
            snap.capture_folder(self.new, app.inspect_image))

    def test_four_states_bilingual_embedded_offline_and_unchanged_sources(self):
        for name in ("same.png", "changed.png", "removed.png"):
            self.picture(self.old, name)
        self.picture(self.new, "same.png")
        self.picture(self.new, "changed.png", (99, 30, 20))
        self.picture(self.new, "added.png", (15, 60, 20))
        evidence = self.report()
        self.assertEqual(evidence["summary"],
                         {"ADDED": 1, "REMOVED": 1, "MODIFIED": 1, "UNCHANGED": 1})
        original = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                    for root in (self.old, self.new) for p in root.rglob("*.png")}
        for lang, title in (("en", "Image delivery review"), ("ja", "納品画像の確認レポート")):
            path = self.base / ("client-" + lang + ".html")
            snap.write_html_delivery(path, evidence, app.atomic_write, lang)
            html = path.read_text(encoding="utf-8")
            self.assertIn(title, html)
            self.assertIn('data:image/png;base64,', html)
            self.assertIn("Content-Security-Policy", html)
            self.assertIn("default-src 'none'", html)
            self.assertNotIn("<script", html)
            self.assertNotIn('src="http', html)
            self.assertIn(path.name, html)
            self.assertIn("SHA-256", html)
        self.assertEqual(original, {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for root in (self.old, self.new) for p in root.rglob("*.png")})

    def test_missing_baseline_never_invents_old_photo(self):
        self.picture(self.old, "changed.png")
        self.picture(self.new, "changed.png", (200, 1, 1))
        evidence = self.report()
        shutil.rmtree(self.old)
        html = customer.render_html_delivery(evidence, "en")
        self.assertIn("Baseline image unavailable", html)
        self.assertEqual(html.count("data:image/png;base64,"), 1)

    def test_after_file_mutation_blocks_export_and_no_stale_success(self):
        path = self.picture(self.new, "new.png")
        evidence = self.report()
        path.write_bytes(path.read_bytes() + b"changed after comparison")
        target = self.base / "should-not-exist.html"
        with self.assertRaisesRegex(ValueError, "changed"):
            snap.write_html_delivery(target, evidence, app.atomic_write, "en")
        self.assertFalse(target.exists())

    def test_read_denied_and_missing_after_fail_closed(self):
        path = self.picture(self.new, "new.png")
        evidence = self.report()
        target = self.base / "blocked.html"
        with patch.object(snap, "full_hash", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                snap.write_html_delivery(target, evidence, app.atomic_write, "en")
        self.assertFalse(target.exists())
        path.unlink()
        with self.assertRaises(ValueError):
            snap.write_html_delivery(target, evidence, app.atomic_write, "ja")
        self.assertFalse(target.exists())

    def test_reject_symlink_traversal_and_source_output(self):
        path = self.picture(self.new, "new.png")
        evidence = self.report()
        with self.assertRaises(ValueError):
            snap.write_html_delivery(self.new / "report.html", evidence, app.atomic_write)
        link = self.new / "link.png"
        path.rename(link)
        try:
            path.symlink_to(link)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation unavailable")
        with self.assertRaises(ValueError):
            customer.render_html_delivery(evidence)
        evidence["changes"][0]["relative_path"] = "../escape.png"
        with self.assertRaises(ValueError):
            customer.render_html_delivery(evidence)

    def test_escapes_filename_and_never_embeds_baseline_from_snapshot(self):
        evidence = {
            "schema": 1, "old_root": str(self.base / "missing-before"), "new_root": str(self.new),
            "summary": {"ADDED": 0, "REMOVED": 1, "MODIFIED": 0, "UNCHANGED": 0},
            "changes": [{
                "relative_path": 'bad&<script>alert(1)</script>.png', "status": "REMOVED",
                "old_sha256": "a" * 64, "new_sha256": "",
                "old_dimensions": "1x1", "new_dimensions": "",
                "old_bytes": 100, "new_bytes": "",
            }],
        }
        html = customer.render_html_delivery(evidence)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("data:image/", html)

    def test_preview_size_cap_and_unsupported_language(self):
        p = self.picture(self.new, "large.png")
        p.write_bytes(p.read_bytes() + b"x" * (customer.MAX_PREVIEW_BYTES + 1))
        html = customer.render_html_delivery(self.report())
        self.assertIn("Preview omitted", html)
        self.assertNotIn("data:image/png;base64,", html)
        with self.assertRaises(ValueError):
            customer.render_html_delivery(self.report(), "fr")

    def test_gui_customer_html_is_in_step_three(self):
        source = Path(app.__file__).read_text(encoding="utf-8")
        self.assertIn("command=self.export_delivery_html", source)
        self.assertIn("self.html_button.configure(text=self.t(", source)
        self.assertIn('def export_delivery_html(self):', source)


if __name__ == "__main__":
    unittest.main()
