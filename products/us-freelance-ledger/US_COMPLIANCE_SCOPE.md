# US federal compliance scope — Freelance Ledger US

Reviewed: 2026-10-31

## Product boundary

This app is a local bookkeeping and record-organizing tool, not a tax-return preparer and not a legal-compliance certification tool.

It may help a U.S. sole proprietor organize records commonly used when preparing Schedule C, but it does not decide whether:
- an activity legally qualifies as a trade or business,
- an expense is deductible,
- cash or accrual is the legally permitted or required method,
- a taxpayer may change accounting method,
- a vehicle, home-office, depreciation, meals or travel deduction qualifies,
- state or local tax, licensing or sales-tax duties apply.

## Federal primary sources checked

1. IRS Publication 583 — Starting a Business and Keeping Records
   https://www.irs.gov/publications/p583
2. IRS Instructions for Schedule C
   https://www.irs.gov/instructions/i1040sc
3. IRS Publication 334 — Tax Guide for Small Business
   https://www.irs.gov/publications/p334
4. IRS Publication 463 — Travel, Gift, and Car Expenses
   https://www.irs.gov/publications/p463
5. IRS Publication 587 — Business Use of Your Home
   https://www.irs.gov/publications/p587
6. IRS Instructions for Form 3115 / Publication 538 — accounting-method changes
   https://www.irs.gov/instructions/i3115
   https://www.irs.gov/publications/p538
7. IRS record retention guidance
   https://www.irs.gov/businesses/small-businesses-self-employed/how-long-should-i-keep-records

## Application safety rules

- Never present bookkeeping net as taxable income.
- Never infer that a missing Form 1099 means income is not reportable.
- Never auto-approve a deduction.
- Vehicle, meals, travel, home office, depreciation/capital assets, taxes/licenses, inventory/COGS and accounting-method changes are REVIEW REQUIRED.
- Category suggestions are suggestions only and must show matched evidence/confidence.
- Cash/accrual selection is a bookkeeping setting; the app must not state that the selected method is legally available to the user.
- State/local compliance is outside automated scope unless a separately researched state module is added.
- No mileage rate, per-diem amount, deduction percentage, threshold or dollar limit may be hard-coded without a tax-year-specific official source and update mechanism.
- Do not market the app as IRS compliant or tax compliant.

## 2026-10-31 federal 12-point review (primary IRS sources)

This checklist documents design scope, **not** a compliance certification. Re-check each linked IRS source and its Future Developments before any release; sources are not all 2026 tax-year revisions.

| Topic | Primary IRS basis | Product handling / unresolved issue |
| --- | --- | --- |
| 1. Sole proprietor / Schedule C | [Schedule C instructions](https://www.irs.gov/instructions/i1040sc) | Sole-proprietor record organization only; never decide business eligibility |
| 2. Cash versus accrual | [Pub. 538](https://www.irs.gov/publications/p538), [Pub. 334](https://www.irs.gov/publications/p334) | **HOLD:** selector is persisted/locked, but recognition timing is not yet calculated differently; do not claim cash/accrual accounting is implemented |
| 3. Changing accounting method | [Form 3115 instructions](https://www.irs.gov/instructions/i3115), [Pub. 538](https://www.irs.gov/publications/p538) | Warn that consent and Form 3115 may be required; never switch existing books automatically |
| 4. Income without Form 1099 | [Schedule C instructions](https://www.irs.gov/instructions/i1040sc) | Record business income regardless of whether a 1099 was received; no automatic taxability decision |
| 5. Vehicle and mileage | [Pub. 463](https://www.irs.gov/publications/p463) | REVIEW REQUIRED; supporting mileage/date/business-purpose evidence, no fixed rate |
| 6. Meals/travel | [Pub. 463](https://www.irs.gov/publications/p463) | REVIEW REQUIRED; business purpose and substantiation, no auto-deduct percentage |
| 7. Home office | [Pub. 587](https://www.irs.gov/publications/p587) | REVIEW REQUIRED; exclusive/regular-use and exceptions are not automated |
| 8. Depreciation, capitalization, Section 179 | [Pub. 334](https://www.irs.gov/publications/p334), [Schedule C instructions](https://www.irs.gov/instructions/i1040sc) | REVIEW REQUIRED; tax-year rules can change, no hardcoded thresholds |
| 9. Inventory / COGS | [Pub. 334](https://www.irs.gov/publications/p334) | REVIEW REQUIRED; inventory and small-business exceptions need separate treatment |
| 10. Retention | [Pub. 583](https://www.irs.gov/publications/p583) | No universal deletion-after-3-years policy; retention depends on limitation period and record type |
| 11. Computerized records and source documents | [Pub. 583](https://www.irs.gov/publications/p583) | Keep references, export, backups and audit trail; **HOLD** until restore and source traceability QA |
| 12. State/local obligations | [Schedule C instructions](https://www.irs.gov/instructions/i1040sc) | Separate state/local taxes, sales tax and licenses are explicitly outside automated federal scope |

**Change watch:** The 2025 Schedule C instructions contain changed depreciation/Section 179 rules and a Future Developments notice. Do not transplant those figures into a future tax year. [Form 3115 page](https://www.irs.gov/forms-pubs/about-form-3115) links to recent guidance; verify applicable revenue procedures before release.

**Current package gate:** `COMPLIANCE_HOLD` and `MARKET_FIT_HOLD`. Unimplemented cash/accrual recognition, incomplete evidence/restore QA, and unverified Windows GUI/EXE prevent any tax-method or sales-readiness claim. Bookkeeping net is **not taxable income**.
