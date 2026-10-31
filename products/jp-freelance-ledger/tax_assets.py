from __future__ import annotations
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, ROUND_UP
from datetime import date

JP_CONSUMPTION_TAX_PRESETS = {
    "標準税率10%": Decimal("0.10"),
    "軽減税率8%": Decimal("0.08"),
    "非課税・対象外0%": Decimal("0"),
}

ROUNDING = {
    "切捨て": ROUND_DOWN,
    "四捨五入": ROUND_HALF_UP,
    "切上げ": ROUND_UP,
}

def consumption_tax_from_net(net_yen, rate="0.10", rounding="切捨て"):
    net=Decimal(str(net_yen))
    r=Decimal(str(rate))
    if net < 0 or r < 0: raise ValueError("金額・税率は0以上")
    tax=(net*r).quantize(Decimal("1"), rounding=ROUNDING.get(rounding, ROUND_DOWN))
    return {"net":int(net), "tax":int(tax), "gross":int(net+tax), "rate":str(r)}

def consumption_tax_from_gross(gross_yen, rate="0.10", rounding="切捨て"):
    gross=Decimal(str(gross_yen)); r=Decimal(str(rate))
    if gross < 0 or r < 0: raise ValueError("金額・税率は0以上")
    if r == 0: return {"net":int(gross),"tax":0,"gross":int(gross),"rate":"0"}
    net=(gross/(Decimal("1")+r)).quantize(Decimal("1"), rounding=ROUNDING.get(rounding, ROUND_DOWN))
    return {"net":int(net),"tax":int(gross-net),"gross":int(gross),"rate":str(r)}

def months_in_service(first_use_date: str, year: int) -> int:
    d=date.fromisoformat(first_use_date)
    if year < d.year: return 0
    if year == d.year: return 13-d.month
    return 12

def jp_depreciation_schedule(
    cost_yen: int,
    first_use_date: str,
    useful_life_years: int,
    method: str="定額法",
    straight_line_rate=None,
    declining_rate=None,
    revised_rate=None,
    guarantee_rate=None,
    business_use_percent=100,
    through_year=None,
):
    cost=int(cost_yen); life=int(useful_life_years)
    if cost <= 1 or life <= 0: raise ValueError("取得価額・耐用年数を確認してください")
    first=date.fromisoformat(first_use_date)
    through_year=int(through_year or (first.year+life+5))
    use=Decimal(str(business_use_percent))/Decimal("100")
    if use < 0 or use > 1: raise ValueError("事業使用割合は0〜100%")
    sl=Decimal(str(straight_line_rate)) if straight_line_rate is not None else (Decimal("1")/Decimal(life)).quantize(Decimal("0.001"),rounding=ROUND_HALF_UP)
    dr=Decimal(str(declining_rate)) if declining_rate is not None else None
    rr=Decimal(str(revised_rate)) if revised_rate is not None else None
    gr=Decimal(str(guarantee_rate)) if guarantee_rate is not None else None
    if method not in {"定額法","定率法"}: raise ValueError("償却方法は定額法または定率法")
    if method=="定率法" and (dr is None or rr is None or gr is None):
        raise ValueError("定率法は償却率・改定償却率・保証率を設定してください")
    rows=[]; accumulated=0; revised_base=None
    for year in range(first.year,through_year+1):
        opening=cost-accumulated
        if opening <= 1: break
        months=months_in_service(first_use_date,year)
        if months <= 0: continue
        if method=="定額法":
            raw=Decimal(cost)*sl*Decimal(months)/Decimal(12)
            note="定額法"
        else:
            preliminary=Decimal(opening)*dr
            guarantee=Decimal(cost)*gr
            if revised_base is not None:
                raw=Decimal(revised_base)*rr
                note="定率法（改定償却率）"
            elif preliminary < guarantee:
                revised_base=opening
                raw=Decimal(revised_base)*rr
                note="定率法（保証額到達→改定償却率）"
            else:
                raw=preliminary
                note="定率法"
            raw=raw*Decimal(months)/Decimal(12)
        tax_depr=int(raw.quantize(Decimal("1"),rounding=ROUND_DOWN))
        tax_depr=min(tax_depr,max(0,opening-1))
        business_depr=int((Decimal(tax_depr)*use).quantize(Decimal("1"),rounding=ROUND_DOWN))
        accumulated+=tax_depr
        rows.append({
            "year":year,"months":months,"opening_book_value":opening,
            "tax_depreciation_before_business_use":tax_depr,
            "business_depreciation":business_depr,
            "closing_book_value":cost-accumulated,"method_note":note,
        })
    return rows

def retrospective_adjustment(schedule, posted_by_year: dict[int,int]):
    rows=[]; total=0
    for row in schedule:
        year=int(row["year"]); expected=int(row["business_depreciation"])
        posted=int(posted_by_year.get(year,0)); delta=expected-posted; total+=delta
        rows.append({"year":year,"expected":expected,"posted":posted,"difference":delta})
    return {
        "rows":rows,
        "total_difference":total,
        "auto_post":False,
        "review_required":True,
        "message":"再計算差額です。過年度申告の訂正可否は自動判定せず、調整仕訳候補として確認してください。",
    }
