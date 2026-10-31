# Freelance Ledger Local

A local-only Windows bookkeeping app for solo freelancers in Japan and the United States.

## Product idea

The differentiator is not cloud tax filing. It is **account-free, subscription-free local recordkeeping** with a country profile.

- JP profile: JPY and common freelance bookkeeping categories.
- US profile: USD and common self-employed bookkeeping categories.
- Income/expense ledger, counterparty, memo and a local receipt/reference path.
- Monthly income / expense / net summary.
- Category summaries in the core API.
- UTF-8 CSV export for accountant/tax-preparer handoff.
- SQLite backup.
- Append-only audit log for add/delete actions.
- No login, telemetry, bank connection, cloud sync, tax filing or tax calculation.

The application does **not** decide deductibility, tax classification, filing eligibility or legal compliance. It records what the user enters and exports a reviewable ledger.

## Run

Python 3.12+:

```powershell
cd products/freelance-ledger-local
python main.py
```

Headless core tests:

```powershell
python -m unittest products/freelance-ledger-local/tests/test_core.py -v
```

## Store path

Candidate only. Before Microsoft Store packaging it still needs market-fit review, real Windows GUI QA, source/request binding, Identity, signed MSIX and Windows-checker/install QA.
