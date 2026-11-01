# US federal compliance scope — Double-Entry Bookkeeping US

Reviewed: 2026-10-31

## Product boundary

This product keeps local double-entry books. It is not a tax-return preparer, CPA substitute, payroll system, sales-tax engine, or legal-compliance certification tool.

Federal bookkeeping references checked:
- IRS Publication 583: https://www.irs.gov/publications/p583
- IRS Publication 538: https://www.irs.gov/publications/p538
- IRS Instructions for Form 3115: https://www.irs.gov/instructions/i3115
- IRS Instructions for Schedule C: https://www.irs.gov/instructions/i1040sc
- IRS Publication 463: https://www.irs.gov/publications/p463
- IRS Publication 587: https://www.irs.gov/publications/p587

## Mandatory safety rules

- Debits must equal credits after posting.
- Cash/accrual is not a cosmetic setting. Once records exist, the app locks the method. A later federal tax-method change may require IRS consent/procedures, including Form 3115 depending on facts.
- The app must never say that the chosen method is legally permitted for a particular user.
- P&L net income is accounting/bookkeeping output, not automatically taxable income.
- Inventory/COGS, depreciation, vehicle, meals, travel, home office, and taxes/licenses require special review.
- State/local sales tax, licensing, franchise tax and other requirements are outside automated scope.
- No current-year tax rate, mileage rate, deduction percentage, threshold or dollar limitation is hard-coded without an official tax-year-specific source.
- Do not market the product as IRS compliant or tax compliant.

## 2026-10-31 federal 12-point review (IRS primary sources)

This is a federal-scope risk register, not an IRS approval. Tax-year-specific figures must not be hardcoded, and the linked pages' Future Developments require review before release.

| Check | IRS source | Decision / gap |
| --- | --- | --- |
| 1. Sole proprietor and Schedule C | [Schedule C instructions](https://www.irs.gov/instructions/i1040sc) | Generic double-entry books, not an eligibility or filing decision |
| 2. Cash versus accrual | [Pub. 538](https://www.irs.gov/publications/p538) | **HOLD:** selection is saved and locked but journal/P&L recognition timing is not calculated differently |
| 3. Method changes, consent, Form 3115 | [Form 3115 instructions](https://www.irs.gov/instructions/i3115) | No automated method migration or legal-eligibility decision |
| 4. Income with or without 1099 | [Schedule C instructions](https://www.irs.gov/instructions/i1040sc) | Never omit recorded business income solely because no 1099 exists |
| 5. Vehicle/mileage substantiation | [Pub. 463](https://www.irs.gov/publications/p463) | REVIEW REQUIRED; evidence and business purpose must be reviewed |
| 6. Travel/meals | [Pub. 463](https://www.irs.gov/publications/p463) | REVIEW REQUIRED; no automatic deductible amount |
| 7. Home office | [Pub. 587](https://www.irs.gov/publications/p587) | REVIEW REQUIRED; no automatic qualification |
| 8. Capitalization, depreciation, Section 179 | [Pub. 334](https://www.irs.gov/publications/p334), [Schedule C](https://www.irs.gov/instructions/i1040sc) | REVIEW REQUIRED; tax-year-specific treatment excluded |
| 9. Inventory / COGS | [Pub. 334](https://www.irs.gov/publications/p334) | REVIEW REQUIRED; general journal is not a tax inventory engine |
| 10. Record retention | [Pub. 583](https://www.irs.gov/publications/p583) | No blanket three-year deletion assumption |
| 11. Computerized records and traceability | [Pub. 583](https://www.irs.gov/publications/p583) | **HOLD:** source-document references, backup/restore, audit controls require additional QA |
| 12. State/local sales tax and licensing | [Schedule C](https://www.irs.gov/instructions/i1040sc) | Outside scope, distinct from federal records |

**Change watch:** 2025 Schedule C instructions identify revised depreciation and Section 179 rules. [Form 3115 page](https://www.irs.gov/forms-pubs/about-form-3115) points to newer procedures. Do not apply historical values to another tax year without rechecking official guidance.

**Current gate:** `COMPLIANCE_HOLD` / `MARKET_FIT_HOLD`. Journal balance, trial balance and accounting P&L do not establish taxable income. Cash/accrual recognition, Windows GUI/EXE, backup/restore and document traceability must be validated before promotion/package.

## 2026-10-31 local suggestion safety review

Primary IRS sources rechecked on 2026-10-31: [Publication 583](https://www.irs.gov/publications/p583) (source-document recordkeeping), [Publication 538](https://www.irs.gov/publications/p538) (accounting methods), [2025 Schedule C instructions](https://www.irs.gov/instructions/i1040sc) (sole proprietor scope and Future Developments), [Form 3115 instructions](https://www.irs.gov/instructions/i3115) (method-change procedures), [Publication 463](https://www.irs.gov/publications/p463) (vehicle and travel), [Publication 587](https://www.irs.gov/publications/p587) (home office), and [Publication 334](https://www.irs.gov/publications/p334) (inventory/capital items). These sources are not a 2026 tax-year clearance; verify updates before any sale.

**Design action:** Local journal suggestions now match complete terms rather than accidental substrings (for example, the word `gas` must not match `Vegas`). Equal-confidence conflicting account candidates return no suggestion; the user must select and confirm accounts and amounts. Risky accounts still display `REVIEW REQUIRED`, with confidence and matched evidence, and posting remains a separate manual action. No tax deduction is approved, no federal accounting-method eligibility is inferred, and no method conversion is implemented. The product remains **COMPLIANCE_HOLD / MARKET_FIT_HOLD** pending source traceability, cash/accrual recognition, Windows GUI, and complete accounting QA.
