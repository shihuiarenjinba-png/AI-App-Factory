from __future__ import annotations
import csv, os, sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

CATEGORIES = ["売上高","仕入高","外注工賃","給料賃金","減価償却費","貸倒金","地代家賃","利子割引料","租税公課","荷造運賃","水道光熱費","旅費交通費","通信費","広告宣伝費","接待交際費","損害保険料","修繕費","消耗品費","福利厚生費","雑費","その他"]
DOCUMENT_TYPES = ["領収書","請求書","レシート","契約書","振込記録","通帳・明細","その他"]
class LedgerError(ValueError): pass

def default_db_path():
    base=Path(os.environ.get("APPDATA") or (Path.home()/".local"/"share"))
    p=base/"JPFreelanceLedger"; p.mkdir(parents=True,exist_ok=True); return p/"books.sqlite3"

def validate_date(v):
    try: return date.fromisoformat(v).isoformat()
    except ValueError as e: raise LedgerError("日付はYYYY-MM-DD形式で入力してください") from e

def yen_to_int(v):
    try: d=Decimal(str(v))
    except (InvalidOperation,ValueError) as e: raise LedgerError("金額が正しくありません") from e
    if not d.is_finite() or d<=0: raise LedgerError("金額は1円以上にしてください")
    return int(d.quantize(Decimal("1"),rounding=ROUND_HALF_UP))

class Store:
    def __init__(self,path=None):
        self.path=Path(path) if path else default_db_path(); self.path.parent.mkdir(parents=True,exist_ok=True)
        self.conn=sqlite3.connect(self.path); self.conn.row_factory=sqlite3.Row; self._schema()
    def _schema(self):
        self.conn.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS transactions(
          id INTEGER PRIMARY KEY AUTOINCREMENT, txn_date TEXT NOT NULL,
          kind TEXT NOT NULL CHECK(kind IN ('収入','経費')), amount_yen INTEGER NOT NULL CHECK(amount_yen>0),
          category TEXT NOT NULL, counterparty TEXT NOT NULL DEFAULT '', document_type TEXT NOT NULL DEFAULT '',
          document_path TEXT NOT NULL DEFAULT '', memo TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS audit_log(
          id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, entity_id INTEGER,
          detail TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        """); self.conn.commit()
    def add(self,txn_date,kind,amount,category,counterparty="",document_type="",document_path="",memo=""):
        txn_date=validate_date(txn_date)
        if kind not in {"収入","経費"}: raise LedgerError("種別が不正です")
        if not category.strip(): raise LedgerError("勘定科目を選択してください")
        amount_yen=yen_to_int(amount)
        with self.conn:
            cur=self.conn.execute("""INSERT INTO transactions(txn_date,kind,amount_yen,category,counterparty,document_type,document_path,memo)
            VALUES(?,?,?,?,?,?,?,?)""",(txn_date,kind,amount_yen,category.strip(),counterparty.strip(),document_type.strip(),document_path.strip(),memo.strip()))
            i=int(cur.lastrowid)
            self.conn.execute("INSERT INTO audit_log(action,entity_id,detail) VALUES(?,?,?)",("ADD",i,f"{txn_date}|{kind}|{amount_yen}|{category}"))
        return i
    def rows(self,limit=10000):
        return [dict(r) for r in self.conn.execute("SELECT * FROM transactions ORDER BY txn_date DESC,id DESC LIMIT ?",(min(max(int(limit),1),10000),)).fetchall()]
    def monthly(self,year,month):
        rows=self.conn.execute("SELECT kind,COALESCE(SUM(amount_yen),0) t FROM transactions WHERE txn_date LIKE ? GROUP BY kind",(f"{year:04d}-{month:02d}-%",)).fetchall()
        out={"収入":0,"経費":0}
        for r in rows: out[r["kind"]]=int(r["t"])
        out["差引"]=out["収入"]-out["経費"]; return out
    def annual_category_summary(self,year):
        rows=self.conn.execute("SELECT kind,category,SUM(amount_yen) t FROM transactions WHERE txn_date LIKE ? GROUP BY kind,category ORDER BY kind,category",(f"{year:04d}-%",)).fetchall()
        return [dict(r) for r in rows]
    def export_csv(self,target):
        target=Path(target); target.parent.mkdir(parents=True,exist_ok=True)
        with target.open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.writer(f); w.writerow(["取引日","種別","金額(円)","勘定科目","取引先","証憑種別","証憑参照","摘要"])
            for r in reversed(self.rows()): w.writerow([r["txn_date"],r["kind"],r["amount_yen"],r["category"],r["counterparty"],r["document_type"],r["document_path"],r["memo"]])
        return target
    def backup(self,target):
        target=Path(target); target.parent.mkdir(parents=True,exist_ok=True); d=sqlite3.connect(target)
        try: self.conn.backup(d)
        finally: d.close()
        return target
    def close(self): self.conn.close()
