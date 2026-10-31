from __future__ import annotations

import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core import LedgerError, LedgerStore, minor_to_text

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Freelance Ledger Local")
        self.geometry("1080x720")
        self.minsize(900, 620)
        self.store = LedgerStore()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.profile_var = tk.StringVar(value=self.store.profile)
        self.date_var = tk.StringVar(value=date.today().isoformat())
        self.kind_var = tk.StringVar(value="income")
        self.amount_var = tk.StringVar()
        self.category_var = tk.StringVar()
        self.counterparty_var = tk.StringVar()
        self.memo_var = tk.StringVar()
        self.receipt_var = tk.StringVar()
        self.summary_var = tk.StringVar()

        self._build()
        self._profile_changed(initial=True)
        self.refresh()

    def _build(self):
        top = ttk.Frame(self, padding=14)
        top.pack(fill="x")
        ttk.Label(top, text="Freelance Ledger Local", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Label(top, text="Country / 国").pack(side="left", padx=(24, 6))
        profile = ttk.Combobox(top, textvariable=self.profile_var, values=["JP", "US"], width=7, state="readonly")
        profile.pack(side="left")
        profile.bind("<<ComboboxSelected>>", lambda _e: self._profile_changed())

        ttk.Label(
            self,
            text="Local-only bookkeeping. Tax treatment is not determined by this app. / ローカル専用。税務判断は行いません。",
        ).pack(fill="x", padx=14)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=14, pady=10)

        entry = ttk.Labelframe(body, text="New transaction / 取引入力", padding=12)
        body.add(entry, weight=1)
        rows = [
            ("Date / 日付", self.date_var),
            ("Amount / 金額", self.amount_var),
            ("Counterparty / 取引先", self.counterparty_var),
            ("Memo / メモ", self.memo_var),
            ("Receipt path / 証憑パス", self.receipt_var),
        ]
        ttk.Label(entry, text="Type / 種別").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Combobox(entry, textvariable=self.kind_var, values=["income", "expense"], state="readonly").grid(
            row=0, column=1, sticky="ew", pady=4
        )
        ttk.Label(entry, text="Category / 科目").grid(row=1, column=0, sticky="w", pady=4)
        self.category_box = ttk.Combobox(entry, textvariable=self.category_var, state="normal")
        self.category_box.grid(row=1, column=1, sticky="ew", pady=4)
        for i, (label, var) in enumerate(rows, start=2):
            ttk.Label(entry, text=label).grid(row=i, column=0, sticky="w", pady=4)
            ttk.Entry(entry, textvariable=var).grid(row=i, column=1, sticky="ew", pady=4)
        ttk.Button(entry, text="Browse receipt / 証憑参照", command=self.browse_receipt).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(8, 4)
        )
        ttk.Button(entry, text="Add transaction / 取引を追加", command=self.add_transaction).grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=4
        )
        ttk.Button(entry, text="Backup books / バックアップ", command=self.backup).grid(
            row=9, column=0, columnspan=2, sticky="ew", pady=4
        )
        ttk.Button(entry, text="Export CSV / CSV出力", command=self.export_csv).grid(
            row=10, column=0, columnspan=2, sticky="ew", pady=4
        )
        entry.columnconfigure(1, weight=1)

        listing = ttk.Labelframe(body, text="Ledger / 帳簿", padding=10)
        body.add(listing, weight=3)
        ttk.Label(listing, textvariable=self.summary_var, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))

        columns = ("date", "kind", "amount", "category", "counterparty", "memo")
        self.tree = ttk.Treeview(listing, columns=columns, show="headings", selectmode="browse")
        headings = {
            "date": "Date / 日付", "kind": "Type / 種別", "amount": "Amount / 金額",
            "category": "Category / 科目", "counterparty": "Counterparty / 取引先", "memo": "Memo / メモ",
        }
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=120 if col != "memo" else 190, anchor="w")
        self.tree.pack(fill="both", expand=True)
        ttk.Button(listing, text="Delete selected / 選択を削除", command=self.delete_selected).pack(
            anchor="e", pady=(8, 0)
        )

    def _profile_changed(self, initial=False):
        desired = self.profile_var.get()
        try:
            if not initial and desired != self.store.profile:
                self.store.set_profile(desired)
            self.profile_var.set(self.store.profile)
            self.category_box["values"] = self.store.categories
            if not self.category_var.get() or self.category_var.get() not in self.store.categories:
                self.category_var.set(self.store.categories[0])
        except LedgerError as exc:
            self.profile_var.set(self.store.profile)
            messagebox.showwarning("Profile", str(exc))

    def browse_receipt(self):
        path = filedialog.askopenfilename(title="Select local receipt/reference file")
        if path:
            self.receipt_var.set(path)

    def add_transaction(self):
        try:
            self.store.add_transaction(
                self.date_var.get(), self.kind_var.get(), self.amount_var.get(), self.category_var.get(),
                self.counterparty_var.get(), self.memo_var.get(), self.receipt_var.get(),
            )
        except LedgerError as exc:
            messagebox.showerror("Input error", str(exc))
            return
        self.amount_var.set("")
        self.counterparty_var.set("")
        self.memo_var.set("")
        self.receipt_var.set("")
        self.refresh()

    def delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            return
        if not messagebox.askyesno("Confirm", "Delete the selected ledger row? / 選択行を削除しますか？"):
            return
        self.store.delete_transaction(int(selected[0]))
        self.refresh()

    def refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for txn in self.store.transactions():
            self.tree.insert("", "end", iid=str(txn.id), values=(
                txn.txn_date, txn.kind, minor_to_text(txn.amount_minor, self.store.currency),
                txn.category, txn.counterparty, txn.memo,
            ))
        today = date.today()
        totals = self.store.monthly_summary(today.year, today.month)
        self.summary_var.set(
            f"{today.year}-{today.month:02d}  Income: {minor_to_text(totals['income'], self.store.currency)}  "
            f"Expense: {minor_to_text(totals['expense'], self.store.currency)}  "
            f"Net: {minor_to_text(totals['net'], self.store.currency)} {self.store.currency}"
        )

    def export_csv(self):
        path = filedialog.asksaveasfilename(
            title="Export CSV", defaultextension=".csv", filetypes=[("CSV", "*.csv")]
        )
        if path:
            self.store.export_csv(path)
            messagebox.showinfo("Export", "CSV exported.")

    def backup(self):
        path = filedialog.asksaveasfilename(
            title="Backup books", defaultextension=".sqlite3", filetypes=[("SQLite", "*.sqlite3")]
        )
        if path:
            self.store.backup_to(path)
            messagebox.showinfo("Backup", "Backup created.")

    def on_close(self):
        self.store.close()
        self.destroy()

if __name__ == "__main__":
    App().mainloop()
