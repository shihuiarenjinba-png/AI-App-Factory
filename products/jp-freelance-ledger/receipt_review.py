"""Review-first, local-only receipt intake. No OCR or tax classification."""
from __future__ import annotations

import hashlib
from pathlib import Path

ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
MAX_FILES = 100
MAX_FILE_BYTES = 25 * 1024 * 1024


class ReceiptReviewError(ValueError):
    pass


def _inspect(value):
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ReceiptReviewError("通常のファイルを選択してください")
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ReceiptReviewError("画像（JPG/PNG/WebP）またはPDFのみ対応")
    size = path.stat().st_size
    if size < 1 or size > MAX_FILE_BYTES:
        raise ReceiptReviewError("空ファイルまたは25MB超のファイルです")
    digest = hashlib.sha256()
    read_bytes = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            read_bytes += len(chunk)
            if read_bytes > MAX_FILE_BYTES:
                raise ReceiptReviewError("25MBを超えています")
            digest.update(chunk)
    if read_bytes != size:
        raise ReceiptReviewError("読込中にファイルが変更されました")
    return {"path": str(path), "sha256": digest.hexdigest(), "size": size}


def _known(store):
    paths = {row[0] for row in store.conn.execute("SELECT file_path FROM receipt_queue")}
    table = store.conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='receipt_intake_index'"
    ).fetchone()
    hashes = {row[0] for row in store.conn.execute(
        "SELECT sha256 FROM receipt_intake_index"
    )} if table else set()
    return paths, hashes


def review_receipts(paths, store):
    """No DB writes. A bad file does not stop the rest of the batch."""
    values = list(paths)
    if len(values) > MAX_FILES:
        raise ReceiptReviewError("一度に選べるのは100ファイルまでです")
    known_paths, known_hashes = _known(store)
    valid, duplicates, errors = [], [], []
    seen_paths, seen_hashes = set(), set()
    for original in values:
        try:
            item = _inspect(original)
            if item["path"] in known_paths | seen_paths or item["sha256"] in known_hashes | seen_hashes:
                duplicates.append({"path": str(original), "reason": "登録済み、または同じ内容のファイル"})
            else:
                valid.append(item)
                seen_paths.add(item["path"])
                seen_hashes.add(item["sha256"])
        except (OSError, ValueError) as exc:
            errors.append({"path": str(original), "reason": str(exc)})
    return {"valid": valid, "duplicates": duplicates, "errors": errors}


def apply_receipt_review(store, preview):
    """Re-hash before atomic intake; never trust a stale preview."""
    valid = preview["valid"]
    verified = []
    for item in valid:
        try:
            current = _inspect(item["path"])
        except (OSError, ValueError) as exc:
            raise ReceiptReviewError("確認後にファイルを読めなくなりました。再確認してください") from exc
        if current != item:
            raise ReceiptReviewError("確認後にファイルが変更されました。もう一度確認してください")
        verified.append(current)
    imported, duplicates = 0, 0
    with store.conn:
        store.conn.execute("""CREATE TABLE IF NOT EXISTS receipt_intake_index(
            sha256 TEXT PRIMARY KEY, file_path TEXT NOT NULL UNIQUE,
            queue_id INTEGER NOT NULL, size_bytes INTEGER NOT NULL
        )""")
        for item in verified:
            existing = store.conn.execute(
                "SELECT 1 FROM receipt_queue WHERE file_path=?",
                (item["path"],)
            ).fetchone()
            same_hash = store.conn.execute(
                "SELECT 1 FROM receipt_intake_index WHERE sha256=?",
                (item["sha256"],)
            ).fetchone()
            if existing or same_hash:
                duplicates += 1
                continue
            cursor = store.conn.execute(
                "INSERT INTO receipt_queue(file_path) VALUES(?)", (item["path"],)
            )
            queue_id = int(cursor.lastrowid)
            store.conn.execute(
                "INSERT INTO receipt_intake_index(sha256,file_path,queue_id,size_bytes) VALUES(?,?,?,?)",
                (item["sha256"], item["path"], queue_id, item["size"])
            )
            store.conn.execute(
                "INSERT INTO audit_log(action,entity_id,detail) VALUES(?,?,?)",
                ("RECEIPT_QUEUE_ADD", queue_id, item["sha256"])
            )
            imported += 1
    return {"imported": imported, "duplicates": duplicates,
            "errors": len(preview["errors"])}
