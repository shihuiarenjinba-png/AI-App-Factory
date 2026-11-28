from __future__ import annotations
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP, ROUND_UP
from urllib.parse import urlsplit
from datetime import date

ROUNDING = {"floor":ROUND_DOWN,"nearest":ROUND_HALF_UP,"ceil":ROUND_UP}

def _finite(value, label):
    # bool is a subclass of int but is not a user-entered monetary/rate value.
    if isinstance(value, bool):
        raise ValueError(f"Invalid {label}")
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
        any(not label or len(label) > 63 or not label.isascii() or
            not all(ch.isalnum() or ch == "-" for ch in label) or
            label.startswith("-") or label.endswith("-") for label in host.split(".")) or
        parsed.username is not None or parsed.password is not None or
        port not in (None, 443) or not parsed.netloc):
        raise ValueError("Tax profile requires an official HTTPS IRS URL")
    year=_year(tax_year)
    if year<2000: raise ValueError("Tax year is invalid")
    if not isinstance(method_name,str) or not method_name.strip():
        raise ValueError("Method name is required")
    return {"source_url":source_url,"tax_year":year,"method_name":method_name.strip(),"review_required":True}

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

# Source-pinned Section 179 reference facts. These are not an allowable
# deduction calculation: eligibility, business-income limits, entity-level
# aggregation, elections, business use and recapture still require review.
IRS_PUB_946_2025_PDF_URL = "https://www.irs.gov/pub/irs-pdf/p946.pdf"
IRS_PUB_946_2025_HTML_URL = "https://www.irs.gov/publications/p946"
IRS_IR_2026_133_URL = "https://www.irs.gov/newsroom/irs-releases-tax-inflation-adjustments-for-tax-year-2027-taxpayers-continue-to-benefit-from-the-working-families-tax-cuts"
IRS_PUB_946_2025_VERSION = "IRS Publication 946 (2025)"
SECTION_179_SOURCE_FIXTURES = {
    2025: {
        "tax_year": 2025,
        "source_version": IRS_PUB_946_2025_VERSION,
        "source_url": IRS_PUB_946_2025_PDF_URL,
        "source_effective_period": "Tax years beginning in 2025",
        "section_179_max_usd": "2500000",
        "section_179_phaseout_threshold_usd": "4000000",
        "suv_limit_usd": "31300",
        "corroborating_source_url": None,
        "corroborating_source_version": None,
    },
    2026: {
        "tax_year": 2026,
        "source_version": IRS_PUB_946_2025_VERSION,
        "source_url": IRS_PUB_946_2025_PDF_URL,
        "source_effective_period": "Tax years beginning in 2026",
        "section_179_max_usd": "2560000",
        "section_179_phaseout_threshold_usd": "4090000",
        "suv_limit_usd": "32000",
        "corroborating_source_url": IRS_IR_2026_133_URL,
        "corroborating_source_version": "IRS IR-2026-133 (2026-11-05)",
    },
}
SPECIAL_DEPRECIATION_EFFECTIVE_AFTER = "2025-01-19"
SPECIAL_DEPRECIATION_RULE_SUMMARY = (
    "100% special depreciation may apply to certain qualified property acquired "
    "and placed in service after 2025-01-19. Qualification, election, business-use, "
    "basis and recapture rules must be reviewed; this is not a blanket rate."
)

def section_179_source_reference(tax_year):
    """Return IRS Publication 946 reference facts without calculating a deduction."""
    try:
        year = _year(tax_year)
    except ValueError:
        year = None
    fixture = SECTION_179_SOURCE_FIXTURES.get(year)
    if fixture is None:
        return {
            "status": "REVIEW_REQUIRED",
            "tax_year": year,
            "source_version": None,
            "source_url": None,
            "source_effective_period": None,
            "section_179_max_usd": None,
            "section_179_phaseout_threshold_usd": None,
            "suv_limit_usd": None,
            "special_depreciation_effective_after": SPECIAL_DEPRECIATION_EFFECTIVE_AFTER,
            "special_depreciation_rule": SPECIAL_DEPRECIATION_RULE_SUMMARY,
            "eligibility_determined": False,
            "deduction_approved": False,
            "auto_post": False,
            "reason": "TAX_YEAR_SOURCE_NOT_VERIFIED",
        }
    return {
        **fixture,
        "status": "REVIEW_REQUIRED",
        "reference_only": True,
        "special_depreciation_effective_after": SPECIAL_DEPRECIATION_EFFECTIVE_AFTER,
        "special_depreciation_rule": SPECIAL_DEPRECIATION_RULE_SUMMARY,
        "eligibility_determined": False,
        "deduction_approved": False,
        "auto_post": False,
        "source_note": "Reference limits only; not an allowable deduction calculation.",
    }

def _is_pub946_source_url(source_url):
    try:
        parsed = urlsplit(source_url)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except (TypeError, ValueError):
        return False
    return (
        parsed.scheme == "https"
        and host in {"irs.gov", "www.irs.gov"}
        and parsed.path.rstrip("/") in {"/publications/p946", "/pub/irs-pdf/p946.pdf"}
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
        and bool(parsed.netloc)
    )

def _review_date(value):
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None

def build_tax_depreciation_review(
    *,
    tax_year=None,
    source_url=None,
    source_version=None,
    acquisition_date=None,
    placed_in_service_date=None,
    asset_class=None,
    recovery_period_years=None,
    depreciable_basis_usd=None,
    business_use_percent=None,
    macrs_method=None,
    convention=None,
    section_179_election=None,
    special_depreciation_election=None,
    eligibility_confirmed=None,
    prior_depreciation_applicable=None,
    prior_depreciation_usd=None,
):
    """Build a source-bound, read-only depreciation review envelope.

    This deliberately does not apply MACRS tables, determine eligibility,
    calculate a deduction, approve an election, or write to the ledger.
    User-supplied schedules remain manual previews and must be reviewed
    separately against the source version and asset facts recorded here.
    """
    missing = []
    blocking = []
    review_reasons = [
        "HUMAN_TAX_REVIEW_REQUIRED",
        "NO_AUTOMATIC_MACRS_TABLE_APPLIED",
        "NO_LEDGER_POSTING",
    ]

    try:
        year = _year(tax_year)
    except ValueError:
        year = None
        if tax_year is None or str(tax_year).strip() == "":
            missing.append("tax_year")
        else:
            blocking.append("INVALID_TAX_YEAR")

    source_reference = section_179_source_reference(year)
    if year is not None and source_reference.get("section_179_max_usd") is None:
        blocking.append("TAX_YEAR_SOURCE_NOT_VERIFIED")

    if source_url is None or not str(source_url).strip():
        missing.append("source_url")
    else:
        try:
            require_tax_profile(source_url, year or 2025, macrs_method or "manual review")
        except ValueError:
            blocking.append("OFFICIAL_IRS_SOURCE_REQUIRED")
        if not _is_pub946_source_url(source_url):
            blocking.append("UNSUPPORTED_IRS_PUBLICATION_SOURCE")

    if source_version is None or not str(source_version).strip():
        missing.append("source_version")
    elif source_version != IRS_PUB_946_2025_VERSION:
        blocking.append("SOURCE_VERSION_MISMATCH")

    def required_text(name, value):
        if value is None or not isinstance(value, str) or not value.strip():
            missing.append(name)
            return None
        return value.strip()

    acquisition_text = required_text("acquisition_date", acquisition_date)
    placed_text = required_text("placed_in_service_date", placed_in_service_date)
    asset_class_value = required_text("asset_class", asset_class)
    method_value = required_text("macrs_method", macrs_method)
    convention_value = required_text("convention", convention)

    acquired = _review_date(acquisition_text)
    placed = _review_date(placed_text)
    if acquisition_text and acquired is None:
        blocking.append("INVALID_ACQUISITION_DATE")
    if placed_text and placed is None:
        blocking.append("INVALID_PLACED_IN_SERVICE_DATE")

    special_window = None
    if acquired and placed:
        if placed < acquired:
            blocking.append("PLACED_IN_SERVICE_BEFORE_ACQUISITION")
            special_window = "INVALID_DATE_ORDER_REVIEW_REQUIRED"
        elif acquired > date(2025, 1, 19) and placed > date(2025, 1, 19):
            special_window = "POST_2025_01_19_CANDIDATE_REVIEW_REQUIRED"
        elif acquired <= date(2025, 1, 19) and date(2024, 12, 31) < placed < date(2026, 1, 1):
            special_window = "PRE_2025_01_20_ACQUISITION_2025_SERVICE_REVIEW_REQUIRED"
        else:
            special_window = "OTHER_RULE_WINDOW_REVIEW_REQUIRED"

    recovery_period = None
    if recovery_period_years is None or str(recovery_period_years).strip() == "":
        missing.append("recovery_period_years")
    else:
        try:
            recovery_period = _finite(recovery_period_years, "recovery period")
            if recovery_period <= 0 or recovery_period > 100:
                raise ValueError("Recovery period must be greater than 0 and no more than 100 years")
        except ValueError:
            blocking.append("INVALID_RECOVERY_PERIOD")

    basis = None
    if depreciable_basis_usd is None or str(depreciable_basis_usd).strip() == "":
        missing.append("depreciable_basis_usd")
    else:
        try:
            basis = _finite(depreciable_basis_usd, "depreciable basis")
            if basis <= 0:
                raise ValueError("Depreciable basis must be positive")
        except ValueError:
            blocking.append("INVALID_DEPRECIABLE_BASIS")

    business_use = None
    if business_use_percent is None or str(business_use_percent).strip() == "":
        missing.append("business_use_percent")
    else:
        try:
            business_use = _percent(business_use_percent, "business use")
        except ValueError:
            blocking.append("INVALID_BUSINESS_USE_PERCENT")

    if method_value and method_value.lower() in {"unknown", "unspecified"}:
        blocking.append("MACRS_METHOD_UNRESOLVED")
    if convention_value and convention_value.lower() in {"unknown", "unspecified"}:
        blocking.append("MACRS_CONVENTION_UNRESOLVED")

    section_179_value = required_text("section_179_election", section_179_election)
    if section_179_value and section_179_value.lower() not in {"elect_in", "elect_out", "not_applicable", "unknown"}:
        blocking.append("INVALID_SECTION_179_ELECTION")
    elif section_179_value and section_179_value.lower() == "unknown":
        blocking.append("SECTION_179_ELECTION_UNRESOLVED")

    special_election_value = required_text("special_depreciation_election", special_depreciation_election)
    if special_election_value and special_election_value.lower() not in {
        "claim_100", "elect_40", "elect_60", "elect_out", "not_applicable", "unknown"
    }:
        blocking.append("INVALID_SPECIAL_DEPRECIATION_ELECTION")
    elif special_election_value and special_election_value.lower() == "unknown":
        blocking.append("SPECIAL_DEPRECIATION_ELECTION_UNRESOLVED")

    if not isinstance(eligibility_confirmed, bool):
        missing.append("eligibility_confirmed")
    elif not eligibility_confirmed:
        blocking.append("ELIGIBILITY_NOT_CONFIRMED")

    prior_amount = None
    if not isinstance(prior_depreciation_applicable, bool):
        missing.append("prior_depreciation_applicable")
    elif prior_depreciation_applicable:
        if prior_depreciation_usd is None or str(prior_depreciation_usd).strip() == "":
            missing.append("prior_depreciation_usd")
        else:
            try:
                prior_amount = _finite(prior_depreciation_usd, "prior depreciation")
                if prior_amount < 0:
                    raise ValueError("Prior depreciation cannot be negative")
            except ValueError:
                blocking.append("INVALID_PRIOR_DEPRECIATION")
    else:
        prior_amount = Decimal("0")

    provenance = {
        "tax_year": year,
        "source_url": source_url,
        "source_version": source_version,
        "source_effective_period": source_reference.get("source_effective_period"),
        "acquisition_date": acquisition_text,
        "placed_in_service_date": placed_text,
        "asset_class": asset_class_value,
        "recovery_period_years": str(recovery_period) if recovery_period is not None else None,
        "depreciable_basis_usd": str(basis) if basis is not None else None,
        "business_use_percent": str(business_use) if business_use is not None else None,
        "macrs_method": method_value,
        "convention": convention_value,
        "section_179_election": section_179_value,
        "special_depreciation_election": special_election_value,
        "eligibility_confirmed": eligibility_confirmed if isinstance(eligibility_confirmed, bool) else None,
        "prior_depreciation_applicable": prior_depreciation_applicable if isinstance(prior_depreciation_applicable, bool) else None,
        "prior_depreciation_usd": str(prior_amount) if prior_amount is not None else (
            str(prior_depreciation_usd) if prior_depreciation_usd is not None else None
        ),
    }
    missing = list(dict.fromkeys(missing))
    blocking = list(dict.fromkeys(blocking))
    return {
        "status": "REVIEW_REQUIRED",
        "review_required": True,
        "provenance_complete": not missing and not blocking,
        "ready_for_manual_review": not missing and not blocking,
        "missing_fields": missing,
        "blocking_reasons": blocking,
        "review_reasons": list(dict.fromkeys(review_reasons + blocking)),
        "source_reference": source_reference,
        "source_effective_date": SPECIAL_DEPRECIATION_EFFECTIVE_AFTER,
        "special_depreciation_window": special_window,
        "eligibility_determined": False,
        "deduction_approved": False,
        "calculation_performed": False,
        "calculation_preview": None,
        "auto_post": False,
        "ledger_write": False,
        "tax_advice": False,
        "provenance": provenance,
    }
