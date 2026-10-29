# Offline Notes Canary

Internal APP conveyor canary: real offline Tkinter Windows notes GUI. No API keys, accounts, telemetry, downloads, or third-party dependencies. Not Store-certified or sale-ready.

Run: python main.py (Python 3.12). New, Open, Save, Search, Export TXT, Delete, Japanese/English switch. Ctrl+N/S/O/F. Save/Open/Exit prompt for unsaved changes. JSON saved atomically with valid previous backup (.bak); 5 MB and 1000-note limits.

Headless tests: python -m unittest discover -s tests -v. Real Windows EXE and 1024x768 GUI/installation QA remain required. Prior local GUI screenshots do not prove this exact committed revision.

Safety revision 2: if writing the previous-version backup fails, saving stops without replacing the primary notes database. TXT export refuses the currently open notes JSON file, its .bak path, and hardlink aliases even when the file chooser suggests an overwrite. Four headless regressions cover these protections; Windows GUI remains unverified.

Safety revision 3: Save refuses unrelated JSON, damaged primary files (even with a valid backup), and unrelated/damaged backup paths. Users must choose a new filename rather than lose existing data. Four new headless regressions cover these cases; GUI remains unverified.
