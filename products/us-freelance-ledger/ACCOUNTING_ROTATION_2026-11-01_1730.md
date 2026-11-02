# US Freelance Ledger — manual depreciation safety audit

Checked: 2026-11-01 JST. Draft PR #60. US-only, USD, English, cross_market_sale=false.

## IRS primary sources checked

- IRS Publication 946 (2025): https://www.irs.gov/publications/p946 — MACRS, conventions, special allowances and Section 179 vary by tax year and acquisition/service dates; its Future Developments section and 2025 law changes prohibit blindly reusing fixed percentages.
- IRS Publication 583: https://www.irs.gov/publications/p583 — preserve supporting records and accounting-method consistency.
- IRS Publication 538: https://www.irs.gov/publications/p538 — cash/accrual and method changes require independent accounting treatment.
- IRS Schedule C instructions (2025): https://www.irs.gov/instructions/i1040sc — sole proprietor scope, method-change/Form 3115 review, 1099-independent income records and state/local scope.
- IRS Publication 463: https://www.irs.gov/publications/p463 — mileage, meals and travel substantiation, no automatic deduction decision.
- IRS Publication 587: https://www.irs.gov/publications/p587 — home office is review-only.
- IRS Publication 334: https://www.irs.gov/publications/p334 — inventory/COGS, capital items and records are distinct.
- IRS Form 3115 instructions: https://www.irs.gov/instructions/i3115 — changes to tax accounting method/section 481(a) are never silently automated.
- Benchmark: https://www.gnucash.org/features.phtml — validation and reproducible reports are minimum accounting-engine expectations, not a paid differentiator.

## Concrete fix

The local `custom_tax_depreciation_schedule` previously allowed cumulative manually entered percentages above 100%, yielding depreciation larger than the original cost. It now requires finite positive cost, finite business-use percentage between 0 and 100, valid finite annual rates between 0 and 100, no duplicate year after normalization, nonempty schedule, and cumulative posted amount no greater than original cost. Rounding is deterministic to cents. No MACRS/bonus/Section 179 rates are inferred.

Added root CI fixtures in `tests/test_us_freelance_tax_assets.py`: exact 60/40 split, 50% business use, over-100%, negative, NaN, Infinity, empty schedule, duplicate year and invalid business-use inputs. These are *manual tax review* safeguards, not IRS tax calculation certification.

## Outstanding

US cash/accrual recognition timing, Form 3115 review, jurisdiction-specific sales tax, year-specific tax depreciation, original receipt archival, Windows EXE and GUI QA, market fit and signed MSIX remain separately gated. No Partner Center writes or Store submission. Verify CI for exact PR head before declaring PASS.
