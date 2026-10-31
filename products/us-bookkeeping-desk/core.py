from __future__ import annotations
import csv,os,re,sqlite3
from datetime import date
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
from pathlib import Path
TYPES=("asset","liability","equity","revenue","expense")
METHODS=("cash","accrual")
DEFAULT=[
("1000","Cash","asset"),("1100","Bank","asset"),("1200","Accounts Receivable","asset"),("1300","Inventory","asset"),("1500","Fixed Assets","asset"),
("2000","Accounts Payable","liability"),("2100","Accrued Liabilities","liability"),("3000","Owner Equity","equity"),("4000","Sales / Service Revenue","revenue"),("4100","Other Income","revenue"),
("5000","Cost of Goods Sold - review","expense"),("5100","Contract Labor","expense"),("5200","Rent Expense","expense"),("5300","Utilities","expense"),("5350","Vehicle Expense - review","expense"),("5400","Travel Expense - review","expense"),("5450","Meals Expense - review","expense"),("5500","Supplies Expense","expense"),("5600","Depreciation Expense - review","expense"),("5700","Taxes and Licenses - review","expense"),("5750","Business Use of Home - review","expense"),("5900","Other Expense","expense")]
SUGGEST_ENTRY_RULES=[
 (["rent","lease","office space"],"5200","1100","Rent Expense"),
 (["utility","utilities","internet","phone","electric","water","gas"],"5300","1100","Utilities"),
 (["travel","flight","hotel","airfare","lodging"],"5400","1100","Travel Expense - review"),
 (["mileage","vehicle","car","truck","gas","fuel","parking","toll"],"5350","1100","Vehicle Expense - review"),
 (["meal","restaurant","lunch","dinner"],"5450","1100","Meals Expense - review"),
 (["supply","supplies","paper","ink","toner","cable"],"5500","1100","Supplies Expense"),
 (["contractor","freelancer","subcontractor","contract labor"],"5100","1100","Contract Labor"),
 (["inventory","goods for resale","cost of goods"],"5000","1100","Cost of Goods Sold - review"),
 (["depreciation","section 179","capital asset","fixed asset"],"5600","1100","Depreciation Expense - review"),
 (["business tax","license","permit","registration fee"],"5700","1100","Taxes and Licenses - review"),
 (["home office","business use of home"],"5750","1100","Business Use of Home - review"),
 (["sale","client payment","service revenue","invoice paid","income"],"1100","4000","Sales / Service Revenue"),
]
REVIEW_ACCOUNT_RULES={
 "5000":["Inventory and cost-of-goods-sold treatment can depend on inventory and accounting rules."],
 "5350":["Vehicle deductions require substantiation and method-specific review."],
 "5400":["Travel requires business-purpose, tax-home and substantiation review."],
 "5450":["Business meals have special qualification and percentage rules."],
 "5600":["Capitalization, depreciation and Section 179 require tax-year/entity review."],
 "5700":["Federal/state/local tax and license treatment varies; state/local rules are not automated."],
 "5750":["Business-use-of-home deductions have qualification tests and limitations."]
}
def review_requirements_for_codes(codes):
 out=[]
 for code in codes:
  for msg in REVIEW_ACCOUNT_RULES.get(str(code),[]):
   if msg not in out:out.append(msg)
 return out

def suggest_entry(text):
 """Offer a reviewable candidate only when the local evidence is unambiguous."""
 hay=(text or "").strip().lower()
 if not hay:return None
 candidates=[]
 for words,debit,credit,label in SUGGEST_ENTRY_RULES:
  # Substrings are unsafe for financial categorization ("gas" in "Vegas").
  hits=[w for w in words if re.search(r"(?<![A-Za-z0-9])"+re.escape(w)+r"(?![A-Za-z0-9])",hay)]
  if hits:
   score=min(0.95,0.58+0.12*len(hits))
   candidates.append({"debit_code":debit,"credit_code":credit,"label":label,
                      "confidence":round(score,2),"matched":hits,
                      "review_reasons":review_requirements_for_codes([debit,credit])})
 candidates.sort(key=lambda item:(-item["confidence"],item["debit_code"],item["credit_code"]))
 # Equal top scores across different journal rules are not evidence of a reliable entry.
 if len(candidates)>1 and candidates[0]["confidence"]==candidates[1]["confidence"]:
  return None
 return candidates[0] if candidates else None
class BookError(ValueError):pass
def pth():
 b=Path(os.environ.get("APPDATA") or (Path.home()/".local"/"share"));p=b/"USBookkeepingDesk";p.mkdir(parents=True,exist_ok=True);return p/"books.sqlite3"
def vd(v):
 try:return date.fromisoformat(v).isoformat()
 except ValueError as e:raise BookError("Date must use YYYY-MM-DD") from e
def cents(v):
 if v in ("",None):return 0
 try:d=Decimal(str(v))
 except (InvalidOperation,ValueError) as e:raise BookError("Invalid amount") from e
 if not d.is_finite() or d<0:raise BookError("Amount must be non-negative")
 return int((d*100).quantize(Decimal("1"),rounding=ROUND_HALF_UP))
class Store:
 def __init__(self,path=None,method="cash"):
  if method not in METHODS:raise BookError("Accounting method must be cash or accrual")
  self.path=Path(path) if path else pth();self.path.parent.mkdir(parents=True,exist_ok=True);self.conn=sqlite3.connect(self.path);self.conn.row_factory=sqlite3.Row;self.schema();self.seed()
  if self.meta("accounting_method") is None:self.setmeta("accounting_method",method)
 def schema(self):
  self.conn.executescript("""PRAGMA foreign_keys=ON;
  CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE NOT NULL,name TEXT NOT NULL,type TEXT NOT NULL CHECK(type IN ('asset','liability','equity','revenue','expense')),active INTEGER NOT NULL DEFAULT 1);
  CREATE TABLE IF NOT EXISTS entries(id INTEGER PRIMARY KEY AUTOINCREMENT,entry_date TEXT NOT NULL,description TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
  CREATE TABLE IF NOT EXISTS lines(id INTEGER PRIMARY KEY AUTOINCREMENT,entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,account_id INTEGER NOT NULL REFERENCES accounts(id),debit_cents INTEGER NOT NULL DEFAULT 0 CHECK(debit_cents>=0),credit_cents INTEGER NOT NULL DEFAULT 0 CHECK(credit_cents>=0),CHECK((debit_cents>0 AND credit_cents=0) OR (credit_cents>0 AND debit_cents=0)));
  CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT,action TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);""");self.conn.commit()
 def seed(self):
  if self.conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]:return
  with self.conn:self.conn.executemany("INSERT INTO accounts(code,name,type) VALUES(?,?,?)",DEFAULT)
 def meta(self,k):
  r=self.conn.execute("SELECT value FROM meta WHERE key=?",(k,)).fetchone();return r["value"] if r else None
 def setmeta(self,k,v):
  self.conn.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,v));self.conn.commit()
 @property
 def accounting_method(self):return self.meta("accounting_method") or "cash"
 def set_method(self,m):
  if m not in METHODS:raise BookError("Accounting method must be cash or accrual")
  if self.conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]:raise BookError("Accounting method is locked after the first journal entry")
  self.setmeta("accounting_method",m)
 @property
 def locked(self):return self.meta("locked_through")
 def lock(self,d):
  d=vd(d);self.setmeta("locked_through",d);self.conn.execute("INSERT INTO audit_log(action,detail) VALUES('LOCK',?)",(d,));self.conn.commit()
 def accounts(self):return [dict(r) for r in self.conn.execute("SELECT * FROM accounts WHERE active=1 ORDER BY code")]
 def add_account(self,code,name,t):
  if not code.strip() or not name.strip() or t not in TYPES:raise BookError("Code, name and valid account type are required")
  try:
   with self.conn:c=self.conn.execute("INSERT INTO accounts(code,name,type) VALUES(?,?,?)",(code.strip(),name.strip(),t))
   return int(c.lastrowid)
  except sqlite3.IntegrityError as e:raise BookError("Account code already exists") from e
 def post(self,d,desc,lines):
  d=vd(d)
  if self.locked and d<=self.locked:raise BookError("Period is locked")
  if not desc.strip():raise BookError("Description is required")
  z=[];td=tc=0
  for code,deb,cred in lines:
   code=str(code).strip()
   if not code:continue
   a=self.conn.execute("SELECT id FROM accounts WHERE code=? AND active=1",(code,)).fetchone()
   if not a:raise BookError(f"Unknown account: {code}")
   db,cr=cents(deb),cents(cred)
   if (db>0)==(cr>0):raise BookError("Each line must have either a debit or a credit")
   td+=db;tc+=cr;z.append((int(a["id"]),db,cr))
  if len(z)<2 or td<=0 or td!=tc:raise BookError("Debits and credits must balance")
  with self.conn:
   c=self.conn.execute("INSERT INTO entries(entry_date,description) VALUES(?,?)",(d,desc.strip()));eid=int(c.lastrowid)
   self.conn.executemany("INSERT INTO lines(entry_id,account_id,debit_cents,credit_cents) VALUES(?,?,?,?)",[(eid,*x) for x in z])
   self.conn.execute("INSERT INTO audit_log(action,detail) VALUES('POST',?)",(f"{eid}|{d}|{td}|{desc}",))
  return eid
 def journal(self):
  return [dict(r) for r in self.conn.execute("""SELECT e.id,e.entry_date,e.description,a.code,a.name,a.type,l.debit_cents,l.credit_cents FROM entries e JOIN lines l ON l.entry_id=e.id JOIN accounts a ON a.id=l.account_id ORDER BY e.entry_date DESC,e.id DESC,l.id""")]
 def trial(self):
  return [dict(r) for r in self.conn.execute("""SELECT a.code,a.name,a.type,COALESCE(SUM(l.debit_cents),0) debit,COALESCE(SUM(l.credit_cents),0) credit FROM accounts a LEFT JOIN lines l ON l.account_id=a.id WHERE a.active=1 GROUP BY a.id ORDER BY a.code""")]
 def pnl(self):
  rev=exp=0
  for r in self.trial():
   if r["type"]=="revenue":rev+=r["credit"]-r["debit"]
   if r["type"]=="expense":exp+=r["debit"]-r["credit"]
  return {"revenue":rev,"expense":exp,"net_income":rev-exp}
 def balance_check(self):
  rows=self.trial();debits=sum(int(r["debit"]) for r in rows);credits=sum(int(r["credit"]) for r in rows)
  return {"debits":debits,"credits":credits,"balanced":debits==credits,"difference":debits-credits}
 def bs(self):
  a=l=e=0
  for r in self.trial():
   if r["type"]=="asset":a+=r["debit"]-r["credit"]
   if r["type"]=="liability":l+=r["credit"]-r["debit"]
   if r["type"]=="equity":e+=r["credit"]-r["debit"]
  ni=self.pnl()["net_income"];return {"assets":a,"liabilities":l,"equity":e,"current_income":ni,"liabilities_and_equity":l+e+ni}
 def ledger(self,code):
  return [dict(r) for r in self.conn.execute("""SELECT e.entry_date,e.description,l.debit_cents,l.credit_cents FROM lines l JOIN entries e ON e.id=l.entry_id JOIN accounts a ON a.id=l.account_id WHERE a.code=? ORDER BY e.entry_date,e.id,l.id""",(code,))]
 def export(self,target):
  target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
  with target.open("w",encoding="utf-8-sig",newline="") as f:
   w=csv.writer(f);w.writerow(["date","description","account_code","account","debit_usd","credit_usd","accounting_method"])
   for r in reversed(self.journal()):w.writerow([r["entry_date"],r["description"],r["code"],r["name"],f'{r["debit_cents"]/100:.2f}',f'{r["credit_cents"]/100:.2f}',self.accounting_method])
  return target
 def close(self):self.conn.close()
