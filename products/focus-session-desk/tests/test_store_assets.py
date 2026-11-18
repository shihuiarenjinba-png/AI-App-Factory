"""Fail-closed package PNG validation for Focus Session Desk.

This is a delivery gate only. It does not change product code, Identity, or Version.
Run: python -m unittest products/focus-session-desk/tests/test_store_assets.py
"""
import struct
import unittest
import zlib
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


if __name__ == "__main__":
    unittest.main()
