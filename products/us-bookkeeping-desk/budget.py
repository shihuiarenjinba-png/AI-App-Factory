"""Local monthly expense budgets; read-only actuals from posted double-entry journals.

Amounts are integer USD cents. Budget entries do not post journal lines and
do not claim tax deductibility. Negative actuals (refunds) are preserved.
"""
from __future__ import annotations

import re
from datetime import date

from core import BookError, cents


def valid_month(month):
    if not isinstance(month, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise BookError("Month must use YYYY-MM")
    try:
        date.fromisoformat(month + "-01")
    except ValueError as exc:
        raise BookError("Month must use YYYY-MM") from exc
    return month


class MonthlyBudgets:
    def __init__(self, store):
        self.store = store
        self.conn = store.conn
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS monthly_expense_budgets(
                    month TEXT NOT NULL,
                    account_id INTEGER NOT NULL REFERENCES accounts(id),
                    amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
                    PRIMARY KEY(month, account_id)
                )
            """)

    def set_budget(self, month, account_code, amount):
        month = valid_month(month)
        code = str(account_code).strip()
        row = self.conn.execute(
            "SELECT id FROM accounts WHERE code=? AND type='expense' AND active=1",
            (code,),
        ).fetchone()
        if row is None:
            raise BookError("Choose an active expense account")
        if amount in ("", None):
            raise BookError("Enter a spending target in USD")
        amount_cents = cents(amount)
        with self.conn:
            self.conn.execute("""
                INSERT INTO monthly_expense_budgets(month,account_id,amount_cents)
                VALUES(?,?,?)
                ON CONFLICT(month,account_id) DO UPDATE SET amount_cents=excluded.amount_cents
            """, (month, int(row["id"]), amount_cents))
            self.conn.execute(
                "INSERT INTO audit_log(action,detail) VALUES('BUDGET_SET',?)",
                (f"{month}|{code}|{amount_cents}",),
            )
        return amount_cents

    def report(self, month):
        month = valid_month(month)
        rows = []
        for row in self.conn.execute("""
            SELECT a.code,a.name,
                COALESCE(b.amount_cents,0) AS planned_cents,
                b.account_id IS NOT NULL AS has_budget,
                COALESCE(SUM(CASE WHEN e.entry_date >= ? AND e.entry_date < ?
                    THEN l.debit_cents-l.credit_cents ELSE 0 END),0) AS actual_cents
            FROM accounts a
            LEFT JOIN monthly_expense_budgets b ON b.account_id=a.id AND b.month=?
            LEFT JOIN lines l ON l.account_id=a.id
            LEFT JOIN entries e ON e.id=l.entry_id
            WHERE a.type='expense' AND a.active=1
            GROUP BY a.id ORDER BY a.code
        """, (month + "-01", _next_month(month), month)):
            actual = int(row["actual_cents"])
            planned = int(row["planned_cents"])
            if actual or row["has_budget"]:
                rows.append({
                    "code": row["code"], "name": row["name"],
                    "has_budget": bool(row["has_budget"]),
                    "planned_cents": planned, "actual_cents": actual,
                    "remaining_cents": planned - actual if row["has_budget"] else None,
                })
        return {
            "month": month, "currency": "USD", "book_only": True,
            "tax_decision": False,
            "rows": rows,
            "planned_cents": sum(r["planned_cents"] for r in rows if r["has_budget"]),
            "actual_cents": sum(r["actual_cents"] for r in rows),
            "unbudgeted_actual_cents": sum(r["actual_cents"] for r in rows if not r["has_budget"]),
        }


def _next_month(month):
    year, m = map(int, month.split("-"))
    return f"{year+1:04d}-01-01" if m == 12 else f"{year:04d}-{m+1:02d}-01"
