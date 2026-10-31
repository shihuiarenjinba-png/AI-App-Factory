"""Read-only US book account roll-forward and journal drill-down.

All amounts are integer cents from the local journal. These are book balances,
not tax balances, and neither method eligibility nor tax deductions are inferred.
"""
from __future__ import annotations

from datetime import date


class RollforwardError(ValueError):
    pass


def _date(value):
    if not isinstance(value, str):
        raise RollforwardError("Date must use YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise RollforwardError("Date must use YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise RollforwardError("Date must use YYYY-MM-DD")
    return value


def _range(start, end):
    start, end = _date(start), _date(end)
    if start > end:
        raise RollforwardError("Start date must not exceed end date")
    return start, end


def _codes(store, account_codes):
    if account_codes is None:
        return None
    if isinstance(account_codes, (str, bytes)):
        raise RollforwardError("Account codes must be a sequence")
    try:
        codes = list(account_codes)
    except TypeError as exc:
        raise RollforwardError("Account codes must be a sequence") from exc
    if not codes or any(not isinstance(c, str) or not c.strip() or c != c.strip() for c in codes):
        raise RollforwardError("Account codes must be nonempty exact strings")
    if len(codes) != len(set(codes)):
        raise RollforwardError("Duplicate account codes")
    placeholders = ",".join("?" for _ in codes)
    found = {r[0] for r in store.conn.execute(
        f"SELECT code FROM accounts WHERE active=1 AND code IN ({placeholders})", codes
    )}
    if found != set(codes):
        raise RollforwardError("Unknown or inactive account code")
    return codes


def account_rollforward(store, start_date, end_date, account_codes=None):
    """Return opening + period movement = closing for every active account.

    Signed balances are debit minus credit. Credit-normal accounts also include
    a normal-side presentation, without hiding negative/abnormal balances.
    Only an unfiltered full-chart report can assert a balancing invariant.
    """
    start, end = _range(start_date, end_date)
    codes = _codes(store, account_codes)
    sql = """
        SELECT a.code,a.name,a.type,
          COALESCE(SUM(CASE WHEN e.entry_date < ?
            THEN l.debit_cents-l.credit_cents ELSE 0 END),0) AS opening,
          COALESCE(SUM(CASE WHEN e.entry_date BETWEEN ? AND ?
            THEN l.debit_cents ELSE 0 END),0) AS period_debit,
          COALESCE(SUM(CASE WHEN e.entry_date BETWEEN ? AND ?
            THEN l.credit_cents ELSE 0 END),0) AS period_credit
        FROM accounts a
        LEFT JOIN lines l ON l.account_id=a.id
        LEFT JOIN entries e ON e.id=l.entry_id
        WHERE a.active=1
    """
    params = [start, start, end, start, end]
    if codes is not None:
        sql += " AND a.code IN (" + ",".join("?" for _ in codes) + ")"
        params.extend(codes)
    sql += " GROUP BY a.id ORDER BY a.code"
    rows = []
    for r in store.conn.execute(sql, params):
        opening = int(r["opening"])
        debit, credit = int(r["period_debit"]), int(r["period_credit"])
        closing = opening + debit - credit
        normal_side = "debit" if r["type"] in ("asset", "expense") else "credit"
        sign = 1 if normal_side == "debit" else -1
        rows.append({
            "code": r["code"], "name": r["name"], "type": r["type"],
            "normal_side": normal_side,
            "opening_debit_minus_credit_cents": opening,
            "period_debit_cents": debit, "period_credit_cents": credit,
            "closing_debit_minus_credit_cents": closing,
            "opening_normal_cents": sign * opening,
            "closing_normal_cents": sign * closing,
        })
    totals = {
        "opening_debit_minus_credit_cents": sum(r["opening_debit_minus_credit_cents"] for r in rows),
        "period_debit_cents": sum(r["period_debit_cents"] for r in rows),
        "period_credit_cents": sum(r["period_credit_cents"] for r in rows),
        "closing_debit_minus_credit_cents": sum(r["closing_debit_minus_credit_cents"] for r in rows),
    }
    full = codes is None
    return {
        "start_date": start, "end_date": end, "accounting_method": store.accounting_method,
        "book_only": True, "tax_decision": False, "complete_chart": full,
        "balanced": (totals["opening_debit_minus_credit_cents"] == 0
                     and totals["period_debit_cents"] == totals["period_credit_cents"]
                     and totals["closing_debit_minus_credit_cents"] == 0) if full else None,
        "totals": totals, "accounts": rows,
    }


def account_drilldown(store, code, start_date, end_date):
    """Source journal lines with a running signed balance for one account."""
    report = account_rollforward(store, start_date, end_date, [code])
    account = report["accounts"][0]
    balance = account["opening_debit_minus_credit_cents"]
    rows = []
    for r in store.conn.execute("""
        SELECT l.id AS line_id,e.id AS entry_id,e.entry_date,e.description,
               l.debit_cents,l.credit_cents
        FROM lines l JOIN entries e ON e.id=l.entry_id
        JOIN accounts a ON a.id=l.account_id
        WHERE a.code=? AND e.entry_date BETWEEN ? AND ?
        ORDER BY e.entry_date,e.id,l.id
    """, (code, report["start_date"], report["end_date"])):
        balance += int(r["debit_cents"]) - int(r["credit_cents"])
        rows.append({**dict(r), "running_debit_minus_credit_cents": balance})
    if balance != account["closing_debit_minus_credit_cents"]:
        raise RollforwardError("Journal and roll-forward mismatch")
    return {"account": account, "lines": rows, "book_only": True}
