from __future__ import annotations
import csv, os, sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

CATEGORIES=["Business income","Advertising","Car and truck expenses - review","Commissions and fees","Contract labor","Insurance","Interest","Legal and professional services","Office expense","Rent or lease","Repairs and maintenance","Supplies","Taxes and licenses - review","Travel - review","Meals - review","Utilities","Business use of home - review","Depreciation / Section 179 - review","Other expenses"]
DOCUMENT_TYPES=["Receipt","Invoice","Bank statement","Card statement","1099 form","Contract","Mileage/supporting record","Other"]
METHODS=("cash","accrual")
SUGGEST_RULES=[
 ("Advertising",["advertising","ad spend","google ads","meta ads","marketing"]),
 ("Car and truck expenses - review",["mileage","gas","fuel","parking","toll","vehicle","car"]),
 ("Commissions and fees",["commission","platform fee","merchant fee","processing fee","stripe","paypal"]),
 ("Contract labor",["contractor","freelancer","subcontractor","1099 contractor"]),
 ("Insurance",["insurance","premium"]),
 ("Legal and professional services",["lawyer","attorney","accountant","bookkeeper","cpa","legal"]),
 ("Office expense",["office","paper","printer","software subscription","stationery"]),
 ("Rent or lease",["rent","lease","coworking","office space"]),
 ("Repairs and maintenance",["repair","maintenance"]),
 ("Supplies",["supplies","materials","ink","toner","cable"]),
 ("Taxes and licenses - review",["license","permit","business tax","registration fee"]),
 ("Travel - review",["flight","hotel","travel","airfare","lodging"]),
 ("Meals - review",["meal","restaurant","lunch","dinner"]),
 ("Utilities",["electric","utility","internet","phone","water","gas"]),
 ("Business use of home - review",["home office","business use of home"]),
 ("Depreciation / Section 179 - review",["depreciation","section 179","capital asset","equipment purchase","fixed asset"]),
 ("Business income",["invoice paid","client payment","service revenue","sales","income"])
]

REVIEW_RULES={
 "Car and truck expenses - review":["Vehicle deductions require separate substantiation and method rules."],
 "Meals - review":["Business meals have special qualification and percentage rules; do not auto-deduct."],
 "Travel - review":["Travel requires business-purpose, tax-home and substantiation review."],
 "Business use of home - review":["Home-office rules have qualification tests and limitations."],
 "Depreciation / Section 179 - review":["Capitalization, depreciation and Section 179 require separate tax-year/entity review."],
 "Taxes and licenses - review":["Federal, state and local treatment varies; state/local requirements are outside automated scope."]
}
def review_requirements(category):
    return list(REVIEW_RULES.get(category,[]))

def suggest_category(text,kind="expense",limit=3):
    hay=(text or "").strip().lower()
    if not hay:return []
    out=[]
    for category,words in SUGGEST_RULES:
        if kind=="income" and category!="Business income":continue
        if kind=="expense" and category=="Business income":continue
        hits=[w for w in words if w in hay]
        if hits:
            out.append({"category":category,"confidence":round(min(0.95,0.55+0.12*len(hits)),2),"matched":hits,"requires_review":bool(review_requirements(category)),"review_reasons":review_requirements(category)})
    out.sort(key=lambda x:(-x["confidence"],x["category"]))
    return out[:max(1,int(limit))]
class LedgerError(ValueError): pass

def default_db_path():
    base=Path(os.environ.get("APPDATA") or (Path.home()/".local"/"share")); p=base/"USFreelanceLedger"; p.mkdir(parents=True,exist_ok=True); return p/"books.sqlite3"

def validate_date(v):
    try:return date.fromisoformat(v).isoformat()
    except ValueError as e: raise LedgerError("Date must use YYYY-MM-DD") from e

def usd_to_cents(v):
    try:d=Decimal(str(v))
    except (InvalidOperation,ValueError) as e: raise LedgerError("Invalid amount") from e
    if not d.is_finite() or d<=0: raise LedgerError("Amount must be positive")
    return int((d*100).quantize(Decimal("1"),rounding=ROUND_HALF_UP))

class Store:
    def __init__(self,path=None,accounting_method="cash"):
        if accounting_method not in METHODS: raise LedgerError("Accounting method must be cash or accrual")
        self.path=Path(path) if path else default_db_path(); self.path.parent.mkdir(parents=True,exist_ok=True)
        self.conn=sqlite3.connect(self.path); self.conn.row_factory=sqlite3.Row; self._schema()
        if self._meta("accounting_method") is None:self._set_meta("accounting_method",accounting_method)
    def _schema(self):
        self.conn.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS transactions(
          id INTEGER PRIMARY KEY AUTOINCREMENT, txn_date TEXT NOT NULL,
          kind TEXT NOT NULL CHECK(kind IN ('income','expense')), amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
          category TEXT NOT NULL, payer_payee TEXT NOT NULL DEFAULT '', document_type TEXT NOT NULL DEFAULT '',
          document_path TEXT NOT NULL DEFAULT '', memo TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT,action TEXT NOT NULL,entity_id INTEGER,detail TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        """); self.conn.commit()
    def _meta(self,k):
        r=self.conn.execute("SELECT value FROM meta WHERE key=?",(k,)).fetchone(); return r["value"] if r else None
    def _set_meta(self,k,v):
        self.conn.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,v)); self.conn.commit()
    @property
    def accounting_method(self):return self._meta("accounting_method") or "cash"
    def set_accounting_method(self,method):
        if method not in METHODS:raise LedgerError("Accounting method must be cash or accrual")
        if self.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]:raise LedgerError("Accounting method is locked after the first transaction")
        self._set_meta("accounting_method",method)
    def add(self,txn_date,kind,amount,category,payer_payee="",document_type="",document_path="",memo=""):
        txn_date=validate_date(txn_date)
        if kind not in {"income","expense"}:raise LedgerError("Type must be income or expense")
        if not category.strip():raise LedgerError("Category is required")
        cents=usd_to_cents(amount)
        with self.conn:
            cur=self.conn.execute("""INSERT INTO transactions(txn_date,kind,amount_cents,category,payer_payee,document_type,document_path,memo) VALUES(?,?,?,?,?,?,?,?)""",(txn_date,kind,cents,category.strip(),payer_payee.strip(),document_type.strip(),document_path.strip(),memo.strip()))
            i=int(cur.lastrowid); self.conn.execute("INSERT INTO audit_log(action,entity_id,detail) VALUES(?,?,?)",("ADD",i,f"{txn_date}|{kind}|{cents}|{category}"))
        return i
    def rows(self,limit=10000):
        return [dict(r) for r in self.conn.execute("SELECT * FROM transactions ORDER BY txn_date DESC,id DESC LIMIT ?",(min(max(int(limit),1),10000),)).fetchall()]
    def monthly(self,year,month):
        rows=self.conn.execute("SELECT kind,COALESCE(SUM(amount_cents),0) t FROM transactions WHERE txn_date LIKE ? GROUP BY kind",(f"{year:04d}-{month:02d}-%",)).fetchall()
        out={"income":0,"expense":0}
        for r in rows:out[r["kind"]]=int(r["t"])
        out["net"]=out["income"]-out["expense"];return out
    def annual_summary(self,year):
        rows=self.conn.execute("SELECT kind,COALESCE(SUM(amount_cents),0) t FROM transactions WHERE txn_date LIKE ? GROUP BY kind",(f"{year:04d}-%",)).fetchall()
        out={"income":0,"expense":0}
        for r in rows:out[r["kind"]]=int(r["t"])
        out["net"]=out["income"]-out["expense"]
        return out
    def schedule_c_prep_summary(self,year):
        rows=self.conn.execute("SELECT kind,category,SUM(amount_cents) t FROM transactions WHERE txn_date LIKE ? GROUP BY kind,category ORDER BY kind,category",(f"{year:04d}-%",)).fetchall()
        return [dict(r) for r in rows]
    def export_csv(self,target):
        target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
        with target.open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.writer(f);w.writerow(["date","type","amount_usd","category","payer_payee","document_type","document_reference","memo","accounting_method"])
            for r in reversed(self.rows()):w.writerow([r["txn_date"],r["kind"],f'{r["amount_cents"]/100:.2f}',r["category"],r["payer_payee"],r["document_type"],r["document_path"],r["memo"],self.accounting_method])
        return target
    def backup(self,target):
        target=Path(target);target.parent.mkdir(parents=True,exist_ok=True);d=sqlite3.connect(target)
        try:self.conn.backup(d)
        finally:d.close()
        return target
    def close(self):self.conn.close()
