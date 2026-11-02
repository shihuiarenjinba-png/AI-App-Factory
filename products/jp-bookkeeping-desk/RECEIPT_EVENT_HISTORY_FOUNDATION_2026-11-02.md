# Receipt status event history — staged foundation (2026-11-02 JST)

**Stage:** REVIEW-ONLY / NOT YET IN MONTH-END UI. No migration or automatic historical reconstruction is claimed.

## Why this stage exists

The current `receipt_queue` stores present status and created_at, not an append-only sequence of state changes. Therefore the January or February month-end pending count **cannot** be inferred from present queue rows. `monthly_close.py` deliberately keeps `unprocessed_receipts_as_of_month_end=null` and labels `unprocessed_receipts` as the **current all-date queue**. Do not silently change this gate.

The new opt-in `receipt_event_history.py` creates an append-only table with `receipt_id`, event kind (ENQUEUED / POSTED / REOPENED), UTC event timestamp, status and original file path. It replays events at the **Japan local month-end** boundary. New inserts and transitions must use its transactional API; duplicate enqueue and repeated status transitions do not create duplicate events. The table rejects UPDATE/DELETE. An existing database with legacy queue rows is permanently flagged `LEGACY_HISTORY_UNKNOWN` for historical reporting unless a separately reviewed migration with independent original evidence is designed. Unlogged queue rows, bypassed status changes, missing original receipt records, invalid event sequences, and timestamp problems return `null/HOLD` instead of a guessed number.

## Test coverage

`tests/test_jp_receipt_event_history.py` covers January/February and March replay, future-dated receipts, JST midnight boundary, reopen after processing, repeated replay/idempotency, legacy rows, bypassed inserts/status updates, missing source row, append-only protection, and invalid/backdated timestamps.

**Integration intentionally deferred:** The existing `Store.enqueue_receipts` and GUI still bypass the opt-in history writer. Until they are wired and end-to-end fixtures pass, the month-end HTML/JSON must continue to show **現在の未処理証憑（全期間）** separately from **対象月末時点の未処理証憑（履歴未検証・算出不可）**. Never expose the new replay count as verified from a legacy database.

## Official primary-source design check (accessed 2026-11-02)

- [国税庁 No.2070 青色申告制度（令和8年4月1日現在法令等）](https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2070.htm): 日々の取引の記帳、証憑保存、帳簿の継続性を重視。アプリの月末集計は税務認定ではない。
- [国税庁 電子帳簿保存の取組紹介](https://www.nta.go.jp/about/introduction/torikumi/week/dennsityoubo.htm): 電子取引で受領した請求書等は元の電子データを保存する必要がある。HTML/PDFの月次レポートだけでは代替しない。

This is bookkeeping evidence infrastructure, **not** OCR accuracy, deductible-expense approval, tax filing automation, or a claim of electronic-books-law compliance. No Identity, MSIX, Store or central Windows ledger changes.
