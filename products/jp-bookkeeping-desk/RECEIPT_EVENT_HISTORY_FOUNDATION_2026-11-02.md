# Receipt status event history — staged foundation (2026-11-02 JST)

**Stage:** REVIEW-ONLY / STAGED INTEGRATION (2026-11-02 10:00 JST). New Store enqueue/manual status writes and month-end HTML/JSON are wired; no legacy migration, no physical Windows GUI QA, and no automatic historical reconstruction are claimed.

## Why this stage exists

The current `receipt_queue` stores present status and created_at, not an append-only sequence of state changes. Therefore the January or February month-end pending count **cannot** be inferred from present queue rows. `monthly_close.py` deliberately keeps `unprocessed_receipts_as_of_month_end=null` and labels `unprocessed_receipts` as the **current all-date queue**. Do not silently change this gate.

The new opt-in `receipt_event_history.py` creates an append-only table with `receipt_id`, event kind (ENQUEUED / POSTED / REOPENED), UTC event timestamp, status and original file path. It replays events at the **Japan local month-end** boundary. New inserts and transitions must use its transactional API; duplicate enqueue and repeated status transitions do not create duplicate events. The table rejects UPDATE/DELETE. An existing database with legacy queue rows is permanently flagged `LEGACY_HISTORY_UNKNOWN` for historical reporting unless a separately reviewed migration with independent original evidence is designed. Unlogged queue rows, bypassed status changes, missing original receipt records, invalid event sequences, and timestamp problems return `null/HOLD` instead of a guessed number.

## Test coverage

`tests/test_jp_receipt_event_history.py` covers January/February and March replay, future-dated receipts, JST midnight boundary, reopen after processing, repeated replay/idempotency, legacy rows, bypassed inserts/status updates, missing source row, append-only protection, and invalid/backdated timestamps.

**Integration stage (2026-11-02 10:00 JST):** `Store.enqueue_receipts` now calls `ReceiptHistory.add`; the new `Store.set_receipt_status` calls `ReceiptHistory.transition`. The receipt list/dialog offers explicit manual status changes only, without posting a journal entry or approving a deduction. The report tab displays a beginner-facing **現在の未処理（全期間）** card and opens the receipt list. Month-end HTML/JSON uses `replay(year,month)` and separately shows the current queue and **対象月末時点の未処理**. For legacy/unlogged/invalid history the as-of field stays `null`, with `receipt_history_status=HOLD` and a plain-language **算出不可・要確認** label. Verified history is limited to new fully event-covered databases. No synthetic or old receipt status is silently backfilled.

The new `tests/test_jp_receipt_history_integration.py` covers Store writes, duplicate enqueue, manual post/reopen, January/February cutoff, future events, restart, month-end JSON/HTML, legacy database, bypassed changes and missing source. The test is not a claim of observed Windows GUI usability. Real client documents stay local; month-end HTML shows only receipt filenames, not full source paths. This implementation does **not** claim electronic-record legal compliance, OCR precision, or tax eligibility.

## Official primary-source design check (accessed 2026-11-02)

- [国税庁 No.2070 青色申告制度（令和8年4月1日現在法令等）](https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2070.htm): 日々の取引の記帳、証憑保存、帳簿の継続性を重視。アプリの月末集計は税務認定ではない。
- [国税庁 電子帳簿保存の取組紹介](https://www.nta.go.jp/about/introduction/torikumi/week/dennsityoubo.htm): 電子取引で受領した請求書等は元の電子データを保存する必要がある。HTML/PDFの月次レポートだけでは代替しない。

This is bookkeeping evidence infrastructure, **not** OCR accuracy, deductible-expense approval, tax filing automation, or a claim of electronic-books-law compliance. No Identity, MSIX, Store or central Windows ledger changes.


## Primary-source verification for this integration (2026-11-02 JST)

- [NTA No.2080 白色申告者の記帳・帳簿等保存制度](https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2080.htm), 令和8年4月1日現在法令等: daily transaction records and original documents must be preserved; a report cannot substitute for source evidence.
- [NTA No.6496 仕入税額控除のための帳簿及び請求書等](https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6496.htm), 令和8年4月1日現在法令等: retaining evidence and tax eligibility are separate; receipt status is never a deduction decision.
- [NTA 電子帳簿保存の取組紹介](https://www.nta.go.jp/about/introduction/torikumi/week/dennsityoubo.htm): received electronic transaction data must be retained, not replaced by a printed monthly HTML/PDF report; 2027-only preferential rules are not inferred for 2026.
