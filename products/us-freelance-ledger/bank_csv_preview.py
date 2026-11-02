"""Read-only US/USD bank CSV preview. Never imports, matches or posts transactions."""
from __future__ import annotations

import csv
import hashlib
import io
import os
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

MAX_SOURCE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 2000
REQUIRED = ("date", "amount", "direction", "currency")


class BankCSVError(ValueError):
    pass


def _safe_cell(value):
    return str(value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ")[:160]


def _money(raw):
    value = str(raw or "").strip()
    if not value or value.startswith(("+", "-")):
        raise BankCSVError("Missing or signed amount; use a positive USD amount and the direction column")
    try:
        number = Decimal(value.replace(",", ""))
        if not number.is_finite() or number <= 0 or number != number.quantize(Decimal("0.01")):
            raise ValueError("Not positive exact cents")
        cents = int(number * 100)
        if cents > 2**63 - 1:
            raise ValueError("Out of range")
        return cents
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise BankCSVError("Amount must be positive USD with at most two decimals") from exc


def _direction(raw):
    value = str(raw or "").strip().lower()
    if value in ("credit", "deposit", "income", "in"):
        return "income"
    if value in ("debit", "withdrawal", "expense", "out"):
        return "expense"
    raise BankCSVError("Direction must be credit/debit, deposit/withdrawal, income/expense or in/out")


def _date(raw):
    value = str(raw or "").strip()
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("Noncanonical date")
    except (TypeError, ValueError) as exc:
        raise BankCSVError("Date must be a real YYYY-MM-DD date") from exc
    return value


def csv_headers(source):
    path = Path(source)
    try:
        if not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
            raise BankCSVError("Choose a CSV file no larger than 5 MiB")
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            headers = next(reader)
        if not headers or len(headers) > 60 or any(not x.strip() for x in headers):
            raise BankCSVError("CSV needs a non-empty header row (60 columns maximum)")
        if len(headers) != len(set(headers)):
            raise BankCSVError("Duplicate CSV header names must be corrected first")
        return headers
    except (OSError, UnicodeError, csv.Error, StopIteration) as exc:
        raise BankCSVError("Cannot read CSV header; use UTF-8 CSV with a header row") from exc


def preview_bank_csv(source, mapping, conn):
    """Pure preview: no INSERT/UPDATE/DELETE and no transaction changes."""
    headers = csv_headers(source)
    if set(mapping) != set(REQUIRED) or any(mapping[k] not in headers for k in REQUIRED):
        raise BankCSVError("Map Date, Amount, In/Out and Currency to four existing CSV columns")
    if len(set(mapping.values())) != 4:
        raise BankCSVError("Each mapped field needs a different CSV column")
    try:
        raw = Path(source).read_bytes()
        if len(raw) > MAX_SOURCE_BYTES:
            raise BankCSVError("CSV is larger than 5 MiB")
        decoded = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(decoded, newline=""), strict=True)
        if reader.fieldnames != headers:
            raise BankCSVError("CSV header changed; select the file again")
        ledger = {}
        for item in conn.execute(
            "SELECT id,txn_date,kind,amount_cents FROM transactions ORDER BY id"
        ):
            key = (str(item[1]), str(item[2]), int(item[3]))
            ledger.setdefault(key, []).append(int(item[0]))
        rows = []
        seen = set()
        for index, item in enumerate(reader, 2):
            if index > MAX_ROWS + 1:
                raise BankCSVError("CSV exceeds 2000 records; split it before review")
            if None in item or any(v is None for v in item.values()):
                raise BankCSVError("CSV row has missing or extra columns; correct the file")
            currency = str(item[mapping["currency"]] or "").strip().upper()
            if currency != "USD":
                raise BankCSVError(
                    "Only explicitly labelled USD rows are supported; foreign or missing currency was refused"
                )
            issues = []
            try:
                day = _date(item[mapping["date"]])
                cents = _money(item[mapping["amount"]])
                kind = _direction(item[mapping["direction"]])
                key = (day, kind, cents)
                candidates = ledger.get(key, [])
                if key in seen:
                    issues.append("DUPLICATE_CSV_CANDIDATE")
                seen.add(key)
                if not candidates:
                    issues.append("NO_LEDGER_CANDIDATE")
                elif len(candidates) > 1:
                    issues.append("MULTIPLE_LEDGER_CANDIDATES")
            except BankCSVError as exc:
                day, cents, kind, candidates = "", None, "", []
                issues.append("INVALID_ROW: " + str(exc))
            rows.append({
                "line": index, "date": day, "amount_cents": cents, "direction": kind,
                "ledger_candidate_ids": candidates,
                "status": "REVIEW REQUIRED" if issues else "CANDIDATE ONLY",
                "issues": issues,
            })
        if not rows:
            raise BankCSVError("CSV has no transaction rows")
        return {
            "source": str(Path(source).resolve()), "source_sha256": hashlib.sha256(raw).hexdigest(),
            "mapping": dict(mapping), "currency": "USD", "rows": rows,
            "review_required": sum(x["status"] == "REVIEW REQUIRED" for x in rows),
            "ledger_unchanged": True,
        }
    except (OSError, UnicodeError, csv.Error, sqlite3.DatabaseError) as exc:
        raise BankCSVError("CSV preview failed; ledger remains unchanged") from exc


def save_review_report(preview, destination):
    """Save an explicitly requested review copy without overwriting anything."""
    path = Path(destination)
    if path.suffix.lower() != ".txt":
        raise BankCSVError("Save the review copy as a .txt file")
    if not path.parent.is_dir():
        raise BankCSVError("Choose an existing destination folder")
    lines = [
        "US BANK CSV REVIEW — NOT POSTED — REVIEW REQUIRED",
        "Source: " + _safe_cell(preview["source"]),
        "Source SHA256: " + preview["source_sha256"],
        "Currency: USD",
        "Rows: " + str(len(preview["rows"])),
        "Rows requiring review: " + str(preview["review_required"]),
        "No ledger posting, bank verification, matching or tax certification.",
        "",
        "LINE | DATE | DIRECTION | USD CENTS | LEDGER CANDIDATES | STATUS | ISSUES",
    ]
    for row in preview["rows"]:
        lines.append(" | ".join([
            str(row["line"]), _safe_cell(row["date"]), _safe_cell(row["direction"]),
            str(row["amount_cents"]) if row["amount_cents"] is not None else "INVALID",
            ",".join(str(i) for i in row["ledger_candidate_ids"]),
            row["status"], "; ".join(_safe_cell(x) for x in row["issues"]),
        ]))
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise BankCSVError("Existing report was not overwritten; choose a new file name") from exc
    except OSError as exc:
        raise BankCSVError("Report could not be saved; do not assume success") from exc
    return str(path.resolve())
