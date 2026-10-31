import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "products" / "freelance-ledger-local" / "core.py"
SPEC = importlib.util.spec_from_file_location("freelance_ledger_core", CORE)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

class FactoryFreelanceLedgerContract(unittest.TestCase):
    def test_balanced_storage_contract(self):
        with tempfile.TemporaryDirectory() as td:
            store = mod.LedgerStore(Path(td) / "x.db", "JP")
            store.add_transaction("2026-10-31", "income", "5000", "売上高")
            store.add_transaction("2026-10-31", "expense", "800", "通信費")
            self.assertEqual(store.monthly_summary(2026, 10)["net"], 4200)
            self.assertEqual(store.profile, "JP")
            store.close()

    def test_country_profiles_exist(self):
        self.assertEqual(mod.profile_info("JP")["currency"], "JPY")
        self.assertEqual(mod.profile_info("US")["currency"], "USD")

if __name__ == "__main__":
    unittest.main()
