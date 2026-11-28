"""Read-only source-bound package preflight for pinned product source commits."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.build_windows_msix import (
    VERSION,
    identity_is_tracked,
    identity_path_for,
    source_head,
    verify_assets,
    verify_inputs,
)


def inspect_source(
    source_root: Path,
    slug: str,
    expected_sha: str,
    expected_request_id: str | None = None,
) -> dict:
    source_root = Path(source_root).resolve(strict=True)
    actual_sha = source_head(source_root)
    if actual_sha != expected_sha:
        raise ValueError(
            f"source checkout mismatch for {slug}: expected {expected_sha}, got {actual_sha}"
        )

    factory_request_id = None
    factory_request_source_sha = None
    request_binding_status = "NOT_SUPPLIED"
    if expected_request_id is not None:
        deterministic_request_id = f"app-{slug}-{actual_sha[:12]}"
        if expected_request_id != deterministic_request_id:
            raise ValueError(
                "factory request id does not match current source SHA for " + slug
            )
        factory_request_id = expected_request_id
        factory_request_source_sha = actual_sha
        request_binding_status = "PASS"

    product = source_root / "products" / slug
    asset_hashes = verify_assets(product)
    identity_path = identity_path_for(product)
    tracked = identity_is_tracked(source_root, slug)
    recorded_source_sha = None
    version_status = "UNAVAILABLE"
    identity_status = "MISSING"
    hold_reason = "official source-bound Identity return missing"

    if identity_path.is_symlink():
        identity_status = "LINKED"
        hold_reason = "approved Identity path is linked"
    elif identity_path.is_file():
        try:
            identity = json.loads(identity_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            identity = {}
            identity_status = "INVALID"
            hold_reason = "approved Identity JSON is invalid"
        recorded_source_sha = identity.get("source_sha")
        version = identity.get("version")
        if not isinstance(version, str) or not version:
            version_status = "MISSING"
        elif VERSION.fullmatch(version):
            version_status = "PRESENT"
        else:
            version_status = "INVALID"

        if identity_status != "INVALID":
            if recorded_source_sha != actual_sha:
                identity_status = "STALE_TRACKED" if tracked else "STALE"
                hold_reason = "Identity source SHA does not match the pinned current source"
            elif tracked:
                identity_status = "TRACKED_NOT_ACCEPTED"
                hold_reason = "Identity return is committed inside the immutable source"
            else:
                try:
                    verify_inputs(source_root, slug)
                except ValueError as error:
                    identity_status = "HOLD"
                    hold_reason = str(error)
                else:
                    identity_status = "READY"
                    hold_reason = None

    status = (
        "PREFLIGHT_READY"
        if identity_status == "READY" and version_status == "PRESENT"
        else "DELIVERY_HOLD"
    )
    return {
        "schema": "factory-msix-source-preflight-v1",
        "product_slug": slug,
        "source_sha": actual_sha,
        "expected_source_sha": expected_sha,
        # Factory request binding is deterministic QA metadata, not an Identity return.
        "factory_request_id": factory_request_id,
        "factory_request_source_sha": factory_request_source_sha,
        "request_binding_status": request_binding_status,
        "asset_validation": "PASS",
        "asset_sha256": asset_hashes,
        "identity_status": identity_status,
        "identity_recorded_source_sha": recorded_source_sha,
        "identity_file_tracked": tracked,
        "version_status": version_status,
        "status": status,
        "hold_reason": hold_reason,
        "makeappx_invoked": False,
        "product_msix_created": False,
        "store_submission": False,
        "publish": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument(
        "--expected-request-id",
        help="Optional deterministic Factory request ID bound to the exact source SHA.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_source_sha):
        raise SystemExit("invalid expected source SHA")
    try:
        report = inspect_source(
            args.source_root,
            args.slug,
            args.expected_source_sha,
            args.expected_request_id,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print("PACKAGE_SOURCE_PREFLIGHT_FAIL:", str(error)[:240])
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
