# JP freelance month-end completeness and beginner UX

Reviewed: 2026-11-01 (JST). Scope: JP-only, JPY, local bookkeeping; no Store submission.

## Official references and design impact

- NTA, bookkeeping and preservation of consumption-tax transaction details (2026-04-01 law basis): https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6621.htm — preserve date, transaction detail, counterparty and separate tax-rate records where applicable. This export is a *review pack*, not a claim of tax-compliant storage or a tax-return form.
- NTA, source documents and invoice preservation (2026-04-01 law basis): https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6496.htm — retain the source invoices separately. A PDF generated from the report is not a substitute for original electronic documents.
- NTA, electronic bookkeeping overview (2025 return guidance, accessed 2026-11-01): https://www.keisan.nta.go.jp/r7yokuaru_sp/cat2/cat26/cat267/scid1687.html — electronic records require their own storage conditions; no legal certification is asserted.
- IRS Publication 583 (accessed 2026-11-01): https://www.irs.gov/publications/p583 — US books and supporting documents must reconcile, but these US requirements are *not* transplanted into this JP product.
- IRS Publication 946 (2025 revision, accessed 2026-11-01): https://www.irs.gov/publications/p946 — tax-year-sensitive depreciation; no US tax schedule or automatic deduction was added.
- GnuCash features (benchmark): https://www.gnucash.org/features.phtml — reliable ledger/report reconciliation is a baseline capability, not a UI to copy.

## Backend gap fixed

The month-end export previously called `store.rows(10000)`, which silently omitted transactions beyond the first 10,000 UI rows. The export now reads all rows for the selected month directly from the SQLite ledger, checks income and expense totals against the authoritative monthly aggregation, and rejects invalid months. Category totals distinguish revenue from expense even if a category label is reused. The pending receipt list no longer truncates at 1,000; JSON includes its explicit count. No transactions or tax eligibility are modified.

## Beginner-facing improvement

The existing month-end export method was unreachable from the app UI. A visible `帳簿出力・CSV` menu now offers `月末の帳簿パックを作成` without adding height to the 1024×768 layout. Canceling year/month selection no longer opens an unnecessary directory dialog. Output remains HTML/CSV/JSON, with PDF only if local Edge printing succeeds.

## Test and safety gates

Added fixtures for 10,005 transactions, 1,001 pending receipts, mixed revenue/expense labels, HTML escaping, invalid month and the UI command wiring. Tests validate headless behavior only; Windows GUI/install and Store screenshot are not claimed PASS. No OCR was run, so OCR accuracy is **unmeasured**; automatic tax deductibility approvals and automatic posting remain prohibited. Receipt records are source *references*, not a compliant electronic document vault. `MARKET_FIT_HOLD` and package/Identity gates are unchanged.

Next: implement source-document integrity verification and user-visible missing-file warnings, then actual Windows 1024×768 review and signed MSIX QA after market-fit and compliance gates.
