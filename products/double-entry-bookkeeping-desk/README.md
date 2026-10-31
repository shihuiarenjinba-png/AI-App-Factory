# Double-Entry Bookkeeping Desk

Local-only Windows double-entry bookkeeping for users who want a conventional journal/ledger workflow without a cloud account.

## Features

- JPY or USD books; currency is locked after the first journal entry.
- Editable chart of accounts with Japanese and English names.
- Six-line split journal entry form.
- Balanced-debit/credit enforcement.
- Journal view.
- Trial balance.
- Profit & loss summary.
- Balance sheet summary including current net income.
- Period lock to prevent posting into a closed period.
- CSV journal export and SQLite backup.
- Append-only audit events for posting and period locking.
- No cloud, login, telemetry, bank sync, payroll, tax filing or automatic tax advice.

This is an accounting record tool, not tax/legal advice and not a certified filing system.

## Run

```powershell
cd products/double-entry-bookkeeping-desk
python main.py
```

Core tests:

```powershell
python -m unittest products/double-entry-bookkeeping-desk/tests/test_core.py -v
```

## Store status

New product candidate. It needs market-fit validation, real Windows GUI QA, immutable source/request binding, Partner Center Identity, signed MSIX and Windows-checker/install QA before Store readiness.
