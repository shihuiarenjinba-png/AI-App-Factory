"""File Integrity Ledger: offline, read-only SHA-256 snapshots.

No source file is modified. Snapshot/CSV destinations are explicit user choices.
"""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

MAX_FILES = 100
MAX_BYTES = 256 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024  # Bound serialized snapshots and actual file reads.
HEX64 = re.compile(r"^[0-9a-f]{64}$")
KIND = "file-integrity-ledger"

TEXT = {
    "en": {
        "title": "File Integrity Ledger", "add": "Add files", "remove": "Remove row",
        "clear": "Clear list", "save": "Save snapshot", "open": "Open snapshot",
        "verify": "Verify now", "export": "Export CSV", "lang": "Language",
        "path": "File", "size": "Bytes", "digest": "SHA-256", "result": "Result",
        "ready": "Choose local files to create a checksum snapshot. Original files are never changed.",
        "empty": "No files yet. Use Add files, then Save snapshot to keep a baseline.",
        "added": "Added {count} file(s). Save a snapshot when ready.",
        "loaded": "Snapshot loaded. Verify now to compare with disk.",
        "saved": "Snapshot saved with {count} file(s).",
        "verified": "Verified {count}: {ok} unchanged, {changed} changed, {missing} missing, {errors} errors.",
        "exported": "CSV exported.", "choose": "Select a row first.",
        "no_files": "Add or open files first.", "error": "Operation failed",
        "confirm": "Clear the list? Source files will not be deleted.",
        "warning": "Review the reported files before relying on this snapshot.",
        "recover": "Snapshot is invalid. Recover the previous valid .bak snapshot?",
        "not_checked": "NOT CHECKED", "ok": "UNCHANGED", "modified": "MODIFIED",
        "missing": "MISSING", "error_result": "ERROR",
        "language": "English", "help": "Read-only: no delete, upload, sync or background scanning.",
    },
    "ja": {
        "title": "ファイル整合性台帳", "add": "ファイル追加", "remove": "行を除外",
        "clear": "一覧クリア", "save": "記録を保存", "open": "記録を開く",
        "verify": "再検証", "export": "CSV出力", "lang": "言語",
        "path": "ファイル", "size": "バイト", "digest": "SHA-256", "result": "結果",
        "ready": "ローカルファイルを選んで検証記録を作成します。元ファイルは変更しません。",
        "empty": "ファイルがありません。「ファイル追加」後に記録を保存してください。",
        "added": "{count}件追加しました。必要なら記録を保存してください。",
        "loaded": "記録を開きました。「再検証」で現在の状態と比較できます。",
        "saved": "{count}件の記録を保存しました。",
        "verified": "{count}件検証：一致{ok}、変更{changed}、不明{missing}、エラー{errors}。",
        "exported": "CSVを出力しました。", "choose": "先に行を選択してください。",
        "no_files": "先にファイルを追加するか記録を開いてください。", "error": "操作エラー",
        "confirm": "一覧をクリアしますか？ 元ファイルは削除されません。",
        "warning": "検証結果を確認してから記録を利用してください。",
        "recover": "記録が破損しています。有効な以前の.bak記録を復元しますか？",
        "not_checked": "未検証", "ok": "一致", "modified": "変更あり",
        "missing": "見つからない", "error_result": "エラー",
        "language": "日本語", "help": "読み取り専用：削除・アップロード・同期・自動走査はしません。",
    },
}


def hash_file(path, limit=MAX_BYTES):
    """Return (size, sha256), rejecting symlinks, non-files and changing inputs."""
    file = Path(path)
    before = file.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError("Only regular non-symlink files are supported")
    if before.st_size > limit:
        raise ValueError("File exceeds 256 MiB limit")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(file, flags)
    try:
        with os.fdopen(descriptor, "rb") as reader:
            opened = os.fstat(reader.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise ValueError("File changed type during open")
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                    opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns):
                raise ValueError("File changed during open")
            digest = hashlib.sha256()
            size = 0
            while True:
                chunk = reader.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise ValueError("File exceeds 256 MiB limit")
                digest.update(chunk)
            after = os.fstat(reader.fileno())
            if (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError("File changed during hashing")
            return size, digest.hexdigest()
    except BaseException:
        raise


def make_entry(path):
    path = Path(path).absolute()
    if len(str(path)) > 2048:
        raise ValueError("File path is too long")
    size, digest = hash_file(path)
    return {"path": str(path), "size": size, "sha256": digest}


def snapshot(entries):
    data = {"schema": 1, "kind": KIND, "entries": list(entries)}
    validate_snapshot(data)
    return data


def validate_snapshot(data):
    if not isinstance(data, dict) or set(data) != {"schema", "kind", "entries"}:
        raise ValueError("Invalid snapshot schema")
    if type(data["schema"]) is not int or data["schema"] != 1 or data["kind"] != KIND:
        raise ValueError("Wrong snapshot version or kind")
    entries = data["entries"]
    if not isinstance(entries, list) or not 0 <= len(entries) <= MAX_FILES:
        raise ValueError("Too many snapshot entries")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "size", "sha256"}:
            raise ValueError("Invalid snapshot entry")
        path, size, digest = entry["path"], entry["size"], entry["sha256"]
        if (not isinstance(path, str) or not 1 <= len(path) <= 2048
                or "\x00" in path or not os.path.isabs(path)):
            raise ValueError("Snapshot paths must be absolute")
        if type(size) is not int or not 0 <= size <= MAX_BYTES:
            raise ValueError("Invalid file size")
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise ValueError("Invalid SHA-256")
        key = os.path.normcase(os.path.normpath(path))
        if key in seen:
            raise ValueError("Duplicate file path")
        seen.add(key)
    return data


def _atomic_write(path, content):
    path = Path(path)
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("Linked snapshot/output path is prohibited")
    if not path.parent.is_dir():
        raise FileNotFoundError("Destination folder does not exist")
    fd, temp = tempfile.mkstemp(prefix=".integrity-ledger-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as writer:
            writer.write(content)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _snapshot_payload(data):
    """Serialize once and reject oversized content before changing the destination."""
    validate_snapshot(data)
    payload = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise ValueError("Snapshot exceeds 2 MiB limit")
    return payload


def load_snapshot(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Linked snapshot path is prohibited")
    # Bound bytes actually read, rather than trusting a size check followed by read_text.
    with path.open("rb") as reader:
        payload = reader.read(MAX_SNAPSHOT_BYTES + 1)
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise ValueError("Snapshot exceeds 2 MiB limit")
    return validate_snapshot(json.loads(payload.decode("utf-8")))


def save_snapshot(path, data):
    payload = _snapshot_payload(data)
    path = Path(path)
    if path.exists():
        try:
            previous = load_snapshot(path)
        except (ValueError, OSError, json.JSONDecodeError, UnicodeError):
            previous = None
        if previous is not None:
            backup = Path(str(path) + ".bak")
            _atomic_write(backup, _snapshot_payload(previous))
    _atomic_write(path, payload)


def recover_snapshot(path):
    return load_snapshot(str(path) + ".bak")


def verify_snapshot(data):
    validate_snapshot(data)
    results = []
    for entry in data["entries"]:
        try:
            size, digest = hash_file(entry["path"])
            status = "UNCHANGED" if (size == entry["size"] and digest == entry["sha256"]) else "MODIFIED"
        except FileNotFoundError:
            status = "MISSING"
        except (OSError, ValueError):
            status = "ERROR"
        results.append({"path": entry["path"], "size": entry["size"],
                        "sha256": entry["sha256"], "status": status})
    return results


def csv_safe(value):
    value = str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_csv(path, data, results=None):
    validate_snapshot(data)
    statuses = {row["path"]: row["status"] for row in (results or [])}
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("path", "bytes", "sha256", "status"))
    for entry in data["entries"]:
        writer.writerow((csv_safe(entry["path"]), entry["size"],
                         entry["sha256"], csv_safe(statuses.get(entry["path"], "NOT CHECKED"))))
    _atomic_write(path, ("\ufeff" + buffer.getvalue()).encode("utf-8"))


class LedgerApp:
    def __init__(self, root):
        self.root = root
        self.language = "en"
        self.entries = []
        self.results = []
        self.status = tk.StringVar()
        self.root.geometry("980x690")
        self.root.minsize(850, 620)
        self.frame = ttk.Frame(root, padding=12)
        self.frame.pack(fill="both", expand=True)
        self.heading = ttk.Label(self.frame, font=("Segoe UI", 17, "bold"))
        self.heading.pack(anchor="w", pady=(0, 4))
        self.intro = ttk.Label(self.frame, wraplength=850)
        self.intro.pack(anchor="w", pady=(0, 10))
        self.toolbar = ttk.Frame(self.frame)
        self.toolbar.pack(fill="x", pady=(0, 8))
        self.actions = [
            ("add", self.add_files), ("remove", self.remove_row), ("clear", self.clear),
            ("save", self.save), ("open", self.open), ("verify", self.verify),
            ("export", self.export),
        ]
        self.buttons = {}
        for key, action in self.actions:
            button = ttk.Button(self.toolbar, command=action)
            button.pack(side="left", padx=(0, 5))
            self.buttons[key] = button
        self.language_button = ttk.Button(self.frame, command=self.toggle_language)
        self.language_button.pack(anchor="e", pady=(0, 5))
        table_frame = ttk.Frame(self.frame)
        table_frame.pack(fill="both", expand=True)
        self.table = ttk.Treeview(table_frame, columns=("path", "size", "digest", "result"),
                                  show="headings", selectmode="browse")
        for key, width in (("path", 400), ("size", 85), ("digest", 260), ("result", 125)):
            self.table.column(key, width=width, minwidth=60, stretch=(key == "path"))
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        ttk.Label(self.frame, textvariable=self.status, wraplength=900).pack(
            fill="x", pady=(10, 3))
        self.footer = ttk.Label(self.frame)
        self.footer.pack(anchor="w")
        self.root.bind("<Control-o>", lambda event: self.open())
        self.root.bind("<Control-s>", lambda event: self.save())
        self.root.bind("<Control-r>", lambda event: self.verify())
        self.localize()
        self.status.set(TEXT[self.language]["empty"])

    def t(self, key):
        return TEXT[self.language][key]

    def localize(self):
        self.root.title(self.t("title"))
        self.heading.configure(text=self.t("title"))
        self.intro.configure(text=self.t("ready"))
        self.footer.configure(text=self.t("help"))
        self.language_button.configure(text=self.t("language"))
        for key, button in self.buttons.items():
            button.configure(text=self.t(key))
        for key in ("path", "size", "digest", "result"):
            self.table.heading(key, text=self.t(key))
        self.refresh()

    def toggle_language(self):
        self.language = "ja" if self.language == "en" else "en"
        self.localize()

    def refresh(self):
        self.table.delete(*self.table.get_children())
        status_map = {row["path"]: row["status"] for row in self.results}
        mapping = {"NOT CHECKED": "not_checked", "UNCHANGED": "ok",
                   "MODIFIED": "modified", "MISSING": "missing", "ERROR": "error_result"}
        for i, entry in enumerate(self.entries):
            raw = status_map.get(entry["path"], "NOT CHECKED")
            self.table.insert("", "end", iid=str(i),
                              values=(entry["path"], entry["size"],
                                      entry["sha256"][:16] + "...", self.t(mapping[raw])))

    def error(self, exc):
        messagebox.showerror(self.t("error"), str(exc), parent=self.root)

    def add_files(self):
        paths = filedialog.askopenfilenames(parent=self.root, title=self.t("add"))
        if not paths:
            return
        try:
            existing = {os.path.normcase(row["path"]) for row in self.entries}
            added = 0
            for path in paths:
                if os.path.normcase(str(Path(path).absolute())) in existing:
                    continue
                if len(self.entries) >= MAX_FILES:
                    raise ValueError("Maximum 100 files")
                entry = make_entry(path)
                self.entries.append(entry)
                existing.add(os.path.normcase(entry["path"]))
                added += 1
            self.results = []
            self.refresh()
            self.status.set(self.t("added").format(count=added))
        except (OSError, ValueError) as exc:
            self.refresh()
            self.error(exc)

    def remove_row(self):
        selected = self.table.selection()
        if not selected:
            self.status.set(self.t("choose"))
            return
        self.entries.pop(int(selected[0]))
        self.results = []
        self.refresh()
        self.status.set(self.t("empty") if not self.entries else self.t("ready"))

    def clear(self):
        if self.entries and messagebox.askyesno(self.t("clear"), self.t("confirm"), parent=self.root):
            self.entries, self.results = [], []
            self.refresh()
            self.status.set(self.t("empty"))

    def save(self):
        if not self.entries:
            self.status.set(self.t("no_files"))
            return
        path = filedialog.asksaveasfilename(parent=self.root, title=self.t("save"),
                                            defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            save_snapshot(path, snapshot(self.entries))
            self.status.set(self.t("saved").format(count=len(self.entries)))
        except (OSError, ValueError) as exc:
            self.error(exc)

    def open(self):
        path = filedialog.askopenfilename(parent=self.root, title=self.t("open"),
                                          filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            data = load_snapshot(path)
        except (OSError, ValueError, json.JSONDecodeError, UnicodeError) as exc:
            if not messagebox.askyesno(self.t("error"), self.t("recover"), parent=self.root):
                self.error(exc)
                return
            try:
                data = recover_snapshot(path)
            except (OSError, ValueError, json.JSONDecodeError, UnicodeError) as recovery_error:
                self.error(recovery_error)
                return
        self.entries = data["entries"]
        self.results = []
        self.refresh()
        self.status.set(self.t("loaded"))

    def verify(self):
        if not self.entries:
            self.status.set(self.t("no_files"))
            return
        try:
            self.results = verify_snapshot(snapshot(self.entries))
            counts = {s: sum(r["status"] == s for r in self.results)
                      for s in ("UNCHANGED", "MODIFIED", "MISSING", "ERROR")}
            self.refresh()
            self.status.set(self.t("verified").format(
                count=len(self.results), ok=counts["UNCHANGED"], changed=counts["MODIFIED"],
                missing=counts["MISSING"], errors=counts["ERROR"]))
            if any(counts[s] for s in ("MODIFIED", "MISSING", "ERROR")):
                messagebox.showwarning(self.t("verify"), self.t("warning"), parent=self.root)
        except (OSError, ValueError) as exc:
            self.error(exc)

    def export(self):
        if not self.entries:
            self.status.set(self.t("no_files"))
            return
        path = filedialog.asksaveasfilename(parent=self.root, title=self.t("export"),
                                            defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            export_csv(path, snapshot(self.entries), self.results)
            self.status.set(self.t("exported"))
        except (OSError, ValueError) as exc:
            self.error(exc)


def main():
    root = tk.Tk()
    LedgerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
