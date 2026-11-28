"""Regression tests for exact source-to-request binding in package preflight."""
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

from scripts.package_source_preflight import inspect_source


def png_bytes(width, height):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + (b"\x00" * (width * 4)) for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


class PackageSourcePreflightTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "source"
        self.root.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Preflight QA")
        self.git("config", "user.email", "qa@example.invalid")

        self.slug = "focus-session-desk"
        self.product = self.root / "products" / self.slug
        assets = self.product / "store" / "assets"
        assets.mkdir(parents=True)
        (self.product / "manifest.json").write_text(
            '{"kind":"app","slug":"focus-session-desk","entry":"main.py"}\n',
            encoding="utf-8",
        )
        (self.product / "main.py").write_text(
            "print('preflight fixture')\n", encoding="utf-8"
        )
        for filename, dimensions in (
            ("StoreLogo.png", (300, 300)),
            ("Square150.png", (150, 150)),
            ("Square44.png", (44, 44)),
        ):
            (assets / filename).write_bytes(png_bytes(*dimensions))

        self.git("add", "products/focus-session-desk")
        self.git("commit", "-m", "fixture: immutable Focus source")
        self.source_sha = self.git("rev-parse", "HEAD")

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def test_current_focus_request_is_bound_to_exact_source_sha(self):
        request_id = f"app-{self.slug}-{self.source_sha[:12]}"
        report = inspect_source(self.root, self.slug, self.source_sha, request_id)

        self.assertEqual(report["source_sha"], self.source_sha)
        self.assertEqual(report["factory_request_id"], request_id)
        self.assertEqual(report["factory_request_source_sha"], self.source_sha)
        self.assertEqual(report["request_binding_status"], "PASS")
        self.assertEqual(report["identity_status"], "MISSING")
        self.assertEqual(report["version_status"], "UNAVAILABLE")
        self.assertEqual(report["status"], "DELIVERY_HOLD")
        self.assertIs(report["makeappx_invoked"], False)
        self.assertIs(report["product_msix_created"], False)
        self.assertIs(report["store_submission"], False)
        self.assertIs(report["publish"], False)

    def test_stale_source_request_pair_is_rejected(self):
        stale_request_id = f"app-{self.slug}-fb6293839bc7"
        with self.assertRaisesRegex(
            ValueError, "factory request id does not match current source SHA"
        ):
            inspect_source(
                self.root, self.slug, self.source_sha, stale_request_id
            )

    def test_request_id_is_not_inferred_when_not_supplied(self):
        report = inspect_source(self.root, self.slug, self.source_sha)

        self.assertIsNone(report["factory_request_id"])
        self.assertIsNone(report["factory_request_source_sha"])
        self.assertEqual(report["request_binding_status"], "NOT_SUPPLIED")
        self.assertEqual(report["identity_status"], "MISSING")
        self.assertEqual(report["version_status"], "UNAVAILABLE")
        self.assertIs(report["product_msix_created"], False)

    def test_source_checkout_mismatch_is_rejected_before_request_binding(self):
        with self.assertRaisesRegex(ValueError, "source checkout mismatch"):
            inspect_source(
                self.root,
                self.slug,
                "0" * 40,
                f"app-{self.slug}-{self.source_sha[:12]}",
            )


if __name__ == "__main__":
    unittest.main()
