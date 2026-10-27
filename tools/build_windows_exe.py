"""Build an actual Windows EXE before Store Identity is available.

This is a local/Windows build stage, NOT an MSIX, Store candidate, or Identity
lookup. It accepts only an exact, clean, committed APP product source SHA.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

SLUG = re.compile(r"^[a-z][a-z0-9-]{3,39}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SOURCE_REPOSITORY = "shihuiarenjinba-png/AI-App-Factory"
SOURCE_BRANCH = re.compile(r"^codex/[A-Za-z0-9._/-]+$")
REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def current_source_branch(root: Path, claimed_branch: str | None = None) -> str:
    """Bind receipt to the actual checked-out codex ref, including detached Actions checkouts."""
    head = _git(root, "rev-parse", "HEAD")
    # A local checkout has an authoritative symbolic ref even if the test
    # runner itself carries unrelated GITHUB_REF/GITHUB_SHA environment vars.
    try:
        branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    except subprocess.CalledProcessError:
        if claimed_branch is not None:
            # Provisioner first authenticates ls-remote and checks out the exact
            # SHA detached. Also require its local origin tracking ref to match.
            if (not SOURCE_BRANCH.fullmatch(claimed_branch) or ".." in claimed_branch
                    or "//" in claimed_branch or claimed_branch.endswith(("/", "."))):
                raise ValueError("unsafe claimed Factory source branch")
            try:
                tracked = _git(root, "rev-parse", "refs/remotes/origin/" + claimed_branch)
            except subprocess.CalledProcessError as exc:
                raise ValueError("origin source branch tracking ref absent") from exc
            if tracked != head:
                raise ValueError("detached source HEAD differs from origin branch ref")
            branch = claimed_branch
        else:
            ref = os.environ.get("GITHUB_REF", "")
            if not ref.startswith("refs/heads/codex/") or os.environ.get("GITHUB_SHA") != head:
                raise ValueError("detached Git checkout lacks verified codex ref/SHA")
            branch = ref[len("refs/heads/"):]
    if (not SOURCE_BRANCH.fullmatch(branch) or ".." in branch or "//" in branch
            or branch.endswith(("/", "."))):
        raise ValueError("unsafe or non-codex source branch")
    if claimed_branch is not None and claimed_branch != branch:
        raise ValueError("claimed Factory source branch differs from checkout")
    return branch


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True,
        text=True, encoding="utf-8", timeout=30,
    )
    return result.stdout.strip()


def verify_source(root: Path, slug: str, expected_sha: str) -> Path:
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        raise ValueError("invalid APP product slug")
    if not isinstance(expected_sha, str) or not SHA40.fullmatch(expected_sha) or expected_sha == "0" * 40:
        raise ValueError("exact non-placeholder source SHA required")
    root = root.resolve(strict=True)
    # Git for Windows prints forward slashes while pathlib uses native
    # separators. Compare canonical paths, not raw text representations.
    if not Path(_git(root, "rev-parse", "--show-toplevel")).samefile(root):
        raise ValueError("root must be Git checkout top-level")
    if _git(root, "rev-parse", "HEAD") != expected_sha:
        raise ValueError("source HEAD differs from pinned SHA")
    products = root / "products"
    product = products / slug
    if products.is_symlink() or product.is_symlink() or not product.is_dir():
        raise ValueError("APP product directory missing or linked")
    if any(path.is_symlink() for path in product.rglob("*")):
        raise ValueError("linked APP product content forbidden")
    paths = ("factory/config.json", f"proposals/{slug}.json",
             f"products/{slug}/manifest.json",
             f"products/{slug}/main.py", f"products/{slug}/tests/test_smoke.py")
    for rel in paths:
        file = root / rel
        if file.is_symlink() or not file.is_file() or file.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("required committed APP source missing, linked, or oversized")
        _git(root, "cat-file", "-e", f"HEAD:{rel}")
    if _git(root, "status", "--porcelain", "--untracked-files=all", "--",
            "factory/config.json", f"proposals/{slug}.json", f"products/{slug}"):
        raise ValueError("APP source differs from pinned Git commit")
    config = json.loads((root / "factory/config.json").read_text(encoding="utf-8"))
    manifest = json.loads((product / "manifest.json").read_text(encoding="utf-8"))
    proposal = json.loads((root / "proposals" / (slug + ".json")).read_text(encoding="utf-8"))
    if (not isinstance(proposal, dict) or proposal.get("slug") != slug
            or not isinstance(proposal.get("title"), str)
            or not 1 <= len(proposal["title"]) <= 100
            or proposal["title"] != proposal["title"].strip()
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in proposal["title"])):
        raise ValueError("Factory product title missing or unapproved")
    if not isinstance(config, dict) or config.get("kind") != "app":
        raise ValueError("wrong Factory lane")
    if (not isinstance(manifest, dict) or manifest.get("kind") != "app"
            or manifest.get("slug") != slug or manifest.get("entry") != "main.py"):
        raise ValueError("APP product manifest mismatch")
    return product / "main.py"


def _run_pyinstaller(source: Path, slug: str, work: Path, root: Path) -> None:
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--onefile", "--windowed", "--noupx", "--name", slug,
         "--paths", str(source.parent),
         "--distpath", str(work / "dist"), "--workpath", str(work / "build"),
         "--specpath", str(work / "spec"), str(source)],
        cwd=root, check=True, timeout=1200,
    )


def build_exe(root: Path, slug: str, expected_sha: str, output: Path,
              request_id: str | None = None,
              source_branch: str | None = None) -> dict:
    if sys.platform != "win32":
        raise ValueError("Windows runner required for real EXE build")
    if request_id is not None and (not isinstance(request_id, str)
            or not REQUEST_ID.fullmatch(request_id)):
        raise ValueError("unsafe APP request_id")
    root = root.resolve(strict=True)
    source = verify_source(root, slug, expected_sha)
    source_branch = current_source_branch(root, source_branch)
    display_name = json.loads((root / "proposals" / (slug + ".json")).read_text(
        encoding="utf-8"))["title"]
    if output.exists() or output.is_symlink():
        raise ValueError("refusing to overwrite existing EXE evidence")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.parent.is_symlink():
        raise ValueError("linked output parent forbidden")
    with tempfile.TemporaryDirectory(prefix="app-preidentity-", dir=output.parent) as temporary:
        work = Path(temporary)
        _run_pyinstaller(source, slug, work, root)
        candidate = work / "dist" / (slug + ".exe")
        if not candidate.is_file() or candidate.is_symlink():
            raise ValueError("PyInstaller produced no regular Windows EXE")
        size = candidate.stat().st_size
        if not 1024 < size <= 300 * 1024 * 1024:
            raise ValueError("Windows EXE size outside QA limits")
        with candidate.open("rb") as reader:
            if reader.read(2) != b"MZ":
                raise ValueError("Windows EXE PE signature absent")
        digest = hashlib.sha256()
        with candidate.open("rb") as reader:
            for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                digest.update(chunk)
        receipt = {
            "schema_version": 1,
            "stage": "PRE_IDENTITY_WINDOWS_EXE",
            "status": "EXE_QA_UNSIGNED",
            "source_repository": SOURCE_REPOSITORY,
            "source_factory": "AI-App-Factory",
            "source_branch": source_branch,
            "source_sha": expected_sha,
            "request_id": request_id,
            "product_type": "APP",
            "slug": slug,
            "display_name": display_name,
            "executable": slug + ".exe",
            "executable_sha256": digest.hexdigest(),
            "executable_bytes": size,
            "official_identity_status": "NOT_COLLECTED",
            "store_id": None,
            "msix_status": "NOT_BUILT",
        }
        final = work / "final"
        final.mkdir()
        shutil.copyfile(candidate, final / (slug + ".exe"))
        if hashlib.sha256((final / (slug + ".exe")).read_bytes()).hexdigest() != digest.hexdigest():
            raise ValueError("copied Windows EXE hash mismatch")
        (final / "exe-receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if output.exists() or output.is_symlink():
            raise ValueError("output appeared during build; refuse overwrite")
        os.replace(final, output)
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--slug", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--request-id", help="Exact immutable Provisioner request_id; omit for EXE-only QA")
    parser.add_argument("--source-branch", help="Exact codex branch for authenticated detached Provisioner checkout")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = build_exe(args.root, args.slug, args.expected_sha, args.output,
                           request_id=args.request_id, source_branch=args.source_branch)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError,
            subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print("PRE_IDENTITY_EXE_HOLD: " + type(exc).__name__ + ": " + str(exc)[:200],
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
