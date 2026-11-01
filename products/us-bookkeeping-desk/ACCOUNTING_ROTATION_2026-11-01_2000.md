# US bookkeeping rotation — 2026-11-01 20:00 JST

## Changes implemented in this review branch
- New `budget.py`: local USD monthly spending targets by active expense account; posted journal lines are the **only** source of actuals. Zero/negative net spending is preserved; months are isolated. Targets are not journal entries.
- Beginner-facing `Plan monthly spending` dialog: choose month, category, USD target, save, then compare actual spending and remaining budget. Expense accounts are selected by name rather than typing an account code. No background posting, bank access, tax deduction, or accounting-method change.
- New tests cover split entries, refunds, persistence/restart, idempotent target updates, invalid values, month/year boundaries, and journal → trial balance → P&L/B/S invariants.
- This is an incremental budgeting feature, **not** a claim of parity with GnuCash/QuickBooks or a federal tax engine. No Windows GUI was inspected in this run.

## Federal primary-source review (checked 2026-11-01)
1. Schedule C sole proprietor scope: https://www.irs.gov/instructions/i1040sc — no eligibility or return preparation claim.
2. Cash/accrual recognition: https://www.irs.gov/publications/p538 — budgeting compares **book postings**, not tax-year recognition. Existing cash/accrual timing gap remains HOLD.
3. Method changes / Form 3115 and section 481(a): https://www.irs.gov/instructions/i3115 — no automated migration, election or retroactive tax amendment.
4. Income regardless of 1099: https://www.irs.gov/publications/p334 — no automatic exclusion based on form receipt.
5. Mileage/vehicle records: https://www.irs.gov/publications/p463 — evidence and business use require review; no mileage rate hardcoded.
6. Meals/travel business purpose: https://www.irs.gov/publications/p463 — expense budget does not establish deductibility.
7. Home-office rules: https://www.irs.gov/publications/p587 — no home-office eligibility calculation.
8. Depreciation/Section 179: https://www.irs.gov/publications/p946 — 2025 publication has year-specific changed rules and Future Developments; tax schedules stay manual-source and review-only.
9. Inventory/COGS: https://www.irs.gov/publications/p334 — spending budget is not inventory valuation or tax COGS.
10. Records retention: https://www.irs.gov/publications/p583 — no auto-deletion/retention period.
11. Computerized source documents: https://www.irs.gov/publications/p583 — budget audit action is recorded; receipts remain linked to journal via separate vault. No tamper-proof certification.
12. State/local tax and licensing: https://www.irs.gov/instructions/i1040sc — distinct from federal accounting; no nationwide rate or compliance claim.

## Depreciation/tax/retroactive audit
- US book depreciation remains separate from tax depreciation; 2025 IRS Publication 946 cannot be silently treated as a 2026 tax schedule. MACRS, convention, bonus and section 179 require tax-year-specific review. Sales-tax jurisdiction/rate remains manual. No Form 3115 or section 481(a) auto-adjustment.
- Japan products are **not modified** in this US branch. NTA official guidance rechecked 2026-11-01: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2106.htm (post-2007 straight/declining methods and 3-rate declining balance), https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2100.htm (useful life), https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2107.htm (capital expenditures). Do not apply US method/COA to JP.
- Country scope remains US-only/English/USD with `cross_market_sale=false`. No rates or thresholds added.

## Functional baseline and release gate
- Free baseline: https://www.gnucash.org/features.phtml — GnuCash already provides budgets, scheduled transactions, reconciliation, A/R/A/P. This work closes only one limited gap; no proprietary code/layout copied.
- `COMPLIANCE_HOLD`, `MARKET_FIT_HOLD`, `EXE_HOLD`, `UI_HOLD`, `PRE_IDENTITY_HOLD` until independent CI, real Windows GUI/EXE, and Factory lifecycle evidence.
- Existing Windows `verify_source` failure documented in the earlier 14:00 rotation: missing owner-generated `proposals/us-bookkeeping-desk.json`; do **not** fabricate this file in a product branch or overwrite Factory owner state.
- No Partner Center registration, Store identity request, MSIX upload, certification or publish.
