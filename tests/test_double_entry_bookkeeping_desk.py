import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "products" / "double-entry-bookkeeping-desk" / "core.py"
SPEC = importlib.util.spec_from_file_location("double_entry_core", CORE)
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)

class FactoryBookkeepingContract(unittest.TestCase):
    def test_double_entry_contract(self):
        with tempfile.TemporaryDirectory() as td:
            store = mod.BookStore(Path(td) / "x.db", "JPY")
            store.post_entry("2026-10-31", "sale", [
                ("1000", "10000", ""),
                ("4000", "", "10000"),
            ])
            tb = store.trial_balance()
            self.assertEqual(sum(int(x["debit"]) for x in tb), sum(int(x["credit"]) for x in tb))
            self.assertEqual(store.income_statement()["net_income"], 10000)
            store.close()

    def test_default_accounts_present(self):
        with tempfile.TemporaryDirectory() as td:
            store = mod.BookStore(Path(td) / "x.db", "USD")
            codes = {x["code"] for x in store.accounts()}
            self.assertTrue({"1000","2000","3000","4000","5000"}.issubset(codes))
            store.close()

if __name__ == "__main__":
    unittest.main()
