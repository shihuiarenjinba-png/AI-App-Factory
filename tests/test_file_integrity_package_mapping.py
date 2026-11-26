"""Read-only contract for File Integrity Store PNG -> MSIX staging paths.

The test invokes the existing builder's real staging/copy code with PyInstaller and
MakeAppx intercepted. It never calls the Windows SDK, reads a real Identity,
creates a real MSIX, or changes product/source files.
"""
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from tools import build_windows_msix as builder

SLUG = "file-integrity-ledger"
EXPECTED_ASSETS = ("StoreLogo.png", "Square150.png", "Square44.png")
TEST_IDENTITY = {
    "reviewed": True,
    "source": "partner_center",
    "store_id": "9PTEST123",
    "name": "Example.Company.App",
    "publisher": "CN=QA-ONLY",
    "version": "1.0.0.0",
    "verified_by": "QA fixture only",
    "evidence_url": "https://partner.microsoft.com/dashboard/products/qa-fixture",
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FileIntegrityPackageMapContractTests(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]
        self.source_product = self.repo_root / "products" / SLUG
        self.source_asset_hashes = {
            name: sha256((self.source_product / "store" / "assets" / name).read_bytes())
            for name in EXPECTED_ASSETS
        }
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.product = self.root / "products" / SLUG
        assets = self.product / "store" / "assets"
        assets.mkdir(parents=True)
        (self.product / "main.py").write_text("print('QA-only package map fixture')\n", encoding="utf-8")
        (self.product / "manifest.json").write_text(
            json.dumps({"kind": "app", "slug": SLUG, "entry": "main.py"}),
            encoding="utf-8",
        )
        (self.product / "store" / "approved-identity.json").write_text(
            json.dumps(TEST_IDENTITY), encoding="utf-8"
        )
        for name in EXPECTED_ASSETS:
            shutil.copyfile(self.source_product / "store" / "assets" / name, assets / name)
        self.output = self.root / "out"
        self.fake_run_calls = 0
        self.captured = None

    def _fake_subprocess_run(self, command, **kwargs):
        self.fake_run_calls += 1
        if len(command) >= 3 and command[1:3] == ["-m", "PyInstaller"]:
            dist = Path(command[command.index("--distpath") + 1])
            dist.mkdir(parents=True, exist_ok=True)
            (dist / f"{SLUG}.exe").write_bytes(b"MZ" + b"QA-ONLY-PE-FIXTURE" * 128)
            return subprocess.CompletedProcess(command, 0)

        if str(command[0]).lower().endswith("makeappx.exe"):
            layout = Path(command[command.index("/d") + 1])
            destination = Path(command[command.index("/p") + 1])
            staged_dir = layout / "Assets"
            self.assertTrue(staged_dir.is_dir(), "builder did not create Assets staging directory")
            staged_names = tuple(sorted(p.name for p in staged_dir.iterdir()))
            self.assertEqual(staged_names, tuple(sorted(EXPECTED_ASSETS)))

            staged_hashes = {}
            staged_sizes = {}
            for name in EXPECTED_ASSETS:
                staged = staged_dir / name
                self.assertTrue(staged.is_file(), f"missing staged asset: {name}")
                data = staged.read_bytes()
                actual = sha256(data)
                expected = self.source_asset_hashes[name]
                self.assertEqual(actual, expected, f"staged bytes differ from pinned source: {name}")
                self.assertTrue(data.startswith(PNG_SIGNATURE), f"staged asset is not PNG: {name}")
                staged_hashes[name] = actual
                staged_sizes[name] = len(data)

            ns = {"appx": builder.NS, "uap": builder.UAP}
            manifest_root = ET.parse(layout / "AppxManifest.xml").getroot()
            logo = manifest_root.find("appx:Properties/appx:Logo", ns)
            visual = manifest_root.find(".//uap:VisualElements", ns)
            self.assertIsNotNone(logo, "AppxManifest Logo mapping missing")
            self.assertIsNotNone(visual, "AppxManifest VisualElements mapping missing")
            self.assertEqual(logo.text, r"Assets\StoreLogo.png")
            self.assertEqual(visual.attrib.get("Square150x150Logo"), r"Assets\Square150.png")
            self.assertEqual(visual.attrib.get("Square44x44Logo"), r"Assets\Square44.png")

            self.captured = {
                "staged_hashes": staged_hashes,
                "staged_sizes": staged_sizes,
                "staged_paths": {name: f"Assets/{name}" for name in EXPECTED_ASSETS},
                "manifest_paths": {
                    "StoreLogo.png": logo.text,
                    "Square150.png": visual.attrib["Square150x150Logo"],
                    "Square44.png": visual.attrib["Square44x44Logo"],
                },
            }
            destination.parent.mkdir(parents=True, exist_ok=True)
            # A placeholder only to let the builder return. This is NOT MakeAppx
            # output and must never be described as a real MSIX.
            destination.write_bytes(b"QA-ONLY-NOT-A-MSIX" + b"x" * 2048)
            return subprocess.CompletedProcess(command, 0)

        raise AssertionError(f"unexpected subprocess command: {command!r}")

    def _build_with_intercepts(self):
        with (
            patch.object(builder.sys, "platform", "win32"),
            patch.object(builder, "locate_makeappx", return_value=Path("C:/QA/MakeAppx.exe")),
            patch.object(builder.subprocess, "run", side_effect=self._fake_subprocess_run),
        ):
            return builder.build(self.root, SLUG, self.output)

    def test_builder_stages_all_three_source_pngs_byte_identically(self):
        self.assertEqual(tuple(builder.ASSETS), EXPECTED_ASSETS)
        result = self._build_with_intercepts()
        self.assertTrue(result.is_file())
        self.assertEqual(self.fake_run_calls, 2)
        self.assertIsNotNone(self.captured)
        self.assertEqual(self.captured["staged_hashes"], self.source_asset_hashes)
        self.assertEqual(
            set(self.captured["manifest_paths"]),
            {"StoreLogo.png", "Square150.png", "Square44.png"},
        )

    def test_missing_source_asset_fails_closed_before_build(self):
        (self.product / "store" / "assets" / "Square44.png").unlink()
        with self.assertRaisesRegex(ValueError, "Approved Store asset missing: Square44.png"):
            self._build_with_intercepts()
        self.assertEqual(self.fake_run_calls, 0)
        self.assertFalse((self.output / f"{SLUG}.msix").exists())

    def test_mismatched_asset_bytes_fail_closed_before_package_output(self):
        target = self.product / "store" / "assets" / "StoreLogo.png"
        target.write_bytes(PNG_SIGNATURE + b"deliberately-mismatched-QA-fixture")
        with self.assertRaisesRegex(AssertionError, "staged bytes differ from pinned source: StoreLogo.png"):
            self._build_with_intercepts()
        self.assertFalse((self.output / f"{SLUG}.msix").exists())


if __name__ == "__main__":
    unittest.main()
