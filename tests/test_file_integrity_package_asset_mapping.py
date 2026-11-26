"""QA-only, read-only contract for File Integrity Store PNG staging.

This test uses the real PR115 source PNG bytes, a synthetic Identity only inside
a disposable temporary repository, and a fake MakeAppx executable. It proves
the existing builder maps the three frozen source PNGs to the AppxManifest
asset paths byte-for-byte. It does NOT create a real MSIX, sign, or submit.
"""
from hashlib import sha256
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from tools import build_windows_msix as msix_builder


ROOT = Path(__file__).resolve().parents[1]
SLUG = "file-integrity-ledger"
SOURCE_PRODUCT = ROOT / "products" / SLUG
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Frozen by PR95 and preserved byte-for-byte by PR115.
EXPECTED_ASSET_SHA256 = {
    "StoreLogo.png": "224fa777280cf61877c14146e920fca32bb90bff6f0cea3df4ed0ac77c0645a9",
    "Square150.png": "e00136c7a319756ccc48c2dc50136f5872e272e806cd592a6beb8922bbb1742",
    "Square44.png": "bd61099427a770f8dff247f0f6928e5d50ba2cd8265797c7f13952e96147d70d",
}

# Synthetic fixture only. This never enters the checked-out product tree.
FIXTURE_IDENTITY = {
    "reviewed": True,
    "source": "partner_center",
    "store_id": "9PTEST123",
    "name": "Example.Company.App",
    "publisher": "CN=QA Fixture",
    "version": "1.0.0.0",
    "verified_by": "isolated QA fixture",
    "evidence_url": "https://partner.microsoft.com/dashboard/products/qa-fixture",
}


def assert_exact_asset_bytes(product: Path) -> dict[str, bytes]:
    """Fail closed unless the exact three approved PR95 PNG byte strings exist."""
    asset_dir = product / "store" / "assets"
    if asset_dir.is_symlink() or not asset_dir.is_dir():
        raise ValueError("Store asset directory missing or linked")
    actual_names = {path.name for path in asset_dir.iterdir()}
    if actual_names != set(EXPECTED_ASSET_SHA256):
        raise ValueError("Store asset set differs from the frozen three-PNG contract")

    contents = {}
    for name, expected_sha in EXPECTED_ASSET_SHA256.items():
        path = asset_dir / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Store asset missing or linked: " + name)
        raw = path.read_bytes()
        if not raw.startswith(PNG_MAGIC):
            raise ValueError("Store asset is not PNG: " + name)
        if sha256(raw).hexdigest() != expected_sha:
            raise ValueError("Store asset SHA-256 mismatch: " + name)
        contents[name] = raw
    return contents


class FileIntegrityPackageAssetMappingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.product = self.root / "products" / SLUG
        assets = self.product / "store" / "assets"
        assets.mkdir(parents=True)

        # Read from this exact checked-out source HEAD; never regenerate assets.
        for name in EXPECTED_ASSET_SHA256:
            shutil.copyfile(SOURCE_PRODUCT / "store" / "assets" / name, assets / name)
        shutil.copyfile(SOURCE_PRODUCT / "manifest.json", self.product / "manifest.json")
        shutil.copyfile(SOURCE_PRODUCT / "main.py", self.product / "main.py")
        (self.product / "store" / "approved-identity.json").write_text(
            json.dumps(FIXTURE_IDENTITY), encoding="utf-8"
        )

        # Prove the checked-out source bytes are the frozen values before tests run.
        self.source_bytes = assert_exact_asset_bytes(self.product)

    def _run_builder_with_fake_makeappx(self, output: Path):
        captured = {}
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if len(command) > 2 and command[1:3] == ["-m", "PyInstaller"]:
                dist = Path(command[command.index("--distpath") + 1])
                name = command[command.index("--name") + 1]
                dist.mkdir(parents=True, exist_ok=True)
                # A disposable fake PE; no real executable or Windows SDK is used.
                (dist / (name + ".exe")).write_bytes(b"MZ" + bytes(range(256)) * 16)
                return SimpleNamespace(returncode=0)

            if Path(command[0]).name.lower() == "makeappx.exe":
                layout = Path(command[3])
                destination = Path(command[5])
                captured.update({
                    path.relative_to(layout).as_posix(): path.read_bytes()
                    for path in layout.rglob("*") if path.is_file()
                })
                # A QA sentinel only. This is deliberately NOT an MSIX container.
                destination.write_bytes(b"QA_ONLY_NOT_A_REAL_MSIX\n" + bytes(range(256)) * 16)
                return SimpleNamespace(returncode=0)

            raise AssertionError("unexpected external command in QA-only builder test")

        with patch.object(msix_builder.sys, "platform", "win32"), patch.object(
            msix_builder.subprocess, "run", side_effect=fake_run
        ), patch.object(msix_builder, "locate_makeappx", return_value=Path("makeappx.exe")):
            result = msix_builder.build(self.root, SLUG, output)

        return result, captured, calls

    def test_builder_stages_frozen_png_bytes_at_manifest_paths(self):
        # The test-only SHA guard runs before the actual builder. The builder's
        # own copy loop and manifest generator then determine the staged paths.
        self.assertEqual(tuple(msix_builder.ASSETS), tuple(EXPECTED_ASSET_SHA256))
        self.assertEqual(assert_exact_asset_bytes(self.product), self.source_bytes)

        output = self.root / "qa-output"
        result, staged, calls = self._run_builder_with_fake_makeappx(output)

        expected_members = {f"Assets/{name}" for name in EXPECTED_ASSET_SHA256}
        self.assertEqual({name for name in staged if name.startswith("Assets/")}, expected_members)
        for name, original in self.source_bytes.items():
            member = "Assets/" + name
            self.assertEqual(staged[member], original)
            self.assertEqual(sha256(staged[member]).hexdigest(), EXPECTED_ASSET_SHA256[name])

        manifest = ET.fromstring(staged["AppxManifest.xml"])
        logo = next(node for node in manifest.iter() if node.tag.endswith("}Logo"))
        visual = next(node for node in manifest.iter() if node.tag.endswith("}VisualElements"))
        self.assertEqual(logo.text, r"Assets\StoreLogo.png")
        self.assertEqual(visual.attrib["Square150x150Logo"], r"Assets\Square150.png")
        self.assertEqual(visual.attrib["Square44x44Logo"], r"Assets\Square44.png")

        self.assertTrue(result.is_file())
        self.assertTrue(result.read_bytes().startswith(b"QA_ONLY_NOT_A_REAL_MSIX"))
        self.assertEqual(len(calls), 2, "only fake PyInstaller and fake MakeAppx calls are allowed")

    def test_missing_png_fails_before_any_builder_or_makeappx_call(self):
        (self.product / "store" / "assets" / "Square44.png").unlink()
        output = self.root / "missing-output"
        calls = []

        with patch.object(msix_builder.sys, "platform", "win32"), patch.object(
            msix_builder.subprocess, "run", side_effect=lambda *a, **k: calls.append(a)
        ), patch.object(msix_builder, "locate_makeappx", return_value=Path("makeappx.exe")):
            with self.assertRaisesRegex(ValueError, "Approved Store asset missing: Square44.png"):
                msix_builder.build(self.root, SLUG, output)

        self.assertEqual(calls, [])
        self.assertFalse(output.exists())

    def test_modified_png_fails_frozen_hash_guard(self):
        path = self.product / "store" / "assets" / "Square150.png"
        raw = path.read_bytes()
        path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))

        with self.assertRaisesRegex(ValueError, "Store asset SHA-256 mismatch: Square150.png"):
            assert_exact_asset_bytes(self.product)


if __name__ == "__main__":
    unittest.main()
