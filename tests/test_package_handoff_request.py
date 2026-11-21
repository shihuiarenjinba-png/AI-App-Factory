"""Offline contract tests for the APP package handoff producer."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from package_handoff_request import make_request, BRANCH


class PackageHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git("init", "-q", "-b", BRANCH)
        self.git("config", "user.name", "Test Operator")
        self.git("config", "user.email", "test@example.invalid")
        (self.root / "factory").mkdir()
        (self.root / "proposals").mkdir()
        product = self.root / "products" / "example-product"
        (product / "tests").mkdir(parents=True)
        (self.root / "factory/config.json").write_text(
            '{"kind":"app"}', encoding="utf-8")
        (self.root / "proposals/example-product.json").write_text(
            '{"slug":"example-product","title":"Example Utility"}', encoding="utf-8")
        (product / "manifest.json").write_text(
            '{"slug":"example-product","kind":"app","entry":"main.py"}',
            encoding="utf-8")
        (product / "main.py").write_text("print('example')\n", encoding="utf-8")
        (product / "tests/test_smoke.py").write_text(
            "def test_example(): return True\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "test snapshot")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    def request(self, **changes):
        args = {"root": self.root, "slug": "example-product",
                "request_id": "app-20261026-001"}
        args.update(changes)
        return make_request(**args)

    def test_matches_provisioner_intake_schema(self):
        job = self.request()
        self.assertEqual(set(job), {
            "schema_version", "request_id", "product_type", "source_factory",
            "source_repository", "source_branch", "source_sha", "slug",
            "display_name", "target_owner", "dry_run", "requested_actions",
        })
        self.assertEqual(job["product_type"], "APP")
        self.assertEqual(job["source_branch"], BRANCH)
        self.assertEqual(job["source_sha"], self.git("rev-parse", "HEAD"))
        self.assertEqual(job["display_name"], "Example Utility")
        self.assertIs(job["dry_run"], True)
        self.assertEqual(job["requested_actions"], [
            "BUILD_WINDOWS", "INSPECT_PACKAGE", "LOOKUP_OFFICIAL_IDENTITY",
            "PROPOSE_GITHUB_RETURN",
        ])

    def test_same_commit_deterministic(self):
        self.assertEqual(self.request(), self.request())

    def test_reject_dirty_product(self):
        (self.root / "products/example-product/main.py").write_text("modified")
        with self.assertRaises(ValueError):
            self.request()

    def test_reject_untracked_product(self):
        (self.root / "products/example-product/new.txt").write_text("untracked")
        with self.assertRaises(ValueError):
            self.request()

    def test_reject_wrong_branch(self):
        self.git("switch", "-qc", "codex/unapproved")
        with self.assertRaises(ValueError):
            self.request()

    def test_reject_wrong_lane(self):
        (self.root / "factory/config.json").write_text('{"kind":"game"}')
        self.git("add", ".")
        self.git("commit", "-qm", "wrong lane")
        with self.assertRaises(ValueError):
            self.request()

    def test_reject_missing_product(self):
        with self.assertRaises(ValueError):
            self.request(slug="another-product")

    def test_reject_traversal_and_unsafe_request(self):
        for changes in ({"slug": "../unsafe"}, {"request_id": "../unsafe"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.request(**changes)

    def test_reject_uncommitted_proposal_title(self):
        (self.root / "proposals/example-product.json").write_text(
            '{"slug":"example-product","title":"Fake Name"}')
        with self.assertRaises(ValueError):
            self.request()

    def test_cli_emits_only_dry_run(self):
        # This producer never builds or writes to GitHub.
        script = Path(__file__).resolve().parents[1] / "package_handoff_request.py"
        result = subprocess.run(
            [sys.executable, str(script), "--root", str(self.root),
             "--slug", "example-product", "--request-id", "app-20261026-001"],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["dry_run"])
        self.assertEqual(self.git("status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
