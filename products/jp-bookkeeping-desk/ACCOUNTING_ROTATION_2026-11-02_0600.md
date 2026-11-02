# JP bookkeeping month-end cutoff repair — 2026-11-02 JST

Official sources checked 2026-11-02:
- https://www.nta.go.jp/taxes/shiraberu/shinkoku/kojin_jigyo/0023005-091_01.pdf — 日々の仕訳→仕訳帳→総勘定元帳→試算表→貸借対照表/損益計算書という記帳・決算の流れ。
- https://www.keisan.nta.go.jp/r7yokuaru_sp/aoiroshinkoku/shunyukingaku/scid1711.html — 月別の売上・仕入金額は対象月の月計を区分する必要がある。
- https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2080.htm — 日々の取引の記帳・帳簿等保存。これは申告認定を意味しない。

Fix: `monthly_close.py` previously exported a selected-month journal beside `store.trial()/pnl()/bs()` calculated from all posted dates. Now trial and balance sheet are as-of selected month end; month P/L and calendar-year-to-date P/L are distinct. Prior-year unclosed P/L is displayed explicitly as a B/S bridge, never silently treated as current-year income. Month journal and month debit/credit control use the same window. Later postings are excluded, and Jan/Feb/backdated correction fixtures assert reconciliation. Beginner HTML shows period, unprocessed receipts and human review actions.

Boundaries: no tax-return generation, no automatic deductibility, no retroactive filing amendment. PDF remains an optional local Edge print of the HTML; electronic original documents must be retained separately. This report is an accounting review artifact, not a compliance certification.
