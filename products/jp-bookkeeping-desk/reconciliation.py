"""JPY bank statement reconciliation; never auto-posts journal or tax adjustments."""
from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation

BANK_ACCOUNT_CODES=frozenset({"1100","1110","1120"})
MAX_YEN=2**63-1

class ReconciliationError(ValueError):pass

def _yen(value):
    if isinstance(value,bool):raise ReconciliationError("残高は整数円で入力してください")
    try: n=Decimal(str(value))
    except (InvalidOperation,ValueError) as exc:raise ReconciliationError("残高が不正です") from exc
    if not n.is_finite() or n!=n.to_integral_value() or abs(n)>MAX_YEN:
        raise ReconciliationError("残高は範囲内の整数円にしてください")
    return int(n)

def _date(value):
    try:return date.fromisoformat(value).isoformat()
    except (TypeError,ValueError) as exc:raise ReconciliationError("日付はYYYY-MM-DD形式で入力してください") from exc

class BankReconciler:
    """Persistent, non-posting reconciliation attached to the existing JP Store."""
    def __init__(self,store):
        self.store=store
        self.db=store.conn
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS bank_statements(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          account_id INTEGER NOT NULL REFERENCES accounts(id),
          statement_date TEXT NOT NULL,
          opening_yen INTEGER NOT NULL,
          closing_yen INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','FINALIZED')),
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          finalized_at TEXT,
          UNIQUE(account_id,statement_date));
        CREATE TABLE IF NOT EXISTS bank_statement_lines(
          line_id INTEGER PRIMARY KEY REFERENCES lines(id),
          statement_id INTEGER NOT NULL REFERENCES bank_statements(id) ON DELETE CASCADE);
        """)
        self.db.commit()

    def _account(self,code):
        if str(code) not in BANK_ACCOUNT_CODES:raise ReconciliationError("銀行勘定科目のみ照合できます")
        row=self.db.execute("SELECT id FROM accounts WHERE code=? AND active=1 AND type='資産'",(str(code),)).fetchone()
        if row is None:raise ReconciliationError("銀行勘定科目が見つかりません")
        return int(row[0])

    def _statement(self,sid):
        row=self.db.execute("SELECT * FROM bank_statements WHERE id=?",(sid,)).fetchone()
        if row is None:raise ReconciliationError("照合対象が見つかりません")
        return row

    def start(self,account_code,statement_date,opening_yen,closing_yen):
        account_id=self._account(account_code)
        statement_date=_date(statement_date)
        opening_yen,closing_yen=_yen(opening_yen),_yen(closing_yen)
        latest=self.db.execute("SELECT statement_date,closing_yen,status FROM bank_statements WHERE account_id=? ORDER BY statement_date DESC LIMIT 1",(account_id,)).fetchone()
        if latest:
            if latest["status"]!="FINALIZED":raise ReconciliationError("未確定の照合が存在します")
            if statement_date<=latest["statement_date"]:raise ReconciliationError("確定済み照合以前の日付は使用できません")
            if opening_yen!=latest["closing_yen"]:raise ReconciliationError("前回確定した期末残高と期首残高が一致しません")
        with self.db:
            cur=self.db.execute("INSERT INTO bank_statements(account_id,statement_date,opening_yen,closing_yen) VALUES(?,?,?,?)",(account_id,statement_date,opening_yen,closing_yen))
            sid=int(cur.lastrowid)
            self.db.execute("INSERT INTO audit_log(action,detail) VALUES('RECON_START',?)",(f"{sid}|{account_code}|{statement_date}",))
        return sid

    def mark(self,sid,line_id):
        statement=self._statement(sid)
        if statement["status"]!="OPEN":raise ReconciliationError("確定済み照合は変更できません")
        row=self.db.execute("SELECT l.id,e.entry_date FROM lines l JOIN entries e ON e.id=l.entry_id WHERE l.id=? AND l.account_id=?",(line_id,statement["account_id"])).fetchone()
        if row is None or row["entry_date"]>statement["statement_date"]:
            raise ReconciliationError("この明細は対象口座・照合期間に含まれません")
        previous=self.db.execute("SELECT MAX(statement_date) FROM bank_statements WHERE account_id=? AND status='FINALIZED'",(statement["account_id"],)).fetchone()[0]
        if previous is not None and row["entry_date"]<=previous:
            raise ReconciliationError("前回照合期間以前の明細は対象外です")
        with self.db:
            existing=self.db.execute("SELECT statement_id FROM bank_statement_lines WHERE line_id=?",(line_id,)).fetchone()
            if existing is not None:
                if int(existing[0])==int(sid):return False
                raise ReconciliationError("明細は別の照合で使用済みです")
            self.db.execute("INSERT INTO bank_statement_lines(line_id,statement_id) VALUES(?,?)",(line_id,sid))
        return True

    def unmark(self,sid,line_id):
        if self._statement(sid)["status"]!="OPEN":raise ReconciliationError("確定済み照合は変更できません")
        with self.db:
            cur=self.db.execute("DELETE FROM bank_statement_lines WHERE statement_id=? AND line_id=?",(sid,line_id))
        return cur.rowcount==1

    def report(self,sid):
        statement=self._statement(sid)
        totals=self.db.execute("SELECT COALESCE(SUM(l.debit_yen),0),COALESCE(SUM(l.credit_yen),0),COUNT(*) FROM bank_statement_lines b JOIN lines l ON l.id=b.line_id WHERE b.statement_id=?",(sid,)).fetchone()
        debit,credit,count=map(int,totals)
        calculated=int(statement["opening_yen"])+debit-credit
        difference=int(statement["closing_yen"])-calculated
        return {"statement_id":int(sid),"status":statement["status"],"statement_date":statement["statement_date"],
                "opening_yen":int(statement["opening_yen"]),"statement_closing_yen":int(statement["closing_yen"]),
                "cleared_debits_yen":debit,"cleared_credits_yen":credit,"cleared_count":count,
                "calculated_closing_yen":calculated,"difference_yen":difference,"balanced":difference==0}

    def unmatched(self,sid):
        statement=self._statement(sid)
        previous=self.db.execute("SELECT MAX(statement_date) FROM bank_statements WHERE account_id=? AND status='FINALIZED' AND id<>?",(statement["account_id"],sid)).fetchone()[0]
        sql=("SELECT l.id AS line_id,e.entry_date,e.description,l.debit_yen,l.credit_yen "
             "FROM lines l JOIN entries e ON e.id=l.entry_id "
             "LEFT JOIN bank_statement_lines b ON b.line_id=l.id "
             "WHERE l.account_id=? AND e.entry_date<=? AND b.line_id IS NULL")
        args=[statement["account_id"],statement["statement_date"]]
        if previous is not None:
            sql+=" AND e.entry_date>?"
            args.append(previous)
        sql+=" ORDER BY e.entry_date,e.id,l.id"
        return [dict(row) for row in self.db.execute(sql,args)]

    def finalize(self,sid):
        statement=self._statement(sid)
        result=self.report(sid)
        if statement["status"]=="FINALIZED":return result
        if not result["balanced"]:raise ReconciliationError("照合差額が0円になるまで確定できません")
        previous=self.db.execute("SELECT closing_yen FROM bank_statements WHERE account_id=? AND status='FINALIZED' AND statement_date<? ORDER BY statement_date DESC LIMIT 1",(statement["account_id"],statement["statement_date"])).fetchone()
        if previous and int(previous[0])!=int(statement["opening_yen"]):
            raise ReconciliationError("前回照合の残高が変化しました")
        with self.db:
            self.db.execute("UPDATE bank_statements SET status='FINALIZED',finalized_at=CURRENT_TIMESTAMP WHERE id=? AND status='OPEN'",(sid,))
            self.db.execute("INSERT INTO audit_log(action,detail) VALUES('RECON_FINALIZE',?)",(f"{sid}|{result['calculated_closing_yen']}|{result['cleared_count']}",))
        return self.report(sid)
