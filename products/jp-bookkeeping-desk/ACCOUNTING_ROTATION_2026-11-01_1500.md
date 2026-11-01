# JP bookkeeping: verified local receipt intake (2026-11-01)

Review-only stacked change on Draft PR #61. Market: JP, JPY, no US accounting logic.

## Backend gap implemented
- Source-document import validation and SHA-256 duplicate prevention (including renamed copies).
- Per-file transaction: a missing, unsupported, empty or oversized file does not abort valid siblings.
- Existing SQLite queue remains the reference store; a new hash-index table is created idempotently.
- 25 MiB per-file limit, 64 KiB streaming chunks, no network, no OCR, no automatic journal or tax posting.
- Original file stays in place; users must retain it. Queue references are **not** a legal e-record archive or backup.
- Tests cover duplicates, restart, corruption/empty input, mixed batches, file-size boundary, and journal→trial/P&L/B/S invariants.

## Beginner UX
- One button selects multiple files and reports accepted / duplicate / skipped counts and reasons.
- A second button opens a readable local queue list; explicit copy explains that OCR and auto-posting have **not** happened.
- No accounting knowledge or cloud login required to collect source-document references.

## Official source review — checked 2026-11-01
- NTA No.2070 (https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2070.htm): blue-return bookkeeping and source documents; queue references do not satisfy storage requirements on their own.
- NTA No.2080 (https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2080.htm): date, counterparty, amount and evidence retention are separate from merely selecting receipt paths.
- NTA No.2106 (https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2106.htm): depreciation rates/guarantee rates depend on acquisition date and official tables; no inferred rates introduced.
- NTA No.6303 (https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6303.htm): standard 10%, reduced 8%, and announced 2027–2029 food-rate change. Current hardcoded tax presets must **not** be used as an evergreen automatic tax-year rule; date-aware guard remains a packaging blocker.
- IRS Publication 583 (https://www.irs.gov/publications/p583) and Publication 946 (https://www.irs.gov/publications/p946) reviewed for cross-country separation only. No US logic added.
- GnuCash (https://www.gnucash.org/features.phtml): attachments/source traceability and reconciliation are baseline capability benchmarks, not sufficient paid differentiation.

## Gate
Unit tests require CI confirmation. Windows EXE, 1024x768 real GUI, Identity, signed MSIX, market-fit and Store review remain unverified / HOLD. No Store writes or merges.
