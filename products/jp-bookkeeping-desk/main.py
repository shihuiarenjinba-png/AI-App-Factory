import tkinter as tk
from datetime import date
from tkinter import filedialog,messagebox,simpledialog,ttk
from core import TYPES,BookError,Store,suggest_entry
from tax_assets import JP_CONSUMPTION_TAX_PRESETS,consumption_tax_from_net,jp_depreciation_schedule
class App(tk.Tk):
 def __init__(self):
  super().__init__();self.title("複式簿記デスク 日本版");self.geometry("1180x760");self.minsize(980,650);self.s=Store();self.protocol("WM_DELETE_WINDOW",self.close)
  self.d=tk.StringVar(value=date.today().isoformat());self.desc=tk.StringVar();self.lines=[];self.build();self.refresh_accounts();self.refresh()
 def build(self):
  ttk.Label(self,text="複式簿記デスク 日本版",font=("Yu Gothic UI",18,"bold")).pack(anchor="w",padx=14,pady=(14,2));ttk.Label(self,text="日本国内向け・円建て。仕訳帳→総勘定元帳→試算表→貸借対照表・損益計算書の流れをローカルで管理します。").pack(anchor="w",padx=14)
  p=ttk.Panedwindow(self,orient="horizontal");p.pack(fill="both",expand=True,padx=14,pady=10);f=ttk.Labelframe(p,text="仕訳入力",padding=10);p.add(f,weight=2)
  ttk.Label(f,text="日付").grid(row=0,column=0);ttk.Entry(f,textvariable=self.d).grid(row=0,column=1,sticky="ew");ttk.Label(f,text="摘要").grid(row=1,column=0);ttk.Entry(f,textvariable=self.desc).grid(row=1,column=1,columnspan=2,sticky="ew")
  ttk.Label(f,text="勘定科目").grid(row=2,column=0);ttk.Label(f,text="借方").grid(row=2,column=1);ttk.Label(f,text="貸方").grid(row=2,column=2)
  for i in range(6):
   a,b,c=tk.StringVar(),tk.StringVar(),tk.StringVar();box=ttk.Combobox(f,textvariable=a,state="readonly");box.grid(row=3+i,column=0,sticky="ew");ttk.Entry(f,textvariable=b).grid(row=3+i,column=1);ttk.Entry(f,textvariable=c).grid(row=3+i,column=2);self.lines.append((a,b,c,box))
  ttk.Button(f,text="仕訳候補を推測",command=self.suggest).grid(row=9,column=0,columnspan=3,sticky="ew",pady=3)
  ttk.Button(f,text="記帳",command=self.post).grid(row=10,column=0,sticky="ew");ttk.Button(f,text="科目追加",command=self.add_account).grid(row=10,column=1,sticky="ew");ttk.Button(f,text="期間を締める",command=self.lock).grid(row=10,column=2,sticky="ew");ttk.Button(f,text="税率・固定資産計算",command=self.tax_assets).grid(row=11,column=0,columnspan=3,sticky="ew",pady=3)
  ttk.Button(f,text="CSV出力",command=self.export).grid(row=12,column=0,columnspan=3,sticky="ew",pady=4);f.columnconfigure(0,weight=2)
  nb=ttk.Notebook(p);p.add(nb,weight=3);j=ttk.Frame(nb,padding=8);r=ttk.Frame(nb,padding=8);nb.add(j,text="仕訳帳");nb.add(r,text="帳票")
  self.tree=ttk.Treeview(j,columns=("d","x","a","db","cr"),show="headings")
  for c,t in zip(("d","x","a","db","cr"),("日付","摘要","勘定科目","借方","貸方")):self.tree.heading(c,text=t)
  self.tree.pack(fill="both",expand=True);self.report=tk.Text(r,font=("Consolas",10),state="disabled");self.report.pack(fill="both",expand=True)
 def refresh_accounts(self):
  vals=[f'{a["code"]} {a["name"]}' for a in self.s.accounts()]
  for _,_,_,b in self.lines:b["values"]=vals
 def code(self,x):return x.split()[0] if x.strip() else ""
 def suggest(self):
  cand=suggest_entry(self.desc.get())
  if not cand:
   messagebox.showinfo("仕訳候補","摘要から候補を絞れませんでした。手動で勘定科目を選択してください。");return
  vals={a["code"]:f'{a["code"]} {a["name"]}' for a in self.s.accounts()}
  self.lines[0][0].set(vals.get(cand["debit_code"],""));self.lines[1][0].set(vals.get(cand["credit_code"],""))
  messagebox.showinfo("仕訳候補",f'候補: {cand["label"]}\n借方 {cand["debit_code"]} / 貸方 {cand["credit_code"]}\n確信度 {cand["confidence"]:.0%}\n一致語 {", ".join(cand["matched"])}\n\n金額と科目は記帳前に確認してください。')
 def post(self):
  try:self.s.post(self.d.get(),self.desc.get(),[(self.code(a.get()),b.get(),c.get()) for a,b,c,_ in self.lines])
  except BookError as e:messagebox.showerror("仕訳エラー",str(e));return
  self.desc.set("")
  for a,b,c,_ in self.lines:a.set("");b.set("");c.set("")
  self.refresh()
 def add_account(self):
  code=simpledialog.askstring("科目","科目コード");name=simpledialog.askstring("科目","科目名");typ=simpledialog.askstring("科目","区分: 資産 / 負債 / 純資産 / 収益 / 費用")
  if not all([code,name,typ]):return
  try:self.s.add_account(code,name,typ)
  except BookError as e:messagebox.showerror("科目",str(e));return
  self.refresh_accounts()
 def lock(self):
  d=simpledialog.askstring("締め","この日まで締めます (YYYY-MM-DD)")
  if d:
   try:self.s.lock(d);messagebox.showinfo("締め",f"{d}まで締めました")
   except BookError as e:messagebox.showerror("締め",str(e))
 def refresh(self):
  for i in self.tree.get_children():self.tree.delete(i)
  for i,r in enumerate(self.s.journal()):self.tree.insert("","end",iid=str(i),values=(r["entry_date"],r["description"],f'{r["code"]} {r["name"]}',f'{r["debit_yen"]:,}' if r["debit_yen"] else "",f'{r["credit_yen"]:,}' if r["credit_yen"] else ""))
  p=self.s.pnl();b=self.s.bs();chk=self.s.balance_check();t=["試算表","="*60]
  for x in self.s.trial():
   if x["debit"] or x["credit"]:t.append(f'{x["code"]:<6}{x["name"]:<18}{x["debit"]:>14,}{x["credit"]:>14,}')
  t+=["",f'貸借一致: {"OK" if chk["balanced"] else "要確認"} / 差額 {chk["difference"]:,}円',"","損益計算書",f'収益 {p["収益"]:,}円',f'費用 {p["費用"]:,}円',f'当期利益 {p["利益"]:,}円',"","貸借対照表",f'資産 {b["資産"]:,}円',f'負債 {b["負債"]:,}円',f'純資産 {b["純資産"]:,}円',f'当期利益 {b["当期利益"]:,}円']
  self.report.configure(state="normal");self.report.delete("1.0","end");self.report.insert("1.0","\n".join(t));self.report.configure(state="disabled")
 def tax_assets(self):
  mode=simpledialog.askstring("税率・固定資産","消費税 または 減価償却 と入力してください")
  if not mode:return
  try:
   if "消費" in mode:
    amount=simpledialog.askinteger("消費税","税抜金額（円）",minvalue=0)
    if amount is None:return
    rate_name=simpledialog.askstring("消費税","標準税率10% / 軽減税率8% / 非課税・対象外0%",initialvalue="標準税率10%")
    rate=JP_CONSUMPTION_TAX_PRESETS.get(rate_name or "",None)
    if rate is None:
     custom=simpledialog.askfloat("消費税","税率を小数で入力（例 0.10）",minvalue=0)
     if custom is None:return
     rate=str(custom)
    x=consumption_tax_from_net(amount,rate)
    messagebox.showinfo("消費税計算",f'税抜 {x["net"]:,}円\n税額 {x["tax"]:,}円\n税込 {x["gross"]:,}円')
   else:
    cost=simpledialog.askinteger("減価償却","取得価額（円）",minvalue=2)
    first=simpledialog.askstring("減価償却","事業供用開始日 YYYY-MM-DD",initialvalue=date.today().isoformat())
    life=simpledialog.askinteger("減価償却","耐用年数",minvalue=1)
    method=simpledialog.askstring("減価償却","定額法 または 定率法",initialvalue="定額法")
    use=simpledialog.askfloat("減価償却","事業使用割合（%）",initialvalue=100,minvalue=0,maxvalue=100)
    kwargs={}
    if method=="定率法":
     kwargs["declining_rate"]=simpledialog.askfloat("定率法","償却率（例 0.500）",minvalue=0)
     kwargs["revised_rate"]=simpledialog.askfloat("定率法","改定償却率",minvalue=0)
     kwargs["guarantee_rate"]=simpledialog.askfloat("定率法","保証率",minvalue=0)
    rows=jp_depreciation_schedule(cost,first,life,method=method,business_use_percent=use,through_year=date.today().year+life,**kwargs)
    lines=[f'{r["year"]}: {r["business_depreciation"]:,}円 / 月数 {r["months"]} / {r["method_note"]}' for r in rows[:12]]
    messagebox.showinfo("減価償却スケジュール","\n".join(lines)+"\n\n※税務上の方法・率・耐用年数は最新の国税庁資料と届出状況を確認してください。")
  except Exception as e:messagebox.showerror("計算エラー",str(e))
 def export(self):
  x=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")])
  if x:self.s.export(x);messagebox.showinfo("CSV","出力しました")
 def close(self):self.s.close();self.destroy()
if __name__=="__main__":App().mainloop()
