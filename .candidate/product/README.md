# File Integrity Ledger

Offline Windows desktop utility for creating and verifying read-only SHA-256 snapshots of **selected** local files. Original source files are never deleted, renamed, uploaded, or repaired. No network access, login, analytics, elevated privileges, or third-party runtime dependencies.

## Run

Python 3.12 with Tkinter: \`python main.py\`. Choose **Add files** (up to 100 regular files, each up to 256 MiB), then **Save snapshot** to store a baseline. **Open snapshot** and **Verify now** later to see unchanged, modified, missing, and error statuses. **Export CSV** saves a reviewable report with spreadsheet-formula escaping. **Remove row** only removes the list entry, never a disk file. The language button switches between English and Japanese.

JSON snapshots use atomic replacement; the previous valid version is kept as a \`.bak\` file. A damaged snapshot prompts before loading the backup. Hashes are computed from selected local files only, not from folders or remote locations. Hashes are not digital signatures or a proof of authorship.

## Tests

\`python -m unittest discover -s tests -v\` tests hashing, file changes, missing paths, invalid snapshots, duplicate paths, size limits, atomic saves, backup recovery, CSV escaping, and bilingual labels without a display server.

## Quality limits

Windows EXE is an unsigned QA artifact, not a Store-ready MSIX. Windows GUI/install, 1024x768 visual evidence, packaging Identity, signature, accessibility and commercial QA require separate verification. No such PASS is claimed from headless tests.
