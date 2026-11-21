"""Package a previously built, SHA-pinned Windows APP EXE after official Identity return.

This is a local/Windows-only MakeAppx path. No new PyInstaller build, no Store
Identity inference, no signing or Store submission. Only real EXE bytes are used.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

# Support both python -m tools.build_windows_msix_from_exe and direct script invocation.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.build_windows_exe import current_source_branch
from tools.build_windows_msix import ASSETS, appx_manifest, locate_makeappx, verify_inputs
from tools.msix_handoff import msix_data

SHA40 = re.compile(r"^[a-f0-9]{40}$")
SHA64 = re.compile(r"^[a-f0-9]{64}$")
REQUEST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{3,127}$")
BRANCH = re.compile(r"^codex/[A-Za-z0-9._/-]+$")
MAX_EXE = 300 * 1024 * 1024


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args],
                          check=True, capture_output=True, timeout=30).stdout.strip()


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate EXE receipt key")
        result[key] = value
    return result


def inspect_exe_evidence(root: Path, slug: str, evidence: Path,
                         source_sha: str, source_branch: str,
                         request_id: str) -> tuple[Path, str]:
    """Fail closed if EXE, provenance, or pinned APP source changed."""
    if not isinstance(source_sha, str) or not SHA40.fullmatch(source_sha) or source_sha == "0" * 40:
        raise ValueError("exact source SHA required")
    if (not isinstance(source_branch, str) or not BRANCH.fullmatch(source_branch)
            or ".." in source_branch or "//" in source_branch
            or source_branch.endswith(("/", "."))):
        raise ValueError("safe codex source branch required")
    if not isinstance(request_id, str) or not REQUEST.fullmatch(request_id):
        raise ValueError("immutable request_id required")
    root = root.resolve(strict=True)
    if current_source_branch(root, source_branch) != source_branch:
        raise ValueError("current Factory branch differs from pinned EXE branch")
    if subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor",
                       source_sha, "HEAD"], capture_output=True, timeout=30).returncode:
        raise ValueError("EXE source SHA is not ancestor of Factory HEAD")
    paths = ["factory/config.json", f"proposals/{slug}.json", f"products/{slug}"]
    changed = _git(root, "diff", "--no-renames", "--name-only", "-z",
                   source_sha, "HEAD", "--", *paths)
    for raw in changed.split(b"\0"):
        if not raw:
            continue
        try:
            path = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("non-UTF-8 source change") from exc
        if (path != f"products/{slug}/store/approved-identity.json"
                and not path.startswith(f"products/{slug}/store/assets/")):
            raise ValueError("APP code/proposal changed since pinned EXE build")
    if _git(root, "status", "--porcelain", "--untracked-files=all", "--", *paths):
        raise ValueError("uncommitted APP source or Identity")
    if evidence.is_symlink() or not evidence.is_dir():
        raise ValueError("EXE evidence directory absent or linked")
    exe = evidence / (slug + ".exe")
    receipt_path = evidence / "exe-receipt.json"
    if ({p.name for p in evidence.iterdir()} != {exe.name, receipt_path.name}
            or exe.is_symlink() or receipt_path.is_symlink()
            or not exe.is_file() or not receipt_path.is_file()
            or receipt_path.stat().st_size > 32768):
        raise ValueError("EXE evidence files missing, extra or linked")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"),
                         object_pairs_hook=_no_duplicates)
    expected = {
        "schema_version": 1, "stage": "PRE_IDENTITY_WINDOWS_EXE",
        "status": "EXE_QA_UNSIGNED", "product_type": "APP",
        "source_factory": "AI-App-Factory",
        "source_repository": "shihuiarenjinba-png/AI-App-Factory",
        "source_branch": source_branch, "source_sha": source_sha,
        "request_id": request_id, "slug": slug, "executable": exe.name,
        "official_identity_status": "NOT_COLLECTED", "store_id": None,
        "msix_status": "NOT_BUILT",
    }
    if not isinstance(receipt, dict) or any(receipt.get(k) != v for k, v in expected.items()):
        raise ValueError("EXE receipt immutable contract mismatch")
    proposal = json.loads((root / "proposals" / (slug + ".json")).read_text(encoding="utf-8"))
    if receipt.get("display_name") != proposal.get("title"):
        raise ValueError("EXE receipt display_name mismatch")
    size = exe.stat().st_size
    if (type(receipt.get("executable_bytes")) is not int
            or receipt["executable_bytes"] != size or not 1024 < size <= MAX_EXE):
        raise ValueError("EXE byte size mismatch")
    expected_hash = receipt.get("executable_sha256")
    if not isinstance(expected_hash, str) or not SHA64.fullmatch(expected_hash):
        raise ValueError("EXE SHA-256 missing")
    digest = sha256()
    with exe.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("EXE PE header missing")
        stream.seek(0)
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_hash:
        raise ValueError("EXE hash differs from pre-Identity receipt")
    return exe, expected_hash


def pack_with_makeappx(layout: Path, destination: Path) -> None:
    subprocess.run([str(locate_makeappx()), "pack", "/d", str(layout),
                    "/p", str(destination), "/o"], check=True, timeout=180)


def build_from_exe(root: Path, slug: str, evidence: Path, out: Path,
                   source_sha: str, source_branch: str, request_id: str) -> dict:
    if sys.platform != "win32":
        raise ValueError("real Windows runner required")
    root = root.resolve(strict=True)
    product, identity = verify_inputs(root, slug)
    exe, exe_hash = inspect_exe_evidence(
        root, slug, evidence, source_sha, source_branch, request_id)
    if out.exists() or out.is_symlink():
        raise ValueError("refuse overwrite of MSIX output")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.parent.is_symlink():
        raise ValueError("linked MSIX output parent forbidden")
    with tempfile.TemporaryDirectory(prefix="app-msix-prebuilt-", dir=out.parent) as tmp:
        work = Path(tmp)
        layout = work / "layout"
        (layout / "Assets").mkdir(parents=True)
        shutil.copyfile(exe, layout / exe.name)
        for name in ASSETS:
            shutil.copyfile(product / "store/assets" / name, layout / "Assets" / name)
        (layout / "AppxManifest.xml").write_bytes(appx_manifest(identity, exe.name))
        staged = work / "final"
        staged.mkdir()
        package = staged / (slug + ".msix")
        pack_with_makeappx(layout, package)
        details = msix_data(package)  # ZIP structure, manifest, runnable EXE + CRC
        if (details["executable_sha256"] != exe_hash
                or any(details[key] != identity[key] for key in ("name", "publisher", "version"))):
            raise ValueError("MakeAppx package differs from approved Identity or pinned EXE")
        receipt = {
            "schema_version": 1, "status": "QA_UNSIGNED",
            "request_id": request_id, "product_type": "APP",
            "source_factory": "AI-App-Factory",
            "source_repository": "shihuiarenjinba-png/AI-App-Factory",
            "source_branch": source_branch, "source_sha": source_sha,
            "slug": slug, "display_name": json.loads(
                (root / "proposals" / (slug + ".json")).read_text(encoding="utf-8"))["title"],
            "store_id": identity["store_id"],
            "identity": {key: identity[key] for key in ("name", "publisher", "version")},
            "executable_sha256": exe_hash,
            "package": package.name, "package_sha256": details["package_sha256"],
            "package_bytes": details["package_bytes"], "store_submitted": False,
        }
        (staged / "msix-build-receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if out.exists() or out.is_symlink():
            raise ValueError("output appeared during MSIX build")
        os.replace(staged, out)
    return receipt


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--slug", required=True)
    p.add_argument("--exe-evidence", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--source-sha", required=True)
    p.add_argument("--source-branch", required=True)
    p.add_argument("--request-id", required=True)
    args = p.parse_args(argv)
    try:
        print(json.dumps(build_from_exe(args.root, args.slug, args.exe_evidence,
              args.output, args.source_sha, args.source_branch, args.request_id),
              ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError,
            subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print("PREBUILT_MSIX_HOLD: " + type(exc).__name__ + ": " + str(exc)[:180],
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
