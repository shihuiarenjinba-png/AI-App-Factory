from __future__ import annotations
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP, ROUND_UP
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

def _finite_number(value, label):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{label}は有限の数値で指定してください") from exc
    if not n.is_finite():
        raise ValueError(f"{label}は有限の数値で指定してください")
    return n


def _yen_amount(value, label):
    n = _finite_number(value, label)
    if n < 0 or n != n.to_integral_value() or n > 2**63 - 1:
        raise ValueError(f"{label}は0以上の整数円で指定してください")
    return n


def _rate(value, label, allow_zero=False):
    n = _finite_number(value, label)
    if n < 0 or n > 1 or (not allow_zero and n == 0):
        raise ValueError(f"{label}は0から1の範囲で指定してください")
    return n


def _rounding(value):
    if value not in ROUNDING:
        raise ValueError("端数処理は切捨て・四捨五入・切上げから選択してください")
    return ROUNDING[value]


def consumption_tax_from_net(net_yen, rate="0.10", rounding="切捨て"):
    net=_yen_amount(net_yen, "税抜金額")
    r=_rate(rate, "消費税率", allow_zero=True)
    tax=(net*r).quantize(Decimal("1"), rounding=_rounding(rounding))
    return {"net":int(net), "tax":int(tax), "gross":int(net+tax), "rate":str(r)}

def consumption_tax_from_gross(gross_yen, rate="0.10", rounding="切捨て"):
    gross=_yen_amount(gross_yen, "税込金額"); r=_rate(rate, "消費税率", allow_zero=True)
    rounding_mode=_rounding(rounding)
    if r == 0: return {"net":int(gross),"tax":0,"gross":int(gross),"rate":"0"}
    net=(gross/(Decimal("1")+r)).quantize(Decimal("1"), rounding=rounding_mode)
    return {"net":int(net),"tax":int(gross-net),"gross":int(gross),"rate":str(r)}

def validate_jp_depreciation_method(asset_class: str, first_use_date: str, method: str):
    d=date.fromisoformat(first_use_date)
    if d < date(2007,4,1):
        raise ValueError("平成19年3月31日以前取得は旧定額法・旧定率法の別制度です。現行計算に混ぜず旧制度レビューへ送ってください。")
    key=(asset_class or "").strip().lower()
    if method=="定率法":
        if key in {"建物","building"} and d >= date(1998,4,1):
            raise ValueError("平成10年4月1日以後取得の建物は定額法のみの扱いです。")
        if key in {"建物附属設備","構築物","building equipment","structure"} and d >= date(2016,4,1):
            raise ValueError("平成28年4月1日以後取得の建物附属設備・構築物は定額法のみの扱いです。")
    return True

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
    asset_class: str="その他",
    straight_line_rate=None,
    declining_rate=None,
    revised_rate=None,
    guarantee_rate=None,
    business_use_percent=100,
    through_year=None,
):
    cost_decimal=_yen_amount(cost_yen, "取得価額")
    life_decimal=_finite_number(useful_life_years, "耐用年数")
    if cost_decimal <= 1 or life_decimal <= 0 or life_decimal != life_decimal.to_integral_value():
        raise ValueError("取得価額・耐用年数を確認してください")
    cost=int(cost_decimal); life=int(life_decimal)
    first=date.fromisoformat(first_use_date)
    validate_jp_depreciation_method(asset_class,first_use_date,method)
    if through_year is None:
        through_year=first.year+life+5
    else:
        year_decimal=_finite_number(through_year, "計算終了年")
        if year_decimal != year_decimal.to_integral_value() or not first.year <= int(year_decimal) <= 9999:
            raise ValueError("計算終了年は供用開始年以降の整数年にしてください")
        through_year=int(year_decimal)
    use=_finite_number(business_use_percent, "事業使用割合")/Decimal("100")
    if use < 0 or use > 1: raise ValueError("事業使用割合は0〜100%")
    if method=="定額法" and straight_line_rate is None:
        raise ValueError("定額法の償却率を設定してください。国税庁の耐用年数別表の正式率を使用します。")
    sl=_rate(straight_line_rate, "定額法償却率") if straight_line_rate is not None else None
    dr=_rate(declining_rate, "定率法償却率") if declining_rate is not None else None
    rr=_rate(revised_rate, "改定償却率") if revised_rate is not None else None
    gr=_rate(guarantee_rate, "保証率") if guarantee_rate is not None else None
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


# Reviewed 2026-11-01 against NTA No.6303/6102. This is a cautious
# calculator gate, not a taxability or deduction determination.
JP_TAX_RATE_SOURCE = "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6303.htm"
JP_TAX_REVIEWED_ON = "2026-11-01"
JP_TAX_AUTOCALC_UNTIL = date(2027, 3, 31)
JP_TAX_CATEGORIES = {
    "標準課税": Decimal("0.10"),
    "飲食料品（酒類・外食を除く）": Decimal("0.08"),
    "定期購読新聞": Decimal("0.08"),
}


def assess_jp_consumption_tax(transaction_date: str, category: str) -> dict:
    """Rate hint only for explicitly user-selected category in verified period.

    NTA announces a food-rate change starting 2027-04-01. No numeric rate is
    inferred for that period or for dates beyond our reviewed rate window.
    """
    try:
        when = date.fromisoformat(transaction_date)
    except (TypeError, ValueError) as exc:
        raise ValueError("取引日はYYYY-MM-DD形式で入力してください") from exc
    if category not in (*JP_TAX_CATEGORIES, "要確認"):
        raise ValueError("課税区分を選び直してください")
    result = {
        "transaction_date": when.isoformat(), "category": category,
        "review_required": True, "rate": None,
        "source_url": JP_TAX_RATE_SOURCE, "reviewed_on": JP_TAX_REVIEWED_ON,
    }
    if when < date(2019, 10, 1):
        result["reason"] = "旧税率・経過措置の可能性があるため、過去の取引は個別確認してください。"
    elif when > JP_TAX_AUTOCALC_UNTIL:
        result["reason"] = "2027年4月から飲食料品の税率変更が告知されています。新しい公式税率と適用時期を確認してください。"
    elif category == "要確認":
        result["reason"] = "非課税・免税・対象外かどうかは自動判定しません。取引内容を確認してください。"
    else:
        result["review_required"] = False
        result["rate"] = str(JP_TAX_CATEGORIES[category])
        result["reason"] = "選択した区分での参考計算です。課税区分と端数処理を確認してください。"
    return result


def consumption_tax_review(net_yen, transaction_date: str, category: str, rounding="切捨て") -> dict:
    """Return no tax amount when a date/category requires manual review."""
    net = int(_yen_amount(net_yen, "税抜金額"))
    _rounding(rounding)
    result = assess_jp_consumption_tax(transaction_date, category)
    result["net"] = net
    result["tax"] = None
    result["gross"] = None
    if not result["review_required"]:
        result.update(consumption_tax_from_net(net, result["rate"], rounding))
    return result
