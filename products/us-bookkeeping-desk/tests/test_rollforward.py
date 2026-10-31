"""Journal -> ledger -> trial -> P&L/B/S roll-forward fixtures."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Store, BookError
from rollforward import roll_forward, account_drilldown

class RollForwardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/"book.sqlite3")
        self.store.post("2026-01-01","Owner capital",[("1100","1000.00",""),("3000","","1000.00")])
        self.store.post("2026-01-05","Service revenue",[("1100","500.00",""),("4000","","500.00")])
        self.store.post("2026-02-03","Office rent",[("5200","200.00",""),("1100","","200.00")])
    def tearDown(self):
        self.store.close()
        self.temp.cleanup()
    def test_journal_ledger_trial_pnl_bs(self):
        r=roll_forward(self.store,"2026-02-01","2026-02-28")
        bank=next(a for a in r["accounts"] if a["code"]=="1100")
        self.assertEqual((bank["opening_normal"],bank["period_debits"],bank["period_credits"],bank["closing_normal"]),(150000,0,20000,130000))
        self.assertEqual(r["period_pl"],{"revenue":0,"expense":20000,"book_income":-20000})
        self.assertEqual(r["as_of_pl"]["book_income"],30000)
        self.assertEqual(r["as_of_bs"]["assets"],130000)
        self.assertEqual(r["as_of_bs"]["liabilities_equity_income"],130000)
        self.assertEqual(r["trial"]["debits"],r["trial"]["credits"])
        self.assertEqual(r["as_of_pl"]["book_income"],self.store.pnl()["net_income"])
        self.assertEqual(r["as_of_bs"]["assets"],self.store.bs()["assets"])
        self.assertIsNone(r["taxable_income"])
        detail=account_drilldown(self.store,"1100","2026-02-01","2026-02-28")
        self.assertEqual(len(detail),1)
        self.assertEqual(sum(x["credit_cents"] for x in detail),bank["period_credits"])
        self.assertEqual([x["entry_id"] for x in detail],bank["entry_ids"])
    def test_partial_and_empty_period(self):
        jan=roll_forward(self.store,"2026-01-01","2026-01-31")
        self.assertEqual(jan["as_of_pl"]["book_income"],50000)
        empty=roll_forward(self.store,"2027-01-01","2027-12-31")
        self.assertEqual(empty["period_pl"]["book_income"],0)
        self.assertEqual(empty["as_of_bs"]["assets"],130000)
        self.assertEqual(account_drilldown(self.store,"1100","2027-01-01","2027-12-31"),[])
    def test_invalid_dates_and_account(self):
        for start,end in [("2026-02-30","2026-03-01"),("2026-03-01","2026-02-01"),("2026-1-01","2026-02-01")]:
            with self.subTest(start=start,end=end),self.assertRaises(BookError):
                roll_forward(self.store,start,end)
        with self.assertRaises(BookError):
            account_drilldown(self.store,"not-an-account","2026-01-01","2026-12-31")
    def test_corrupt_entry_fails_closed(self):
        self.store.conn.execute("UPDATE lines SET credit_cents=credit_cents-1 WHERE id=(SELECT MIN(id) FROM lines WHERE credit_cents>0)")
        self.store.conn.commit()
        with self.assertRaises(BookError):
            roll_forward(self.store,"2026-01-01","2026-12-31")
        with self.assertRaises(BookError):
            account_drilldown(self.store,"1100","2026-01-01","2026-12-31")
    def test_locked_period_unchanged(self):
        self.store.lock("2026-01-31")
        r=roll_forward(self.store,"2026-01-01","2026-02-28")
        self.assertEqual(r["journal_entry_count"],3)
        self.assertEqual(self.store.locked,"2026-01-31")
        self.assertEqual(len(self.store.journal()),6)

if __name__=="__main__":
    unittest.main()
