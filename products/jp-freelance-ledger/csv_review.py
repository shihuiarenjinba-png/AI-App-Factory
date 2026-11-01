"""Review-first, idempotent import of this product's own Japanese CSV format.

Import is local only. A preview never posts transactions. The user must confirm
before apply_csv_import is called. This is not a tax filing or bank feed import.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path

from core import CATEGORIES, DOCUMENT_TYPES, validate_date

CSV_FIELDS = ("取引日", "種別", "金額(円)", "勘定科目", "取引先", "証憑種別", "証憑参照", "摘要")
MAX_BYTES = 8_000_000
MAX_ROWS = 5_000
MAX_FIELD_LENGTH = 2_000


class CSVReviewError(ValueError):
    pass


def _normalize(raw):
    if None in raw or any(value is None for value in raw.values()):
        raise CSVReviewError("列数が一致しません")
    fields = [str(raw[key]).strip() for key in CSV_FIELDS]
    if any(len(value) > MAX_FIELD_LENGTH for value in fields):
        raise CSVReviewError("入力が長すぎます")
    try:
        fields[0] = validate_date(fields[0])
    except (ValueError, TypeError) as exc:
        raise CSVReviewError("日付はYYYY-MM-DD形式にしてください") from exc
    if fields[1] not in ("収入", "経費"):
        raise CSVReviewError("種別は収入または経費を選択してください")
    if not re.fullmatch(r"[0-9]+", fields[2]) or int(fields[2]) < 1:
        raise CSVReviewError("金額は1円以上の整数で入力してください")
    amount_text = fields[2].lstrip("0") or "0"
    if len(amount_text) > 19 or int(amount_text) > 9223372036854775807:
        raise CSVReviewError("金額が保存可能な範囲を超えています")
    fields[2] = amount_text
    if fields[3] not in CATEGORIES:
        raise CSVReviewError("勘定科目が一覧にありません。手動で確認してください")
    if fields[5] and fields[5] not in DOCUMENT_TYPES:
        raise CSVReviewError("証憑種別が一覧にありません")
    return fields


def _fingerprint(fields):
    payload = json.dumps(fields, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ensure_table(store):
    store.conn.execute("""
        CREATE TABLE IF NOT EXISTS csv_import_history (
            fingerprint TEXT PRIMARY KEY,
            transaction_id INTEGER NOT NULL REFERENCES transactions(id),
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _already_present(store, fields, fingerprint):
    if store.conn.execute(
        "SELECT 1 FROM csv_import_history WHERE fingerprint=?", (fingerprint,)
    ).fetchone():
        return True
    return bool(store.conn.execute("""
        SELECT 1 FROM transactions
        WHERE txn_date=? AND kind=? AND amount_yen=? AND category=?
          AND counterparty=? AND document_type=? AND document_path=? AND memo=?
        LIMIT 1
    """, (fields[0], fields[1], int(fields[2]), *fields[3:])).fetchone())


def review_csv(path, store):
    """Return a deterministic preview; never insert or modify a transaction."""
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise CSVReviewError("CSVファイルが存在しないか、8MBを超えています")
    data = path.read_bytes()
    try:
        content = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content, newline=""), strict=True)
        if tuple(reader.fieldnames or ()) != CSV_FIELDS:
            raise CSVReviewError("列名が一致しません。本アプリで出力したCSVを使用してください")
        _ensure_table(store)
        valid, errors, duplicates, seen = [], [], [], set()
        for line, raw in enumerate(reader, start=2):
            if line > MAX_ROWS + 1:
                raise CSVReviewError("5000行を超えるCSVは分割してください")
            try:
                fields = _normalize(raw)
            except CSVReviewError as exc:
                errors.append({"line": line, "reason": str(exc)})
                continue
            fingerprint = _fingerprint(fields)
            if fingerprint in seen or _already_present(store, fields, fingerprint):
                duplicates.append({"line": line, "reason": "同じ取引は登録済み、またはCSV内で重複"})
                continue
            seen.add(fingerprint)
            valid.append({"line": line, "fields": fields, "fingerprint": fingerprint})
    except (UnicodeError, csv.Error) as exc:
        raise CSVReviewError("CSVの文字コードまたは形式を確認してください（UTF-8形式）") from exc
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(data).hexdigest(),
        "valid": valid,
        "errors": errors,
        "duplicates": duplicates,
        "total": len(valid) + len(errors) + len(duplicates),
    }


def apply_csv_import(store, preview):
    """Commit only rows explicitly reviewed, and reject stale previews."""
    fresh = review_csv(preview["path"], store)
    if (fresh["sha256"] != preview["sha256"] or
        [r["fingerprint"] for r in fresh["valid"]] !=
        [r["fingerprint"] for r in preview["valid"]] or
        fresh["duplicates"] != preview["duplicates"] or
        fresh["errors"] != preview["errors"]):
        raise CSVReviewError("確認後にCSVまたは帳簿が変更されました。もう一度確認してください")
    count = 0
    with store.conn:
        _ensure_table(store)
        for row in fresh["valid"]:
            fields = row["fields"]
            if _already_present(store, fields, row["fingerprint"]):
                raise CSVReviewError("取引が途中で変更されました。再確認してください")
            cur = store.conn.execute("""
                INSERT INTO transactions
                (txn_date,kind,amount_yen,category,counterparty,document_type,document_path,memo)
                VALUES(?,?,?,?,?,?,?,?)
            """, (fields[0], fields[1], int(fields[2]), *fields[3:]))
            store.conn.execute(
                "INSERT INTO csv_import_history(fingerprint,transaction_id) VALUES(?,?)",
                (row["fingerprint"], int(cur.lastrowid)),
            )
            store.conn.execute(
                "INSERT INTO audit_log(action,entity_id,detail) VALUES(?,?,?)",
                ("CSV_IMPORT", int(cur.lastrowid), json.dumps({"source_sha256": fresh["sha256"], "csv_line": row["line"]})),
            )
            count += 1
    return {"imported": count, "duplicates": len(fresh["duplicates"]), "errors": len(fresh["errors"])}
