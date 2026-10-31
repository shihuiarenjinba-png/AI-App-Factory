from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, simpledialog, ttk

from core import ACCOUNT_TYPES, BookError, BookStore, minor_to_text

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Double-Entry Bookkeeping Desk")
        self.geometry("1180x760")
        self.minsize(980, 650)
        self.store = BookStore()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.currency_var = tk.StringVar(value=self.store.currency)
        self.date_var = tk.StringVar(value=date.today().isoformat())
        self.desc_var = tk.StringVar()
        self.report_var = tk.StringVar()
        self.line_vars = []

        self._build()
        self.refresh_accounts()
        self.refresh_all()

    def _build(self):
        header = ttk.Frame(self, padding=14)
        header.pack(fill="x")
        ttk.Label(header, text="Double-Entry Bookkeeping Desk", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Label(header, text="Currency / 通貨").pack(side="left", padx=(22, 6))
        currency = ttk.Combobox(header, textvariable=self.currency_var, values=["JPY", "USD"], width=8, state="readonly")
        currency.pack(side="left")
        currency.bind("<<ComboboxSelected>>", lambda _e: self.change_currency())
        ttk.Label(self, text="Local double-entry books. No tax filing, bank sync, payroll or cloud account.").pack(
            fill="x", padx=14
        )

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=14, pady=10)

        form = ttk.Labelframe(body, text="Journal entry / 仕訳入力", padding=10)
        body.add(form, weight=2)
        ttk.Label(form, text="Date / 日付").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.date_var, width=16).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(form, text="Description / 摘要").grid(row=1, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.desc_var).grid(row=1, column=1, columnspan=3, sticky="ew", pady=3)

        ttk.Label(form, text="Account / 勘定科目").grid(row=2, column=0, sticky="w")
        ttk.Label(form, text="Debit / 借方").grid(row=2, column=1, sticky="w")
        ttk.Label(form, text="Credit / 貸方").grid(row=2, column=2, sticky="w")
        for i in range(6):
            account = tk.StringVar()
            debit = tk.StringVar()
            credit = tk.StringVar()
            box = ttk.Combobox(form, textvariable=account, state="readonly", width=34)
            box.grid(row=3+i, column=0, sticky="ew", pady=2)
            ttk.Entry(form, textvariable=debit, width=14).grid(row=3+i, column=1, sticky="ew", pady=2)
            ttk.Entry(form, textvariable=credit, width=14).grid(row=3+i, column=2, sticky="ew", pady=2)
            self.line_vars.append((account, debit, credit, box))

        actions = ttk.Frame(form)
        actions.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="Post / 記帳", command=self.post).pack(side="left")
        ttk.Button(actions, text="Add account / 科目追加", command=self.add_account).pack(side="left", padx=5)
        ttk.Button(actions, text="Lock through / 締め", command=self.lock_period).pack(side="left", padx=5)
        ttk.Button(actions, text="Export CSV", command=self.export_csv).pack(side="left", padx=5)
        ttk.Button(actions, text="Backup", command=self.backup).pack(side="left", padx=5)
        form.columnconfigure(0, weight=2)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(2, weight=1)

        notebook = ttk.Notebook(body)
        body.add(notebook, weight=3)
        journal_tab = ttk.Frame(notebook, padding=8)
        reports_tab = ttk.Frame(notebook, padding=8)
        notebook.add(journal_tab, text="Journal / 仕訳帳")
        notebook.add(reports_tab, text="Reports / 帳票")

        cols = ("date","desc","account","debit","credit")
        self.tree = ttk.Treeview(journal_tab, columns=cols, show="headings")
        for col, title in [
            ("date","Date / 日付"),("desc","Description / 摘要"),("account","Account / 科目"),
            ("debit","Debit / 借方"),("credit","Credit / 貸方")
        ]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=120 if col != "desc" else 220)
        self.tree.pack(fill="both", expand=True)

        self.report = tk.Text(reports_tab, wrap="none", font=("Consolas", 10), state="disabled")
        self.report.pack(fill="both", expand=True)
        ttk.Button(reports_tab, text="Refresh reports / 帳票更新", command=self.refresh_reports).pack(anchor="e", pady=6)

    def refresh_accounts(self):
        accounts = self.store.accounts()
        labels = [f"{a['code']}  {a['name_ja']} / {a['name_en']}" for a in accounts]
        for _account, _debit, _credit, box in self.line_vars:
            box["values"] = labels

    def account_code(self, label):
        return label.split()[0] if label.strip() else ""

    def change_currency(self):
        try:
            self.store.set_currency(self.currency_var.get())
        except BookError as exc:
            self.currency_var.set(self.store.currency)
            messagebox.showwarning("Currency", str(exc))
        self.refresh_all()

    def post(self):
        lines = [(self.account_code(a.get()), d.get(), c.get()) for a,d,c,_box in self.line_vars]
        try:
            self.store.post_entry(self.date_var.get(), self.desc_var.get(), lines)
        except BookError as exc:
            messagebox.showerror("Journal entry", str(exc))
            return
        self.desc_var.set("")
        for a,d,c,_box in self.line_vars:
            a.set(""); d.set(""); c.set("")
        self.refresh_all()

    def add_account(self):
        code = simpledialog.askstring("Account", "Code / 科目コード")
        if not code:
            return
        ja = simpledialog.askstring("Account", "Japanese name / 日本語名")
        if not ja:
            return
        en = simpledialog.askstring("Account", "English name")
        if not en:
            return
        typ = simpledialog.askstring("Account", "Type: asset, liability, equity, revenue, expense")
        if not typ:
            return
        try:
            self.store.add_account(code, ja, en, typ.strip().lower())
        except BookError as exc:
            messagebox.showerror("Account", str(exc))
            return
        self.refresh_accounts()

    def lock_period(self):
        value = simpledialog.askstring("Period lock", "Lock entries through YYYY-MM-DD / この日まで締める")
        if not value:
            return
        try:
            self.store.set_lock(value)
        except BookError as exc:
            messagebox.showerror("Period lock", str(exc))
            return
        messagebox.showinfo("Period lock", f"Locked through {self.store.locked_through}")

    def refresh_all(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i,row in enumerate(self.store.journal()):
            self.tree.insert("", "end", iid=str(i), values=(
                row["entry_date"], row["description"],
                f"{row['code']} {row['name_ja']}",
                minor_to_text(int(row["debit_minor"]), self.store.currency) if row["debit_minor"] else "",
                minor_to_text(int(row["credit_minor"]), self.store.currency) if row["credit_minor"] else "",
            ))
        self.refresh_reports()

    def refresh_reports(self):
        tb = self.store.trial_balance()
        pnl = self.store.income_statement()
        bs = self.store.balance_sheet()
        lines = ["TRIAL BALANCE / 試算表", "=" * 72]
        lines.append(f"{'Code':<8}{'Account':<30}{'Debit':>15}{'Credit':>15}")
        for row in tb:
            if row["debit"] or row["credit"]:
                lines.append(
                    f"{row['code']:<8}{row['name_en'][:29]:<30}"
                    f"{minor_to_text(int(row['debit']),self.store.currency):>15}"
                    f"{minor_to_text(int(row['credit']),self.store.currency):>15}"
                )
        lines += [
            "", "PROFIT & LOSS / 損益",
            f"Revenue: {minor_to_text(pnl['revenue'], self.store.currency)}",
            f"Expense: {minor_to_text(pnl['expense'], self.store.currency)}",
            f"Net income: {minor_to_text(pnl['net_income'], self.store.currency)}",
            "", "BALANCE SHEET / 貸借対照",
            f"Assets: {minor_to_text(bs['assets'], self.store.currency)}",
            f"Liabilities: {minor_to_text(bs['liabilities'], self.store.currency)}",
            f"Equity before current income: {minor_to_text(bs['equity_before_current_income'], self.store.currency)}",
            f"Current net income: {minor_to_text(bs['current_net_income'], self.store.currency)}",
            f"Liabilities + equity: {minor_to_text(bs['liabilities_and_equity'], self.store.currency)}",
            "", f"Locked through: {self.store.locked_through or '-'}",
        ]
        self.report.configure(state="normal")
        self.report.delete("1.0", "end")
        self.report.insert("1.0", "\n".join(lines))
        self.report.configure(state="disabled")

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")])
        if path:
            self.store.export_journal_csv(path)
            messagebox.showinfo("Export", "Journal CSV exported.")

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".sqlite3", filetypes=[("SQLite","*.sqlite3")])
        if path:
            self.store.backup_to(path)
            messagebox.showinfo("Backup", "Backup created.")

    def on_close(self):
        self.store.close()
        self.destroy()

if __name__ == "__main__":
    App().mainloop()
