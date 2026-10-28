# Offline Image Inventory Desk

Private offline read-only image-header inventory for PNG/JPEG/GIF/BMP. Python stdlib and Tkinter only. No uploads, login, telemetry or image edits.

Run `python main.py`. Add up to 200 local images; review dimensions, format and byte count. Save/reopen JSON sessions containing only local paths with `.bak` recovery, or export CSV. File replacement requires confirmation.

Limitations: header inspection only, not full pixel validation, EXIF inspection, resizing or thumbnails. Files over 64 MiB, symlinks and invalid headers are rejected; JPEG frame header must appear in first 1 MiB. Windows GUI QA remains unverified.

Headless tests: `python -m unittest discover -s tests -v`.
