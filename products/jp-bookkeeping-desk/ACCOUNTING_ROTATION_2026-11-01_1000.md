# JP Bookkeeping Desk — verified receipt intake / beginner workflow

Reviewed: **2026-11-01 JST**. Scope: JP-only, JPY, `cross_market_sale=false`. No tax return, tax deductibility, OCR, or automatic journal posting.

## Implemented
- Existing receipt queue migrated in place with optional SHA-256 and byte size; legacy path-only rows are **not** presented as verified.
- Multi-select PNG/JPEG/PDF/WebP: reject missing, empty, over 20 MiB, unsupported extension, and mismatched file signatures; report errors per file without stopping valid neighbors.
- Reject duplicate file paths or identical SHA-256 content; preserve status `PENDING`, keep an intake audit entry, and show the most recent verified items after reopening the app.
- Beginner path: **証憑を追加 → 科目と金額を確認 → 記帳**. Show added/duplicate/error counts and a view-only queue; clearly state **no OCR and no automatic posting**.
- Original files are **not copied**. They must remain at their paths, and any later OCR/attachment linkage must recheck SHA-256. Signature check is **not** full image/PDF decoding or malware scanning.

## Primary official references checked 2026-11-01
- NTA No.2080 (令和8年4月1日現在): https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2080.htm — daily transaction records and supporting documents matter; path/hash-only intake does **not** satisfy legal electronic retention requirements by itself.
- NTA No.2106 (令和8年4月1日現在): https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2106.htm — declining-balance depreciation requires appropriate rate, revised rate, and guarantee rate; this receipt feature does not determine any tax rate or depreciation.
- NTA consumption tax rate reference (令和7年4月1日現在): https://www.keisan.nta.go.jp/r7yokuaru/shohizei/shohizeishikumi/kazeihyojunzeiritsu/zeiritsu.html — 10%/8% examples are jurisdiction/date-dependent, and receipts are not auto-classified.
- IRS Publication 583 (12/2024): https://www.irs.gov/publications/p583 — source-document traceability; **US logic not imported into JP product**.
- IRS Publication 538 (01/2022): https://www.irs.gov/publications/p538 — cash/accrual and accounting method consistency; no US method switch in JP product.
- IRS Publication 946 (2025, with Future Developments): https://www.irs.gov/publications/p946 — US depreciation rules are tax-year-specific; no US MACRS/Section 179/bonus constants imported.
- GnuCash baseline: https://www.gnucash.org/features.phtml — mature free accounting functionality makes audit-friendly document intake a baseline rather than a claim of parity.

## Validation and remaining gates
- Locally ran `python -m unittest discover -s tests -p test_jp_receipt_import_verified.py -v`: **4/4 PASS** on isolated SQLite fixtures. These tests cover mixed good/bad batch, duplicate content, restart, legacy migration, size and format refusal.
- Existing product-wide CI and Windows GUI/EXE are **not** marked PASS until the new Draft PR workflows finish.
- Pending: actual Windows 1024×768 visual QA, receipt link to journal after explicit human confirmation, copied/immutable evidence vault and applicable electronic-book preservation compliance review, market-fit, formal Factory promotion, signed MSIX.
- No main/release change, Partner Center operation, identity guess, merge, or Store submission.
