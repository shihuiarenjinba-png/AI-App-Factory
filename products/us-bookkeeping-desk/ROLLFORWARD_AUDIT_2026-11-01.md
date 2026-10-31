# US bookkeeping — account roll-forward and source drill-down

Checked: 2026-11-01 JST. Target: US-only Double-Entry Bookkeeping Desk, Draft PR #62 base. This is a new backend-only capability, not a Store-ready product.

## Evidence / benchmark
- IRS Publication 583 (records, journal/ledger and source-document traceability): https://www.irs.gov/publications/p583
- IRS Publication 538 (cash/accrual accounting method distinction; method-change risk): https://www.irs.gov/publications/p538
- IRS Publication 946 (2025 asset depreciation and tax-year-specific rules; not used to infer tax deduction): https://www.irs.gov/publications/p946
- GnuCash feature baseline (double entry, split transactions, reports, reconciliation): https://www.gnucash.org/features.phtml
- GnuCash transaction report capability: https://www.gnucash.org/docs/v5/C/gnucash-manual/report-classes.html
- Existing product benchmark: products/us-bookkeeping-desk/ENGINE_BENCHMARK.md

## Concrete capability
- Read-only, date-bounded account roll-forward: opening debits/credits, period movements, closing signed and normal-side balances.
- Source drill-down to journal entry ID and line ID.
- All amounts are integer USD cents; journal completeness and debit=credit are verified before any report.
- Cross-checks aggregate trial balance, P&L, and balance-sheet equation; corrupt entries cause a safe exception rather than a false PASS.
- Five product-specific regression tests cover report parity, empty periods, dates, source trace, corrupted entries and period lock preservation.

## Explicit limitations / HOLD
- This is book reporting only. Book income is not taxable income, no automatic federal/state deduction, no Form 3115 or tax depreciation decision.
- Existing cash/accrual selector is not yet an independently validated recognition engine; no method conversion claim.
- GUI, Windows EXE, Store screenshots, Identity, MSIX and full market-fit remain unverified.
- No import reconciliation, bank matching, period close adjustments or source-document attachment has been implemented by this change.
- Future integration should expose a simple account/date/report view, with a clear source-entry drill-down; never copy a competitor UI.
