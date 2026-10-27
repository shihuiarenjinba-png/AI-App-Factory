"""Offline regression tests for the real Windows EXE pre-Identity stage."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.build_windows_exe import build_exe, verify_source


class PreIdentityWindowsBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q", "-b", "codex/factory-autoloop-20261026")
        self.git("config", "user.name", "CI Fixture")
        self.git("config", "user.email", "ci@example.invalid")
        (self.root / "factory").mkdir()
        (self.root / "factory/config.json").write_text('{"kind":"app"}')
        (self.root / "proposals").mkdir()
        (self.root / "proposals/example-tool.json").write_text(
            '{"slug":"example-tool","title":"Example Tool"}')
        self.product = self.root / "products" / "example-tool"
        (self.product / "tests").mkdir(parents=True)
        (self.product / "manifest.json").write_text(
            '{"kind":"app","slug":"example-tool","entry":"main.py"}')
        (self.product / "main.py").write_text("print('offline example')\n")
        (self.product / "tests/test_smoke.py").write_text("def test_smoke(): assert True\n")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture: committed app source")
        self.sha = self.git("rev-parse", "HEAD")
        self.output = self.root / "exports" / "preidentity"

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    @staticmethod
    def fake_builder(source, slug, work, root):
        destination = work / "dist"
        destination.mkdir(parents=True)
        (destination / (slug + ".exe")).write_bytes(b"MZ" + b"real-windows-binary-fixture" * 100)

    def test_committed_app_without_identity_is_eligible_for_exe(self):
        source = verify_source(self.root, "example-tool", self.sha)
        self.assertEqual(source, self.product / "main.py")
        self.assertFalse((self.product / "store/approved-identity.json").exists())

    def test_preidentity_build_produces_real_bytes_and_receipt(self):
        with patch("tools.build_windows_exe.sys.platform", "win32"), patch(
            "tools.build_windows_exe._run_pyinstaller", side_effect=self.fake_builder
        ):
            receipt = build_exe(self.root, "example-tool", self.sha, self.output)
        executable = self.output / "example-tool.exe"
        self.assertTrue(executable.is_file())
        self.assertEqual(receipt["executable_sha256"],
                         hashlib.sha256(executable.read_bytes()).hexdigest())
        self.assertEqual(json.loads((self.output / "exe-receipt.json").read_text()), receipt)
        self.assertEqual(receipt["status"], "EXE_QA_UNSIGNED")
        self.assertEqual(receipt["display_name"], "Example Tool")
        self.assertIsNone(receipt["store_id"])
        self.assertEqual(receipt["msix_status"], "NOT_BUILT")
        with patch("tools.build_windows_exe.sys.platform", "win32"):
            with self.assertRaisesRegex(ValueError, "overwrite"):
                build_exe(self.root, "example-tool", self.sha, self.output)

    def test_missing_identity_never_becomes_store_ready(self):
        with patch("tools.build_windows_exe.sys.platform", "win32"), patch(
            "tools.build_windows_exe._run_pyinstaller", side_effect=self.fake_builder
        ):
            result = build_exe(self.root, "example-tool", self.sha, self.output)
        self.assertEqual(result["official_identity_status"], "NOT_COLLECTED")
        self.assertNotIn("READY_FOR_STORE", result.values())

    def test_wrong_source_sha_rejected(self):
        with self.assertRaisesRegex(ValueError, "source HEAD"):
            verify_source(self.root, "example-tool", "f" * 40)

    def test_dirty_source_rejected(self):
        (self.product / "main.py").write_text("print('changed')\n")
        with self.assertRaisesRegex(ValueError, "differs"):
            verify_source(self.root, "example-tool", self.sha)

    def test_untracked_source_rejected(self):
        (self.product / "extra.py").write_text("print('extra')\n")
        with self.assertRaisesRegex(ValueError, "differs"):
            verify_source(self.root, "example-tool", self.sha)

    def test_dirty_product_title_rejected(self):
        (self.root / "proposals/example-tool.json").write_text(
            '{"slug":"example-tool","title":"Changed Tool"}')
        with self.assertRaisesRegex(ValueError, "differs"):
            verify_source(self.root, "example-tool", self.sha)

    def test_wrong_product_kind_rejected(self):
        (self.product / "manifest.json").write_text(
            '{"kind":"game","slug":"example-tool","entry":"main.py"}')
        with self.assertRaises(ValueError):
            verify_source(self.root, "example-tool", self.sha)

    def test_unsafe_slug_rejected(self):
        for slug in ("../example-tool", "EXAMPLE-TOOL", "x"):
            with self.subTest(slug=slug), self.assertRaises(ValueError):
                verify_source(self.root, slug, self.sha)

    def test_non_windows_build_holds(self):
        with patch("tools.build_windows_exe.sys.platform", "linux"):
            with self.assertRaisesRegex(ValueError, "Windows runner"):
                build_exe(self.root, "example-tool", self.sha, self.output)

    def test_missing_executable_holds_without_partial_output(self):
        with patch("tools.build_windows_exe.sys.platform", "win32"), patch(
            "tools.build_windows_exe._run_pyinstaller", return_value=None
        ):
            with self.assertRaisesRegex(ValueError, "no regular Windows EXE"):
                build_exe(self.root, "example-tool", self.sha, self.output)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
