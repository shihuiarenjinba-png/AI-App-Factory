"""Local-only verified receipt intake. No OCR, posting, or tax classification."""
from __future__ import annotations
import hashlib
import sqlite3
from pathlib import Path

MAX_RECEIPT_BYTES = 20 * 1024 * 1024
EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf", ".webp"}

def _format_ok(suffix: str, header: bytes) -> bool:
    if suffix == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in (".jpg", ".jpeg"):
        return header.startswith(b"\xff\xd8\xff")
    if suffix == ".pdf":
        return header.startswith(b"%PDF-")
    if suffix == ".webp":
        return header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    return False

def _prepare_schema(conn: sqlite3.Connection) -> None:
    """Upgrade receipt_queue in place, preserving legacy unverified rows."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(receipt_queue)")}
    if not cols:
        raise ValueError("証憑の保存先が初期化されていません")
    with conn:
        if "sha256" not in cols:
            conn.execute("ALTER TABLE receipt_queue ADD COLUMN sha256 TEXT")
        if "size_bytes" not in cols:
            conn.execute("ALTER TABLE receipt_queue ADD COLUMN size_bytes INTEGER")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS receipt_queue_verified_sha ON receipt_queue(sha256) WHERE sha256 IS NOT NULL")

def _inspect(path: object, max_bytes: int) -> tuple[str, str, int]:
    p = Path(path).expanduser()
    if p.is_symlink():
        raise ValueError("ショートカットやシンボリックリンクは選択できません")
    if p.suffix.lower() not in EXTENSIONS:
        raise ValueError("PNG・JPEG・PDF・WebPのみ対応しています")
    if not p.is_file():
        raise ValueError("ファイルが見つかりません")
    size = p.stat().st_size
    if size == 0 or size > max_bytes:
        raise ValueError("ファイルが空、または20MBの上限を超えています")
    h = hashlib.sha256()
    count = 0
    with p.open("rb") as f:
        header = f.read(16)
        if not _format_ok(p.suffix.lower(), header):
            raise ValueError("拡張子とファイル形式が一致しません")
        h.update(header)
        count += len(header)
        while block := f.read(1024 * 1024):
            count += len(block)
            if count > max_bytes:
                raise ValueError("読み込み中にサイズ上限を超えました")
            h.update(block)
    if count != size:
        raise ValueError("読み込み中にファイルサイズが変わりました")
    return str(p.resolve(strict=True)), h.hexdigest(), count

def import_receipts_verified(conn: sqlite3.Connection, paths: object, max_bytes: int = MAX_RECEIPT_BYTES) -> dict:
    """Per-file validation; duplicate path/content rejected; no automatic posting."""
    if type(max_bytes) is not int or not 1 <= max_bytes <= 200 * 1024 * 1024:
        raise ValueError("ファイル容量上限は1〜209715200バイトの整数で指定してください")
    if paths is None or isinstance(paths, (str, bytes, Path)):
        raise ValueError("証憑は複数ファイルの一覧で指定してください")
    _prepare_schema(conn)
    result = {"added": 0, "duplicates": 0, "errors": 0, "details": []}
    for path in paths:
        try:
            resolved, digest, size = _inspect(path, max_bytes)
            with conn:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO receipt_queue(file_path,status,sha256,size_bytes,note) VALUES(?,?,?,?,?)",
                    (resolved, "PENDING", digest, size, "未読取・未記帳 / 原本は元の場所に保管"),
                )
                if cursor.rowcount == 1:
                    conn.execute("INSERT INTO audit_log(action,detail) VALUES('RECEIPT_ENQUEUE',?)", (f"sha256={digest}|bytes={size}",))
                    result["added"] += 1
                else:
                    result["duplicates"] += 1
        except (OSError, ValueError, sqlite3.Error, TypeError) as exc:
            result["errors"] += 1
            if len(result["details"]) < 10:
                result["details"].append(f"{Path(str(path)).name}: {exc}")
    return result

def list_receipts_verified(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    _prepare_schema(conn)
    rows = conn.execute(
        "SELECT file_path,sha256,size_bytes,status FROM receipt_queue WHERE sha256 IS NOT NULL ORDER BY id DESC LIMIT ?",
        (max(1, min(int(limit), 100)),),
    )
    return [{"name": Path(r[0]).name, "sha256": r[1], "size_bytes": r[2], "status": r[3]} for r in rows]
