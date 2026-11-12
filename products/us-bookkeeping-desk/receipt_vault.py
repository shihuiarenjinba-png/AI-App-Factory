"""Local evidence attachments for existing US bookkeeping journal entries.

Receipts are stored in SQLite, not sent to a service or interpreted for tax.
Importing never posts a journal entry or changes its accounting totals.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

MAX_RECEIPT_BYTES = 15 * 1024 * 1024
MAGIC = {
    ".pdf": ("application/pdf", lambda b: b.startswith(b"%PDF-")),
    ".png": ("image/png", lambda b: b.startswith(b"\x89PNG\r\n\x1a\n")),
    ".jpg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
    ".webp": ("image/webp", lambda b: b.startswith(b"RIFF") and b[8:12] == b"WEBP"),
}


class ReceiptError(ValueError):
    pass


class ReceiptVault:
    def __init__(self, store):
        self.conn = store.conn
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS receipt_documents (
                id INTEGER PRIMARY KEY,
                sha256 TEXT NOT NULL UNIQUE,
                original_name TEXT NOT NULL,
                media_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                content BLOB NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS receipt_links (
                entry_id INTEGER NOT NULL REFERENCES entries(id),
                document_id INTEGER NOT NULL REFERENCES receipt_documents(id),
                PRIMARY KEY (entry_id, document_id)
            );
        """)
        self.conn.commit()

    def _entry(self, entry_id):
        if isinstance(entry_id, bool) or not isinstance(entry_id, int) or entry_id <= 0:
            raise ReceiptError("Choose a saved journal entry first")
        if self.conn.execute("SELECT 1 FROM entries WHERE id=?", (entry_id,)).fetchone() is None:
            raise ReceiptError("Journal entry no longer exists")

    @staticmethod
    def _read_file(path):
        file = Path(path)
        if file.is_symlink() or not file.is_file():
            raise ReceiptError("Choose a regular local file, not a link or folder")
        suffix = file.suffix.lower()
        if suffix not in MAGIC:
            raise ReceiptError("Only PDF, PNG, JPEG and WebP evidence files are supported")
        before = file.stat()
        if before.st_size == 0 or before.st_size > MAX_RECEIPT_BYTES:
            raise ReceiptError("File must be between 1 byte and 15 MB")
        # The symlink check is best effort, not an OS-level security sandbox.
        with file.open("rb") as handle:
            content = handle.read(MAX_RECEIPT_BYTES + 1)
        after = file.stat()
        if len(content) == 0 or len(content) > MAX_RECEIPT_BYTES:
            raise ReceiptError("File must be between 1 byte and 15 MB")
        if before.st_size != after.st_size or len(content) != after.st_size:
            raise ReceiptError("File changed while being read; retry")
        mime, verify = MAGIC[suffix]
        if not verify(content):
            raise ReceiptError("File content does not match its extension")
        return file.name, mime, content

    def attach_many(self, entry_id, paths):
        """Per-file transactions: a failed file never discards other imports."""
        self._entry(entry_id)
        results = []
        for path in paths:
            name = Path(path).name
            try:
                original_name, media_type, content = self._read_file(path)
                digest = hashlib.sha256(content).hexdigest()
                with self.conn:
                    self.conn.execute("""
                        INSERT OR IGNORE INTO receipt_documents
                        (sha256, original_name, media_type, size_bytes, content)
                        VALUES (?, ?, ?, ?, ?)
                    """, (digest, original_name, media_type, len(content), content))
                    doc_id = self.conn.execute(
                        "SELECT id FROM receipt_documents WHERE sha256=?", (digest,)
                    ).fetchone()[0]
                    cursor = self.conn.execute(
                        "INSERT OR IGNORE INTO receipt_links(entry_id,document_id) VALUES (?,?)",
                        (entry_id, doc_id),
                    )
                    added = cursor.rowcount == 1
                    if added:
                        self.conn.execute(
                            "INSERT INTO audit_log(action,detail) VALUES('RECEIPT_ATTACH',?)",
                            (f"entry={entry_id}|document={doc_id}|sha256={digest}",),
                        )
                results.append({"file": name, "status": "attached" if added else "duplicate",
                                "sha256": digest, "document_id": doc_id})
            except (OSError, ValueError) as exc:
                results.append({"file": name, "status": "rejected", "reason": str(exc)})
        return results

    def for_entry(self, entry_id):
        self._entry(entry_id)
        return [dict(row) for row in self.conn.execute("""
            SELECT d.id, d.original_name, d.media_type, d.size_bytes, d.sha256, d.created_at
            FROM receipt_documents d JOIN receipt_links l ON l.document_id=d.id
            WHERE l.entry_id=? ORDER BY d.id
        """, (entry_id,))]

    def save_copy(self, entry_id, document_id, target):
        """Export a verified copy, never silently overwrite an existing file."""
        self._entry(entry_id)
        row = self.conn.execute("""
            SELECT d.content, d.sha256 FROM receipt_documents d
            JOIN receipt_links l ON l.document_id=d.id
            WHERE l.entry_id=? AND d.id=?
        """, (entry_id, document_id)).fetchone()
        if row is None:
            raise ReceiptError("Receipt is not attached to the selected entry")
        content = bytes(row["content"])
        if hashlib.sha256(content).hexdigest() != row["sha256"]:
            raise ReceiptError("Saved receipt failed integrity verification")
        target = Path(target)
        with target.open("xb") as output:
            output.write(content)
        return target
