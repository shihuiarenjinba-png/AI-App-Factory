"""Read-only integrity check of receipt file references (not a tax substantiation check)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from receipt_queue import MAX_RECEIPT_BYTES, list_receipts


def audit_receipts(conn, limit=1000):
    """Re-hash each referenced local file; never modify files or receipt state.

    A SQLite backup contains the reference and original hash, not file bytes.
    The result is an advisory status, not proof of legal sufficiency.
    """
    results = []
    for row in list_receipts(conn, limit=limit):
        source = Path(row["source_path"])
        result = {"id": row["id"], "path": row["source_path"], "linked": row["status"] == "LINKED"}
        try:
            if source.is_symlink():
                raise ValueError("Symbolic link: review the source location")
            if not source.is_file():
                result.update(status="MISSING", reason="File no longer exists at its recorded location")
            else:
                before = source.stat()
                if before.st_size < 1 or before.st_size > MAX_RECEIPT_BYTES:
                    raise ValueError("File is empty or exceeds the 25 MiB intake limit")
                digest = hashlib.sha256()
                with source.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                after = source.stat()
                if source.is_symlink() or (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                    raise ValueError("File changed while being checked")
                if before.st_size != row["size_bytes"] or digest.hexdigest() != row["sha256"]:
                    result.update(status="CHANGED", reason="Content differs from the file originally queued")
                else:
                    result.update(status="OK", reason="Content matches the stored SHA-256 fingerprint")
        except (OSError, ValueError) as exc:
            result.update(status="REVIEW", reason=str(exc))
        results.append(result)
    return results
