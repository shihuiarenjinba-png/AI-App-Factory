from __future__ import annotations
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, ROUND_UP
from datetime import date

ROUNDING = {"floor":ROUND_DOWN,"nearest":ROUND_HALF_UP,"ceil":ROUND_UP}

def manual_sales_tax(amount_before_tax, rate_percent, rounding="nearest"):
    amount=Decimal(str(amount_before_tax)); rate=Decimal(str(rate_percent))/Decimal("100")
    if amount < 0 or rate < 0: raise ValueError("Amount and rate must be non-negative")
    tax=(amount*rate).quantize(Decimal("0.01"),rounding=ROUNDING.get(rounding,ROUND_HALF_UP))
    return {"net":amount,"tax":tax,"gross":amount+tax,"rate_percent":Decimal(str(rate_percent))}

def months_in_service(first_use_date: str, year: int) -> int:
    d=date.fromisoformat(first_use_date)
    if year < d.year: return 0
    if year == d.year: return 13-d.month
    return 12

def straight_line_book_schedule(cost, first_use_date, useful_life_years, salvage_value=0, business_use_percent=100, through_year=None):
    cost=Decimal(str(cost)); salvage=Decimal(str(salvage_value)); life=int(useful_life_years)
    if cost <= 0 or life <= 0 or salvage < 0 or salvage >= cost: raise ValueError("Check asset values")
    first=date.fromisoformat(first_use_date); through_year=int(through_year or first.year+life+2)
    use=Decimal(str(business_use_percent))/Decimal("100")
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
    cost=Decimal(str(cost)); use=Decimal(str(business_use_percent))/Decimal("100")
    if cost <= 0: raise ValueError("Cost must be positive")
    rows=[]; accumulated=Decimal("0")
    for year in sorted(int(y) for y in percentages_by_year):
        pct=Decimal(str(percentages_by_year[year]))
        if pct < 0: raise ValueError("Percentage must be non-negative")
        amount=(cost*pct/Decimal("100")).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
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
    if not source_url or "irs.gov" not in source_url.lower():
        raise ValueError("Tax profile requires an IRS source URL")
    if int(tax_year) < 2000: raise ValueError("Tax year is invalid")
    if not method_name.strip(): raise ValueError("Method name is required")
    return {"source_url":source_url,"tax_year":int(tax_year),"method_name":method_name,"review_required":True}
