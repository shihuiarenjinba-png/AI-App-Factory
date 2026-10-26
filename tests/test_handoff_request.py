import json
import tempfile
import unittest
from pathlib import Path
from handoff_request import request


def prepared(root, kind):
    (root / "factory").mkdir()
    (root / "factory/config.json").write_text(json.dumps({"kind": kind}), encoding="utf-8")
    (root / "products" / "example-product").mkdir(parents=True)
    (root / "products" / "example-product" / "manifest.json").write_text(
        json.dumps({"kind": kind, "slug": "example-product", "entry": "main.py"}),
        encoding="utf-8")


def make(root, **overrides):
    args = {"root": root, "slug": "example-product", "request_id": "request-001",
            "repository_owner": "shihuiarenjinba-png", "repository_name": "product-example",
            "template_repository": "shihuiarenjinba-png/example-template",
            "source_sha": "a" * 40, "review_reference": "review-001"}
    args.update(overrides)
    return request(**args)


class HandoffTest(unittest.TestCase):
    def test_dry_run_contract(self):
        for kind, typ in (("app", "APP"), ("game", "GAME")):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                prepared(root, kind)
                out = make(root)
                self.assertEqual(out["product_type"], typ)
                self.assertTrue(out["dry_run"])
                self.assertEqual(out["visibility"], "private")

    def test_wrong_product_type_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared(root, "app")
            (root / "products/example-product/manifest.json").write_text(
                json.dumps({"kind": "game", "slug": "example-product", "entry": "main.py"}),
                encoding="utf-8")
            with self.assertRaises(ValueError):
                make(root)

    def test_path_traversal_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared(root, "game")
            with self.assertRaises(ValueError):
                make(root, slug="../hacked")

    def test_invalid_source_sha_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared(root, "app")
            with self.assertRaises(ValueError):
                make(root, source_sha="short")

    def test_unknown_template_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared(root, "app")
            with self.assertRaises(ValueError):
                make(root, template_repository="not-a-repo")


if __name__ == "__main__":
    unittest.main()
