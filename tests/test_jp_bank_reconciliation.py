"""Regression tests for bank statement reconciliation on the real JP journal schema."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/"products"/"jp-bookkeeping-desk"
def load(name,filename):
    spec=importlib.util.spec_from_file_location(name,ROOT/filename)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module

core=load("jp_bookkeeping_bank_core","core.py")
recon=load("jp_bookkeeping_bank_recon","reconciliation.py")

class BankReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=core.Store(Path(self.tmp.name)/"books.db")
        self.r=recon.BankReconciler(self.store)
        self.store.post("2026-09-30","開始残高",[("1100","1000",""),("3000","","1000")])
        self.store.post("2026-10-10","売上",[("1100","500",""),("4000","","500")])
        self.store.post("2026-10-12","家賃",[("5200","200",""),("1100","","200")])
        self.ids=[row[0] for row in self.store.conn.execute(
            "SELECT l.id FROM lines l JOIN accounts a ON a.id=l.account_id WHERE a.code='1100' ORDER BY l.id")]

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_two_statements_journal_trial_pnl_bs_consistent(self):
        first=self.r.start("1100","2026-09-30",0,1000)
        self.assertTrue(self.r.mark(first,self.ids[0]))
        self.assertFalse(self.r.mark(first,self.ids[0]))
        self.assertEqual(self.r.finalize(first)["difference_yen"],0)
        self.assertEqual(self.r.finalize(first)["status"],"FINALIZED")
        second=self.r.start("1100","2026-10-31",1000,1300)
        self.assertEqual(len(self.r.unmatched(second)),2)
        self.r.mark(second,self.ids[1])
        self.r.mark(second,self.ids[2])
        self.assertEqual(self.r.unmatched(second),[])
        self.assertEqual(self.r.finalize(second)["calculated_closing_yen"],1300)
        self.assertTrue(self.store.balance_check()["balanced"])
        self.assertEqual(self.store.pnl()["利益"],300)
        self.assertEqual(self.store.bs()["資産"],1300)
        self.assertEqual(self.store.bs()["資産"],self.store.bs()["負債純資産合計"])
        self.assertEqual(sum(x["debit"] for x in self.store.trial()),sum(x["credit"] for x in self.store.trial()))
        self.assertEqual(sum(x["debit_yen"]-x["credit_yen"] for x in self.store.ledger("1100")),1300)
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='RECON_FINALIZE'").fetchone()[0],2)
        with self.assertRaises(recon.ReconciliationError):self.r.unmark(second,self.ids[1])
        reopened=recon.BankReconciler(self.store)
        self.assertEqual(reopened.report(second)["status"],"FINALIZED")

    def test_nonzero_difference_blocks_and_unmark_is_reversible(self):
        sid=self.r.start("1100","2026-10-31",1000,1300)
        self.r.mark(sid,self.ids[1])
        self.assertEqual(self.r.report(sid)["difference_yen"],-200)
        with self.assertRaises(recon.ReconciliationError):self.r.finalize(sid)
        self.assertTrue(self.r.unmark(sid,self.ids[1]))
        self.assertFalse(self.r.unmark(sid,self.ids[1]))
        self.assertEqual(self.r.report(sid)["cleared_count"],0)
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='RECON_FINALIZE'").fetchone()[0],0)

    def test_prior_balance_duplicate_and_wrong_account(self):
        first=self.r.start("1100","2026-09-30",0,1000)
        with self.assertRaises(recon.ReconciliationError):self.r.start("1100","2026-10-31",1000,1300)
        self.r.mark(first,self.ids[0])
        self.r.finalize(first)
        with self.assertRaises(recon.ReconciliationError):self.r.start("1100","2026-10-31",999,1300)
        with self.assertRaises(recon.ReconciliationError):self.r.start("1000","2026-10-31",0,0)
        second=self.r.start("1100","2026-10-31",1000,1300)
        with self.assertRaises(recon.ReconciliationError):self.r.mark(second,self.ids[0])
        with self.assertRaises(recon.ReconciliationError):self.r.mark(second,99999)

    def test_future_lines_and_noninteger_balances_rejected(self):
        for amount in ["NaN","Infinity","1.2",True,2**64]:
            with self.subTest(amount=amount):
                with self.assertRaises(recon.ReconciliationError):
                    self.r.start("1100","2026-10-31",amount,100)
        sid=self.r.start("1100","2026-09-30",0,1000)
        with self.assertRaises(recon.ReconciliationError):self.r.mark(sid,self.ids[1])
        with self.assertRaises(recon.ReconciliationError):self.r.start("1100","2026-13-99",0,0)

if __name__=="__main__":unittest.main()
