# APP rotation — JP bookkeeping integrity (2026-11-01 JST)

## Result and boundaries
- Product: `jp-bookkeeping-desk`, JP / JPY only. `cross_market_sale=false` remains mandatory.
- Added `reporting.py`: read-only account roll-forward (opening, debit/credit movement, closing), source journal entry/line drill-down, all-account period controls and period P/L.
- Added `tests/test_jp_account_roll_forward.py`: split entries, reversing corrections, contra-asset sign, restart persistence, zero activity, invalid periods, and journal -> ledger -> trial -> P/L -> B/S invariants.
- Hardened `tax_assets.py`: reject NaN/Infinity, fractional JPY, invalid rounding, rate outside [0,1], fractional life, invalid service percentages and backwards calculation years. Added regression fixtures.
- These are backend capabilities only. No consumer GUI, actual Windows installation, signed MSIX, tax-return calculation or automatic tax decision is certified.
- `period_net_income_yen` is book profit, **not** taxable income.

## Official primary-source verification — 2026-11-01
Japan:
1. NTA No.2080, records and supporting documents for white-return filers: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2080.htm
   - Impact: preserve traceable daily entries and source evidence; do not assert automatic compliance with storage rules.
2. NTA No.2106, straight-line vs declining-balance depreciation: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2106.htm
   - Impact: require official method-specific rate, revised rate and guarantee rate; reject unsafe numeric inputs rather than inventing rates.
3. NTA No.2105, legacy pre-April 2007 depreciation: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2105.htm
   - Impact: keep older acquisition regimes separate; no current-formula shortcut.
4. NTA No.5930, corporate records retention: https://www.nta.go.jp/taxes/shiraberu/taxanswer/hojin/5930.htm
   - Impact: legal retention differs by taxpayer and circumstances; no one-size-fits-all retention claim.

US cross-market safety references (US product logic **not** implemented here):
1. IRS Pub 583 (journals, ledgers, computerized record source trace): https://www.irs.gov/publications/p583
2. IRS Pub 538 (cash/accrual and method-change approval): https://www.irs.gov/publications/p538
3. IRS Schedule C instructions (sole proprietor, 1099, state/local separate): https://www.irs.gov/instructions/i1040sc
4. IRS Pub 587 (home office source documentation): https://www.irs.gov/publications/p587
5. IRS Pub 946 (2025 publication, depreciation, MACRS, Section 179, year-specific): https://www.irs.gov/publications/p946
6. IRS Form 3115 instructions (method changes/consent): https://www.irs.gov/instructions/i3115
7. IRS Pub 334 (sole proprietor, inventory/COGS): https://www.irs.gov/publications/p334
8. IRS Pub 463 (mileage, travel, meals substantiation): https://www.irs.gov/publications/p463

No US tax year numeric constant or US tax rate was imported into JP code. No automatic deductions, tax filings, or accounting-method changes.

## Benchmark
- GnuCash features: https://www.gnucash.org/features.phtml — free double-entry, reconciliations and transaction reports set the baseline.
- `ENGINE_BENCHMARK.md` remains the feature comparison contract (freee, QuickBooks, Xero, SAP S/4HANA, Oracle NetSuite). Functional parity only; no proprietary source, layouts, or branding copied.

## Remaining gates
- Confirm official rate tables by asset acquisition year and exact category, tax-inclusive/exclusive rules, partial-year proration, small-asset treatment and retrospective adjustment with human review.
- Verify real Windows EXE and GUI at 1024x768, first-run flows, EN/JA where applicable, backup/restore and screenshots.
- MARKET_FIT_HOLD / COMPLIANCE_HOLD until market and regulatory evidence, review and tests support promotion.
- Do not submit or publish to Microsoft Store without human approval.
