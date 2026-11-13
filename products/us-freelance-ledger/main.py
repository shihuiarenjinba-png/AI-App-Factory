import tkinter as tk
import ctypes
import sys
from datetime import date
from pathlib import Path
from tkinter import filedialog,messagebox,simpledialog,ttk
from core import CATEGORIES,DOCUMENT_TYPES,METHODS,LedgerError,Store,suggest_category,review_requirements
from tax_assets import manual_sales_tax,straight_line_book_schedule,custom_tax_depreciation_schedule,require_tax_profile
from receipt_queue import enqueue_receipts, list_receipts, link_receipt
from bank_reconcile import BankReviewError, match_transaction, unmatch_transaction, match_statuses, statement_preview, finalize_statement, cancel_statement
from bank_report import export_bank_report
from bank_csv_preview import BankCSVError, csv_headers, preview_bank_csv, save_review_report

# Keep the confirmation aligned with cancel_statement: no blanket promise of undo.
BANK_FINALIZE_WARNING = (
    "Undo checked can reopen only the latest statement with intact saved evidence.\n"
    "Legacy/missing evidence, changed entries or a later checked month: "
    "REVIEW REQUIRED; automatic undo is blocked.\n"
    "Undo leaves ledger amounts unchanged, returns matches to review, and saves an audit record."
)

TAX_REVIEW_TITLE = "REVIEW REQUIRED — US tax calculation"
TAX_REVIEW_TEXT = (
    "United States (USD) only. This is a manual estimate, NOT a tax return or filing.\n"
    "Verify tax year, jurisdiction, IRS publication, method and business-use percentage.\n"
    "No tax amounts are posted automatically. Continue to the manual calculator?"
)

def confirm_us_tax_review(parent, askyesno=messagebox.askyesno):
    """Require explicit confirmation before any US tax calculator is opened."""
    return askyesno(TAX_REVIEW_TITLE, TAX_REVIEW_TEXT, parent=parent) is True


def _work_area(root):
    """Return Tk-coordinate desktop work area; exclude the Windows taskbar."""
    if sys.platform == "win32":
        try:
            from ctypes import wintypes
            area = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(
                48, 0, ctypes.byref(area), 0
            ) and area.right > area.left and area.bottom > area.top:
                return area.left, area.top, area.right - area.left, area.bottom - area.top
        except (AttributeError, OSError, ValueError):
            pass
    width, height = root.winfo_screenwidth(), root.winfo_screenheight()
    if sys.platform == "win32":
        # SPI failure is not evidence that the taskbar is absent. Keep a
        # conservative inset on all four sides rather than hiding controls.
        return 64, 64, max(1, width - 128), max(1, height - 128)
    return 0, 0, width, height


def _window_bounds(area):
    """Fit the first window within the available work area, including margins."""
    x, y, available_width, available_height = area
    if available_width <= 0 or available_height <= 0:
        raise ValueError("Invalid desktop work area")
    # Tk geometry sizes the client area, not the outer decorated window.
    # On hosted Windows a 1000x696 client at +12,+12 measured as an outer
    # 1016x735 window, crossing the 1024x720 taskbar-safe work area.
    # Reserve space for borders/title bar and DPI-dependent decorations.
    horizontal_reserve = 64 if sys.platform == "win32" else 24
    vertical_reserve = 96 if sys.platform == "win32" else 24
    width = min(1100, max(1, available_width - horizontal_reserve))
    height = min(720, max(1, available_height - vertical_reserve))
    left = x + max(0, (available_width - width) // 2)
    top = y + max(0, (available_height - height) // 2)
    return f"{width}x{height}+{left}+{top}", min(900, width), min(620, height)


class App(tk.Tk):
    def __init__(self):
        super().__init__();self.title("Freelance Ledger US")
        geometry, min_width, min_height = _window_bounds(_work_area(self))
        self.geometry(geometry);self.minsize(min_width, min_height)
        self.store=Store();self.protocol("WM_DELETE_WINDOW",self.close)
        self.v={k:tk.StringVar() for k in ["date","kind","amount","category","party","doctype","docpath","memo","method"]}
        self.v["date"].set(date.today().isoformat());self.v["kind"].set("income");self.v["category"].set(CATEGORIES[0]);self.v["doctype"].set(DOCUMENT_TYPES[0]);self.v["method"].set(self.store.accounting_method)
        self.summary=tk.StringVar();self.receipt_summary=tk.StringVar();self.build();self.refresh();self.refresh_receipts()

    def build(self):
        ttk.Label(self,text="Freelance Ledger US",font=("Segoe UI",18,"bold")).pack(anchor="w",padx=14,pady=(14,2))
        ttk.Label(self,text="United States only · USD · local-only. Bookkeeping support only; federal special rules require review and state/local rules are not automated.").pack(anchor="w",padx=14)
        p=ttk.Panedwindow(self,orient="horizontal");p.pack(fill="both",expand=True,padx=14,pady=10)
        f=ttk.Labelframe(p,text="Transaction",padding=10);p.add(f,weight=1)
        ttk.Label(f,text="Accounting method").grid(row=0,column=0,sticky="w")
        m=ttk.Combobox(f,textvariable=self.v["method"],values=METHODS,state="readonly")
        m.grid(row=0,column=1,sticky="ew",pady=3);m.bind("<<ComboboxSelected>>",lambda _e:self.change_method())
        ttk.Label(f,text="Type").grid(row=1,column=0,sticky="w")
        ttk.Combobox(f,textvariable=self.v["kind"],values=["income","expense"],state="readonly").grid(row=1,column=1,sticky="ew",pady=3)
        ttk.Label(f,text="Category").grid(row=2,column=0,sticky="w")
        ttk.Combobox(f,textvariable=self.v["category"],values=CATEGORIES,state="readonly").grid(row=2,column=1,sticky="ew",pady=3)
        ttk.Label(f,text="Supporting document").grid(row=3,column=0,sticky="w")
        ttk.Combobox(f,textvariable=self.v["doctype"],values=DOCUMENT_TYPES,state="readonly").grid(row=3,column=1,sticky="ew",pady=3)
        for i,(lab,key) in enumerate([("Date","date"),("Amount (USD)","amount"),("Payer / payee","party"),("Memo / business purpose","memo"),("Document reference","docpath")],start=4):
            ttk.Label(f,text=lab).grid(row=i,column=0,sticky="w")
            ttk.Entry(f,textvariable=self.v[key]).grid(row=i,column=1,sticky="ew",pady=3)
        ttk.Button(f,text="Browse supporting file",command=self.pick).grid(row=9,column=0,columnspan=2,sticky="ew",pady=4)
        ttk.Button(f,text="Suggest category",command=self.suggest).grid(row=10,column=0,columnspan=2,sticky="ew",pady=4)
        ttk.Button(f,text="Add transaction",command=self.add).grid(row=11,column=0,columnspan=2,sticky="ew",pady=4)
        ttk.Button(f,text="US tax / fixed assets — REVIEW REQUIRED",command=self.tax_assets).grid(row=12,column=0,columnspan=2,sticky="ew",pady=4)
        ttk.Button(f,text="Export CSV",command=self.export).grid(row=13,column=0,sticky="ew",pady=4)
        ttk.Button(f,text="Backup",command=self.backup).grid(row=13,column=1,sticky="ew",pady=4)
        f.columnconfigure(1,weight=1)
        r=ttk.Labelframe(p,text="Ledger",padding=10);p.add(r,weight=3)
        ttk.Label(r,textvariable=self.summary,font=("Segoe UI",11,"bold")).pack(anchor="w")
        receipt_actions=ttk.Frame(r);receipt_actions.pack(fill="x",pady=(6,2))
        ttk.Button(receipt_actions,text="Add receipts / PDFs",command=self.add_receipts).pack(side="left",padx=(0,6))
        ttk.Button(receipt_actions,text="Review receipt queue",command=self.review_receipts).pack(side="left",padx=(0,6))
        ttk.Label(r,textvariable=self.receipt_summary).pack(anchor="w")
        bank_hint=ttk.Label(r,text="Bank check: 1. Select a row → Match selected  2. Check statement (difference 0)  3. Undo checked (latest only). REVIEW REQUIRED.",wraplength=420)
        bank_hint.pack(anchor="w",fill="x",pady=(5,1))
        r.bind("<Configure>",lambda event:bank_hint.configure(wraplength=max(220,event.width-24)),add="+")
        bank_actions=ttk.Frame(r);bank_actions.pack(fill="x",pady=3)
        ttk.Button(bank_actions,text="Match selected",command=self.match_bank).grid(row=0,column=0,sticky="ew",padx=(0,4),pady=2)
        ttk.Button(bank_actions,text="Check statement",command=self.check_bank).grid(row=0,column=1,sticky="ew",padx=(4,0),pady=2)
        ttk.Button(bank_actions,text="Undo match",command=self.unmatch_bank).grid(row=1,column=0,sticky="ew",padx=(0,4),pady=2)
        ttk.Button(bank_actions,text="Undo checked",command=self.cancel_bank).grid(row=1,column=1,sticky="ew",padx=(4,0),pady=2)
        ttk.Button(bank_actions,text="Export bank check report",command=self.export_bank_check).grid(row=2,column=0,columnspan=2,sticky="ew",pady=2)
        ttk.Button(bank_actions,text="Preview bank CSV (no posting)",command=self.preview_bank_csv_gui).grid(row=3,column=0,columnspan=2,sticky="ew",pady=2)
        bank_actions.columnconfigure(0,weight=1)
        bank_actions.columnconfigure(1,weight=1)
        cols=("date","kind","amount","category","party","memo","bank");self.tree=ttk.Treeview(r,columns=cols,show="headings")
        for c,t in zip(cols,["Date","Type","Amount","Category","Payer / payee","Memo","Bank check"]):
            self.tree.heading(c,text=t);self.tree.column(c,width=90 if c in ("date","kind","amount","bank") else 110)
        self.tree.pack(fill="both",expand=True,pady=(8,0))

    def refresh_receipts(self):
        rows=list_receipts(self.store.conn)
        pending=sum(row["status"]=="PENDING_MANUAL_REVIEW" for row in rows)
        linked=sum(row["status"]=="LINKED" for row in rows)
        self.receipt_summary.set(
            f"Receipts: {pending} awaiting manual entry, {linked} linked. "
            "No OCR or automatic tax decisions."
        )

    def add_receipts(self):
        paths=filedialog.askopenfilenames(
            title="Choose receipt files to review",
            filetypes=[("Receipts (PDF, PNG, JPEG)","*.pdf *.png *.jpg *.jpeg")],
        )
        if not paths:return
        results=enqueue_receipts(self.store.conn,paths)
        counts={status:sum(r["status"]==status for r in results)
                for status in ("QUEUED","DUPLICATE","REJECTED")}
        failures=[f'{r["path"]}: {r["reason"]}' for r in results if r["status"]=="REJECTED"]
        self.refresh_receipts()
        messagebox.showinfo(
            "Receipt intake",
            f'{counts["QUEUED"]} added, {counts["DUPLICATE"]} already queued, '
            f'{counts["REJECTED"]} could not be added.\n'
            "Files remain in their original locations. Review each receipt and enter the details yourself."
            + ("\n\nIssues:\n" + "\n".join(failures[:5]) if failures else "")
        )

    def review_receipts(self):
        rows=[r for r in list_receipts(self.store.conn)
              if r["status"]=="PENDING_MANUAL_REVIEW"]
        if not rows:
            messagebox.showinfo("Receipt queue","No receipts are awaiting manual review.")
            return
        win=tk.Toplevel(self);win.title("Receipts awaiting manual entry")
        win.geometry("760x430");win.minsize(540,320)
        ttk.Label(win,text="Select a receipt, then enter its date, amount and category manually.").pack(anchor="w",padx=12,pady=(12,4))
        listing=tk.Listbox(win,exportselection=False)
        listing.pack(fill="both",expand=True,padx=12,pady=6)
        for r in rows:
            listing.insert("end",f'{r["id"]}: {r["source_path"]}')
        def choose():
            selection=listing.curselection()
            if not selection:return
            selected=rows[selection[0]]["source_path"]
            self.v["docpath"].set(selected)
            self.v["doctype"].set("Receipt")
            win.destroy()
        ttk.Button(win,text="Use selected file for this transaction",command=choose).pack(pady=(2,12))

    def _selected_transaction(self):
        selected=self.tree.selection()
        if not selected:
            messagebox.showinfo("Choose a transaction","Select a ledger row first.")
            return None
        return int(selected[0])

    def match_bank(self):
        txn_id=self._selected_transaction()
        if txn_id is None:return
        account=simpledialog.askstring("Match to bank statement","Bank account label (e.g. Business Checking):",parent=self)
        if account is None:return
        statement_day=simpledialog.askstring("Match to bank statement","Statement ending date (YYYY-MM-DD):",parent=self)
        if statement_day is None:return
        if not messagebox.askyesno("Confirm manual match",
            "Have you checked this transaction against the actual bank statement?\n"
            "This does not import or verify bank records."):
            return
        try:match_transaction(self.store.conn,txn_id,account,statement_day)
        except BankReviewError as exc:messagebox.showerror("Cannot match",str(exc));return
        self.refresh()

    def unmatch_bank(self):
        txn_id=self._selected_transaction()
        if txn_id is None:return
        try:unmatch_transaction(self.store.conn,txn_id)
        except BankReviewError as exc:messagebox.showwarning("Cannot undo",str(exc));return
        self.refresh()

    def check_bank(self):
        account=simpledialog.askstring("Check bank statement","Bank account label:",parent=self)
        if account is None:return
        statement_day=simpledialog.askstring("Check bank statement","Statement ending date (YYYY-MM-DD):",parent=self)
        if statement_day is None:return
        opening=simpledialog.askstring("Check bank statement","Opening balance (USD, e.g. 100.00):",parent=self)
        if opening is None:return
        closing=simpledialog.askstring("Check bank statement","Closing balance (USD, e.g. 150.00):",parent=self)
        if closing is None:return
        try:report=statement_preview(self.store.conn,account,statement_day,opening,closing)
        except BankReviewError as exc:messagebox.showerror("Statement check",str(exc));return
        difference=report["difference_cents"]
        if difference:
            messagebox.showwarning("Balance does not match",
                f'Difference USD {difference/100:,.2f}. Check missing transfers, bank fees, '
                "cash entries and wrong matches. Nothing was finalized.")
            return
        if not messagebox.askyesno("Finalize bank statement",
            f'{len(report["transaction_ids"])} matched transactions; difference USD 0.00.\n'
            "Have you checked the actual statement and included all relevant bank movements?\n" +
            BANK_FINALIZE_WARNING):
            return
        try:finalize_statement(self.store.conn,account,statement_day,opening,closing)
        except BankReviewError as exc:messagebox.showerror("Statement check",str(exc));return
        self.refresh()
        messagebox.showinfo("Statement checked","Matched entries were finalized locally. This is not a tax or bank certification.")

    def cancel_bank(self):
        account=simpledialog.askstring("Undo checked statement","Bank account label:",parent=self)
        if account is None:return
        statement_day=simpledialog.askstring("Undo checked statement","Statement ending date (YYYY-MM-DD):",parent=self)
        if statement_day is None:return
        if not messagebox.askyesno(
            "Review required — undo bank check",
            "1. Check the original bank statement.\n"
            "2. Only the latest checked statement can be undone.\n"
            "3. The matches will return to 'Matched' for review; your ledger amounts "
            "and tax treatment will NOT change.\n\n"
            "Undo this bank check and keep an audit record?"
        ):return
        try:result=cancel_statement(self.store.conn,account,statement_day)
        except BankReviewError as exc:messagebox.showerror("Cannot undo bank check",str(exc));return
        self.refresh()
        messagebox.showinfo(
            "Bank check reopened — REVIEW REQUIRED",
            f'{len(result["transaction_ids"])} entries returned to Matched. '
            "Review the actual statement, check the difference is zero, and finalize again."
        )



    def preview_bank_csv_gui(self):
        """Four-step bank CSV review. Source and ledger are never modified."""
        win=tk.Toplevel(self)
        win.title("Bank CSV review — USD only — NOT posted")
        win.transient(self)
        win.geometry(f"{min(780,max(480,self.winfo_width()-80))}x{min(520,max(400,self.winfo_height()-50))}")
        win.resizable(True,True)
        source=tk.StringVar(value="No file chosen")
        status=tk.StringVar(value="Choose a CSV, map four columns, then preview. Nothing is posted.")
        selection={name:tk.StringVar(value="") for name in ("date","amount","direction","currency")}
        state={"source":None,"preview":None}
        ttk.Label(win,text="1. Choose USD CSV  →  2. Map columns  →  3. Review matches  →  4. Save results",
                  wraplength=680).pack(anchor="w",padx=10,pady=(10,4))
        ttk.Label(win,text="Read-only: no posting or tax decisions. CANDIDATE = possible same date/amount; "
                  "UNMATCHED = no exact entry; DUPLICATE = repeated CSV row; "
                  "REVIEW REQUIRED = ambiguous, already checked or invalid.",
                  wraplength=700).pack(anchor="w",padx=10)
        top=ttk.Frame(win);top.pack(fill="x",padx=10,pady=6)
        ttk.Label(top,textvariable=source).pack(side="left",fill="x",expand=True)
        mapping_frame=ttk.Frame(win);mapping_frame.pack(fill="x",padx=10,pady=4)
        combos={}
        for i,(name,title) in enumerate((("date","Date"),("amount","Positive amount"),
                                         ("direction","In / Out"),("currency","Currency (USD)"))):
            cell=ttk.Frame(mapping_frame);cell.grid(row=0,column=i,sticky="ew",padx=3)
            ttk.Label(cell,text=title).pack(anchor="w")
            combo=ttk.Combobox(cell,textvariable=selection[name],values=(),state="readonly",width=15)
            combo.pack(fill="x");combos[name]=combo
            mapping_frame.columnconfigure(i,weight=1)
        columns=("line","date","direction","cents","ledger","status")
        listing=ttk.Treeview(win,columns=columns,show="headings",height=7)
        for name,title,width in (("line","CSV line",65),("date","Date",95),
                                 ("direction","In / Out",85),("cents","USD cents",95),
                                 ("ledger","Possible ledger IDs",130),("status","Review",160)):
            listing.heading(name,text=title)
            listing.column(name,width=width,stretch=name in ("ledger","status"))
        listing.pack(fill="both",expand=True,padx=10,pady=(5,2))
        ttk.Label(win,textvariable=status,wraplength=700).pack(anchor="w",padx=10,pady=4)
        actions=ttk.Frame(win);actions.pack(fill="x",padx=10,pady=(2,10))
        save_button=ttk.Button(actions,text="4. Save review copy (.txt)",state="disabled")
        save_button.pack(side="right",padx=3)
        def choose():
            filename=filedialog.askopenfilename(parent=win,title="Choose a USD bank CSV",
                                               filetypes=[("CSV","*.csv")])
            if not filename:return
            state["preview"]=None
            save_button.configure(state="disabled")
            for item in listing.get_children():listing.delete(item)
            try:headers=csv_headers(filename)
            except BankCSVError as exc:
                state["source"]=None
                source.set("No valid CSV selected")
                status.set(str(exc));messagebox.showerror("CSV not accepted",str(exc),parent=win)
                return
            state["source"]=filename;source.set(filename)
            for name,combo in combos.items():
                selection[name].set("")
                combo.configure(values=headers)
            status.set("Select the Date, Amount, In/Out and Currency columns explicitly.")
        def review():
            state["preview"]=None
            save_button.configure(state="disabled")
            for item in listing.get_children():listing.delete(item)
            if not state["source"]:
                messagebox.showwarning("Choose CSV","Select a CSV file first.",parent=win);return
            try:
                report=preview_bank_csv(state["source"],{k:v.get() for k,v in selection.items()},
                                        self.store.conn)
            except BankCSVError as exc:
                status.set("REVIEW REQUIRED — " + str(exc))
                messagebox.showwarning("Preview refused",str(exc),parent=win)
                return
            state["preview"]=report
            for row in report["rows"][:100]:
                listing.insert("","end",values=(row["line"],row["date"],row["direction"],
                    row["amount_cents"] if row["amount_cents"] is not None else "INVALID",
                    ",".join(map(str,row["ledger_candidate_ids"])) or
                    ",".join(f'{x["transaction_id"]}:{x["difference_cents"]:+d}c' for x in row["difference_candidates"]),
                    row["review_bucket"] + " — " + row["status"] +
                    (": "+",".join(row["issues"]) if row["issues"] else "")))
            buckets=report["buckets"]
            status.set(f'{len(report["rows"])} rows: {buckets["CANDIDATE"]} candidate, '
                       f'{buckets["UNMATCHED"]} unmatched, {buckets["DUPLICATE"]} duplicate, '
                       f'{buckets["REVIEW REQUIRED"]} need review. '
                       'Showing first 100; NO match is confirmed. Step 4 saves all rows.')
            save_button.configure(state="normal")
        def save():
            report=state["preview"]
            if report is None:return
            target=filedialog.asksaveasfilename(parent=win,title="Save bank CSV review copy",
                  defaultextension=".txt",filetypes=[("Text review","*.txt")])
            if not target:return
            try:path=save_review_report(report,target,self.store.conn)
            except BankCSVError as exc:
                status.set("NOT SAVED — " + str(exc))
                messagebox.showerror("NOT saved",str(exc),parent=win);return
            status.set("Review saved to: " + path + " — ledger unchanged")
            messagebox.showinfo("Review copy saved — REVIEW REQUIRED",
                f'Saved to: {path}\nOriginal bank CSV and ledger unchanged. '
                'Check the actual bank statement before manual matching.',parent=win)
        ttk.Button(top,text="1. Choose CSV",command=choose).pack(side="right",padx=3)
        ttk.Button(actions,text="3. Preview candidates",command=review).pack(side="left",padx=3)
        save_button.configure(command=save)

    def export_bank_check(self):
        """Export a checked statement or an audited historical undo, never silently overwrite."""
        account=simpledialog.askstring("Export bank check","Bank account label:",parent=self)
        if account is None:return
        statement_day=simpledialog.askstring("Export bank check","Statement ending date (YYYY-MM-DD):",parent=self)
        if statement_day is None:return
        target=filedialog.asksaveasfilename(
            parent=self,title="Save bank check CSV (a matching .txt report is also created)",
            defaultextension=".csv",filetypes=[("CSV report","*.csv")]
        )
        if not target:return
        try:receipt=export_bank_report(self.store.conn,account,statement_day,target)
        except (BankReviewError,OSError) as exc:
            messagebox.showerror("Bank report NOT saved",str(exc))
            return
        messagebox.showinfo(
            "Bank check report saved — REVIEW REQUIRED",
            f'Status: {receipt["status"]}\n'
            f'Entries: {len(receipt["transaction_ids"])}\n'
            f'Difference: USD {receipt["difference_cents"]/100:.2f}\n'
            f'CSV: {receipt["csv_path"]}\n'
            f'Readable report: {receipt["text_path"]}\n\n'
            "Compare with your actual bank statement. Not bank or tax certification."
        )

    def change_method(self):
        if not messagebox.askyesno(
            "Accounting method",
            "Cash/accrual is a federal accounting-method issue, not merely a display preference. "
            "Changing an established method may require IRS procedures such as Form 3115. "
            "Use the method appropriate for your records and professional advice. Continue?"
        ):
            self.v["method"].set(self.store.accounting_method);return
        try:self.store.set_accounting_method(self.v["method"].get())
        except LedgerError as e:self.v["method"].set(self.store.accounting_method);messagebox.showwarning("Accounting method",str(e))

    def pick(self):
        x=filedialog.askopenfilename(title="Select supporting document")
        if x:self.v["docpath"].set(x)

    def suggest(self):
        text=" ".join([self.v["party"].get(),self.v["memo"].get(),self.v["doctype"].get()])
        result=suggest_category(text,self.v["kind"].get())
        if not result:
            messagebox.showinfo("Category suggestion","No reliable category suggestion. Review the transaction and choose manually.")
            return
        best=result[0];self.v["category"].set(best["category"])
        reasons=review_requirements(best["category"])
        extra=("\n\nREVIEW REQUIRED:\n- "+"\n- ".join(reasons)) if reasons else ""
        messagebox.showinfo(
            "Category suggestion",
            f'Candidate: {best["category"]}\nConfidence: {best["confidence"]:.0%}\nMatched: {", ".join(best["matched"])}{extra}\n\nReview before posting.'
        )

    def add(self):
        reasons=review_requirements(self.v["category"].get())
        if reasons:
            msg="This category has special federal/state rules:\n\n- "+"\n- ".join(reasons)+"\n\nRecord it as bookkeeping data anyway?"
            if not messagebox.askyesno("Review required",msg):
                return
        try:txn_id=self.store.add(
            self.v["date"].get(),self.v["kind"].get(),self.v["amount"].get(),self.v["category"].get(),
            self.v["party"].get(),self.v["doctype"].get(),self.v["docpath"].get(),self.v["memo"].get()
        )
        except LedgerError as e:messagebox.showerror("Input error",str(e));return
        source=self.v["docpath"].get()
        if source and any(Path(r["source_path"]).resolve()==Path(source).resolve() and r["status"]=="PENDING_MANUAL_REVIEW"
                          for r in list_receipts(self.store.conn)):
            if not link_receipt(self.store.conn,source,txn_id):
                messagebox.showwarning(
                    "Receipt needs review",
                    "Transaction saved, but the receipt file changed or could not be verified. "
                    "Check the original document before relying on this reference."
                )
        self.refresh_receipts()
        for k in ["amount","party","docpath","memo"]:self.v[k].set("")
        self.refresh()

    def refresh(self):
        for i in self.tree.get_children():self.tree.delete(i)
        bank_status=match_statuses(self.store.conn)
        for r in self.store.rows():
            status={"CLEARED":"Matched","RECONCILED":"Checked"}.get(bank_status.get(r["id"]),"Not matched")
            self.tree.insert("","end",iid=str(r["id"]),values=(r["txn_date"],r["kind"],f'USD {r["amount_cents"]/100:,.2f}',r["category"],r["payer_payee"],r["memo"],status))
        d=date.today();s=self.store.monthly(d.year,d.month);y=self.store.annual_summary(d.year)
        self.summary.set(
            f"{d:%B %Y} bookkeeping net USD {s['net']/100:,.2f}  |  "
            f"YTD income USD {y['income']/100:,.2f}  expenses USD {y['expense']/100:,.2f}  "
            f"bookkeeping net USD {y['net']/100:,.2f} (not taxable income)"
        )

    def tax_assets(self):
        if not confirm_us_tax_review(self):
            return
        mode=simpledialog.askstring("Tax / fixed assets","Enter sales tax, book depreciation, or tax depreciation")
        if not mode:return
        try:
            lower=mode.strip().lower()
            if lower == "sales tax":
                amount=simpledialog.askfloat("Sales tax","Amount before tax",minvalue=0)
                rate=simpledialog.askfloat("Sales tax","Jurisdiction rate (%) — enter manually",minvalue=0)
                jurisdiction=simpledialog.askstring("Sales tax","Jurisdiction name")
                if amount is None or rate is None:return
                x=manual_sales_tax(amount,rate)
                messagebox.showinfo("REVIEW REQUIRED — Sales tax",f'Jurisdiction: {jurisdiction or "manual"}\nTax USD {x["tax"]}\nGross USD {x["gross"]}\n\nREVIEW REQUIRED: Arithmetic only; nexus/taxability is not determined. No posting.')
            elif lower == "tax depreciation":
                source=simpledialog.askstring("Tax depreciation","IRS source URL",initialvalue="https://www.irs.gov/publications/p946")
                tax_year=simpledialog.askinteger("Tax depreciation","Tax year",initialvalue=date.today().year,minvalue=2000)
                method=simpledialog.askstring("Tax depreciation","Method/profile name")
                require_tax_profile(source,tax_year,method or "")
                cost=simpledialog.askfloat("Tax depreciation","Depreciable basis (USD)",minvalue=0)
                start=simpledialog.askinteger("Tax depreciation","First schedule year",initialvalue=tax_year,minvalue=2000)
                raw=simpledialog.askstring("Tax depreciation","Year percentages, comma-separated")
                if cost is None or start is None or not raw:return
                vals=[v.strip() for v in raw.split(",") if v.strip()]
                rows=custom_tax_depreciation_schedule(cost,{start+i:v for i,v in enumerate(vals)})
                messagebox.showinfo("REVIEW REQUIRED — Tax depreciation","\n".join(f'{r["year"]}: USD {r["business_depreciation"]}' for r in rows[:12])+"\n\nREVIEW REQUIRED: Verify IRS tax-year rules before use. No posting.")
            elif lower == "book depreciation":
                cost=simpledialog.askfloat("Book depreciation","Asset cost (USD)",minvalue=0)
                first=simpledialog.askstring("Book depreciation","Placed-in-service date YYYY-MM-DD",initialvalue=date.today().isoformat())
                life=simpledialog.askinteger("Book depreciation","Useful life in years",minvalue=1)
                salvage=simpledialog.askfloat("Book depreciation","Salvage value",initialvalue=0,minvalue=0)
                use=simpledialog.askfloat("Book depreciation","Business-use percent",initialvalue=100,minvalue=0,maxvalue=100)
                if cost is None or not first or life is None:return
                rows=straight_line_book_schedule(cost,first,life,salvage_value=salvage or 0,business_use_percent=use or 0,through_year=date.today().year+life)
                messagebox.showinfo("REVIEW REQUIRED — Book depreciation","\n".join(f'{r["year"]}: USD {r["business_depreciation"]}' for r in rows[:12])+"\n\nREVIEW REQUIRED: Book and tax depreciation are separate. No posting.")
            else:
                messagebox.showwarning("REVIEW REQUIRED — Unknown calculation",
                    "Choose exactly one supported calculation: sales tax, book depreciation, or tax depreciation. Nothing was calculated or posted.")
                return
        except Exception as e:messagebox.showerror("Calculation error",str(e))
    def export(self):
        x=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")])
        if x:self.store.export_csv(x);messagebox.showinfo("Export","CSV exported")

    def backup(self):
        x=filedialog.asksaveasfilename(defaultextension=".sqlite3",filetypes=[("SQLite","*.sqlite3")])
        if x:self.store.backup(x);messagebox.showinfo("Backup","Backup created")

    def close(self):
        self.store.close();self.destroy()

if __name__=="__main__":
    App().mainloop()
