# JP bookkeeping: effective-date tax calculator guard (2026-11-01)

Review-only stacked on Draft PR #69 / #61. Market remains JP, currency JPY.

## Backend
- Added a transaction-date/category gate to consumption-tax **reference** calculation.
- Explicit category choice required; uncertain/exempt category returns REVIEW_REQUIRED without tax figures.
- 2019-09-30 and earlier historical rates are not guessed.
- 2019-10-01 through 2027-03-31: rate hints are 10% standard / 8% eligible food or subscription newspaper when explicitly selected.
- 2027-04-01 and later: return REVIEW_REQUIRED without a numeric tax amount, because NTA reports a 2027–2029 food-rate change and rates must not be evergreen.
- No automated tax determination, deduction, journal posting, or tax return.

## Beginner UX
- Tax dialog now asks for transaction date and plain-language category before showing any numbers.
- "要確認" is the safe default. A review-required case shows why and displays no invented tax.
- Calculation is labeled reference-only and never silently posts.

## Official sources (checked 2026-11-01)
- NTA No.6303 https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6303.htm — standard 10%, reduced 8%, announced 2027-04-01 through 2029-03-31 food-rate change.
- NTA No.6102 https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6102.htm — eligible food, alcohol/dining exclusions and qualifying newspaper rules.
- NTA No.2070 https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2070.htm — bookkeeping / source retention, not tax-compliance certification.
- NTA depreciation https://www.keisan.nta.go.jp/r1yokuaru/aoiroshinkoku/hitsuyokeihi/genkashokyakuhi/teigakuho.html — method, guarantee and revised rate require official year-specific references.
- IRS Pub. 583 https://www.irs.gov/publications/p583 and Pub. 946 https://www.irs.gov/publications/p946 — separate US method and depreciation regimes; no US rules added.
- GnuCash https://www.gnucash.org/features.phtml — baseline accounting parity benchmark, not proof of willingness to pay.

## Remaining gate
Market fit, Windows EXE, 1024x768 real GUI, source/Identity binding, signed MSIX and Store submission are not passed. Review-only, no merge.
