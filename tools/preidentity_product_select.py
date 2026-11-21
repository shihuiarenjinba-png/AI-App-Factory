"""Select a committed APP product for a real pre-Identity Windows EXE build.

Reuses the MSIX push-range selection but deliberately does not require Store
Identity: that is the purpose of the earlier EXE stage.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

try:
    from tools.msix_push_product import choose_slug, SelectionHold
except ModuleNotFoundError:
    from msix_push_product import choose_slug, SelectionHold


def select(event: str, explicit_slug: str, before: str, after: str,
           root: Path = Path(".")) -> str:
    slug = choose_slug(event, explicit_slug, before, after, cwd=root)
    manifest = root / "products" / slug / "manifest.json"
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 32768:
        raise SelectionHold("APP product manifest missing or linked")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise SelectionHold("invalid APP product manifest") from exc
    if (not isinstance(data, dict) or data.get("kind") != "app"
            or data.get("slug") != slug or data.get("entry") != "main.py"):
        raise SelectionHold("wrong APP product lane or entrypoint")
    return slug


def main() -> int:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        print("PRE_IDENTITY_SELECTION_HOLD: GITHUB_OUTPUT missing", file=sys.stderr)
        return 2
    try:
        slug = select(
            os.environ.get("GITHUB_EVENT_NAME", ""),
            os.environ.get("EXPLICIT_SLUG", ""),
            os.environ.get("PUSH_BEFORE", ""),
            os.environ.get("GITHUB_SHA", ""),
        )
    except (SelectionHold, OSError) as exc:
        reason = str(exc).replace("\r", " ").replace("\n", " ")[:200]
        print("PRE_IDENTITY_SELECTION_HOLD: " + reason)
        with open(output, "a", encoding="utf-8") as handle:
            handle.write("ready=false\n")
        return 0
    with open(output, "a", encoding="utf-8") as handle:
        handle.write("ready=true\nslug=" + slug + "\n")
    print("PRE_IDENTITY_APP_SELECTED: " + slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
