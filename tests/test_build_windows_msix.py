import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zlib
import struct

from tools.build_windows_msix import (
    appx_manifest,
    build,
    stage_package_layout,
    verify_assets,
    verify_inputs,
)


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


class WindowsPackageContractTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "repo"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "QA Fixture"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "qa@example.invalid"], check=True)

        self.product = self.root / "products" / "demo-product"
        asset_dir = self.product / "store" / "assets"
        asset_dir.mkdir(parents=True)
        (self.product / "main.py").write_text(
            "import tkinter as tk\nroot=tk.Tk()\nroot.title('QA fixture')\nroot.mainloop()\n",
            encoding="utf-8",
        )
        (self.product / "manifest.json").write_text(
            json.dumps({"kind": "app", "slug": "demo-product", "entry": "main.py"}),
            encoding="utf-8",
        )
        for name, dims in (
            ("StoreLogo.png", (300, 300)),
            ("Square150.png", (150, 150)),
            ("Square44.png", (44, 44)),
        ):
            (asset_dir / name).write_bytes(png_bytes(*dims))

        subprocess.run(
            ["git", "-C", str(self.root), "add", "products/demo-product"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-m", "immutable package source"],
            check=True,
            capture_output=True,
        )
        self.source_sha = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.identity_path = self.product / "store" / "approved-identity.json"
        self.identity = {
            "schema_version": "1.0",
            "reviewed": True,
            "source": "partner_center",
            "request_id": f"app-demo-product-{self.source_sha[:12]}",
            "product_type": "APP",
            "source_factory": "AI-App-Factory",
            "source_repository": "shihuiarenjinba-png/AI-App-Factory",
            "source_branch": "codex/demo-product",
            "source_sha": self.source_sha,
            "verified_source_sha": self.source_sha,
            "expected_head_sha": self.source_sha,
            "store_id": "9PTEST123",
            "name": "OkinawaDesktopTools.Demo",
            "publisher": "CN=TEST",
            "version": "1.0.0.0",
            "verified_by": "LOCAL_OPERATOR_FIXTURE",
            "evidence_url": "https://partner.microsoft.com/dashboard/products/demo",
            "package_version_gate": "APPROVED",
        }
        self.write_identity()

    def write_identity(self, value=None):
        self.identity_path.write_text(
            json.dumps(value if value is not None else self.identity),
            encoding="utf-8",
        )

    def test_exact_source_bound_untracked_identity_passes(self):
        product, cfg = verify_inputs(self.root, "demo-product")
        self.assertTrue(product.samefile(self.product))
        self.assertEqual(cfg["source_sha"], self.source_sha)
        self.assertEqual(cfg["version"], "1.0.0.0")
        self.assertEqual(len(verify_assets(product)), 3)

    def test_missing_identity_holds(self):
        self.identity_path.unlink()
        with self.assertRaisesRegex(ValueError, "Identity return missing"):
            verify_inputs(self.root, "demo-product")

    def test_stale_source_identity_is_rejected(self):
        stale = dict(
            self.identity,
            source_sha="0" * 40,
            verified_source_sha="0" * 40,
            expected_head_sha="0" * 40,
            request_id="app-demo-product-000000000000",
        )
        self.write_identity(stale)
        with self.assertRaisesRegex(ValueError, "stale approved Identity"):
            verify_inputs(self.root, "demo-product")

    def test_missing_authoritative_version_is_not_guessed(self):
        missing = dict(self.identity)
        missing.pop("version")
        self.write_identity(missing)
        with self.assertRaisesRegex(ValueError, "Version missing; do not infer"):
            verify_inputs(self.root, "demo-product")

    def test_version_gate_hold_is_rejected(self):
        held = dict(self.identity, package_version_gate="HOLD")
        self.write_identity(held)
        with self.assertRaisesRegex(ValueError, "Version gate is not approved"):
            verify_inputs(self.root, "demo-product")

    def test_identity_cannot_be_committed_into_the_source(self):
        subprocess.run(
            ["git", "-C", str(self.root), "add", "products/demo-product/store/approved-identity.json"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-m", "invalid tracked identity fixture"],
            check=True,
            capture_output=True,
        )
        new_head = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        tracked = dict(
            self.identity,
            source_sha=new_head,
            verified_source_sha=new_head,
            expected_head_sha=new_head,
            request_id=f"app-demo-product-{new_head[:12]}",
        )
        self.write_identity(tracked)
        with self.assertRaisesRegex(ValueError, "tracked in the source commit"):
            verify_inputs(self.root, "demo-product")

    def test_modified_product_source_is_rejected(self):
        (self.product / "main.py").write_text("print('modified')\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "differs from committed HEAD"):
            verify_inputs(self.root, "demo-product")

    def test_missing_png_is_rejected(self):
        (self.product / "store/assets/StoreLogo.png").unlink()
        with self.assertRaisesRegex(ValueError, "asset missing or unsafe"):
            verify_assets(self.product)

    def test_png_crc_mismatch_is_rejected(self):
        path = self.product / "store/assets/Square150.png"
        data = bytearray(path.read_bytes())
        data[-5] ^= 0x01
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "CRC mismatch"):
            verify_assets(self.product)

    def test_wrong_png_dimensions_are_rejected(self):
        path = self.product / "store/assets/Square150.png"
        path.write_bytes(png_bytes(44, 44))
        with self.assertRaisesRegex(ValueError, "dimensions mismatch"):
            verify_assets(self.product)

    def test_identity_manifest_uses_exact_verified_name_publisher_version(self):
        xml = appx_manifest(self.identity, "demo-product.exe")
        root = ET.fromstring(xml)
        node = next(x for x in root.iter() if x.tag.endswith("}Identity"))
        self.assertEqual(node.attrib["Name"], self.identity["name"])
        self.assertEqual(node.attrib["Publisher"], self.identity["publisher"])
        self.assertEqual(node.attrib["Version"], self.identity["version"])

    def test_stage_copies_exact_executable_and_png_bytes(self):
        exe = self.root / "demo-product.exe"
        exe.write_bytes(b"fixture executable bytes")
        layout = self.root / "layout"
        receipt = stage_package_layout(self.product, self.identity, exe, layout)
        self.assertEqual((layout / "demo-product.exe").read_bytes(), exe.read_bytes())
        for name in ("StoreLogo.png", "Square150.png", "Square44.png"):
            self.assertEqual(
                (layout / "Assets" / name).read_bytes(),
                (self.product / "store/assets" / name).read_bytes(),
            )
            self.assertEqual(receipt["asset_sha256"][name], verify_assets(self.product)[name])

    def test_stage_rejects_mismatched_asset_copy(self):
        exe = self.root / "demo-product.exe"
        exe.write_bytes(b"fixture executable bytes")
        layout = self.root / "layout"
        import tools.build_windows_msix as builder_module
        real_copy = builder_module.shutil.copyfile

        def corrupt_square150(source, destination, *args, **kwargs):
            result = real_copy(source, destination, *args, **kwargs)
            if Path(destination).name == "Square150.png":
                Path(destination).write_bytes(b"corrupt staged bytes")
            return result

        with patch("tools.build_windows_msix.shutil.copyfile", side_effect=corrupt_square150):
            with self.assertRaisesRegex(ValueError, "staged Store asset SHA-256 mismatch"):
                stage_package_layout(self.product, self.identity, exe, layout)

    def test_stale_identity_blocks_build_before_pyinstaller_or_makeappx(self):
        stale = dict(
            self.identity,
            source_sha="0" * 40,
            verified_source_sha="0" * 40,
            expected_head_sha="0" * 40,
        )
        self.write_identity(stale)
        output = self.root / "package-output"
        with patch("tools.build_windows_msix.sys.platform", "win32"):
            with self.assertRaisesRegex(ValueError, "stale approved Identity"):
                build(self.root, "demo-product", output)
        self.assertFalse(output.exists())

    def test_unsafe_slug_is_rejected_before_path_lookup(self):
        for slug in ("../demo-product", "../../products/demo-product",
                     "demo/product", "Demo-product", "", "a"):
            with self.subTest(slug=slug):
                with self.assertRaisesRegex(ValueError, "unsafe product slug"):
                    verify_inputs(self.root, slug)


if __name__ == "__main__":
    unittest.main()
