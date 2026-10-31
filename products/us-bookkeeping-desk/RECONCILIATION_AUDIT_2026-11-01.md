# US bookkeeping reconciliation audit — 2026-11-01 JST

## Official references checked (2026-11-01)
- IRS Publication 583, records and double-entry journal/ledger/source traceability: https://www.irs.gov/publications/p583
- IRS Publication 538, cash/accrual accounting methods and Form 3115 review: https://www.irs.gov/publications/p538
- IRS Publication 946 (2025), year-specific depreciation changes, not implemented in this reconciliation module: https://www.irs.gov/publications/p946
- IRS Form 3115, method changes must not be silently automated: https://www.irs.gov/forms-pubs/about-form-3115
- GnuCash feature benchmark, cleared/reconciled states and statement reconciliation: https://www.gnucash.org/features.phtml

## Gap implemented
Read-only statement-to-journal-line reconciliation for an existing USD asset account. Statement opening and closing balances, dated signed line amounts, and explicit unique statement-to-ledger-line matches are verified. A match must refer to an actual journal line in the selected account and period with the same signed cents. Journal imbalance, mismatched statement totals, duplicate source IDs, duplicate matches, wrong account, invalid dates, floating-point amounts, and inconsistent opening balances fail closed.

Unmatched statement items remain review-needed; outstanding ledger movements are surfaced rather than deleted or silently cleared. The reconciliation reports its difference, outstanding delta and a manual-confirmation flag. All computations use integer cents. The fixture reconciles the same journal to ledger, trial balance, P&L and B/S.

## Known gaps / release gates
- First version requires exact equality of statement and ledger opening balances; carried-forward outstanding items require a later reviewed implementation.
- No persisted cleared/reconciled state, audit event, statement import, bank connection, or automatic journal posting.
- Cash/accrual tax recognition and tax deductibility are not inferred. Book net income is not taxable income.
- No GUI evidence or Windows EXE artifact from this branch.
- MARKET_FIT_HOLD / COMPLIANCE_HOLD; no formal Factory promotion, Identity binding, signed MSIX, Store submission or commercial readiness.
