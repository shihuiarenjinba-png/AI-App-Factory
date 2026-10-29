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

def normalize_tags(text):
    """Parse user-entered tags without silently truncating or merging labels."""
    if not isinstance(text, str):
        raise ValueError("Tags must be text")
    tags = [part.strip() for part in re.split(r"[,、]", text) if part.strip()]
    if len(tags) > 8 or any(len(tag) > 30 for tag in tags):
        raise ValueError("Use at most 8 tags, up to 30 characters each")
    if len({tag.casefold() for tag in tags}) != len(tags):
        raise ValueError("Duplicate tags are not allowed")
    if any(0xD800 <= ord(ch) <= 0xDFFF for tag in tags for ch in tag):
        raise ValueError("Invalid Unicode surrogate in tag")
    return tags

def validate_notes(notes):
    if not isinstance(notes, list) or len(notes) > 1000:
        raise ValueError("Invalid note list")
    ids = set()
    for n in notes:
        if not isinstance(n, dict) or not {"id", "title", "body"}.issubset(n) or set(n) - {"id", "title", "body", "tags", "favorite"}:
            raise ValueError("Invalid note structure")
        if not isinstance(n["id"], str) or not re.fullmatch("[0-9a-f]{32}", n["id"]) or n["id"] in ids:
            raise ValueError("Duplicate or invalid note ID")
        ids.add(n["id"])
        if not isinstance(n["title"], str) or not isinstance(n["body"], str) or len(n["title"]) > 300 or len(n["body"]) > 300000:
            raise ValueError("Invalid or oversized note text")
        if "favorite" in n and type(n["favorite"]) is not bool:
            raise ValueError("Favorite must be true or false")
        if "tags" in n:
            tags = n["tags"]
            if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
                raise ValueError("Invalid tags")
            if normalize_tags(",".join(tags)) != tags:
                raise ValueError("Invalid or noncanonical tags")
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
            if not isinstance(value, dict) or type(value.get("schema")) is not int or value["schema"] not in (1, 2):
                raise ValueError("Unsupported notes schema")
            notes = validate_notes(value.get("notes"))
            if value["schema"] == 1 and any("tags" in n or "favorite" in n for n in notes):
                raise ValueError("Schema 1 cannot contain note metadata")
            return [dict(n) for n in notes], candidate != path
        except (OSError, ValueError, UnicodeError, RecursionError) as exc:
            if reason is None:
                reason = exc
    raise ValueError("Cannot read notes or backup: " + str(reason))

def notes_payload(notes):
    validate_notes(notes)
    schema = 2 if any("tags" in n or "favorite" in n for n in notes) else 1
    payload = (json.dumps({"schema": schema, "notes": notes}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(payload) > 5000000:
        raise ValueError("Notes exceed 5 MB")
    return payload

def save_notes_new(path, notes):
    """Atomically create a new notes file, never replacing a competing path."""
    payload = notes_payload(notes)
    path = Path(path)
    if not path.parent.is_dir():
        raise ValueError("Choose an existing destination folder")
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".notes-", delete=False) as f:
            temp = Path(f.name)
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        # Hard-link creation is atomic and fails if the destination exists,
        # including when another process creates it after the file dialog.
        # Unsupported filesystems fail closed rather than falling back to replace.
        os.link(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)

def save_notes(path, notes):
    payload = notes_payload(notes)
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
    return [n for n in notes if q in (n["title"] + "\n" + n["body"] + "\n" + " ".join(n.get("tags", []))).casefold()]

def find_matches(text, query, limit=200):
    """Return bounded, non-overlapping offsets for a visible search highlight."""
    if not isinstance(text, str) or not isinstance(query, str):
        raise ValueError("Search requires text")
    needle = query.strip()
    if not needle or len(needle) > 200:
        return []
    return [(match.start(), match.end()) for _, match in zip(
        range(limit), re.finditer(re.escape(needle), text, flags=re.IGNORECASE))]

def safe_filename(title):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")[:80]
    if name.split(".", 1)[0].rstrip(" ").upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in (*range(1, 10), "¹", "²", "³")), *(f"LPT{i}" for i in (*range(1, 10), "¹", "²", "³"))}:
        name = "note_" + name
    return (name or "untitled") + ".txt"

STRINGS = {
    "ja": ["オフラインメモ", "新規", "開く", "保存", "TXT書出", "削除", "English", "メモを検索", "タイトル", "「新規」からメモを作成してください。", "未保存の変更", "保存済み", "このメモを削除しますか？", "変更を保存しますか？", "操作に失敗しました", "バックアップから復元。別名保存してください。", "TXT書き出し完了", "既存ファイルを上書きしますか？", "入力内容とファイルの保存先を確認し、もう一度お試しください。", "バックアップから復元", "タグ（カンマ区切り）", "☆ お気に入り", "★ お気に入り", "お気に入りのみ", "名前を付けて保存"],
    "en": ["Offline Notes", "New", "Open", "Save", "Export TXT", "Delete", "日本語", "Search notes", "Title", "Create your first note with New.", "Unsaved changes", "Saved", "Delete this note?", "Save changes?", "Action failed", "Recovered from backup. Save to a new file.", "TXT exported", "Overwrite existing file?", "Check your input and file location, then try again.", "Restore backup", "Tags (comma-separated)", "☆ Favorite", "★ Favorited", "Favorites only", "Save As"]
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
        self.title, self.query, self.status, self.tag_text = tk.StringVar(), tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.recent_ids = []
        self.favorites_only = tk.BooleanVar(value=False)
        bar = ttk.Frame(root, padding=8)
        bar.grid(row=0, column=0, sticky="ew")
        self.buttons = []
        for i, fn in enumerate((self.new, self.open_file, self.save, self.export, self.delete, self.language, self.restore_backup)):
            b = ttk.Button(bar, command=fn)
            b.grid(row=0, column=i, padx=3)
            self.buttons.append(b)
        self.favorite_button = ttk.Button(bar, command=self.toggle_favorite)
        self.favorite_button.grid(row=0, column=7, padx=3)
        self.save_as_button = ttk.Button(bar, command=self.save_as)
        self.save_as_button.grid(row=0, column=8, padx=3)
        pane = ttk.Panedwindow(root, orient="horizontal")
        pane.grid(row=1, column=0, sticky="nsew", padx=8)
        left = ttk.Frame(pane, padding=4)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(3, weight=1)
        self.search_label = ttk.Label(left)
        self.search_label.grid(row=0, column=0, sticky="w")
        self.search_entry = ttk.Entry(left, textvariable=self.query)
        self.search_entry.grid(row=1, column=0, sticky="ew")
        self.favorites_check = ttk.Checkbutton(
            left, variable=self.favorites_only, command=self.refresh_list)
        self.favorites_check.grid(row=2, column=0, sticky="w", pady=(5, 3))
        self.listbox = tk.Listbox(left, exportselection=False)
        self.listbox.grid(row=3, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", self.select)
        pane.add(left, weight=1)
        right = ttk.Frame(pane, padding=4)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(4, weight=1)
        self.title_label = ttk.Label(right)
        self.title_label.grid(row=0, column=0, sticky="w")
        self.title_entry = ttk.Entry(right, textvariable=self.title)
        self.title_entry.grid(row=1, column=0, sticky="ew")
        self.tag_label = ttk.Label(right)
        self.tag_label.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.tag_entry = ttk.Entry(right, textvariable=self.tag_text)
        self.tag_entry.grid(row=3, column=0, sticky="ew")
        self.body = tk.Text(right, wrap="word", undo=True)
        self.body.grid(row=4, column=0, sticky="nsew")
        self.body.bind("<<Modified>>", self.body_changed)
        self.body.tag_configure("search_match", background="#ffe59a")
        pane.add(right, weight=3)
        ttk.Label(root, textvariable=self.status, padding=8).grid(row=2, column=0, sticky="ew")
        self.visible = []
        self.query.trace_add("write", lambda *_: (self.refresh_list(), self.highlight_search()))
        self.title.trace_add("write", lambda *_: self.changed())
        self.tag_text.trace_add("write", lambda *_: self.changed())
        root.bind("<Control-n>", lambda _: self.new())
        root.bind("<Control-s>", lambda _: self.save())
        root.bind("<Control-Shift-S>", lambda _: self.save_as())
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
        self.favorites_check.configure(text=self.t(23))
        self.save_as_button.configure(text=self.t(24))
        self.title_label.configure(text=self.t(8))
        self.tag_label.configure(text=self.t(20))
        self.refresh_favorite_button()
        if self.current is None:
            self.show(None)
        self.status.set(self.t(10) if self.dirty else self.t(9) if not self.notes else self.t(11))

    def refresh_favorite_button(self):
        note = next((n for n in self.notes if n["id"] == self.current), None)
        self.favorite_button.configure(
            text=self.t(22 if note and note.get("favorite", False) else 21),
            state="normal" if note else "disabled")

    def toggle_favorite(self):
        try:
            self.commit_editor()
            note = next((n for n in self.notes if n["id"] == self.current), None)
            if note is None:
                return
            if note.get("favorite", False):
                note.pop("favorite", None)
            else:
                note["favorite"] = True
            self.dirty = True
            self.status.set(self.t(10))
            self.refresh_favorite_button()
            self.refresh_list()
        except (OSError, ValueError) as exc:
            self.error(exc)

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
            self.highlight_search()

    def commit_editor(self):
        n = next((n for n in self.notes if n["id"] == self.current), None)
        if n:
            title, body = self.title.get(), self.body.get("1.0", "end-1c")
            if len(title) > 300 or len(body) > 300000:
                raise ValueError("Note is too long")
            tags = normalize_tags(self.tag_text.get())
            if n.get("tags", []) != tags:
                if tags:
                    n["tags"] = tags
                else:
                    n.pop("tags", None)
                self.dirty = True
            if (n["title"], n["body"]) != (title, body):
                n["title"], n["body"] = title, body
                self.dirty = True

    def refresh_list(self):
        # Search the visible, unsaved editor text without mutating the saved model.
        # The editor is committed only on Save or when switching notes.
        notes = self.notes
        if self.current and not self.loading:
            title, body = self.title.get(), self.body.get("1.0", "end-1c")
            # Include draft tags in search results without committing them.
            # Partial/invalid input is allowed while typing; Save validates it.
            tag_widget = getattr(self, "tag_text", None)
            draft_tags = ([part.strip() for part in re.split(r"[,、]", tag_widget.get())
                           if part.strip()] if tag_widget is not None else [])
            notes = [{**n, "title": title, "body": body, "tags": draft_tags}
                     if n["id"] == self.current else n for n in self.notes]
        filtered = search_notes(notes, self.query.get())
        only_favorites = getattr(self, "favorites_only", None)
        if only_favorites is not None and only_favorites.get():
            filtered = [n for n in filtered if n.get("favorite", False)]
        recent = getattr(self, "recent_ids", [])
        filtered.sort(key=lambda n: (
            not n.get("favorite", False),
            recent.index(n["id"]) if n["id"] in recent else len(recent)))
        self.visible = [n["id"] for n in filtered]
        self.listbox.delete(0, "end")
        for n in filtered:
            self.listbox.insert("end", ("★ " if n.get("favorite", False) else "") + (n["title"] or "(untitled)"))
        if self.current in self.visible:
            self.listbox.selection_set(self.visible.index(self.current))

    def show(self, note_id):
        self.current = note_id
        if note_id is not None:
            self.recent_ids = [note_id] + [i for i in self.recent_ids if i != note_id][:999]
        n = next((n for n in self.notes if n["id"] == note_id), None)
        self.loading = True
        self.title_entry.configure(state="normal" if n else "disabled")
        self.title.set(n["title"] if n else "")
        self.tag_entry.configure(state="normal" if n else "disabled")
        self.tag_text.set(", ".join(n.get("tags", [])) if n else "")
        self.refresh_favorite_button()
        self.body.configure(state="normal")
        self.body.delete("1.0", "end")
        self.body.insert("1.0", n["body"] if n else self.t(9))
        if n is None:
            self.body.configure(state="disabled")
        self.body.edit_modified(False)
        self.loading = False
        self.refresh_list()
        self.highlight_search()

    def highlight_search(self):
        """Highlight matches in the active note body; never modify note data."""
        self.body.tag_remove("search_match", "1.0", "end")
        if not self.current:
            return
        query = self.query.get()
        if not query.strip():
            return
        text = self.body.get("1.0", "end-1c")
        for start, end in find_matches(text, query):
            self.body.tag_add("search_match", f"1.0+{start}c", f"1.0+{end}c")

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

    def save_as(self):
        """Save a separate notes copy; never overwrite another existing file."""
        try:
            self.commit_editor()
            selected = filedialog.asksaveasfilename(
                initialfile=self.path.name if self.path else "notes.json",
                defaultextension=".json", filetypes=[("JSON", "*.json")])
            if not selected:
                return False
            destination = Path(selected)
            save_notes_new(destination, self.notes)
            self.path, self.dirty = destination, False
            self.status.set(self.t(11) + " — " + str(destination))
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
            save_notes_new(destination, recovered_notes)
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
