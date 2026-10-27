"""Use an immutable pre-Identity Windows EXE for APP MSIX; never rebuild it.

The Partner Center attestation is supplied by the authenticated local operator
via Provisioner. This code only checks its provenance; it cannot authenticate
to Partner Center, reserve a Store name, or submit a package.
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

REPOSITORY = "shihuiarenjinba-png/AI-App-Factory"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SLUG = re.compile(r"[a-z][a-z0-9-]{3,39}\Z")
RUN_ID = re.compile(r"[1-9][0-9]{4,19}\Z")


def hold(reason: str) -> None:
    raise ValueError("PINNED_EXE_HOLD: " + reason)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            text=True, encoding="utf-8", timeout=30, check=True)
    return result.stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def approved_identity(root: Path, slug: str) -> dict:
    if not SLUG.fullmatch(slug):
        hold("invalid slug")
    path = root / "products" / slug / "store" / "approved-identity.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
        hold("approved Identity file missing, linked or oversized")
    try:
        identity = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("PINNED_EXE_HOLD: malformed approved Identity JSON") from exc
    if not isinstance(identity, dict):
        hold("approved Identity must be a JSON object")
    expected = {
        "reviewed": True, "source": "partner_center",
        "product_type": "APP", "source_factory": "AI-App-Factory",
        "source_repository": REPOSITORY, "slug": slug,
        "package_kind": "exe",
    }
    if any(type(identity.get(k)) is not type(v) or identity.get(k) != v
           for k, v in expected.items()):
        hold("approved Identity APP lane/provenance mismatch")
    source_sha = identity.get("source_sha")
    if not isinstance(source_sha, str) or not SHA40.fullmatch(source_sha):
        hold("missing exact source_sha")
    if identity.get("expected_head_sha") != source_sha:
        hold("expected HEAD and source SHA mismatch")
    branch = identity.get("source_branch")
    if (not isinstance(branch, str) or not branch.startswith("codex/")
            or not re.fullmatch(r"codex/[A-Za-z0-9._/-]+", branch)
            or ".." in branch or "//" in branch):
        hold("source branch must be an isolated codex branch")
    active = os.environ.get("GITHUB_REF_NAME") or git(root, "branch", "--show-current")
    if active != branch:
        hold("Identity source branch differs from checked-out work branch")
    if os.environ.get("GITHUB_REF") and os.environ["GITHUB_REF"] != "refs/heads/" + branch:
        hold("GitHub ref is not the approved source branch")
    if not isinstance(identity.get("request_id"), str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:-]{3,127}", identity["request_id"]):
        hold("request_id missing or invalid")
    name = identity.get("display_name")
    if (not isinstance(name, str) or not 1 <= len(name) <= 100
            or name != name.strip() or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        hold("display_name missing or invalid")
    if (not isinstance(identity.get("package_sha256"), str)
            or not SHA256.fullmatch(identity["package_sha256"])
            or type(identity.get("package_bytes")) is not int
            or not 1024 < identity["package_bytes"] <= 300 * 1024 * 1024):
        hold("inspected EXE package SHA and byte count required")
    if git(root, "rev-parse", "HEAD^") != source_sha:
        hold("Identity return must be the sole commit after pinned Factory source")
    changed = git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()
    if changed != [f"products/{slug}/store/approved-identity.json"]:
        hold("Identity return commit changed source or unrelated files")
    if git(root, "status", "--porcelain", "--untracked-files=no", "--", f"products/{slug}"):
        hold("product files changed after Identity return")
    return identity


def verify_prebuilt(root: Path, slug: str, prebuilt: Path, identity: dict) -> Path:
    if prebuilt.is_symlink() or not prebuilt.is_dir():
        hold("prebuilt EXE directory missing or linked")
    exe = prebuilt / (slug + ".exe")
    receipt_path = prebuilt / "exe-receipt.json"
    if any(p.is_symlink() or not p.is_file() for p in (exe, receipt_path)):
        hold("prebuilt EXE or receipt missing or linked")
    if receipt_path.stat().st_size > 32768:
        hold("EXE receipt oversized")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("PINNED_EXE_HOLD: invalid EXE receipt") from exc
    expected = {
        "schema_version": 1, "stage": "PRE_IDENTITY_WINDOWS_EXE",
        "status": "EXE_QA_UNSIGNED", "source_repository": REPOSITORY,
        "source_sha": identity["source_sha"], "product_type": "APP",
        "slug": slug, "display_name": identity["display_name"],
        "executable": slug + ".exe", "official_identity_status": "NOT_COLLECTED",
        "store_id": None, "msix_status": "NOT_BUILT",
    }
    if not isinstance(receipt, dict) or any(
            type(receipt.get(k)) is not type(v) or receipt.get(k) != v
            for k, v in expected.items()):
        hold("EXE receipt does not match Factory source and Identity return")
    size = exe.stat().st_size
    if (size != identity["package_bytes"] or
            type(receipt.get("executable_bytes")) is not int or
            receipt["executable_bytes"] != size):
        hold("prebuilt EXE size differs from both approved Identity and receipt")
    with exe.open("rb") as stream:
        if stream.read(2) != b"MZ":
            hold("prebuilt EXE lacks Windows PE signature")
    digest = sha256_file(exe)
    if (digest != identity["package_sha256"] or
            receipt.get("executable_sha256") != digest):
        hold("prebuilt EXE SHA-256 differs from approved Identity or receipt")
    return exe


def verify_msix(msix: Path, identity: dict) -> dict:
    try:
        from tools.msix_handoff import msix_data
    except ModuleNotFoundError:
        from msix_handoff import msix_data
    actual = msix_data(msix)
    for field in ("name", "publisher", "version"):
        if actual[field] != identity[field]:
            hold("MSIX " + field + " differs from official Partner Center Identity")
    if actual["executable_sha256"] != identity["package_sha256"]:
        hold("MSIX contains a different EXE than the pinned pre-Identity build")
    return actual


def download_artifact(root: Path, slug: str, run_id: str, destination: Path) -> dict:
    identity = approved_identity(root, slug)
    if not RUN_ID.fullmatch(str(run_id)):
        hold("positive numeric GitHub Actions run ID required")
    if destination.exists() or destination.is_symlink():
        hold("refusing to overwrite an existing EXE download")
    command = ["gh", "run", "view", str(run_id), "-R", REPOSITORY,
               "--json", "headSha,headBranch,status,conclusion,workflowName,event"]
    result = subprocess.run(command, capture_output=True, text=True,
                            encoding="utf-8", timeout=60, check=True)
    try:
        run = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("PINNED_EXE_HOLD: invalid GitHub run metadata") from exc
    if (run.get("headSha") != identity["source_sha"]
            or run.get("headBranch") != identity["source_branch"]
            or run.get("status") != "completed" or run.get("conclusion") != "success"
            or run.get("workflowName") != "Factory pre-Identity Windows EXE"
            or run.get("event") not in ("push", "workflow_dispatch")):
        hold("EXE artifact run is not a successful run for the pinned source SHA")
    artifact = f"factory-preidentity-exe-{slug}-{identity['source_sha']}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pinned-exe-", dir=destination.parent) as tmp:
        tmp_path = Path(tmp)
        subprocess.run(["gh", "run", "download", str(run_id), "-R", REPOSITORY,
                        "-n", artifact, "-D", str(tmp_path)], check=True, timeout=180)
        verify_prebuilt(root, slug, tmp_path, identity)
        tmp_path.rename(destination)
    return {"source_sha": identity["source_sha"], "artifact_name": artifact,
            "executable_sha256": identity["package_sha256"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--slug", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(download_artifact(args.root, args.slug, args.run_id, args.output)))
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        print("PREBUILT_ARTIFACT_HOLD: " + type(exc).__name__ + ": " + str(exc)[:200],
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
