"""Conservative US book-asset and manual sales-tax review helpers.

This module never computes tax depreciation or a deductible amount. Its outputs
are review worksheets and must not be automatically posted or filed.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlsplit


CENT = Decimal('0.01')


def _number(value, name):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f'{name} must be numeric') from exc
    if not number.is_finite():
        raise ValueError(f'{name} must be finite')
    return number


def _date(value, name):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{name} must be ISO YYYY-MM-DD') from exc


def manual_sales_tax_review(net_amount, rate_percent, *, state, locality, source_note):
    """Compute user-supplied arithmetic, not jurisdictional tax applicability."""
    if not all(isinstance(v, str) and v.strip() for v in (state, locality, source_note)):
        raise ValueError('State, locality and user rate source are required')
    net = _number(net_amount, 'net_amount')
    rate = _number(rate_percent, 'rate_percent')
    if net < 0 or not 0 <= rate <= 100:
        raise ValueError('Invalid net amount or manually supplied rate')
    tax = (net * rate / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    return {
        'net': net, 'tax': tax, 'gross': net + tax,
        'rate_percent': rate, 'state': state.strip(), 'locality': locality.strip(),
        'source_note': source_note.strip(), 'review_required': True,
        'auto_post': False,
        'notice': 'Manual arithmetic only; state/local sales-tax rules and nexus are not determined.',
    }


def book_straight_line_schedule(cost, first_use_date, useful_life_years, *,
                                salvage_value=0, business_use_percent=100,
                                through_year=None):
    """Book (not tax) straight-line depreciation with first-month convention.

    Business-use is an allocation column, not a tax deduction determination.
    First-use month is counted in full for this *book-policy example* only.
    """
    cost = _number(cost, 'cost')
    salvage = _number(salvage_value, 'salvage_value')
    use = _number(business_use_percent, 'business_use_percent')
    if cost <= 0 or salvage < 0 or salvage >= cost or not 0 <= use <= 100:
        raise ValueError('Invalid book asset values')
    if isinstance(useful_life_years, bool) or not isinstance(useful_life_years, int) or useful_life_years <= 0 or useful_life_years > 100:
        raise ValueError('Useful life must be an integer from 1 to 100')
    first = _date(first_use_date, 'first_use_date')
    end = first.year + useful_life_years + 1 if through_year is None else int(through_year)
    if end < first.year or end > first.year + 102:
        raise ValueError('Invalid through_year')
    annual = (cost - salvage) / Decimal(useful_life_years)
    remaining = cost - salvage
    rows = []
    for year in range(first.year, end + 1):
        if remaining <= 0:
            break
        months = 13 - first.month if year == first.year else 12
        expense = min(remaining, annual * months / 12)
        remaining -= expense
        rows.append({
            'year': year, 'months': months,
            'book_expense': expense.quantize(CENT, rounding=ROUND_HALF_UP),
            'business_use_allocation': (expense * use / 100).quantize(CENT, rounding=ROUND_HALF_UP),
            'remaining_depreciable_basis': remaining.quantize(CENT, rounding=ROUND_HALF_UP),
        })
    return {'rows': rows, 'review_required': True, 'auto_post': False,
            'basis': 'BOOK_ONLY', 'tax_deduction': None,
            'notice': 'Not a MACRS, Section 179, bonus-depreciation or tax-return calculation.'}


def tax_profile_review(source_url, tax_year, method_name, *, acquired_date, first_use_date):
    """Only register evidence; no federal tax computation is authorized."""
    parsed = urlsplit(source_url)
    if parsed.scheme != 'https' or parsed.hostname not in ('irs.gov', 'www.irs.gov'):
        raise ValueError('An HTTPS IRS primary-source URL is required')
    if not isinstance(tax_year, int) or isinstance(tax_year, bool) or not 2000 <= tax_year <= 2100:
        raise ValueError('Explicit tax year is required')
    if not isinstance(method_name, str) or not method_name.strip():
        raise ValueError('Method description is required')
    acquired = _date(acquired_date, 'acquired_date')
    first = _date(first_use_date, 'first_use_date')
    if first < acquired:
        raise ValueError('Placed-in-service date precedes acquisition')
    return {'tax_year': tax_year, 'source_url': source_url, 'method_name': method_name.strip(),
            'acquired_date': acquired.isoformat(), 'first_use_date': first.isoformat(),
            'review_required': True, 'auto_post': False, 'tax_depreciation': None,
            'notice': 'Confirm current-year IRS Publication 946 and Form 3115/section 481(a) applicability.'}


def retrospective_book_review(schedule, posted_by_year):
    """Compare every scheduled and posted year; never silently drop over-postings."""
    expected = {}
    for row in schedule:
        year = int(row['year'])
        if year in expected:
            raise ValueError('Duplicate schedule year')
        expected[year] = _number(row['business_use_allocation'], 'business_use_allocation')
    posted = {int(year): _number(amount, 'posted amount') for year, amount in posted_by_year.items()}
    years = sorted(set(expected) | set(posted))
    rows = [{'year': year, 'expected': expected.get(year, Decimal(0)),
             'posted': posted.get(year, Decimal(0)),
             'difference': expected.get(year, Decimal(0)) - posted.get(year, Decimal(0))}
            for year in years]
    return {'rows': rows, 'total_difference': sum((row['difference'] for row in rows), Decimal(0)),
            'review_required': True, 'auto_post': False,
            'notice': 'Book catch-up review only. Do not amend past tax returns or post adjustments automatically.'}
