"""Read-only APP Factory -> local package Provisioner job producer.

Emits exactly the 1.0 schema accepted by Repository-Provisioner-app/package_job.py.
No GitHub write, Partner Center lookup, build, or authorization is performed.
The source SHA is derived from the checked-out Git HEAD, never supplied by a caller.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

OWNER = "shihuiarenjinba-png"
FACTORY = "AI-App-Factory"
BRANCH = "codex/factory-autoloop-20261026"  # legacy test fixture; runtime uses the checked-out codex branch
BRANCH_RE = re.compile(r"^codex/[A-Za-z0-9._/-]+$")
SLUG = re.compile(r"^[a-z][a-z0-9-]{3,39}$")
REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
ACTIONS = [
    "BUILD_WINDOWS", "INSPECT_PACKAGE",
    "LOOKUP_OFFICIAL_IDENTITY", "PROPOSE_GITHUB_RETURN",
]


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True, capture_output=True, text=True, timeout=15,
    )
    return result.stdout.strip()


def _read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
        raise ValueError("missing, linked, or oversized product metadata")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("metadata must be a JSON object")
    return value


def _valid_work_branch(value: object) -> bool:
    """Accept safe codex/* work branches; never main, release, or traversal refs."""
    if (not isinstance(value, str) or not 7 <= len(value) <= 240
            or BRANCH_RE.fullmatch(value) is None
            or ".." in value or "//" in value or "@{" in value
            or value.endswith(("/", "."))):
        return False
    return all(part and not part.startswith(".") and not part.endswith(".lock")
               for part in value.split("/"))


def make_request(root: Path, slug: str, request_id: str | None = None) -> dict:
    """Produce a deterministic candidate from a clean, committed APP source snapshot."""
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        raise ValueError("unsafe product slug")
    root = root.resolve(strict=True)
    # Git for Windows can emit 8.3 short paths (RUNNER~1) while pathlib
    # resolves the long path. Compare filesystem identity, not path text.
    if not Path(_git(root, "rev-parse", "--show-toplevel")).samefile(root):
        raise ValueError("root must be Git checkout top-level")
    source_branch = _git(root, "branch", "--show-current")
    if not _valid_work_branch(source_branch):
        raise ValueError("unapproved or unsafe Factory source branch")
    head = _git(root, "rev-parse", "HEAD")
    if not SHA.fullmatch(head) or head == "0" * 40:
        raise ValueError("unusable Git source HEAD")
    if request_id is None:
        # Same deterministic source-SHA naming convention used by the original
        # Factory promotion script for File Integrity Ledger.
        request_id = "app-" + slug + "-" + head[:12]
    if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
        raise ValueError("unsafe request ID")

    paths = [
        "factory/config.json",
        "proposals/" + slug + ".json",
        "products/" + slug + "/manifest.json",
        "products/" + slug + "/main.py",
        "products/" + slug + "/tests/test_smoke.py",
    ]
    product = root / "products" / slug
    if product.is_symlink() or not product.is_dir():
        raise ValueError("product directory unavailable")
    for rel in paths:
        path = root / rel
        if path.is_symlink() or not path.is_file():
            raise ValueError("missing or linked source file")
        _git(root, "cat-file", "-e", "HEAD:" + rel)
    # Check all files under product, not only the manifest, including untracked
    # content. Dirty files cannot be attested to by the pinned commit SHA.
    if _git(root, "status", "--porcelain", "--",
            "factory/config.json", "proposals/" + slug + ".json",
            "products/" + slug):
        raise ValueError("product snapshot differs from committed HEAD")

    config = _read_json(root / "factory/config.json")
    manifest = _read_json(product / "manifest.json")
    proposal = _read_json(root / "proposals" / (slug + ".json"))
    if config.get("kind") != "app" or manifest.get("kind") != "app":
        raise ValueError("wrong Factory product lane")
    if manifest.get("slug") != slug or manifest.get("entry") != "main.py":
        raise ValueError("product manifest mismatch")
    if proposal.get("slug") != slug:
        raise ValueError("proposal slug mismatch")
    title = proposal.get("title")
    if (not isinstance(title, str) or not 1 <= len(title) <= 100
            or title != title.strip()
            or any(ord(c) < 32 or ord(c) == 127 for c in title)):
        raise ValueError("invalid or missing approved product title")

    return {
        "schema_version": "1.0",
        "request_id": request_id,
        "product_type": "APP",
        "source_factory": FACTORY,
        "source_repository": OWNER + "/" + FACTORY,
        "source_branch": source_branch,
        "source_sha": head,
        "slug": slug,
        "display_name": title,
        "target_owner": OWNER,
        "dry_run": True,
        "requested_actions": list(ACTIONS),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--request-id", help="Optional explicit ID; default is app-<slug>-<source SHA prefix>")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(make_request(args.root, args.slug, args.request_id),
                         ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, json.JSONDecodeError,
            subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print("PACKAGE_HANDOFF_HOLD: source or metadata verification failed",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
