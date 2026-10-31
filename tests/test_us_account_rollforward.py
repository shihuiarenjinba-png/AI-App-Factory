"""US roll-forward fixtures: journal -> ledger -> trial -> P&L/B/S."""
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'products' / 'us-bookkeeping-desk'
spec = importlib.util.spec_from_file_location('us_rollforward', ROOT / 'rollforward.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FakeStore:
    accounting_method = 'cash'

    def __init__(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
        CREATE TABLE accounts(id INTEGER PRIMARY KEY,code TEXT,name TEXT,type TEXT);
        CREATE TABLE entries(id INTEGER PRIMARY KEY,entry_date TEXT,description TEXT);
        CREATE TABLE lines(id INTEGER PRIMARY KEY,entry_id INTEGER,account_id INTEGER,debit_cents INTEGER,credit_cents INTEGER);
        INSERT INTO accounts VALUES(1,'1100','Bank','asset'),(2,'4000','Revenue','revenue'),(3,'5200','Rent','expense'),(4,'2000','Payables','liability');
        INSERT INTO entries VALUES(1,'2026-09-20','Opening equity receipt'),(2,'2026-10-02','October sale'),(3,'2026-10-04','Rent'),(4,'2026-11-01','Future sale');
        INSERT INTO lines VALUES(1,1,1,10000,0),(2,1,2,0,10000),(3,2,1,15025,0),(4,2,2,0,15025),(5,3,3,5000,0),(6,3,1,0,5000),(7,4,1,9000,0),(8,4,2,0,9000);
        """)


class TestRollForward(unittest.TestCase):
    def setUp(self):
        self.s = FakeStore()

    def tearDown(self):
        self.s.conn.close()

    def test_opening_movement_closing_and_drilldown(self):
        r = mod.account_rollforward(self.s, '2026-10-01', '2026-10-31')
        x = {z['code']: z for z in r['rows']}
        self.assertEqual((x['1100']['opening_cents'], x['1100']['movement_cents'], x['1100']['closing_cents']), (10000, 10025, 20025))
        self.assertEqual((x['4000']['opening_cents'], x['4000']['movement_cents'], x['4000']['closing_cents']), (10000, 15025, 25025))
        self.assertEqual(x['5200']['closing_cents'], 5000)
        self.assertEqual([q['running_balance_cents'] for q in x['1100']['entries']], [25025, 20025])
        self.assertEqual(r['journal_check']['period_debits_cents'], 20025)
        self.assertEqual(r['journal_check']['period_credits_cents'], 20025)
        self.assertFalse(r['taxable_income'])

    def test_subset_still_checks_full_journal(self):
        r = mod.account_rollforward(self.s, '2026-10-01', '2026-10-31', ['1100'])
        self.assertEqual([x['code'] for x in r['rows']], ['1100'])
        self.assertEqual(r['journal_check']['period_debits_cents'], 20025)

    def test_restart_idempotent_and_read_only(self):
        before = self.s.conn.total_changes
        a = mod.account_rollforward(self.s, '2026-10-01', '2026-10-31')
        b = mod.account_rollforward(self.s, '2026-10-01', '2026-10-31')
        self.assertEqual(a, b)
        self.assertEqual(self.s.conn.total_changes, before)

    def test_invalid_dates_and_account_filters(self):
        for st, en in [('2026-02-30', '2026-10-31'), ('2026-11-01', '2026-10-31'), ('20261001', '2026-10-31')]:
            with self.subTest(st=st), self.assertRaises(mod.RollForwardError):
                mod.account_rollforward(self.s, st, en)
        for codes in [['1100', '1100'], ['9999'], [], ['']]:
            with self.subTest(codes=codes), self.assertRaises(mod.RollForwardError):
                mod.account_rollforward(self.s, '2026-10-01', '2026-10-31', codes)

    def test_unbalanced_corruption_is_not_hidden(self):
        self.s.conn.execute("UPDATE lines SET credit_cents=14025 WHERE id=4")
        with self.assertRaises(mod.RollForwardError):
            mod.account_rollforward(self.s, '2026-10-01', '2026-10-31', ['1100'])

    def test_empty_period_and_zero_accounts(self):
        r = mod.account_rollforward(self.s, '2026-08-01', '2026-08-31', include_zero=True)
        self.assertEqual(len(r['rows']), 4)
        self.assertTrue(all(x['closing_cents'] == 0 for x in r['rows']))


class IntegrationWithBookStore(unittest.TestCase):
    def test_journal_ledger_trial_pnl_bs_and_restart(self):
        core_spec = importlib.util.spec_from_file_location('us_rollforward_core', ROOT / 'core.py')
        core = importlib.util.module_from_spec(core_spec)
        core_spec.loader.exec_module(core)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'books.sqlite3'
            store = core.Store(path, 'cash')
            store.post('2026-09-30', 'Opening sale', [('1100', '100.00', ''), ('4000', '', '100.00')])
            store.post('2026-10-02', 'October sale', [('1100', '50.00', ''), ('4000', '', '50.00')])
            store.post('2026-10-04', 'Rent', [('5200', '20.00', ''), ('1100', '', '20.00')])
            store.post('2026-11-01', 'Later sale', [('1100', '999.00', ''), ('4000', '', '999.00')])
            before = (store.journal(), store.trial(), store.pnl(), store.bs(), store.balance_check(), store.ledger('1100'))
            report = mod.account_rollforward(store, '2026-10-01', '2026-10-31')
            rows = {r['code']: r for r in report['rows']}
            self.assertEqual((rows['1100']['opening_cents'], rows['1100']['movement_cents'], rows['1100']['closing_cents']), (10000, 3000, 13000))
            self.assertEqual(rows['4000']['closing_cents'], 15000)
            self.assertEqual(rows['5200']['closing_cents'], 2000)
            self.assertTrue(report['journal_check']['balanced'])
            self.assertTrue(store.balance_check()['balanced'])
            self.assertEqual(store.bs()['assets'], store.bs()['liabilities_and_equity'])
            self.assertEqual(store.pnl()['net_income'], 112900)
            self.assertEqual(before, (store.journal(), store.trial(), store.pnl(), store.bs(), store.balance_check(), store.ledger('1100')))
            store.close()
            store = core.Store(path)
            self.assertEqual(report, mod.account_rollforward(store, '2026-10-01', '2026-10-31'))
            store.close()


if __name__ == '__main__':
    unittest.main()
