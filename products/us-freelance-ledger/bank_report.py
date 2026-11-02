"""Read-only, evidence-bound export of a US bank reconciliation and its undo audit.

This is a bookkeeping receipt, NOT a bank verification or tax certification.
No online synchronization and no mutation of ledger entries.
"""
from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from bank_reconcile import BankReviewError, _account, _day, _require_cash_book, _schema


def _usd(cents: int) -> str:
    cents = int(cents)
    return ("-" if cents < 0 else "") + f"{abs(cents) // 100}.{abs(cents) % 100:02d}"


def _cell(value: object) -> str:
    """Avoid spreadsheet formula evaluation of user-provided labels/audit details."""
    value = str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")) and not value.lstrip().replace(".", "", 1).lstrip("-").isdigit():
        return "'" + value
    if value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def _read_receipt(conn: sqlite3.Connection, account: str, statement_date: str) -> dict:
    _schema(conn)
    _require_cash_book(conn)
    account, statement_date = _account(account), _day(statement_date)
    if conn.in_transaction:
        raise BankReviewError("Finish the current database operation before exporting")
    conn.execute("BEGIN")
    try:
        active = conn.execute(
            "SELECT id,opening_cents,closing_cents,movement_cents FROM bank_reconciliations "
            "WHERE account=? AND statement_date=?", (account, statement_date)
        ).fetchone()
        history = conn.execute(
            "SELECT id,action,entity_id,detail,created_at FROM audit_log "
            "WHERE action IN ('BANK_MATCH','BANK_RECONCILE','BANK_RECONCILE_MEMBERS',"
            "'BANK_RECONCILE_CANCEL') ORDER BY id"
        ).fetchall()
        snapshots = []
        for event in history:
            if event[1] != "BANK_RECONCILE_MEMBERS":
                continue
            try:
                candidate = json.loads(event[3])
            except (ValueError, TypeError):
                continue
            if isinstance(candidate, dict) and candidate.get("account") == account and candidate.get("statement_date") == statement_date:
                snapshots.append((event, candidate))
        if not snapshots:
            raise BankReviewError("No verified reconciliation membership; legacy records require manual review")
        source, snapshot = snapshots[-1]
        if type(source[2]) is not int or source[2] <= 0:
            raise BankReviewError("Reconciliation audit ID is damaged; REVIEW REQUIRED")
        rid = source[2]
        expected_keys = {
            "account", "statement_date", "opening_cents", "closing_cents",
            "movement_cents", "transaction_ids", "members"
        }
        if set(snapshot) != expected_keys or any(
            type(snapshot[key]) is not int for key in
            ("opening_cents", "closing_cents", "movement_cents")
        ):
            raise BankReviewError("Reconciliation evidence is incomplete or altered; REVIEW REQUIRED")
        ids = snapshot["transaction_ids"]
        members = snapshot["members"]
        if (not isinstance(ids, list) or not ids or
            any(type(i) is not int or i <= 0 for i in ids) or
            ids != sorted(set(ids)) or not isinstance(members, list) or
            [m.get("transaction_id") for m in members if isinstance(m, dict)] != ids or
            len(members) != len(ids)):
            raise BankReviewError("Reconciliation member evidence is damaged; REVIEW REQUIRED")
        if any(not isinstance(m, dict) or m.get("kind") not in ("income", "expense") or
               type(m.get("amount_cents")) is not int or m["amount_cents"] <= 0 for m in members):
            raise BankReviewError("Reconciliation amount evidence is damaged; REVIEW REQUIRED")
        try:
            opening = int(snapshot["opening_cents"])
            closing = int(snapshot["closing_cents"])
            movement = int(snapshot["movement_cents"])
        except (TypeError, ValueError, OverflowError) as exc:
            raise BankReviewError("Reconciliation balances are damaged; REVIEW REQUIRED") from exc
        if opening + movement != closing or sum(
            m["amount_cents"] * (1 if m["kind"] == "income" else -1) for m in members
        ) != movement:
            raise BankReviewError("Reconciliation totals do not match saved evidence; REVIEW REQUIRED")
        reconciled = [
            e for e in history
            if e[1] == "BANK_RECONCILE" and e[2] == rid and e[0] < source[0]
            and e[3] == f"{account}|{statement_date}|{closing}"
        ]
        cancellations = [e for e in history if e[1] == "BANK_RECONCILE_CANCEL" and e[2] == rid and e[0] > source[0]]
        if not reconciled:
            raise BankReviewError("Reconciliation audit is missing; REVIEW REQUIRED")
        if active is not None:
            if int(active[0]) != rid or cancellations or (int(active[1]), int(active[2]), int(active[3])) != (opening, closing, movement):
                raise BankReviewError("Active reconciliation conflicts with audit evidence; REVIEW REQUIRED")
            current = conn.execute(
                "SELECT m.transaction_id,t.kind,t.amount_cents,m.account,m.statement_date,m.status "
                "FROM bank_matches m LEFT JOIN transactions t ON t.id=m.transaction_id "
                "WHERE m.reconciliation_id=? ORDER BY m.transaction_id", (rid,)
            ).fetchall()
            actual = [{"transaction_id": int(x[0]), "kind": x[1], "amount_cents": x[2]} for x in current]
            if actual != members or any(x[3] != account or x[4] != statement_date or x[5] != "RECONCILED" for x in current):
                raise BankReviewError("Current matches differ from saved evidence; REVIEW REQUIRED")
            status = "CHECKED"
            selected_cancel = None
        else:
            selected_cancel = cancellations[-1] if cancellations else None
            if selected_cancel is None:
                raise BankReviewError("Statement is not finalized and has no verified undo audit")
            try:
                if json.loads(selected_cancel[3]) != snapshot:
                    raise ValueError("Undo evidence differs")
            except (ValueError, TypeError) as exc:
                raise BankReviewError("Undo audit is damaged; REVIEW REQUIRED") from exc
            status = "UNDONE (historical receipt)"
        relevant = []
        for event in history:
            eid, action, entity, detail, created_at = event
            if action == "BANK_MATCH" and entity in ids and detail == f"{account}|{statement_date}" and eid < source[0]:
                relevant.append((eid, action, entity, detail, created_at))
            elif action in ("BANK_RECONCILE", "BANK_RECONCILE_MEMBERS") and entity == rid and eid <= source[0]:
                relevant.append((eid, action, entity, detail, created_at))
            elif selected_cancel is not None and eid == selected_cancel[0]:
                relevant.append((eid, action, entity, detail, created_at))
        conn.commit()
        return {
            "account": account, "statement_date": statement_date, "status": status,
            "reconciliation_id": rid, "opening_cents": opening, "closing_cents": closing,
            "movement_cents": movement, "difference_cents": 0,
            "transaction_ids": ids, "members": members, "audit": relevant,
        }
    except Exception:
        conn.rollback()
        raise


def export_bank_report(conn: sqlite3.Connection, account: str, statement_date: str, csv_target: str | Path) -> dict:
    """Create CSV and readable TXT exclusively; never overwrite either file.

    Both outputs are removed if either write fails. A successful receipt always
    describes a verified checked statement or a verified historical undo.
    """
    try:
        report = _read_receipt(conn, account, statement_date)
    except sqlite3.DatabaseError as exc:
        raise BankReviewError("Bank database is unavailable or damaged; report not saved") from exc
    target = Path(csv_target).expanduser().absolute()
    if target.suffix.lower() != ".csv":
        raise BankReviewError("Choose a .csv output filename")
    human = target.with_suffix(".txt")
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    records = [["record_type", "field", "reference_id", "value", "notes"]]
    for field in ("account", "statement_date", "status", "reconciliation_id"):
        records.append(["statement", field, "", _cell(report[field]), ""])
    for field in ("opening_cents", "closing_cents", "movement_cents", "difference_cents"):
        records.append(["statement", field.replace("_cents", "_usd"), "", _usd(report[field]), ""])
    records.extend([
        ["statement", "generated_utc", "", generated, ""],
        ["statement", "csv_saved_to", "", str(target), ""],
        ["statement", "readable_saved_to", "", str(human), ""],
    ])
    for member in report["members"]:
        records.append([
            "member", "transaction", str(member["transaction_id"]),
            member["kind"], _usd(member["amount_cents"]),
        ])
    for event_id, action, entity, detail, created_at in report["audit"]:
        records.append(["audit", action, str(event_id), _cell(detail), _cell(created_at)])
    output = io.StringIO(newline="")
    csv.writer(output).writerows(records)
    text = [
        "US Freelance Ledger — manual bank reconciliation receipt",
        "Bookkeeping only. Not verified by a bank; not a tax determination.",
        f"Generated UTC: {generated}",
        f"CSV: {target}", f"Readable report: {human}",
        f"Account: {report['account']}",
        f"Statement ending: {report['statement_date']}",
        f"Status: {report['status']}",
        f"Reconciliation ID: {report['reconciliation_id']}",
        f"Opening USD: {_usd(report['opening_cents'])}",
        f"Cleared movement USD: {_usd(report['movement_cents'])}",
        f"Calculated / statement closing USD: {_usd(report['closing_cents'])}",
        f"Difference USD: {_usd(report['difference_cents'])}",
        "Transaction IDs: " + ", ".join(map(str, report["transaction_ids"])),
        "",
        "Matched transaction evidence (ID | type | USD):",
    ]
    text.extend(f"  {m['transaction_id']} | {m['kind']} | {_usd(m['amount_cents'])}" for m in report["members"])
    text.extend(["", "Reconciliation / cancellation audit (event ID | UTC/database time | action | detail):"])
    text.extend(f"  {eid} | {created} | {action} | {detail}" for eid, action, _, detail, created in report["audit"])
    text.extend(["", "REVIEW REQUIRED: compare with the original bank statement. Undo does not alter ledger amounts.",
                 "Historical undo reports describe the original action, not a current bank balance.", ""])
    created_paths = []
    try:
        for path, content, encoding in (
            (target, output.getvalue(), "utf-8-sig"),
            (human, "\n".join(text), "utf-8"),
        ):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created_paths.append(path)
            with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
    except (OSError, UnicodeError) as exc:
        for path in reversed(created_paths):
            try:
                path.unlink()
            except OSError:
                pass
        raise BankReviewError("Report not saved. Choose an unused CSV/TXT filename and a writable folder") from exc
    return {
        "csv_path": str(target), "text_path": str(human), "status": report["status"],
        "transaction_ids": report["transaction_ids"], "difference_cents": 0,
    }
