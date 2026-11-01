# Accounting four-product tax/depreciation safety audit

Checked: 2026-11-01 JST. Scope: JP freelance PR #59, US freelance PR #60, JP bookkeeping PR #61, US bookkeeping PR #62. This is a development review, not legal/tax advice. Branch is stacked on US freelance PR #60 and does not modify the other three product branches.

## Official sources and design consequences

| Jurisdiction | Primary source | Consequence |
| --- | --- | --- |
| JP | NTA No. 6101 https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6101.htm | Standard 10% / reduced 8% are current categories; tax applicability needs review. |
| JP | NTA No. 6102 https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6102.htm | Future change: official page discusses a temporary food rate change from 2027-04-01 to 2029-03-31. Do not assume 8% forever. |
| JP | NTA No. 6375 https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6375.htm | Tax-inclusive and tax-exclusive accounting must be distinguished. |
| JP | NTA depreciation https://www.keisan.nta.go.jp/r1yokuaru/aoiroshinkoku/hitsuyokeihi/genkashokyakuhi/teigakuho.html | Declining balance requires statutory depreciation, revised and guarantee rates; no guessed rate. |
| JP | NTA months https://www.keisan.nta.go.jp/r7yokuaru/aoiroshinkoku/hitsuyokeihi/genkashokyakuhi/shokyakukikan.html | The cited partial-year example counts the first month. |
| JP | NTA small assets https://www.nta.go.jp/taxes/shiraberu/taxanswer/hojin/5408.htm | Corporate small-asset threshold changed from below JPY 300,000 to below JPY 400,000 for acquisitions from 2026-04-01. This corporate rule is not automatically an individual sole-proprietor rule. |
| US | IRS Pub. 946 (2025) https://www.irs.gov/publications/p946 | 2025 changes in bonus depreciation / Section 179 depend on acquisition and service dates. Book depreciation is not tax depreciation. |
| US | IRS Pub. 583 https://www.irs.gov/publications/p583 | Source-document traceability, journal/ledger balancing, retention. Book net is not taxable income. |
| US | IRS Pub. 538 https://www.irs.gov/publications/p538 | Accounting method changes may require IRS consent. |
| US | IRS Form 3115 https://www.irs.gov/forms-pubs/about-form-3115 | Section 481(a) / retrospective tax adjustments require review; never automatically amend returns. |
| US | IRS recordkeeping https://www.irs.gov/businesses/small-businesses-self-employed/what-kind-of-records-should-i-keep | Keep source documents and legible underlying records. |

## Four-product source audit

- **JP PR #59 / #61**: existing configurable tax/depreciation helpers need finite-value/rate-range validation, official rate provenance, tax-year profiles, and fixtures for 2026/2027 changes. Keep MARKET_FIT_HOLD / COMPLIANCE_HOLD.
- **US PR #60 / #62**: existing manual sales tax has no required jurisdiction; book depreciation lacks complete finite and 0-100% checks; custom tax depreciation can exceed 100% cumulatively; IRS URL substring checking accepts lookalike hosts. These helpers must not automatically post or claim tax results.
- **All four**: retrospective reconciliation must include over-posted years absent from new schedule. Country-specific chart/category master and suggestion codes must be cross-checked; cross_market_sale=false is mandatory.

## Code change and scope

This stacked branch adds review-only \`products/us-freelance-ledger/asset_review.py\`: mandatory state/locality/source note for manual sales-tax arithmetic, finite Decimal validation, BOOK_ONLY straight-line worksheet, HTTPS IRS host check, acquisition/service-date checks, and retrospective book comparison including over-postings. 13 local regression tests passed 2026-11-01.

**Not integrated into GUI yet.** Existing \`tax_assets.py\` is untouched because it was edited in the preceding 12 minutes. Do not treat this as a resolved package gate. Tax calculations, filing, posted journal changes and tax-deduction claims remain forbidden.

Next: owner-reviewed integration, both US products' regression fixtures, JP year/entity-scoped profiles, country master consistency tests, Windows GUI/EXE QA, and package gates. No Store submit/publish.
