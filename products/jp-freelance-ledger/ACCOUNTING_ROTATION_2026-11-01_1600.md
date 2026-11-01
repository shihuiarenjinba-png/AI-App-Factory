# JP Freelance Ledger — monthly balance review rotation

Checked: 2026-11-01 (JST). Product: JP-only / JPY / local SQLite.
Base: Draft PR #59. No main/release, Store or Partner Center writes.

## Primary legal sources checked and design impact

- NTA No.6303, consumption tax standard 10% / reduced 8%, and the warning of a temporary food-transfer change from 2027-04-01 to 2029-03-31: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6303.htm — **do not** infer a universal future tax rate or assign a tax class from a cashbook category.
- NTA No.6102, reduced tax-rate scope and future effective-date notice: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6102.htm — future date-aware tax profiles require a separately verified effective-date schedule; no automatic tax assessment in this change.
- NTA No.2106, straight-line and declining-balance depreciation, including revised rate, guarantee rate, and months of business use: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2106.htm — preserve user-supplied, independently checked rate fields; no approximated official declining-balance rates.
- NTA No.2100, fixed-asset useful life and tax-rate tables: https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2100.htm — asset schedules remain review-only; no automatic past-return correction.
- GnuCash feature baseline (functional comparison only): https://www.gnucash.org/features.phtml — review-first reconciliation and auditability are baseline expectations, not evidence of paid-market differentiation.

## Concrete backend feature

Added `reconciliation.py`: manual monthly **whole-cashbook balance** review, with opening balance + income - expense = calculated closing balance. The user enters an independently checked closing balance. Difference must equal zero before an explicit confirmation can record the check. Source transaction SHA-256 fingerprint binds the preview; later transaction changes mark the previous check stale. Repeated identical confirmation is idempotent, with one audit record. No auto-adjusting entries, silent posting, bank feed, account-specific bank reconciliation, tax filing, or claim of compliance.

## Human-first UI

The existing CSV menu is renamed `帳簿の確認・入出力`, with `月次残高チェック` added without adding a vertical form row. A user enters month, opening balance and independently checked closing balance, then sees income, expense, expected balance and difference. Only zero-difference previews can be explicitly recorded. All explanations avoid internal developer terms. **Actual Windows GUI at 1024×768 is not yet observed**, so UI PASS is withheld.

## Tests and gates

Six isolated Python fixtures passed locally on 2026-11-01: preview/no posting, zero-difference and audit, duplicate confirmation, mismatch rejection, stale source and mutated preview rejection, invalid date/amount, and empty month. Root `tests/test_jp_freelance_reconciliation.py` runs product fixtures in Factory CI. GitHub CI status must be checked against exact PR head; do not mark PASS until verified.

Country isolation: `market-scope.json` JP / ja-JP / JPY / `cross_market_sale=false`. The product remains MARKET_FIT_HOLD / GUI_UNVERIFIED / EXE_UNVERIFIED / MSIX_UNVERIFIED. The cashbook check does not establish the tax or banking treatment of any entry.

## Windows EXE build failure found and fixed on this Draft branch

The first actual Windows PyInstaller build produced a PE executable, but the build step failed while printing the JSON receipt because the Windows runner console could not encode the Japanese display name (`UnicodeEncodeError: 'charmap' codec`). The builder now escapes non-ASCII characters **only for stdout JSON** (`ensure_ascii=True`); the on-disk UTF-8 receipt remains unchanged. Added `tests/test_preidentity_windows_console_encoding.py` to reproduce this with strict ASCII stdout. `proposals/jp-freelance-ledger.json` and product `tests/test_smoke.py` now satisfy the explicit pre-Identity source contract. **No EXE PASS claim until the new exact-SHA workflow succeeds and artifact is checked.**
