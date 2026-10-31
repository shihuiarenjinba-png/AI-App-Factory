from __future__ import annotations
import csv
import json
from dataclasses import dataclass, asdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

APP_NAME = "Local Double-Entry Bookkeeper"
ACCOUNT_TYPES = ("asset", "liability", "equity", "income", "expense")
DEFAULT_ACCOUNTS = [
    ("1000", "Cash", "asset"),
    ("1010", "Bank", "asset"),
    ("1100", "Accounts Receivable", "asset"),
    ("1500", "Equipment", "asset"),
    ("2000", "Accounts Payable", "liability"),
    ("2100", "Loan Payable", "liability"),
    ("3000", "Owner's Equity", "equity"),
    ("4000", "Sales", "income"),
    ("4100", "Service Revenue", "income"),
    ("5000", "Rent Expense", "expense"),
    ("5100", "Supplies Expense", "expense"),
    ("5200", "Utilities Expense", "expense"),
    ("5900", "Miscellaneous Expense", "expense"),
]

def app_data_dir() -> Path:
    import os
    root = os.environ.get("APPDATA")
    path = Path(root) / "LocalDoubleEntryBookkeeper" if root else Path.home() / ".local-double-entry-bookkeeper"
    path.mkdir(parents=True, exist_ok=True)
    return path

def validate_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Date must be YYYY-MM-DD.")
    return value

def parse_money(text: str) -> int:
    try:
        value = Decimal(str(text).replace(",", "").strip()).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError("Enter a valid amount.")
    if value <= 0:
        raise ValueError("Amount must be greater than zero.")
    return int(value * 100)

def money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) / 100:,.2f}"

@dataclass
class Account:
    code: str
    name: str
    type: str

@dataclass
class Line:
    account_code: str
    debit: int = 0
    credit: int = 0

@dataclass
class Entry:
    id: int
    date: str
    memo: str
    reference: str
    lines: list

class Book:
    def __init__(self, accounts=None, entries=None):
        self.accounts = accounts or [Account(*row) for row in DEFAULT_ACCOUNTS]
        self.entries = entries or []

    def account_map(self):
        return {a.code: a for a in self.accounts}

    def add_account(self, code: str, name: str, account_type: str):
        code = code.strip()
        name = name.strip()
        if not code or not name:
            raise ValueError("Account code and name are required.")
        if account_type not in ACCOUNT_TYPES:
            raise ValueError("Unknown account type.")
        if code in self.account_map():
            raise ValueError("Account code already exists.")
        self.accounts.append(Account(code[:20], name[:100], account_type))
        self.accounts.sort(key=lambda a: a.code)

    def next_id(self):
        return max((e.id for e in self.entries), default=0) + 1

    def add_simple_entry(self, date_text, memo, reference, debit_code, credit_code, amount_text):
        validate_date(date_text)
        amap = self.account_map()
        if debit_code not in amap or credit_code not in amap:
            raise ValueError("Choose valid accounts.")
        if debit_code == credit_code:
            raise ValueError("Debit and credit accounts must differ.")
        amount = parse_money(amount_text)
        entry = Entry(
            self.next_id(), date_text, memo.strip()[:300], reference.strip()[:100],
            [Line(debit_code, debit=amount), Line(credit_code, credit=amount)]
        )
        self.entries.append(entry)
        return entry

    def add_entry(self, date_text, memo, reference, lines):
        validate_date(date_text)
        amap = self.account_map()
        parsed = []
        for line in lines:
            if line.account_code not in amap:
                raise ValueError("Unknown account.")
            if line.debit < 0 or line.credit < 0 or (line.debit and line.credit):
                raise ValueError("Each line must contain a non-negative debit or credit, not both.")
            if not line.debit and not line.credit:
                raise ValueError("Zero-value line.")
            parsed.append(line)
        if len(parsed) < 2:
            raise ValueError("At least two lines are required.")
        if sum(x.debit for x in parsed) != sum(x.credit for x in parsed):
            raise ValueError("Entry is not balanced.")
        entry = Entry(self.next_id(), date_text, memo.strip()[:300], reference.strip()[:100], parsed)
        self.entries.append(entry)
        return entry

    def delete_entry(self, entry_id: int):
        old = len(self.entries)
        self.entries = [e for e in self.entries if e.id != entry_id]
        return len(self.entries) != old

    def trial_balance(self):
        totals = {a.code: {"debit": 0, "credit": 0} for a in self.accounts}
        for entry in self.entries:
            for line in entry.lines:
                totals[line.account_code]["debit"] += line.debit
                totals[line.account_code]["credit"] += line.credit
        return totals

    def account_balance(self, code: str):
        account = self.account_map()[code]
        totals = self.trial_balance()[code]
        if account.type in ("asset", "expense"):
            return totals["debit"] - totals["credit"]
        return totals["credit"] - totals["debit"]

    def profit_loss(self):
        income = sum(self.account_balance(a.code) for a in self.accounts if a.type == "income")
        expenses = sum(self.account_balance(a.code) for a in self.accounts if a.type == "expense")
        return {"income": income, "expenses": expenses, "profit": income - expenses}

    def balance_sheet(self):
        assets = sum(self.account_balance(a.code) for a in self.accounts if a.type == "asset")
        liabilities = sum(self.account_balance(a.code) for a in self.accounts if a.type == "liability")
        equity = sum(self.account_balance(a.code) for a in self.accounts if a.type == "equity")
        earnings = self.profit_loss()["profit"]
        return {
            "assets": assets,
            "liabilities": liabilities,
            "equity": equity,
            "current_earnings": earnings,
            "difference": assets - (liabilities + equity + earnings),
        }

    def to_dict(self):
        return {
            "schema": 1,
            "accounts": [asdict(a) for a in self.accounts],
            "entries": [
                {
                    "id": e.id,
                    "date": e.date,
                    "memo": e.memo,
                    "reference": e.reference,
                    "lines": [asdict(line) for line in e.lines],
                }
                for e in self.entries
            ],
        }

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get("schema") != 1:
            raise ValueError("Unsupported or invalid book file.")
        accounts = [Account(**raw) for raw in data.get("accounts", [])]
        if not accounts:
            raise ValueError("Book must contain accounts.")
        book = cls(accounts, [])
        seen = set()
        for raw in data.get("entries", []):
            entry_id = int(raw["id"])
            if entry_id in seen:
                raise ValueError("Duplicate entry id.")
            seen.add(entry_id)
            lines = [Line(**line) for line in raw.get("lines", [])]
            entry = book.add_entry(
                raw["date"], raw.get("memo", ""), raw.get("reference", ""), lines
            )
            entry.id = entry_id
        return book

def save_atomic(path: Path, book: Book):
    if path.is_symlink():
        raise ValueError("Refusing to write through a symbolic link.")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    bak = path.with_suffix(path.suffix + ".bak")
    tmp.write_text(json.dumps(book.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Book.from_dict(json.loads(tmp.read_text(encoding="utf-8")))
    if path.exists():
        bak_tmp = bak.with_suffix(bak.suffix + ".tmp")
        bak_tmp.write_bytes(path.read_bytes())
        bak_tmp.replace(bak)
    tmp.replace(path)

def load_book(path: Path) -> Book:
    try:
        return Book.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        bak = path.with_suffix(path.suffix + ".bak")
        if bak.exists():
            return Book.from_dict(json.loads(bak.read_text(encoding="utf-8")))
        raise

def export_journal_csv(path: Path, book: Book):
    amap = book.account_map()
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "entry_id", "date", "memo", "reference", "account_code",
            "account_name", "debit", "credit"
        ])
        for entry in sorted(book.entries, key=lambda e: (e.date, e.id)):
            for line in entry.lines:
                writer.writerow([
                    entry.id, entry.date, entry.memo, entry.reference,
                    line.account_code, amap[line.account_code].name,
                    money(line.debit) if line.debit else "",
                    money(line.credit) if line.credit else "",
                ])

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1100x760")
        self.minsize(980, 680)
        self.path = app_data_dir() / "book.json"
        try:
            self.book = load_book(self.path) if self.path.exists() else Book()
        except Exception as exc:
            messagebox.showwarning(APP_NAME, f"Could not load book. Starting new.\n{exc}")
            self.book = Book()

        self.date_var = tk.StringVar(value=date.today().isoformat())
        self.memo = tk.StringVar()
        self.reference = tk.StringVar()
        self.amount = tk.StringVar()
        self.debit = tk.StringVar()
        self.credit = tk.StringVar()
        self.status = tk.StringVar(value="Local only / ローカル保存")
        self._build()
        self.refresh_all()

    def _build(self):
        header = ttk.Frame(self, padding=10)
        header.pack(fill="x")
        ttk.Label(header, text=APP_NAME, font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Button(header, text="Export journal CSV / 仕訳CSV", command=self.export).pack(side="right")
        ttk.Label(
            self,
            text="Double-entry bookkeeping only; tax filing and tax advice are outside this app. / 複式簿記用。税務申告・税務判断は対象外です。",
            foreground="#555", padding=(10, 0, 10, 8)
        ).pack(fill="x")

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.journal_tab = ttk.Frame(self.tabs, padding=10)
        self.accounts_tab = ttk.Frame(self.tabs, padding=10)
        self.reports_tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(self.journal_tab, text="Journal / 仕訳")
        self.tabs.add(self.accounts_tab, text="Accounts / 勘定科目")
        self.tabs.add(self.reports_tab, text="Reports / 帳票")
        self._build_journal()
        self._build_accounts()
        self._build_reports()
        ttk.Label(self, textvariable=self.status, padding=(10, 0, 10, 8)).pack(fill="x")

    def _build_journal(self):
        form = ttk.LabelFrame(self.journal_tab, text="Simple balanced entry / 1対1仕訳", padding=10)
        form.pack(fill="x")
        row1 = ttk.Frame(form); row1.pack(fill="x", pady=3)
        self._field(row1, "Date / 日付", self.date_var, 12)
        self._field(row1, "Memo / 摘要", self.memo, 30)
        self._field(row1, "Ref / 証憑", self.reference, 16)

        row2 = ttk.Frame(form); row2.pack(fill="x", pady=3)
        ttk.Label(row2, text="Debit / 借方").pack(side="left")
        self.debit_box = ttk.Combobox(row2, textvariable=self.debit, state="readonly", width=30)
        self.debit_box.pack(side="left", padx=(4, 10))
        ttk.Label(row2, text="Credit / 貸方").pack(side="left")
        self.credit_box = ttk.Combobox(row2, textvariable=self.credit, state="readonly", width=30)
        self.credit_box.pack(side="left", padx=(4, 10))
        self._field(row2, "Amount / 金額", self.amount, 14)
        ttk.Button(row2, text="Post / 記帳", command=self.post).pack(side="left", padx=8)

        columns = ("date", "memo", "debit", "credit", "amount", "ref")
        self.tree = ttk.Treeview(self.journal_tab, columns=columns, show="headings", selectmode="browse")
        for name, title, width in [
            ("date", "Date", 90), ("memo", "Memo", 260), ("debit", "Debit", 180),
            ("credit", "Credit", 180), ("amount", "Amount", 110), ("ref", "Ref", 120)
        ]:
            self.tree.heading(name, text=title)
            self.tree.column(name, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=10)
        ttk.Button(self.journal_tab, text="Delete selected / 選択削除", command=self.delete).pack(anchor="e")

    def _build_accounts(self):
        columns = ("code", "name", "type", "balance")
        self.accounts_tree = ttk.Treeview(self.accounts_tab, columns=columns, show="headings")
        for name, title, width in [
            ("code", "Code", 90), ("name", "Account / 科目", 300),
            ("type", "Type", 120), ("balance", "Balance", 130)
        ]:
            self.accounts_tree.heading(name, text=title)
            self.accounts_tree.column(name, width=width, anchor="w")
        self.accounts_tree.pack(fill="both", expand=True)
        ttk.Button(self.accounts_tab, text="Add account / 科目追加", command=self.add_account_dialog).pack(anchor="e", pady=8)

    def _build_reports(self):
        self.report_text = tk.Text(self.reports_tab, wrap="none", height=28)
        self.report_text.pack(fill="both", expand=True)
        buttons = ttk.Frame(self.reports_tab); buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="Trial Balance / 試算表", command=lambda: self.show_report("trial")).pack(side="left")
        ttk.Button(buttons, text="Profit & Loss / 損益", command=lambda: self.show_report("pl")).pack(side="left", padx=6)
        ttk.Button(buttons, text="Balance Sheet / 貸借", command=lambda: self.show_report("bs")).pack(side="left")

    def _field(self, parent, label, variable, width):
        ttk.Label(parent, text=label).pack(side="left", padx=(0, 4))
        ttk.Entry(parent, textvariable=variable, width=width).pack(side="left", padx=(0, 10))

    def account_values(self):
        return [f"{a.code} — {a.name}" for a in self.book.accounts]

    def code_from_value(self, value):
        return value.split(" — ", 1)[0] if " — " in value else value

    def refresh_all(self):
        values = self.account_values()
        self.debit_box["values"] = values
        self.credit_box["values"] = values
        if not self.debit.get() and values:
            self.debit.set(values[0])
        if not self.credit.get() and len(values) > 1:
            self.credit.set(values[1])

        for item in self.tree.get_children():
            self.tree.delete(item)
        amap = self.book.account_map()
        for entry in sorted(self.book.entries, key=lambda e: (e.date, e.id), reverse=True):
            if len(entry.lines) == 2:
                debit = next((line for line in entry.lines if line.debit), None)
                credit = next((line for line in entry.lines if line.credit), None)
                amount = debit.debit if debit else 0
                self.tree.insert("", "end", iid=str(entry.id), values=(
                    entry.date, entry.memo,
                    amap[debit.account_code].name if debit else "Split",
                    amap[credit.account_code].name if credit else "Split",
                    money(amount), entry.reference
                ))

        for item in self.accounts_tree.get_children():
            self.accounts_tree.delete(item)
        for account in self.book.accounts:
            self.accounts_tree.insert("", "end", values=(
                account.code, account.name, account.type, money(self.book.account_balance(account.code))
            ))
        self.show_report("trial")

    def post(self):
        try:
            self.book.add_simple_entry(
                self.date_var.get(), self.memo.get(), self.reference.get(),
                self.code_from_value(self.debit.get()), self.code_from_value(self.credit.get()),
                self.amount.get()
            )
            save_atomic(self.path, self.book)
            self.memo.set(""); self.reference.set(""); self.amount.set("")
            self.status.set("Saved locally / 保存済み")
            self.refresh_all()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def delete(self):
        selected = self.tree.selection()
        if not selected:
            return
        if messagebox.askyesno(APP_NAME, "Delete selected journal entry? / 選択仕訳を削除しますか？"):
            self.book.delete_entry(int(selected[0]))
            save_atomic(self.path, self.book)
            self.refresh_all()

    def add_account_dialog(self):
        code = simpledialog.askstring(APP_NAME, "Account code / 科目コード:", parent=self)
        if code is None:
            return
        name = simpledialog.askstring(APP_NAME, "Account name / 科目名:", parent=self)
        if name is None:
            return
        account_type = simpledialog.askstring(
            APP_NAME, "Type: asset, liability, equity, income, expense", parent=self
        )
        if account_type is None:
            return
        try:
            self.book.add_account(code, name, account_type.strip().lower())
            save_atomic(self.path, self.book)
            self.refresh_all()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def show_report(self, kind):
        self.report_text.delete("1.0", "end")
        if kind == "trial":
            tb = self.book.trial_balance()
            self.report_text.insert("end", "TRIAL BALANCE / 試算表\n\n")
            self.report_text.insert("end", f'{"Code":<8} {"Account":<28} {"Debit":>14} {"Credit":>14}\n')
            for account in self.book.accounts:
                totals = tb[account.code]
                if totals["debit"] or totals["credit"]:
                    self.report_text.insert(
                        "end",
                        f'{account.code:<8} {account.name[:28]:<28} '
                        f'{money(totals["debit"]):>14} {money(totals["credit"]):>14}\n'
                    )
            debit_total = sum(v["debit"] for v in tb.values())
            credit_total = sum(v["credit"] for v in tb.values())
            self.report_text.insert("end", f"\nTotal debit: {money(debit_total)}   Total credit: {money(credit_total)}\n")
        elif kind == "pl":
            result = self.book.profit_loss()
            self.report_text.insert(
                "end",
                "PROFIT & LOSS / 損益\n\n"
                f'Income / 収益: {money(result["income"])}\n'
                f'Expenses / 費用: {money(result["expenses"])}\n'
                f'Profit / 利益: {money(result["profit"])}\n'
            )
        else:
            result = self.book.balance_sheet()
            self.report_text.insert(
                "end",
                "BALANCE SHEET / 貸借対照サマリ\n\n"
                f'Assets / 資産: {money(result["assets"])}\n'
                f'Liabilities / 負債: {money(result["liabilities"])}\n'
                f'Equity / 純資産: {money(result["equity"])}\n'
                f'Current earnings / 当期損益: {money(result["current_earnings"])}\n'
                f'Check difference / 差額: {money(result["difference"])}\n'
            )

    def export(self):
        target = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not target:
            return
        try:
            export_journal_csv(Path(target), self.book)
            self.status.set("Journal CSV exported / 仕訳CSV出力済み")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

if __name__ == "__main__":
    App().mainloop()
