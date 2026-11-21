"""Fail-closed package PNG validation for File Integrity Ledger.

This is a delivery gate only. It does not change product code, Identity, or Version.
Run: python -m unittest products/focus-session-desk/tests/test_store_assets.py
"""
import hashlib
import io
import struct
import unittest
import zlib
import zipfile
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "store" / "assets"
EXPECTED = {"StoreLogo.png": (300, 300), "Square150.png": (150, 150), "Square44.png": (44, 44)}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def validate_png(path, expected_size):
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("not a PNG")
    pos = len(PNG_SIGNATURE)
    chunks = []
    size = None
    while pos < len(data):
        if len(data) - pos < 12:
            raise ValueError("truncated PNG chunk")
        length = struct.unpack_from(">I", data, pos)[0]
        kind = data[pos + 4:pos + 8]
        end = pos + 12 + length
        if end > len(data):
            raise ValueError("truncated PNG data")
        payload = data[pos + 8:pos + 8 + length]
        crc = struct.unpack_from(">I", data, pos + 8 + length)[0]
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            raise ValueError("PNG CRC mismatch")
        chunks.append(kind)
        if kind == b"IHDR":
            if size is not None or length != 13:
                raise ValueError("invalid IHDR")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            size = (width, height)
            if depth != 8 or color not in (2, 6) or (compression, filtering, interlace) != (0, 0, 0):
                raise ValueError("expected 8-bit RGB/RGBA non-interlaced PNG")
        pos = end
        if kind == b"IEND":
            break
    if not chunks or chunks[0] != b"IHDR" or chunks[-1] != b"IEND" or b"IDAT" not in chunks or pos != len(data):
        raise ValueError("invalid PNG structure")
    if size != expected_size:
        raise ValueError(f"PNG size {size} != {expected_size}")


class StoreAssetsTest(unittest.TestCase):
    def test_required_assets(self):
        for filename, dimensions in EXPECTED.items():
            with self.subTest(filename=filename):
                self.assertTrue((ASSETS / filename).is_file(), f"missing delivery asset: {filename}")
                validate_png(ASSETS / filename, dimensions)


    def test_package_zip_payload_roundtrip(self):
        """Preflight only: package-style ZIP paths and exact byte preservation.

        Does not assert that a real MSIX was built, signed or installed.
        """
        original = {}
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for filename, dimensions in EXPECTED.items():
                data = (ASSETS / filename).read_bytes()
                validate_png(ASSETS / filename, dimensions)
                name = "Assets/" + filename
                original[name] = hashlib.sha256(data).hexdigest()
                archive.writestr(name, data)
        output.seek(0)
        with zipfile.ZipFile(output, "r") as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(set(archive.namelist()), set(original))
            for name, expected_sha in original.items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), expected_sha)


if __name__ == "__main__":
    unittest.main()
