"""Configuration loading and persistence.

Settings live in a plain JSON file so the web UI can write them back after
the values have been dialled in interactively. Whatever ends up in this file
is what the real booth software should start from.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "config.json"

_lock = threading.Lock()


class Config:
    """Mutable configuration backed by a JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_PATH
        self.data: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        with _lock:
            with self.path.open(encoding="utf-8") as fh:
                self.data = json.load(fh)
        log.info("Configuration loaded from %s", self.path)

    def save(self) -> None:
        """Write the current configuration back to disk atomically."""
        with _lock:
            tmp = self.path.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            tmp.replace(self.path)
        log.info("Configuration written to %s", self.path)

    def section(self, name: str) -> dict[str, Any]:
        return self.data.setdefault(name, {})

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self.section(section).get(key, default)
