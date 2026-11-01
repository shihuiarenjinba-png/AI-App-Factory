# US Freelance Ledger — receipt evidence integrity rotation

Reviewed: 2026-11-01 (JST). Branch: codex/app-us-freelance-ledger-20261031. Draft PR #60.

## Primary official sources and design implications

- IRS, [What kind of records should I keep?](https://www.irs.gov/businesses/small-businesses-self-employed/what-kind-of-records-should-i-keep), checked 2026-11-01: source receipts, invoices, and transaction records must remain accessible. Added a read-only SHA-256 verification of *referenced* receipt files, with missing/changed/unsafe cases surfaced to the user. This does not archive the originals.
- IRS, [Publication 583](https://www.irs.gov/publications/p583), checked 2026-11-01: electronic bookkeeping still needs supporting records. The check never changes transactions or claims legal sufficiency.
- IRS, [Schedule C Instructions (2025)](https://www.irs.gov/instructions/i1040sc), checked 2026-11-01: sole proprietor reporting and cash/accrual treatment require their own legal determination; accounting-method selector is not a recognition engine. No tax-return logic changed.
- IRS, [Publication 463 (2025)](https://www.irs.gov/publications/p463), checked 2026-11-01: mileage, meals, travel require substantiation; the checker does not approve deductions or rates.
- IRS, [Publication 587 (2025)](https://www.irs.gov/publications/p587), checked 2026-11-01: home-office qualification is not inferred from evidence.
- IRS, [Publication 946 (2025)](https://www.irs.gov/publications/p946), checked 2026-11-01: depreciation depends on placed-in-service and acquisition dates; no tax-year amounts are hard-coded here.
- IRS, [Publication 538](https://www.irs.gov/publications/p538) and [Form 3115 instructions](https://www.irs.gov/instructions/i3115), scope carried forward: method changes require separate review.
- IRS, [Publication 334](https://www.irs.gov/publications/p334), scope carried forward: inventory, COGS, business expenses need independent classification review.
- State/local tax and sales-tax rates remain outside federal automation; no nationwide tax rate or certification claim.

## Backend gap implemented

New `receipt_integrity.audit_receipts` checks each referenced file against the original recorded SHA-256 and byte length, rejects symlinks, detects missing/changed/empty/oversized/unreadable files, and detects files changing during a check. Results are advisory and **do not mutate** transaction records, original files, or receipt status. UI action **Check receipt files** gives a beginner-readable summary and names the affected files. It explicitly warns that SQLite backup does not include original receipt bytes.

Regression fixtures: original match; modified content; deleted file; empty file; no receipts; no mutation. Local isolated smoke tests: 2/2 PASS before GitHub write (with stubbed receipt listing); GitHub branch CI is the authoritative integration check and must be separately verified. Windows 1024x768 GUI remains **unverified**.

## Gates

- US-only / USD-only / cross_market_sale=false; no Japan accounting logic.
- `COMPLIANCE_HOLD` / `MARKET_FIT_HOLD` remain. Cash/accrual recognition, restore QA, actual Windows GUI/EXE, and original receipt archiving remain incomplete.
- Do not promote, merge, sign, submit, or claim IRS compliance based on this rotation.
