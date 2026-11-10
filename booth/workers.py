"""One worker per destination, strictly sequential and in capture order."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

from .journal import Journal

log = logging.getLogger(__name__)


class SinkWorker(threading.Thread):
    def __init__(self, journal: Journal, sink: str,
                 handler: Callable[[Path, str, str], None], interval: float = 2.0,
                 events=None, label: str = "", strict_order: bool = False,
                 give_up_after: int = 0) -> None:
        super().__init__(name=f"sink-{sink}", daemon=True)
        self.strict_order = strict_order
        self.give_up_after = give_up_after
        self.journal = journal
        self.events = events
        self.label = label or sink
        self.sink = sink
        self.handler = handler
        self.interval = interval
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        log.info("Worker for %s started", self.sink)
        while not self._stop.is_set():
            item = self.journal.claim_next(self.sink, strict_order=self.strict_order,
                                           give_up_after=self.give_up_after)
            if item is None:
                self._stop.wait(self.interval)
                continue
            path = Path(item["path"])
            if not path.exists():
                # Discarded or cleaned up after being queued: nothing owed.
                self.journal.finish(item["id"], self.sink, ok=True)
                continue
            try:
                self.handler(path, item["kind"], item["session"] or "")
                self.journal.finish(item["id"], self.sink, ok=True)
                if self.events and item["kind"] == "result":
                    self.events.add(f"{path.name} auf {self.label} gesichert", "good")
            except Exception as exc:  # noqa: BLE001 - the queue must never die
                message = str(exc) or exc.__class__.__name__
                self.journal.finish(item["id"], self.sink, ok=False, error=message)
                if self.events and item["kind"] == "result":
                    self.events.add(f"{self.label}: {path.name} wartet ({message})", "warn")
                self._stop.wait(1.0)
