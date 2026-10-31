# Freelance Ledger JP/US

Local-only Windows bookkeeping organizer for freelancers and sole proprietors who want to keep business records without uploading financial data to a vendor.

## Features

- Japan / United States mode in one app.
- Income and expense ledger with region-specific category suggestions.
- User-supplied business-use percentage for mixed personal/business expenses.
- Counterparty, payment account, description and evidence-reference fields.
- Region-filtered income, expense and net summaries.
- CSV export for a tax professional or downstream accounting workflow.
- Atomic local JSON save with last-known-good .bak recovery.
- Japanese/English labels and a 1024x768-friendly Tkinter layout.

## Scope

This is bookkeeping software, not tax filing or tax advice. Category names are organizational suggestions only. It does not decide whether an expense is deductible, calculate a tax return, submit Schedule C, submit a Japanese income-tax return, or replace a qualified professional.

The design is informed by:
- Japan NTA bookkeeping/storage guidance: https://www.nta.go.jp/taxes/shiraberu/shinkoku/kojin_jigyo/0023005-091_01.pdf
- IRS recordkeeping guidance: https://www.irs.gov/businesses/small-businesses-self-employed/recordkeeping
- IRS Schedule C information: https://www.irs.gov/forms-pubs/about-schedule-c-form-1040

## Market position

The product is deliberately not a cloud bank-sync competitor. Its proposed paid-use value is privacy-first local bookkeeping, no account, no subscription dependency, and a clean CSV handoff to an accountant/tax preparer. That thesis still requires user validation before Store packaging.

## Run and test

python main.py

Tests are headless and live in tests/test_smoke.py.

Python 3.12+ standard library is sufficient. No network, telemetry, login, payment, remote shell, credential handling or automatic downloads.

## Status

Review-only candidate. Windows installation, signing, MSIX packaging, accessibility and Store certification are downstream gates and are not claimed here.
