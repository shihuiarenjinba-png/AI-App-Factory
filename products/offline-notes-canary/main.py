"""Offline Notes Canary: local-only Tkinter scratchpad."""
import json
import os
import re
import tempfile
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

def new_note():
    return {"id": uuid.uuid4().hex, "title": "", "body": ""}

def validate_notes(notes):
    if not isinstance(notes, list) or len(notes) > 1000:
        raise ValueError("Invalid note list")
    ids = set()
    for n in notes:
        if not isinstance(n, dict) or set(n) != {"id", "title", "body"}:
            raise ValueError("Invalid note structure")
        if not isinstance(n["id"], str) or not re.fullmatch("[0-9a-f]{32}", n["id"]) or n["id"] in ids:
            raise ValueError("Duplicate or invalid note ID")
        ids.add(n["id"])
        if not isinstance(n["title"], str) or not isinstance(n["body"], str) or len(n["title"]) > 300 or len(n["body"]) > 300000:
            raise ValueError("Invalid or oversized note text")
        # JSON permits escaped lone surrogates, but UTF-8 saving and Tkinter do not.
        # Reject them while loading so a corrupt file can fall back to its backup.
        for field in ("title", "body"):
            if any(0xD800 <= ord(char) <= 0xDFFF for char in n[field]):
                raise ValueError("Invalid Unicode surrogate in note text")
    return notes

def atomic_write(path, data):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Cannot overwrite a symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".notes-", delete=False) as f:
            temp = Path(f.name)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)

def reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result

def read_notes(path):
    path = Path(path)
    reason = None
    for candidate in (path, path.with_name(path.name + ".bak")):
        try:
            if candidate.stat().st_size > 5000000:
                raise ValueError("File exceeds 5 MB")
            value = json.loads(candidate.read_text(encoding="utf-8"),
                               object_pairs_hook=reject_duplicate_json_keys)
            if not isinstance(value, dict) or type(value.get("schema")) is not int or value["schema"] != 1:
                raise ValueError("Unsupported notes schema")
            return [dict(n) for n in validate_notes(value.get("notes"))], candidate != path
        except (OSError, ValueError, UnicodeError, RecursionError) as exc:
            if reason is None:
                reason = exc
    raise ValueError("Cannot read notes or backup: " + str(reason))

def save_notes(path, notes):
    validate_notes(notes)
    payload = (json.dumps({"schema": 1, "notes": notes}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(payload) > 5000000:
        raise ValueError("Notes exceed 5 MB")
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Cannot save through a symbolic link")
    if path.exists():
        try:
            _, recovered = read_notes(path)
        except (OSError, ValueError) as exc:
            raise ValueError(
                "Existing file is not a valid notes database; choose another filename"
            ) from exc
        if recovered:
            raise ValueError(
                "Primary notes file is damaged; save recovered notes to a new filename"
            )
        backup = path.with_name(path.name + ".bak")
        if backup.is_symlink():
            raise ValueError("Cannot overwrite a symbolic-link backup")
        if backup.exists():
            try:
                _, backup_recovered = read_notes(backup)
            except (OSError, ValueError) as exc:
                raise ValueError(
                    "Existing backup is not a valid notes database; choose another filename"
                ) from exc
            if backup_recovered:
                raise ValueError("Existing backup is damaged; choose another filename")
        # Backup failure is fatal; never replace the primary in that case.
        atomic_write(backup, path.read_bytes())
    atomic_write(path, payload)

def search_notes(notes, term):
    q = term.strip().casefold()
    return [n for n in notes if q in (n["title"] + "\n" + n["body"]).casefold()]

def safe_filename(title):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")[:80]
    if name.split(".", 1)[0].rstrip(" ").upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in (*range(1, 10), "¹", "²", "³")), *(f"LPT{i}" for i in (*range(1, 10), "¹", "²", "³"))}:
        name = "note_" + name
    return (name or "untitled") + ".txt"

STRINGS = {
    "ja": ["オフラインメモ", "新規", "開く", "保存", "TXT書出", "削除", "English", "メモを検索", "タイトル", "「新規」からメモを作成してください。", "未保存の変更", "保存済み", "このメモを削除しますか？", "変更を保存しますか？", "操作に失敗しました", "バックアップから復元。別名保存してください。", "TXT書き出し完了", "既存ファイルを上書きしますか？", "入力内容とファイルの保存先を確認し、もう一度お試しください。", "バックアップから復元"],
    "en": ["Offline Notes", "New", "Open", "Save", "Export TXT", "Delete", "日本語", "Search notes", "Title", "Create your first note with New.", "Unsaved changes", "Saved", "Delete this note?", "Save changes?", "Action failed", "Recovered from backup. Save to a new file.", "TXT exported", "Overwrite existing file?", "Check your input and file location, then try again.", "Restore backup"]
}

class App:
    def __init__(self, root):
        self.root, self.lang = root, "ja"
        self.notes, self.current, self.path = [], None, None
        self.dirty, self.loading = False, False
        root.geometry("940x640")
        root.minsize(780, 520)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        self.title, self.query, self.status = tk.StringVar(), tk.StringVar(), tk.StringVar()
        bar = ttk.Frame(root, padding=8)
        bar.grid(row=0, column=0, sticky="ew")
        self.buttons = []
        for i, fn in enumerate((self.new, self.open_file, self.save, self.export, self.delete, self.language, self.restore_backup)):
            b = ttk.Button(bar, command=fn)
            b.grid(row=0, column=i, padx=3)
            self.buttons.append(b)
        pane = ttk.Panedwindow(root, orient="horizontal")
        pane.grid(row=1, column=0, sticky="nsew", padx=8)
        left = ttk.Frame(pane, padding=4)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)
        self.search_label = ttk.Label(left)
        self.search_label.grid(row=0, column=0, sticky="w")
        self.search_entry = ttk.Entry(left, textvariable=self.query)
        self.search_entry.grid(row=1, column=0, sticky="ew")
        self.listbox = tk.Listbox(left, exportselection=False)
        self.listbox.grid(row=2, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", self.select)
        pane.add(left, weight=1)
        right = ttk.Frame(pane, padding=4)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        self.title_label = ttk.Label(right)
        self.title_label.grid(row=0, column=0, sticky="w")
        self.title_entry = ttk.Entry(right, textvariable=self.title)
        self.title_entry.grid(row=1, column=0, sticky="ew")
        self.body = tk.Text(right, wrap="word", undo=True)
        self.body.grid(row=2, column=0, sticky="nsew")
        self.body.bind("<<Modified>>", self.body_changed)
        pane.add(right, weight=3)
        ttk.Label(root, textvariable=self.status, padding=8).grid(row=2, column=0, sticky="ew")
        self.visible = []
        self.query.trace_add("write", lambda *_: self.refresh_list())
        self.title.trace_add("write", lambda *_: self.changed())
        root.bind("<Control-n>", lambda _: self.new())
        root.bind("<Control-s>", lambda _: self.save())
        root.bind("<Control-o>", lambda _: self.open_file())
        root.bind("<Control-f>", lambda _: self.search_entry.focus_set())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.labels()
        self.show(None)

    def t(self, i):
        return STRINGS[self.lang][i]

    def labels(self):
        self.root.title(self.t(0))
        for i, b in enumerate(self.buttons):
            b.configure(text=self.t(i + 1 if i < 6 else 19))
        self.search_label.configure(text=self.t(7))
        self.title_label.configure(text=self.t(8))
        if self.current is None:
            self.show(None)
        self.status.set(self.t(10) if self.dirty else self.t(9) if not self.notes else self.t(11))

    def language(self):
        self.lang = "en" if self.lang == "ja" else "ja"
        self.labels()

    def changed(self):
        if self.current and not self.loading:
            self.dirty = True
            self.status.set(self.t(10))
            if self.query.get():
                self.refresh_list()

    def body_changed(self, _event=None):
        if self.body.edit_modified():
            self.body.edit_modified(False)
            self.changed()

    def commit_editor(self):
        n = next((n for n in self.notes if n["id"] == self.current), None)
        if n:
            title, body = self.title.get(), self.body.get("1.0", "end-1c")
            if len(title) > 300 or len(body) > 300000:
                raise ValueError("Note is too long")
            if (n["title"], n["body"]) != (title, body):
                n["title"], n["body"] = title, body
                self.dirty = True

    def refresh_list(self):
        # Search the visible, unsaved editor text without mutating the saved model.
        # The editor is committed only on Save or when switching notes.
        notes = self.notes
        if self.current and not self.loading:
            title, body = self.title.get(), self.body.get("1.0", "end-1c")
            notes = [{**n, "title": title, "body": body} if n["id"] == self.current else n
                     for n in self.notes]
        filtered = search_notes(notes, self.query.get())
        self.visible = [n["id"] for n in filtered]
        self.listbox.delete(0, "end")
        for n in filtered:
            self.listbox.insert("end", n["title"] or "(untitled)")
        if self.current in self.visible:
            self.listbox.selection_set(self.visible.index(self.current))

    def show(self, note_id):
        self.current = note_id
        n = next((n for n in self.notes if n["id"] == note_id), None)
        self.loading = True
        self.title_entry.configure(state="normal" if n else "disabled")
        self.title.set(n["title"] if n else "")
        self.body.configure(state="normal")
        self.body.delete("1.0", "end")
        self.body.insert("1.0", n["body"] if n else self.t(9))
        if n is None:
            self.body.configure(state="disabled")
        self.body.edit_modified(False)
        self.loading = False
        self.refresh_list()

    def select(self, _event=None):
        sel = self.listbox.curselection()
        if sel:
            next_id = self.visible[sel[0]]
            if next_id != self.current:
                try:
                    self.commit_editor()
                    self.show(next_id)
                except (OSError, ValueError) as exc:
                    self.error(exc)

    def new(self):
        try:
            self.commit_editor()
            n = new_note()
            self.notes.append(n)
            self.query.set("")
            self.show(n["id"])
            self.dirty = True
            self.status.set(self.t(10))
            self.title_entry.focus_set()
        except (OSError, ValueError) as exc:
            self.error(exc)

    def delete(self):
        if self.current and messagebox.askyesno(self.t(0), self.t(12)):
            self.notes = [n for n in self.notes if n["id"] != self.current]
            self.show(self.notes[0]["id"] if self.notes else None)
            self.dirty = True
            self.status.set(self.t(10))

    def save(self):
        try:
            self.commit_editor()
            path = self.path
            if path is None:
                selected = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
                if not selected:
                    return False
                path = Path(selected)
            save_notes(path, self.notes)
            self.path, self.dirty = path, False
            self.status.set(self.t(11) + " — " + str(path))
            self.refresh_list()
            return True
        except (OSError, ValueError) as exc:
            self.error(exc)
            return False

    def confirm(self):
        self.commit_editor()
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(self.t(0), self.t(13))
        return False if answer is None else self.save() if answer else True

    def open_file(self):
        try:
            if not self.confirm():
                return
            selected = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
            if not selected:
                return
            notes, recovered = read_notes(Path(selected))
            self.notes, self.path, self.dirty = notes, None if recovered else Path(selected), recovered
            self.query.set("")
            self.show(notes[0]["id"] if notes else None)
            self.status.set(self.t(15) if recovered else self.t(11))
        except (OSError, ValueError) as exc:
            self.error(exc)

    def restore_backup(self):
        """Explicit, non-destructive restore to a NEW JSON file."""
        try:
            if not self.confirm():
                return
            selected = filedialog.askopenfilename(
                filetypes=[("Notes backup", "*.bak"), ("All files", "*.*")])
            if not selected:
                return
            backup = Path(selected)
            if not backup.name.lower().endswith(".bak") or backup.is_symlink():
                raise ValueError("Choose a regular .bak notes backup")
            recovered_notes, used_fallback = read_notes(backup)
            if used_fallback:
                raise ValueError("Selected backup is damaged")
            output = filedialog.asksaveasfilename(
                initialfile="restored-notes.json", defaultextension=".json",
                filetypes=[("JSON", "*.json")])
            if not output:
                return
            destination = Path(output)
            # Never overwrite an existing file during recovery, even if valid.
            if destination.exists() or destination.is_symlink():
                raise ValueError("Restore requires a new, unused filename")
            save_notes(destination, recovered_notes)
            self.notes, self.path, self.dirty = recovered_notes, destination, False
            self.query.set("")
            self.show(recovered_notes[0]["id"] if recovered_notes else None)
            self.status.set(self.t(11) + " — " + str(destination))
        except (OSError, ValueError) as exc:
            self.error(exc)

    def export(self):
        try:
            self.commit_editor()
            n = next((n for n in self.notes if n["id"] == self.current), None)
            if n is None:
                messagebox.showinfo(self.t(0), self.t(9))
                return
            selected = filedialog.asksaveasfilename(initialfile=safe_filename(n["title"]), defaultextension=".txt", filetypes=[("Text", "*.txt")])
            if not selected:
                return
            path = Path(selected)
            if getattr(self, "path", None) is not None:
                active = Path(self.path).absolute()
                protected = (active, active.with_name(active.name + ".bak"))
                output = path.absolute()
                if any(output == item or (
                    path.exists() and item.exists() and os.path.samefile(path, item)
                ) for item in protected):
                    raise ValueError("TXT export cannot overwrite the notes database or backup")
            if path.exists() and not messagebox.askyesno(self.t(0), self.t(17)):
                return
            atomic_write(path, (n["title"] + "\n\n" + n["body"] + "\n").encode("utf-8"))
            self.status.set(self.t(16) + " — " + str(path))
        except (OSError, ValueError) as exc:
            self.error(exc)

    def error(self, exc):
        messagebox.showerror(self.t(14), self.t(18) + "\n\n" + str(exc))
        self.status.set(self.t(14) + " — " + self.t(18))

    def close(self):
        try:
            if self.confirm():
                self.root.destroy()
        except (OSError, ValueError) as exc:
            self.error(exc)

if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
