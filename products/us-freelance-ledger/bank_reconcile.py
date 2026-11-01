"""Manual bank-statement matching for the US-only local bookkeeping ledger.

This does not import bank data, validate a tax deduction, or replace a bank statement.
All money arithmetic uses integer cents. Existing transaction amounts are immutable.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any


class BankReviewError(ValueError):
    pass


def _day(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("Non-canonical date")
        return value
    except (TypeError, ValueError) as exc:
        raise BankReviewError("Use a valid YYYY-MM-DD statement date") from exc


def _account(value: str) -> str:
    value = (value or "").strip()
    if not value or len(value) > 80:
        raise BankReviewError("Enter a bank account label (1-80 characters)")
    return value


def _cents(value: Any) -> int:
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount != amount.quantize(Decimal("0.01")):
            raise ValueError("Not an exact cent amount")
        cents = int(amount * 100)
        if abs(cents) > 2**63 - 1:
            raise ValueError("Out of range")
        return cents
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BankReviewError("Enter a valid dollar amount with at most two decimals") from exc


def _schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS bank_reconciliations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account TEXT NOT NULL,
        statement_date TEXT NOT NULL,
        opening_cents INTEGER NOT NULL,
        closing_cents INTEGER NOT NULL,
        movement_cents INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(account, statement_date)
    );
    CREATE TABLE IF NOT EXISTS bank_matches (
        transaction_id INTEGER PRIMARY KEY REFERENCES transactions(id) ON DELETE RESTRICT,
        account TEXT NOT NULL,
        statement_date TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('CLEARED', 'RECONCILED')),
        reconciliation_id INTEGER REFERENCES bank_reconciliations(id)
    );
    """)
    conn.commit()


def _require_cash_book(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT value FROM meta WHERE key='accounting_method'").fetchone()
    if row is None or row[0] != "cash":
        raise BankReviewError("Statement matching is available only for cash-basis books; accrual requires separate payment tracking")


def match_transaction(conn: sqlite3.Connection, transaction_id: int, account: str, statement_date: str) -> None:
    _schema(conn)
    _require_cash_book(conn)
    account, statement_date = _account(account), _day(statement_date)
    row = conn.execute("SELECT txn_date FROM transactions WHERE id=?", (transaction_id,)).fetchone()
    if row is None:
        raise BankReviewError("Select an existing transaction")
    if row[0] > statement_date:
        raise BankReviewError("Statement date cannot be before the transaction date")
    if conn.execute("SELECT 1 FROM bank_reconciliations WHERE account=? AND statement_date=?",
                    (account, statement_date)).fetchone():
        raise BankReviewError("This statement has already been finalized")
    try:
        with conn:
            conn.execute(
                "INSERT INTO bank_matches(transaction_id,account,statement_date,status) VALUES(?,?,?,'CLEARED')",
                (transaction_id, account, statement_date),
            )
            conn.execute(
                "INSERT INTO audit_log(action,entity_id,detail) VALUES(?,?,?)",
                ("BANK_MATCH", transaction_id, f"{account}|{statement_date}"),
            )
    except sqlite3.IntegrityError as exc:
        raise BankReviewError("This transaction is already matched; remove the old match first") from exc


def unmatch_transaction(conn: sqlite3.Connection, transaction_id: int) -> None:
    _schema(conn)
    with conn:
        result = conn.execute(
            "DELETE FROM bank_matches WHERE transaction_id=? AND status='CLEARED'",
            (transaction_id,),
        )
        if result.rowcount != 1:
            raise BankReviewError("Only a not-yet-finalized match can be removed")
        conn.execute(
            "INSERT INTO audit_log(action,entity_id,detail) VALUES(?,?,?)",
            ("BANK_UNMATCH", transaction_id, "Manual statement match removed"),
        )


def match_statuses(conn: sqlite3.Connection) -> dict[int, str]:
    _schema(conn)
    return {int(row[0]): row[1] for row in conn.execute(
        "SELECT transaction_id,status FROM bank_matches"
    )}


def statement_preview(
    conn: sqlite3.Connection, account: str, statement_date: str,
    opening: Any, closing: Any,
) -> dict:
    _schema(conn)
    _require_cash_book(conn)
    account, statement_date = _account(account), _day(statement_date)
    opening_cents, closing_cents = _cents(opening), _cents(closing)
    if conn.execute(
        "SELECT 1 FROM bank_reconciliations WHERE account=? AND statement_date=?",
        (account, statement_date),
    ).fetchone():
        raise BankReviewError("This bank statement has already been finalized")
    prior = conn.execute(
        "SELECT closing_cents FROM bank_reconciliations WHERE account=? AND statement_date<? "
        "ORDER BY statement_date DESC LIMIT 1", (account, statement_date),
    ).fetchone()
    later = conn.execute(
        "SELECT 1 FROM bank_reconciliations WHERE account=? AND statement_date>? LIMIT 1",
        (account, statement_date),
    ).fetchone()
    if later:
        raise BankReviewError("Review statements in chronological order; a later statement is finalized")
    if prior is not None and prior[0] != opening_cents:
        raise BankReviewError("Opening balance differs from the previous finalized closing balance")
    rows = conn.execute(
        "SELECT t.id,t.kind,t.amount_cents FROM bank_matches m "
        "JOIN transactions t ON t.id=m.transaction_id "
        "WHERE m.account=? AND m.statement_date=? AND m.status='CLEARED' ORDER BY t.id",
        (account, statement_date),
    ).fetchall()
    if not rows:
        raise BankReviewError("Match at least one transaction to this statement first")
    movement = sum(int(r[2]) * (1 if r[1] == "income" else -1) for r in rows)
    calculated = opening_cents + movement
    if abs(calculated) > 2**63 - 1:
        raise BankReviewError("Statement total exceeds the supported range")
    return {
        "account": account, "statement_date": statement_date,
        "opening_cents": opening_cents, "closing_cents": closing_cents,
        "movement_cents": movement, "calculated_cents": calculated,
        "difference_cents": closing_cents - calculated,
        "transaction_ids": [int(r[0]) for r in rows],
    }


def finalize_statement(
    conn: sqlite3.Connection, account: str, statement_date: str,
    opening: Any, closing: Any,
) -> dict:
    preview = statement_preview(conn, account, statement_date, opening, closing)
    if preview["difference_cents"] != 0:
        raise BankReviewError("Balance difference must be zero before finalizing")
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO bank_reconciliations"
                "(account,statement_date,opening_cents,closing_cents,movement_cents)"
                " VALUES(?,?,?,?,?)",
                (preview["account"], preview["statement_date"],
                 preview["opening_cents"], preview["closing_cents"], preview["movement_cents"]),
            )
            for transaction_id in preview["transaction_ids"]:
                updated = conn.execute(
                    "UPDATE bank_matches SET status='RECONCILED',reconciliation_id=? "
                    "WHERE transaction_id=? AND status='CLEARED'",
                    (cur.lastrowid, transaction_id),
                )
                if updated.rowcount != 1:
                    raise BankReviewError("Statement match changed; retry after reviewing")
            conn.execute(
                "INSERT INTO audit_log(action,entity_id,detail) VALUES(?,?,?)",
                ("BANK_RECONCILE", cur.lastrowid,
                 f'{preview["account"]}|{preview["statement_date"]}|{preview["closing_cents"]}'),
            )
    except sqlite3.IntegrityError as exc:
        raise BankReviewError("Statement already exists or contains conflicting matches") from exc
    return preview
