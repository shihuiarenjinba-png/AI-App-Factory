# US bookkeeping — account roll-forward and depreciation guard

Reviewed: **2026-11-01 (JST)**. Scope: `us-bookkeeping-desk`, United States only, USD, local-only. Implementation is in a dedicated stacked Draft PR; do not treat it as merged or Store-ready.

## Primary-source and benchmark check

| Evidence | Official source | Engineering consequence |
| --- | --- | --- |
| Journals, ledgers, balanced double-entry, computerized-record traceability | [IRS Publication 583](https://www.irs.gov/publications/p583), 12/2024 edition, checked 2026-11-01 | Report derives account opening/activity/closing balances from journal-line IDs, checks the complete journal even for filtered reports, and exposes entry/line drill-down. It does not silently repair corrupted journals. |
| Cash versus accrual recognition | [IRS Publication 538](https://www.irs.gov/publications/p538), 01/2022 edition, checked 2026-11-01 | Accounting-method label is preserved but is **not** a tax-method eligibility or cash/accrual recognition engine; compliance HOLD continues. |
| Book versus tax depreciation and placed-in-service date | [IRS Publication 946 (2025)](https://www.irs.gov/publications/p946), checked 2026-11-01 | User-entered percentages are an arithmetic preview only. Reject non-finite values, business-use over 100%, and aggregate percentages over 100%. Do not hardcode MACRS, Section 179, or bonus-depreciation rates for 2026. |
| Method changes and section 481(a) | [IRS Form 3115 instructions](https://www.irs.gov/instructions/i3115), checked 2026-11-01 | Retrospective difference remains `REVIEW_REQUIRED`; no automated amendment, method conversion, or posting. |
| Mature accounting feature baseline | [GnuCash features](https://www.gnucash.org/features.phtml), [QuickBooks support](https://quickbooks.intuit.com/learn-support/), [Xero support](https://central.xero.com/) | Add account roll-forward and traceable journal drill-down without copying UI or proprietary code. |

## Concrete changes

1. `rollforward.py`: exact integer-cent opening + activity = closing per account; natural-sign debit/credit handling; date/account filtering; complete-journal balance gate; journal-line provenance and running balance; no writes.
2. `tax_assets.py`: guard non-finite sales-tax and depreciation inputs, reject impossible depreciation percentages and business-use ratios, and require a real HTTPS `irs.gov` hostname for tax-source metadata. Source URL validation is **not** a tax-law approval.
3. `tests/test_us_account_rollforward.py` and `tests/test_us_tax_assets_guard.py`: deterministic positive/negative, period boundary, restart, filtered-account, corruption, percentage, and URL spoofing fixtures; full Factory CI must verify integration with `core.Store`.

## Unchanged gates

`COMPLIANCE_HOLD`, `MARKET_FIT_HOLD`, `GUI_HOLD`, `EXE_HOLD`, `PRE_IDENTITY_HOLD` and `STORE_HOLD` remain. Current work does not implement cash/accrual recognition, source-document attachments, secure backup/restore, signed MSIX, Windows UI validation, or any federal/state tax-return calculation. `net_income` is bookkeeping net income, **not** taxable income. Partner Center registration and Store submission are prohibited until independent gates pass.

Country boundary: `market-scope.json` must remain US-only, USD, `cross_market_sale=false`. Do not add Japanese tax terminology or Japan-market availability to this product.
