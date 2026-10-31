import importlib.util,sys,tempfile,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"core.py";S=importlib.util.spec_from_file_location("usfl",P);m=importlib.util.module_from_spec(S);sys.modules[S.name]=m;S.loader.exec_module(m)
class T(unittest.TestCase):
 def test_usd_and_method_lock(self):
  with tempfile.TemporaryDirectory() as d:
   s=m.Store(Path(d)/"x.db","cash");s.add("2026-10-01","income","100.25","Business income");self.assertEqual(s.monthly(2026,10)["income"],10025)
   with self.assertRaises(m.LedgerError):s.set_accounting_method("accrual")
   s.close()
if __name__=="__main__":unittest.main()
