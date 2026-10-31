import tkinter as tk
from datetime import date
from tkinter import filedialog,messagebox,simpledialog,ttk
from core import TYPES,METHODS,BookError,Store
class App(tk.Tk):
 def __init__(self):
  super().__init__();self.title("Double-Entry Bookkeeping US");self.geometry("1180x760");self.minsize(980,650);self.s=Store();self.protocol("WM_DELETE_WINDOW",self.close)
  self.d=tk.StringVar(value=date.today().isoformat());self.desc=tk.StringVar();self.method=tk.StringVar(value=self.s.accounting_method);self.lines=[];self.build();self.refresh_accounts();self.refresh()
 def build(self):
  ttk.Label(self,text="Double-Entry Bookkeeping US",font=("Segoe UI",18,"bold")).pack(anchor="w",padx=14,pady=(14,2));ttk.Label(self,text="United States only · USD · local books. Choose cash or accrual before the first entry.").pack(anchor="w",padx=14)
  p=ttk.Panedwindow(self,orient="horizontal");p.pack(fill="both",expand=True,padx=14,pady=10);f=ttk.Labelframe(p,text="Journal entry",padding=10);p.add(f,weight=2)
  ttk.Label(f,text="Accounting method").grid(row=0,column=0);m=ttk.Combobox(f,textvariable=self.method,values=METHODS,state="readonly");m.grid(row=0,column=1,sticky="ew");m.bind("<<ComboboxSelected>>",lambda _e:self.change_method())
  ttk.Label(f,text="Date").grid(row=1,column=0);ttk.Entry(f,textvariable=self.d).grid(row=1,column=1,sticky="ew");ttk.Label(f,text="Description").grid(row=2,column=0);ttk.Entry(f,textvariable=self.desc).grid(row=2,column=1,columnspan=2,sticky="ew")
  ttk.Label(f,text="Account").grid(row=3,column=0);ttk.Label(f,text="Debit").grid(row=3,column=1);ttk.Label(f,text="Credit").grid(row=3,column=2)
  for i in range(6):
   a,b,c=tk.StringVar(),tk.StringVar(),tk.StringVar();box=ttk.Combobox(f,textvariable=a,state="readonly");box.grid(row=4+i,column=0,sticky="ew");ttk.Entry(f,textvariable=b).grid(row=4+i,column=1);ttk.Entry(f,textvariable=c).grid(row=4+i,column=2);self.lines.append((a,b,c,box))
  ttk.Button(f,text="Post entry",command=self.post).grid(row=10,column=0,sticky="ew");ttk.Button(f,text="Add account",command=self.add_account).grid(row=10,column=1,sticky="ew");ttk.Button(f,text="Lock period",command=self.lock).grid(row=10,column=2,sticky="ew");ttk.Button(f,text="Export journal CSV",command=self.export).grid(row=11,column=0,columnspan=3,sticky="ew",pady=4);f.columnconfigure(0,weight=2)
  nb=ttk.Notebook(p);p.add(nb,weight=3);j=ttk.Frame(nb,padding=8);r=ttk.Frame(nb,padding=8);nb.add(j,text="Journal");nb.add(r,text="Reports")
  self.tree=ttk.Treeview(j,columns=("d","x","a","db","cr"),show="headings")
  for c,t in zip(("d","x","a","db","cr"),("Date","Description","Account","Debit","Credit")):self.tree.heading(c,text=t)
  self.tree.pack(fill="both",expand=True);self.report=tk.Text(r,font=("Consolas",10),state="disabled");self.report.pack(fill="both",expand=True)
 def refresh_accounts(self):
  vals=[f'{a["code"]} {a["name"]}' for a in self.s.accounts()]
  for _,_,_,b in self.lines:b["values"]=vals
 def code(self,x):return x.split()[0] if x.strip() else ""
 def change_method(self):
  try:self.s.set_method(self.method.get())
  except BookError as e:self.method.set(self.s.accounting_method);messagebox.showwarning("Accounting method",str(e))
 def post(self):
  try:self.s.post(self.d.get(),self.desc.get(),[(self.code(a.get()),b.get(),c.get()) for a,b,c,_ in self.lines])
  except BookError as e:messagebox.showerror("Journal entry",str(e));return
  self.desc.set("")
  for a,b,c,_ in self.lines:a.set("");b.set("");c.set("")
  self.refresh()
 def add_account(self):
  code=simpledialog.askstring("Account","Code");name=simpledialog.askstring("Account","Name");typ=simpledialog.askstring("Account","Type: asset, liability, equity, revenue, expense")
  if not all([code,name,typ]):return
  try:self.s.add_account(code,name,typ.lower())
  except BookError as e:messagebox.showerror("Account",str(e));return
  self.refresh_accounts()
 def lock(self):
  d=simpledialog.askstring("Period lock","Lock entries through YYYY-MM-DD")
  if d:
   try:self.s.lock(d);messagebox.showinfo("Period lock",f"Locked through {d}")
   except BookError as e:messagebox.showerror("Period lock",str(e))
 def refresh(self):
  for i in self.tree.get_children():self.tree.delete(i)
  for i,r in enumerate(self.s.journal()):self.tree.insert("","end",iid=str(i),values=(r["entry_date"],r["description"],f'{r["code"]} {r["name"]}',f'USD {r["debit_cents"]/100:,.2f}' if r["debit_cents"] else "",f'USD {r["credit_cents"]/100:,.2f}' if r["credit_cents"] else ""))
  p=self.s.pnl();b=self.s.bs();t=["TRIAL BALANCE","="*64]
  for x in self.s.trial():
   if x["debit"] or x["credit"]:t.append(f'{x["code"]:<6}{x["name"]:<24}{x["debit"]/100:>14,.2f}{x["credit"]/100:>14,.2f}')
  t+=["","PROFIT & LOSS",f'Revenue USD {p["revenue"]/100:,.2f}',f'Expenses USD {p["expense"]/100:,.2f}',f'Net income USD {p["net_income"]/100:,.2f}',"","BALANCE SHEET",f'Assets USD {b["assets"]/100:,.2f}',f'Liabilities USD {b["liabilities"]/100:,.2f}',f'Equity USD {b["equity"]/100:,.2f}',f'Current income USD {b["current_income"]/100:,.2f}',"",f'Accounting method: {self.s.accounting_method}']
  self.report.configure(state="normal");self.report.delete("1.0","end");self.report.insert("1.0","\n".join(t));self.report.configure(state="disabled")
 def export(self):
  x=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")])
  if x:self.s.export(x);messagebox.showinfo("Export","Journal exported")
 def close(self):self.s.close();self.destroy()
if __name__=="__main__":App().mainloop()
