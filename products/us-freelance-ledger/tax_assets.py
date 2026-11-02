from __future__ import annotations
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP, ROUND_UP
from datetime import date
from urllib.parse import urlsplit

ROUNDING = {"floor":ROUND_DOWN,"nearest":ROUND_HALF_UP,"ceil":ROUND_UP}

def _finite(value, label):
    try:
        result=Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError(f"Invalid {label}") from exc
    if not result.is_finite():
        raise ValueError(f"Invalid {label}")
    return result

def _percent(value, label):
    result=_finite(value,label)
    if not Decimal("0") <= result <= Decimal("100"):
        raise ValueError(f"{label} must be between 0 and 100")
    return result

def manual_sales_tax(amount_before_tax, rate_percent, rounding="nearest"):
    amount=_finite(amount_before_tax,"amount")
    rate=_percent(rate_percent,"sales tax rate")
    if amount < 0:
        raise ValueError("Amount must be non-negative")
    if rounding not in ROUNDING:
        raise ValueError("Unknown rounding mode")
    tax=(amount*rate/Decimal("100")).quantize(Decimal("0.01"),rounding=ROUNDING[rounding])
    return {"net":amount,"tax":tax,"gross":amount+tax,"rate_percent":rate}

def months_in_service(first_use_date: str, year: int) -> int:
    d=date.fromisoformat(first_use_date)
    if year < d.year: return 0
    if year == d.year: return 13-d.month
    return 12

def straight_line_book_schedule(cost, first_use_date, useful_life_years, salvage_value=0, business_use_percent=100, through_year=None):
    cost=_finite(cost,"cost"); salvage=_finite(salvage_value,"salvage value"); life=int(useful_life_years)
    use=_percent(business_use_percent,"Business use")/Decimal("100")
    if cost <= 0 or life <= 0 or salvage < 0 or salvage >= cost: raise ValueError("Check asset values")
    first=date.fromisoformat(first_use_date); through_year=int(through_year) if through_year is not None else first.year+life+2
    if through_year < first.year: raise ValueError("Through year cannot precede first use")
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
    """Manual, review-only percentages; not an IRS-approved MACRS calculator."""
    cost=Decimal(str(cost)); use=Decimal(str(business_use_percent))/Decimal("100")
    if not cost.is_finite() or cost <= 0:
        raise ValueError("Cost must be positive and finite")
    if not use.is_finite() or not Decimal("0") <= use <= Decimal("1"):
        raise ValueError("Business-use percentage must be between 0 and 100")
    if not percentages_by_year:
        raise ValueError("Enter a year-specific reviewed depreciation schedule")
    normalized={}
    for key, value in percentages_by_year.items():
        year=int(key)
        if year in normalized:
            raise ValueError("Duplicate year in schedule")
        pct=Decimal(str(value))
        if not pct.is_finite() or not Decimal("0") <= pct <= Decimal("100"):
            raise ValueError("Each annual percentage must be between 0 and 100")
        normalized[year]=pct
    rows=[]; accumulated=Decimal("0")
    for year in sorted(normalized):
        pct=normalized[year]
        amount=(cost*pct/Decimal("100")).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
        if accumulated + amount > cost:
            raise ValueError("Depreciation cannot exceed original cost; review rates and years")
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
    if not isinstance(source_url,str):
        raise ValueError("Tax profile requires an IRS source URL")
    parsed=urlsplit(source_url)
    host=parsed.hostname
    if parsed.scheme!="https" or not host or not (host=="irs.gov" or host.endswith(".irs.gov")):
        raise ValueError("Tax profile requires an HTTPS IRS source URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Tax profile source URL must not contain credentials")
    if int(tax_year) < 2000: raise ValueError("Tax year is invalid")
    if not isinstance(method_name,str) or not method_name.strip(): raise ValueError("Method name is required")
    return {"source_url":source_url,"tax_year":int(tax_year),"method_name":method_name.strip(),"review_required":True}


def business_mileage_2026_review(trip_date, miles, purpose="business"):
    """Date-scoped IRS *estimate*, never an approved deduction or auto-post.

    2026 is split at July 1 by IRS Announcement 2026-11. Unsupported years
    and non-business purposes are REVIEW_REQUIRED with no business estimate.
    This does not establish eligibility, log substantiation, or method choice.
    """
    if not isinstance(trip_date, str) or len(trip_date) != 10:
        raise ValueError("Trip date must be YYYY-MM-DD")
    try:
        driven = date.fromisoformat(trip_date)
    except ValueError as exc:
        raise ValueError("Invalid trip date") from exc
    if driven.isoformat() != trip_date:
        raise ValueError("Trip date must be YYYY-MM-DD")
    distance = _finite(miles, "miles")
    if distance < 0 or distance > Decimal("10000000"):
        raise ValueError("Miles must be between 0 and 10000000")
    base = {"status": "REVIEW_REQUIRED", "review_required": True,
            "auto_post": False, "deduction_approved": False,
            "trip_date": trip_date, "purpose": purpose,
            "miles": distance, "rate_usd_per_mile": None,
            "estimate_usd": None, "source_url": None}
    if driven.year != 2026:
        return {**base, "reason": "TAX_YEAR_UNSUPPORTED_REVIEW_REQUIRED"}
    if purpose != "business":
        return {**base, "reason": "NON_BUSINESS_PURPOSE_REVIEW_REQUIRED"}
    if driven < date(2026, 7, 1):
        rate = Decimal("0.725")
        source = "https://www.irs.gov/newsroom/irs-sets-2026-business-standard-mileage-rate-at-725-cents-per-mile-up-25-cents"
    else:
        rate = Decimal("0.76")
        source = "https://www.irs.gov/irb/2026-29_irb"
    return {**base, "reason": "BUSINESS_MILEAGE_METHOD_AND_LOG_REVIEW_REQUIRED",
            "rate_usd_per_mile": rate,
            "estimate_usd": (distance * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "source_url": source}
