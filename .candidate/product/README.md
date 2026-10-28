# Offline Text Diff Desk

Original offline Windows Tkinter utility for comparing two local UTF-8 documents. Select left and right files (max 1 MiB and 10,000 lines each), Compare, optionally ignore whitespace, and export a unified diff. Read-only source panes, bilingual English/Japanese UI, 1024x768 initial window. No login, network, telemetry or privileged access.

Save session writes only file paths and options to JSON using atomic replacement and a previous-version .bak. Reopen after restart to reread both files, or recover a damaged session from the backup. Source files are never modified, renamed, deleted or uploaded. Explicit output paths and overwrite confirmation are required. Invalid UTF-8, symlinks and binary input are rejected.

Run: `python main.py`. Test: `python -m unittest discover -s tests -v`.

The Windows EXE is unsigned QA-only. No Windows GUI/install, accessibility, Store MSIX or commercial-quality PASS is claimed without separate evidence.

Safety update: the explicit output and its automatic .bak are both checked against protected source documents (including hardlinks). New output and replacement backup are written to temporary files before atomic replacement; failed backup writes preserve the previous output and backup.
