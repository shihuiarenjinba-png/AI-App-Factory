"""Read-only JP bookkeeping roll-forward and source-entry drill-down.

This is a management/accounting report, not a tax-return or deduction engine.
Amounts are integer JPY; each movement is traceable to its posted journal line.
"""
from __future__ import annotations

import re
from datetime import date


class ReportError(ValueError):
    pass


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ReportError("日付はYYYY-MM-DD形式で指定してください")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ReportError("実在する日付を指定してください") from exc


def _period(start, end):
    start, end = _date(start), _date(end)
    if start > end:
        raise ReportError("開始日は終了日以前にしてください")
    return start, end


def _normal_sign(account_type):
    if account_type in ("資産", "費用"):
        return 1
    if account_type in ("負債", "純資産", "収益"):
        return -1
    raise ReportError("未対応の勘定科目区分です")


def account_roll_forward(store, code, start_date, end_date):
    """Opening + dated movements = closing, with source journal IDs.

    Negative normal balances (including contra assets) remain negative; they
    are not silently converted to positive amounts.
    """
    start, end = _period(start_date, end_date)
    row = store.conn.execute(
        "SELECT id,code,name,type FROM accounts WHERE code=?", (str(code),)
    ).fetchone()
    if row is None:
        raise ReportError("勘定科目が見つかりません")
    account = dict(row)
    sign = _normal_sign(account["type"])
    opening = store.conn.execute(
        """SELECT COALESCE(SUM(l.debit_yen),0),COALESCE(SUM(l.credit_yen),0)
           FROM lines l JOIN entries e ON e.id=l.entry_id
           WHERE l.account_id=? AND e.entry_date<?""",
        (account["id"], start),
    ).fetchone()
    opening_debit, opening_credit = map(int, opening)
    balance = sign * (opening_debit - opening_credit)
    movements = []
    for item in store.conn.execute(
        """SELECT l.id AS line_id,e.id AS entry_id,e.entry_date,e.description,
                  l.debit_yen,l.credit_yen
           FROM lines l JOIN entries e ON e.id=l.entry_id
           WHERE l.account_id=? AND e.entry_date>=? AND e.entry_date<=?
           ORDER BY e.entry_date,e.id,l.id""",
        (account["id"], start, end),
    ):
        entry = dict(item)
        debit, credit = int(entry["debit_yen"]), int(entry["credit_yen"])
        delta = sign * (debit - credit)
        balance += delta
        entry["signed_delta_yen"] = delta
        entry["running_balance_yen"] = balance
        movements.append(entry)
    debits = sum(int(r["debit_yen"]) for r in movements)
    credits = sum(int(r["credit_yen"]) for r in movements)
    opening_balance = sign * (opening_debit - opening_credit)
    return {
        "account_code": account["code"],
        "account_name": account["name"],
        "account_type": account["type"],
        "start_date": start,
        "end_date": end,
        "opening_balance_yen": opening_balance,
        "period_debits_yen": debits,
        "period_credits_yen": credits,
        "closing_balance_yen": balance,
        "movements": movements,
        "reconciles": balance == opening_balance + sign * (debits - credits),
        "taxable_income_claim": False,
    }


def period_roll_forward(store, start_date, end_date):
    """All-account control report tying period postings to journal/trial."""
    start, end = _period(start_date, end_date)
    accounts = store.conn.execute(
        "SELECT code,type FROM accounts ORDER BY code"
    ).fetchall()
    rows = [account_roll_forward(store, a["code"], start, end) for a in accounts]
    debits = sum(r["period_debits_yen"] for r in rows)
    credits = sum(r["period_credits_yen"] for r in rows)
    revenue = sum(
        r["period_credits_yen"] - r["period_debits_yen"]
        for r in rows if r["account_type"] == "収益"
    )
    expenses = sum(
        r["period_debits_yen"] - r["period_credits_yen"]
        for r in rows if r["account_type"] == "費用"
    )
    return {
        "start_date": start,
        "end_date": end,
        "accounts": rows,
        "period_debits_yen": debits,
        "period_credits_yen": credits,
        "journal_balanced": debits == credits,
        "all_accounts_reconcile": all(r["reconciles"] for r in rows),
        "period_revenue_yen": revenue,
        "period_expenses_yen": expenses,
        "period_net_income_yen": revenue - expenses,
        "taxable_income_claim": False,
    }
