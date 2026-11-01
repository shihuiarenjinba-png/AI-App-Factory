"""Beginner-friendly monthly expense budget window, JP/JPY only."""
from __future__ import annotations
import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk
from budget import BudgetError, MonthlyBudget

def open_budget_window(parent, store):
    budget = MonthlyBudget(store)
    win = tk.Toplevel(parent)
    win.title("月の予算と実績")
    win.geometry("820x520")
    win.minsize(700, 420)
    win.transient(parent)
    period = tk.StringVar(value=date.today().strftime("%Y-%m"))
    account = tk.StringVar()
    amount = tk.StringVar()
    status = tk.StringVar(value="予算を決めなくても、記帳済みの経費を確認できます。")
    outer = ttk.Frame(win, padding=12)
    outer.pack(fill="both", expand=True)
    ttk.Label(outer, text="月の予算と実績", font=("Yu Gothic UI", 15, "bold")).pack(anchor="w")
    ttk.Label(outer, text="経費の使いすぎを確認します。税額や控除の判定ではありません。").pack(anchor="w", pady=(0, 8))
    controls = ttk.Frame(outer)
    controls.pack(fill="x")
    ttk.Label(controls, text="対象月 YYYY-MM").grid(row=0, column=0, sticky="w")
    ttk.Entry(controls, textvariable=period, width=12).grid(row=0, column=1, padx=6)
    expense_accounts = [a for a in store.accounts() if a["type"] == "費用"]
    values = [f'{a["code"]} {a["name"]}' for a in expense_accounts]
    if values:
        account.set(values[0])
    ttk.Label(controls, text="経費科目").grid(row=1, column=0, sticky="w", pady=6)
    ttk.Combobox(controls, textvariable=account, values=values, state="readonly", width=25).grid(row=1, column=1, columnspan=2, sticky="w", padx=6)
    ttk.Label(controls, text="月予算（円）").grid(row=1, column=3, sticky="w", padx=(8, 0))
    ttk.Entry(controls, textvariable=amount, width=15).grid(row=1, column=4, padx=6)
    columns = ("code", "name", "budget", "actual", "remaining", "state")
    table = ttk.Treeview(outer, columns=columns, show="headings", height=12)
    for col, title, width in zip(columns, ("コード", "経費科目", "予算", "実績", "残り", "判定"), (75, 180, 110, 110, 110, 90)):
        table.heading(col, text=title)
        table.column(col, width=width, stretch=col == "name", anchor="w" if col == "name" else "e")
    table.pack(fill="both", expand=True, pady=8)
    ttk.Label(outer, textvariable=status, wraplength=750).pack(anchor="w")

    def refresh():
        try:
            report = budget.report(period.get())
        except BudgetError as exc:
            messagebox.showerror("対象月を確認", str(exc), parent=win)
            return
        for item in table.get_children():
            table.delete(item)
        for row in report["rows"]:
            fmt = lambda x: "未設定" if x is None else f"{x:,}"
            table.insert("", "end", values=(row["code"], row["name"], fmt(row["budget_yen"]),
                                              fmt(row["actual_yen"]), fmt(row["remaining_yen"]), row["status"]))
        suffix = "未設定の経費があります。全体の残額は表示しません。" if not report["all_active_expenses_budgeted"] else f'残り {report["total_remaining_yen"]:,}円'
        status.set(f'設定済み予算 {report["budget_total_yen"]:,}円 / 記帳済み経費 {report["actual_total_yen"]:,}円。{suffix}')

    def save():
        try:
            if not account.get().strip():
                raise BudgetError("経費科目を選択してください")
            changed = budget.set_budget(period.get(), account.get().split()[0], amount.get())
        except BudgetError as exc:
            messagebox.showerror("入力を確認", str(exc), parent=win)
            return
        status.set("予算を保存しました。" if changed else "同じ予算が既に保存されています。")
        refresh()

    ttk.Button(controls, text="予算を保存", command=save).grid(row=1, column=5, padx=6)
    ttk.Button(controls, text="月の実績を表示", command=refresh).grid(row=0, column=3, columnspan=2, sticky="w", padx=8)
    ttk.Button(controls, text="閉じる", command=win.destroy).grid(row=0, column=5, padx=6)
    refresh()
    return win
