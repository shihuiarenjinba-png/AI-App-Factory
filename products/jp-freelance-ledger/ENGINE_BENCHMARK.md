# Accounting engine benchmark

Reviewed: 2026-10-31
Market: Japan

## Principle

Benchmark and reproduce mature **accounting capabilities and calculation behavior**, not proprietary source code, brand assets, text, or UI layouts. Our commercial differentiation is a simpler local-first UI.

Primary capability references:
- GnuCash features: https://www.gnucash.org/features.phtml
- freee accounting/fixed assets: https://support.freee.co.jp/
- QuickBooks fixed assets / audit log / class tracking: https://quickbooks.intuit.com/learn-support/
- Xero reconciliation / history: https://central.xero.com/
- SAP S/4HANA Asset Accounting: https://help.sap.com/
- Oracle NetSuite Multi-Book / Fixed Assets: https://docs.oracle.com/en/cloud/saas/netsuite/

## Backend capability ladder

### Core integrity
- balanced double-entry
- split transactions
- reversible adjusting entries
- period lock / close and reopen controls
- immutable audit history for create/edit/delete/system-generated entries
- source-document reference and change provenance
- deterministic decimal/rounding rules
- accounting equation and roll-forward fixtures

### Reconciliation
- cleared / reconciled state
- statement opening balance + statement ending balance
- unmatched and duplicate detection
- reconciliation difference must reach zero before finalization
- reconciliation exception report
- undo/reopen with audit trail

### Recurring and accrual engine
- recurring journal templates
- scheduled accruals / deferrals
- automatic reversing entries
- prepaid-expense amortization schedules
- due-date reminders without silently posting when review is required

### Receivables / payables
- customer/vendor subledgers
- invoice/bill status
- partial payments
- A/R and A/P aging buckets
- bad-debt/write-off workflow as review-required where tax treatment differs

### Fixed assets
- asset master, acquisition, placed-in-service date
- book value, accumulated depreciation, remaining value
- configurable depreciation method/rates/life/salvage/business-use
- book depreciation vs tax depreciation kept separate
- prior accumulated depreciation / catch-up difference
- disposal / retirement / gain-loss calculation
- impairment or write-down support where relevant
- depreciation forecast and roll-forward report
- multiple valuation/depreciation books only where product scope justifies it

### Dimensions and management accounting
- project / department / class / location-like dimensions
- P&L and balance reports by dimension
- allocation rules with deterministic source/target totals
- budget vs actual and variance calculations

### Reporting and close
- journal
- general ledger
- trial balance
- P&L
- balance sheet
- cash movement summary
- account roll-forward
- fixed-asset register
- depreciation schedule
- reconciliation pack
- close checklist
- drill-down from report value to source entries

### Tax and jurisdiction
- country-specific rules only
- rates and tax-year profiles versioned with source URL/date
- no stale rate or tax rule hard-coding
- tax calculation separated from legal taxability/deductibility decisions
- retroactive recalculation produces adjustment candidates, not silent tax-return amendments

### Advanced enterprise-inspired architecture
- base book plus optional tax/management books
- chart-of-accounts mapping between books
- parallel valuations without corrupting primary book
- full-value postings per book, not hidden deltas
- book-specific reports and fixed-asset schedules
- foreign-currency transaction support only after base-currency accounting remains exact
- import validation, idempotency, duplicate prevention, and deterministic recalculation

## Rotation rule

Each APP rotation:
1. Re-check official/current documentation for the target country and at least one mature accounting product.
2. Identify the highest-value backend gap.
3. Implement one concrete calculation/ledger capability, not just research.
4. Add positive, boundary, rounding, reversal, retrospective, and corruption/duplicate fixtures.
5. Verify reports reconcile back to journal/ledger totals.
6. Preserve local-only operation and simple consumer UI.
7. Do not claim feature parity until fixtures and Windows QA pass.
