"""Local-only monthly category budget review. A planning aid, not a tax determination."""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict

from core import CATEGORIES

INCOME_CATEGORIES = frozenset(("売上高", "受取手数料", "雑収入"))
MAX_BUDGET_YEN = 10**12


class BudgetError(ValueError):
    pass


def _month(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value):
        raise BudgetError("対象月は YYYY-MM 形式で入力してください")
    year, month = map(int, value.split("-"))
    if year < 1:
        raise BudgetError("対象年が範囲外です")
    return year, month


def _next_month(value):
    year, month = _month(value)
    if (year, month) == (9999, 12):
        return "9999-12-32"
    return f"{year + (month == 12):04d}-{month % 12 + 1:02d}-01"


def _validate_key(kind, category):
    if kind not in ("収入", "経費"):
        raise BudgetError("収入か経費を選択してください")
    if not isinstance(category, str) or category not in CATEGORIES:
        raise BudgetError("勘定科目を一覧から選んでください")
    if (category in INCOME_CATEGORIES) != (kind == "収入"):
        raise BudgetError("収入・経費と勘定科目の組み合わせを確認してください")


def _budget_yen(value):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]{1,13}", str(value).strip()):
        raise BudgetError("予算は0円以上の整数で入力してください（カンマ・小数不可）")
    amount = int(str(value).strip())
    if amount > MAX_BUDGET_YEN:
        raise BudgetError("予算が入力上限を超えています")
    return amount


def _schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS monthly_category_budgets (
        month TEXT NOT NULL, kind TEXT NOT NULL, category TEXT NOT NULL,
        budget_yen INTEGER NOT NULL CHECK(budget_yen >= 0),
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(month, kind, category))""")


def set_budget(conn, month, kind, category, budget_yen):
    """Explicitly set one budget; repeated identical saves have no extra audit entry."""
    _month(month)
    _validate_key(kind, category)
    amount = _budget_yen(budget_yen)
    with conn:
        _schema(conn)
        old = conn.execute(
            "SELECT budget_yen FROM monthly_category_budgets WHERE month=? AND kind=? AND category=?",
            (month, kind, category),
        ).fetchone()
        if old is not None and int(old[0]) == amount:
            return {"saved": False, "budget_yen": amount}
        conn.execute("""INSERT INTO monthly_category_budgets(month,kind,category,budget_yen)
            VALUES(?,?,?,?) ON CONFLICT(month,kind,category) DO UPDATE SET
            budget_yen=excluded.budget_yen, updated_at=CURRENT_TIMESTAMP""",
            (month, kind, category, amount))
        conn.execute("INSERT INTO audit_log(action,entity_id,detail) VALUES(?,?,?)",
                     ("MONTH_BUDGET_SET", None, f"{month}|{kind}|{category}|{amount}"))
    return {"saved": True, "budget_yen": amount}


def monthly_budget_report(conn, month):
    """Recompute from every transaction; show categories without budgets separately."""
    _month(month)
    _schema(conn)
    records = [tuple(r) for r in conn.execute(
        "SELECT id,txn_date,kind,amount_yen,category FROM transactions "
        "WHERE txn_date >= ? AND txn_date < ? ORDER BY txn_date,id",
        (month + "-01", _next_month(month)),
    ).fetchall()]
    actual = defaultdict(int)
    totals = {"収入": 0, "経費": 0}
    for rec in records:
        _, txn_date, kind, amount, category = rec
        if (not isinstance(txn_date, str) or not txn_date.startswith(month + "-")
                or kind not in totals or isinstance(amount, bool)
                or not isinstance(amount, int) or amount <= 0 or amount > 10**15
                or not isinstance(category, str) or not category.strip()):
            raise BudgetError("帳簿データに不整合があります。予算比較は中止しました")
        actual[(kind, category)] += amount
        totals[kind] += amount

    budget_rows = [tuple(r) for r in conn.execute(
        "SELECT kind,category,budget_yen FROM monthly_category_budgets "
        "WHERE month=? ORDER BY kind,category", (month,),
    ).fetchall()]
    budget_keys = set()
    rows = []
    for kind, category, amount in budget_rows:
        _validate_key(kind, category)
        if not isinstance(amount, int) or not 0 <= amount <= MAX_BUDGET_YEN:
            raise BudgetError("予算データに不整合があります。比較を中止しました")
        key = (kind, category)
        budget_keys.add(key)
        value = actual.get(key, 0)
        rows.append({"kind": kind, "category": category, "budget_yen": amount,
                     "actual_yen": value, "difference_yen": value - amount,
                     "budget_set": True})
    for key, value in sorted(actual.items()):
        if key not in budget_keys:
            rows.append({"kind": key[0], "category": key[1], "budget_yen": None,
                         "actual_yen": value, "difference_yen": None,
                         "budget_set": False})
    rows.sort(key=lambda r: (r["kind"], r["category"]))
    fingerprint = hashlib.sha256(json.dumps(
        [records, budget_rows], ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return {"month": month, "rows": rows, "transaction_count": len(records),
            "income_yen": totals["収入"], "expense_yen": totals["経費"],
            "net_yen": totals["収入"] - totals["経費"],
            "unbudgeted_categories": sum(not r["budget_set"] for r in rows),
            "source_sha256": fingerprint}
