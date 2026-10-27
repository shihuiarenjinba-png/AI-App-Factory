"""Offline contract checks for immutable APP EXE -> MSIX handoff."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.prebuilt_msix import approved_identity, verify_prebuilt, download_artifact


class PinnedExeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.slug = "sample-tool"
        self.branch = "codex/factory-autoloop-20261026"
        self.product = self.root / "products" / self.slug
        (self.product / "store").mkdir(parents=True)
        (self.product / "manifest.json").write_text(
            '{"kind":"app","slug":"sample-tool","entry":"main.py"}', encoding="utf-8")
        self.git("init", "-q")
        self.git("config", "user.name", "QA")
        self.git("config", "user.email", "qa@example.invalid")
        self.git("checkout", "-qb", self.branch)
        self.git("add", ".")
        self.git("commit", "-qm", "committed Factory product")
        self.sha = self.git("rev-parse", "HEAD")
        self.exe_dir = self.root / "exe"
        self.exe_dir.mkdir()
        self.exe = self.exe_dir / (self.slug + ".exe")
        self.exe.write_bytes(b"MZ" + b"p" * 1200)
        self.digest = hashlib.sha256(self.exe.read_bytes()).hexdigest()
        self.identity = {
            "reviewed": True, "source": "partner_center",
            "product_type": "APP", "source_factory": "AI-App-Factory",
            "source_repository": "shihuiarenjinba-png/AI-App-Factory",
            "source_branch": self.branch, "source_sha": self.sha,
            "expected_head_sha": self.sha, "slug": self.slug,
            "display_name": "Sample Tool", "request_id": "app-request-1234",
            "package_kind": "exe", "package_sha256": self.digest,
            "package_bytes": self.exe.stat().st_size,
        }
        self.write_identity()
        self.git("add", ".")
        self.git("commit", "-qm", "store: return verified Partner Center identity")
        self.receipt = {
            "schema_version": 1, "stage": "PRE_IDENTITY_WINDOWS_EXE",
            "status": "EXE_QA_UNSIGNED",
            "source_repository": "shihuiarenjinba-png/AI-App-Factory",
            "source_sha": self.sha, "product_type": "APP",
            "slug": self.slug, "display_name": "Sample Tool",
            "executable": self.slug + ".exe",
            "official_identity_status": "NOT_COLLECTED", "store_id": None,
            "msix_status": "NOT_BUILT", "executable_bytes": self.exe.stat().st_size,
            "executable_sha256": self.digest,
        }
        self.write_receipt()
        env = patch.dict(os.environ, {
            "GITHUB_REF_NAME": self.branch, "GITHUB_REF": "refs/heads/" + self.branch,
        })
        env.start()
        self.addCleanup(env.stop)

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.root), *args], text=True).strip()

    def write_identity(self):
        (self.product / "store" / "approved-identity.json").write_text(
            json.dumps(self.identity), encoding="utf-8")

    def write_receipt(self):
        (self.exe_dir / "exe-receipt.json").write_text(
            json.dumps(self.receipt), encoding="utf-8")

    def test_accepts_exact_exe_bytes_from_source_commit(self):
        identity = approved_identity(self.root, self.slug)
        self.assertEqual(verify_prebuilt(self.root, self.slug, self.exe_dir, identity), self.exe)

    def test_wrong_exe_bytes_are_blocked(self):
        self.exe.write_bytes(self.exe.read_bytes() + b"tamper")
        with self.assertRaisesRegex(ValueError, "size differs"):
            verify_prebuilt(self.root, self.slug, self.exe_dir, approved_identity(self.root, self.slug))

    def test_forged_receipt_is_blocked(self):
        self.receipt["source_sha"] = "a" * 40
        self.write_receipt()
        with self.assertRaisesRegex(ValueError, "receipt does not match"):
            verify_prebuilt(self.root, self.slug, self.exe_dir, approved_identity(self.root, self.slug))

    def test_different_exe_sha_in_approval_is_blocked(self):
        identity = approved_identity(self.root, self.slug)
        identity["package_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
            verify_prebuilt(self.root, self.slug, self.exe_dir, identity)

    def test_wrong_source_branch_is_blocked(self):
        with patch.dict(os.environ, {"GITHUB_REF_NAME": "codex/another-branch"}):
            with self.assertRaisesRegex(ValueError, "source branch differs"):
                approved_identity(self.root, self.slug)

    def test_unrelated_commit_after_identity_return_is_blocked(self):
        (self.root / "unrelated.txt").write_text("not part of Identity")
        self.git("add", ".")
        self.git("commit", "-qm", "unexpected change")
        with self.assertRaisesRegex(ValueError, "sole commit"):
            approved_identity(self.root, self.slug)

    def test_invalid_run_id_fails_before_network(self):
        with self.assertRaisesRegex(ValueError, "run ID"):
            download_artifact(self.root, self.slug, "123;bad", self.root / "download")

    def test_no_prebuilt_means_no_msix_rebuild(self):
        from tools.build_windows_msix import build
        with self.assertRaisesRegex(ValueError, "pinned pre-Identity EXE directory required"):
            with patch("tools.build_windows_msix.sys.platform", "win32"):
                build(self.root, self.slug, self.root / "out")


if __name__ == "__main__":
    unittest.main()
