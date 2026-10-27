"""End-to-end offline contract for reusing real EXE bytes in a gated MSIX."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools.build_windows_exe import build_exe
from tools.build_windows_msix_from_exe import build_from_exe, inspect_exe_evidence

PNG = b"\x89PNG\r\n\x1a\n" + b"fixture"
IDENTITY = {
    "reviewed": True, "source": "partner_center", "store_id": "9PTEST123",
    "name": "Example.Company.App", "publisher": "CN=TEST",
    "version": "1.0.0.0", "verified_by": "local-operator",
    "evidence_url": "https://partner.microsoft.com/dashboard/products/demo",
}


class PinnedExeMsixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.slug = "example-tool"
        self.branch = "codex/app-qa-fixture"
        self.request_id = "app-qa-request-001"
        self.git("init", "-q", "-b", self.branch)
        self.git("config", "user.name", "CI Fixture")
        self.git("config", "user.email", "ci@example.invalid")
        (self.root / "factory").mkdir()
        (self.root / "factory/config.json").write_text('{"kind":"app"}')
        (self.root / "proposals").mkdir()
        (self.root / "proposals/example-tool.json").write_text(
            '{"slug":"example-tool","title":"Example Tool"}')
        self.product = self.root / "products" / self.slug
        (self.product / "tests").mkdir(parents=True)
        (self.product / "manifest.json").write_text(
            '{"kind":"app","slug":"example-tool","entry":"main.py"}')
        (self.product / "main.py").write_text("print('hello')\n")
        (self.product / "tests/test_smoke.py").write_text("def test_smoke(): assert True\n")
        self.git("add", ".")
        self.git("commit", "-qm", "committed pre-Identity source")
        self.source_sha = self.git("rev-parse", "HEAD")
        self.evidence = self.root / "exports" / "preidentity"
        with patch("tools.build_windows_exe.sys.platform", "win32"), patch(
            "tools.build_windows_exe._run_pyinstaller", side_effect=self.fake_exe
        ):
            self.exe_receipt = build_exe(
                self.root, self.slug, self.source_sha, self.evidence,
                request_id=self.request_id)
        store = self.product / "store"
        (store / "assets").mkdir(parents=True)
        (store / "approved-identity.json").write_text(json.dumps(IDENTITY))
        for name in ("StoreLogo.png", "Square150.png", "Square44.png"):
            (store / "assets" / name).write_bytes(PNG)
        self.git("add", ".")
        self.git("commit", "-qm", "official Identity and approved assets return")
        self.output = self.root / "exports" / "msix"

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    @staticmethod
    def fake_exe(source, slug, work, root):
        dest = work / "dist"
        dest.mkdir(parents=True)
        (dest / (slug + ".exe")).write_bytes(b"MZ" + b"windows-pe-test" * 200)

    @staticmethod
    def fake_makeappx(layout, destination):
        with zipfile.ZipFile(destination, "w") as z:
            z.write(layout / "AppxManifest.xml", "AppxManifest.xml")
            z.write(layout / "example-tool.exe", "example-tool.exe")
            z.writestr("AppxBlockMap.xml", "<BlockMap/>")
            z.writestr("[Content_Types].xml", "<Types/>")

    def build(self):
        with patch("tools.build_windows_msix_from_exe.sys.platform", "win32"), patch(
            "tools.build_windows_msix_from_exe.pack_with_makeappx",
            side_effect=self.fake_makeappx
        ):
            return build_from_exe(
                self.root, self.slug, self.evidence, self.output,
                self.source_sha, self.branch, self.request_id)

    def test_prebuilt_exe_is_used_byte_for_byte_in_msix(self):
        result = self.build()
        package = self.output / "example-tool.msix"
        self.assertTrue(package.is_file())
        with zipfile.ZipFile(package) as z:
            self.assertEqual(z.read("example-tool.exe"),
                             (self.evidence / "example-tool.exe").read_bytes())
        self.assertEqual(result["request_id"], self.request_id)
        self.assertEqual(result["source_sha"], self.source_sha)
        self.assertEqual(result["source_branch"], self.branch)
        self.assertEqual(result["executable_sha256"], self.exe_receipt["executable_sha256"])
        self.assertEqual(result["package_sha256"], hashlib.sha256(package.read_bytes()).hexdigest())
        self.assertEqual(json.loads((self.output / "msix-build-receipt.json").read_text()), result)
        self.assertEqual(result["status"], "QA_UNSIGNED")
        self.assertFalse(result["store_submitted"])
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.build()

    def test_wrong_request_id_blocks_package(self):
        with self.assertRaisesRegex(ValueError, "immutable contract"):
            inspect_exe_evidence(self.root, self.slug, self.evidence,
                                 self.source_sha, self.branch, "other-request")

    def test_wrong_source_sha_blocks_package(self):
        with self.assertRaises(ValueError):
            inspect_exe_evidence(self.root, self.slug, self.evidence,
                                 "f" * 40, self.branch, self.request_id)

    def test_wrong_branch_blocks_package(self):
        with self.assertRaisesRegex(ValueError, "branch"):
            inspect_exe_evidence(self.root, self.slug, self.evidence,
                                 self.source_sha, "codex/other-branch", self.request_id)

    def test_corrupted_exe_blocks_package(self):
        exe = self.evidence / "example-tool.exe"
        with exe.open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaisesRegex(ValueError, "byte size mismatch"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_changed_app_code_after_exe_blocks_package(self):
        (self.product / "main.py").write_text("print('changed')\n")
        self.git("add", ".")
        self.git("commit", "-qm", "changed app after EXE build")
        with self.assertRaisesRegex(ValueError, "changed since pinned"):
            self.build()

    def test_missing_official_identity_blocks_package(self):
        (self.product / "store/approved-identity.json").unlink()
        with self.assertRaisesRegex(ValueError, "Identity missing"):
            self.build()

    def test_missing_request_id_in_receipt_blocks_package(self):
        receipt = self.evidence / "exe-receipt.json"
        data = json.loads(receipt.read_text())
        data["request_id"] = None
        receipt.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "immutable contract"):
            self.build()

    def test_manifest_only_zip_is_not_a_real_msix(self):
        def bad_makeappx(layout, destination):
            with zipfile.ZipFile(destination, "w") as z:
                z.write(layout / "AppxManifest.xml", "AppxManifest.xml")
        with patch("tools.build_windows_msix_from_exe.sys.platform", "win32"), patch(
            "tools.build_windows_msix_from_exe.pack_with_makeappx",
            side_effect=bad_makeappx
        ):
            with self.assertRaisesRegex(ValueError, "metadata"):
                build_from_exe(self.root, self.slug, self.evidence, self.output,
                               self.source_sha, self.branch, self.request_id)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
