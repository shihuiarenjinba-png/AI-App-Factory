# US bookkeeping tax and depreciation guard — 2026-11-01

Sources rechecked 2026-11-01 JST:
- IRS Publication 583 https://www.irs.gov/publications/p583 — recordkeeping and supporting evidence.
- IRS Publication 538 https://www.irs.gov/publications/p538 — method changes and accounting-method limits.
- IRS Publication 946 (2025) https://www.irs.gov/publications/p946 — tax-year-specific depreciation and Section 179 changes; no rate is inferred.
- IRS Form 3115 https://www.irs.gov/instructions/i3115 — retrospective method changes may require professional review.

Safety fixes: reject spoofed IRS source URLs (HTTPS hostname, not substring), NaN/Infinity and out-of-range percentages; reject schedules exceeding 100% of basis; include posted-only years in retrospective difference rather than hiding over-postings. Existing UI still asks users to enter rates manually. No automatic tax deduction, no filing, no state sales-tax rate lookup, no claim of tax compliance. All tax schedules remain REVIEW_REQUIRED. Product remains COMPLIANCE_HOLD and MARKET_FIT_HOLD pending legal and Windows GUI/EXE QA.
