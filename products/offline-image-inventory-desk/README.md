# Offline Image Inventory Desk

Private offline read-only image-header inventory for PNG/JPEG/GIF/BMP. Python stdlib and Tkinter only. No uploads, login, telemetry or image edits.

Run `python main.py`. Add up to 200 local images; review dimensions, format and byte count. Save/reopen JSON sessions containing only local paths with `.bak` recovery, or export CSV. File replacement requires confirmation.

Limitations: inventory checks image headers only, not full pixel validation or EXIF inspection. The client HTML report uses SHA-verified small original PNG/JPEG/GIF bytes scaled in the browser, not decoded/resized thumbnails or visual pixel-diff analysis. Files over 64 MiB, symlinks and invalid headers are rejected; JPEG frame header must appear in first 1 MiB. Windows GUI QA remains unverified.

Headless tests: `python -m unittest discover -s tests -v`.

## Experimental MSIX desktop screenshot check (review only)

Enable **MSIX screenshot check** after adding images; optionally select **Issues only** and **Export check CSV**. This is a read-only, header-only triage for Store listing screenshots, not image editing, upload, certification or a claim of Partner Center acceptance. It preserves previous snapshot rows when adding images.

Based on [Microsoft's MSIX screenshot guidance](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/screenshots-and-images), rechecked 2026-10-31: PNG, desktop 1366 x 768 or larger, portrait/landscape allowed, max 10 desktop screenshots and a documented 50 MB per-image limit. Landscape below 1366 x 768 and non-PNG images are flagged; portrait screenshots that meet rotated bounds require manual review because exact threshold semantics are not explicit. Files near 50 MB require manual review because byte interpretation is not specified; >50 MiB is flagged as over either common interpretation. A "BASIC_CANDIDATE" is never Store-ready: this header scanner cannot verify image pixels, content, overlay text, localization, listing completeness or actual Partner Center acceptance. A list with over 10 files is shown as a batch warning, not silently dropped.

The CSV includes per-image status, actionable explanation, rule URL, checked date, batch count and limit. All source images remain unchanged. **MARKET_FIT_HOLD 64/100** remains in force; no paid-release or commercial MSIX permission follows from this prototype. This feature must pass real Windows GUI 1024x768 review and market validation before Store packaging.


## Read-only image delivery snapshot comparison (review-only revision)

For small production studios: 1. Save folder snapshot as JSON outside the image folder; 2. Open baseline later and Compare folder; 3. Export changes to CSV/JSON outside both image folders. The comparison window lists ADDED, REMOVED, MODIFIED and UNCHANGED relative paths. Full-file SHA-256, dimensions and byte counts support same-name content-change review. Renames are added+removed, not inferred. Repeated scans are deterministic.

This is not backup, legal proof, cryptographic signing, pixel validation or synchronization. Only PNG/JPEG/GIF/BMP; max 200 image entries and 64 MiB each. Symlinks, read failures and files changing mid-scan fail closed instead of falsely reporting deletion. Never writes, repairs, moves or deletes source images. A baseline/report must be saved outside scanned image folders.

The why-pay hypothesis is a three-step, non-destructive delivery evidence report, not duplicate detection. Free tools already compare content and detect duplicates. See the market research JSON under docs/market. MARKET_FIT_HOLD remains 64/100; Windows GUI and commercial MSIX remain unverified.


## Client-readable HTML delivery report (review-only, 2026-11-02)

After step 2 (compare), step 3 offers **Save client HTML with previews** before the existing TXT/CSV/JSON exports. The HTML is a standalone offline file: a readable ADDED/REMOVED/MODIFIED/UNCHANGED summary, SHA-256 and dimensions/bytes, creation-time disclaimer, and small inline image previews when the exact local bytes still match the comparison. Preview display is capped at 16 tiles, 96 KiB per original file, and 8 megapixels. PNG/JPEG/GIF only; BMP and larger files receive an honest no-preview label. The output is capped at 4 MiB, HTML text is escaped, and CSP blocks scripts and external network content. No source files are written or copied.

The baseline JSON **never contains old image bytes**. When a previous version no longer exists or has changed, the report shows that its preview is unavailable; it never invents a before image. A missing, modified, linked or unreadable *current* image blocks HTML export, invalidates the GUI's previous comparison, and requires a fresh scan. The report must be saved outside both image folders. The app shows the selected destination path after success. Date shown is report creation time, not proof of file modification/delivery time.

Windows/Ubuntu unit tests, hosted Windows Tk DPI smoke and packaged-EXE replay are machine evidence only. No LOCAL_GUI_PASS or human buyer evidence is claimed. This revision remains **MARKET_FIT_HOLD 64/100, independent buyers 0/5, why-pay unverified**; do not promote, rebind Identity, build commercial MSIX or submit to Store.
