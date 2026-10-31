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

## One-click Store review preset (candidate)

**Review Store issues** / **Store要確認だけ表示** turns on the header-only MSIX check and Issues-only view in one click, clearing stale size and orientation filters first. It does not change, remove, upload, or certify images. A batch with more than ten screenshots still displays the explicit count warning even when all individual headers pass. Both CSV exports and session saves continue to include the entire inventory, not only the filtered rows. Windows GUI validation remains pending.

## Read-only duplicate candidates (candidate; GUI QA pending)

Click **Find duplicates / 重複候補を探す** to hash only files sharing an inventory byte size with another file. Identical SHA-256 digests are grouped as D1, D2, etc., and the view shows candidate duplicates. **Reset / 解除** returns to the full list. Stale orientation, size and Store-issues filters are cleared before duplicate review. The tool never deletes or edits images and does not upload content; the full inventory remains in session saves and CSV exports. Hashes are recomputed on demand, not cached across file additions, removals or session reloads.

The operation checks regular files, symlinks, file sizes and modifications during hashing; missing or changed files are skipped with an error. This is exact-byte duplicate triage, not visual similarity or proof that two different encodings depict the same image. No duplicate is automatically removed. Actual Windows 1024x768 GUI QA and the product's **MARKET_FIT_HOLD 64/100** still block commercial packaging.

## One-click actionable review CSV (candidate; Windows GUI QA pending)

**Export review report / 要確認レポートCSV** recomputes same-size SHA-256 duplicate candidates on demand, combines them with the conservative MSIX screenshot-header checks, and writes a single local CSV. Rows needing attention appear first; `original_index` retains the source inventory order. Fields include dimensions, orientation, issue/action, duplicate group, duplicate scan error, batch warning, official rule URL and the check date. This is an evidence review, not a Microsoft Store acceptance claim. No images are changed or deleted. A missing or changed file in a duplicate scan is recorded as an error rather than a false match; image-header checks still refer to the saved inventory snapshot. Source image paths are protected from CSV overwrite. The button is placed on a separate toolbar row to reduce horizontal crowding at 1024px, but **real Windows 1024x768 GUI QA has not been performed**.

This feature does not change the product's **MARKET_FIT_HOLD 64/100** or authorize MSIX packaging, Store submission, or promotion.


## Source freshness check for review CSV (candidate)

The one-click review report now re-reads **every** source image header before export, including images that have no same-size duplicate. `source_check` is `SOURCE_MATCH`, `SOURCE_CHANGED` or `SOURCE_UNAVAILABLE`; `source_action` explains how to rescan. Stale or missing images always appear in the attention group, and the UI summary counts them. The report preserves the original saved snapshot for audit rather than silently replacing it. Re-add or reopen the session to rescan before relying on results. A matching header and byte count is **not** a cryptographic guarantee of unchanged pixels, and this tool is not Store certification. Sources remain read-only; regression tests cover changed, missing and recovered images. Real Windows GUI QA remains pending.
