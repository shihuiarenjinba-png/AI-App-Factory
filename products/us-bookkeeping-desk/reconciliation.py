"""Local, reviewable US bank-statement reconciliation (bookkeeping only).

No bank feed, journal mutation, tax decision or silent posting. All balances
are cents, and the user explicitly chooses which journal lines cleared.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

class ReconciliationError(ValueError):
    pass

def _date(value):
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError) as exc:
        raise ReconciliationError("Date must be YYYY-MM-DD") from exc

def _cents(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            raise ValueError()
        return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ReconciliationError("Invalid statement balance") from exc

class BankReconciler:
    """Use with core.Store; never changes journal lines or financial reports."""
    def __init__(self, store):
        self.store, self.conn = store, store.conn
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS bank_reconciliations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            opening_cents INTEGER NOT NULL,
            closing_cents INTEGER NOT NULL,
            cleared_cents INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(account_id, end_date)
        );
        CREATE TABLE IF NOT EXISTS bank_reconciled_lines (
            line_id INTEGER PRIMARY KEY REFERENCES lines(id),
            reconciliation_id INTEGER NOT NULL REFERENCES bank_reconciliations(id)
        );
        """)
        self.conn.commit()

    def _account(self, code):
        row = self.conn.execute(
            "SELECT id,type FROM accounts WHERE code=? AND active=1", (str(code),)
        ).fetchone()
        if row is None or row["type"] != "asset":
            raise ReconciliationError("Select an active asset bank account")
        return int(row["id"])

    def _previous(self, account_id):
        return self.conn.execute(
            "SELECT * FROM bank_reconciliations WHERE account_id=? ORDER BY end_date DESC,id DESC LIMIT 1",
            (account_id,),
        ).fetchone()

    def _evaluate(self, code, start, end, opening, closing, line_ids):
        aid = self._account(code)
        start, end = _date(start), _date(end)
        if start > end:
            raise ReconciliationError("Start date must not exceed end date")
        opening, closing = _cents(opening), _cents(closing)
        previous = self._previous(aid)
        if previous:
            if start <= previous["end_date"]:
                raise ReconciliationError("Statement period overlaps a finalized reconciliation")
            if opening != previous["closing_cents"]:
                raise ReconciliationError("Opening balance must equal previous closing balance")
        else:
            booked = self.conn.execute("""
                SELECT COALESCE(SUM(l.debit_cents-l.credit_cents),0)
                FROM lines l JOIN entries e ON e.id=l.entry_id
                WHERE l.account_id=? AND e.entry_date < ?
            """, (aid, start)).fetchone()[0]
            if opening != booked:
                raise ReconciliationError("Opening balance does not match pre-period bank ledger")
        ids = list(line_ids)
        if len(ids) != len(set(ids)):
            raise ReconciliationError("Duplicate journal line selection")
        if any(not isinstance(i, int) or isinstance(i, bool) or i <= 0 for i in ids):
            raise ReconciliationError("Journal line IDs must be positive integers")
        # Outstanding lines from a previous statement can clear later. On the
        # first statement, pre-period lines are already in opening balance.
        earliest = "0001-01-01" if previous else start
        eligible = self.conn.execute("""
            SELECT l.id,e.entry_date,l.debit_cents,l.credit_cents,
                   CASE WHEN b.line_id IS NULL THEN 0 ELSE 1 END AS already_reconciled
            FROM lines l JOIN entries e ON e.id=l.entry_id
            LEFT JOIN bank_reconciled_lines b ON b.line_id=l.id
            WHERE l.account_id=? AND e.entry_date BETWEEN ? AND ?
            ORDER BY e.entry_date,e.id,l.id
        """, (aid, earliest, end)).fetchall()
        by_id = {int(r["id"]): r for r in eligible}
        if any(i not in by_id or by_id[i]["already_reconciled"] for i in ids):
            raise ReconciliationError("Out-of-period, foreign or already reconciled journal line")
        selected = set(ids)
        cleared = sum(int(by_id[i]["debit_cents"])-int(by_id[i]["credit_cents"]) for i in ids)
        outstanding = sum(int(r["debit_cents"])-int(r["credit_cents"])
                          for r in eligible if r["id"] not in selected and not r["already_reconciled"])
        book_end = self.conn.execute("""
            SELECT COALESCE(SUM(l.debit_cents-l.credit_cents),0)
            FROM lines l JOIN entries e ON e.id=l.entry_id
            WHERE l.account_id=? AND e.entry_date <= ?
        """, (aid, end)).fetchone()[0]
        difference = opening + cleared - closing
        return {
            "account_code": str(code), "start_date": start, "end_date": end,
            "opening_cents": opening, "statement_closing_cents": closing,
            "cleared_cents": cleared, "difference_cents": difference,
            "book_closing_cents": int(book_end), "outstanding_cents": outstanding,
            "selected_line_ids": sorted(ids), "ready": difference == 0,
            "review_required": True, "tax_decision": False,
        }

    def preview(self, code, start, end, opening, closing, line_ids):
        return self._evaluate(code, start, end, opening, closing, line_ids)

    def finalize(self, code, start, end, opening, closing, line_ids, confirmed=False):
        if not confirmed:
            raise ReconciliationError("Explicit user confirmation is required")
        try:
            # Revalidate under write lock; no TOCTOU between preview and save.
            self.conn.execute("BEGIN IMMEDIATE")
            result = self._evaluate(code, start, end, opening, closing, line_ids)
            if not result["ready"]:
                raise ReconciliationError("Statement difference must be zero")
            aid = self._account(code)
            cursor = self.conn.execute("""
                INSERT INTO bank_reconciliations
                (account_id,start_date,end_date,opening_cents,closing_cents,cleared_cents)
                VALUES(?,?,?,?,?,?)
            """, (aid,result["start_date"],result["end_date"],result["opening_cents"],
                  result["statement_closing_cents"],result["cleared_cents"]))
            rid = int(cursor.lastrowid)
            self.conn.executemany(
                "INSERT INTO bank_reconciled_lines(line_id,reconciliation_id) VALUES(?,?)",
                [(i,rid) for i in result["selected_line_ids"]],
            )
            self.conn.execute(
                "INSERT INTO audit_log(action,detail) VALUES('BANK_RECONCILE',?)",
                (f'{rid}|{code}|{result["start_date"]}|{result["end_date"]}|{result["statement_closing_cents"]}',),
            )
            self.conn.commit()
            return {**result, "reconciliation_id": rid}
        except Exception:
            self.conn.rollback()
            raise

    def history(self, code):
        aid = self._account(code)
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM bank_reconciliations WHERE account_id=? ORDER BY end_date,id", (aid,)
        )]
