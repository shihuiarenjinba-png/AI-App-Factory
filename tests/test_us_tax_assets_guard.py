"""US tax/depreciation safety fixtures; not a tax-law certification."""
import importlib.util
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'products' / 'us-bookkeeping-desk'
spec = importlib.util.spec_from_file_location('us_tax_assets_guard', ROOT / 'tax_assets.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class TaxArithmeticGuardTests(unittest.TestCase):
    def test_existing_valid_cases(self):
        self.assertEqual(m.manual_sales_tax('100', '8.25')['tax'], Decimal('8.25'))
        self.assertEqual(m.straight_line_book_schedule('1200', '2026-01-01', 4, through_year=2026)[0]['business_depreciation'], Decimal('300.00'))
        self.assertTrue(m.retrospective_adjustment(m.custom_tax_depreciation_schedule('1000', {2026: '20', 2027: '32'}), {}, True)['review_required'])
        self.assertTrue(m.require_tax_profile('https://www.irs.gov/publications/p946', 2026, 'Manual review')['review_required'])

    def test_reject_nonfinite(self):
        for x in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(x=x), self.assertRaises(ValueError):
                m.manual_sales_tax(x, '5')
            with self.subTest(x=x), self.assertRaises(ValueError):
                m.manual_sales_tax('100', x)
            with self.subTest(x=x), self.assertRaises(ValueError):
                m.straight_line_book_schedule(x, '2026-01-01', 5)
            with self.subTest(x=x), self.assertRaises(ValueError):
                m.custom_tax_depreciation_schedule('100', {2026: x})

    def test_reject_over_depreciation_and_business_use(self):
        for percent in ('101', '-1'):
            with self.assertRaises(ValueError):
                m.straight_line_book_schedule('1000', '2026-01-01', 5, business_use_percent=percent)
            with self.assertRaises(ValueError):
                m.custom_tax_depreciation_schedule('1000', {2026: '20'}, business_use_percent=percent)
        with self.assertRaises(ValueError):
            m.custom_tax_depreciation_schedule('1000', {2026: '70', 2027: '40'})

    def test_reject_lookalike_irs_url(self):
        for url in ('https://irs.gov.evil.example/p946', 'http://www.irs.gov/publications/p946', 'https://example.com/irs.gov', 'https://www.irs.gov@evil.example/p946'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                m.require_tax_profile(url, 2026, 'MACRS review')


if __name__ == '__main__':
    unittest.main()
