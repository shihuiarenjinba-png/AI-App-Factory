"""Pre-Identity product selection must not require an invented Store ID."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.preidentity_product_select import select
from tools.msix_push_product import SelectionHold


class PreIdentitySelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        product = self.root / "products" / "example-tool"
        product.mkdir(parents=True)
        self.manifest = product / "manifest.json"
        self.manifest.write_text(json.dumps({
            "kind": "app", "slug": "example-tool", "entry": "main.py",
        }), encoding="utf-8")

    def test_manual_app_without_store_identity_is_selected(self):
        self.assertEqual(
            select("workflow_dispatch", "example-tool", "", "", self.root),
            "example-tool")
        self.assertFalse((self.root / "products/example-tool/store/approved-identity.json").exists())

    def test_wrong_lane_holds(self):
        self.manifest.write_text('{"kind":"game","slug":"example-tool","entry":"main.py"}')
        with self.assertRaises(SelectionHold):
            select("workflow_dispatch", "example-tool", "", "", self.root)

    def test_invalid_manual_slug_holds(self):
        with self.assertRaises(SelectionHold):
            select("workflow_dispatch", "../example-tool", "", "", self.root)

    def test_missing_manifest_holds(self):
        self.manifest.unlink()
        with self.assertRaises(SelectionHold):
            select("workflow_dispatch", "example-tool", "", "", self.root)


if __name__ == "__main__":
    unittest.main()
