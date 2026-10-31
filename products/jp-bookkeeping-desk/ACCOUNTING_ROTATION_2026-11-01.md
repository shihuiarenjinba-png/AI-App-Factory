# Accounting rotation evidence — 2026-11-01 (JST)

## Scope and release gate
- Four **independent** country-scoped products: jp-freelance-ledger (JP/JPY), us-freelance-ledger (US/USD), jp-bookkeeping-desk (JP/JPY), us-bookkeeping-desk (US/USD).
- Confirmed `products/jp-bookkeeping-desk/market-scope.json`: `store_markets=["JP"]`, `cross_market_sale=false`.
- This rotation implements **one JP bookkeeping backend gap**. It does not establish market-fit, Windows GUI QA, tax compliance, or Store readiness for any product.
- No tax return filing, deduction eligibility, accounting-method change, or retrospective filing correction is automated.

## Primary sources checked (2026-11-01)
### Japan / NTA
1. Blue-return bookkeeping, documents, retention: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2070.htm
   - Design impact: preserve journal, ledger, source-document traceability; no assertion of compliant electronic recordkeeping without separate validation.
2. Consumption tax standard 10% and reduced 8%, transitional/future changes: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6303.htm
   - Design impact: existing presets are examples, not an eternal universal tax rate. Date/jurisdiction/applicability must be confirmed before tax-related automation.
3. Current straight-line/declining-balance method, revised and guarantee rates, acquisition-date differences: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2106.htm
   - Design impact: use official rate tables and explicit rate/life settings; no guessed declining-balance rate.
4. Pre-2007 legacy depreciation: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2105.htm
   - Design impact: legacy assets remain separate review; do not apply post-2007 formulas.
5. Capital improvement vs repair: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2107.htm
   - Design impact: asset classification requires evidence and review; no automatic tax-deductibility conclusion.

### United States / IRS
1. Recordkeeping, cash/accrual, source documents: https://www.irs.gov/publications/p583
2. Small-business/sole-proprietor income and inventory: https://www.irs.gov/publications/p334
3. Cash/accrual and method changes: https://www.irs.gov/publications/p538
4. Form 3115/consent and future developments: https://www.irs.gov/instructions/i3115
5. Schedule C scope, 1099 and state/local separation: https://www.irs.gov/instructions/i1040sc
6. Mileage, travel, meals, business-purpose substantiation: https://www.irs.gov/publications/p463
7. Home-office tests and records: https://www.irs.gov/publications/p587
8. MACRS, conventions, Section 179, bonus depreciation, annual changes: https://www.irs.gov/publications/p946

Design impact for both US products: federal vs state/local/sales tax separate; method changes and section 481(a) review required; book net income must not be labeled taxable income; 1099 absence must not suppress recorded income; vehicle/travel/meals/home-office and inventory/COGS require source documents and human review; book and tax depreciation separate; no universal US sales-tax rate or unversioned tax-year constants. IRS Pub 946 is currently marked **2025 returns**, so do not silently apply its numeric limits to 2026. Source pages contain Future Developments warnings. No automatic deduction or filing decisions.

## Mature-engine comparison
GnuCash: https://www.gnucash.org/features.phtml — free double-entry, split, cleared/reconciled transactions, statement reconciliation, recurring entries, A/R and A/P, budgets. These are baseline capabilities rather than unique paid differentiation. Other benchmark references in `ENGINE_BENCHMARK.md` remain functional targets only; no source/UI/branding copied.

## Concrete backend change: JP bank statement reconciliation
- Added `products/jp-bookkeeping-desk/reconciliation.py` and `tests/test_jp_bank_reconciliation.py`.
- Operator-entered opening/closing JPY statement balances; only JP bank-account codes 1100/1110/1120; no auto journal postings.
- Persistent OPEN/FINALIZED sessions, per-line selection, idempotent mark/finalize, date and account validation, prior-statement balance continuity, unmatched-line report, zero-difference finalization gate, audit events.
- Regression fixture covers two statement periods, missing/mismatched lines, wrong account, duplicate selections, future-dated entries, invalid amounts, persistence, and journal → ledger → trial balance → P/L → B/S invariants.
- Initial statement opening balance is **operator-supplied** and must be cross-checked with historical bank evidence. No bank login/import or external API is involved.
- This is backend-only. Consumer GUI flow, real Windows EXE, screenshots, and installation QA remain **NOT VERIFIED**. Do not market this as completed reconciliation UI.

## Remaining compliance and engine gaps
- JP: confirm tax year, applicable rate, invoice/electronic records retention, asset category, life/rates, month proration, tax-inclusive/exclusive accounting, retroactive adjustment review.
- US: country-specific evidence pack per PR, state/local tax and sales-tax jurisdiction settings, 2026-specific IRS updates, source-document retention, depreciation books separated, method-change REVIEW REQUIRED.
- Both: source-document linking, reconciliation undo with audit, import idempotency, A/R and A/P aging, asset lifecycle and disposal, real GUI QA.
- All four products remain **MARKET_FIT_HOLD / COMMERCIAL_QA_HOLD** pending product-specific evidence. This rotation makes no claim that the other three branches were modified.
