"""Review-first monthly cashbook balance check (not bank reconciliation or tax filing)."""
from __future__ import annotations

import hashlib
import json
import re


class ReconciliationError(ValueError):
    pass


def _month(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise ReconciliationError("対象月は YYYY-MM 形式で入力してください")
    year, month = map(int, value.split("-"))
    if not 1 <= year <= 9999:
        raise ReconciliationError("対象年が範囲外です")
    return year, month


def _yen(value):
    if isinstance(value, bool) or not re.fullmatch(r"[+-]?\d{1,16}", str(value).strip()):
        raise ReconciliationError("残高は整数の円で入力してください（小数・カンマ不可）")
    amount = int(str(value).strip())
    if abs(amount) > 10**15:
        raise ReconciliationError("残高が上限を超えています")
    return amount


def _next_month(month):
    y, m = _month(month)
    if y == 9999 and m == 12:
        return "9999-12-32"
    return f"{y + (m == 12):04d}-{m % 12 + 1:02d}-01"


def _rows(conn, month):
    _month(month)
    return conn.execute(
        "SELECT id,txn_date,kind,amount_yen,category,counterparty,document_type,document_path,memo "
        "FROM transactions WHERE txn_date >= ? AND txn_date < ? ORDER BY txn_date,id",
        (month + "-01", _next_month(month)),
    ).fetchall()


def preview(conn, month, opening_yen, closing_yen):
    _month(month)
    opening, closing = _yen(opening_yen), _yen(closing_yen)
    records = [tuple(r) for r in _rows(conn, month)]
    if any(r[2] not in ("収入", "経費") or not isinstance(r[3], int) or r[3] <= 0 for r in records):
        raise ReconciliationError("取引データが不正です。帳簿を確認してください")
    income = sum(r[3] for r in records if r[2] == "収入")
    expense = sum(r[3] for r in records if r[2] == "経費")
    expected = opening + income - expense
    fingerprint = hashlib.sha256(json.dumps(records, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
    return {"month": month, "opening_yen": opening, "closing_yen": closing,
            "income_yen": income, "expense_yen": expense, "calculated_yen": expected,
            "difference_yen": closing - expected, "transaction_count": len(records),
            "source_sha256": fingerprint}


def _schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS monthly_balance_checks (
        month TEXT PRIMARY KEY, opening_yen INTEGER NOT NULL, closing_yen INTEGER NOT NULL,
        calculated_yen INTEGER NOT NULL, source_sha256 TEXT NOT NULL,
        checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")


def confirm(conn, month, opening_yen, closing_yen, expected_sha256):
    """Record an explicit zero-difference check; reject changed previews and duplicates."""
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ReconciliationError("確認対象の識別子が不正です")
    with conn:
        _schema(conn)
        result = preview(conn, month, opening_yen, closing_yen)
        if result["source_sha256"] != expected_sha256:
            raise ReconciliationError("確認後に取引が変更されました。もう一度照合してください")
        if result["difference_yen"]:
            raise ReconciliationError("残高差額がゼロではありません。記録できません")
        old = conn.execute("SELECT opening_yen,closing_yen,source_sha256 FROM monthly_balance_checks WHERE month=?", (month,)).fetchone()
        if old and tuple(old) == (result["opening_yen"], result["closing_yen"], result["source_sha256"]):
            return {**result, "recorded": False}
        conn.execute("""INSERT INTO monthly_balance_checks(month,opening_yen,closing_yen,calculated_yen,source_sha256)
            VALUES(?,?,?,?,?) ON CONFLICT(month) DO UPDATE SET
            opening_yen=excluded.opening_yen,closing_yen=excluded.closing_yen,
            calculated_yen=excluded.calculated_yen,source_sha256=excluded.source_sha256,
            checked_at=CURRENT_TIMESTAMP""",
            (month, result["opening_yen"], result["closing_yen"], result["calculated_yen"], result["source_sha256"]))
        conn.execute("INSERT INTO audit_log(action,entity_id,detail) VALUES(?,?,?)",
                     ("MONTH_BALANCE_CHECK", None, f"{month}|{result['source_sha256']}|{result['closing_yen']}"))
        return {**result, "recorded": True}


def status(conn, month):
    _month(month)
    _schema(conn)
    old = conn.execute("SELECT opening_yen,closing_yen,source_sha256 FROM monthly_balance_checks WHERE month=?", (month,)).fetchone()
    if old is None:
        return "未照合"
    current = preview(conn, month, old[0], old[1])
    return "再確認が必要" if current["source_sha256"] != old[2] or current["difference_yen"] else "照合済み"
