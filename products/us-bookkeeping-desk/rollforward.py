"""Read-only US bookkeeping account roll-forward and journal drill-down.

Amounts are integer USD cents; book income is not taxable income.
No journal entry, locked period or tax treatment is modified.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from core import BookError

_TYPES = {"asset", "liability", "equity", "revenue", "expense"}
_CREDIT_NORMAL = {"liability", "equity", "revenue"}

def _date(value):
    if not isinstance(value, str):
        raise BookError("Date must use YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise BookError("Date must use YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise BookError("Date must use YYYY-MM-DD")
    return value

def _period(start_date, end_date):
    start, end = _date(start_date), _date(end_date)
    if start > end:
        raise BookError("Start date must not exceed end date")
    return start, end

def _verify_journal(conn, end):
    """Fail closed on incomplete or unbalanced posted journal entries."""
    rows = conn.execute("""
        SELECT e.id, COUNT(l.id) AS line_count,
               COALESCE(SUM(l.debit_cents),0) AS debits,
               COALESCE(SUM(l.credit_cents),0) AS credits
          FROM entries e LEFT JOIN lines l ON l.entry_id=e.id
         WHERE e.entry_date<=?
         GROUP BY e.id
    """, (end,)).fetchall()
    for row in rows:
        if row["line_count"] < 2 or row["debits"] <= 0 or row["debits"] != row["credits"]:
            raise BookError(f"Unbalanced or incomplete journal entry: {row['id']}")
    return len(rows)

def roll_forward(store, start_date, end_date):
    """Opening + period movements = closing, reconciled to trial, P&L and B/S."""
    start, end = _period(start_date, end_date)
    conn = store.conn
    count = _verify_journal(conn, end)
    accounts = conn.execute("SELECT code,name,type FROM accounts ORDER BY code").fetchall()
    balances = {}
    for a in accounts:
        if a["type"] not in _TYPES:
            raise BookError("Unsupported account type")
        balances[a["code"]] = {
            "code": a["code"], "name": a["name"], "type": a["type"],
            "opening_debits": 0, "opening_credits": 0,
            "period_debits": 0, "period_credits": 0, "entry_ids": set(),
        }
    lines = conn.execute("""
        SELECT a.code,e.id AS entry_id,e.entry_date,l.debit_cents,l.credit_cents
          FROM lines l JOIN entries e ON e.id=l.entry_id
          JOIN accounts a ON a.id=l.account_id
         WHERE e.entry_date<=?
         ORDER BY e.entry_date,e.id,l.id
    """, (end,)).fetchall()
    for line in lines:
        row = balances[line["code"]]
        if line["entry_date"] < start:
            row["opening_debits"] += line["debit_cents"]
            row["opening_credits"] += line["credit_cents"]
        else:
            row["period_debits"] += line["debit_cents"]
            row["period_credits"] += line["credit_cents"]
            row["entry_ids"].add(line["entry_id"])
    result, totals = [], defaultdict(int)
    for row in balances.values():
        row["opening_signed"] = row["opening_debits"] - row["opening_credits"]
        row["period_signed"] = row["period_debits"] - row["period_credits"]
        row["closing_signed"] = row["opening_signed"] + row["period_signed"]
        multiplier = -1 if row["type"] in _CREDIT_NORMAL else 1
        row["opening_normal"] = multiplier * row["opening_signed"]
        row["closing_normal"] = multiplier * row["closing_signed"]
        row["entry_ids"] = sorted(row["entry_ids"])
        for key in ("opening_debits", "opening_credits", "period_debits", "period_credits"):
            totals[key] += row[key]
        result.append(row)
    period_revenue = sum(x["period_credits"]-x["period_debits"] for x in result if x["type"]=="revenue")
    period_expense = sum(x["period_debits"]-x["period_credits"] for x in result if x["type"]=="expense")
    revenue = sum(x["closing_normal"] for x in result if x["type"]=="revenue")
    expense = sum(x["closing_normal"] for x in result if x["type"]=="expense")
    assets = sum(x["closing_normal"] for x in result if x["type"]=="asset")
    liabilities = sum(x["closing_normal"] for x in result if x["type"]=="liability")
    equity = sum(x["closing_normal"] for x in result if x["type"]=="equity")
    closing_debits = totals["opening_debits"]+totals["period_debits"]
    closing_credits = totals["opening_credits"]+totals["period_credits"]
    if closing_debits != closing_credits or assets != liabilities+equity+revenue-expense:
        raise BookError("Journal/trial balance/financial statement mismatch")
    return {
        "start_date": start, "end_date": end, "journal_entry_count": count,
        "accounts": result,
        "trial": {"debits": closing_debits, "credits": closing_credits, "balanced": True},
        "period_pl": {"revenue": period_revenue, "expense": period_expense,
                      "book_income": period_revenue-period_expense},
        "as_of_pl": {"revenue": revenue, "expense": expense,
                     "book_income": revenue-expense},
        "as_of_bs": {"assets": assets, "liabilities": liabilities, "equity": equity,
                     "book_income": revenue-expense,
                     "liabilities_equity_income": liabilities+equity+revenue-expense},
        "taxable_income": None,
    }

def account_drilldown(store, account_code, start_date, end_date):
    """Trace movements to journal and line IDs without changing source records."""
    start, end = _period(start_date, end_date)
    if not isinstance(account_code, str) or not account_code.strip():
        raise BookError("Account code is required")
    if not store.conn.execute("SELECT 1 FROM accounts WHERE code=?", (account_code,)).fetchone():
        raise BookError("Unknown account")
    _verify_journal(store.conn, end)
    return [dict(row) for row in store.conn.execute("""
        SELECT e.id AS entry_id,l.id AS line_id,e.entry_date,e.description,
               l.debit_cents,l.credit_cents
          FROM lines l JOIN entries e ON e.id=l.entry_id
          JOIN accounts a ON a.id=l.account_id
         WHERE a.code=? AND e.entry_date>=? AND e.entry_date<=?
         ORDER BY e.entry_date,e.id,l.id
    """, (account_code, start, end)).fetchall()]
