"""Durable record of every kept picture and where it still has to go.

One journal, several destinations: the USB stick and the EventPics gallery are
both "sinks" over the same list. That keeps one guarantee in one place instead
of two queues that drift apart.

SQLite rather than a JSON file on purpose - the box gets unplugged at the end
of the night, usually mid-write.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger(__name__)

PENDING, WORKING, DONE, FAILED = "pending", "working", "done", "failed"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    path      TEXT NOT NULL,
    kind      TEXT NOT NULL,           -- result | shot
    session   TEXT,
    taken_at  REAL,                    -- real capture time, kept for gallery order
    created   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sink_state (
    item_id    INTEGER NOT NULL,
    sink       TEXT NOT NULL,
    state      TEXT NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    not_before REAL NOT NULL DEFAULT 0, -- backoff after a failure
    last_error TEXT,
    updated    REAL NOT NULL,
    PRIMARY KEY (item_id, sink)
);
CREATE INDEX IF NOT EXISTS idx_sink_pending ON sink_state (sink, state, not_before);
"""


class Journal:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as db:
            db.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        # WAL survives a power cut far better than the default journal mode.
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def add(self, path: Path, kind: str, sinks: Iterable[str],
            session: str = "", taken_at: float | None = None) -> int:
        now = time.time()
        with self._lock, self._connect() as db:
            cur = db.execute(
                "INSERT INTO items (path, kind, session, taken_at, created) VALUES (?,?,?,?,?)",
                (str(path), kind, session, taken_at or now, now))
            item_id = int(cur.lastrowid)
            for sink in sinks:
                db.execute("INSERT OR REPLACE INTO sink_state "
                           "(item_id, sink, state, attempts, not_before, updated) "
                           "VALUES (?,?,?,0,0,?)", (item_id, sink, PENDING, now))
        log.info("Journal: %s (%s) queued for %s", Path(path).name, kind, ", ".join(sinks))
        return item_id

    def claim_next(self, sink: str, strict_order: bool = False,
                   give_up_after: int = 0) -> dict[str, Any] | None:
        """Oldest item still owed to this sink. Strictly one at a time.

        `strict_order` decides what happens when the oldest item is waiting out
        a backoff. Without it the next item is taken instead, which is fine for
        a USB stick - the files land in a folder and nobody looks at the order.
        With it the queue waits, because a gallery shows pictures in the order
        they arrive: if the second picture were uploaded while the first is
        being retried, the evening would be out of sequence for good.

        `give_up_after` keeps a strict queue from stalling for ever on one
        picture that can never succeed. Zero means never give up.
        """
        now = time.time()
        with self._lock, self._connect() as db:
            if strict_order:
                row = db.execute(
                    "SELECT i.*, s.attempts, s.not_before FROM items i "
                    "JOIN sink_state s ON s.item_id = i.id "
                    "WHERE s.sink = ? AND s.state IN (?, ?) ORDER BY i.id LIMIT 1",
                    (sink, PENDING, FAILED)).fetchone()
                if row is None:
                    return None
                if give_up_after and row["attempts"] >= give_up_after:
                    # Give up rather than block the queue forever. The entry
                    # counts as done; the failure stays on record.
                    db.execute("UPDATE sink_state SET state=?, updated=? "
                               "WHERE item_id=? AND sink=?", (DONE, now, row["id"], sink))
                    log.error("Journal: %s gives up on item %s after %s attempts",
                              sink, row["id"], row["attempts"])
                    return None
                if row["not_before"] > now:
                    return None          # warten, nicht ueberholen
            else:
                row = db.execute(
                    "SELECT i.*, s.attempts FROM items i JOIN sink_state s ON s.item_id = i.id "
                    "WHERE s.sink = ? AND s.state IN (?, ?) AND s.not_before <= ? "
                    "ORDER BY i.id LIMIT 1",
                    (sink, PENDING, FAILED, now)).fetchone()
                if row is None:
                    return None
            db.execute("UPDATE sink_state SET state=?, updated=? WHERE item_id=? AND sink=?",
                       (WORKING, now, row["id"], sink))
            return dict(row)

    def finish(self, item_id: int, sink: str, ok: bool, error: str = "",
               backoff_base: float = 5.0, backoff_max: float = 300.0) -> None:
        now = time.time()
        with self._lock, self._connect() as db:
            if ok:
                db.execute("UPDATE sink_state SET state=?, last_error=NULL, updated=? "
                           "WHERE item_id=? AND sink=?", (DONE, now, item_id, sink))
                return
            row = db.execute("SELECT attempts FROM sink_state WHERE item_id=? AND sink=?",
                             (item_id, sink)).fetchone()
            attempts = (row["attempts"] if row else 0) + 1
            # Grows to a five minute ceiling: a venue without wifi should not be
            # retried every second for six hours, but must catch up on its own.
            delay = min(backoff_max, backoff_base * (2 ** min(attempts - 1, 6)))
            db.execute("UPDATE sink_state SET state=?, attempts=?, not_before=?, "
                       "last_error=?, updated=? WHERE item_id=? AND sink=?",
                       (FAILED, attempts, now + delay, error[:500], now, item_id, sink))
        log.warning("Journal: %s attempt %s for item %s failed (%s), retry in %.0fs",
                    sink, attempts, item_id, error, delay)

    def stats(self, sink: str) -> dict[str, Any]:
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT state, COUNT(*) n FROM sink_state WHERE sink=? "
                              "GROUP BY state", (sink,)).fetchall()
            counts = {r["state"]: r["n"] for r in rows}
            last = db.execute("SELECT updated FROM sink_state WHERE sink=? AND state=? "
                              "ORDER BY updated DESC LIMIT 1", (sink, DONE)).fetchone()
            err = db.execute("SELECT last_error FROM sink_state WHERE sink=? AND state=? "
                             "AND last_error IS NOT NULL ORDER BY updated DESC LIMIT 1",
                             (sink, FAILED)).fetchone()
        return {
            "sink": sink,
            "done": counts.get(DONE, 0),
            "pending": counts.get(PENDING, 0) + counts.get(WORKING, 0),
            "failed": counts.get(FAILED, 0),
            "last_done_at": last["updated"] if last else None,
            "last_error": err["last_error"] if err else None,
        }

    def reset_working(self) -> None:
        """After a restart nothing is actually in flight - put those back."""
        with self._lock, self._connect() as db:
            db.execute("UPDATE sink_state SET state=? WHERE state=?", (PENDING, WORKING))
