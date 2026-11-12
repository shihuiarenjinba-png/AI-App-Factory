"""US reconciliation fixtures: journal -> ledger -> trial -> P&L -> B/S."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "products" / "us-bookkeeping-desk"

def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

core = load("us_bank_core", "core.py")
recon = load("us_bank_reconciliation", "reconciliation.py")

class BankReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "books.sqlite3"
        self.s = core.Store(self.path, "cash")
        self.s.post("2026-10-01", "Client receipt",
                    [("1100","1000.00",""),("4000","","1000.00")])
        self.s.post("2026-10-03", "Office rent",
                    [("5200","300.00",""),("1100","","300.00")])
        self.s.post("2026-10-04", "Uncleared receipt",
                    [("1100","100.00",""),("4000","","100.00")])
        self.r = recon.BankReconciler(self.s)
        self.bank_lines = [dict(r) for r in self.s.conn.execute("""
            SELECT l.id,e.entry_date,l.debit_cents,l.credit_cents
            FROM lines l JOIN entries e ON e.id=l.entry_id
            JOIN accounts a ON a.id=l.account_id
            WHERE a.code='1100' ORDER BY e.entry_date,e.id
        """)]
    def tearDown(self):
        self.s.close()
        self.tmp.cleanup()

    def test_reconcile_preserves_all_book_reports_and_restarts(self):
        before = (self.s.journal(), self.s.trial(), self.s.pnl(), self.s.bs(),
                  self.s.balance_check(), self.s.ledger("1100"))
        ids = [self.bank_lines[0]["id"],self.bank_lines[1]["id"]]
        p = self.r.preview("1100","2026-10-01","2026-10-31",0,700,ids)
        self.assertTrue(p["ready"])
        self.assertEqual(p["outstanding_cents"],10000)
        self.assertEqual(p["book_closing_cents"],80000)
        with self.assertRaises(recon.ReconciliationError):
            self.r.finalize("1100","2026-10-01","2026-10-31",0,700,ids)
        result = self.r.finalize("1100","2026-10-01","2026-10-31",0,700,ids,confirmed=True)
        self.assertEqual(result["difference_cents"],0)
        self.assertTrue(self.s.balance_check()["balanced"])
        self.assertEqual(self.s.pnl()["net_income"],80000)
        self.assertEqual(self.s.bs()["assets"],self.s.bs()["liabilities_and_equity"])
        self.assertEqual(before,(self.s.journal(),self.s.trial(),self.s.pnl(),self.s.bs(),
                                 self.s.balance_check(),self.s.ledger("1100")))
        self.assertEqual(self.s.conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='BANK_RECONCILE'").fetchone()[0],1)
        self.s.close()
        self.s = core.Store(self.path)
        self.r = recon.BankReconciler(self.s)
        self.assertEqual(len(self.r.history("1100")),1)

    def test_duplicate_foreign_line_and_difference_are_rejected_atomically(self):
        ids = [self.bank_lines[0]["id"],self.bank_lines[1]["id"]]
        for selection in ([ids[0],ids[0]],[2],[999],[True]):
            with self.subTest(selection=selection),self.assertRaises(recon.ReconciliationError):
                self.r.preview("1100","2026-10-01","2026-10-31",0,700,selection)
        with self.assertRaises(recon.ReconciliationError):
            self.r.finalize("1100","2026-10-01","2026-10-31",0,900,ids,confirmed=True)
        self.assertEqual(self.r.history("1100"),[])
        self.r.finalize("1100","2026-10-01","2026-10-31",0,700,ids,confirmed=True)
        with self.assertRaises(recon.ReconciliationError):
            self.r.finalize("1100","2026-10-01","2026-10-31",0,700,ids,confirmed=True)
        self.assertEqual(len(self.r.history("1100")),1)

    def test_backdated_post_is_blocked_after_reconciliation(self):
        ids = [self.bank_lines[0]["id"],self.bank_lines[1]["id"]]
        self.r.finalize("1100","2026-10-01","2026-10-31",0,700,ids,confirmed=True)
        before = (self.s.journal(),self.s.trial(),self.s.pnl(),self.s.bs())
        with self.assertRaises(core.BookError):
            self.s.post("2026-10-15","Late backdated expense",
                        [("5200","1.00",""),("1100","","1.00")])
        self.assertEqual(before,(self.s.journal(),self.s.trial(),self.s.pnl(),self.s.bs()))
        self.s.post("2026-11-02","New month expense",
                    [("5200","1.00",""),("1100","","1.00")])
        self.assertTrue(self.s.balance_check()["balanced"])

    def test_carry_forward_outstanding_receipt_and_no_tax_inference(self):
        ids = [self.bank_lines[0]["id"],self.bank_lines[1]["id"]]
        self.r.finalize("1100","2026-10-01","2026-10-31",0,700,ids,confirmed=True)
        with self.assertRaises(recon.ReconciliationError):
            self.r.preview("1100","2026-11-01","2026-11-30",0,800,[self.bank_lines[2]["id"]])
        p = self.r.preview("1100","2026-11-01","2026-11-30",700,800,[self.bank_lines[2]["id"]])
        self.assertTrue(p["ready"])
        self.assertFalse(p["tax_decision"])
        self.assertEqual(p["outstanding_cents"],0)
        self.r.finalize("1100","2026-11-01","2026-11-30",700,800,
                        [self.bank_lines[2]["id"]],confirmed=True)
        self.assertEqual(len(self.r.history("1100")),2)
        self.assertEqual(self.s.pnl()["net_income"],80000)

if __name__ == "__main__":
    unittest.main()
