"""Review-only US bank statement reconciliation. All amounts are integer USD cents.

This does not change journal entries, cleared flags, tax treatment or source files.
The first version requires statement opening = ledger opening, and does not
silently carry forward prior-period outstanding checks. No automatic posting.
"""
from __future__ import annotations
from collections.abc import Mapping
from core import BookError
from rollforward import _date, _period, _verify_journal

MAX_CENTS = 10**15

def _money(value, label):
    if type(value) is not int or abs(value) > MAX_CENTS:
        raise BookError(f"{label} must be an integer cent amount")
    return value

def preview_statement_reconciliation(
    store, account_code, start_date, end_date,
    opening_cents, closing_cents, statement_items, matches,
):
    """Match statement IDs to actual journal line IDs without mutating the book.

    statement_items: [{"id":str,"date":"YYYY-MM-DD","amount_cents":signed int},...]
    matches: {statement_id: ledger_line_id}; ledger IDs must be unique.
    An unmatched book line is reported as outstanding, not deleted or posted.
    """
    start, end = _period(start_date, end_date)
    opening = _money(opening_cents, "Opening statement balance")
    closing = _money(closing_cents, "Closing statement balance")
    if not isinstance(account_code, str) or not account_code.strip():
        raise BookError("Bank account code is required")
    if not isinstance(statement_items, list) or not isinstance(matches, Mapping):
        raise BookError("Statement items and matches must be a list and mapping")
    conn = store.conn
    account = conn.execute("SELECT id,type FROM accounts WHERE code=?", (account_code,)).fetchone()
    if account is None or account["type"] != "asset":
        raise BookError("Reconciliation requires an existing asset account")
    _verify_journal(conn, end)
    rows = conn.execute("""
        SELECT l.id AS line_id,e.id AS entry_id,e.entry_date,e.description,
               l.debit_cents,l.credit_cents
          FROM lines l JOIN entries e ON e.id=l.entry_id
         WHERE l.account_id=? AND e.entry_date<=?
         ORDER BY e.entry_date,e.id,l.id
    """, (account["id"],end)).fetchall()
    ledger_opening = sum(r["debit_cents"]-r["credit_cents"]
                         for r in rows if r["entry_date"] < start)
    if ledger_opening != opening:
        raise BookError("Opening statement balance differs from ledger; review prior outstanding items")
    period_rows = {r["line_id"]: r for r in rows if r["entry_date"] >= start}
    items = {}
    for item in statement_items:
        if not isinstance(item, Mapping):
            raise BookError("Invalid statement item")
        sid = item.get("id")
        if not isinstance(sid,str) or not sid.strip() or sid in items:
            raise BookError("Statement IDs must be unique nonempty strings")
        day = _date(item.get("date"))
        if not start <= day <= end:
            raise BookError("Statement item outside selected period")
        amount = _money(item.get("amount_cents"), "Statement amount")
        if amount == 0:
            raise BookError("Zero-value statement line needs manual review")
        items[sid] = {"id":sid,"date":day,"amount_cents":amount}
    if opening + sum(item["amount_cents"] for item in items.values()) != closing:
        raise BookError("Statement line totals do not equal stated closing balance")
    used_lines = set()
    matched = []
    for sid, line_id in matches.items():
        if sid not in items or type(line_id) is not int or line_id in used_lines:
            raise BookError("Unknown, duplicated or invalid statement-to-ledger match")
        line = period_rows.get(line_id)
        if line is None:
            raise BookError("Matched journal line is outside account or statement period")
        amount = line["debit_cents"]-line["credit_cents"]
        if amount != items[sid]["amount_cents"]:
            raise BookError("Statement and journal amounts differ")
        used_lines.add(line_id)
        matched.append({"statement_id":sid,"line_id":line_id,
                        "entry_id":line["entry_id"],"amount_cents":amount})
    unmatched_statement = sorted(set(items)-set(matches))
    outstanding = [
        {"line_id":r["line_id"],"entry_id":r["entry_id"],
         "entry_date":r["entry_date"],"amount_cents":r["debit_cents"]-r["credit_cents"]}
        for r in period_rows.values() if r["line_id"] not in used_lines
    ]
    cleared = sum(row["amount_cents"] for row in matched)
    all_book = sum(r["debit_cents"]-r["credit_cents"] for r in period_rows.values())
    reconciled_balance = ledger_opening + cleared
    difference = closing - reconciled_balance
    outstanding_delta = all_book - cleared
    book_closing = ledger_opening + all_book
    if book_closing != reconciled_balance + outstanding_delta:
        raise BookError("Ledger movement reconciliation mismatch")
    return {
        "account_code":account_code,"start_date":start,"end_date":end,
        "statement_opening_cents":opening,"statement_closing_cents":closing,
        "book_opening_cents":ledger_opening,"book_closing_cents":book_closing,
        "reconciled_balance_cents":reconciled_balance,
        "outstanding_book_delta_cents":outstanding_delta,
        "difference_cents":difference,
        "matched":matched,"unmatched_statement_ids":unmatched_statement,
        "outstanding_book_lines":outstanding,
        "ready_for_manual_confirmation":bool(items) and not unmatched_statement and difference==0,
        "preview_only":True,"auto_post":False,"taxable_income":None,
    }
