import tkinter as tk
from datetime import date
from tkinter import filedialog,messagebox,ttk
from core import CATEGORIES,DOCUMENT_TYPES,METHODS,LedgerError,Store

class App(tk.Tk):
    def __init__(self):
        super().__init__();self.title("Freelance Ledger US");self.geometry("1100x720");self.minsize(900,620)
        self.store=Store();self.protocol("WM_DELETE_WINDOW",self.close)
        self.v={k:tk.StringVar() for k in ["date","kind","amount","category","party","doctype","docpath","memo","method"]}
        self.v["date"].set(date.today().isoformat());self.v["kind"].set("income");self.v["category"].set(CATEGORIES[0]);self.v["doctype"].set(DOCUMENT_TYPES[0]);self.v["method"].set(self.store.accounting_method)
        self.summary=tk.StringVar();self.build();self.refresh()
    def build(self):
        ttk.Label(self,text="Freelance Ledger US",font=("Segoe UI",18,"bold")).pack(anchor="w",padx=14,pady=(14,2))
        ttk.Label(self,text="United States only · USD · local-only records. This app does not prepare or file a tax return.").pack(anchor="w",padx=14)
        p=ttk.Panedwindow(self,orient="horizontal");p.pack(fill="both",expand=True,padx=14,pady=10)
        f=ttk.Labelframe(p,text="Transaction",padding=10);p.add(f,weight=1)
        ttk.Label(f,text="Accounting method").grid(row=0,column=0,sticky="w");m=ttk.Combobox(f,textvariable=self.v["method"],values=METHODS,state="readonly");m.grid(row=0,column=1,sticky="ew",pady=3);m.bind("<<ComboboxSelected>>",lambda _e:self.change_method())
        ttk.Label(f,text="Type").grid(row=1,column=0,sticky="w");ttk.Combobox(f,textvariable=self.v["kind"],values=["income","expense"],state="readonly").grid(row=1,column=1,sticky="ew",pady=3)
        ttk.Label(f,text="Category").grid(row=2,column=0,sticky="w");ttk.Combobox(f,textvariable=self.v["category"],values=CATEGORIES,state="readonly").grid(row=2,column=1,sticky="ew",pady=3)
        ttk.Label(f,text="Supporting document").grid(row=3,column=0,sticky="w");ttk.Combobox(f,textvariable=self.v["doctype"],values=DOCUMENT_TYPES,state="readonly").grid(row=3,column=1,sticky="ew",pady=3)
        for i,(lab,key) in enumerate([("Date","date"),("Amount (USD)","amount"),("Payer / payee","party"),("Memo","memo"),("Document reference","docpath")],start=4):
            ttk.Label(f,text=lab).grid(row=i,column=0,sticky="w");ttk.Entry(f,textvariable=self.v[key]).grid(row=i,column=1,sticky="ew",pady=3)
        ttk.Button(f,text="Browse supporting file",command=self.pick).grid(row=9,column=0,columnspan=2,sticky="ew",pady=4)
        ttk.Button(f,text="Add transaction",command=self.add).grid(row=10,column=0,columnspan=2,sticky="ew",pady=4)
        ttk.Button(f,text="Export CSV",command=self.export).grid(row=11,column=0,sticky="ew",pady=4);ttk.Button(f,text="Backup",command=self.backup).grid(row=11,column=1,sticky="ew",pady=4);f.columnconfigure(1,weight=1)
        r=ttk.Labelframe(p,text="Ledger",padding=10);p.add(r,weight=3);ttk.Label(r,textvariable=self.summary,font=("Segoe UI",11,"bold")).pack(anchor="w")
        cols=("date","kind","amount","category","party","memo");self.tree=ttk.Treeview(r,columns=cols,show="headings")
        for c,t in zip(cols,["Date","Type","Amount","Category","Payer / payee","Memo"]):self.tree.heading(c,text=t);self.tree.column(c,width=120)
        self.tree.pack(fill="both",expand=True,pady=(8,0))
    def change_method(self):
        try:self.store.set_accounting_method(self.v["method"].get())
        except LedgerError as e:self.v["method"].set(self.store.accounting_method);messagebox.showwarning("Accounting method",str(e))
    def pick(self):
        x=filedialog.askopenfilename(title="Select supporting document")
        if x:self.v["docpath"].set(x)
    def add(self):
        try:self.store.add(self.v["date"].get(),self.v["kind"].get(),self.v["amount"].get(),self.v["category"].get(),self.v["party"].get(),self.v["doctype"].get(),self.v["docpath"].get(),self.v["memo"].get())
        except LedgerError as e:messagebox.showerror("Input error",str(e));return
        for k in ["amount","party","docpath","memo"]:self.v[k].set("")
        self.refresh()
    def refresh(self):
        for i in self.tree.get_children():self.tree.delete(i)
        for r in self.store.rows():self.tree.insert("","end",values=(r["txn_date"],r["kind"],f'USD {r["amount_cents"]/100:,.2f}',r["category"],r["payer_payee"],r["memo"]))
        d=date.today();s=self.store.monthly(d.year,d.month);self.summary.set(f"{d:%B %Y}  Income USD {s['income']/100:,.2f}  Expenses USD {s['expense']/100:,.2f}  Net USD {s['net']/100:,.2f}")
    def export(self):
        x=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")])
        if x:self.store.export_csv(x);messagebox.showinfo("Export","CSV exported")
    def backup(self):
        x=filedialog.asksaveasfilename(defaultextension=".sqlite3",filetypes=[("SQLite","*.sqlite3")])
        if x:self.store.backup(x);messagebox.showinfo("Backup","Backup created")
    def close(self):self.store.close();self.destroy()
if __name__=="__main__":App().mainloop()
