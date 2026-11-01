"""Local-only verified receipt reference queue. Does not perform OCR or accounting."""
from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

ALLOWED_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".pdf"})
DEFAULT_MAX_BYTES = 25 * 1024 * 1024


def _fingerprint(path: Path, max_bytes: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while chunk := stream.read(65536):
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("25MB等の設定上限を超えています")
            digest.update(chunk)
    if total == 0:
        raise ValueError("空のファイルは取り込めません")
    return digest.hexdigest(), total


def ingest_receipts(store, paths, max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    """Queue references individually; one broken file must not cancel other files.

    File content stays at its original location. Hashes prevent renamed copies
    from being queued again; no OCR, tax inference, upload or automatic posting.
    """
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("ファイル容量上限は正の整数で指定してください")
    store.conn.execute("""CREATE TABLE IF NOT EXISTS receipt_fingerprints (
        sha256 TEXT PRIMARY KEY,
        receipt_id INTEGER NOT NULL UNIQUE REFERENCES receipt_queue(id) ON DELETE CASCADE,
        size_bytes INTEGER NOT NULL CHECK(size_bytes > 0)
    )""")
    store.conn.commit()
    result = {"added": 0, "duplicates": 0, "rejected": 0, "items": []}
    for raw in paths:
        label = Path(str(raw)).name
        try:
            path = Path(os.fspath(raw)).expanduser().resolve(strict=True)
            if path.suffix.lower() not in ALLOWED_EXTENSIONS:
                raise ValueError("対応形式はPNG/JPEG/WebP/PDFです")
            if not path.is_file():
                raise ValueError("通常のファイルではありません")
            if path.stat().st_size > max_bytes:
                raise ValueError("ファイル容量の上限を超えています")
            fingerprint, size = _fingerprint(path, max_bytes)
            if path.stat().st_size != size:
                raise ValueError("読み取り中にファイルが変更されました")
            with store.conn:
                existing_path = store.conn.execute(
                    "SELECT id FROM receipt_queue WHERE file_path=?", (str(path),)
                ).fetchone()
                existing_hash = store.conn.execute(
                    "SELECT receipt_id FROM receipt_fingerprints WHERE sha256=?",
                    (fingerprint,),
                ).fetchone()
                if existing_path or existing_hash:
                    result["duplicates"] += 1
                    result["items"].append({"file": label, "status": "duplicate"})
                    continue
                row = store.conn.execute(
                    "INSERT INTO receipt_queue(file_path,status,note) VALUES(?,?,?)",
                    (str(path), "PENDING", "原本は元の場所に保持。OCR・自動記帳は未実施"),
                )
                store.conn.execute(
                    "INSERT INTO receipt_fingerprints(sha256,receipt_id,size_bytes) VALUES(?,?,?)",
                    (fingerprint, row.lastrowid, size),
                )
            result["added"] += 1
            result["items"].append({"file": label, "status": "queued"})
        except (OSError, ValueError, TypeError, sqlite3.Error) as exc:
            result["rejected"] += 1
            result["items"].append({"file": label, "status": "rejected", "reason": str(exc)})
    return result


def list_receipts(store, limit: int = 100) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("表示件数は1〜500で指定してください")
    return [
        {"id": int(row["id"]), "name": Path(row["file_path"]).name,
         "path": row["file_path"], "status": row["status"],
         "created_at": row["created_at"]}
        for row in store.conn.execute(
            "SELECT id,file_path,status,created_at FROM receipt_queue ORDER BY id DESC LIMIT ?",
            (limit,),
        )
    ]
