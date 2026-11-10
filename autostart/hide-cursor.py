#!/usr/bin/env python3
"""Creates a cursor theme made entirely of invisible pointers.

A photo booth has no mouse. Many touchscreens nevertheless register as a mouse
as well, and the compositor then shows a pointer - in the middle of the
picture, motionless, because the touch bridge swallows the mouse events. The
interface hides its own pointer, but only while it is over its window, and
without a single mouse movement that never happens.

A cursor theme of its own, whose images are fully transparent, fixes that. The
service points XCURSOR_PATH at it.

The theme is called "default" on purpose: cage asks wlroots for the theme with
no name, and that is always "default" - cage does not read XCURSOR_THEME.
Verified on the Pi: named "photobooth-hidden" the white arrow sat in the middle
of the picture despite the variables being set; named "default" it is gone.

    python3 hide-cursor.py /home/<user>/.config/photobooth/cursor
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

THEME = "default"

#: Names the compositor and applications use for the ordinary pointer.
NAMES = ["default", "left_ptr", "arrow", "top_left_arrow", "pointer", "hand1", "hand2",
         "text", "xterm", "watch", "progress", "crosshair"]

#: Sizes the pointer may be asked for. If one is missing the compositor falls
#: back to its built-in theme - and the pointer would be back.
SIZES = [16, 24, 32, 48, 64, 96, 128]

MAGIC = b"Xcur"
IMAGE_TYPE = 0xFFFD0002


def transparent_cursor() -> bytes:
    """Eine Xcursor-Datei mit einem durchsichtigen Bild je Groesse."""
    toc = b""
    chunks = b""
    header_size = 16
    toc_size = len(SIZES) * 12
    offset = header_size + toc_size
    for size in SIZES:
        # Bildkopf (36 Byte) plus ein Bildpunkt, vollstaendig durchsichtig.
        chunk = struct.pack("<IIIIIIIII", 36, IMAGE_TYPE, size, 1, 1, 1, 0, 0, 0)
        chunk += struct.pack("<I", 0)
        toc += struct.pack("<III", IMAGE_TYPE, size, offset)
        chunks += chunk
        offset += len(chunk)
    header = struct.pack("<IIII", int.from_bytes(MAGIC, "little"), header_size,
                         0x00010000, len(SIZES))
    return header + toc + chunks


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1
                  else Path.home() / ".config" / "photobooth" / "cursor")
    cursors = target / THEME / "cursors"
    cursors.mkdir(parents=True, exist_ok=True)
    data = transparent_cursor()
    for name in NAMES:
        (cursors / name).write_bytes(data)
    (target / THEME / "index.theme").write_text(
        f"[Icon Theme]\nName={THEME}\nComment=Unsichtbar, fuer die Fotobox\n",
        encoding="utf-8")
    print(f"Unsichtbarer Mauszeiger unter {target / THEME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
