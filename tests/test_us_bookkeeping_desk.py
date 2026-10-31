import importlib.util,sys,tempfile,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"products"/"us-bookkeeping-desk"/"core.py";S=importlib.util.spec_from_file_location("usb_factory",P);m=importlib.util.module_from_spec(S);sys.modules[S.name]=m;S.loader.exec_module(m)
class T(unittest.TestCase):
 def test_us_chart(self):
  with tempfile.TemporaryDirectory() as d:
   s=m.Store(Path(d)/"x.db");self.assertIn("Cash",{x["name"] for x in s.accounts()});self.assertIn(s.accounting_method,m.METHODS);s.close()
if __name__=="__main__":unittest.main()
