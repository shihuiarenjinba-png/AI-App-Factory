import importlib.util,sys,tempfile,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"core.py";S=importlib.util.spec_from_file_location("usb",P);m=importlib.util.module_from_spec(S);sys.modules[S.name]=m;S.loader.exec_module(m)
class T(unittest.TestCase):
 def test_double_entry_and_method_lock(self):
  with tempfile.TemporaryDirectory() as d:
   s=m.Store(Path(d)/"x.db","cash");s.post("2026-10-31","sale",[("1000","100.00",""),("4000","","100.00")]);self.assertEqual(s.pnl()["net_income"],10000)
   with self.assertRaises(m.BookError):s.set_method("accrual")
   s.close()
if __name__=="__main__":unittest.main()
