# JP Freelance Ledger — accounting engine / human-first UX rotation

Reviewed: 2026-11-01 (JST)
Scope: JP only, JPY only, local SQLite. Draft PR #59, not Store-ready.

## Primary sources checked (official, current)

- NTA No.2080 (白色申告者の記帳・帳簿等保存制度): https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2080.htm — daily income/expense records and supporting documents remain important; imported data must preserve date, amount, counterparty, description, and evidence references. No tax filing automation.
- NTA No.6621 (帳簿の記載事項と保存): https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6621.htm — consumption-tax bookkeeping requires appropriate date, transaction details, counterparties, and tax-rate distinction. This import is a **general ledger data import**, not a complete tax-bookkeeping or invoice compliance certification.
- NTA No.6497 (仕入税額控除のために保存する帳簿・請求書等): https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6497.htm — receipt references alone do not establish input tax credit eligibility; require separate user review and original document retention.
- NTA No.6303 (消費税等の税率): https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6303.htm — current standard 10% / reduced 8%; do not infer tax classification from a CSV category.
- NTA No.6102 (軽減税率制度): https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6102.htm — page checked 2026-11-01 flags a **2027-04-01 to 2029-03-31 temporary change for food transfers**. Existing 10%/8% UI presets must not be treated as perpetual date-aware tax rules. Require transaction-date and item-classification evidence before automated tax treatment.
- GnuCash capabilities (mature free baseline): https://www.gnucash.org/features.phtml — import transaction matching, duplicate detection, reconciliation, scheduled transactions, reports. Benchmark functional requirements only; no copied UI or source.

## Concrete backend gap closed in this rotation

Added `csv_review.py`: review-first import of this app's own UTF-8 CSV export format, strict JP fields, date and integer-JPY checks, category and evidence-type validation, file size/row limits, SHA-256 preview binding, intra-file and preexisting-transaction duplicate checks, persistent import fingerprints, audit entries, and atomic rollback on write failure. No network or cloud dependency.

The preview makes **no transaction postings**. The user explicitly confirms valid rows; invalid rows and duplicates are excluded and counted. CSV is not a tax declaration, bank integration, OCR, or automatic journal classification. The import does not create a balanced double-entry ledger; this freelance cashbook remains separate from the JP bookkeeping product.

## Human-first UI change

Replaced the single `CSV出力` action with `CSV 入出力` menu, exposing `CSVを確認して取り込む` and `CSVに書き出す` without increasing the vertical form rows. Import preview displays new, duplicate, and invalid counts, up to five line-specific explanations, and a confirmation before writing. The main table refreshes after success. This is a code-level UX change, **not a Windows GUI 1024x768 PASS**.

## Test evidence and remaining gates

- Local isolated fixture: 6/6 tests passed 2026-11-01, covering preview-only, idempotent re-import, existing manual duplicates, file mutation rejection, malformed data, audit, monthly/annual rollup, and atomic rollback. Isolated fixture used a schema-compatible test stub; GitHub core CI is authoritative for the actual product.
- Root `tests/test_jp_freelance_csv_review.py` invokes the six product tests on Linux/Windows CI. Do not report CI PASS until the current commit run finishes.
- `market-scope.json`: JP, ja-JP, JPY, cross_market_sale=false; no US tax/accounting mode.
- `tax_assets.py`: rates are user-supplied for depreciation; do not silently infer official declining/revised/guarantee rates. Retrospective differences remain review-only; no automatic amended returns.
- Still missing for the pre-Identity EXE build contract: `proposals/jp-freelance-ledger.json` and `products/jp-freelance-ledger/tests/test_smoke.py`, which `tools/build_windows_exe.py` currently requires. Do not fabricate owner-controlled Factory promotion or claim EXE PASS.
- Product market-fit score, Windows GUI/install QA, signed MSIX, and final Store readiness are not established.

Next owner action: complete official Factory lifecycle/proposal+smoke contract, then exact-SHA Windows EXE and actual GUI QA; revisit effective-date tax profile before commercial tax-related features.
