"""Local active-book pointer for restored JP ledgers; no automatic merging."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import uuid
from pathlib import Path


class BookSelectionError(ValueError):
    pass


def _pointer(default_db):
    return Path(default_db).parent / "active-book.json"


def _validated_ledger(path):
    path = Path(path).expanduser().absolute()
    if path.name != "books.sqlite3" or path.is_symlink() or not path.is_file():
        raise BookSelectionError("復元した帳簿ファイルが見つからないか安全に開けません")
    try:
        conn = sqlite3.connect("file:" + path.resolve().as_posix() + "?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise BookSelectionError("帳簿データの整合性を確認できません")
            row = conn.execute("SELECT value FROM meta WHERE key='backup_ledger_id'").fetchone()
            if row is None:
                raise BookSelectionError("帳簿の識別情報がありません")
            ledger = str(uuid.UUID(row[0]))
            if ledger != row[0]:
                raise BookSelectionError("帳簿の識別情報が正しくありません")
            return ledger
        finally:
            conn.close()
    except (sqlite3.Error, TypeError, ValueError) as exc:
        if isinstance(exc, BookSelectionError):
            raise
        raise BookSelectionError("帳簿ファイルの確認に失敗しました") from exc


def active_book(default_db):
    """Do not silently fall back to a different ledger if the pointer is bad."""
    pointer = _pointer(default_db)
    if not pointer.exists() and not pointer.is_symlink():
        return Path(default_db)
    if pointer.is_symlink() or not pointer.is_file() or pointer.stat().st_size > 4096:
        raise BookSelectionError("前回の帳簿選択が安全に読み取れません")
    try:
        obj = json.loads(pointer.read_text(encoding="utf-8"))
        if not isinstance(obj, dict) or set(obj) != {"database", "ledger_id"}:
            raise BookSelectionError("前回の帳簿選択が不正です")
        selected = Path(obj["database"])
        if not selected.is_absolute() or _validated_ledger(selected) != obj["ledger_id"]:
            raise BookSelectionError("前回の帳簿と識別情報が一致しません")
        return selected
    except (OSError, ValueError, TypeError) as exc:
        if isinstance(exc, BookSelectionError):
            raise
        raise BookSelectionError("前回の帳簿選択が読み取れません") from exc


def remember_book(default_db, restored_db):
    """Persist a verified separate book for next launch; no DB is overwritten."""
    ledger_id = _validated_ledger(restored_db)
    pointer = _pointer(default_db)
    pointer.parent.mkdir(parents=True, exist_ok=True)
    if pointer.is_symlink():
        raise BookSelectionError("帳簿の選択先が安全ではありません")
    stage = None
    try:
        fd, stage = tempfile.mkstemp(prefix=".book-selection-", dir=pointer.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"database": str(Path(restored_db).absolute()),
                       "ledger_id": ledger_id}, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(stage, pointer)
        stage = None
    except OSError as exc:
        raise BookSelectionError("次回起動用の帳簿選択を保存できません") from exc
    finally:
        if stage is not None:
            Path(stage).unlink(missing_ok=True)
    return ledger_id


def reset_book(default_db):
    pointer = _pointer(default_db)
    if pointer.is_symlink():
        raise BookSelectionError("帳簿の選択先が安全ではありません")
    pointer.unlink(missing_ok=True)
