# JP bookkeeping month-end traceability — 2026-11-02 JST

## Primary-source check (2026-11-02)
- NTA [No.2080, bookkeeping and retention](https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2080.htm), page labeled **令和8年4月1日現在法令等**: transaction dates, counterparties, amounts and clear records matter; supporting documents must be retained. Design impact: display source entry date, description, entry ID, account, debit and credit for month-end report amounts. This is an accounting traceability feature, **not** a claim that the app satisfies statutory preservation requirements.
- NTA [No.2070, blue-return system](https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2070.htm): used as background for keeping journal and ledger records distinct from tax filing approval. No automatic tax deduction, tax return, or electronic-record compliance claims.

## Implementation and regression
- Monthly HTML now links each trial/P&L account to **この数字の根拠を見る**, showing dated original journal lines and entry IDs; separate monthly, year-to-date and month-end cumulative debit/credit amounts.
- JSON includes machine-readable `account_drilldown`; a fail-closed reconciliation prevents export when account totals disagree with source journal lines.
- The main GUI now exposes the previously inaccessible month-end report export as a beginner-facing button.
- `tests/test_monthly_drilldown.py`: Jan/Feb fixture verifies month P&L, year-to-date P&L, month-end B/S, source entry IDs and exclusion of future March entries. Test outcome is **pending CI**, not LOCAL_GUI_PASS.
- Current receipt queue remains explicitly all-dates/current-state, **not** a historical month-end snapshot.
- JP-only, JPY-only; no automatic deduction approval, tax filing, Partner Center upload or commercial readiness promotion.
