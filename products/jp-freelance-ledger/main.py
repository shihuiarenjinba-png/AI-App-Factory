import tkinter as tk
from datetime import date
from tkinter import filedialog,messagebox,ttk
from core import CATEGORIES,DOCUMENT_TYPES,LedgerError,Store

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("個人事業帳簿ローカル"); self.geometry("1100x720"); self.minsize(900,620)
        self.store=Store(); self.protocol("WM_DELETE_WINDOW",self.close)
        self.v={k:tk.StringVar() for k in ["date","kind","amount","category","counterparty","doctype","docpath","memo"]}
        self.v["date"].set(date.today().isoformat()); self.v["kind"].set("収入"); self.v["category"].set(CATEGORIES[0]); self.v["doctype"].set(DOCUMENT_TYPES[0])
        self.summary=tk.StringVar(); self.build(); self.refresh()
    def build(self):
        ttk.Label(self,text="個人事業帳簿ローカル",font=("Yu Gothic UI",18,"bold")).pack(anchor="w",padx=14,pady=(14,2))
        ttk.Label(self,text="日本国内向け・円建て・完全ローカル保存。税額計算や申告可否の判定は行いません。").pack(anchor="w",padx=14)
        p=ttk.Panedwindow(self,orient="horizontal"); p.pack(fill="both",expand=True,padx=14,pady=10)
        f=ttk.Labelframe(p,text="取引入力",padding=10); p.add(f,weight=1)
        fields=[("取引日","date"),("金額（円）","amount"),("取引先","counterparty"),("摘要","memo"),("証憑参照","docpath")]
        ttk.Label(f,text="種別").grid(row=0,column=0,sticky="w"); ttk.Combobox(f,textvariable=self.v["kind"],values=["収入","経費"],state="readonly").grid(row=0,column=1,sticky="ew",pady=3)
        ttk.Label(f,text="勘定科目").grid(row=1,column=0,sticky="w"); ttk.Combobox(f,textvariable=self.v["category"],values=CATEGORIES,state="readonly").grid(row=1,column=1,sticky="ew",pady=3)
        ttk.Label(f,text="証憑種別").grid(row=2,column=0,sticky="w"); ttk.Combobox(f,textvariable=self.v["doctype"],values=DOCUMENT_TYPES,state="readonly").grid(row=2,column=1,sticky="ew",pady=3)
        for i,(label,key) in enumerate(fields,start=3):
            ttk.Label(f,text=label).grid(row=i,column=0,sticky="w"); ttk.Entry(f,textvariable=self.v[key]).grid(row=i,column=1,sticky="ew",pady=3)
        ttk.Button(f,text="証憑ファイルを参照",command=self.pick).grid(row=8,column=0,columnspan=2,sticky="ew",pady=4)
        ttk.Button(f,text="記帳する",command=self.add).grid(row=9,column=0,columnspan=2,sticky="ew",pady=4)
        ttk.Button(f,text="CSV出力",command=self.export).grid(row=10,column=0,sticky="ew",pady=4)
        ttk.Button(f,text="帳簿バックアップ",command=self.backup).grid(row=10,column=1,sticky="ew",pady=4); f.columnconfigure(1,weight=1)
        r=ttk.Labelframe(p,text="帳簿",padding=10); p.add(r,weight=3); ttk.Label(r,textvariable=self.summary,font=("Yu Gothic UI",11,"bold")).pack(anchor="w")
        cols=("date","kind","amount","category","counterparty","memo"); self.tree=ttk.Treeview(r,columns=cols,show="headings")
        for c,t in zip(cols,["日付","種別","金額","勘定科目","取引先","摘要"]): self.tree.heading(c,text=t); self.tree.column(c,width=120)
        self.tree.pack(fill="both",expand=True,pady=(8,0))
    def pick(self):
        x=filedialog.askopenfilename(title="領収書・請求書などを選択"); 
        if x:self.v["docpath"].set(x)
    def add(self):
        try:self.store.add(self.v["date"].get(),self.v["kind"].get(),self.v["amount"].get(),self.v["category"].get(),self.v["counterparty"].get(),self.v["doctype"].get(),self.v["docpath"].get(),self.v["memo"].get())
        except LedgerError as e: messagebox.showerror("入力エラー",str(e)); return
        for k in ["amount","counterparty","docpath","memo"]: self.v[k].set("")
        self.refresh()
    def refresh(self):
        for i in self.tree.get_children():self.tree.delete(i)
        for r in self.store.rows(): self.tree.insert("","end",values=(r["txn_date"],r["kind"],f'{r["amount_yen"]:,}',r["category"],r["counterparty"],r["memo"]))
        d=date.today(); s=self.store.monthly(d.year,d.month); self.summary.set(f"{d.year}年{d.month}月　収入 {s['収入']:,}円　経費 {s['経費']:,}円　差引 {s['差引']:,}円")
    def export(self):
        x=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")])
        if x:self.store.export_csv(x); messagebox.showinfo("CSV","出力しました")
    def backup(self):
        x=filedialog.asksaveasfilename(defaultextension=".sqlite3",filetypes=[("SQLite","*.sqlite3")])
        if x:self.store.backup(x); messagebox.showinfo("バックアップ","作成しました")
    def close(self):self.store.close();self.destroy()
if __name__=="__main__":App().mainloop()
