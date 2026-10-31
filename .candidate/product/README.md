# Offline Image Inventory Desk

Private offline read-only image-header inventory for PNG/JPEG/GIF/BMP. Python stdlib and Tkinter only. No uploads, login, telemetry or image edits.

Run `python main.py`. Add up to 200 local images; review dimensions, format and byte count. Save/reopen JSON sessions containing only local paths with `.bak` recovery, or export CSV. File replacement requires confirmation.

Limitations: header inspection only, not full pixel validation, EXIF inspection, resizing or thumbnails. Files over 64 MiB, symlinks and invalid headers are rejected; JPEG frame header must appear in first 1 MiB. Windows GUI QA remains unverified.

Headless tests: `python -m unittest discover -s tests -v`.

## Experimental MSIX desktop screenshot check (review only)

Enable **MSIX screenshot check** after adding images; optionally select **Issues only** and **Export check CSV**. This is a read-only, header-only triage for Store listing screenshots, not image editing, upload, certification or a claim of Partner Center acceptance. It preserves previous snapshot rows when adding images.

Based on [Microsoft's MSIX screenshot guidance](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/screenshots-and-images), rechecked 2026-10-31: PNG, desktop 1366 x 768 or larger, portrait/landscape allowed, max 10 desktop screenshots and a documented 50 MB per-image limit. Landscape below 1366 x 768 and non-PNG images are flagged; portrait screenshots that meet rotated bounds require manual review because exact threshold semantics are not explicit. Files near 50 MB require manual review because byte interpretation is not specified; >50 MiB is flagged as over either common interpretation. A "BASIC_CANDIDATE" is never Store-ready: this header scanner cannot verify image pixels, content, overlay text, localization, listing completeness or actual Partner Center acceptance. A list with over 10 files is shown as a batch warning, not silently dropped.

The CSV includes per-image status, actionable explanation, rule URL, checked date, batch count and limit, plus an explicit `REVIEW_BATCH_LIMIT` flag on every row if the full batch exceeds ten screenshots. The UI displays the same batch warning even if every individual screenshot passes its basic header check.

## Inventory filters (candidate; Windows GUI QA pending)

Choose **All / Wide / Tall / Square**, optionally enter minimum width, minimum height and maximum whole MiB, then click **Apply filters**. **Reset** clears these view-only filters. The filters never delete or change source files, the inventory snapshot or original row indices; **Remove selected** removes the selected visible rows only. **Issues only** further narrows the visible list while the MSIX check is enabled. Save session and both CSV exports intentionally include the full inventory rather than the visible subset, to avoid silently losing evidence. Invalid numeric inputs show an error without replacing the active filter.

The filter interface is bilingual (English/Japanese) and needs actual 1024x768 Windows GUI inspection before any UI PASS claim. All source images remain unchanged. **MARKET_FIT_HOLD 64/100** remains in force; no paid-release or commercial MSIX permission follows from this prototype. This feature must pass real Windows GUI 1024x768 review and market validation before Store packaging.
