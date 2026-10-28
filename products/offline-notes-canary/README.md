# Offline Notes Canary

Internal APP conveyor canary: real offline Tkinter Windows notes GUI. No API keys, accounts, telemetry, downloads, or third-party dependencies. Not Store-certified or sale-ready.

Run: python main.py (Python 3.12). New, Open, Save, Search, Export TXT, Delete, Japanese/English switch. Ctrl+N/S/O/F. Save/Open/Exit prompt for unsaved changes. JSON saved atomically with valid previous backup (.bak); 5 MB and 1000-note limits.

Headless tests: python -m unittest discover -s tests -v. Real Windows EXE and 1024x768 GUI/installation QA remain required. Prior local GUI screenshots do not prove this exact committed revision.
