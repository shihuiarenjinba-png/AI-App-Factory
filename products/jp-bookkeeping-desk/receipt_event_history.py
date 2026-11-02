"""Opt-in, fail-closed receipt status history foundation for JP month-end reports.

Not yet wired to legacy GUI/Store.enqueue_receipts or monthly_close. Never infer
historical statuses from receipt_queue.created_at or its present status.
All event times are UTC; the requested month-end boundary is Asia/Tokyo.
"""
import calendar
import sqlite3
from datetime import date, datetime, timedelta, timezone

JST = timezone(timedelta(hours=9), "JST")
UTC = timezone.utc


def _utc(value=None):
    if value is None:
        value = datetime.now(UTC)
    elif isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("event timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


class ReceiptHistory:
    """New writes must use add/transition. Old/bypassed rows force HOLD."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.execute("""CREATE TABLE IF NOT EXISTS receipt_status_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            receipt_id INTEGER NOT NULL,
            event_kind TEXT NOT NULL CHECK(event_kind IN ('ENQUEUED','POSTED','REOPENED')),
            status TEXT NOT NULL CHECK(status IN ('PENDING','POSTED')),
            occurred_utc TEXT NOT NULL,
            path_snapshot TEXT NOT NULL
        )""")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS receipt_history_meta (
            key TEXT PRIMARY KEY, value TEXT NOT NULL
        )""")
        self.conn.execute("""CREATE TRIGGER IF NOT EXISTS receipt_events_no_update
            BEFORE UPDATE ON receipt_status_events BEGIN
                SELECT RAISE(ABORT, 'RECEIPT_EVENT_APPEND_ONLY');
            END""")
        self.conn.execute("""CREATE TRIGGER IF NOT EXISTS receipt_events_no_delete
            BEFORE DELETE ON receipt_status_events BEGIN
                SELECT RAISE(ABORT, 'RECEIPT_EVENT_APPEND_ONLY');
            END""")
        existing = self.conn.execute(
            "SELECT value FROM receipt_history_meta WHERE key='legacy_unverified'"
        ).fetchone()
        if existing is None:
            old_rows = self.conn.execute("SELECT COUNT(*) FROM receipt_queue").fetchone()[0]
            old_events = self.conn.execute("SELECT COUNT(*) FROM receipt_status_events").fetchone()[0]
            self.conn.execute(
                "INSERT INTO receipt_history_meta(key,value) VALUES('legacy_unverified',?)",
                ("1" if old_rows or old_events else "0",))
        self.conn.commit()

    def add(self, path, at=None):
        path = str(path).strip()
        if not path:
            raise ValueError("empty receipt path")
        when = _utc(at)
        with self.conn:
            found = self.conn.execute(
                "SELECT id FROM receipt_queue WHERE file_path=?", (path,)).fetchone()
            if found:
                return int(found[0]), False
            cur = self.conn.execute(
                "INSERT INTO receipt_queue(file_path,status,created_at) VALUES(?,?,?)",
                (path, "PENDING", when))
            rid = int(cur.lastrowid)
            self.conn.execute(
                "INSERT INTO receipt_status_events(receipt_id,event_kind,status,occurred_utc,path_snapshot) VALUES(?,?,?,?,?)",
                (rid, "ENQUEUED", "PENDING", when, path))
            return rid, True

    def transition(self, receipt_id, new_status, at=None):
        if new_status not in ("PENDING", "POSTED"):
            raise ValueError("unsupported receipt status")
        when = _utc(at)
        with self.conn:
            row = self.conn.execute(
                "SELECT file_path,status FROM receipt_queue WHERE id=?",
                (receipt_id,)).fetchone()
            if row is None:
                raise ValueError("receipt not found")
            path, current = row
            event = self.conn.execute(
                "SELECT status,occurred_utc,path_snapshot FROM receipt_status_events "
                "WHERE receipt_id=? ORDER BY event_id DESC LIMIT 1", (receipt_id,)).fetchone()
            if event is None or event[0] != current or event[2] != path:
                raise ValueError("RECEIPT_HISTORY_INCOMPLETE_HOLD")
            if new_status == current:
                return False
            if (current, new_status) not in (("PENDING", "POSTED"), ("POSTED", "PENDING")):
                raise ValueError("invalid status transition")
            if datetime.fromisoformat(when) <= datetime.fromisoformat(event[1]):
                raise ValueError("event timestamp must advance")
            kind = "POSTED" if new_status == "POSTED" else "REOPENED"
            self.conn.execute("UPDATE receipt_queue SET status=? WHERE id=?",
                              (new_status, receipt_id))
            self.conn.execute(
                "INSERT INTO receipt_status_events(receipt_id,event_kind,status,occurred_utc,path_snapshot) VALUES(?,?,?,?,?)",
                (receipt_id, kind, new_status, when, path))
            return True

    def replay(self, year, month):
        """Return count only for fully event-covered databases; otherwise null/HOLD."""
        try:
            year, month = int(year), int(month)
            if not (1 <= year <= 9999 and 1 <= month <= 12):
                raise ValueError()
            last = calendar.monthrange(year, month)[1]
            cutoff = (datetime(year, month, last, tzinfo=JST)
                      + timedelta(days=1)).astimezone(UTC)
        except (ValueError, OverflowError):
            raise ValueError("invalid month-end date")
        hold = lambda why: {
            "unprocessed_receipts_as_of_month_end": None,
            "status": "HOLD", "reason": why,
            "scope": "HISTORICAL_EVENTS_REQUIRED_NOT_INFERRED"}
        legacy = self.conn.execute(
            "SELECT value FROM receipt_history_meta WHERE key='legacy_unverified'"
        ).fetchone()
        if legacy is None or legacy[0] != "0":
            return hold("LEGACY_HISTORY_UNKNOWN")
        rows = {int(r[0]): (r[1], r[2]) for r in self.conn.execute(
            "SELECT id,file_path,status FROM receipt_queue")}
        events = list(self.conn.execute(
            "SELECT receipt_id,event_kind,status,occurred_utc,path_snapshot "
            "FROM receipt_status_events ORDER BY event_id"))
        seen = {}
        state_at_cutoff = {}
        try:
            for rid, kind, status, stamp, path in events:
                rid = int(rid)
                if rid not in rows or rows[rid][0] != path:
                    return hold("SOURCE_RECEIPT_MISSING_OR_CHANGED")
                dt = datetime.fromisoformat(stamp)
                if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
                    return hold("INVALID_EVENT_TIME")
                previous = seen.get(rid)
                if previous is None:
                    if kind != "ENQUEUED" or status != "PENDING":
                        return hold("EVENT_SEQUENCE_GAP")
                elif (dt <= previous[1] or
                      (previous[0], kind, status) not in
                      (("PENDING", "POSTED", "POSTED"),
                       ("POSTED", "REOPENED", "PENDING"))):
                    return hold("EVENT_SEQUENCE_GAP")
                seen[rid] = (status, dt)
                if dt < cutoff:
                    state_at_cutoff[rid] = status
        except (ValueError, TypeError):
            return hold("INVALID_EVENT_TIME")
        if set(seen) != set(rows):
            return hold("UNLOGGED_RECEIPT")
        if any(seen[rid][0] != row[1] for rid, row in rows.items()):
            return hold("UNLOGGED_STATUS_CHANGE")
        return {
            "unprocessed_receipts_as_of_month_end": sum(
                status != "POSTED" for status in state_at_cutoff.values()),
            "status": "VERIFIED_HISTORY_ONLY",
            "scope": "EVENT_TIME_AS_OF_JST_MONTH_END",
            "as_of_date": date(year, month, last).isoformat(),
            "tax_filing_or_deduction_approved": False}
