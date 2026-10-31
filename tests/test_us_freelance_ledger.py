import importlib.util,sys,tempfile,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"products"/"us-freelance-ledger"/"core.py";S=importlib.util.spec_from_file_location("usfl_factory",P);m=importlib.util.module_from_spec(S);sys.modules[S.name]=m;S.loader.exec_module(m)
class T(unittest.TestCase):
 def test_us_only_contract(self):
  self.assertIn("cash",m.METHODS);self.assertIn("accrual",m.METHODS)
  with tempfile.TemporaryDirectory() as d:
   s=m.Store(Path(d)/"x.db");s.add("2026-10-31","expense","12.50","Supplies");self.assertEqual(s.monthly(2026,10)["expense"],1250);s.close()
if __name__=="__main__":unittest.main()
