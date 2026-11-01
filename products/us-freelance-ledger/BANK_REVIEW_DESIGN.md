# US freelance ledger — manual bank-statement review

Verified primary sources on **2026-11-01** (JST). This is product design evidence, not legal compliance certification.

## Product capability and consumer workflow

1. Record a business income/expense entry (no bank credentials).
2. Select the ledger row, choose **Match selected**, enter a bank account label and statement ending date, and confirm the paper/PDF statement was checked.
3. Use **Check statement** to enter opening and closing bank balances. Only a zero-cent difference can be finalized. Use **Undo match** before finalization when necessary.
4. The ledger shows **Not matched / Matched / Checked**. Status persists after restart. A finalized statement is immutable in this initial version.

The account label is a *manual grouping key*, not an online bank connection. Users must enter **all** relevant bank movements and distinguish bank entries from cash/accrual entries. Missing transfers, fees, deposits, withdrawals and multi-account movement can prevent reconciliation. The engine does not create balancing journal entries, fetch bank statements, validate external evidence or decide deductibility. UI is designed for novice 3-step review; **1024x768 Windows GUI remains unverified**.

## Arithmetic and safety

- Integer cents only, no binary floating-point for statement comparisons; invalid dates, fractional cents and overflow are rejected.
- Each transaction can be matched once. Reconciled matches cannot be undone by the UI; unfinalized matches can be removed with audit evidence.
- Per-account and per-statement-date isolation, prior closing/opening balance continuity, chronological finalization.
- Statement sum: opening balance + matched income - matched expense = expected closing balance. Difference must be zero.
- Reconciliation never changes the original transaction amount, income/expense report, tax treatment or accounting method.
- SQLite tables and audit log are included in the existing database backup. Restore and Windows GUI QA remain required.
- This is not a complete bank reconciliation engine: bank data are not imported, cash/accrual timing is not modeled, and split/multi-currency/transfer accounting is not implemented. No claim of GnuCash, QuickBooks, Xero, SAP or NetSuite parity.

## IRS official review (2026-11-01)

| Topic | Primary source | Design consequence |
| --- | --- | --- |
| Sole proprietor / Schedule C | https://www.irs.gov/instructions/i1040sc | Do not determine eligibility or taxability |
| Cash vs accrual | https://www.irs.gov/publications/p538 | Matching bank movements does not make accrual recognition correct |
| Method changes / Form 3115 | https://www.irs.gov/forms-pubs/about-form-3115 | No automatic method conversion |
| Income regardless of Form 1099 | https://www.irs.gov/publications/p334 | Bank matching does not filter income by form receipt |
| Vehicle substantiation | https://www.irs.gov/publications/p463 | Manual review required; no mileage deduction rule |
| Meals and travel | https://www.irs.gov/publications/p463 | Business purpose and evidence remain user-reviewed |
| Home office | https://www.irs.gov/publications/p587 | No home-office eligibility inference |
| Depreciation, capitalization, Section 179 | https://www.irs.gov/publications/p946 | Pub. 946 is for 2025 returns; 2026 tax schedules need applicable tax-year verification; book and tax schedules remain separate |
| Inventory / COGS | https://www.irs.gov/instructions/i1040sc | Do not equate bank outflow with deductible COGS |
| Records retention | https://www.irs.gov/publications/p583 | No universal retention period hardcoded |
| Computerized source traceability | https://www.irs.gov/publications/p583 | Preserve manual match audit and source document reference; bank statement bytes not archived |
| State/local sales tax, licenses | https://www.irs.gov/instructions/i1040sc | Separate jurisdiction; no nationwide rate or automatic obligations |

**Change watch:** IRS Pub. 946 (2025) describes date-sensitive bonus depreciation changes; Form 3115 instructions and published revenue procedures can change. Do not ship tax-year-dependent tax computations based solely on these references.

## Japan separation review (2026-11-01)

Japan-only products remain separate from this US implementation:
- NTA income-tax depreciation overview: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2100.htm — cost allocation across useful life, not instant expensing.
- NTA consumption tax rates: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6303.htm — 10% standard, 8% reduced as described in the source; source now notes a future 2027-2029 food-rate change, so rate profiles must be effective-date/version aware.
- NTA corporate depreciation method-change procedure: https://www.nta.go.jp/taxes/shiraberu/taxanswer/hojin/5407.htm — **corporate-tax scope**, do not transplant as personal income-tax rules.
- Japan bookkeeping remains JP/JPY and US remains US/USD; each market-scope.json must retain cross_market_sale=false.

## Verification gates

Headless tests cover exact-cent reconciliation, mismatches, audit, persistence after restart, duplicate matches, chronological account continuity, invalid dates, overflow and unchanged bookkeeping totals. GitHub CI result must be verified on the exact new branch HEAD. No GUI screenshot, EXE, signed MSIX, identity binding, Partner Center action or Store readiness is claimed from these tests.
