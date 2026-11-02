"""Portable, local-only JP bookkeeping backup: fail closed, never tax approval.

A backup contains one consistent SQLite snapshot and *preserved* receipt bytes.
Restore always creates a NEW directory; it never overwrites an open book.
SHA-256 checks detect accidental corruption, not malicious re-signing.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

FORMAT = "JP_BOOKKEEPING_CUSTODY_V1"
MAX_DB = 128 * 1024 * 1024
MAX_ORIGINAL = 32 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_FILES = 4096
STORED_NAME = re.compile(r"[0-9a-f]{32}\.bin")
SHA = re.compile(r"[0-9a-f]{64}")


class BackupError(ValueError):
    """A review-required backup/restore failure; no partial success."""


def _hold(code):
    raise BackupError("REVIEW_REQUIRED_" + code)


def _regular_bytes(path, maximum):
    path = Path(path)
    if path.is_symlink():
        _hold("SYMLINK")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) |
                     getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise BackupError("REVIEW_REQUIRED_FILE_UNREADABLE") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            _hold("FILE_TYPE_OR_SIZE")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(maximum + 1)
        after = os.fstat(fd)
        now = path.lstat()
        signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        if (len(data) > maximum or len(data) != after.st_size or
                signature(before) != signature(after) or
                signature(after) != signature(now)):
            _hold("FILE_CHANGED_DURING_READ")
        return data
    except OSError as exc:
        raise BackupError("REVIEW_REQUIRED_FILE_UNREADABLE") from exc
    finally:
        os.close(fd)


def _file_record(data):
    return {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def _book_rows(db):
    try:
        conn = sqlite3.connect("file:" + Path(db).resolve().as_posix() + "?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                _hold("DATABASE_INTEGRITY")
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                _hold("DATABASE_FOREIGN_KEYS")
            row = conn.execute("SELECT value FROM meta WHERE key='backup_ledger_id'").fetchone()
            if row is None:
                _hold("LEDGER_ID_MISSING")
            ledger_id = row[0]
            if str(uuid.UUID(ledger_id)) != ledger_id:
                _hold("LEDGER_ID_INVALID")
            queue = conn.execute("SELECT id,file_path FROM receipt_queue").fetchall()
            originals = conn.execute(
                "SELECT receipt_id,source_path,storage_name,sha256,size_bytes "
                "FROM receipt_originals").fetchall()
            if len(queue) != len(originals):
                _hold("LEGACY_OR_MISSING_ORIGINAL")
            by_id = {int(r[0]): r[1] for r in queue}
            names = {}
            for rid, source, name, sha, size in originals:
                if (rid not in by_id or by_id[rid] != source or
                        not isinstance(name, str) or not STORED_NAME.fullmatch(name) or
                        not isinstance(sha, str) or not SHA.fullmatch(sha) or
                        not isinstance(size, int) or size <= 0 or size > MAX_ORIGINAL or
                        name in names):
                    _hold("ORIGINAL_METADATA")
                names[name] = {"sha256": sha, "size": size}
            if len(names) != len(queue):
                _hold("ORIGINAL_DUPLICATE")
            return ledger_id, names, len(queue)
        finally:
            conn.close()
    except (sqlite3.Error, ValueError, TypeError) as exc:
        if isinstance(exc, BackupError):
            raise
        raise BackupError("REVIEW_REQUIRED_DATABASE_INVALID") from exc


def _inspect(archive):
    data = _regular_bytes(archive, MAX_TOTAL)
    try:
        with zipfile.ZipFile(__import__("io").BytesIO(data)) as z:
            entries = z.infolist()
            if not entries or len(entries) > MAX_FILES + 2:
                _hold("ARCHIVE_ENTRY_COUNT")
            names = [x.filename for x in entries]
            if len(names) != len(set(names)):
                _hold("DUPLICATE_ARCHIVE_ENTRY")
            for x in entries:
                name = x.filename
                if (name not in ("manifest.json", "books.sqlite3") and
                    not (name.startswith("receipt-originals/") and
                         STORED_NAME.fullmatch(name[len("receipt-originals/"):]))):
                    _hold("ARCHIVE_PATH")
                if (x.is_dir() or stat.S_ISLNK(x.external_attr >> 16) or
                        x.flag_bits & 1 or x.file_size > MAX_DB or
                        (name.startswith("receipt-originals/") and x.file_size > MAX_ORIGINAL)):
                    _hold("ARCHIVE_ENTRY_UNSAFE")
            if sum(x.file_size for x in entries) > MAX_TOTAL:
                _hold("ARCHIVE_TOO_LARGE")
            if "manifest.json" not in names or "books.sqlite3" not in names:
                _hold("MANIFEST_OR_DATABASE_MISSING")
            if z.getinfo("manifest.json").file_size > 1024 * 1024:
                _hold("MANIFEST_TOO_LARGE")
            raw = z.read("manifest.json")
            if len(raw) > 1024 * 1024:
                _hold("MANIFEST_TOO_LARGE")
            manifest = json.loads(raw.decode("utf-8"))
            if (not isinstance(manifest, dict) or manifest.get("format") != FORMAT or
                    not isinstance(manifest.get("files"), dict) or
                    set(names) != set(manifest["files"]) | {"manifest.json"}):
                _hold("MANIFEST_MISMATCH")
            files = {}
            for name in names:
                if name == "manifest.json":
                    continue
                item = manifest["files"].get(name)
                if not isinstance(item, dict) or set(item) != {"sha256", "size"}:
                    _hold("MANIFEST_FILE_RECORD")
                payload = z.read(name)
                if _file_record(payload) != item:
                    _hold("ARCHIVE_HASH_MISMATCH")
                files[name] = payload
    except (OSError, ValueError, UnicodeError, KeyError, zipfile.BadZipFile, RuntimeError) as exc:
        if isinstance(exc, BackupError):
            raise
        raise BackupError("REVIEW_REQUIRED_ARCHIVE_INVALID") from exc
    with tempfile.TemporaryDirectory(prefix="jp-backup-check-") as td:
        db = Path(td) / "books.sqlite3"
        db.write_bytes(files["books.sqlite3"])
        ledger_id, originals, count = _book_rows(db)
    if manifest.get("ledger_id") != ledger_id or manifest.get("receipt_count") != count:
        _hold("WRONG_LEDGER_OR_COUNT")
    if set(files) != {"books.sqlite3"} | {"receipt-originals/" + x for x in originals}:
        _hold("DATABASE_ARCHIVE_ORIGINAL_MISMATCH")
    for name, record in originals.items():
        if _file_record(files["receipt-originals/" + name]) != record:
            _hold("ORIGINAL_DATABASE_HASH_MISMATCH")
    return {"status": "VERIFIED_BACKUP", "ledger_id": ledger_id,
            "receipt_count": count, "files": files}


def inspect_backup(archive, expected_ledger_id=None):
    """Dry run only; returns a safe summary, never changes a ledger."""
    result = _inspect(archive)
    if expected_ledger_id is not None and result["ledger_id"] != expected_ledger_id:
        _hold("DIFFERENT_LEDGER")
    return {k: v for k, v in result.items() if k != "files"}


def create_backup(store, target):
    target = Path(target).expanduser().absolute()
    if (not target.parent.is_dir() or target.parent.is_symlink() or
            target.exists() or target.is_symlink()):
        _hold("BACKUP_DESTINATION_UNSAFE_OR_EXISTS")
    root = store.receipt_custody.root
    if root.is_symlink():
        _hold("ORIGINAL_STORAGE_LINK")
    ledger_id = store.conn.execute(
        "SELECT value FROM meta WHERE key='backup_ledger_id'").fetchone()
    if ledger_id is None:
        with store.conn:
            store.conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES(?,?)",
                               ("backup_ledger_id", str(uuid.uuid4())))
    with tempfile.TemporaryDirectory(prefix=".jp-backup-", dir=target.parent) as td:
        td = Path(td)
        snapshot = td / "books.sqlite3"
        conn = sqlite3.connect(snapshot)
        try:
            store.conn.backup(conn)
        finally:
            conn.close()
        ledger_id, originals, count = _book_rows(snapshot)
        if {p.name for p in root.iterdir()} != set(originals):
            _hold("ORPHAN_OR_UNEXPECTED_ORIGINAL")
        files = {"books.sqlite3": _regular_bytes(snapshot, MAX_DB)}
        for name, record in originals.items():
            payload = _regular_bytes(root / name, MAX_ORIGINAL)
            if _file_record(payload) != record:
                _hold("ORIGINAL_CHANGED_OR_MISSING")
            files["receipt-originals/" + name] = payload
        if sum(map(len, files.values())) > MAX_TOTAL:
            _hold("BACKUP_TOO_LARGE")
        manifest = {
            "format": FORMAT, "ledger_id": ledger_id, "receipt_count": count,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "files": {name: _file_record(data) for name, data in sorted(files.items())},
        }
        stage = td / "backup.zip"
        with zipfile.ZipFile(stage, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for name, data in sorted(files.items()):
                z.writestr(name, data)
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True))
        inspection = inspect_backup(stage, expected_ledger_id=ledger_id)
        # Hard link publishes a completed file without overwriting an existing target.
        try:
            os.link(stage, target)
        except OSError as exc:
            raise BackupError("REVIEW_REQUIRED_BACKUP_PUBLISH_FAILED") from exc
        return {**inspection, "path": str(target)}


def restore_backup(archive, destination_parent, expected_ledger_id=None):
    """Verified restore into a new sibling directory, never into a live DB."""
    result = _inspect(archive)
    if expected_ledger_id is not None and result["ledger_id"] != expected_ledger_id:
        _hold("DIFFERENT_LEDGER")
    parent = Path(destination_parent).expanduser().absolute()
    if not parent.is_dir() or parent.is_symlink():
        _hold("RESTORE_PARENT_UNSAFE")
    stage = Path(tempfile.mkdtemp(prefix=".jp-restore-", dir=parent))
    try:
        (stage / "receipt-originals").mkdir(mode=0o700)
        for name, data in result["files"].items():
            path = stage / name
            with path.open("xb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
        ledger, originals, count = _book_rows(stage / "books.sqlite3")
        if ledger != result["ledger_id"] or count != result["receipt_count"]:
            _hold("RESTORE_DATABASE_MISMATCH")
        for name, record in originals.items():
            if _file_record(_regular_bytes(stage / "receipt-originals" / name,
                                           MAX_ORIGINAL)) != record:
                _hold("RESTORE_ORIGINAL_MISMATCH")
        # Unpredictable, new-only name; no existing ledger is ever modified.
        dest = parent / ("restored-jp-book-" + uuid.uuid4().hex)
        if dest.exists() or dest.is_symlink():
            _hold("RESTORE_DESTINATION_EXISTS")
        os.rename(stage, dest)
        return {"status": "RESTORED_NEW_BOOK", "ledger_id": ledger,
                "receipt_count": count, "database": str(dest / "books.sqlite3"),
                "originals": str(dest / "receipt-originals")}
    except (OSError, sqlite3.Error) as exc:
        raise BackupError("REVIEW_REQUIRED_RESTORE_FAILED") from exc
    finally:
        if stage.exists():
            import shutil
            shutil.rmtree(stage)
