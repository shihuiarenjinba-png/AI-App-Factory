from __future__ import annotations
import csv, os, sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

CATEGORIES = ["売上高","受取手数料","雑収入","仕入高","外注工賃","給料賃金","専従者給与","法定福利費","福利厚生費","地代家賃","水道光熱費","旅費交通費","通信費","広告宣伝費","接待交際費","損害保険料","修繕費","消耗品費","租税公課","荷造運賃","支払手数料","新聞図書費","会議費","車両費","研修費","ソフトウェア利用料","リース料","減価償却費","貸倒金","利子割引料","雑費","その他"]
DOCUMENT_TYPES = ["領収書","請求書","レシート","契約書","振込記録","通帳・明細","その他"]

SUGGEST_RULES = [
    ("通信費", ["通信", "携帯", "スマホ", "電話", "internet", "wifi", "回線", "プロバイダ"]),
    ("旅費交通費", ["電車", "バス", "タクシー", "交通", "新幹線", "航空", "ホテル", "宿泊", "出張"]),
    ("地代家賃", ["家賃", "賃料", "オフィス", "事務所", "コワーキング"]),
    ("広告宣伝費", ["広告", "ad", "宣伝", "google ads", "meta ads", "チラシ"]),
    ("外注工賃", ["外注", "業務委託", "freelance", "請負"]),
    ("消耗品費", ["文具", "インク", "トナー", "ケーブル", "備品", "消耗品"]),
    ("支払手数料", ["手数料", "決済", "振込手数料", "stripe", "paypal"]),
    ("水道光熱費", ["電気", "水道", "ガス", "光熱"]),
    ("接待交際費", ["会食", "接待", "贈答", "手土産"]),
    ("損害保険料", ["保険", "insurance"]),
    ("修繕費", ["修理", "修繕", "repair"]),
    ("租税公課", ["印紙", "登録免許", "事業税", "固定資産税"]),
    ("売上高", ["売上", "報酬", "請求", "入金", "制作料", "業務報酬", "service fee"]),
]

def suggest_category(text, kind="経費", limit=3):
    hay=(text or "").strip().lower()
    if not hay:
        return []
    scored=[]
    for category, words in SUGGEST_RULES:
        if kind=="収入" and category!="売上高":
            continue
        if kind=="経費" and category=="売上高":
            continue
        hits=[w for w in words if w.lower() in hay]
        if hits:
            score=min(0.95, 0.55 + 0.12*len(hits))
            scored.append({"category":category,"confidence":round(score,2),"matched":hits})
    scored.sort(key=lambda x:(-x["confidence"], x["category"]))
    return scored[:max(1,int(limit))]
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
    def annual_summary(self,year):
        rows=self.conn.execute("SELECT kind,COALESCE(SUM(amount_yen),0) t FROM transactions WHERE txn_date LIKE ? GROUP BY kind",(f"{year:04d}-%",)).fetchall()
        out={"収入":0,"経費":0}
        for r in rows: out[r["kind"]]=int(r["t"])
        out["差引"]=out["収入"]-out["経費"]
        return out
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
