"""Select exactly one product from the entire GitHub push range, not HEAD alone."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SLUG = re.compile(r"[a-z][a-z0-9-]{3,39}\Z")


try:
    from tools.market_fit_gate import MarketFitHold, assert_market_fit
except ModuleNotFoundError:
    from market_fit_gate import MarketFitHold, assert_market_fit


class SelectionHold(ValueError):
    """A push cannot be safely mapped to exactly one product."""


def slug_from_paths(paths: list[str]) -> str:
    slugs: set[str] = set()
    for path in paths:
        parts = path.split("/")
        if parts[0] != "products":
            continue
        if len(parts) < 3 or not SLUG.fullmatch(parts[1]):
            raise SelectionHold("malformed product path in push")
        slugs.add(parts[1])
    if len(slugs) != 1:
        raise SelectionHold("expected exactly one changed product across entire push")
    return next(iter(slugs))


def push_paths(before: str, after: str, *, cwd: Path | None = None) -> list[str]:
    if not SHA40.fullmatch(before) or before == "0" * 40:
        raise SelectionHold("push has no usable previous commit; use manual dispatch")
    if not SHA40.fullmatch(after) or after == "0" * 40:
        raise SelectionHold("push has no valid current commit")
    if before == after:
        raise SelectionHold("push did not advance the source commit")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", before, after],
        cwd=cwd, capture_output=True, check=False, timeout=30,
    )
    if ancestor.returncode != 0:
        raise SelectionHold("push history is non-fast-forward or unavailable")
    changed = subprocess.run(
        # A cross-product rename changes *both* source and destination products.
        # Git rename detection reports only the destination with --name-only,
        # which could incorrectly select one product and export its MSIX.
        ["git", "diff", "--no-renames", "--name-only", "-z", before, after, "--", "products/"],
        cwd=cwd, capture_output=True, check=False, timeout=30,
    )
    if changed.returncode != 0:
        raise SelectionHold("cannot inspect complete product push range")
    try:
        return [name.decode("utf-8") for name in changed.stdout.split(b"\0") if name]
    except UnicodeDecodeError as exc:
        raise SelectionHold("push contains non-UTF-8 product paths") from exc


def choose_slug(event: str, explicit_slug: str, before: str, after: str,
                *, cwd: Path | None = None) -> str:
    if event == "workflow_dispatch":
        if not SLUG.fullmatch(explicit_slug):
            raise SelectionHold("invalid manual product slug")
        return explicit_slug
    if event != "push":
        raise SelectionHold("unsupported product selection event")
    return slug_from_paths(push_paths(before, after, cwd=cwd))


def main() -> int:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        print("MSIX_SELECTION_HOLD: GITHUB_OUTPUT missing", file=sys.stderr)
        return 2
    try:
        slug = choose_slug(
            os.environ.get("GITHUB_EVENT_NAME", ""),
            os.environ.get("EXPLICIT_SLUG", ""),
            os.environ.get("PUSH_BEFORE", ""),
            os.environ.get("GITHUB_SHA", ""),
        )
        if not (Path("products") / slug / "store" / "approved-identity.json").is_file():
            raise SelectionHold("approved Identity absent; do not invent Store IDs")
        assert_market_fit(Path("."), slug)
    except (SelectionHold, MarketFitHold, subprocess.TimeoutExpired, OSError) as exc:
        reason = str(exc).replace("\r", " ").replace("\n", " ")[:200]
        print("MSIX_SELECTION_HOLD: " + reason)
        with open(output, "a", encoding="utf-8") as handle:
            handle.write("ready=false\n")
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as handle:
                handle.write("MSIX export HOLD: " + reason + "\n")
        return 0
    with open(output, "a", encoding="utf-8") as handle:
        handle.write("ready=true\nslug=" + slug + "\n")
    print("MSIX_PRODUCT_SELECTED: " + slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
