import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog,messagebox,simpledialog,ttk
from core import TYPES,BookError,Store,suggest_entry
from monthly_close import export_month_end_package
from tax_assets import JP_CONSUMPTION_TAX_PRESETS,consumption_tax_from_net,jp_depreciation_schedule
from budget_ui import open_budget_window
from cash_movement_ui import open_cash_movement_window
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
  ttk.Button(f,text="科目・帳簿を調べる",command=self.lookup_help).grid(row=9,column=0,columnspan=3,sticky="ew",pady=3)
  ttk.Button(f,text="複数レシートを取り込む",command=self.import_receipts).grid(row=10,column=0,columnspan=3,sticky="ew",pady=3)
  ttk.Button(f,text="仕訳候補を推測",command=self.suggest).grid(row=11,column=0,columnspan=3,sticky="ew",pady=3)
  ttk.Button(f,text="記帳",command=self.post).grid(row=12,column=0,sticky="ew");ttk.Button(f,text="科目追加",command=self.add_account).grid(row=12,column=1,sticky="ew");ttk.Button(f,text="期間を締める",command=self.lock).grid(row=12,column=2,sticky="ew")
  ttk.Button(f,text="税率・固定資産計算",command=self.tax_assets).grid(row=13,column=0,columnspan=3,sticky="ew",pady=3)
  ttk.Button(f,text="CSV出力",command=self.export).grid(row=14,column=0,sticky="ew",pady=4)
  ttk.Button(f,text="月の予算と実績",command=self.open_budget).grid(row=14,column=1,sticky="ew",pady=4)
  ttk.Button(f,text="お金の出入りを確認",command=self.open_cash_movement).grid(row=14,column=2,sticky="ew",pady=4)
  f.columnconfigure(0,weight=2)
  nb=ttk.Notebook(p);p.add(nb,weight=3);j=ttk.Frame(nb,padding=8);r=ttk.Frame(nb,padding=8);nb.add(j,text="仕訳帳");nb.add(r,text="帳票")
  self.tree=ttk.Treeview(j,columns=("d","x","a","db","cr"),show="headings")
  for c,t in zip(("d","x","a","db","cr"),("日付","摘要","勘定科目","借方","貸方")):self.tree.heading(c,text=t)
  self.tree.pack(fill="both",expand=True)
  ttk.Button(r,text="この数字の根拠を見る：月末レポートを保存（HTML・CSV・JSON）",command=self.month_end_pack).pack(anchor="w",pady=(0,6))
  receipt_card=ttk.Labelframe(r,text="未処理証憑（確認する書類）",padding=8);receipt_card.pack(fill="x",pady=(0,6))
  self.receipt_summary=tk.StringVar(value="未処理証憑を確認しています")
  ttk.Label(receipt_card,textvariable=self.receipt_summary,wraplength=650,justify="left").pack(anchor="w")
  ttk.Button(receipt_card,text="未処理証憑の一覧・処理状態を見る",command=self.view_receipts).pack(anchor="w",pady=(5,0))
  backup_actions=ttk.Frame(receipt_card);backup_actions.pack(anchor="w",pady=(6,0))
  ttk.Button(backup_actions,text="バックアップを作成",command=self.backup_receipts).pack(side="left",padx=(0,5))
  ttk.Button(backup_actions,text="復元前の確認",command=self.inspect_receipt_backup).pack(side="left",padx=(0,5))
  ttk.Button(backup_actions,text="別の帳簿として復元",command=self.restore_receipt_backup).pack(side="left")
  self.report=tk.Text(r,font=("Consolas",10),state="disabled");self.report.pack(fill="both",expand=True)
 def refresh_accounts(self):
  vals=[f'{a["code"]} {a["name"]}' for a in self.s.accounts()]
  for _,_,_,b in self.lines:b["values"]=vals
 def code(self,x):return x.split()[0] if x.strip() else ""
 def lookup_help(self):
  q=simpledialog.askstring("科目・帳簿検索","例: 家賃 / パソコン / 個人カード / 売掛 / 原状回復 / 資産除去債務")
  if not q:return
  accounts=self.s.search_help(q,limit=7,include_advanced=True);books=self.s.search_book_help(q,limit=4);lines=[]
  if accounts:
   lines.append("【勘定科目・参考情報】")
   active_codes={item["code"] for item in self.s.accounts()}
   for a in accounts:
    level="上級・要確認" if a["audience"]=="advanced" else a["audience"]
    if a["code"] not in active_codes:level+=" / 参考のみ・記帳科目未登録"
    lines.append(f'・{a["code"]} {a["name"]} ({a["type"]} / {level})\n  使う場面: {a["use_text"]}\n  帳簿: {a["books"]}\n  例: {a["example"]}')
  if books:
   lines.append("\n【帳簿候補】")
   for b in books:lines.append(f'・{b["book"]}: {b["purpose"]}')
  if not lines:lines=["候補が見つかりませんでした。用途・取引内容を別の言葉で検索してください。"]
  messagebox.showinfo("科目・帳簿検索","\n".join(lines[:20]))
 def import_receipts(self):
  paths=filedialog.askopenfilenames(title="複数のレシート・請求書画像/PDFを選択")
  if not paths:return
  added=0;failures=[]
  for path in paths:
   try:added+=self.s.enqueue_receipts([path],preserve_source=True)
   except BookError as e:failures.append(f"{Path(path).name}: {e}")
  self.refresh_receipt_card()
  summary=f"{added}件の原本バイトをローカルに保存しました。"
  if failures:
   summary+=f"\n{len(failures)}件は保存できず要確認です。\n"+"\n".join(failures[:5])
  summary+="\n原本の確認と記帳・税務上の必要経費判定は別です。自動で経費認定しません。"
  (messagebox.showwarning if failures else messagebox.showinfo)("証憑取り込み",summary)
 def refresh_receipt_card(self):
  rows=self.s.receipts()
  pending=sum(r["status"]!="POSTED" for r in rows)
  custody=self.s.receipt_custody_summary()
  self.receipt_summary.set(
   f"現在の未処理：{pending}件（全期間）。原本を確認できる：{custody['verified']}件、"
   f"確認が必要：{custody['review_required']}件。"
   "対象月末時点の件数は月末レポートで確認します。"
   "古いデータや記録欠損は要確認です。処理状態は仕訳・税務上の経費承認を意味しません。")
 def backup_receipts(self):
  path=filedialog.asksaveasfilename(title="証憑と帳簿のバックアップ保存先",defaultextension=".zip",
                                    filetypes=[("バックアップ ZIP","*.zip")])
  if not path:return
  try:
   result=self.s.create_receipt_backup(path)
   messagebox.showinfo("バックアップを作成",
    f'帳簿と原本 {result["receipt_count"]}件を照合して保存しました。\\n保存先: {result["path"]}\\n'
    "別のドライブにもコピーしてください。税務上の適合や経費承認を保証しません。")
  except BookError as e:
   messagebox.showwarning("バックアップを作成できません",
    f"確認が必要なデータがあります。保存は中止しました。\\n理由: {e}\\n原本の保存状態を確認してください。")
 def inspect_receipt_backup(self):
  path=filedialog.askopenfilename(title="復元前にバックアップを確認",filetypes=[("バックアップ ZIP","*.zip")])
  if not path:return
  try:
   info=self.s.inspect_receipt_backup(path)
   messagebox.showinfo("復元前の確認",
    f'照合できました。原本 {info["receipt_count"]}件。\\n'
    "復元時は新しい帳簿を作成します。現在の帳簿は上書きしません。\\n"
    "原本の外部ファイル参照は復元後に再確認が必要な場合があります。")
  except BookError as e:
   messagebox.showwarning("復旧できない理由",
    f"バックアップの照合に失敗しました。復元しません。\\n理由: {e}")
 def restore_receipt_backup(self):
  path=filedialog.askopenfilename(title="復元するバックアップを選択",filetypes=[("バックアップ ZIP","*.zip")])
  if not path:return
  try:info=self.s.inspect_receipt_backup(path)
  except BookError as e:
   messagebox.showwarning("復旧できない理由",f"復元前の照合に失敗しました。\\n理由: {e}");return
  if not messagebox.askyesno("復元前の確認",
   f'原本 {info["receipt_count"]}件を確認しました。\\n'
   "現在の帳簿を上書きせず、新しいフォルダーに復元します。続けますか？"):return
  parent=filedialog.askdirectory(title="復元先の親フォルダーを選択（新しい帳簿を作成）")
  if not parent:return
  try:
   restored=self.s.restore_receipt_backup(path,parent)
   messagebox.showinfo("新しい帳簿へ復元",
    f'復元しました。原本 {restored["receipt_count"]}件。\\n'
    f'新しい帳簿: {restored["database"]}\\n'
    "現在開いている帳簿は変更していません。復元した帳簿の原本参照は再確認してください。")
  except BookError as e:
   messagebox.showwarning("復旧できない理由",
    f"復元を中止しました。現在の帳簿は変更していません。\\n理由: {e}")
 def view_receipts(self):
  win=tk.Toplevel(self);win.title("証憑の確認・処理状態");win.geometry("760x440");win.minsize(640,350)
  ttk.Label(win,text="原本を確認してから状態を変更してください。処理済みでも仕訳登録・税務上の経費認定はされません。",
            wraplength=700).pack(anchor="w",padx=12,pady=10)
  tree=ttk.Treeview(win,columns=("id","file","status","original"),show="headings",selectmode="browse")
  for col,title,width in (("id","ID",55),("file","証憑ファイル名",250),("status","現在の状態",170),("original","原本の確認",155)):
   tree.heading(col,text=title);tree.column(col,width=width,stretch=(col=="file"))
  tree.pack(fill="both",expand=True,padx=12,pady=6)
  def populate():
   for item in tree.get_children():tree.delete(item)
   for row in self.s.receipts():
    filename=Path(str(row["file_path"]).replace(chr(92),"/")).name
    status="未処理" if row["status"]=="PENDING" else "処理済み（確認状態のみ）"
    custody=self.s.receipt_custody_status(row["id"])
    original="原本を確認できる" if custody["status"]=="VERIFIED" else "確認が必要"
    tree.insert("","end",iid=str(row["id"]),values=(row["id"],filename,status,original))
  def change(status):
   selected=tree.selection()
   if not selected:
    messagebox.showinfo("証憑の確認","対象の証憑を選択してください",parent=win);return
   if status=="POSTED":
    custody=self.s.receipt_custody_status(int(selected[0]))
    if custody["status"]!="VERIFIED":
     messagebox.showerror("原本の確認",f"原本の保存状態が未確認です：{custody['reason']}\n原本を確認するまで処理済みには変更できません。",parent=win);return
   action="処理済み" if status=="POSTED" else "未処理"
   if not messagebox.askyesno("証憑の確認",f"選択した証憑を{action}に変更しますか？\n税務判断や仕訳登録は行いません。",parent=win):return
   try:self.s.set_receipt_status(int(selected[0]),status)
   except BookError as e:messagebox.showerror("証憑の履歴",f"状態変更を中止しました：{e}",parent=win);return
   populate();self.refresh_receipt_card()
  actions=ttk.Frame(win);actions.pack(fill="x",padx=12,pady=10)
  ttk.Button(actions,text="原本を確認済みとして記録",command=lambda:change("POSTED")).pack(side="left",padx=(0,8))
  ttk.Button(actions,text="未処理に戻す",command=lambda:change("PENDING")).pack(side="left")
  def inspect_original():
   selected=tree.selection()
   if not selected:
    messagebox.showinfo("原本の確認","証憑を選択してください",parent=win);return
   info=self.s.receipt_custody_status(int(selected[0]))
   if info["status"]=="VERIFIED":
    messagebox.showinfo("原本の確認",f"原本を確認できる\nSHA-256: {info['sha256']}\n容量: {info['size_bytes']} bytes\n保存日時(UTC): {info['captured_utc']}\nローカル保存先: {info['stored_original']}\n\nこの照合は税務上の承認を意味しません。",parent=win)
   else:
    messagebox.showwarning("原本の確認",f"確認が必要：{info['reason']}\n原本の再確認が必要です。旧データを自動補完しません。",parent=win)
  ttk.Button(actions,text="原本の保存状態を確認",command=inspect_original).pack(side="left",padx=(8,0))
  populate()
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
  self.report.configure(state="normal");self.report.delete("1.0","end");self.report.insert("1.0","\n".join(t));self.report.configure(state="disabled");self.refresh_receipt_card()
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
    asset_class=simpledialog.askstring("減価償却","資産種類（例: 建物 / 建物附属設備 / 構築物 / 器具備品 / 車両運搬具）",initialvalue="器具備品")
    method=simpledialog.askstring("減価償却","定額法 または 定率法",initialvalue="定額法")
    use=simpledialog.askfloat("減価償却","事業使用割合（%）",initialvalue=100,minvalue=0,maxvalue=100)
    kwargs={"asset_class":asset_class or "その他"}
    if method=="定額法":
     kwargs["straight_line_rate"]=simpledialog.askfloat("定額法","国税庁の耐用年数別表の償却率（例 4年なら0.250）",minvalue=0)
    if method=="定率法":
     kwargs["declining_rate"]=simpledialog.askfloat("定率法","償却率（例 0.500）",minvalue=0)
     kwargs["revised_rate"]=simpledialog.askfloat("定率法","改定償却率",minvalue=0)
     kwargs["guarantee_rate"]=simpledialog.askfloat("定率法","保証率",minvalue=0)
    rows=jp_depreciation_schedule(cost,first,life,method=method,business_use_percent=use,through_year=date.today().year+life,**kwargs)
    lines=[f'{r["year"]}: {r["business_depreciation"]:,}円 / 月数 {r["months"]} / {r["method_note"]}' for r in rows[:12]]
    messagebox.showinfo("減価償却スケジュール","\n".join(lines)+"\n\n※税務上の方法・率・耐用年数は最新の国税庁資料と届出状況を確認してください。")
  except Exception as e:messagebox.showerror("計算エラー",str(e))
 def month_end_pack(self):
  d=date.today();year=simpledialog.askinteger("月末締めパック","年",initialvalue=d.year,minvalue=2000);month=simpledialog.askinteger("月末締めパック","月",initialvalue=d.month,minvalue=1,maxvalue=12)
  out=filedialog.askdirectory(title="月末締めパックの保存先")
  if not out or year is None or month is None:return
  try:
   result=export_month_end_package(self.s,year,month,out)
   msg=f'HTML: {result["html"]}\nCSV: {result["csv"]}\nJSON: {result["json"]}'
   msg+=f'\nPDF: {result["pdf"]}' if result["pdf_generated"] else "\nPDF: この環境では生成できませんでした（HTMLは保存済み）"
   messagebox.showinfo("月末締めパック",msg)
  except Exception as e:messagebox.showerror("月末締めパック",str(e))
 def export(self):
  x=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")])
  if x:self.s.export(x);messagebox.showinfo("CSV","出力しました")
 def open_budget(self):open_budget_window(self,self.s)
 def open_cash_movement(self):open_cash_movement_window(self,self.s)
 def close(self):self.s.close();self.destroy()
if __name__=="__main__":App().mainloop()
