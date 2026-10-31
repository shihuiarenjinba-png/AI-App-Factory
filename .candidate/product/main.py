from __future__ import annotations
import csv
import json
from dataclasses import dataclass, asdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "Freelance Ledger JP/US"

REGIONS = {
    "JP": {
        "currency": "JPY",
        "symbol": "¥",
        "decimals": 0,
        "income": ["Sales / 売上", "Service income / 業務収入", "Other income / その他収入"],
        "expense": [
            "Outsourcing / 外注工賃", "Advertising / 広告宣伝費", "Supplies / 消耗品費",
            "Travel / 旅費交通費", "Communications / 通信費", "Rent / 地代家賃",
            "Utilities / 水道光熱費", "Taxes & dues / 租税公課", "Insurance / 損害保険料",
            "Repairs / 修繕費", "Depreciation / 減価償却費",
            "Professional fees / 支払手数料", "Other expense / 雑費"
        ],
    },
    "US": {
        "currency": "USD",
        "symbol": "$",
        "decimals": 2,
        "income": ["Gross receipts / Sales", "Services", "Other business income"],
        "expense": [
            "Advertising", "Car & truck", "Commissions & fees", "Contract labor",
            "Depreciation", "Insurance", "Interest", "Legal & professional services",
            "Office expense", "Rent or lease", "Repairs & maintenance", "Supplies",
            "Taxes & licenses", "Travel", "Meals", "Utilities", "Wages", "Other expense"
        ],
    },
}

def app_data_dir() -> Path:
    import os
    root = os.environ.get("APPDATA")
    path = Path(root) / "FreelanceLedgerJPUS" if root else Path.home() / ".freelance-ledger-jp-us"
    path.mkdir(parents=True, exist_ok=True)
    return path

def validate_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Date must be YYYY-MM-DD.")
    return value

def parse_amount(text: str, region: str) -> int:
    cfg = REGIONS[region]
    try:
        value = Decimal(str(text).replace(",", "").strip())
    except InvalidOperation:
        raise ValueError("Enter a valid amount.")
    if value <= 0:
        raise ValueError("Amount must be greater than zero.")
    quant = Decimal("1") if cfg["decimals"] == 0 else Decimal("0.01")
    value = value.quantize(quant, rounding=ROUND_HALF_UP)
    return int(value * (100 if cfg["decimals"] == 2 else 1))

def format_minor(amount: int, region: str) -> str:
    cfg = REGIONS[region]
    if cfg["decimals"] == 2:
        return f'{cfg["symbol"]}{amount / 100:,.2f}'
    return f'{cfg["symbol"]}{amount:,}'

@dataclass
class Transaction:
    id: int
    date: str
    region: str
    kind: str
    category: str
    amount_minor: int
    business_use_pct: int
    counterparty: str
    payment_account: str
    description: str
    evidence_ref: str

    @property
    def adjusted_minor(self) -> int:
        if self.kind != "expense":
            return self.amount_minor
        return (self.amount_minor * self.business_use_pct + 50) // 100

class Ledger:
    def __init__(self, transactions=None):
        self.transactions = transactions or []

    def next_id(self) -> int:
        return max((t.id for t in self.transactions), default=0) + 1

    def add(self, *, date_text, region, kind, category, amount_text,
            business_use_pct=100, counterparty="", payment_account="",
            description="", evidence_ref=""):
        validate_date(date_text)
        if region not in REGIONS:
            raise ValueError("Unknown region.")
        if kind not in ("income", "expense"):
            raise ValueError("Type must be income or expense.")
        if category not in REGIONS[region][kind]:
            raise ValueError("Choose a category for the selected region and type.")
        try:
            pct = int(business_use_pct)
        except (TypeError, ValueError):
            raise ValueError("Business-use percentage must be 0-100.")
        if not 0 <= pct <= 100:
            raise ValueError("Business-use percentage must be 0-100.")
        tx = Transaction(
            self.next_id(), date_text, region, kind, category,
            parse_amount(amount_text, region), pct,
            counterparty.strip()[:160], payment_account.strip()[:120],
            description.strip()[:500], evidence_ref.strip()[:500]
        )
        self.transactions.append(tx)
        return tx

    def delete(self, tx_id: int) -> bool:
        old = len(self.transactions)
        self.transactions = [t for t in self.transactions if t.id != tx_id]
        return len(self.transactions) != old

    def summary(self, region: str):
        rows = [t for t in self.transactions if t.region == region]
        income = sum(t.amount_minor for t in rows if t.kind == "income")
        expenses = sum(t.adjusted_minor for t in rows if t.kind == "expense")
        by_category = {}
        for t in rows:
            key = (t.kind, t.category)
            value = t.amount_minor if t.kind == "income" else t.adjusted_minor
            by_category[key] = by_category.get(key, 0) + value
        return {"income": income, "expenses": expenses, "net": income - expenses, "by_category": by_category}

    def to_dict(self):
        return {"schema": 1, "transactions": [asdict(t) for t in self.transactions]}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get("schema") != 1:
            raise ValueError("Unsupported or invalid ledger file.")
        result = []
        for raw in data.get("transactions", []):
            tx = Transaction(**raw)
            validate_date(tx.date)
            if tx.region not in REGIONS or tx.kind not in ("income", "expense"):
                raise ValueError("Invalid transaction region/type.")
            if tx.category not in REGIONS[tx.region][tx.kind]:
                raise ValueError("Invalid transaction category.")
            if tx.amount_minor <= 0 or not 0 <= tx.business_use_pct <= 100:
                raise ValueError("Invalid transaction values.")
            result.append(tx)
        return cls(result)

def save_atomic(path: Path, ledger: Ledger):
    if path.is_symlink():
        raise ValueError("Refusing to write through a symbolic link.")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    bak = path.with_suffix(path.suffix + ".bak")
    tmp.write_text(json.dumps(ledger.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Ledger.from_dict(json.loads(tmp.read_text(encoding="utf-8")))
    if path.exists():
        bak_tmp = bak.with_suffix(bak.suffix + ".tmp")
        bak_tmp.write_bytes(path.read_bytes())
        bak_tmp.replace(bak)
    tmp.replace(path)

def load_ledger(path: Path) -> Ledger:
    try:
        return Ledger.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        bak = path.with_suffix(path.suffix + ".bak")
        if bak.exists():
            return Ledger.from_dict(json.loads(bak.read_text(encoding="utf-8")))
        raise

def export_csv(path: Path, ledger: Ledger, region: str):
    rows = [t for t in ledger.transactions if t.region == region]
    scale = Decimal(100 if REGIONS[region]["decimals"] == 2 else 1)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "date", "region", "type", "category", "amount", "business_use_pct",
            "adjusted_amount", "counterparty", "payment_account", "description", "evidence_ref"
        ])
        for t in rows:
            writer.writerow([
                t.date, t.region, t.kind, t.category,
                str(Decimal(t.amount_minor) / scale), t.business_use_pct,
                str(Decimal(t.adjusted_minor) / scale), t.counterparty,
                t.payment_account, t.description, t.evidence_ref
            ])

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1100x760")
        self.minsize(980, 680)
        self.path = app_data_dir() / "ledger.json"
        try:
            self.ledger = load_ledger(self.path) if self.path.exists() else Ledger()
        except Exception as exc:
            messagebox.showwarning(APP_NAME, f"Could not load ledger. Starting empty.\n{exc}")
            self.ledger = Ledger()

        self.region = tk.StringVar(value="JP")
        self.kind = tk.StringVar(value="expense")
        self.date_var = tk.StringVar(value=date.today().isoformat())
        self.category = tk.StringVar()
        self.amount = tk.StringVar()
        self.business_pct = tk.StringVar(value="100")
        self.counterparty = tk.StringVar()
        self.account = tk.StringVar(value="Bank / 銀行")
        self.description = tk.StringVar()
        self.evidence = tk.StringVar()
        self.status = tk.StringVar(value="Local only / ローカル保存")
        self._build()
        self._sync_categories()
        self.refresh()

    def _build(self):
        header = ttk.Frame(self, padding=10)
        header.pack(fill="x")
        ttk.Label(header, text=APP_NAME, font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Label(header, text="Region / 地域").pack(side="left", padx=(25, 5))
        region_box = ttk.Combobox(header, textvariable=self.region, values=["JP", "US"], state="readonly", width=6)
        region_box.pack(side="left")
        region_box.bind("<<ComboboxSelected>>", lambda _e: self._sync_categories())
        ttk.Button(header, text="Export CSV / CSV出力", command=self.export).pack(side="right")

        ttk.Label(
            self,
            text="Bookkeeping organizer only. No tax filing or automatic deductibility decisions. / 記帳整理用。税務申告・経費可否を自動確定しません。",
            foreground="#555", padding=(10, 0, 10, 8)
        ).pack(fill="x")

        form = ttk.LabelFrame(self, text="Add transaction / 取引入力", padding=10)
        form.pack(fill="x", padx=10)
        r1 = ttk.Frame(form); r1.pack(fill="x", pady=3)
        self._field(r1, "Date / 日付", self.date_var, 12)
        ttk.Label(r1, text="Type / 種別").pack(side="left", padx=(10, 4))
        kind_box = ttk.Combobox(r1, textvariable=self.kind, values=["income", "expense"], state="readonly", width=10)
        kind_box.pack(side="left")
        kind_box.bind("<<ComboboxSelected>>", lambda _e: self._sync_categories())
        ttk.Label(r1, text="Category / 科目候補").pack(side="left", padx=(10, 4))
        self.category_box = ttk.Combobox(r1, textvariable=self.category, state="readonly", width=28)
        self.category_box.pack(side="left", fill="x", expand=True)
        self._field(r1, "Amount / 金額", self.amount, 14)

        r2 = ttk.Frame(form); r2.pack(fill="x", pady=3)
        self._field(r2, "Business % / 事業割合", self.business_pct, 8)
        self._field(r2, "Client/Vendor / 相手先", self.counterparty, 22)
        self._field(r2, "Account / 口座", self.account, 18)
        self._field(r2, "Evidence / 証憑メモ", self.evidence, 24)

        r3 = ttk.Frame(form); r3.pack(fill="x", pady=3)
        ttk.Label(r3, text="Description / 摘要").pack(side="left", padx=(0, 4))
        ttk.Entry(r3, textvariable=self.description).pack(side="left", fill="x", expand=True)
        ttk.Button(r3, text="Add / 追加", command=self.add_transaction).pack(side="left", padx=(8, 0))

        body = ttk.Frame(self, padding=10); body.pack(fill="both", expand=True)
        columns = ("date", "kind", "category", "amount", "business", "counterparty", "description")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="browse")
        settings = [
            ("date", "Date", 90), ("kind", "Type", 70), ("category", "Category", 190),
            ("amount", "Amount", 110), ("business", "Business %", 80),
            ("counterparty", "Client/Vendor", 150), ("description", "Description", 260)
        ]
        for name, title, width in settings:
            self.tree.heading(name, text=title)
            self.tree.column(name, width=width, anchor="w")
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        footer = ttk.Frame(self, padding=(10, 0, 10, 10)); footer.pack(fill="x")
        self.summary_label = ttk.Label(footer, font=("Segoe UI", 11, "bold"))
        self.summary_label.pack(side="left")
        ttk.Button(footer, text="Delete selected / 選択削除", command=self.delete_selected).pack(side="right")
        ttk.Label(footer, textvariable=self.status).pack(side="right", padx=16)

    def _field(self, parent, label, variable, width):
        ttk.Label(parent, text=label).pack(side="left", padx=(0, 4))
        ttk.Entry(parent, textvariable=variable, width=width).pack(side="left")

    def _sync_categories(self):
        values = REGIONS[self.region.get()][self.kind.get()]
        self.category_box["values"] = values
        if self.category.get() not in values:
            self.category.set(values[0])
        self.refresh()

    def add_transaction(self):
        try:
            self.ledger.add(
                date_text=self.date_var.get(), region=self.region.get(), kind=self.kind.get(),
                category=self.category.get(), amount_text=self.amount.get(),
                business_use_pct=self.business_pct.get(), counterparty=self.counterparty.get(),
                payment_account=self.account.get(), description=self.description.get(),
                evidence_ref=self.evidence.get()
            )
            save_atomic(self.path, self.ledger)
            self.amount.set(""); self.description.set(""); self.evidence.set("")
            self.status.set("Saved locally / 保存済み")
            self.refresh()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def refresh(self):
        if not hasattr(self, "tree"):
            return
        region = self.region.get()
        for item in self.tree.get_children():
            self.tree.delete(item)
        rows = [t for t in self.ledger.transactions if t.region == region]
        for t in sorted(rows, key=lambda x: (x.date, x.id), reverse=True):
            self.tree.insert("", "end", iid=str(t.id), values=(
                t.date, t.kind, t.category, format_minor(t.amount_minor, region),
                t.business_use_pct, t.counterparty, t.description
            ))
        s = self.ledger.summary(region)
        self.summary_label.configure(text=(
            f'Income / 収入: {format_minor(s["income"], region)}   '
            f'Expenses / 経費: {format_minor(s["expenses"], region)}   '
            f'Net / 差引: {format_minor(s["net"], region)}'
        ))

    def delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            return
        if messagebox.askyesno(APP_NAME, "Delete selected record? / 選択した記録を削除しますか？"):
            self.ledger.delete(int(selected[0]))
            save_atomic(self.path, self.ledger)
            self.refresh()

    def export(self):
        target = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not target:
            return
        try:
            export_csv(Path(target), self.ledger, self.region.get())
            self.status.set("CSV exported / CSV出力済み")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

if __name__ == "__main__":
    App().mainloop()
