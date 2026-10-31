"""Statement -> matched journal line -> ledger -> trial/P&L/B/S fixtures."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import Store,BookError
from reconciliation import preview_statement_reconciliation
from rollforward import roll_forward

class StatementReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/"book.db")
        self.store.post("2026-01-01","Capital",[("1100","1000.00",""),("3000","","1000.00")])
        self.store.post("2026-01-05","Sales",[("1100","500.00",""),("4000","","500.00")])
        self.rent=self.store.post("2026-02-03","Rent",[("5200","200.00",""),("1100","","200.00")])
        self.check=self.store.post("2026-02-10","Uncleared check",[("5500","50.00",""),("1100","","50.00")])
        self.rent_line=self.line(self.rent,"1100")
    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()
    def line(self,eid,code):
        return self.store.conn.execute("""
            SELECT l.id FROM lines l JOIN accounts a ON a.id=l.account_id
            WHERE l.entry_id=? AND a.code=?""",(eid,code)).fetchone()[0]
    def preview(self,items=None,matches=None,opening=150000,closing=130000):
        if items is None:
            items=[{"id":"rent-bank","date":"2026-02-03","amount_cents":-20000}]
        if matches is None:
            matches={"rent-bank":self.rent_line}
        return preview_statement_reconciliation(self.store,"1100","2026-02-01","2026-02-28",
                                                opening,closing,items,matches)
    def test_cleared_statement_and_outstanding_book_item(self):
        before=(len(self.store.journal()),self.store.balance_check(),self.store.pnl(),self.store.bs())
        r=self.preview()
        self.assertTrue(r["ready_for_manual_confirmation"])
        self.assertEqual((r["reconciled_balance_cents"],r["book_closing_cents"],
                          r["outstanding_book_delta_cents"],r["difference_cents"]),
                         (130000,125000,-5000,0))
        self.assertEqual([x["line_id"] for x in r["outstanding_book_lines"]],
                         [self.line(self.check,"1100")])
        self.assertEqual(r["matched"][0]["entry_id"],self.rent)
        self.assertTrue(r["preview_only"])
        self.assertFalse(r["auto_post"])
        self.assertIsNone(r["taxable_income"])
        self.assertEqual(before,(len(self.store.journal()),self.store.balance_check(),
                                 self.store.pnl(),self.store.bs()))
        report=roll_forward(self.store,"2026-02-01","2026-02-28")
        self.assertEqual(report["as_of_bs"]["assets"],125000)
        self.assertEqual(report["trial"]["debits"],report["trial"]["credits"])
    def test_unmatched_statement_stays_review_only(self):
        rows=[{"id":"rent-bank","date":"2026-02-03","amount_cents":-20000},
              {"id":"unknown","date":"2026-02-07","amount_cents":1000}]
        r=self.preview(items=rows,closing=131000)
        self.assertFalse(r["ready_for_manual_confirmation"])
        self.assertEqual(r["unmatched_statement_ids"],["unknown"])
        self.assertEqual(r["difference_cents"],1000)
    def test_wrong_account_duplicate_or_wrong_amount_fails_closed(self):
        expense_line=self.line(self.rent,"5200")
        for match in [{"rent-bank":expense_line},{"rent-bank":self.line(self.check,"1100")}]:
            with self.subTest(match=match),self.assertRaises(BookError):
                self.preview(matches=match)
        rows=[{"id":"a","date":"2026-02-03","amount_cents":-20000},
              {"id":"b","date":"2026-02-03","amount_cents":-20000}]
        with self.assertRaises(BookError):
            self.preview(items=rows,matches={"a":self.rent_line,"b":self.rent_line},closing=110000)
    def test_invalid_statement_and_balance_fails_closed(self):
        with self.assertRaises(BookError):
            self.preview(opening=150001)
        with self.assertRaises(BookError):
            self.preview(closing=129999)
        for amount in [float("nan"),-20000.0,True,"-20000"]:
            with self.subTest(amount=str(amount)),self.assertRaises(BookError):
                self.preview(items=[{"id":"rent-bank","date":"2026-02-03","amount_cents":amount}])
        with self.assertRaises(BookError):
            self.preview(items=[{"id":"rent-bank","date":"2026-03-01","amount_cents":-20000}])
        with self.assertRaises(BookError):
            self.preview(items=[{"id":"x","date":"2026-02-03","amount_cents":-10000},
                                {"id":"x","date":"2026-02-04","amount_cents":-10000}],matches={})
    def test_corrupted_journal_fails_closed(self):
        self.store.conn.execute("UPDATE lines SET credit_cents=credit_cents-1 WHERE id=?",(self.rent_line,))
        self.store.conn.commit()
        with self.assertRaises(BookError):
            self.preview()
    def test_empty_statement_not_ready(self):
        r=self.preview(items=[],matches={},opening=150000,closing=150000)
        self.assertFalse(r["ready_for_manual_confirmation"])
        self.assertEqual(len(r["outstanding_book_lines"]),2)

if __name__=="__main__":unittest.main()
