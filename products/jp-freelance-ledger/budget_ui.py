"""Beginner-first budget window; review never posts accounting or tax entries."""
import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from budgets import BudgetError, INCOME_CATEGORIES, monthly_budget_report, set_budget
from core import CATEGORIES


def open_budget_window(parent, store):
    window = tk.Toplevel(parent)
    window.title("月次予算と実績")
    window.geometry("680x480")
    window.minsize(600, 420)
    window.transient(parent)
    window.grab_set()

    month = tk.StringVar(value=date.today().strftime("%Y-%m"))
    kind = tk.StringVar(value="経費")
    category = tk.StringVar()
    amount = tk.StringVar()
    summary = tk.StringVar(value="月を確認して「実績を表示」を押してください。")

    frame = ttk.Frame(window, padding=12)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="予算と実績を比べる", font=("Yu Gothic UI", 14, "bold")).grid(
        row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
    ttk.Label(frame, text="計画との差を確認する機能です。税額・控除額の判定や自動記帳はしません。").grid(
        row=1, column=0, columnspan=4, sticky="w", pady=(0, 12))
    ttk.Label(frame, text="対象月 YYYY-MM").grid(row=2, column=0, sticky="w")
    ttk.Entry(frame, textvariable=month, width=12).grid(row=2, column=1, sticky="w")
    ttk.Label(frame, text="種別").grid(row=3, column=0, sticky="w", pady=5)
    ttk.Combobox(frame, textvariable=kind, values=("収入", "経費"), state="readonly", width=9).grid(
        row=3, column=1, sticky="w", pady=5)
    ttk.Label(frame, text="科目").grid(row=3, column=2, sticky="w")
    categories = ttk.Combobox(frame, textvariable=category, state="readonly", width=22)
    categories.grid(row=3, column=3, sticky="ew", padx=(5, 0))
    ttk.Label(frame, text="予算（円）").grid(row=4, column=0, sticky="w", pady=5)
    ttk.Entry(frame, textvariable=amount, width=18).grid(row=4, column=1, sticky="w")
    ttk.Label(frame, text="未設定の科目は予算0円とは扱いません。").grid(
        row=4, column=2, columnspan=2, sticky="w")

    def change_kind(*_):
        values = [x for x in CATEGORIES if (x in INCOME_CATEGORIES) == (kind.get() == "収入")]
        categories["values"] = values
        if category.get() not in values:
            category.set(values[0] if values else "")

    kind.trace_add("write", change_kind)
    change_kind()

    columns = ("kind", "category", "budget", "actual", "difference")
    table = ttk.Treeview(frame, columns=columns, show="headings", height=9)
    for key, title, width in zip(columns,
                                 ("種別", "科目", "予算", "実績", "実績－予算"),
                                 (60, 150, 110, 110, 130)):
        table.heading(key, text=title)
        table.column(key, width=width, anchor="e" if key in ("budget", "actual", "difference") else "w")
    table.grid(row=6, column=0, columnspan=4, sticky="nsew", pady=(12, 5))
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=table.yview)
    scrollbar.grid(row=6, column=4, sticky="ns", pady=(12, 5))
    table.configure(yscrollcommand=scrollbar.set)
    ttk.Label(frame, textvariable=summary, wraplength=610, justify="left").grid(
        row=7, column=0, columnspan=4, sticky="w", pady=(4, 0))
    frame.columnconfigure(3, weight=1)
    frame.rowconfigure(6, weight=1)

    def refresh():
        try:
            report = monthly_budget_report(store.conn, month.get().strip())
        except BudgetError as exc:
            messagebox.showerror("入力を確認してください", str(exc), parent=window)
            return
        for item in table.get_children():
            table.delete(item)
        for row in report["rows"]:
            budget = f'{row["budget_yen"]:,}' if row["budget_set"] else "未設定"
            diff = f'{row["difference_yen"]:+,}' if row["budget_set"] else "—"
            table.insert("", "end", values=(row["kind"], row["category"], budget,
                                              f'{row["actual_yen"]:,}', diff))
        summary.set(
            f'収入 {report["income_yen"]:,}円 / 経費 {report["expense_yen"]:,}円 / '
            f'差引 {report["net_yen"]:,}円。'
            f'予算未設定の科目 {report["unbudgeted_categories"]}件。'
            "経費のプラス差額は予算超過、収入のマイナス差額は目標未達です。"
        )

    def save():
        try:
            proposed = amount.get().strip()
            if not proposed:
                raise BudgetError("予算を入力してください。0円も設定できます")
            # Validate before asking for confirmation; no mutation until confirmed.
            from budgets import _budget_yen, _month, _validate_key
            _month(month.get().strip())
            _validate_key(kind.get(), category.get())
            value = _budget_yen(proposed)
            if not messagebox.askyesno(
                "予算を確認", f'{month.get().strip()} / {kind.get()} / {category.get()}\n'
                f'予算 {value:,}円を保存しますか？\n実際の取引や税額は変更しません。',
                parent=window,
            ):
                return
            result = set_budget(store.conn, month.get().strip(), kind.get(), category.get(), value)
            refresh()
            messagebox.showinfo("予算", "予算を保存しました。" if result["saved"] else "同じ予算がすでに保存されています。",
                                parent=window)
        except (BudgetError, ValueError) as exc:
            messagebox.showerror("入力を確認してください", str(exc), parent=window)

    ttk.Button(frame, text="実績を表示", command=refresh).grid(row=5, column=0, columnspan=2, sticky="ew", pady=4)
    ttk.Button(frame, text="予算を確認して保存", command=save).grid(
        row=5, column=2, columnspan=2, sticky="ew", pady=4)
    refresh()
    return window
