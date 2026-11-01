# JP Freelance Ledger — budget review + tax input safety

Checked: **2026-11-01 JST**. Japan-only / Japanese / JPY / local SQLite.
Owner: APP 00 lane. Stacked on Draft PR #72, itself based on #59. No merge, Store writes, Partner Center authentication, Identity guesses, or source/request promotion.

## Primary official sources and decisions

1. NTA No.6303, https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6303.htm (checked 2026-11-01): current standard 10% / reduced 8% consumption tax. NTA now carries a **2027-04-01 through 2029-03-31 food-transfer change notice**. A general cashbook category is not sufficient to assign tax treatment. Existing calculator remains an explicitly user-selected arithmetic aid; future transactions require date-aware source validation before automatic tax profiles can be enabled.
2. NTA No.6102, https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6102.htm (checked 2026-11-01): reduced-rate scope is restricted. Do not infer taxability from a category or memo. No automatic posting.
3. NTA No.2100, https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2100.htm (checked 2026-11-01): asset useful lives and rate tables require a verified source and asset classification. Do not invent rates or small-asset eligibility.
4. NTA No.2106, https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2106.htm (checked 2026-11-01): straight-line / declining-balance, revised rate, guarantee rate, acquisition-era differences, and partial-year service months. The current calculator requires explicit verified rates and checks method restrictions. Added fixture for six-month prorating; rate master and acquisition-era validation still require further review before tax-compliance claims.
5. NTA No.2107, https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2107.htm (checked 2026-11-01): repair versus capital improvement is fact-specific; account suggestions cannot automatically determine treatment.
6. GnuCash features, https://www.gnucash.org/features.phtml (checked 2026-11-01): budgeting, reconciliation, scheduled transactions, and double-entry are mature free-software baselines. Budget-versus-actual alone is **not** evidence of commercial differentiation. No proprietary source, layout, branding or wording copied.
7. IRS Pub. 583, https://www.irs.gov/publications/p583 (checked 2026-11-01): US cash/accrual and recordkeeping are distinct from this JP-only product. No US rules, Schedule C, or tax-method switching is introduced.

## Backend gap implemented

- Added a local SQLite **monthly category budget versus actual** engine. It reads every month-matching cashbook transaction, calculates income, expense and net, and verifies the net equals the existing monthly cashbook calculation.
- Budget writes require explicit user confirmation in UI. A repeated identical write is idempotent; changed budgets produce an audit event. Budget updates **never** create transactions or journal postings.
- A genuinely unset budget is shown as **未設定**, distinct from an explicit 0 yen budget. Income below target and expenses over budget are explained separately.
- Category/kind mismatches, malformed dates, non-integer or out-of-range amounts, and corrupted transactions fail closed. Report fingerprint changes when source transactions or budgets change. Persistence survives SQLite restart.
- This product is a cashbook, **not** a double-entry ledger. The cashbook net is **not** taxable income and is not represented as journal → ledger → trial balance → P/L/B/S parity. That parity remains a separate gate for JP/US bookkeeping products.

## Human-first UX

- Existing `帳簿の確認・入出力` menu adds `月次予算と実績`; no extra row is added to the crowded main input form.
- One 680×480 dialog offers month, income/expense, category, budget and a scrollable report. A novice can view, select and explicitly save a budget in 3–5 operations. No silent posting or tax determination.
- 1024×768 real Windows GUI, keyboard accessibility and screenshot **not yet observed**; no UI PASS claim.

## Tax / depreciation / retroactive / account-master audit

- `tax_assets.py`: reject NaN, infinity, fractional-yen inputs, negative/over-limit tax rates and unknown rounding modes instead of silently accepting/truncating. User still chooses rates; this is **not** automatic tax applicability.
- `retrospective_adjustment`: include years with posted amounts but no new expected schedule amount, so retrospective differences cannot disappear; signed differences are review-only. No past return amendments.
- `jp_depreciation_schedule`: verified required straight-line/declining rate inputs and six-month prorating fixture; fixed-asset category and useful-life review remain human responsibilities. No approximation of official rates.
- `account_catalog.py`: checked that expense categories, asset, accumulated depreciation, prepaid/unpaid, tax, travel, payroll, inventory and owner accounts are represented in the backend master. Search suggestions must not create missing account codes. Existing receipt queue is **not** OCR and must not be advertised as scanned.
- No changes to JP/US market scope. `market-scope.json`: JP / JPY / ja-JP / `cross_market_sale=false`.

## Tests and gates

- Product fixtures: 8 budget tests + 7 tax/retroactive tests, including restart, idempotency, corruption, month boundary, no posting, unsafe numeric inputs and posted-only years.
- Root Factory CI wrappers added. **PASS is pending exact-head CI confirmation**; real Windows GUI and EXE must be reverified for this new branch.
- MARKET_FIT_HOLD, COMPLIANCE_REVIEW, GUI_UNVERIFIED, POST_IDENTITY_HOLD, MSIX_UNVERIFIED, STORE_HOLD. No Store submission or publication.
- Existing product source, proposal, and build contract remain review-only; this branch does **not** claim owner-controlled promotion, immutable source_sha/request_id, PRE_IDENTITY_READY, or Store registration readiness.
