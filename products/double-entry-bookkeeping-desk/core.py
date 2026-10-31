from __future__ import annotations

import csv
import os
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

ACCOUNT_TYPES = ("asset", "liability", "equity", "revenue", "expense")
DEFAULT_ACCOUNTS = [
    ("1000", "現金", "Cash", "asset"),
    ("1100", "普通預金", "Bank", "asset"),
    ("1200", "売掛金", "Accounts Receivable", "asset"),
    ("2000", "買掛金", "Accounts Payable", "liability"),
    ("3000", "元入金・資本", "Owner Equity", "equity"),
    ("4000", "売上・サービス収益", "Sales / Service Revenue", "revenue"),
    ("5000", "消耗品費", "Supplies Expense", "expense"),
    ("5100", "地代家賃", "Rent Expense", "expense"),
    ("5200", "支払手数料・専門家費用", "Professional Fees", "expense"),
    ("5300", "旅費交通費", "Travel Expense", "expense"),
]

class BookError(ValueError):
    pass

def default_db_path() -> Path:
    base = Path(os.environ.get("APPDATA") or (Path.home() / ".local" / "share"))
    folder = base / "DoubleEntryBookkeepingDesk"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "books.sqlite3"

def validate_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise BookError("date must be YYYY-MM-DD") from exc

def amount_to_minor(value, currency: str, allow_zero: bool = True) -> int:
    if value in ("", None):
        return 0
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BookError("invalid amount") from exc
    if not amount.is_finite() or amount < 0 or (amount == 0 and not allow_zero):
        raise BookError("amount must be non-negative")
    factor = Decimal("1") if currency == "JPY" else Decimal("100")
    return int((amount * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

def minor_to_text(value: int, currency: str) -> str:
    if currency == "JPY":
        return f"{value:,}"
    return f"{Decimal(value) / Decimal(100):,.2f}"

class BookStore:
    def __init__(self, path: str | Path | None = None, currency: str = "JPY"):
        if currency not in {"JPY", "USD"}:
            raise BookError("currency must be JPY or USD")
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._create_schema()
        existing = self._meta_get("currency")
        if existing is None:
            self._meta_set("currency", currency)
        elif existing not in {"JPY", "USD"}:
            raise BookError("unsupported stored currency")
        self._seed_accounts()

    def _create_schema(self):
        self.conn.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS accounts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name_ja TEXT NOT NULL,
            name_en TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('asset','liability','equity','revenue','expense')),
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS journal_entries(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_date TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS journal_lines(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            debit_minor INTEGER NOT NULL DEFAULT 0 CHECK(debit_minor >= 0),
            credit_minor INTEGER NOT NULL DEFAULT 0 CHECK(credit_minor >= 0),
            CHECK((debit_minor > 0 AND credit_minor = 0) OR (credit_minor > 0 AND debit_minor = 0))
        );
        CREATE TABLE IF NOT EXISTS audit_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)
        self.conn.commit()

    def _meta_get(self, key):
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def _meta_set(self, key, value):
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        self.conn.commit()

    @property
    def currency(self):
        return self._meta_get("currency") or "JPY"

    @property
    def locked_through(self):
        return self._meta_get("locked_through")

    def set_currency(self, currency: str):
        if currency not in {"JPY", "USD"}:
            raise BookError("currency must be JPY or USD")
        if self.conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]:
            raise BookError("currency cannot change after entries exist")
        self._meta_set("currency", currency)

    def set_lock(self, through_date: str):
        through_date = validate_date(through_date)
        self._meta_set("locked_through", through_date)
        with self.conn:
            self.conn.execute(
                "INSERT INTO audit_log(action,detail) VALUES(?,?)",
                ("LOCK_PERIOD", through_date),
            )

    def _seed_accounts(self):
        if self.conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]:
            return
        with self.conn:
            self.conn.executemany(
                "INSERT INTO accounts(code,name_ja,name_en,type) VALUES(?,?,?,?)",
                DEFAULT_ACCOUNTS,
            )

    def add_account(self, code: str, name_ja: str, name_en: str, account_type: str) -> int:
        code, name_ja, name_en = code.strip(), name_ja.strip(), name_en.strip()
        if not code or not name_ja or not name_en or account_type not in ACCOUNT_TYPES:
            raise BookError("code, names and valid account type are required")
        try:
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO accounts(code,name_ja,name_en,type) VALUES(?,?,?,?)",
                    (code, name_ja, name_en, account_type),
                )
            return int(cur.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise BookError("account code already exists") from exc

    def accounts(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT id,code,name_ja,name_en,type,active FROM accounts WHERE active=1 ORDER BY code"
        ).fetchall()]

    def post_entry(self, entry_date: str, description: str, lines):
        entry_date = validate_date(entry_date)
        if self.locked_through and entry_date <= self.locked_through:
            raise BookError("period is locked")
        description = description.strip()
        if not description:
            raise BookError("description is required")
        normalized = []
        total_debit = total_credit = 0
        for code, debit, credit in lines:
            code = str(code).strip()
            if not code:
                continue
            account = self.conn.execute("SELECT id FROM accounts WHERE code=? AND active=1", (code,)).fetchone()
            if account is None:
                raise BookError(f"unknown account: {code}")
            d = amount_to_minor(debit, self.currency)
            c = amount_to_minor(credit, self.currency)
            if (d > 0) == (c > 0):
                raise BookError("each line must have either debit or credit")
            total_debit += d
            total_credit += c
            normalized.append((int(account["id"]), d, c))
        if len(normalized) < 2:
            raise BookError("at least two journal lines are required")
        if total_debit <= 0 or total_debit != total_credit:
            raise BookError("debits and credits must balance")
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO journal_entries(entry_date,description) VALUES(?,?)",
                (entry_date, description),
            )
            entry_id = int(cur.lastrowid)
            self.conn.executemany(
                "INSERT INTO journal_lines(entry_id,account_id,debit_minor,credit_minor) VALUES(?,?,?,?)",
                [(entry_id, account_id, debit, credit) for account_id, debit, credit in normalized],
            )
            self.conn.execute(
                "INSERT INTO audit_log(action,detail) VALUES(?,?)",
                ("POST_ENTRY", f"{entry_id}|{entry_date}|{total_debit}|{description}"),
            )
        return entry_id

    def journal(self, limit: int = 1000):
        rows = self.conn.execute(
            """SELECT e.id,e.entry_date,e.description,a.code,a.name_ja,a.name_en,
                      l.debit_minor,l.credit_minor
               FROM journal_entries e
               JOIN journal_lines l ON l.entry_id=e.id
               JOIN accounts a ON a.id=l.account_id
               ORDER BY e.entry_date DESC,e.id DESC,l.id ASC LIMIT ?""",
            (max(1, min(int(limit), 20000)),),
        ).fetchall()
        return [dict(r) for r in rows]

    def trial_balance(self):
        rows = self.conn.execute(
            """SELECT a.code,a.name_ja,a.name_en,a.type,
                      COALESCE(SUM(l.debit_minor),0) debit,
                      COALESCE(SUM(l.credit_minor),0) credit
               FROM accounts a LEFT JOIN journal_lines l ON l.account_id=a.id
               WHERE a.active=1
               GROUP BY a.id ORDER BY a.code"""
        ).fetchall()
        return [dict(r) for r in rows]

    def income_statement(self):
        revenue = expense = 0
        for row in self.trial_balance():
            if row["type"] == "revenue":
                revenue += int(row["credit"]) - int(row["debit"])
            elif row["type"] == "expense":
                expense += int(row["debit"]) - int(row["credit"])
        return {"revenue": revenue, "expense": expense, "net_income": revenue - expense}

    def balance_sheet(self):
        assets = liabilities = equity = 0
        for row in self.trial_balance():
            if row["type"] == "asset":
                assets += int(row["debit"]) - int(row["credit"])
            elif row["type"] == "liability":
                liabilities += int(row["credit"]) - int(row["debit"])
            elif row["type"] == "equity":
                equity += int(row["credit"]) - int(row["debit"])
        net_income = self.income_statement()["net_income"]
        return {
            "assets": assets,
            "liabilities": liabilities,
            "equity_before_current_income": equity,
            "current_net_income": net_income,
            "liabilities_and_equity": liabilities + equity + net_income,
        }

    def export_journal_csv(self, target: str | Path):
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["entry_id","date","description","account_code","account_ja","account_en","debit","credit","currency"])
            for row in reversed(self.journal(20000)):
                writer.writerow([
                    row["id"], row["entry_date"], row["description"], row["code"], row["name_ja"], row["name_en"],
                    minor_to_text(int(row["debit_minor"]), self.currency).replace(",", ""),
                    minor_to_text(int(row["credit_minor"]), self.currency).replace(",", ""),
                    self.currency,
                ])
        return target

    def backup_to(self, target: str | Path):
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        dest = sqlite3.connect(target)
        try:
            self.conn.backup(dest)
        finally:
            dest.close()
        return target

    def close(self):
        self.conn.close()
