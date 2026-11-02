# JP Bookkeeping: local receipt backup / restore — market and safety evidence

Checked: 2026-11-02 JST. Scope: JP-only local bookkeeping, not a tax-filing or statutory-compliance product.

## Sources and concrete design consequences

- [NTA No.2080, 2026-04-01](https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2080.htm): daily transaction records and associated documents require appropriate preservation, with different periods depending on document/book type. Consequence: keep journal DB and original receipt bytes together; do **not** claim legal sufficiency.
- [NTA No.6496, 2026-04-01](https://www.nta.go.jp/taxes/shiraberu/taxanswer/shohi/6496.htm): records and invoices are generally both relevant to input-tax-credit requirements, subject to exceptions. Consequence: no automatic expense/deduction approval from a backup or file hash.
- [GnuCash Backup wiki, checked 2026-11-02](https://wiki.gnucash.org/wiki/Backup): free alternative already supports local file backup and manual restoration. Backup alone is not a paid differentiator.
- [freee file-box download help, updated 2026-04-20](https://support.freee.co.jp/hc/ja/articles/115005133903-%E3%83%95%E3%82%A1%E3%82%A4%E3%83%AB%E3%81%AE%E7%B5%9E%E3%82%8A%E8%BE%BC%E3%81%BF-%E5%89%8A%E9%99%A4-%E7%84%A1%E8%A6%96-%E3%83%80%E3%82%A6%E3%83%B3%E3%83%AD%E3%83%BC%E3%83%89): cloud competitor allows bulk receipt download, but notes that downloaded files alone do not satisfy all record-management requirements. Consequence: show caution rather than a compliance badge.
- [freee file-box handling, updated 2026-10-30](https://support.freee.co.jp/hc/ja/articles/4413886154649-%E5%8F%96%E5%BC%95%E5%85%88%E3%81%A8%E3%82%84%E3%82%8A%E5%8F%96%E3%81%97%E3%81%9F%E5%90%84%E7%A8%AE%E5%B8%B3%E7%A5%A8%E9%A1%A8%E9%A1%9E%E3%82%92%E3%83%95%E3%82%A1%E3%82%A4%E3%83%AB%E3%83%9C%E3%83%83%E3%82%AF%E3%82%B9%E3%81%A7%E7%AE%A1%E7%90%86%E3%81%99%E3%82%8B-%E9%9B%BB%E5%AD%90%E5%B8%B3%E7%B0%BF%E4%BF%9D%E5%AD%98%E6%B3%95): version/change history matters. Consequence: receipt event history is included in SQLite snapshot, not reconstructed from current status.
- [GnuCash user backup confusion, 2023-02-06](https://www.reddit.com/r/GnuCash/comments/10vcing): a user described confusing Save As with backup and editing the wrong file. Anecdotal UX signal, not a representative buyer survey. Consequence: restore to a *new* ledger directory and explicitly say the open ledger is unchanged.
- [GnuCash user restore confusion, 2024-02-19](https://www.reddit.com/r/GnuCash/comments/1auuo1x): user confusion about file formats during recovery. Consequence: dry-run inspect and actionable failure message before restore.

## Implemented, without copying competitors

1. SQLite consistent snapshot + preserved receipt-original bytes in one ZIP, manifest with ledger UUID, file SHA-256 and sizes; archive re-read verification before atomic publish.
2. Dry-run rejects missing/changed bytes, duplicate entries, traversal, symlink entries, orphan blobs, wrong ledger IDs (when explicitly checked), legacy records without originals, unsafe destinations.
3. Restore creates a separate directory; it never overwrites an open book. The original external source path may require manual revalidation after moving PCs.
4. Novice buttons: バックアップを作成 / 復元前の確認 / 別の帳簿として復元 / 復旧できない理由.
5. No cloud sync, OCR accuracy claim, tax-deductibility claim, legal-compliance claim, encryption claim, or tamper-proof/authenticity claim.

## Market decision

**MARKET_FIT_HOLD.** Backup is a reliability baseline already offered by free competitors. The hypothesis is that a beginner values one portable bundle containing journal and original evidence with preflight safety checks, but willingness to pay is unmeasured. Real Windows GUI 1024x768 at 125/150% DPI, recovery-to-open-ledger usability, and independent buyer tasks remain unverified. Do not score higher or promote to Store packaging on the basis of synthetic tests alone.

Consumer verdict now: **NO** — a recovered ledger is written safely but the GUI still lacks a guided way to open that restored book on the next launch. This is the next consumer usability gap to resolve, not an excuse to add ERP complexity.
