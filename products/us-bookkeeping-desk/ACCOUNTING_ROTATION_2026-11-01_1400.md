# US bookkeeping rotation — 2026-11-01 (14:00 JST)

## Scope, product and status
- Product: `us-bookkeeping-desk` / US-only, English, USD, `cross_market_sale=false`.
- Backend gap implemented: local source-document/receipt traceability, SHA-256 content deduplication, per-file partial failure isolation, verified copy export and audit log. Existing journal, ledger, trial balance, P&L and B/S are never mutated by evidence imports.
- Human-first UX implemented: select a saved Journal row -> **Attach receipts** (multi-file) -> **Review receipts** (metadata + save verified copy). Clear success/duplicate/rejected counts. No OCR, no automated tax deduction or posting.
- Supported file types: PDF, PNG, JPEG, WebP; 15 MB per file. Magic bytes are checked but full document validity and malware safety are **not** established. SQLite BLOB storage is local-only and increases backup size.
- Windows 1024x768 GUI and EXE are **not** asserted PASS until Windows run evidence exists.
- Product remains `COMPLIANCE_HOLD / MARKET_FIT_HOLD`; no Store upload or Partner Center changes.

## Official primary-source review — checked 2026-11-01
1. Sole proprietor / Schedule C: https://www.irs.gov/instructions/i1040sc — this generic bookkeeping app does not determine who must file Schedule C.
2. Cash versus accrual: https://www.irs.gov/publications/p538 — the saved selection does not establish a compliant federal recognition engine; existing gap remains.
3. Method change / Form 3115 / consent: https://www.irs.gov/instructions/i3115 and https://www.irs.gov/forms-pubs/about-form-3115 — never auto-convert methods or make a section 481(a) adjustment. The IRS page refers to updated procedures; tax-year review required.
4. Income with/without 1099: https://www.irs.gov/instructions/i1040sc — journal evidence is not conditional on receiving a 1099; no income exclusion is inferred.
5. Vehicle and mileage records: https://www.irs.gov/publications/p463 — receipt alone is not sufficient substantiation; business purpose, mileage and method need human review.
6. Meals and travel: https://www.irs.gov/publications/p463 — preserve evidence without deciding deductibility or percentages.
7. Home-office qualification: https://www.irs.gov/publications/p587 — evidence capture does not decide eligibility or limits.
8. Depreciation/capitalization/Section 179: https://www.irs.gov/publications/p946 and https://www.irs.gov/publications/p334 — Pub. 946 includes 2025 and 2026 developments; no rates, limits, MACRS conventions or bonus allowances were changed in this rotation.
9. Inventory/COGS: https://www.irs.gov/publications/p334 — source receipts do not establish inventory cost flow or COGS tax treatment.
10. Records retention: https://www.irs.gov/publications/p583 — no automatic deletion/blanket retention period; user remains responsible for retention.
11. Computerized records/source documents: https://www.irs.gov/publications/p583 — implement local evidence-to-journal linking, content hash and export; no claim of IRS-certified or tamper-proof archive.
12. State/local tax, sales tax, licensing: https://www.irs.gov/instructions/i1040sc — outside federal bookkeeping engine; no nationwide sales-tax default.

## Functional benchmark — checked 2026-11-01
- GnuCash features: https://www.gnucash.org/features.phtml — double-entry, reconciliation, scheduled transactions and reporting are free baseline features. We do not copy code, layout or wording.
- This iteration improves *traceability and consumer workflow*, not accounting feature parity. Still missing production-grade cash/accrual timing, full audit/backup restore, AR/AP aging, recurring entries, and real Windows GUI proof.

## Tests and release safety
- `tests/test_us_receipt_vault.py` checks multi-file import, duplicate handling, persistent restart, report invariance, journal-to-ledger-to-trial-to-P&L/B/S balance, file rejection, symlink rejection, verified export, corruption detection, and no overwrite.
- No bank feed, external API, SaaS, telemetry, OCR, auto-categorization, tax filing, deduction approval or cross-market sale.
- Existing `products/us-bookkeeping-desk/US_COMPLIANCE_SCOPE.md` remains mandatory at package gate.
- Status requires independent CI result and Windows UI/EXE review; these are not implied by source changes.
