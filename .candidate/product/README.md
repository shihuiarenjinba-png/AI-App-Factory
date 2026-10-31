# Local Double-Entry Bookkeeper

A local-only Windows desktop bookkeeping app for people who want conventional double-entry books without a cloud account.

## Features

- Standard chart of accounts with assets, liabilities, equity, income and expenses.
- Balanced debit/credit journal posting.
- Custom account creation.
- Trial balance.
- Profit & Loss summary.
- Balance Sheet summary including current earnings.
- Journal CSV export for an accountant or downstream offline workflow.
- Atomic local JSON save with .bak recovery.
- Japanese/English labels and a 1024x768-friendly UI.

## Market position

GnuCash already provides powerful free double-entry bookkeeping, including split transactions, reconciliation and reports. This product therefore must not be sold simply as another ledger. Its proposed value is a smaller, simpler local-first Windows workflow with a much lower learning surface.

Reference competitor:
https://www.gnucash.org/features.phtml

The paid-use thesis still needs user validation before Store packaging.

## Scope

This app records books. It does not prepare or file tax returns, determine deductibility, provide tax/legal advice, sync bank credentials or upload financial data.

Version 1 exposes a simple one-debit/one-credit posting screen. The internal model already validates balanced multi-line entries so a split-entry editor can be added as the next product-quality revision.

## Run and test

python main.py

Headless tests are in tests/test_smoke.py.

Python 3.12+ standard library is sufficient. No network, telemetry, login, payment, remote shell, credential handling or automatic downloads.

## Status

Review-only candidate. Windows installation, signing, MSIX packaging, accessibility and Store certification are downstream gates and are not claimed here.
