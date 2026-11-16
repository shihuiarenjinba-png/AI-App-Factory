import json
import tempfile
import unittest
from pathlib import Path

from tools.generate_package_assets import ASSET_SIZES, ensure_assets


class PackageAssetTests(unittest.TestCase):
    def test_generates_required_pngs_from_explicit_approved_config(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "packaging-assets").mkdir()
            (root / "products" / "focus-session-desk" / "store").mkdir(parents=True)
            (root / "packaging-assets" / "focus-session-desk.json").write_text(json.dumps({
                "schema_version": 1,
                "slug": "focus-session-desk",
                "approved": True,
                "kind": "focus",
                "background": "#162234",
                "accent": "#4CC9F0"
            }), encoding="utf-8")
            paths = ensure_assets(root, "focus-session-desk")
            self.assertEqual({p.name for p in paths}, set(ASSET_SIZES))
            for path in paths:
                self.assertTrue(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_unapproved_config_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "packaging-assets").mkdir()
            (root / "products" / "focus-session-desk" / "store").mkdir(parents=True)
            (root / "packaging-assets" / "focus-session-desk.json").write_text(json.dumps({
                "schema_version": 1, "slug": "focus-session-desk", "approved": False,
                "kind": "focus", "background": "#162234", "accent": "#4CC9F0"
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                ensure_assets(root, "focus-session-desk")


if __name__ == "__main__":
    unittest.main()
