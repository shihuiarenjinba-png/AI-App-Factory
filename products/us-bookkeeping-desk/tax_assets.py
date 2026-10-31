from __future__ import annotations
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP, ROUND_UP
from datetime import date
from urllib.parse import urlsplit

ROUNDING = {"floor":ROUND_DOWN,"nearest":ROUND_HALF_UP,"ceil":ROUND_UP}

def _finite(value, label):
    try:
        d=Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid {label}") from exc
    if not d.is_finite():
        raise ValueError(f"{label} must be finite")
    return d

def _percent(value, label):
    p=_finite(value,label)
    if p<0 or p>100:
        raise ValueError(f"{label} must be between 0 and 100")
    return p


def manual_sales_tax(amount_before_tax, rate_percent, rounding="nearest"):
    amount=_finite(amount_before_tax,"amount")
    rate=_percent(rate_percent,"manual sales-tax rate")
    if amount<0: raise ValueError("Amount must be non-negative")
    if rounding not in ROUNDING: raise ValueError("Unknown rounding method")
    tax=(amount*rate/100).quantize(Decimal("0.01"),rounding=ROUNDING[rounding])
    return {"net":amount,"tax":tax,"gross":amount+tax,"rate_percent":rate}

def months_in_service(first_use_date: str, year: int) -> int:
    d=date.fromisoformat(first_use_date)
    if year < d.year: return 0
    if year == d.year: return 13-d.month
    return 12

def straight_line_book_schedule(cost, first_use_date, useful_life_years, salvage_value=0, business_use_percent=100, through_year=None):
    cost=_finite(cost,"cost");salvage=_finite(salvage_value,"salvage value")
    use=_percent(business_use_percent,"business-use percent")/100
    life=int(useful_life_years)
    if cost<=0 or life<=0 or salvage<0 or salvage>=cost: raise ValueError("Check asset values")
    first=date.fromisoformat(first_use_date)
    through=int(through_year if through_year is not None else first.year+life+2)
    if through<first.year: raise ValueError("Schedule end predates service")
    annual=(cost-salvage)/Decimal(life)
    rows=[];accumulated=Decimal("0")
    for year in range(first.year,through+1):
        opening=cost-accumulated
        if opening<=salvage:break
        months=months_in_service(first_use_date,year)
        raw=min(annual*months/12,opening-salvage)
        business=(raw*use).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
        accumulated+=raw
        rows.append({"year":year,"months":months,"opening_book_value":opening,
                     "book_depreciation":raw.quantize(Decimal("0.01"),rounding=ROUND_HALF_UP),
                     "business_depreciation":business,
                     "closing_book_value":(cost-accumulated).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)})
    return rows

def custom_tax_depreciation_schedule(cost, percentages_by_year, business_use_percent=100):
    """User-supplied percentages only; NOT verified MACRS/179/bonus tax rates."""
    cost=_finite(cost,"cost")
    use=_percent(business_use_percent,"business-use percent")/100
    if cost<=0:raise ValueError("Cost must be positive")
    if not isinstance(percentages_by_year,dict):raise ValueError("Year percentages must be a mapping")
    years={}
    for key,value in percentages_by_year.items():
        year=int(key)
        if year<1900 or year>9999 or year in years:raise ValueError("Invalid or duplicate schedule year")
        years[year]=_percent(value,"depreciation percentage")
    if sum(years.values(),Decimal("0"))>100:raise ValueError("Total schedule percentages exceed 100")
    rows=[]
    for year,pct in sorted(years.items()):
        amount=(cost*pct/100).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
        business=(amount*use).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
        rows.append({"year":year,"percentage":pct,"tax_depreciation":amount,"business_depreciation":business})
    return rows

def retrospective_adjustment(schedule, posted_by_year, tax_mode=False):
    """Review-only difference, including posted-only years omitted from new schedule."""
    expected={}
    for row in schedule:
        year=int(row["year"])
        if year in expected:raise ValueError("Duplicate schedule year")
        expected[year]=_finite(row["business_depreciation"],"expected depreciation")
    posted={int(y):_finite(v,"posted depreciation") for y,v in posted_by_year.items()}
    rows=[];total=Decimal("0")
    for year in sorted(set(expected)|set(posted)):
        planned=expected.get(year,Decimal("0"));booked=posted.get(year,Decimal("0"))
        delta=planned-booked;total+=delta
        rows.append({"year":year,"expected":planned,"posted":booked,"difference":delta})
    return {"rows":rows,"total_difference":total,"auto_post":False,"review_required":True,
            "tax_mode":bool(tax_mode),
            "message":("Tax catch-up may require IRS accounting-method procedures including Form 3115/section 481(a), depending on facts."
                       if tax_mode else "Book depreciation catch-up requires review before posting.")}

def require_tax_profile(source_url, tax_year, method_name):
    """A substring containing irs.gov is not a genuine IRS source URL."""
    if not isinstance(source_url,str):raise ValueError("Tax profile requires an IRS source URL")
    try:
        u=urlsplit(source_url.strip());host=(u.hostname or "").lower().rstrip(".");port=u.port
    except ValueError as exc:
        raise ValueError("Invalid IRS source URL") from exc
    if (u.scheme!="https" or not host or not (host=="irs.gov" or host.endswith(".irs.gov"))
            or u.username is not None or u.password is not None or port not in (None,443)):
        raise ValueError("Tax profile requires a genuine HTTPS IRS source URL")
    try:year=int(tax_year)
    except (TypeError,ValueError) as exc:raise ValueError("Tax year is invalid") from exc
    if year<2000 or year>9999:raise ValueError("Tax year is invalid")
    if not isinstance(method_name,str) or not method_name.strip():raise ValueError("Method name is required")
    return {"source_url":source_url.strip(),"tax_year":year,
            "method_name":method_name.strip(),"review_required":True}
