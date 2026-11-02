"""Local-only original receipt custody; evidence integrity, never tax approval.

Only the opt-in real-file ingestion path captures bytes. Legacy queue entries
are not backfilled and remain REVIEW_REQUIRED. No content is uploaded.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path

MAX_BYTES = 32 * 1024 * 1024
ALLOWED = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}


class CustodyError(ValueError):
    pass


def _safe_read(path, output=None):
    """Read an ordinary file without following a link; detect replacement/change."""
    path = Path(path)
    if path.is_symlink():
        raise CustodyError("REVIEW_REQUIRED_SOURCE_LINK")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise CustodyError("REVIEW_REQUIRED_SOURCE_UNREADABLE") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size <= 0 or before.st_size > MAX_BYTES:
            raise CustodyError("REVIEW_REQUIRED_SOURCE_SIZE_OR_TYPE")
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(fd, "rb", closefd=False) as source:
            while True:
                block = source.read(1024 * 1024)
                if not block:
                    break
                size += len(block)
                if size > MAX_BYTES:
                    raise CustodyError("REVIEW_REQUIRED_SOURCE_TOO_LARGE")
                digest.update(block)
                if output is not None:
                    output.write(block)
        after = os.fstat(fd)
        path_after = path.lstat()
        signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        if (signature(before) != signature(after) or
                signature(after) != signature(path_after) or size != after.st_size or
                stat.S_ISLNK(path_after.st_mode)):
            raise CustodyError("REVIEW_REQUIRED_SOURCE_CHANGED_DURING_READ")
        return digest.hexdigest(), size
    except OSError as exc:
        raise CustodyError("REVIEW_REQUIRED_SOURCE_UNREADABLE") from exc
    finally:
        os.close(fd)


class ReceiptCustody:
    def __init__(self, conn: sqlite3.Connection, db_path):
        self.conn = conn
        self.root = Path(db_path).parent / "receipt-originals"
        if self.root.is_symlink():
            raise CustodyError("REVIEW_REQUIRED_STORAGE_LINK")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise CustodyError("REVIEW_REQUIRED_STORAGE_LINK")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS receipt_originals (
            receipt_id INTEGER PRIMARY KEY,
            source_path TEXT NOT NULL,
            original_name TEXT NOT NULL,
            storage_name TEXT NOT NULL UNIQUE,
            sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL CHECK(size_bytes>0),
            captured_utc TEXT NOT NULL
        )""")
        self.conn.execute("""CREATE TRIGGER IF NOT EXISTS receipt_originals_no_update
            BEFORE UPDATE ON receipt_originals BEGIN
                SELECT RAISE(ABORT, 'RECEIPT_ORIGINAL_IMMUTABLE');
            END""")
        self.conn.execute("""CREATE TRIGGER IF NOT EXISTS receipt_originals_no_delete
            BEFORE DELETE ON receipt_originals BEGIN
                SELECT RAISE(ABORT, 'RECEIPT_ORIGINAL_IMMUTABLE');
            END""")
        self.conn.commit()

    def capture(self, path, history, at=None):
        path = Path(path).expanduser().absolute()
        if path.suffix.lower() not in ALLOWED:
            raise CustodyError("REVIEW_REQUIRED_UNSUPPORTED_FILE_TYPE")
        key = str(path)
        old = self.conn.execute("SELECT id FROM receipt_queue WHERE file_path=?", (key,)).fetchone()
        if old is not None:
            rid = int(old[0])
            check = self.verify(rid)
            if check["status"] != "VERIFIED":
                raise CustodyError(check["reason"])
            return rid, False

        temporary = self.root / (".capture-" + uuid.uuid4().hex + ".tmp")
        stored = self.root / (uuid.uuid4().hex + ".bin")
        try:
            with temporary.open("xb") as out:
                digest, size = _safe_read(path, out)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, stored)
            # A durable copy precedes the database claim. A crash here can leave
            # an unreferenced blob, never a falsely VERIFIED database record.
            if os.name != "nt":
                directory_fd = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            stamp = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            def insert_metadata(rid):
                self.conn.execute(
                    "INSERT INTO receipt_originals(receipt_id,source_path,original_name,storage_name,sha256,size_bytes,captured_utc) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (rid, key, path.name, stored.name, digest, size, stamp))
            rid, added = history.add(key, at=at, on_insert=insert_metadata)
            if not added:
                stored.unlink(missing_ok=True)
                check = self.verify(rid)
                if check["status"] != "VERIFIED":
                    raise CustodyError(check["reason"])
            return rid, added
        except (OSError, sqlite3.Error) as exc:
            raise CustodyError("REVIEW_REQUIRED_CAPTURE_FAILED") from exc
        finally:
            temporary.unlink(missing_ok=True)
            # If the database did not commit the record, the staged copy is
            # disposable; never delete a blob referenced by a committed row.
            if stored.exists():
                linked = self.conn.execute(
                    "SELECT 1 FROM receipt_originals WHERE storage_name=?", (stored.name,)
                ).fetchone()
                if linked is None:
                    stored.unlink(missing_ok=True)

    def verify(self, receipt_id):
        row = self.conn.execute(
            "SELECT q.file_path, o.source_path,o.storage_name,o.sha256,o.size_bytes,o.captured_utc "
            "FROM receipt_queue q LEFT JOIN receipt_originals o ON o.receipt_id=q.id "
            "WHERE q.id=?", (int(receipt_id),)).fetchone()
        hold = lambda reason: {"status": "REVIEW_REQUIRED", "reason": reason}
        if row is None:
            return hold("SOURCE_RECEIPT_MISSING")
        path, source, name, sha, size, captured = row
        if name is None:
            return hold("LEGACY_ORIGINAL_NOT_CAPTURED")
        if (source != path or not re.fullmatch(r"[0-9a-f]{32}\.bin", name) or
                not re.fullmatch(r"[0-9a-f]{64}", str(sha)) or
                not isinstance(size, int) or size <= 0 or size > MAX_BYTES or not captured):
            return hold("ORIGINAL_METADATA_INVALID")
        blob = self.root / name
        try:
            stored_sha, stored_size = _safe_read(blob)
            if stored_size != size or stored_sha != sha:
                return hold("PRESERVED_ORIGINAL_CHANGED")
            source_sha, source_size = _safe_read(source)
            if source_size != size or source_sha != sha:
                return hold("SOURCE_ORIGINAL_CHANGED")
        except CustodyError as exc:
            reason = str(exc)
            if reason == "REVIEW_REQUIRED_SOURCE_UNREADABLE":
                reason = ("PRESERVED_ORIGINAL_MISSING_OR_UNREADABLE"
                          if not blob.exists() else "SOURCE_ORIGINAL_MISSING_OR_UNREADABLE")
            return hold(reason)
        return {"status": "VERIFIED", "reason": None, "sha256": sha,
                "size_bytes": size, "captured_utc": captured,
                "stored_original": str(blob), "source_path": source}
