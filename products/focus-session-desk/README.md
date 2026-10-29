# Focus Session Desk — offline focus timer and task checklist

A local-only Windows desktop prototype for a focused work session and a small checklist. No login, cloud, tracking, network access, payment, or background service.

## Run

Python 3.12+ with Tkinter:

```sh
python main.py
python -m unittest discover -s tests -v
```

The GUI uses only Python's standard library. All task data, language preference, and focus duration are stored under `%APPDATA%/FocusSessionDesk/state.json` on Windows (or `~/.local/share/FocusSessionDesk/state.json` when APPDATA is unavailable).

## Features

- Add, rename, mark complete, reorder, and delete tasks. Double-click a row to toggle completion.
- Start, pause, resume, and reset a focus countdown; set duration from 1 to 180 minutes. The timer uses a monotonic clock while running.
- Changes are saved locally and atomically with a last-known-good `.bak` copy. Malformed or oversized state is rejected; a valid backup can be restored.
- Exiting an active/paused session asks for confirmation. After restarting, the app shows an interrupted-session notice and starts from an idle timer. It does **not** pretend time continued while closed.
- Switch Japanese/English at any time. Basic controls remain visible at 1024×768; no claim of actual Windows GUI QA is made.
- Press Enter in the task entry to add; task selection enables editing, toggling, deletion and reordering.

## Honest limitations

No OS notifications, tray background timer, calendar sync, statistics, accounts, or network features. The focus countdown only runs while the application is open. The executable, MSIX signing, Store certification, accessibility audit and real Windows install/GUI QA are separate downstream gates. This directory is a **candidate**, not a promoted Factory product until the standard lifecycle validates and promotes it.

## Quality checks

Headless regression tests cover task CRUD, limits, ordering, timer state transitions and pause/resume, validation, Unicode, JSON corruption, backup restoration, interrupted-session semantics and atomic-write failure. A Windows EXE artifact must be generated from a later immutable promoted source SHA and correlated to a Provisioner request_id.
