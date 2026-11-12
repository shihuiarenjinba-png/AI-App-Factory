# US bookkeeping implementation rotation — 2026-11-01 JST

Product: us-bookkeeping-desk; US market only; USD; no federal or state tax filing.
Status: **COMPLIANCE_HOLD / MARKET_FIT_HOLD / GUI_HOLD / MSIX_HOLD**.

## Sources reviewed (2026-11-01)

| Official source | Applicable engineering decision |
| --- | --- |
| IRS Pub 583 (12/2024), https://www.irs.gov/publications/p583 | Double-entry books must reconcile journals, ledgers, source documents and reports. Add read-only account roll-forward with source-line drill-down; do not substitute for source-document retention. |
| IRS Pub 538 (01/2022), https://www.irs.gov/publications/p538 | Cash/accrual method selection is not tax eligibility. Existing method lock stays; no automatic conversion. |
| IRS Form 3115, https://www.irs.gov/forms-pubs/about-form-3115 | Method changes may require consent/procedures; retrospective tax differences remain REVIEW REQUIRED and never auto-post. |
| IRS Pub 334 (2025), https://www.irs.gov/publications/p334 | Sole proprietor/Schedule C scope, all business income even without a 1099, inventory/COGS require context. This remains general bookkeeping only. |
| IRS Pub 463 (2025), https://www.irs.gov/publications/p463 | Mileage, vehicle, meals and travel evidence/business purpose must be reviewed; no automated deductions. |
| IRS Pub 587 (2025), https://www.irs.gov/publications/p587 | Home office qualification not inferred. |
| IRS Pub 946 (2025), https://www.irs.gov/publications/p946 | 2025 legislative changes to bonus depreciation/Section 179 mean historical tables cannot be blindly reused. No automatic MACRS/bonus/179 schedule or fixed tax rates introduced. |
| IRS Schedule C instructions, https://www.irs.gov/instructions/i1040sc | Book net income is not automatically taxable income; state/local tax and licensing are separate. |
| GnuCash features, https://www.gnucash.org/features.phtml | Double-entry, split transactions, reconciliation and reports are free baseline features. Implement capability, not proprietary UI/code. |

Official publication years differ from review date. Recheck Future Developments and current tax-year guidance before release. This review is not an IRS compliance certification.

## Backend gap implemented: account roll-forward

New products/us-bookkeeping-desk/rollforward.py provides:
- Start/end book balances by active chart account in exact integer cents, period debit/credit movements and normal-side presentation.
- Full-chart opening balance, period debits/credits and closing balance consistency flags; filtered subsets do not claim to balance by themselves.
- Drill-down from an account's movement to source journal entry ID, line ID, date, description and running balance.
- Read-only behavior: no new journal, tax, accounting method, reconciliation, or audit records are written.
- Strict date and account selection validation.

New tests/test_us_account_rollforward.py covers opening balances, partial receipt, split expense, reversing journal, report invariance, filtered accounts, invalid dates, source drill-down and persistence across restart. All roll-forward totals must match journal -> ledger -> trial balance -> P&L -> B/S; tests must pass in GitHub CI before calling this PASS.

## Tax/depreciation input safety

Hardened products/us-bookkeeping-desk/tax_assets.py:
- Reject nonfinite monetary/rate values, invalid business-use percentage outside 0-100, negative or over-100 manual annual tax percentages and total depreciation percentages over 100.
- Reject rounding accumulation above cost, ambiguous duplicate years and unsafe/non-IRS HTTP source URLs.
- Keep jurisdiction-specific sales-tax rates manual; tax-year/source-profile remains review-only.
- Preserve retrospective difference review and explicit Form 3115/section 481(a) warning. Never auto-post tax adjustments.

New tests/test_us_tax_asset_guards.py exercises boundary and invalid inputs, duplicate years, rounding and URL spoofing. No 2026 rate, mileage, bonus depreciation or Section 179 threshold is hardcoded.

## Remaining commercial blockers

- Cash/accrual recognition timing is not modeled; selection alone does not establish legal method eligibility.
- No verified source-document linkage, tax-year-specific depreciation decision engine, complete backup/restore QA or consumer-facing roll-forward UI.
- Real Windows EXE/1024x768 GUI, screenshot and install/launch/restart QA not verified here.
- No Partner Center registration, Identity binding, MSIX signing or Store submission.
- Keep MARKET_FIT_HOLD and COMPLIANCE_HOLD until official-scope review, feature validation, Windows QA and buyer-value gate independently pass.
