"""Read-only account roll-forward and journal drill-down for local US books.

Amounts are integer USD cents. Balances are natural-sign balances: debit
positive for assets/expenses, credit positive for liabilities/equity/revenue.
This is a bookkeeping report, never a taxable-income determination.
"""
from __future__ import annotations

import re
from datetime import date


class RollForwardError(ValueError):
    pass


def _iso_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise RollForwardError("Dates must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise RollForwardError("Invalid calendar date") from exc


def account_rollforward(store, start_date, end_date, account_codes=None, include_zero=False):
    """Return opening + period activity = closing, with entry-level provenance.

    A selected-account report still verifies all journal entries, not just the
    filtered accounts. No tables or audit records are changed.
    """
    start, end = _iso_date(start_date), _iso_date(end_date)
    if start > end:
        raise RollForwardError("Start date must not exceed end date")
    if account_codes is not None:
        if isinstance(account_codes, (str, bytes)):
            raise RollForwardError("Account codes must be a sequence")
        try:
            codes = list(account_codes)
        except TypeError as exc:
            raise RollForwardError("Account codes must be a sequence") from exc
        if not codes or any(not isinstance(c, str) or not c.strip() for c in codes):
            raise RollForwardError("Select at least one valid account code")
        if len(codes) != len(set(codes)):
            raise RollForwardError("Duplicate account code selection")
        selected = set(codes)
    else:
        selected = None

    accounts = [dict(r) for r in store.conn.execute(
        "SELECT id,code,name,type FROM accounts ORDER BY code"
    )]
    by_id = {int(a["id"]): a for a in accounts}
    known = {a["code"] for a in accounts}
    if selected is not None and not selected.issubset(known):
        raise RollForwardError("Unknown account code")
    if any(a["type"] not in ("asset", "expense", "liability", "equity", "revenue") for a in accounts):
        raise RollForwardError("Unknown account type")

    report = {}
    for a in accounts:
        report[int(a["id"])] = {
            "code": a["code"], "name": a["name"], "type": a["type"],
            "opening_cents": 0, "period_debits_cents": 0,
            "period_credits_cents": 0, "movement_cents": 0,
            "closing_cents": 0, "entries": [],
        }
    entry_totals = {}
    all_opening_debits = all_opening_credits = 0
    all_period_debits = all_period_credits = 0
    sql = """SELECT e.id AS entry_id,e.entry_date,e.description,l.id AS line_id,
                    l.account_id,l.debit_cents,l.credit_cents
             FROM entries e JOIN lines l ON l.entry_id=e.id
             WHERE e.entry_date <= ? ORDER BY e.entry_date,e.id,l.id"""
    for line in store.conn.execute(sql, (end,)):
        eid, aid = int(line["entry_id"]), int(line["account_id"])
        debit, credit = int(line["debit_cents"]), int(line["credit_cents"])
        if aid not in by_id or debit < 0 or credit < 0 or (debit > 0) == (credit > 0):
            raise RollForwardError("Invalid or orphaned journal line")
        totals = entry_totals.setdefault(eid, [0, 0])
        totals[0] += debit
        totals[1] += credit
        row = report[aid]
        natural = 1 if row["type"] in ("asset", "expense") else -1
        movement = natural * (debit - credit)
        if line["entry_date"] < start:
            row["opening_cents"] += movement
            all_opening_debits += debit
            all_opening_credits += credit
        else:
            row["period_debits_cents"] += debit
            row["period_credits_cents"] += credit
            row["movement_cents"] += movement
            all_period_debits += debit
            all_period_credits += credit
            row["entries"].append({
                "entry_id": eid, "line_id": int(line["line_id"]),
                "date": line["entry_date"], "description": line["description"],
                "debit_cents": debit, "credit_cents": credit,
                "movement_cents": movement,
            })
    if any(debit != credit for debit, credit in entry_totals.values()):
        raise RollForwardError("Unbalanced journal entry detected; report withheld")
    if all_opening_debits != all_opening_credits or all_period_debits != all_period_credits:
        raise RollForwardError("Journal does not balance; report withheld")

    rows = []
    for a in accounts:
        row = report[int(a["id"])]
        row["closing_cents"] = row["opening_cents"] + row["movement_cents"]
        running = row["opening_cents"]
        for line in row["entries"]:
            running += line["movement_cents"]
            line["running_balance_cents"] = running
        if running != row["closing_cents"]:
            raise RollForwardError("Roll-forward reconciliation failed")
        if selected is not None and row["code"] not in selected:
            continue
        if include_zero or row["opening_cents"] or row["movement_cents"] or row["entries"]:
            rows.append(row)
    return {
        "start_date": start, "end_date": end,
        "currency": "USD", "accounting_method": store.accounting_method,
        "balance_basis": "natural_sign", "taxable_income": False,
        "rows": rows,
        "journal_check": {
            "opening_debits_cents": all_opening_debits,
            "opening_credits_cents": all_opening_credits,
            "period_debits_cents": all_period_debits,
            "period_credits_cents": all_period_credits,
            "balanced": True,
        },
    }
