"""Reject manual or automatic MSIX exports outside isolated Factory work branches.

GitHub's push branch filter does not restrict workflow_dispatch.  Check the
actual event/ref before selecting a product, running tests, or building MSIX.
"""
from __future__ import annotations

import os
import re
import sys

_ALLOWED_REF = re.compile(r"refs/heads/codex/[A-Za-z0-9][A-Za-z0-9._/-]*\Z", re.ASCII)
_ALLOWED_EVENTS = frozenset({"push", "workflow_dispatch"})


def validate_export_context(event: str, ref: str, ref_type: str) -> str:
    """Return the checked work branch, or fail closed with a ValueError."""
    if event not in _ALLOWED_EVENTS:
        raise ValueError("unsupported MSIX export event")
    if ref_type != "branch" or not isinstance(ref, str) or not _ALLOWED_REF.fullmatch(ref):
        raise ValueError("MSIX export requires refs/heads/codex/*")
    branch = ref.removeprefix("refs/heads/")
    parts = branch.split("/")
    if any(part in ("", ".", "..") or part.startswith(".") or part.endswith(".")
           for part in parts):
        raise ValueError("invalid work branch components")
    return branch


def main() -> int:
    try:
        branch = validate_export_context(
            os.environ.get("GITHUB_EVENT_NAME", ""),
            os.environ.get("GITHUB_REF", ""),
            os.environ.get("GITHUB_REF_TYPE", ""),
        )
    except ValueError as exc:
        print("MSIX_EXPORT_HOLD: " + str(exc), file=sys.stderr)
        return 2
    print("MSIX_EXPORT_BRANCH_OK: " + branch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
