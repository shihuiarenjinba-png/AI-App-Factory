from __future__ import annotations
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, ROUND_UP
from datetime import date
from urllib.parse import urlsplit

ROUNDING = {"floor": ROUND_DOWN, "nearest": ROUND_HALF_UP, "ceil": ROUND_UP}

def _finite(value, label):
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be a finite number")
    return result

def _business_use(value):
    percent = _finite(value, "Business-use percent")
    if not 0 <= percent <= 100:
        raise ValueError("Business-use percent must be between 0 and 100")
    return percent / Decimal("100")

def manual_sales_tax(amount_before_tax, rate_percent, rounding="nearest"):
    amount = _finite(amount_before_tax, "Amount")
    rate = _finite(rate_percent, "Jurisdiction rate")
    if amount < 0 or rate < 0:
        raise ValueError("Amount and rate must be non-negative")
    if rounding not in ROUNDING:
        raise ValueError("Unsupported rounding mode")
    tax = (amount * rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUNDING[rounding])
    return {"net": amount, "tax": tax, "gross": amount + tax, "rate_percent": rate}

def months_in_service(first_use_date: str, year: int) -> int:
    d = date.fromisoformat(first_use_date)
    if year < d.year: return 0
    if year == d.year: return 13 - d.month
    return 12

def straight_line_book_schedule(cost, first_use_date, useful_life_years, salvage_value=0, business_use_percent=100, through_year=None):
    cost = _finite(cost, "Cost")
    salvage = _finite(salvage_value, "Salvage value")
    life = int(useful_life_years)
    if cost <= 0 or life <= 0 or salvage < 0 or salvage >= cost:
        raise ValueError("Check asset values")
    first = date.fromisoformat(first_use_date)
    through_year = int(through_year or first.year + life + 2)
    if through_year < first.year:
        raise ValueError("End year must not precede placed-in-service year")
    use = _business_use(business_use_percent)
    depreciable = cost - salvage
    annual = depreciable / Decimal(life)
    rows = []
    accumulated = Decimal("0")
    for year in range(first.year, through_year + 1):
        opening = cost - accumulated
        if opening <= salvage: break
        months = months_in_service(first_use_date, year)
        raw = min(annual * Decimal(months) / Decimal(12), opening - salvage)
        business = (raw * use).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        accumulated += raw
        rows.append({
            "year": year, "months": months, "opening_book_value": opening,
            "book_depreciation": raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "business_depreciation": business,
            "closing_book_value": (cost - accumulated).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        })
    return rows

def custom_tax_depreciation_schedule(cost, percentages_by_year, business_use_percent=100):
    """Arithmetic preview from user-supplied rates, NOT an IRS-approved schedule."""
    cost = _finite(cost, "Cost")
    use = _business_use(business_use_percent)
    if cost <= 0: raise ValueError("Cost must be positive")
    rows = []
    accumulated_pct = Decimal("0")
    for year in sorted(int(y) for y in percentages_by_year):
        pct = _finite(percentages_by_year[year], "Percentage")
        if pct < 0 or pct > 100:
            raise ValueError("Each percentage must be between 0 and 100")
        accumulated_pct += pct
        if accumulated_pct > 100:
            raise ValueError("Total depreciation percentages must not exceed 100")
        amount = (cost * pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        business = (amount * use).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        rows.append({"year": year, "percentage": pct, "tax_depreciation": amount, "business_depreciation": business})
    return rows

def retrospective_adjustment(schedule, posted_by_year, tax_mode=False):
    rows = []
    total = Decimal("0")
    key = "business_depreciation"
    for row in schedule:
        year = int(row["year"])
        expected = _finite(row[key], "Expected depreciation")
        posted = _finite(posted_by_year.get(year, 0), "Posted depreciation")
        delta = expected - posted
        total += delta
        rows.append({"year": year, "expected": expected, "posted": posted, "difference": delta})
    return {
        "rows": rows, "total_difference": total, "auto_post": False,
        "review_required": True, "tax_mode": bool(tax_mode),
        "message": (
            "Tax depreciation catch-up may require IRS accounting-method procedures, including Form 3115/section 481(a) depending on facts."
            if tax_mode else "Book depreciation catch-up is calculated for review before posting."
        ),
    }

def require_tax_profile(source_url, tax_year, method_name):
    """Validate provenance shape only; does not establish tax-law applicability."""
    try:
        parts = urlsplit(str(source_url))
        valid_host = parts.hostname == "irs.gov" or (parts.hostname or "").endswith(".irs.gov")
    except ValueError:
        valid_host = False
        parts = None
    if not parts or parts.scheme != "https" or not valid_host or parts.username or parts.password:
        raise ValueError("Tax profile requires an HTTPS IRS source URL")
    if int(tax_year) < 2000: raise ValueError("Tax year is invalid")
    if not isinstance(method_name, str) or not method_name.strip():
        raise ValueError("Method name is required")
    return {"source_url": source_url, "tax_year": int(tax_year), "method_name": method_name, "review_required": True}
