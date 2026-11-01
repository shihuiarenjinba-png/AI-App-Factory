# JP freelance ledger — receipt intake / accounting UX rotation

Checked: 2026-11-01 17:00 JST. Branch: codex/app-jp-freelance-ledger-20261031, Draft PR #59.

## Official evidence and design decisions

- 国税庁 No.2080, https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2080.htm (checked 2026-11-01): individual business records should preserve transaction date, counterparty, amount and evidence. A file-path-only receipt queue must not be presented as proof of a valid accounting entry or compliant document storage.
- 国税庁 No.6303, https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6303.htm (checked 2026-11-01): standard 10% and reduced 8% rates are published, with a notice of temporary changes to food transfers in 2027–2029. The existing tax calculator is a manual illustration only; date-sensitive tax classification and current-law review remain separate package blockers. This rotation does not add tax auto-classification.
- 国税庁 No.5410, https://www.nta.go.jp/taxes/shiraberu/taxanswer/hojin/5410.htm (checked 2026-11-01): declining-balance depreciation uses an official ordinary rate, revised rate, and guarantee rate. Existing tax_assets.py requires explicit rates rather than guessed official values; no automatic filing.
- GnuCash capabilities, https://www.gnucash.org/features.phtml (benchmark checked 2026-11-01): transaction import/duplicate prevention and reconciliation are mature-product baseline capabilities. Reimplement behavior only, not its source/UI.
- US scope audit only (no US code changed): IRS Pub. 583 https://www.irs.gov/publications/p583, Pub. 538 https://www.irs.gov/publications/p538, Pub. 946 (2025) https://www.irs.gov/publications/p946, Schedule C (2025) https://www.irs.gov/instructions/i1040sc (checked 2026-11-01). These do not authorize JP/US rule mixing or tax-rate hardcoding.

## Backend feature implemented

`receipt_review.py` provides review-only batch intake of up to 100 local JPG/JPEG/PNG/WebP/PDF files (max 25MB each). Missing/empty/unsupported files are counted individually instead of stopping the whole review. SHA-256 content fingerprints and canonical paths identify duplicate candidates. The user-confirmed write re-hashes every file, rejects changed previews, and atomically inserts receipt_queue + receipt_intake_index + audit_log records. Re-imports are idempotent; a write failure rolls back the entire accepted batch. No network, OCR, bank connection, tax deduction, or automatic journal posting.

Limitation: preexisting legacy queue records that lack hashes are checked by path, not by content. File references remain external paths; this does not create a legal archive or protect against subsequent deletion/modification of originals. Future work: verified local document vault with controlled retention, hash re-verification and user-visible missing-file warnings.

## Human-first UI implemented

The existing `複数レシートを取り込む` action now shows three counts (new / duplicate / unreadable), up to three plain-language file errors, and asks for explicit confirmation. The dialog states that originals are not moved, OCR is not performed, and no journal entry has been posted. A single bad file does not discard other valid selections.

## Tests and gates

`tests/test_jp_receipt_review.py` adds real SQLite fixtures for preview-only behavior, mixed-good/bad batch, same-content duplicate, repeat/restart idempotency, changed-file rejection, rollback on database failure, and limits. Root Factory CI is the authoritative run; **do not mark CI PASS until the current SHA's workflow completes**. No actual Windows 1024x768 GUI observation was performed, so GUI PASS remains unverified.

Country contract: JP-only, JPY, Japanese UI, cross_market_sale=false. No Identity/Partner Center actions, signed MSIX, or Store submission. MARKET_FIT, EXE, GUI, PRE_IDENTITY and commercial gates remain independently evaluated. No new APP product generated.
