import importlib.util,sys,tempfile,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"products"/"jp-bookkeeping-desk"/"core.py";S=importlib.util.spec_from_file_location("jpb_factory",P);m=importlib.util.module_from_spec(S);sys.modules[S.name]=m;S.loader.exec_module(m)
class T(unittest.TestCase):
 def test_jp_chart(self):
  with tempfile.TemporaryDirectory() as d:
   s=m.Store(Path(d)/"x.db");self.assertIn("現金",{x["name"] for x in s.accounts()});s.close()
if __name__=="__main__":unittest.main()
