from __future__ import annotations
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP, ROUND_UP
from urllib.parse import urlsplit
from datetime import date

ROUNDING = {"floor":ROUND_DOWN,"nearest":ROUND_HALF_UP,"ceil":ROUND_UP}

def _finite(value, label):
    try:
        number=Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid {label}") from exc
    if not number.is_finite():
        raise ValueError(f"Invalid {label}")
    return number

def _percent(value, label):
    number=_finite(value,label)
    if not Decimal("0") <= number <= Decimal("100"):
        raise ValueError(f"{label} must be between 0 and 100")
    return number

def _year(value):
    try:
        year=int(value)
        if str(value).strip()!=str(year) or not 1900<=year<=2100:
            raise ValueError()
        return year
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid schedule year") from exc

def manual_sales_tax(amount_before_tax, rate_percent, rounding="nearest"):
    amount=_finite(amount_before_tax,"amount"); rate=_percent(rate_percent,"manual jurisdiction rate")/Decimal("100")
    if amount < 0: raise ValueError("Amount must be non-negative")
    if rounding not in ROUNDING: raise ValueError("Unknown rounding mode")
    tax=(amount*rate).quantize(Decimal("0.01"),rounding=ROUNDING[rounding])
    return {"net":amount,"tax":tax,"gross":amount+tax,"rate_percent":rate*100}

def months_in_service(first_use_date: str, year: int) -> int:
    d=date.fromisoformat(first_use_date)
    if year < d.year: return 0
    if year == d.year: return 13-d.month
    return 12

def straight_line_book_schedule(cost, first_use_date, useful_life_years, salvage_value=0, business_use_percent=100, through_year=None):
    cost=_finite(cost,"cost"); salvage=_finite(salvage_value,"salvage value")
    life=int(useful_life_years)
    if str(useful_life_years).strip()!=str(life) or not 1<=life<=1000:
        raise ValueError("Useful life must be a whole number of years")
    if cost <= 0 or salvage < 0 or salvage >= cost: raise ValueError("Check asset values")
    first=date.fromisoformat(first_use_date)
    through_year=int(through_year) if through_year is not None else first.year+life+2
    if through_year < first.year or through_year > first.year+life+5:
        raise ValueError("Invalid schedule end year")
    use=_percent(business_use_percent,"business use")/Decimal("100")
    depreciable=cost-salvage
    annual=depreciable/Decimal(life)
    rows=[]; accumulated=Decimal("0")
    for year in range(first.year,through_year+1):
        opening=cost-accumulated
        if opening <= salvage: break
        months=months_in_service(first_use_date,year)
        raw=annual*Decimal(months)/Decimal(12)
        raw=min(raw,opening-salvage)
        business=(raw*use).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
        accumulated+=raw
        rows.append({
            "year":year,"months":months,"opening_book_value":opening,
            "book_depreciation":raw.quantize(Decimal("0.01"),rounding=ROUND_HALF_UP),
            "business_depreciation":business,
            "closing_book_value":(cost-accumulated).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP),
        })
    return rows

def custom_tax_depreciation_schedule(cost, percentages_by_year, business_use_percent=100):
    cost=_finite(cost,"tax depreciable basis")
    use=_percent(business_use_percent,"business use")/Decimal("100")
    if cost <= 0: raise ValueError("Cost must be positive")
    if not isinstance(percentages_by_year,dict) or not percentages_by_year:
        raise ValueError("Enter a manually reviewed tax-year schedule")
    years={_year(year):_percent(pct,"tax-year percentage") for year,pct in percentages_by_year.items()}
    if len(years)!=len(percentages_by_year) or sum(years.values())>100:
        raise ValueError("Tax-year percentages must total no more than 100")
    rows=[]; accumulated=Decimal("0")
    for year in sorted(years):
        pct=years[year]
        amount=(cost*pct/Decimal("100")).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
        if accumulated+amount>cost:
            raise ValueError("Tax schedule exceeds depreciable basis")
        business=(amount*use).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
        accumulated+=amount
        rows.append({"year":year,"percentage":pct,"tax_depreciation":amount,"business_depreciation":business})
    return rows

def retrospective_adjustment(schedule, posted_by_year, tax_mode=False):
    rows=[]; total=Decimal("0")
    key="business_depreciation"
    for row in schedule:
        year=int(row["year"]); expected=Decimal(str(row[key])); posted=Decimal(str(posted_by_year.get(year,0)))
        delta=expected-posted; total+=delta
        rows.append({"year":year,"expected":expected,"posted":posted,"difference":delta})
    return {
        "rows":rows,
        "total_difference":total,
        "auto_post":False,
        "review_required":True,
        "tax_mode":bool(tax_mode),
        "message":(
            "Tax depreciation catch-up may require IRS accounting-method procedures, including Form 3115/section 481(a) depending on facts."
            if tax_mode else
            "Book depreciation catch-up is calculated for review before posting."
        ),
    }

def require_tax_profile(source_url, tax_year, method_name):
    try:
        parsed=urlsplit(source_url)
    except (TypeError,ValueError) as exc:
        raise ValueError("Tax profile requires an official HTTPS IRS URL") from exc
    try:
        host=(parsed.hostname or "").lower()
        port=parsed.port
    except ValueError as exc:
        raise ValueError("Tax profile requires an official HTTPS IRS URL") from exc
    # Reject ambiguous authority, credentials, malformed ports and nonstandard ports.
    if (not isinstance(source_url, str) or
        any(char.isspace() or ord(char) < 32 or ord(char) == 127 or char == "\\" for char in source_url) or
        parsed.scheme != "https" or
        (host != "irs.gov" and not host.endswith(".irs.gov")) or
        parsed.username is not None or parsed.password is not None or
        port not in (None, 443) or not parsed.netloc):
        raise ValueError("Tax profile requires an official HTTPS IRS URL")
    year=_year(tax_year)
    if year<2000: raise ValueError("Tax year is invalid")
    if not isinstance(method_name,str) or not method_name.strip():
        raise ValueError("Method name is required")
    return {"source_url":source_url,"tax_year":year,"method_name":method_name.strip(),"review_required":True}
