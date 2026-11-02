"""JP/JPY monthly expense budget vs actual, for management only.

Reads posted journal lines; never posts entries or decides tax deductibility.
"""
from __future__ import annotations
import re
from datetime import date
from decimal import Decimal, InvalidOperation

MAX_YEN = 2**63 - 1

class BudgetError(ValueError):
    pass

def _month(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
        raise BudgetError("対象月はYYYY-MM形式で入力してください")
    year, month = map(int, value.split("-"))
    if not (2000 <= year <= 2100 and 1 <= month <= 12):
        raise BudgetError("対象月は2000-01から2100-12までで指定してください")
    return year, month

def _yen(value):
    if isinstance(value, bool):
        raise BudgetError("予算は0以上の整数円で入力してください")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BudgetError("予算は0以上の整数円で入力してください") from exc
    if not number.is_finite() or number != number.to_integral_value() or not 0 <= number <= MAX_YEN:
        raise BudgetError("予算は0以上の整数円で入力してください")
    return int(number)

class MonthlyBudget:
    def __init__(self, store):
        self.store = store
        self.db = store.conn
        with self.db:
            self.db.execute("""CREATE TABLE IF NOT EXISTS monthly_expense_budgets (
                year INTEGER NOT NULL CHECK(year BETWEEN 2000 AND 2100),
                month INTEGER NOT NULL CHECK(month BETWEEN 1 AND 12),
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                budget_yen INTEGER NOT NULL CHECK(budget_yen>=0),
                PRIMARY KEY(year,month,account_id)
            )""")

    def set_budget(self, period, account_code, amount_yen):
        year, month = _month(period)
        amount = _yen(amount_yen)
        account = self.db.execute(
            "SELECT id FROM accounts WHERE code=? AND type='費用' AND active=1",
            (str(account_code).strip(),),
        ).fetchone()
        if account is None:
            raise BudgetError("予算には使用中の費用科目を選んでください")
        account_id = int(account["id"])
        previous = self.db.execute(
            "SELECT budget_yen FROM monthly_expense_budgets WHERE year=? AND month=? AND account_id=?",
            (year, month, account_id),
        ).fetchone()
        if previous is not None and int(previous[0]) == amount:
            return False
        with self.db:
            self.db.execute("""INSERT INTO monthly_expense_budgets(year,month,account_id,budget_yen)
                VALUES(?,?,?,?) ON CONFLICT(year,month,account_id)
                DO UPDATE SET budget_yen=excluded.budget_yen""", (year, month, account_id, amount))
            self.db.execute("INSERT INTO audit_log(action,detail) VALUES('BUDGET_SET',?)",
                            (f"{year:04d}-{month:02d}|{str(account_code).strip()}|{amount}",))
        return True

    def report(self, period):
        year, month = _month(period)
        start = date(year, month, 1).isoformat()
        end = date(year + (month == 12), (month % 12) + 1, 1).isoformat()
        rows = []
        for item in self.db.execute("""SELECT a.code,a.name,b.budget_yen,
                COALESCE((SELECT SUM(l.debit_yen-l.credit_yen)
                    FROM lines l JOIN entries e ON e.id=l.entry_id
                    WHERE l.account_id=a.id AND e.entry_date>=? AND e.entry_date<?),0) AS actual_yen
                FROM accounts a
                LEFT JOIN monthly_expense_budgets b
                  ON b.account_id=a.id AND b.year=? AND b.month=?
                WHERE a.type='費用' AND a.active=1 ORDER BY a.code""", (start, end, year, month)):
            budget = None if item["budget_yen"] is None else int(item["budget_yen"])
            actual = int(item["actual_yen"])
            if budget is None and actual == 0:
                continue
            rows.append({"code": item["code"], "name": item["name"],
                         "budget_yen": budget, "actual_yen": actual,
                         "remaining_yen": None if budget is None else budget - actual,
                         "status": "未設定" if budget is None else ("超過" if actual > budget else "予算内")})
        budget_total = sum(row["budget_yen"] for row in rows if row["budget_yen"] is not None)
        actual_total = sum(row["actual_yen"] for row in rows)
        uncovered = sum(row["actual_yen"] for row in rows if row["budget_yen"] is None)
        coverage = all(row["budget_yen"] is not None for row in rows)
        return {"period": period, "rows": rows, "budget_total_yen": budget_total,
                "actual_total_yen": actual_total, "unbudgeted_actual_yen": uncovered,
                "all_active_expenses_budgeted": coverage,
                "total_remaining_yen": budget_total - actual_total if coverage else None,
                "taxable_income_claim": False}
