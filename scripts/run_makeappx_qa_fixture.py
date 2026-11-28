"""Build a disposable test-only MSIX with real PyInstaller and Windows MakeAppx."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import struct
import zlib
import zipfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.build_windows_msix import build


def png_bytes(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
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


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def run_fixture(output_dir: Path) -> dict:
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise ValueError("fixture output directory must be empty")

    with tempfile.TemporaryDirectory(prefix="makeappx-qa-source-") as temp:
        root = Path(temp) / "source"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        git(root, "config", "user.name", "Package Preflight QA")
        git(root, "config", "user.email", "qa@example.invalid")

        product = root / "products" / "demo-product"
        assets = product / "store" / "assets"
        assets.mkdir(parents=True)
        (product / "manifest.json").write_text(
            json.dumps({"kind": "app", "slug": "demo-product", "entry": "main.py"}),
            encoding="utf-8",
        )
        (product / "main.py").write_text(
            "import tkinter as tk\n"
            "root = tk.Tk()\n"
            "root.title('Package Preflight QA Fixture')\n"
            "tk.Label(root, text='QA fixture only').pack(padx=20, pady=20)\n"
            "root.mainloop()\n",
            encoding="utf-8",
        )
        for filename, dimensions in (
            ("StoreLogo.png", (300, 300)),
            ("Square150.png", (150, 150)),
            ("Square44.png", (44, 44)),
        ):
            (assets / filename).write_bytes(png_bytes(*dimensions))

        subprocess.run(
            ["git", "-C", str(root), "add", "products/demo-product"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(root), "commit", "-m", "QA-only package source fixture"],
            check=True,
            capture_output=True,
        )
        source_sha = git(root, "rev-parse", "HEAD")

        # Disposable untracked operator-return fixture: not a product Identity,
        # and its Version is not a product Version.
        identity = {
            "schema_version": "1.0",
            "reviewed": True,
            "source": "partner_center",
            "request_id": f"app-demo-product-{source_sha[:12]}",
            "product_type": "APP",
            "source_factory": "AI-App-Factory",
            "source_repository": "shihuiarenjinba-png/AI-App-Factory",
            "source_branch": "codex/qa-fixture",
            "source_sha": source_sha,
            "verified_source_sha": source_sha,
            "expected_head_sha": source_sha,
            "store_id": "9PTEST123",
            "name": "OkinawaDesktopTools.PackageFixture",
            "publisher": "CN=QA-FIXTURE",
            "version": "1.0.0.0",
            "verified_by": "QA_FIXTURE_ONLY",
            "evidence_url": "https://partner.microsoft.com/dashboard/products/QA-FIXTURE/identity",
            "package_version_gate": "APPROVED",
            "display_name": "Package Preflight QA Fixture",
            "publisher_display_name": "QA Fixture Only",
        }
        (product / "store" / "approved-identity.json").write_text(
            json.dumps(identity, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        msix_path = build(root, "demo-product", output_dir)
        with zipfile.ZipFile(msix_path) as archive:
            names = set(archive.namelist())
            expected = {
                "AppxManifest.xml",
                "demo-product.exe",
                "Assets/StoreLogo.png",
                "Assets/Square150.png",
                "Assets/Square44.png",
            }
            if not expected.issubset(names):
                raise ValueError("real MakeAppx output is missing required package files")

        receipt_path = output_dir / "demo-product.build-receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("makeappx_invoked") is not True:
            raise ValueError("MakeAppx invocation was not recorded")
        if receipt.get("signature_status") != "UNSIGNED":
            raise ValueError("fixture package must remain unsigned")
        if receipt.get("store_submission") is not False or receipt.get("publish") is not False:
            raise ValueError("fixture must not have Store authority")

        label = {
            "artifact_class": "QA_FIXTURE_ONLY_NOT_PRODUCT",
            "source_sha": source_sha,
            "identity_fixture_only": True,
            "version_fixture_only": True,
            "version": "1.0.0.0",
            "real_pyinstaller_invoked": True,
            "real_windows_makeappx_invoked": True,
            "msix_sha256": hashlib.sha256(msix_path.read_bytes()).hexdigest(),
            "signature_status": "UNSIGNED",
            "store_submission": False,
            "publish": False,
        }
        (output_dir / "qa-fixture-label.json").write_text(
            json.dumps(label, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return label


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run_fixture(args.output_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (
        ValueError,
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        zipfile.BadZipFile,
    ) as error:
        print("MAKEAPPX_QA_FIXTURE_FAIL:", str(error)[:240])
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
