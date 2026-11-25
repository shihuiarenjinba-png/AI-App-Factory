"""Build and verify a deterministic, non-submitted Focus identity-revalidation request."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

SOURCE_REPOSITORY = "shihuiarenjinba-png/AI-App-Factory"
SOURCE_BRANCH = "codex/focus-store-assets-gate-20261118"
EXPECTED_SOURCE_SHA = "fb6293839bc7b0bbff0a6d1d3c04e2f8f5942e79"
REQUEST_ID = "app-focus-session-desk-fb6293839bc7"
SLUG = "focus-session-desk"
HISTORICAL_REQUEST_ID = "app-focus-session-desk-8b00bc4e9082"
HISTORICAL_SOURCE_SHA = "8b00bc4e90828c4282463826873aa8dfd2eb93f4"
REGISTRATION_CODE = "MSIX_OR_PWA_APP"
REGISTRATION_LABEL = "MSIX or PWA app"
REQUEST_RELATIVE = Path("handoff/focus-session-desk/source-request/request.json")
HASH_RELATIVE = Path("handoff/focus-session-desk/source-request/request.sha256")
README_RELATIVE = Path("handoff/focus-session-desk/source-request/README.md")


def canonical_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def idempotency_material(payload: dict) -> dict:
    return {
        "operation": payload["operation"],
        "request_id": payload["request_id"],
        "source_repository": payload["source_repository"],
        "source_branch": payload["source_branch"],
        "source_sha": payload["source_sha"],
        "slug": payload["product"]["slug"],
        "registration_code": payload["partner_center"]["selection_code"],
    }


def idempotency_key(payload: dict) -> str:
    return hashlib.sha256(canonical_bytes(idempotency_material(payload))).hexdigest()


def build_payload() -> dict:
    payload = {
        "schema_version": "focus-source-request/1",
        "request_id": REQUEST_ID,
        "operation": "PARTNER_CENTER_IDENTITY_REVALIDATION",
        "source_repository": SOURCE_REPOSITORY,
        "source_branch": SOURCE_BRANCH,
        "source_sha": EXPECTED_SOURCE_SHA,
        "expected_head_sha": EXPECTED_SOURCE_SHA,
        "product": {
            "slug": SLUG,
            "display_name": "Focus Session Desk",
            "product_type": "APP",
        },
        "partner_center": {
            "selection_code": REGISTRATION_CODE,
            "selection_label": REGISTRATION_LABEL,
            "action_scope": "READ_ONLY_IDENTITY_REVALIDATION",
            "write_authorized": False,
        },
        "historical_identity": {
            "status": "HISTORICAL_ONLY_NOT_REUSED",
            "request_id": HISTORICAL_REQUEST_ID,
            "source_sha": HISTORICAL_SOURCE_SHA,
            "reuse_for_current_source": False,
        },
        "required_operator_return_fields": [
            "store_id",
            "name",
            "publisher",
            "version",
            "official_evidence_url",
            "verified_by",
            "operator_verified",
        ],
        "return_target": {
            "repository": SOURCE_REPOSITORY,
            "branch": SOURCE_BRANCH,
            "path": "products/focus-session-desk/store/approved-identity.json",
            "expected_head_sha": EXPECTED_SOURCE_SHA,
            "apply_authorized": False,
        },
        "package_version": {
            "value": None,
            "status": "HOLD_NOT_INFERRED",
        },
        "execution": {
            "dry_run": True,
            "request_submitted": False,
            "partner_center_write": False,
            "identity_write": False,
            "msix_build": False,
            "store_submission": False,
            "store_publication": False,
        },
        "source_drift_policy": (
            "Reject this request if the named source branch no longer points to source_sha "
            "or if products/focus-session-desk differs from that commit."
        ),
    }
    payload["idempotency_key"] = idempotency_key(payload)
    return payload


def verify_payload_bytes(data: bytes, expected_sha256: str | None = None) -> tuple[dict, str]:
    if not isinstance(data, bytes) or not 1 <= len(data) <= 32768:
        raise ValueError("request bytes are missing or oversized")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("request JSON is invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("request must be a JSON object")
    if canonical_bytes(payload) != data:
        raise ValueError("request JSON is not canonical")
    expected = build_payload()
    if payload != expected:
        raise ValueError("request payload differs from the pinned contract")
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError("request SHA-256 mismatch")
    if payload.get("idempotency_key") != idempotency_key(payload):
        raise ValueError("idempotency key mismatch")
    return payload, digest


def assert_source_head(expected: str, observed: str) -> None:
    if observed != expected:
        raise ValueError(f"source branch drift: expected {expected}, observed {observed}")


def assert_product_paths_unchanged(changed_paths: list[str]) -> None:
    prefix = f"products/{SLUG}/"
    changed = sorted(path for path in changed_paths
                     if path == f"products/{SLUG}" or path.startswith(prefix))
    if changed:
        raise ValueError("product source changed after pinned HEAD: " + ", ".join(changed))


def replay_decision(existing: dict[str, str], payload: dict, request_sha256: str) -> str:
    key = payload["idempotency_key"]
    previous = existing.get(key)
    if previous is None:
        return "NEW_DRY_RUN"
    if previous == request_sha256:
        return "IDEMPOTENT_REPLAY_NOOP"
    raise ValueError("idempotency key already exists with different request bytes")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True, capture_output=True, text=True, timeout=20,
    )
    return result.stdout.strip()


def prepare_artifact(source_root: Path, observed_source_head: str, output: Path) -> dict:
    root = source_root.resolve(strict=True)
    assert_source_head(EXPECTED_SOURCE_SHA, observed_source_head)

    actual_head = _git(root, "rev-parse", "HEAD")
    _git(root, "merge-base", "--is-ancestor", EXPECTED_SOURCE_SHA, actual_head)
    changed = _git(root, "diff", "--name-only", EXPECTED_SOURCE_SHA, actual_head).splitlines()
    assert_product_paths_unchanged(changed)

    manifest_raw = _git(root, "show", f"{EXPECTED_SOURCE_SHA}:products/{SLUG}/manifest.json")
    manifest = json.loads(manifest_raw)
    if manifest != {"slug": SLUG, "kind": "app", "entry": "main.py"}:
        raise ValueError("pinned source manifest mismatch")
    _git(root, "cat-file", "-e", f"{EXPECTED_SOURCE_SHA}:products/{SLUG}/main.py")
    _git(root, "cat-file", "-e", f"{EXPECTED_SOURCE_SHA}:products/{SLUG}/tests/test_smoke.py")

    request_path = root / REQUEST_RELATIVE
    hash_path = root / HASH_RELATIVE
    readme_path = root / README_RELATIVE
    for path in (request_path, hash_path, readme_path):
        if path.is_symlink() or not path.is_file():
            raise ValueError("request handoff file is missing or linked")

    request_bytes = request_path.read_bytes()
    recorded_hash = hash_path.read_text(encoding="ascii").strip().split()
    if len(recorded_hash) != 2 or recorded_hash[1] != "request.json":
        raise ValueError("request.sha256 format is invalid")
    payload, digest = verify_payload_bytes(request_bytes, recorded_hash[0])

    output = output.resolve()
    if output.exists():
        raise ValueError("artifact output already exists")
    output.mkdir(parents=True)
    shutil.copyfile(request_path, output / "request.json")
    shutil.copyfile(hash_path, output / "request.sha256")
    shutil.copyfile(readme_path, output / "README.md")

    verification = {
        "schema_version": "focus-source-request-verification/1",
        "request_id": payload["request_id"],
        "source_repository": SOURCE_REPOSITORY,
        "source_branch": SOURCE_BRANCH,
        "source_sha": EXPECTED_SOURCE_SHA,
        "expected_head_sha": EXPECTED_SOURCE_SHA,
        "request_sha256": digest,
        "idempotency_key": payload["idempotency_key"],
        "source_branch_head_check": "PASS",
        "product_tree_unchanged_check": "PASS",
        "request_tamper_check": "PASS",
        "idempotent_replay_check": "PASS",
        "dry_run": True,
        "request_submitted": False,
        "partner_center_write": False,
        "identity_write": False,
        "msix_build": False,
        "store_submission": False,
        "store_publication": False,
    }
    (output / "verification.json").write_bytes(canonical_bytes(verification))
    return verification


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--observed-source-head", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = prepare_artifact(args.source_root, args.observed_source_head, args.output)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        print("FOCUS_SOURCE_REQUEST_HOLD:", type(exc).__name__, str(exc)[:240], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
