"""Generate deterministic package PNG assets for approved products.

This only creates manifest/package icons from an explicit reviewed JSON config.
It never invents Identity or Version and never creates Store listing screenshots.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import zlib

ASSET_SIZES = {
    "StoreLogo.png": 50,
    "Square44.png": 44,
    "Square150.png": 150,
}


def _rgb(hex_color: str) -> tuple[int, int, int]:
    if not isinstance(hex_color, str) or len(hex_color) != 7 or not hex_color.startswith("#"):
        raise ValueError("color must be #RRGGBB")
    try:
        return tuple(int(hex_color[i:i+2], 16) for i in (1, 3, 5))
    except ValueError as exc:
        raise ValueError("invalid color") from exc


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(
        ">I", zlib.crc32(kind + payload) & 0xFFFFFFFF
    )


def _png(width: int, height: int, pixels: bytes) -> bytes:
    raw = b"".join(b"\x00" + pixels[y * width * 4:(y + 1) * width * 4] for y in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )


def _inside_circle(x, y, cx, cy, r):
    dx, dy = x - cx, y - cy
    return dx * dx + dy * dy <= r * r


def _render(size: int, kind: str, background: tuple[int, int, int], accent: tuple[int, int, int]) -> bytes:
    px = bytearray(size * size * 4)
    center = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            color = background
            if kind == "focus":
                r = size * 0.28
                d2 = (x-center)**2 + (y-center)**2
                if (r-size*0.055)**2 <= d2 <= (r+size*0.055)**2:
                    color = accent
                # timer hand
                if abs(x-center) <= max(1, size*0.018) and center-size*0.22 <= y <= center:
                    color = accent
                if center <= x <= center+size*0.15 and abs(y-center) <= max(1, size*0.018):
                    color = accent
            elif kind == "integrity":
                # shield silhouette with center check
                nx = (x-center)/(size*0.30)
                ny = (y-center)/(size*0.34)
                shield = abs(nx) <= 1 and -0.85 <= ny <= 0.65 and (
                    ny <= 0.15 or abs(nx) <= max(0.0, 1.0-(ny-0.15)*1.65)
                )
                if shield:
                    color = accent
                # dark check carved into shield
                if shield:
                    line1 = abs((y-center*1.03) - 0.55*(x-center*0.82)) < size*0.045
                    line2 = abs((y-center*1.10) + 0.80*(x-center*1.15)) < size*0.045
                    if (line1 and x <= center) or (line2 and x >= center-size*0.02):
                        color = background
            else:
                raise ValueError("unsupported package asset kind")
            i = (y * size + x) * 4
            px[i:i+4] = bytes((*color, 255))
    return _png(size, size, bytes(px))


def ensure_assets(root: Path, slug: str) -> list[Path]:
    config_path = root / "packaging-assets" / f"{slug}.json"
    if not config_path.is_file() or config_path.is_symlink():
        raise ValueError("approved package asset config missing")
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    if cfg.get("schema_version") != 1 or cfg.get("slug") != slug or cfg.get("approved") is not True:
        raise ValueError("package asset config not approved for this product")
    kind = cfg.get("kind")
    background = _rgb(cfg.get("background"))
    accent = _rgb(cfg.get("accent"))

    out = root / "products" / slug / "store" / "assets"
    if out.is_symlink():
        raise ValueError("linked package asset directory forbidden")
    out.mkdir(parents=True, exist_ok=True)

    written = []
    for name, size in ASSET_SIZES.items():
        path = out / name
        if path.is_symlink():
            raise ValueError("linked package asset forbidden")
        path.write_bytes(_render(size, kind, background, accent))
        written.append(path)
    return written


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--slug", required=True)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = p.parse_args(argv)
    paths = ensure_assets(args.root, args.slug)
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
