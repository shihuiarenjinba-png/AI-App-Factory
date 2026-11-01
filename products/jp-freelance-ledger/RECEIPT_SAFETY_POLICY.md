# Receipt / invoice image classification safety policy — Japan

Reviewed: 2026-11-01

## What image recognition can and cannot prove

A receipt image can provide evidence about visible facts such as:
- merchant/payee name
- transaction date/time
- line-item text
- gross/net/tax amounts
- invoice/registration identifiers when printed
- payment method hints
- document number

A receipt image **cannot by itself prove tax deductibility**. Business purpose, private use, household allocation, relationship to revenue, capitalization vs expense, family/related-party rules, and other facts can exist outside the image.

Primary NTA basis:
- Necessary expenses are costs directly required to earn business income and other business-related selling/general/administrative expenses.
- Household expenses are not deductible.
- Mixed household/business expenses are deductible only for the clearly separable business-use portion using a reasonable basis.
- Income/resident tax and certain penalties are not necessary expenses.
Sources:
- https://www.nta.go.jp/publication/tenji/pdf/all.pdf
- https://www.keisan.nta.go.jp/r6yokuaru/aoiroshinkoku/hitsuyokeihi/keihinochishiki/keihinochishiki.html

## Four separate accuracy layers

1. OCR_FIELD_ACCURACY
   - date, merchant, amount, tax, invoice number, line items.
2. TRANSACTION_INTERPRETATION_ACCURACY
   - purchase vs refund, cash vs card, multiple tax rates, receipt totals.
3. ACCOUNT_SUGGESTION_ACCURACY
   - top-1 / top-3 bookkeeping account suggestion.
4. TAX_ELIGIBILITY
   - whether an item is a necessary expense, private expense, mixed expense, asset, or otherwise tax-sensitive.

Layer 4 is **never auto-approved from image alone**.

## Mandatory states

- RAW_DOCUMENT
- OCR_EXTRACTED
- NEEDS_FIELD_REVIEW
- BOOKKEEPING_CANDIDATE
- TAX_REVIEW_REQUIRED
- PERSONAL_OR_NONDEDUCTIBLE_CANDIDATE
- ASSET_REVIEW_REQUIRED
- READY_TO_POST
- POSTED

Only a human-confirmed or rule-supported record may enter READY_TO_POST.
Receipt OCR must never jump directly from OCR_EXTRACTED to POSTED.

## Business-purpose gate

Before an expense candidate can be READY_TO_POST, the record must have:
- business purpose or memo,
- payer/payee,
- date,
- amount,
- suggested account,
- source document reference,
- private/business-use answer when relevant,
- capitalization/asset review when relevant.

Examples that always require review:
- home rent/utilities/phone/internet
- meals/entertainment
- vehicle expenses
- PC/camera/equipment and other long-lived items
- taxes and penalties
- family/related-party payments
- repairs that may be capital improvements
- ambiguous Amazon/department-store receipts
- cash withdrawals
- mixed personal/business shopping

## Accuracy benchmark — do not claim a number before measurement

The product must not display an OCR or classification accuracy percentage until a labeled benchmark set has been run.

Release benchmark must report separately:
- exact date accuracy
- exact total-amount accuracy
- merchant extraction accuracy
- tax-rate/tax-amount accuracy
- duplicate-document detection precision/recall
- top-1 account suggestion accuracy
- top-3 account suggestion accuracy
- ambiguous-case REVIEW recall
- unsafe auto-post count

The required unsafe auto-post count is **0 by design**.

Quality targets are acceptance gates, not current measured claims:
- amount/date extraction target: >= 99% on the maintained labeled benchmark
- top-3 account suggestion target: >= 95%
- ambiguous/high-risk transaction routed to REVIEW target: >= 99%
- unsafe automatic tax-deductibility approval: 0

Until a real benchmark exists, UI wording must say:
"読み取り候補" / "仕訳候補" / "要確認"
and must not say:
"自動経費確定" / "税務上経費です".

## Batch behavior

Multiple receipt files may be processed independently.
One failed/low-quality image must not fail the entire batch.
Each document keeps its original source reference, extraction confidence, review state, and reason.
Duplicate candidates are held for review rather than silently posted.
