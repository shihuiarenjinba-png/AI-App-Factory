import sys
import unittest
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tax_assets import manual_sales_tax,straight_line_book_schedule,custom_tax_depreciation_schedule,retrospective_adjustment,require_tax_profile

class TaxGuardTests(unittest.TestCase):
    def test_irs_https_host_not_substring(self):
        x=require_tax_profile("https://www.irs.gov/publications/p946",2025,"manual MACRS review")
        self.assertTrue(x["review_required"])
        for url in ["https://evil.test/irs.gov","https://irs.gov.evil.test/","http://irs.gov/","https://irs.gov@evil.test/x","https://irs.gov:444/x","https://fakeirs.gov/x"]:
            with self.subTest(url=url),self.assertRaises(ValueError):
                require_tax_profile(url,2025,"manual")
    def test_finite_values_and_rate_bounds(self):
        for bad in ["NaN","Infinity","-Infinity"]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                manual_sales_tax(bad,5)
            with self.assertRaises(ValueError):
                straight_line_book_schedule("1000","2026-01-01",5,business_use_percent=bad)
        with self.assertRaises(ValueError):
            custom_tax_depreciation_schedule(1000,{2026:80,2027:30})
        with self.assertRaises(ValueError):
            custom_tax_depreciation_schedule(1000,{2026:-5})
    def test_retroactive_posted_only_year_is_not_lost(self):
        tax=manual_sales_tax("100.00","7.25")
        self.assertEqual((tax["tax"],tax["gross"]),(Decimal("7.25"),Decimal("107.25")))
        sched=custom_tax_depreciation_schedule(1000,{2026:50,2027:50})
        self.assertEqual(sum(x["business_depreciation"] for x in sched),Decimal("1000.00"))
        delta=retrospective_adjustment(sched,{2025:100,2026:400,2027:500},tax_mode=True)
        self.assertEqual(delta["total_difference"],Decimal("0.00"))
        self.assertEqual(delta["rows"][0]["difference"],Decimal("-100"))
        self.assertTrue(delta["review_required"]);self.assertFalse(delta["auto_post"])

if __name__=="__main__":unittest.main()
