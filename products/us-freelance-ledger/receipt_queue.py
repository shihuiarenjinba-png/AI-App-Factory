"""Local-only receipt intake. Files are referenced, never copied or OCR-processed."""
from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

ALLOWED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg"}
MAX_RECEIPTS_PER_BATCH = 100
MAX_RECEIPT_BYTES = 25 * 1024 * 1024


def _schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS receipt_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT NOT NULL,
            sha256 TEXT NOT NULL UNIQUE,
            size_bytes INTEGER NOT NULL CHECK(size_bytes > 0),
            status TEXT NOT NULL DEFAULT 'PENDING_MANUAL_REVIEW',
            transaction_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def _fingerprint(source: str | os.PathLike[str]) -> tuple[str, str, int]:
    path = Path(source).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ValueError("Not a regular local file (or is a symbolic link)")
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError("Select a PDF, PNG, or JPEG file")
    size = path.stat().st_size
    if size < 1 or size > MAX_RECEIPT_BYTES:
        raise ValueError("File must be between 1 byte and 25 MiB")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    if path.is_symlink() or path.stat().st_size != size:
        raise ValueError("File changed while being read")
    return str(path.resolve(strict=True)), digest.hexdigest(), size


def enqueue_receipts(conn: sqlite3.Connection, sources) -> list[dict]:
    """Process every item independently; duplicate content is never queued twice."""
    _schema(conn)
    sources = list(sources)
    results = []
    for index, source in enumerate(sources):
        label = os.fspath(source)
        if index >= MAX_RECEIPTS_PER_BATCH:
            results.append({"path": label, "status": "REJECTED", "reason": "Batch limit is 100 files"})
            continue
        try:
            path, digest, size = _fingerprint(source)
            with conn:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO receipt_queue(source_path,sha256,size_bytes) VALUES(?,?,?)",
                    (path, digest, size),
                )
            results.append({"path": path, "status": "QUEUED" if cur.rowcount else "DUPLICATE", "sha256": digest})
        except (OSError, ValueError, sqlite3.Error) as exc:
            results.append({"path": label, "status": "REJECTED", "reason": str(exc)})
    return results


def list_receipts(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    _schema(conn)
    rows = conn.execute(
        "SELECT id,source_path,sha256,size_bytes,status,transaction_id "
        "FROM receipt_queue ORDER BY id DESC LIMIT ?",
        (min(max(int(limit), 1), 1000),),
    ).fetchall()
    return [dict(zip(("id", "source_path", "sha256", "size_bytes", "status", "transaction_id"), row)) for row in rows]


def link_receipt(conn: sqlite3.Connection, source_path: str, transaction_id: int) -> bool:
    """Link only unchanged, queued content to a user-confirmed transaction."""
    _schema(conn)
    row = conn.execute(
        "SELECT id,sha256,status FROM receipt_queue WHERE source_path=? ORDER BY id DESC LIMIT 1",
        (source_path,),
    ).fetchone()
    if row is None or row[2] != "PENDING_MANUAL_REVIEW":
        return False
    try:
        _, digest, _ = _fingerprint(source_path)
    except (OSError, ValueError):
        return False
    if digest != row[1]:
        return False
    with conn:
        updated = conn.execute(
            "UPDATE receipt_queue SET status='LINKED', transaction_id=? "
            "WHERE id=? AND status='PENDING_MANUAL_REVIEW'",
            (transaction_id, row[0]),
        )
    return bool(updated.rowcount)
