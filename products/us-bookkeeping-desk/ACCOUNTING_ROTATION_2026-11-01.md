# US bookkeeping rotation — 2026-11-01

Product: `us-bookkeeping-desk` · Market: US only · Currency: USD
Status: **COMPLIANCE_HOLD / MARKET_FIT_HOLD / Windows GUI QA pending**.
No tax return, automatic deduction, certification or Store submission is authorized.

## Primary-source review (checked 2026-11-01)

| Regulatory item | Official reference | Engineering decision |
| --- | --- | --- |
| Sole proprietor / Schedule C scope | https://www.irs.gov/instructions/i1040sc (2025 instructions) | General bookkeeping only; no automatic eligibility decision |
| Cash vs accrual | https://www.irs.gov/publications/p538 (01/2022 publication) | Selection locked after first entry; **recognition timing still not modeled**, HOLD |
| Method change / consent / Form 3115 | https://www.irs.gov/instructions/i3115 (12/2022 instructions) | No automated conversion or section 481(a) posting; manual review |
| Income without 1099 | https://www.irs.gov/publications/p334 (2025 publication) | Never omit business income because no 1099 was issued |
| Vehicle and mileage records | https://www.irs.gov/publications/p463 (2025 publication) | Evidence/business purpose review; no automatic deduction |
| Meals and travel | https://www.irs.gov/publications/p463 | Business purpose and substantiation review |
| Home office | https://www.irs.gov/publications/p587 (2025 publication) | No automatic home-office qualification |
| Capitalization, depreciation, Section 179 | https://www.irs.gov/publications/p946 (2025 publication) | Tax-year/profile-specific source required; **2025 legislative changes noted**, no automatic 2026 tax rates |
| Inventory / COGS | https://www.irs.gov/publications/p334 | Special inventory treatment outside general journal engine |
| Record retention | https://www.irs.gov/publications/p583 (12/2024 publication) | No universal automatic deletion period |
| Computerized records and source-document traceability | https://www.irs.gov/publications/p583 | Bank statement review is audit support, **not** a substitute for document references/backup |
| State/local tax and licenses | https://www.irs.gov/instructions/i1040sc | Separate jurisdiction; no national sales tax or license claims |

The linked official publications have different publication years. Recheck each **Future Developments** section before release or use for a later tax year. Neither an old tax table nor a user-selected accounting method establishes current-year legal eligibility.

## Benchmark and concrete backend gap

Reviewed `ENGINE_BENCHMARK.md` (GnuCash, QuickBooks, Xero, SAP and NetSuite capability references). The existing general journal and reports were missing statement reconciliation.

Implemented `reconciliation.py` with:

- Explicit statement opening/closing balances and journal-line selection; no bank API.
- Exact cents arithmetic, zero-difference gate, duplicate/foreign-line rejection and previous-period opening consistency.
- Outstanding line carry-forward, immutable finalized line mapping, persistent history and audit entry.
- Transactional finalization with fresh validation under SQLite write lock.
- Guard against backdated journal postings into a finalized reconciliation period.
- Journal/ledger/trial/P&L/B/S unchanged by reconciliation; net income remains **book**, not taxable income.

New fixtures in `tests/test_us_bank_reconciliation.py` cover matching, unmatched carry-forward, restart, duplicates, nonzero difference, foreign lines, confirmation, backdating and journal/report invariance.

**Limitations:** The backend is not yet exposed through the consumer Tkinter UI. There is no statement import, source-document attachment, verified bank feed, undo/reopen workflow, cash/accrual recognition engine, or complete backup/restore QA. Do not market it as fully reconciled/IRS compliant. GUI, Windows EXE, and CI results must be independently verified before any readiness claim.

## Tax, depreciation, retrospective and COA audit

- `tax_assets.py` separates manual jurisdiction sales-tax arithmetic, straight-line **book** depreciation, user-entered **tax** percentages, and retrospective difference review. Do not infer IRS tax schedules from user-entered percentages.
- 2025 IRS Publication 946 identifies material depreciation/Section 179 changes; **no fixed 2026 MACRS/bonus/Section 179 values are introduced**.
- `retrospective_adjustment(..., tax_mode=True)` is review-only; method-change/Form 3115/section 481(a) implications cannot be auto-determined.
- `core.py` chart covers bank, A/R, A/P, prepaids, assets, accumulated depreciation, inventory/COGS, payroll, travel, fees, insurance, software and expenses. Risky categories remain review-only.
- Suggestion rules must resolve only to valid chart codes; ambiguous evidence abstains and manual posting is required.

## Readiness gates

Backend change: implemented on Draft PR #62; confirm new SHA, GitHub CI and Windows jobs separately.
`MARKET_FIT_HOLD` / `COMPLIANCE_HOLD` remain until verified.
`PRE_IDENTITY_READY`, `POST_IDENTITY_READY`, `MSIX_READY`, `GUI_PASS`, `COMMERCIAL_PASS`: **not established**.
No Partner Center registration or Identity request is triggered.
