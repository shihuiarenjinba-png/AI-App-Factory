import unittest
from decimal import Decimal
from asset_review import (manual_sales_tax_review, book_straight_line_schedule,
                          tax_profile_review, retrospective_book_review)

class AssetReviewTests(unittest.TestCase):
    def test_manual_rate(self):
        result = manual_sales_tax_review('100', '7.25', state='CA', locality='Example', source_note='User-entered')
        self.assertEqual(result['tax'], Decimal('7.25'))
        self.assertFalse(result['auto_post'])

    def test_jurisdiction_required(self):
        with self.assertRaises(ValueError):
            manual_sales_tax_review(100, 5, state='', locality='Town', source_note='manual')

    def test_nan_and_infinity_rejected(self):
        for value in ('NaN', 'Infinity', '-Infinity'):
            with self.assertRaises(ValueError):
                manual_sales_tax_review(value, 5, state='CA', locality='Town', source_note='manual')

    def test_invalid_rate_rejected(self):
        for rate in (-1, 101, 'NaN'):
            with self.assertRaises(ValueError):
                manual_sales_tax_review(100, rate, state='CA', locality='Town', source_note='manual')

    def test_book_partial_year(self):
        result = book_straight_line_schedule(1200, '2026-07-15', 2)
        self.assertEqual(result['rows'][0]['months'], 6)
        self.assertEqual(result['rows'][0]['book_expense'], Decimal('300.00'))
        self.assertEqual(sum(x['book_expense'] for x in result['rows']), Decimal('1200.00'))
        self.assertIsNone(result['tax_deduction'])

    def test_business_allocation(self):
        result = book_straight_line_schedule(1200, '2026-01-01', 2, business_use_percent=25)
        self.assertEqual(result['rows'][0]['business_use_allocation'], Decimal('150.00'))

    def test_invalid_book_percent(self):
        for value in (-1, 101, 'NaN'):
            with self.assertRaises(ValueError):
                book_straight_line_schedule(1000, '2026-01-01', 5, business_use_percent=value)

    def test_invalid_life(self):
        for value in (0, -1, 1.5, True, 101):
            with self.assertRaises(ValueError):
                book_straight_line_schedule(1000, '2026-01-01', value)

    def test_no_lookalike_irs_host(self):
        for url in ('https://irs.gov.evil.example/pub946', 'http://irs.gov/publications/p946',
                    'https://notirs.gov/publications/p946'):
            with self.assertRaises(ValueError):
                tax_profile_review(url, 2025, 'MACRS review', acquired_date='2025-01-01', first_use_date='2025-02-01')

    def test_acquisition_order(self):
        with self.assertRaises(ValueError):
            tax_profile_review('https://www.irs.gov/publications/p946', 2025, 'review',
                               acquired_date='2025-08-01', first_use_date='2025-02-01')

    def test_profile_is_review_only(self):
        x = tax_profile_review('https://www.irs.gov/publications/p946', 2025, 'MACRS review',
                               acquired_date='2025-01-01', first_use_date='2025-02-01')
        self.assertIsNone(x['tax_depreciation'])
        self.assertTrue(x['review_required'])

    def test_retrospective_includes_overposting(self):
        result = retrospective_book_review([{'year': 2025, 'business_use_allocation': '100'}],
                                           {2025: '80', 2024: '50'})
        self.assertEqual(result['total_difference'], Decimal('-30'))
        self.assertEqual([r['year'] for r in result['rows']], [2024, 2025])

    def test_duplicate_schedule_year_rejected(self):
        with self.assertRaises(ValueError):
            retrospective_book_review([{'year': 2025, 'business_use_allocation': 10},
                                       {'year': 2025, 'business_use_allocation': 20}], {})

if __name__ == '__main__': unittest.main()
