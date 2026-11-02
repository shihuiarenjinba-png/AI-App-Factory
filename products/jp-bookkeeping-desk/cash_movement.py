"""Read-only cash/bank movement summary for Japan-only local bookkeeping.

Not a statutory cash-flow statement or a tax calculation. Only explicitly
selected cash/bank accounts are included; internal transfers net to zero.
Every period movement retains the source journal entry ID.
"""
from __future__ import annotations

import re
from datetime import date

CASH_CODES = ("1000", "1010", "1100", "1110", "1120")


class CashMovementError(ValueError):
    pass


def _valid_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise CashMovementError("日付はYYYY-MM-DD形式で入力してください")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise CashMovementError("実在する日付を入力してください") from exc


def cash_movement_report(store, start_date, end_date, account_codes=None):
    start, end = _valid_date(start_date), _valid_date(end_date)
    if start > end:
        raise CashMovementError("開始日は終了日以前にしてください")
    codes = CASH_CODES if account_codes is None else tuple(account_codes)
    if not codes or len(set(codes)) != len(codes) or any(not isinstance(c, str) for c in codes):
        raise CashMovementError("現金・預金科目を重複なく選んでください")
    for code in codes:
        account = store.conn.execute(
            "SELECT type,active FROM accounts WHERE code=?", (code,)
        ).fetchone()
        if account is None or account["type"] != "資産" or not account["active"]:
            raise CashMovementError("対象にできない科目が含まれています")
    slots = ",".join("?" for _ in codes)
    def balance_through(op, day):
        row = store.conn.execute(
            f"""SELECT COALESCE(SUM(l.debit_yen-l.credit_yen),0)
                FROM lines l JOIN entries e ON e.id=l.entry_id
                JOIN accounts a ON a.id=l.account_id
                WHERE a.code IN ({slots}) AND e.entry_date {op} ?""",
            (*codes, day),
        ).fetchone()
        return int(row[0])
    opening = balance_through("<", start)
    closing_from_ledger = balance_through("<=", end)
    movements = []
    running = opening
    for row in store.conn.execute(
        f"""SELECT e.id AS entry_id,e.entry_date,e.description,
                   SUM(l.debit_yen) AS debits,SUM(l.credit_yen) AS credits
            FROM entries e JOIN lines l ON l.entry_id=e.id
            JOIN accounts a ON a.id=l.account_id
            WHERE a.code IN ({slots}) AND e.entry_date>=? AND e.entry_date<=?
            GROUP BY e.id,e.entry_date,e.description
            ORDER BY e.entry_date,e.id""",
        (*codes, start, end),
    ):
        debit, credit = int(row["debits"]), int(row["credits"])
        delta = debit-credit
        running += delta
        movements.append({
            "entry_id": int(row["entry_id"]),
            "date": row["entry_date"],
            "description": row["description"],
            "debit_yen": debit,
            "credit_yen": credit,
            "net_change_yen": delta,
            "balance_yen": running,
            "kind": "入金" if delta > 0 else "出金" if delta < 0 else "口座間移動等（増減なし）",
        })
    receipts = sum(max(0, row["net_change_yen"]) for row in movements)
    payments = sum(max(0, -row["net_change_yen"]) for row in movements)
    reconciles = running == opening + receipts-payments == closing_from_ledger
    return {
        "start_date": start,
        "end_date": end,
        "account_codes": list(codes),
        "opening_yen": opening,
        "receipts_yen": receipts,
        "payments_yen": payments,
        "net_change_yen": receipts-payments,
        "closing_yen": running,
        "source_ledger_closing_yen": closing_from_ledger,
        "reconciles": reconciles,
        "journal_balanced": bool(store.balance_check()["balanced"]),
        "movements": movements,
        "taxable_income_claim": False,
        "statutory_cash_flow_statement_claim": False,
    }
