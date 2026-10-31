from __future__ import annotations

import csv
import os
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

PROFILES = {
    "JP": {
        "currency": "JPY",
        "categories": [
            "売上高", "仕入高", "外注工賃", "消耗品費", "通信費", "旅費交通費",
            "地代家賃", "支払手数料", "広告宣伝費", "租税公課", "水道光熱費", "その他",
        ],
    },
    "US": {
        "currency": "USD",
        "categories": [
            "Business income", "Advertising", "Contract labor", "Insurance",
            "Legal & professional services", "Office expense", "Rent or lease",
            "Supplies", "Taxes & licenses", "Travel", "Meals - review",
            "Utilities", "Other",
        ],
    },
}

class LedgerError(ValueError):
    pass

def default_db_path() -> Path:
    base = Path(os.environ.get("APPDATA") or (Path.home() / ".local" / "share"))
    folder = base / "FreelanceLedgerLocal"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "books.sqlite3"

def profile_info(profile: str) -> dict:
    if profile not in PROFILES:
        raise LedgerError("profile must be JP or US")
    return PROFILES[profile]

def validate_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise LedgerError("date must be YYYY-MM-DD") from exc

def amount_to_minor(amount, currency: str) -> int:
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise LedgerError("invalid amount") from exc
    if not value.is_finite() or value <= 0:
        raise LedgerError("amount must be positive")
    factor = Decimal("1") if currency == "JPY" else Decimal("100")
    return int((value * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

def minor_to_text(value: int, currency: str) -> str:
    if currency == "JPY":
        return f"{value:,}"
    return f"{Decimal(value) / Decimal(100):,.2f}"

@dataclass(frozen=True)
class Transaction:
    id: int
    txn_date: str
    kind: str
    amount_minor: int
    category: str
    counterparty: str
    memo: str
    receipt_path: str

class LedgerStore:
    def __init__(self, path: str | Path | None = None, profile: str = "JP"):
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._create_schema()
        current = self._meta_get("profile")
        if current is None:
            profile_info(profile)
            self._meta_set("profile", profile)
        else:
            profile_info(current)

    def _create_schema(self) -> None:
        self.conn.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            txn_date TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('income','expense')),
            amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
            category TEXT NOT NULL,
            counterparty TEXT NOT NULL DEFAULT '',
            memo TEXT NOT NULL DEFAULT '',
            receipt_path TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS audit_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            entity_id INTEGER,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)
        self.conn.commit()

    def _meta_get(self, key: str):
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def _meta_set(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    @property
    def profile(self) -> str:
        return self._meta_get("profile") or "JP"

    @property
    def currency(self) -> str:
        return profile_info(self.profile)["currency"]

    @property
    def categories(self) -> list[str]:
        return list(profile_info(self.profile)["categories"])

    def set_profile(self, profile: str) -> None:
        profile_info(profile)
        count = self.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        if count:
            raise LedgerError("profile cannot change after transactions exist")
        self._meta_set("profile", profile)

    def add_transaction(self, txn_date: str, kind: str, amount, category: str,
                        counterparty: str = "", memo: str = "", receipt_path: str = "") -> int:
        txn_date = validate_date(txn_date)
        if kind not in {"income", "expense"}:
            raise LedgerError("kind must be income or expense")
        category = category.strip()
        if not category:
            raise LedgerError("category is required")
        amount_minor = amount_to_minor(amount, self.currency)
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO transactions(txn_date,kind,amount_minor,category,counterparty,memo,receipt_path) "
                "VALUES(?,?,?,?,?,?,?)",
                (txn_date, kind, amount_minor, category, counterparty.strip(), memo.strip(), receipt_path.strip()),
            )
            txn_id = int(cur.lastrowid)
            self.conn.execute(
                "INSERT INTO audit_log(action,entity_id,detail) VALUES(?,?,?)",
                ("ADD_TRANSACTION", txn_id, f"{txn_date}|{kind}|{amount_minor}|{category}"),
            )
        return txn_id

    def delete_transaction(self, txn_id: int) -> None:
        row = self.conn.execute(
            "SELECT txn_date,kind,amount_minor,category FROM transactions WHERE id=?", (txn_id,)
        ).fetchone()
        if row is None:
            raise LedgerError("transaction not found")
        with self.conn:
            self.conn.execute("DELETE FROM transactions WHERE id=?", (txn_id,))
            self.conn.execute(
                "INSERT INTO audit_log(action,entity_id,detail) VALUES(?,?,?)",
                ("DELETE_TRANSACTION", txn_id,
                 f"{row['txn_date']}|{row['kind']}|{row['amount_minor']}|{row['category']}"),
            )

    def transactions(self, limit: int = 1000) -> list[Transaction]:
        rows = self.conn.execute(
            "SELECT id,txn_date,kind,amount_minor,category,counterparty,memo,receipt_path "
            "FROM transactions ORDER BY txn_date DESC,id DESC LIMIT ?",
            (max(1, min(int(limit), 10000)),),
        ).fetchall()
        return [Transaction(**dict(row)) for row in rows]

    def monthly_summary(self, year: int, month: int) -> dict[str, int]:
        if month < 1 or month > 12:
            raise LedgerError("month must be 1..12")
        rows = self.conn.execute(
            "SELECT kind,COALESCE(SUM(amount_minor),0) total FROM transactions "
            "WHERE txn_date LIKE ? GROUP BY kind",
            (f"{year:04d}-{month:02d}-%",),
        ).fetchall()
        result = {"income": 0, "expense": 0}
        for row in rows:
            result[row["kind"]] = int(row["total"])
        result["net"] = result["income"] - result["expense"]
        return result

    def category_summary(self, year: int | None = None):
        if year is None:
            rows = self.conn.execute(
                "SELECT kind,category,SUM(amount_minor) total FROM transactions "
                "GROUP BY kind,category ORDER BY kind,category"
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT kind,category,SUM(amount_minor) total FROM transactions "
                "WHERE txn_date LIKE ? GROUP BY kind,category ORDER BY kind,category",
                (f"{year:04d}-%",),
            ).fetchall()
        return [(r["kind"], r["category"], int(r["total"])) for r in rows]

    def export_csv(self, target: str | Path) -> Path:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["date","kind","amount","currency","category","counterparty","memo","receipt_path"])
            for txn in reversed(self.transactions(10000)):
                writer.writerow([
                    txn.txn_date, txn.kind,
                    minor_to_text(txn.amount_minor, self.currency).replace(",", ""),
                    self.currency, txn.category, txn.counterparty, txn.memo, txn.receipt_path,
                ])
        return target

    def backup_to(self, target: str | Path) -> Path:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        destination = sqlite3.connect(target)
        try:
            self.conn.backup(destination)
        finally:
            destination.close()
        return target

    def close(self) -> None:
        self.conn.close()
