# JP bookkeeping — cash movement and beginner UX rotation

Reviewed 2026-11-01 (JST). Draft PR #61; Japan-only, JPY, local-first.

## Implemented
- Added read-only cash/bank movement engine aggregating posted journal lines by entry ID, not by account row. Transfers between selected cash/bank accounts have net zero and do not inflate receipts or payments.
- Opening balance + receipts - payments = closing balance, independently checked against ledger totals. Negative balances remain visible; no automatic correction, tax posting, or tax-return assertion.
- Added beginner-facing "お金の出入りを確認" window with start/end dates, receipts, payments, ending balance, source journal numbers and a plain-language limitation. Button shares existing input row to avoid increasing vertical height at 1024x768.
- Added fixtures for split journals, transfers, refunds, month boundaries, negative balances, empty periods, restart, read-only audit preservation, invalid dates and account scope.
- This is **not** a statutory cash-flow statement. Windows GUI at 1024x768, screenshot evidence, EXE and signed MSIX remain unverified.

## Official references checked 2026-11-01
- NTA No.2070 青色申告制度: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2070.htm — journals and supporting books are required; a management cash movement view does not replace them.
- NTA No.2080 白色申告者の記帳・帳簿等保存制度: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2080.htm — date, counterparty and amount records and source documents matter. This report retains source journal IDs; the app must separately preserve underlying evidence.
- NTA No.2106 減価償却: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2106.htm — method and rate are acquisition-date dependent; this feature makes no depreciation claim.
- NTA No.6303 消費税率: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6303.htm — currently 10%/8%, but the page flags a future 2027-04-01 to 2029-03-31 food-rate change. Existing global tax presets need effective-date and category validation before packaging.
- GnuCash features: https://www.gnucash.org/features.phtml — cash accounts, split postings and reconciliation are baseline free functionality, not yet a proven paid reason.
- US isolation reference: IRS Pub 583 https://www.irs.gov/publications/p583 and Pub 946 https://www.irs.gov/publications/p946 — US methods and depreciation must not be copied into JP code.

## Gate
market-scope.json remains JP/JPY and cross_market_sale=false. MARKET_FIT_HOLD, COMPLIANCE_HOLD (future-date tax rules), Windows GUI/EXE HOLD and Store HOLD until separate evidence. No Partner Center writes or certification claims.
