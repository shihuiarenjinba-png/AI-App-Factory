"""Focus Session Desk: local-only task checklist and honest focus timer."""
import json
from datetime import date
import os
import tempfile
import time
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import messagebox, ttk

MAX_TASKS = 200
MAX_BYTES = 200000
MAX_HISTORY = 500
MIN_MINUTES = 1
MAX_MINUTES = 180
FOCUS_PRESETS = (25, 50)


def new_task(title):
    title = validate_title(title)
    return {"id": uuid.uuid4().hex, "title": title, "done": False}


def validate_title(title):
    if not isinstance(title, str) or not title.strip() or len(title) > 180:
        raise ValueError("Task title must contain 1-180 characters")
    if any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in title):
        raise ValueError("Task title contains invalid characters")
    return title.strip()


def validate_minutes(value):
    if type(value) is not int or not MIN_MINUTES <= value <= MAX_MINUTES:
        raise ValueError("Focus duration must be 1-180 minutes")
    return value


def validate_document(data):
    expected = {"schema", "language", "minutes", "tasks", "session"}
    if not isinstance(data, dict) or not expected.issubset(data) or set(data) - expected - {"history"}:
        raise ValueError("Unsupported data format")
    if type(data["schema"]) is not int or data["schema"] != 1:
        raise ValueError("Unsupported data schema")
    if data["language"] not in ("en", "ja"):
        raise ValueError("Invalid language")
    validate_minutes(data["minutes"])
    tasks = data["tasks"]
    if not isinstance(tasks, list) or len(tasks) > MAX_TASKS:
        raise ValueError("Invalid task list")
    seen = set()
    for task in tasks:
        if not isinstance(task, dict) or set(task) != {"id", "title", "done"}:
            raise ValueError("Invalid task")
        ident = task["id"]
        if not isinstance(ident, str) or len(ident) != 32 or any(c not in "0123456789abcdef" for c in ident) or ident in seen:
            raise ValueError("Invalid or duplicate task ID")
        seen.add(ident)
        validate_title(task["title"])
        if type(task["done"]) is not bool:
            raise ValueError("Invalid task completion state")
    if data["session"] not in ("idle", "interrupted"):
        raise ValueError("Invalid session marker")
    history = data.get("history", [])
    if not isinstance(history, list) or len(history) > MAX_HISTORY:
        raise ValueError("Invalid focus history")
    seen_sessions = set()
    for item in history:
        if not isinstance(item, dict) or set(item) != {"id", "day", "minutes"}:
            raise ValueError("Invalid focus history entry")
        ident, day, minutes = item["id"], item["day"], item["minutes"]
        if (not isinstance(ident, str) or len(ident) != 32
                or any(c not in "0123456789abcdef" for c in ident)
                or ident in seen_sessions):
            raise ValueError("Invalid or duplicate session ID")
        seen_sessions.add(ident)
        if not isinstance(day, str) or len(day) != 10:
            raise ValueError("Invalid focus history date")
        try:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError("Noncanonical date")
        except ValueError as exc:
            raise ValueError("Invalid focus history date") from exc
        validate_minutes(minutes)
    return data


def record_completed_session(document, minutes, day=None):
    """Only call when the timer reaches finished, not on pause or restart."""
    validate_minutes(minutes)
    day = day or date.today().isoformat()
    if date.fromisoformat(day).isoformat() != day:
        raise ValueError("Invalid session date")
    document.setdefault("history", []).append({
        "id": uuid.uuid4().hex, "day": day, "minutes": minutes})
    document["history"] = document["history"][-MAX_HISTORY:]
    validate_document(document)


def today_totals(document, day=None):
    day = day or date.today().isoformat()
    sessions = [entry for entry in document.get("history", []) if entry["day"] == day]
    return len(sessions), sum(entry["minutes"] for entry in sessions)


def persist_completed_session(document, path, minutes, day=None):
    """Persist one finished session before exposing it in the live UI.

    On any write failure the caller's document stays unchanged. Retrying
    after a failed write cannot create a phantom completed session.
    """
    import copy
    candidate = copy.deepcopy(document)
    record_completed_session(candidate, minutes, day)
    candidate["session"] = "idle"
    save_document(path, candidate)
    return candidate


def blank_document():
    return {"schema": 1, "language": "ja", "minutes": 25, "tasks": [], "session": "idle", "history": []}


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _read_one(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > MAX_BYTES:
        raise ValueError("Unsafe or oversized state file")
    document = validate_document(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs))
    document.setdefault("history", [])  # Migrate older schema-1 state in memory.
    return document


def load_document(path):
    path = Path(path)
    reason = None
    for candidate in (path, path.with_name(path.name + ".bak")):
        try:
            return _read_one(candidate), candidate != path
        except (OSError, ValueError, UnicodeError, RecursionError) as exc:
            if reason is None:
                reason = str(exc)
    if not path.exists() and not path.with_name(path.name + ".bak").exists():
        return blank_document(), False
    raise ValueError("State and backup cannot be read: " + str(reason))


def _atomic_write(path, content):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Refusing symbolic-link destination")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".focus-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_document(path, document):
    validate_document(document)
    payload = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(payload) > MAX_BYTES:
        raise ValueError("State file is too large")
    path = Path(path)
    if path.exists():
        try:
            _read_one(path)
        except (OSError, ValueError, UnicodeError, RecursionError):
            pass  # Keep the last known good backup instead of copying corruption.
        else:
            _atomic_write(path.with_name(path.name + ".bak"), path.read_bytes())
    _atomic_write(path, payload)


def add_task(document, title):
    if len(document["tasks"]) >= MAX_TASKS:
        raise ValueError("Maximum of 200 tasks reached")
    task = new_task(title)
    document["tasks"].append(task)
    return task["id"]


def find_task(document, ident):
    for index, task in enumerate(document["tasks"]):
        if task["id"] == ident:
            return index
    raise ValueError("Select a task first")


def rename_task(document, ident, title):
    document["tasks"][find_task(document, ident)]["title"] = validate_title(title)


def toggle_task(document, ident):
    task = document["tasks"][find_task(document, ident)]
    task["done"] = not task["done"]


def delete_task(document, ident):
    document["tasks"].pop(find_task(document, ident))


def move_task(document, ident, delta):
    index = find_task(document, ident)
    target = index + delta
    if not 0 <= target < len(document["tasks"]):
        return False
    document["tasks"][index], document["tasks"][target] = document["tasks"][target], document["tasks"][index]
    return True


class FocusTimer:
    """Monotonic, pause-safe timer; never counts elapsed time while app is closed."""
    def __init__(self, minutes=25, clock=None):
        self.clock = clock or time.monotonic
        self.minutes = validate_minutes(minutes)
        self.state = "idle"
        self.remaining = float(minutes * 60)
        self.started_at = None

    def set_minutes(self, minutes):
        if self.state in ("running", "paused"):
            raise ValueError("Stop the current session before changing duration")
        self.minutes = validate_minutes(minutes)
        self.reset()

    def start(self):
        if self.state != "idle":
            raise ValueError("Session already started")
        self.remaining = float(self.minutes * 60)
        self.started_at = self.clock()
        self.state = "running"

    def tick(self):
        if self.state == "running":
            now = self.clock()
            elapsed = max(0.0, now - self.started_at)
            self.remaining = max(0.0, self.remaining - elapsed)
            self.started_at = now
            if self.remaining <= 0:
                self.state = "finished"
                self.started_at = None
        return self.remaining

    def pause(self):
        if self.state != "running":
            raise ValueError("Only running sessions can be paused")
        self.tick()
        if self.state == "running":
            self.state = "paused"
            self.started_at = None

    def resume(self):
        if self.state != "paused":
            raise ValueError("Only paused sessions can resume")
        self.started_at = self.clock()
        self.state = "running"

    def reset(self):
        self.state = "idle"
        self.remaining = float(self.minutes * 60)
        self.started_at = None

    def display(self):
        remaining = int(self.tick() + 0.999)
        return f"{remaining // 60:02d}:{remaining % 60:02d}"


WORDS = {
    "ja": {
        "name": "集中セッション", "subtitle": "オフライン集中タイマーとタスク一覧",
        "tasks": "タスク", "new": "追加", "edit": "編集", "done": "完了切替",
        "remove": "削除", "up": "上へ", "down": "下へ", "minutes": "集中時間（分）",
        "start": "開始", "pause": "一時停止", "resume": "再開", "reset": "リセット",
        "language": "English", "empty": "まずタスクを追加しましょう。", "prompt": "タスク名",
        "saved": "自動保存済み", "error": "操作できませんでした", "confirm": "選択したタスクを削除しますか？",
        "exit": "実行中の集中時間を中断して終了しますか？", "interrupted": "前回の集中時間は中断されました。再開ではなく新規開始してください。",
        "recovered": "バックアップから復旧しました。現在の内容を確認してください。",
        "finish": "集中時間が終了しました。お疲れさまでした！",
        "running": "実行中", "paused": "一時停止中", "idle": "準備完了", "finished": "完了",
        "duration": "時間を変更", "cancel": "キャンセル", "ok": "OK",
        "preset_25": "25分で開始", "preset_50": "50分で開始",
        "history": "履歴", "today_summary": "今日: {count}回 / {minutes}分",
        "history_empty": "完了したセッションはまだありません。",
        "history_line": "{day} · {minutes}分",
        "completion_unsaved": "完了履歴を保存できません。自動再試行中"
    },
    "en": {
        "name": "Focus Session Desk", "subtitle": "Offline focus timer and task checklist",
        "tasks": "Tasks", "new": "Add", "edit": "Edit", "done": "Toggle done",
        "remove": "Delete", "up": "Move up", "down": "Move down", "minutes": "Focus minutes",
        "start": "Start", "pause": "Pause", "resume": "Resume", "reset": "Reset",
        "language": "日本語", "empty": "Add your first task to get started.", "prompt": "Task name",
        "saved": "Saved locally", "error": "Action failed", "confirm": "Delete the selected task?",
        "exit": "Interrupt the active session and exit?", "interrupted": "Your last session was interrupted. Start a new session to continue.",
        "recovered": "Recovered from backup. Review the restored data.",
        "finish": "Focus session finished. Nice work!",
        "running": "Running", "paused": "Paused", "idle": "Ready", "finished": "Finished",
        "duration": "Apply duration", "cancel": "Cancel", "ok": "OK",
        "preset_25": "Start 25 min", "preset_50": "Start 50 min",
        "history": "History", "today_summary": "Today: {count} sessions / {minutes} min",
        "history_empty": "No completed sessions yet.",
        "history_line": "{day} · {minutes} min",
        "completion_unsaved": "Session history not saved. Retrying"
    }
}


def default_path():
    root = Path(os.environ.get("APPDATA") or Path.home() / ".local" / "share")
    return root / "FocusSessionDesk" / "state.json"


def initial_window_geometry(screen_width, screen_height):
    """Leave room for titlebar and taskbar on a 1024x768 Windows desktop."""
    if (type(screen_width) is not int or type(screen_height) is not int
            or screen_width < 830 or screen_height < 650):
        raise ValueError("Display too small for the Focus Session Desk window")
    width = min(940, screen_width - 40)
    height = min(620, screen_height - 100)
    left = max(0, (screen_width - width) // 2)
    return f"{width}x{height}+{left}+20"


class Desk:
    def __init__(self, root, path=None):
        self.root = root
        self.path = Path(path) if path else default_path()
        self.data, recovered = load_document(self.path)
        interrupted = self.data["session"] == "interrupted"
        self.timer = FocusTimer(self.data["minutes"])
        self._completion_pending = False
        self._completion_retry_after = 0.0
        self._completion_error_shown = False
        self.data["session"] = "idle"
        self.lang = self.data["language"]
        root.geometry(initial_window_geometry(root.winfo_screenwidth(), root.winfo_screenheight()))
        root.minsize(790, 550)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.build()
        self.refresh()
        if recovered:
            root.after(200, lambda: messagebox.showwarning(self.words("name"), self.words("recovered")))
        if interrupted:
            root.after(350, lambda: messagebox.showinfo(self.words("name"), self.words("interrupted")))
        self.save()
        self.tick()

    def words(self, key):
        return WORDS[self.lang][key]

    def build(self):
        self.root.title(self.words("name"))
        self.frame = ttk.Frame(self.root, padding=16)
        self.frame.pack(fill="both", expand=True)
        self.heading = ttk.Label(self.frame, text=self.words("name"), font=("Segoe UI", 19, "bold"))
        self.heading.pack(anchor="w")
        self.sub = ttk.Label(self.frame, text=self.words("subtitle"))
        self.sub.pack(anchor="w", pady=(0, 14))
        self.timer_area = ttk.LabelFrame(self.frame, text=self.words("minutes"), padding=12)
        self.timer_area.pack(fill="x", pady=(0, 14))
        self.clock_label = ttk.Label(self.timer_area, font=("Consolas", 33, "bold"))
        self.clock_label.pack(anchor="center")
        self.timer_state = ttk.Label(self.timer_area)
        self.timer_state.pack(anchor="center")
        bar = ttk.Frame(self.timer_area)
        bar.pack(pady=(10, 0))
        self.minutes_var = tk.StringVar(value=str(self.timer.minutes))
        self.minutes_entry = ttk.Entry(bar, textvariable=self.minutes_var, width=6)
        self.minutes_entry.pack(side="left", padx=4)
        self.duration_button = ttk.Button(bar, command=self.apply_minutes)
        self.duration_button.pack(side="left", padx=4)
        self.start_button = ttk.Button(bar, command=self.start)
        self.start_button.pack(side="left", padx=4)
        self.pause_button = ttk.Button(bar, command=self.pause_resume)
        self.pause_button.pack(side="left", padx=4)
        self.reset_button = ttk.Button(bar, command=self.reset)
        self.reset_button.pack(side="left", padx=4)
        self.preset_buttons = {}
        for preset in FOCUS_PRESETS:
            button = ttk.Button(bar, command=lambda value=preset: self.start_preset(value))
            button.pack(side="left", padx=4)
            self.preset_buttons[preset] = button
        self.tasks_frame = ttk.LabelFrame(self.frame, text=self.words("tasks"), padding=10)
        self.tasks_frame.pack(fill="both", expand=True)
        self.empty = ttk.Label(self.tasks_frame)
        self.empty.pack(anchor="w")
        self.tree = ttk.Treeview(self.tasks_frame, columns=("done", "title"), show="headings", selectmode="browse", height=8)
        self.tree.heading("done", text="✓")
        self.tree.heading("title", text=self.words("tasks"))
        self.tree.column("done", width=55, stretch=False, anchor="center")
        self.tree.column("title", width=500, stretch=True)
        self.tree.pack(fill="both", expand=True, pady=6)
        self.tree.bind("<Double-1>", lambda _: self.toggle())
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        actions = ttk.Frame(self.tasks_frame)
        actions.pack(fill="x")
        self.entry_var = tk.StringVar()
        self.entry = ttk.Entry(actions, textvariable=self.entry_var)
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry.bind("<Return>", lambda _: self.add())
        self.buttons = []
        for key, fn in (("new", self.add), ("edit", self.edit), ("done", self.toggle),
                        ("remove", self.remove), ("up", lambda: self.move(-1)),
                        ("down", lambda: self.move(1))):
            button = ttk.Button(actions, command=fn)
            button.pack(side="left", padx=2)
            self.buttons.append((key, button))
        footer = ttk.Frame(self.frame)
        footer.pack(fill="x", pady=(10, 0))
        self.status = ttk.Label(footer)
        self.status.pack(side="left")
        self.summary = ttk.Label(footer)
        self.summary.pack(side="left", padx=(14, 0))
        self.history_button = ttk.Button(footer, command=self.show_history)
        self.history_button.pack(side="right", padx=(6, 0))
        self.language_button = ttk.Button(footer, command=self.switch_language)
        self.language_button.pack(side="right")
        self.entry.focus_set()
        self.relabel()

    def relabel(self):
        self.root.title(self.words("name"))
        self.heading.configure(text=self.words("name"))
        self.timer_area.configure(text=self.words("minutes"))
        self.tasks_frame.configure(text=self.words("tasks"))
        self.sub.configure(text=self.words("subtitle"))
        self.duration_button.configure(text=self.words("duration"))
        self.start_button.configure(text=self.words("start"))
        self.reset_button.configure(text=self.words("reset"))
        for preset, button in self.preset_buttons.items():
            button.configure(text=self.words(f"preset_{preset}"))
        self.language_button.configure(text=self.words("language"))
        self.history_button.configure(text=self.words("history"))
        self.tree.heading("title", text=self.words("tasks"))
        for key, button in self.buttons:
            button.configure(text=self.words(key))
        self.refresh()

    def on_select(self, _event=None):
        selected = self.tree.selection()
        if selected:
            try:
                self.entry_var.set(self.data["tasks"][find_task(self.data, selected[0])]["title"])
            except ValueError:
                pass

    def selected(self):
        selected = self.tree.selection()
        if not selected:
            raise ValueError(self.words("empty"))
        return selected[0]

    def save(self):
        self.data["language"] = self.lang
        self.data["minutes"] = self.timer.minutes
        self.data["session"] = "interrupted" if self.timer.state in ("running", "paused") else "idle"
        save_document(self.path, self.data)
        self.status.configure(text=self.words("saved"))

    def refresh(self):
        previous = self.tree.selection()
        for item in self.tree.get_children():
            self.tree.delete(item)
        for task in self.data["tasks"]:
            self.tree.insert("", "end", iid=task["id"], values=("✓" if task["done"] else "", task["title"]))
        if previous and self.tree.exists(previous[0]):
            self.tree.selection_set(previous[0])
        self.empty.configure(text=self.words("empty") if not self.data["tasks"] else "")
        count, minutes = today_totals(self.data)
        self.summary.configure(text=self.words("today_summary").format(count=count, minutes=minutes))
        self.timer_state.configure(text=self.words(self.timer.state))
        self.pause_button.configure(text=self.words("resume") if self.timer.state == "paused" else self.words("pause"))
        self.clock_label.configure(text=self.timer.display())
        self.start_button.state(["disabled"] if self.timer.state != "idle" else ["!disabled"])
        for button in self.preset_buttons.values():
            button.state(["disabled"] if self.timer.state != "idle" else ["!disabled"])

    def action(self, fn):
        # Failed disk writes must not leave unsaved changes in the live model.
        import copy
        previous_data = copy.deepcopy(self.data)
        previous_timer = (self.timer.minutes, self.timer.state,
                          self.timer.remaining, self.timer.started_at)
        previous_language = self.lang
        previous_entry = self.entry_var.get()
        try:
            fn()
            self.save()
        except (OSError, ValueError, UnicodeError) as exc:
            self.data = previous_data
            (self.timer.minutes, self.timer.state,
             self.timer.remaining, self.timer.started_at) = previous_timer
            self.lang = previous_language
            self.entry_var.set(previous_entry)
            self.minutes_var.set(str(self.timer.minutes))
            self.relabel()
            messagebox.showerror(self.words("error"), str(exc))
            return False
        self.refresh()
        return True

    def add(self):
        def run():
            ident = add_task(self.data, self.entry_var.get())
            self.entry_var.set("")
            self.tree.selection_set(ident) if self.tree.exists(ident) else None
        self.action(run)

    def edit(self):
        self.action(lambda: rename_task(self.data, self.selected(), self.entry_var.get()))

    def toggle(self):
        self.action(lambda: toggle_task(self.data, self.selected()))

    def remove(self):
        try:
            ident = self.selected()
        except ValueError as exc:
            messagebox.showerror(self.words("error"), str(exc))
            return
        if messagebox.askyesno(self.words("name"), self.words("confirm")):
            self.action(lambda: delete_task(self.data, ident))

    def move(self, delta):
        self.action(lambda: move_task(self.data, self.selected(), delta))

    def apply_minutes(self):
        def run():
            value = self.minutes_var.get().strip()
            if not value.isascii() or not value.isdecimal():
                raise ValueError("Enter a whole number of minutes")
            self.timer.set_minutes(int(value))
        self.action(run)

    def start_preset(self, minutes):
        """Start a saved 25/50-minute session in one click, or leave state unchanged."""
        if minutes not in FOCUS_PRESETS:
            raise ValueError("Unsupported focus preset")

        def run():
            self.timer.set_minutes(minutes)
            self.timer.start()

        if not self.action(run):
            return False
        self.minutes_var.set(str(minutes))
        return True

    def start(self):
        self.action(self.timer.start)

    def pause_resume(self):
        self.action(self.timer.resume if self.timer.state == "paused" else self.timer.pause)

    def reset(self):
        self.action(self.timer.reset)

    def switch_language(self):
        target = "en" if self.lang == "ja" else "ja"
        if self.action(lambda: setattr(self, "lang", target)):
            self.relabel()

    def show_history(self):
        records = list(reversed(self.data.get("history", [])))
        if not records:
            messagebox.showinfo(self.words("history"), self.words("history_empty"))
            return
        lines = [self.words("history_line").format(**entry) for entry in records[:30]]
        messagebox.showinfo(self.words("history"), "\n".join(lines))

    def tick(self):
        was = self.timer.state
        self.timer.tick()
        self.clock_label.configure(text=self.timer.display())
        self.timer_state.configure(text=self.words(self.timer.state))
        if was != "finished" and self.timer.state == "finished":
            self._completion_pending = True
        if self._completion_pending and time.monotonic() >= self._completion_retry_after:
            try:
                updated = persist_completed_session(self.data, self.path, self.timer.minutes)
            except (OSError, ValueError, UnicodeError) as exc:
                self._completion_retry_after = time.monotonic() + 5.0
                self.status.configure(text=self.words("completion_unsaved"))
                if not self._completion_error_shown:
                    messagebox.showerror(self.words("error"), str(exc))
                    self._completion_error_shown = True
            else:
                self.data = updated
                self._completion_pending = False
                self._completion_error_shown = False
                self.status.configure(text=self.words("saved"))
                messagebox.showinfo(self.words("name"), self.words("finish"))
                self.refresh()
        self.root.after(250, self.tick)

    def close(self):
        if self.timer.state in ("running", "paused") and not messagebox.askyesno(self.words("name"), self.words("exit")):
            return
        if self._completion_pending:
            try:
                self.data = persist_completed_session(self.data, self.path, self.timer.minutes)
            except (OSError, ValueError, UnicodeError) as exc:
                messagebox.showerror(self.words("error"), str(exc))
                return  # Do not silently discard a finished but unsaved session.
            self._completion_pending = False
        try:
            self.save()
        except (OSError, ValueError) as exc:
            messagebox.showerror(self.words("error"), str(exc))
            return
        self.root.destroy()


if __name__ == "__main__":
    window = tk.Tk()
    try:
        Desk(window)
        window.mainloop()
    except (OSError, ValueError, UnicodeError) as exc:
        messagebox.showerror("Focus Session Desk", str(exc))
        window.destroy()
