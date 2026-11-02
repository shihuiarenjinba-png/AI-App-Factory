from __future__ import annotations
import csv,os,sqlite3
from datetime import date
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
from pathlib import Path
try:
 from receipt_event_history import ReceiptHistory
except ModuleNotFoundError:
 import importlib.util as _history_importlib
 import sys as _history_sys
 _history_path=Path(__file__).with_name("receipt_event_history.py")
 _history_spec=_history_importlib.spec_from_file_location(f"{__name__}_receipt_event_history",_history_path)
 _history_module=_history_importlib.module_from_spec(_history_spec)
 _history_sys.modules[_history_spec.name]=_history_module
 _history_spec.loader.exec_module(_history_module)
 ReceiptHistory=_history_module.ReceiptHistory
try:
 from receipt_custody import ReceiptCustody, CustodyError
except ModuleNotFoundError:
 import importlib.util as _custody_importlib
 import sys as _custody_sys
 _custody_path=Path(__file__).with_name("receipt_custody.py")
 _custody_spec=_custody_importlib.spec_from_file_location(f"{__name__}_receipt_custody",_custody_path)
 _custody_module=_custody_importlib.module_from_spec(_custody_spec)
 _custody_sys.modules[_custody_spec.name]=_custody_module
 _custody_spec.loader.exec_module(_custody_module)
 ReceiptCustody=_custody_module.ReceiptCustody
 CustodyError=_custody_module.CustodyError
try:
    from account_catalog import ACCOUNT_CATALOG,BOOK_GUIDE
except ModuleNotFoundError:
    import importlib.util as _importlib_util
    import sys as _sys
    _catalog_path=Path(__file__).with_name("account_catalog.py")
    _spec=_importlib_util.spec_from_file_location(f"{__name__}_account_catalog",_catalog_path)
    _mod=_importlib_util.module_from_spec(_spec)
    _sys.modules[_spec.name]=_mod
    _spec.loader.exec_module(_mod)
    ACCOUNT_CATALOG=_mod.ACCOUNT_CATALOG
    BOOK_GUIDE=_mod.BOOK_GUIDE
TYPES=("資産","負債","純資産","収益","費用")
DEFAULT=[
("1000","現金","資産"),("1010","小口現金","資産"),("1100","普通預金","資産"),("1110","当座預金","資産"),("1120","定期預金","資産"),
("1200","売掛金","資産"),("1210","未収入金","資産"),("1220","立替金","資産"),("1230","仮払金","資産"),("1240","前払費用","資産"),
("1300","棚卸資産","資産"),("1310","商品","資産"),("1320","原材料","資産"),("1330","仕掛品","資産"),("1400","短期貸付金","資産"),
("1500","固定資産","資産"),("1510","建物","資産"),("1520","建物附属設備","資産"),("1530","構築物","資産"),("1540","機械装置","資産"),
("1550","車両運搬具","資産"),("1560","工具器具備品","資産"),("1570","ソフトウェア","資産"),("1580","一括償却資産","資産"),("1590","減価償却累計額","資産"),
("1600","敷金保証金","資産"),("1610","長期前払費用","資産"),
("2000","買掛金","負債"),("2010","未払金","負債"),("2020","未払費用","負債"),("2030","預り金","負債"),("2040","仮受金","負債"),
("2050","前受金","負債"),("2060","短期借入金","負債"),("2100","長期借入金","負債"),("2110","未払消費税等","負債"),
("3000","元入金","純資産"),("3010","事業主貸","純資産"),("3020","事業主借","純資産"),
("4000","売上高","収益"),("4010","受取手数料","収益"),("4020","受取利息","収益"),("4030","雑収入","収益"),
("4100","その他収益","収益"),
("5000","仕入高","費用"),("5010","期首商品棚卸高","費用"),("5020","期末商品棚卸高","費用"),
("5100","外注工賃","費用"),("5110","給料賃金","費用"),("5120","法定福利費","費用"),("5130","福利厚生費","費用"),
("5200","地代家賃","費用"),("5210","水道光熱費","費用"),("5220","広告宣伝費","費用"),("5230","接待交際費","費用"),("5240","損害保険料","費用"),
("5250","修繕費","費用"),("5260","租税公課","費用"),("5270","支払手数料","費用"),("5280","新聞図書費","費用"),("5290","会議費","費用"),
("5300","通信費","費用"),("5310","荷造運賃","費用"),("5320","車両費","費用"),("5330","研修費","費用"),("5340","ソフトウェア利用料","費用"),
("5350","リース料","費用"),("5360","貸倒金","費用"),("5370","利子割引料","費用"),("5380","専従者給与","費用"),
("5400","旅費交通費","費用"),("5500","消耗品費","費用"),("5600","減価償却費","費用"),("5900","雑費","費用")
]
SUGGEST_ENTRY_RULES=[
 (["家賃","賃料","オフィス"],"5200","1100","地代家賃"),
 (["通信","携帯","電話","回線","インターネット"],"5300","1100","通信費"),
 (["電車","バス","タクシー","交通","出張"],"5400","1100","旅費交通費"),
 (["文具","備品","消耗品","インク","トナー"],"5500","1100","消耗品費"),
 (["外注","業務委託"],"5100","1100","外注工賃"),
 (["仕入","商品購入"],"5000","1100","仕入高"),
 (["売上","入金","報酬","請求"],"1100","4000","売上高"),
]
def suggest_entry(text):
 hay=(text or "").strip().lower()
 if not hay:return None
 best=None
 for words,debit,credit,label in SUGGEST_ENTRY_RULES:
  hits=[w for w in words if w.lower() in hay]
  if hits:
   score=min(0.95,0.58+0.12*len(hits))
   cand={"debit_code":debit,"credit_code":credit,"label":label,"confidence":round(score,2),"matched":hits}
   if best is None or cand["confidence"]>best["confidence"]:best=cand
 return best
class BookError(ValueError):pass
def pth():
 b=Path(os.environ.get("APPDATA") or (Path.home()/".local"/"share"));p=b/"JPBookkeepingDesk";p.mkdir(parents=True,exist_ok=True);return p/"books.sqlite3"
def vd(v):
 try:return date.fromisoformat(v).isoformat()
 except ValueError as e:raise BookError("日付はYYYY-MM-DD形式で入力してください") from e
def y(v):
 if v in ("",None):return 0
 try:d=Decimal(str(v))
 except (InvalidOperation,ValueError) as e:raise BookError("金額が正しくありません") from e
 if not d.is_finite() or d<0:raise BookError("金額は0以上にしてください")
 return int(d.quantize(Decimal("1"),rounding=ROUND_HALF_UP))
class Store:
 def __init__(self,path=None):
  self.path=Path(path) if path else pth();self.path.parent.mkdir(parents=True,exist_ok=True);self.conn=sqlite3.connect(self.path);self.conn.row_factory=sqlite3.Row;self.schema();self.seed();self.seed_help();self.receipt_history=ReceiptHistory(self.conn);self.receipt_custody=ReceiptCustody(self.conn,self.path)
 def schema(self):
  self.conn.executescript("""PRAGMA foreign_keys=ON;
  CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE NOT NULL,name TEXT NOT NULL,type TEXT NOT NULL CHECK(type IN ('資産','負債','純資産','収益','費用')),active INTEGER NOT NULL DEFAULT 1);
  CREATE TABLE IF NOT EXISTS entries(id INTEGER PRIMARY KEY AUTOINCREMENT,entry_date TEXT NOT NULL,description TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
  CREATE TABLE IF NOT EXISTS lines(id INTEGER PRIMARY KEY AUTOINCREMENT,entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,account_id INTEGER NOT NULL REFERENCES accounts(id),debit_yen INTEGER NOT NULL DEFAULT 0 CHECK(debit_yen>=0),credit_yen INTEGER NOT NULL DEFAULT 0 CHECK(credit_yen>=0),CHECK((debit_yen>0 AND credit_yen=0) OR (credit_yen>0 AND debit_yen=0)));
  CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT,action TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
  CREATE TABLE IF NOT EXISTS account_help(code TEXT PRIMARY KEY,name TEXT NOT NULL,type TEXT NOT NULL,audience TEXT NOT NULL,use_text TEXT NOT NULL,books TEXT NOT NULL,keywords TEXT NOT NULL,example TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS book_help(book TEXT PRIMARY KEY,purpose TEXT NOT NULL,keywords TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS receipt_queue(id INTEGER PRIMARY KEY AUTOINCREMENT,file_path TEXT NOT NULL UNIQUE,status TEXT NOT NULL DEFAULT 'PENDING',suggested_entry TEXT NOT NULL DEFAULT '',note TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);""");self.conn.commit()
 def seed(self):
  if self.conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]:return
  with self.conn:self.conn.executemany("INSERT INTO accounts(code,name,type) VALUES(?,?,?)",DEFAULT)
 def seed_help(self):
  with self.conn:
   for a in ACCOUNT_CATALOG:self.conn.execute("INSERT OR REPLACE INTO account_help(code,name,type,audience,use_text,books,keywords,example) VALUES(?,?,?,?,?,?,?,?)",(a["code"],a["name"],a["type"],a["audience"],a["use"]," / ".join(a["books"])," / ".join(a["keywords"]),a["example"]))
   for b in BOOK_GUIDE:self.conn.execute("INSERT OR REPLACE INTO book_help(book,purpose,keywords) VALUES(?,?,?)",(b["book"],b["purpose"]," / ".join(b["keywords"])))
 def search_help(self,q,limit=8,include_advanced=True):
  q=(q or "").strip()
  if not q:return []
  like=f"%{q}%";sql="SELECT code,name,type,audience,use_text,books,keywords,example FROM account_help WHERE (name LIKE ? OR use_text LIKE ? OR keywords LIKE ? OR example LIKE ? OR books LIKE ?)"
  args=[like]*5
  if not include_advanced:sql+=" AND audience!='advanced'"
  sql+=" ORDER BY CASE WHEN name=? THEN 0 WHEN name LIKE ? THEN 1 ELSE 2 END, code LIMIT ?";args.extend([q,like,max(1,min(int(limit),30))])
  return [dict(r) for r in self.conn.execute(sql,args)]
 def search_book_help(self,q,limit=5):
  q=(q or "").strip()
  if not q:return []
  like=f"%{q}%";return [dict(r) for r in self.conn.execute("SELECT book,purpose,keywords FROM book_help WHERE book LIKE ? OR purpose LIKE ? OR keywords LIKE ? ORDER BY book LIMIT ?",(like,like,like,max(1,min(int(limit),20))))]
 def enqueue_receipts(self,paths,at=None,preserve_source=False):
  """New GUI ingestion preserves original bytes; legacy path-only calls remain review-only."""
  n=0
  for p in paths:
   p=str(p).strip()
   if p:
    try:
     if preserve_source:
      _,added=self.receipt_custody.capture(p,self.receipt_history,at=at)
     else:
      _,added=self.receipt_history.add(p,at=at)
    except (ValueError,OSError) as e:raise BookError(str(e)) from e
    n+=int(added)
  return n
 def receipt_custody_status(self,receipt_id):
  return self.receipt_custody.verify(receipt_id)
 def receipt_custody_summary(self):
  rows=[(r,self.receipt_custody_status(r["id"])) for r in self.receipts()]
  return {"verified":sum(x["status"]=="VERIFIED" for _,x in rows),
          "review_required":sum(x["status"]!="VERIFIED" for _,x in rows),
          "details":[{"id":r["id"],"file_path":r["file_path"],**x} for r,x in rows]}
 def receipts(self):
  return [dict(r) for r in self.conn.execute(
   "SELECT id,file_path,status,created_at FROM receipt_queue ORDER BY id")]
 def set_receipt_status(self,receipt_id,status,at=None):
  """Manual receipt queue state only; does not post a journal or approve tax."""
  try:return self.receipt_history.transition(int(receipt_id),status,at=at)
  except (ValueError,TypeError) as e:raise BookError(str(e)) from e
 def receipt_month_end(self,year,month):
  return self.receipt_history.replay(year,month)
 def accounts(self):return [dict(r) for r in self.conn.execute("SELECT * FROM accounts WHERE active=1 ORDER BY code")]
 def add_account(self,code,name,t):
  if not code.strip() or not name.strip() or t not in TYPES:raise BookError("科目コード・名称・区分を確認してください")
  try:
   with self.conn:c=self.conn.execute("INSERT INTO accounts(code,name,type) VALUES(?,?,?)",(code.strip(),name.strip(),t))
   return int(c.lastrowid)
  except sqlite3.IntegrityError as e:raise BookError("同じ科目コードがあります") from e
 @property
 def locked(self):
  r=self.conn.execute("SELECT value FROM meta WHERE key='locked_through'").fetchone();return r["value"] if r else None
 def lock(self,d):
  d=vd(d);self.conn.execute("INSERT INTO meta(key,value) VALUES('locked_through',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(d,));self.conn.execute("INSERT INTO audit_log(action,detail) VALUES('LOCK',?)",(d,));self.conn.commit()
 def post(self,d,desc,lines):
  d=vd(d)
  if self.locked and d<=self.locked:raise BookError("締め済み期間には記帳できません")
  if not desc.strip():raise BookError("摘要を入力してください")
  z=[];td=tc=0
  for code,deb,cred in lines:
   code=str(code).strip()
   if not code:continue
   a=self.conn.execute("SELECT id FROM accounts WHERE code=? AND active=1",(code,)).fetchone()
   if not a:raise BookError(f"勘定科目がありません: {code}")
   db,cr=y(deb),y(cred)
   if (db>0)==(cr>0):raise BookError("各行は借方または貸方のどちらか一方を入力してください")
   td+=db;tc+=cr;z.append((int(a["id"]),db,cr))
  if len(z)<2 or td<=0 or td!=tc:raise BookError("借方合計と貸方合計を一致させてください")
  # A finalized bank statement is a historical control point. Backdated
  # bank postings must not silently change its underlying ledger balance.
  # Non-bank corrections remain possible, subject to the ordinary period lock.
  if self.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bank_statements'").fetchone():
   for account_id,_,_ in z:
    closed=self.conn.execute(
     "SELECT 1 FROM bank_statements WHERE account_id=? AND status='FINALIZED' AND statement_date>=? LIMIT 1",
     (account_id,d)).fetchone()
    if closed:
     raise BookError("銀行照合確定済みの期間には預金仕訳を追加できません。後日付の訂正仕訳で処理してください")
  with self.conn:
   c=self.conn.execute("INSERT INTO entries(entry_date,description) VALUES(?,?)",(d,desc.strip()));eid=int(c.lastrowid)
   self.conn.executemany("INSERT INTO lines(entry_id,account_id,debit_yen,credit_yen) VALUES(?,?,?,?)",[(eid,*x) for x in z])
   self.conn.execute("INSERT INTO audit_log(action,detail) VALUES('POST',?)",(f"{eid}|{d}|{td}|{desc}",))
  return eid
 def journal(self):
  return [dict(r) for r in self.conn.execute("""SELECT e.id,e.entry_date,e.description,a.code,a.name,a.type,l.debit_yen,l.credit_yen FROM entries e JOIN lines l ON l.entry_id=e.id JOIN accounts a ON a.id=l.account_id ORDER BY e.entry_date DESC,e.id DESC,l.id""")]
 def trial(self):
  return [dict(r) for r in self.conn.execute("""SELECT a.code,a.name,a.type,COALESCE(SUM(l.debit_yen),0) debit,COALESCE(SUM(l.credit_yen),0) credit FROM accounts a LEFT JOIN lines l ON l.account_id=a.id WHERE a.active=1 GROUP BY a.id ORDER BY a.code""")]
 def pnl(self):
  rev=exp=0
  for r in self.trial():
   if r["type"]=="収益":rev+=r["credit"]-r["debit"]
   if r["type"]=="費用":exp+=r["debit"]-r["credit"]
  return {"収益":rev,"費用":exp,"利益":rev-exp}
 def balance_check(self):
  rows=self.trial();debits=sum(int(r["debit"]) for r in rows);credits=sum(int(r["credit"]) for r in rows)
  return {"debits":debits,"credits":credits,"balanced":debits==credits,"difference":debits-credits}
 def bs(self):
  a=l=e=0
  for r in self.trial():
   if r["type"]=="資産":a+=r["debit"]-r["credit"]
   if r["type"]=="負債":l+=r["credit"]-r["debit"]
   if r["type"]=="純資産":e+=r["credit"]-r["debit"]
  ni=self.pnl()["利益"];return {"資産":a,"負債":l,"純資産":e,"当期利益":ni,"負債純資産合計":l+e+ni}
 def ledger(self,code):
  return [dict(r) for r in self.conn.execute("""SELECT e.entry_date,e.description,l.debit_yen,l.credit_yen FROM lines l JOIN entries e ON e.id=l.entry_id JOIN accounts a ON a.id=l.account_id WHERE a.code=? ORDER BY e.entry_date,e.id,l.id""",(code,))]
 def export(self,target):
  target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
  with target.open("w",encoding="utf-8-sig",newline="") as f:
   w=csv.writer(f);w.writerow(["日付","摘要","科目コード","勘定科目","借方","貸方"])
   for r in reversed(self.journal()):w.writerow([r["entry_date"],r["description"],r["code"],r["name"],r["debit_yen"],r["credit_yen"]])
  return target
 def close(self):self.conn.close()
