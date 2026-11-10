"""What the booth did, in plain sentences.

Two readers: the host glancing at the screen during an event, and whoever has
to work out afterwards why a picture never arrived. Both want the same list, so
there is one - short, human, and written to disk so it survives a restart.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger(__name__)

INFO, GOOD, WARN, ERROR = "info", "good", "warn", "error"


class EventLog:
    def __init__(self, path: Path, keep: int = 500) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items: deque[dict[str, Any]] = deque(maxlen=keep)
        self._lock = threading.Lock()
        self._next_id = 1
        self._load()

    def _load(self) -> None:
        """Read the log back - forgiving everything on the way.

        If the box is unplugged while running, the filesystem can pad a
        half-written line with null bytes. That happened on the Pi: afterwards
        there was a line of 400 nulls in the file, reading it raised, and the
        box would not come up - over a log nobody needs in order to take
        photographs. Broken lines are skipped.
        """
        if not self.path.exists():
            return
        try:
            roh = self.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        verworfen = 0
        for line in roh.splitlines()[-self._items.maxlen:]:
            parts = line.replace("\x00", "").split("\t", 2)
            if len(parts) != 3:
                verworfen += 1 if line.strip() else 0
                continue
            try:
                wann = float(parts[0])
            except ValueError:
                verworfen += 1
                continue
            self._items.append({"id": self._next_id, "at": wann,
                                "level": parts[1], "text": parts[2]})
            self._next_id += 1
        if verworfen:
            log.warning("Event log: %s unlesbare Zeilen uebersprungen", verworfen)

    def add(self, text: str, level: str = INFO) -> None:
        now = time.time()
        with self._lock:
            self._items.append({"id": self._next_id, "at": now, "level": level, "text": text})
            self._next_id += 1
            try:
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(f"{now:.3f}\t{level}\t{text}\n")
            except OSError:
                log.debug("Could not append to event log", exc_info=True)
        log.info("Event: %s", text)

    def clear(self) -> int:
        """Throw the list away, on disk as well.

        Kept simple on purpose: no age limit, no rotation. The host decides when
        the old messages have stopped being interesting - usually right after
        the fault they were reading them for.
        """
        with self._lock:
            count = len(self._items)
            self._items.clear()
            try:
                self.path.write_text("", encoding="utf-8")
            except OSError:
                log.warning("Could not empty the event log file")
        return count

    def recent(self, limit: int = 80, since_id: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            items = [i for i in self._items if i["id"] > since_id]
        return items[-limit:]

    def last(self) -> dict[str, Any] | None:
        with self._lock:
            return self._items[-1] if self._items else None
