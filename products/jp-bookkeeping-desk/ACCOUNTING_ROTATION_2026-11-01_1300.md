# JP bookkeeping rotation — budget vs actual (2026-11-01 JST)

## Implementation (review-only Draft PR #61)
- Added `budget.py`: persistent month/account expense budgets, exact integer JPY validation, idempotent updates and audit records.
- Report uses **posted journal lines** (debit minus credit) rather than manually entered actuals; split postings and refund/reversal credits reduce actual expenses. Month boundaries isolate entries. An unbudgeted active expense suppresses the misleading aggregate remaining balance.
- Added `budget_ui.py` and an entry-screen button: "月の予算と実績", plain-language expense selection, actual/remaining/overspend, no tax-deduction claims. No automatic journal posting.
- Added `tests/test_jp_budget.py`: split entries, refunds, journal/P&L/B/S balance, month isolation, unbudgeted expense, zero budget, restart persistence, idempotency and malformed input. CI result must be checked separately.
- Does not change JP tax rates, depreciation, deduction decisions, filing, or market scope. Not yet GUI-tested at 1024×768.

## Primary-source check — retrieved 2026-11-01
1. NTA [No.2070, 青色申告制度](https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2070.htm) — bookkeeping and source-document retention matter; budget is management planning, not an official tax book.
2. NTA [No.2100, 減価償却のあらまし](https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2100.htm) — asset costs must not be treated as an ordinary expense merely because they appear in a budget.
3. NTA [No.2106, 定額法と定率法](https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2106.htm) — official method/rate/guarantee regime is acquisition-year dependent; no approximation added.
4. NTA [No.6303, 消費税率](https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6303.htm) — current standard 10% and reduced 8% are confirmed; page also flags a **future 2027-04-01 to 2029-03-31 food-rate change**. Current presets must not be treated as evergreen; tax-year/effective-date support and updated fixtures are a packaging blocker.
5. [GnuCash features](https://www.gnucash.org/features.phtml) — free product already supports budgeting, reconciliations and split transactions. Budget is baseline parity, not a proven paid differentiator.

## US separation and review — retrieved 2026-11-01
- IRS [Publication 583](https://www.irs.gov/publications/p583): journal/ledger balance, source traceability and computerized records.
- IRS [Publication 334 (2025)](https://www.irs.gov/publications/p334), [Schedule C Instructions (2025)](https://www.irs.gov/instructions/i1040sc): sole proprietor, inventory/COGS, income records and cash/accrual scope.
- IRS [Publication 538](https://www.irs.gov/publications/p538), [Form 3115 Instructions](https://www.irs.gov/instructions/i3115): method changes require a separate review; section 481(a) must not be automated.
- IRS [Publication 463 (2025)](https://www.irs.gov/publications/p463), [Publication 587 (2025)](https://www.irs.gov/publications/p587): vehicle/travel/meals and home-office substantiation.
- IRS [Publication 946 (2025)](https://www.irs.gov/publications/p946): 2025/2026 changes and tax-year-specific depreciation. No MACRS/Section 179/bonus numeric rules copied into JP code.
- US state/local sales tax and licensing remain separate from federal records. No US product was edited in this JP branch; US compliance remains independently gated.

## Status / next gate
- JP-only `market-scope.json` and `cross_market_sale=false` must remain unchanged.
- Verify GitHub CI and actual Windows GUI; do not mark UI PASS from source review.
- Next: effective-date aware JP consumption-tax rules and formal depreciation/retroactive fixtures, without automatic tax conclusions.
- MARKET_FIT_HOLD / COMPLIANCE_HOLD / EXE_HOLD / STORE_HOLD until separate evidence. No Store submission.
