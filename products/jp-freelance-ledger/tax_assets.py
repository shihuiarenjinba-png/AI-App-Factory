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

def _validated_tax_inputs(amount, rate, rounding):
    try:
        yen = Decimal(str(amount))
        tax_rate = Decimal(str(rate))
    except (ValueError, ArithmeticError) as exc:
        raise ValueError("金額・税率を数値で入力してください") from exc
    if (not yen.is_finite() or yen < 0 or yen != yen.to_integral_value()
            or yen > Decimal("1000000000000000")):
        raise ValueError("金額は0円以上の整数で入力してください")
    if not tax_rate.is_finite() or tax_rate < 0 or tax_rate > 1:
        raise ValueError("税率は0以上1以下の小数で入力してください")
    if rounding not in ROUNDING:
        raise ValueError("端数処理方法を確認してください")
    return yen, tax_rate


def consumption_tax_from_net(net_yen, rate="0.10", rounding="切捨て"):
    net, r = _validated_tax_inputs(net_yen, rate, rounding)
    tax = (net*r).quantize(Decimal("1"), rounding=ROUNDING[rounding])
    return {"net": int(net), "tax": int(tax), "gross": int(net+tax), "rate": str(r)}


def consumption_tax_from_gross(gross_yen, rate="0.10", rounding="切捨て"):
    gross, r = _validated_tax_inputs(gross_yen, rate, rounding)
    if r == 0:
        return {"net": int(gross), "tax": 0, "gross": int(gross), "rate": "0"}
    net = (gross/(Decimal("1")+r)).quantize(Decimal("1"), rounding=ROUNDING[rounding])
    return {"net": int(net), "tax": int(gross-net), "gross": int(gross), "rate": str(r)}

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
    cost=int(cost_yen); life=int(useful_life_years)
    if cost <= 1 or life <= 0: raise ValueError("取得価額・耐用年数を確認してください")
    first=date.fromisoformat(first_use_date)
    validate_jp_depreciation_method(asset_class,first_use_date,method)
    through_year=int(through_year or (first.year+life+5))
    use=Decimal(str(business_use_percent))/Decimal("100")
    if use < 0 or use > 1: raise ValueError("事業使用割合は0〜100%")
    if method=="定額法" and straight_line_rate is None:
        raise ValueError("定額法の償却率を設定してください。国税庁の耐用年数別表の正式率を使用します。")
    sl=Decimal(str(straight_line_rate)) if straight_line_rate is not None else None
    dr=Decimal(str(declining_rate)) if declining_rate is not None else None
    rr=Decimal(str(revised_rate)) if revised_rate is not None else None
    gr=Decimal(str(guarantee_rate)) if guarantee_rate is not None else None
    if method not in {"定額法","定率法"}: raise ValueError("償却方法は定額法または定率法")
    if method=="定率法" and (dr is None or rr is None or gr is None):
        raise ValueError("定率法は償却率・改定償却率・保証率を設定してください")
    # Only user-entered/source-verified rates are allowed; never infer tax rates.
    rates = [sl] if method=="定額法" else [dr,rr,gr]
    if any(rate is None or not rate.is_finite() or rate<=0 or rate>1 for rate in rates):
        raise ValueError("償却率・改定償却率・保証率は0超〜1以下の正式率を入力してください")
    if through_year < first.year:
        raise ValueError("終了年は供用開始年以降を指定してください")
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

def retrospective_adjustment(schedule, posted_by_year: dict[int, int]):
    """Recompute every affected year, including years with posted-only amounts.

    Review-only difference report; never post journals or amend tax returns.
    """
    if not isinstance(posted_by_year, dict):
        raise ValueError("既計上額は年別の辞書で指定してください")
    expected_by_year = {}
    for row in schedule:
        year = int(row["year"])
        expected = int(row["business_depreciation"])
        if year < 1 or year > 9999 or year in expected_by_year or expected < 0:
            raise ValueError("償却スケジュールの年・金額が不正です")
        expected_by_year[year] = expected
    posted = {}
    for year, value in posted_by_year.items():
        if type(year) is not int or not 1 <= year <= 9999:
            raise ValueError("既計上額の年を確認してください")
        if isinstance(value, bool):
            raise ValueError("既計上額は整数の円で入力してください")
        try:
            amount = int(value)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError("既計上額は整数の円で入力してください") from exc
        if str(value).strip() != str(amount) or abs(amount) > 10**15:
            raise ValueError("既計上額は整数の円で入力してください")
        posted[year] = amount
    rows = []
    total = 0
    for year in sorted(set(expected_by_year) | set(posted)):
        expected = expected_by_year.get(year, 0)
        amount = posted.get(year, 0)
        delta = expected - amount
        total += delta
        rows.append({"year": year, "expected": expected, "posted": amount,
                     "difference": delta, "posted_only": year not in expected_by_year})
    return {
        "rows": rows,
        "total_difference": total,
        "auto_post": False,
        "review_required": True,
        "message": "再計算差額です。過年度申告の訂正可否は自動判定せず、調整仕訳候補として確認してください。",
    }
