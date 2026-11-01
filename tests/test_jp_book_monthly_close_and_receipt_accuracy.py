import importlib.util,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);return m
core=load("jp_book_core_close",ROOT/"products"/"jp-bookkeeping-desk"/"core.py")
close=load("jp_book_monthly_close",ROOT/"products"/"jp-bookkeeping-desk"/"monthly_close.py")
acc=load("jp_book_receipt_accuracy",ROOT/"products"/"jp-bookkeeping-desk"/"receipt_accuracy.py")
class T(unittest.TestCase):
 def test_monthly_package(self):
  with tempfile.TemporaryDirectory() as td:
   s=core.Store(Path(td)/"x.db")
   s.post("2026-11-01","売上",[("1100","10000",""),("4000","","10000")])
   out=close.export_month_end_package(s,2026,11,Path(td)/"out")
   self.assertTrue(Path(out["html"]).exists());self.assertTrue(Path(out["csv"]).exists());self.assertTrue(Path(out["json"]).exists())
   self.assertTrue(s.balance_check()["balanced"]);s.close()
 def test_unsafe_autopost_fails(self):
  truths=[acc.ReceiptTruth("1","2026-11-01","店A","5000",None,None,True)]
  preds=[acc.ReceiptPrediction("1","2026-11-01","店A","5000",None,(),False,True)]
  m=acc.evaluate(truths,preds)
  self.assertEqual(m["unsafe_auto_post_count"],1)
  self.assertFalse(acc.release_gate(m)["pass"])
if __name__=="__main__":unittest.main()
