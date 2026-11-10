"""Copying every kept picture onto a USB stick.

The stick is a mirror, never the primary store: it can be missing, full or
pulled out mid-write, and none of that may stop the booth. Whatever could not
be copied stays in the journal and is caught up when a stick reappears.

Files are written to a temporary name and renamed into place, so a stick that
is yanked mid-copy holds either the whole picture or nothing - never a
half-written file the couple later finds broken.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: Written to a stick the booth has adopted, so a guest's own stick plugged in
#: for charging never silently receives the whole evening.
MARKER = ".eventpics-fotobox"


class UsbTarget:
    """Finds a usable stick and copies files onto it."""

    def __init__(self, config, events=None) -> None:
        self.config = config
        self.events = events
        self.last_error: str | None = None
        self._was_present: bool | None = None

    def section(self) -> dict[str, Any]:
        return self.config.section("usb")

    def _search_roots(self) -> list[Path]:
        configured = self.section().get("search_paths")
        if configured:
            return [Path(p) for p in configured]
        roots = [Path("/media"), Path("/mnt")]
        found: list[Path] = []
        for root in roots:
            if not root.is_dir():
                continue
            for child in root.iterdir():
                # /media/<user>/<label> on Raspberry Pi OS, /mnt/<label> elsewhere
                found.append(child)
                if child.is_dir():
                    found.extend(c for c in child.iterdir() if c.is_dir())
        return found

    def find_mount(self) -> Path | None:
        require_marker = bool(self.section().get("require_marker", False))
        # Only a blind search insists on a real mount point. Someone who
        # names a path in the settings means that path, even if it is an
        # ordinary folder - for trying things out, say.
        nur_einhaengepunkte = not self.section().get("search_paths")
        candidates: list[Path] = []
        for path in self._search_roots():
            try:
                if not path.is_dir() or not os.access(path, os.W_OK):
                    continue
                # A writable folder is not yet a stick. On some systems
                # /media/<user> belongs to the user and so looked like a
                # volume - the box then reported the SD card's free space as
                # the stick's.
                if nur_einhaengepunkte and not os.path.ismount(path):
                    continue
            except OSError:
                continue
            if (path / MARKER).exists():
                return path                      # our own prepared stick wins
            candidates.append(path)
        if require_marker:
            return None
        return candidates[0] if candidates else None

    def poll_presence(self) -> None:
        """Notice a stick being plugged in or pulled out, and say so."""
        present = self.find_mount() is not None
        if self._was_present is not None and present != self._was_present and self.events:
            self.events.add("USB-Stick angesteckt" if present else "USB-Stick entfernt",
                            "good" if present else "warn")
        self._was_present = present

    def status(self) -> dict[str, Any]:
        mount = self.find_mount()
        info: dict[str, Any] = {
            "present": mount is not None,
            "mount": str(mount) if mount else None,
            "adopted": bool(mount and (mount / MARKER).exists()),
            "last_error": self.last_error,
        }
        if mount:
            try:
                usage = shutil.disk_usage(mount)
                info["free_gb"] = round(usage.free / 1e9, 2)
                info["total_gb"] = round(usage.total / 1e9, 2)
            except OSError as exc:
                info["last_error"] = str(exc)
        return info

    def adopt(self) -> dict[str, Any]:
        """Mark the stick currently plugged in as the booth's own."""
        mount = self.find_mount()
        if mount is None:
            return {"ok": False, "error": "Kein beschreibbarer USB-Stick gefunden"}
        try:
            (mount / MARKER).write_text("EventPics Fotobox\n", encoding="utf-8")
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "mount": str(mount)}

    def copy(self, source: Path, kind: str, session: str = "") -> Path:
        """Copy one file onto the stick. Raises if it cannot be completed."""
        mount = self.find_mount()
        if mount is None:
            raise FileNotFoundError("Kein USB-Stick angesteckt")

        folder = str(self.section().get("folder", "Fotobox"))
        sub = "Bilder" if kind == "result" else "Einzelaufnahmen"
        target_dir = mount / folder / sub
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / Path(source).name

        if target.exists() and target.stat().st_size == Path(source).stat().st_size:
            return target                        # already there, nothing to do

        tmp = target.with_suffix(target.suffix + ".part")
        with open(source, "rb") as src, open(tmp, "wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 512)
            dst.flush()
            os.fsync(dst.fileno())               # survive an unplug right after
        os.replace(tmp, target)
        self.last_error = None
        return target
