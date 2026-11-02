"""Small, read-only cash movement window for non-accountant users."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from cash_movement import CashMovementError, cash_movement_report


def open_cash_movement_window(parent, store):
    window = tk.Toplevel(parent)
    window.title("お金の出入りを確認")
    window.geometry("850x550")
    window.minsize(720, 450)
    window.transient(parent)
    frame = ttk.Frame(window, padding=12)
    frame.pack(fill="both", expand=True)
    ttk.Label(
        frame, text="現金・預金の動き",
        font=("Yu Gothic UI", 15, "bold"),
    ).pack(anchor="w")
    ttk.Label(
        frame,
        text="記帳した取引から入金・出金と残高を確認します。現金と預金の間の移動は二重計上しません。",
        wraplength=790,
    ).pack(anchor="w", pady=(2, 8))
    filters = ttk.Frame(frame)
    filters.pack(fill="x")
    today = date.today()
    start = tk.StringVar(value=today.replace(day=1).isoformat())
    end = tk.StringVar(value=today.isoformat())
    ttk.Label(filters, text="開始日").pack(side="left")
    ttk.Entry(filters, textvariable=start, width=13).pack(side="left", padx=(5, 12))
    ttk.Label(filters, text="終了日").pack(side="left")
    ttk.Entry(filters, textvariable=end, width=13).pack(side="left", padx=5)
    summary = tk.StringVar()
    ttk.Label(frame, textvariable=summary, wraplength=790).pack(anchor="w", pady=8)
    columns = ("date", "description", "kind", "change", "balance", "id")
    table = ttk.Treeview(frame, columns=columns, show="headings", height=12)
    for key, title, width in zip(
        columns,
        ("日付", "取引内容", "区分", "増減（円）", "残高（円）", "仕訳番号"),
        (105, 250, 155, 110, 110, 80),
    ):
        table.heading(key, text=title)
        table.column(key, width=width, stretch=key == "description")
    table.pack(fill="both", expand=True)
    ttk.Label(
        frame,
        text="※帳簿上の現金・預金の増減です。税務申告用のキャッシュフロー計算書ではありません。",
        wraplength=790,
    ).pack(anchor="w", pady=(8, 0))

    def refresh():
        try:
            result = cash_movement_report(store, start.get(), end.get())
        except CashMovementError as exc:
            messagebox.showerror("日付・科目を確認", str(exc), parent=window)
            return
        for item in table.get_children():
            table.delete(item)
        for row in result["movements"]:
            table.insert("", "end", values=(
                row["date"], row["description"], row["kind"],
                f'{row["net_change_yen"]:+,}', f'{row["balance_yen"]:,}',
                row["entry_id"],
            ))
        summary.set(
            f'開始残高 {result["opening_yen"]:,}円  ＋ 入金 {result["receipts_yen"]:,}円'
            f'  － 出金 {result["payments_yen"]:,}円  ＝ 終了残高 {result["closing_yen"]:,}円'
            + ("" if result["reconciles"] and result["journal_balanced"] else "  ※帳簿の一致を確認してください")
        )
    ttk.Button(filters, text="表示を更新", command=refresh).pack(side="left", padx=12)
    refresh()
    return window
