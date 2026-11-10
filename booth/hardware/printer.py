"""Printer interface via CUPS command line tools.

No Python CUPS binding is used on purpose: lpstat and lp are present on every
Raspberry Pi OS install that has CUPS, which keeps the dependency list short.

The generated test page is built to reveal the two things that actually go
wrong on a Selphy: wrong media size and cropped borders.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_TIMEOUT = 15


class PrinterError(RuntimeError):
    pass


def cups_available() -> bool:
    return shutil.which("lpstat") is not None and shutil.which("lp") is not None


def _run(args: list[str]) -> str:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=_TIMEOUT, check=False
        )
    except FileNotFoundError as exc:
        raise PrinterError(f"Befehl nicht gefunden: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise PrinterError(f"Zeitüberschreitung bei: {' '.join(args)}") from exc
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip() or f"Exit-Code {result.returncode}"
        raise PrinterError(message)
    return result.stdout


def list_printers() -> dict[str, Any]:
    if not cups_available():
        return {"available": False, "printers": [], "default": None,
                "note": "CUPS ist nicht installiert (lpstat/lp fehlen)."}

    printers: list[dict[str, Any]] = []
    try:
        for line in _run(["lpstat", "-p"]).splitlines():
            # Format: "printer NAME is idle.  enabled since ..."
            if not line.startswith("printer "):
                continue
            parts = line.split()
            printers.append({
                "name": parts[1],
                "state": " ".join(parts[2:]).rstrip("."),
            })
    except PrinterError as exc:
        return {"available": True, "printers": [], "default": None, "error": str(exc)}

    default = None
    try:
        out = _run(["lpstat", "-d"]).strip()
        if ":" in out:
            default = out.split(":", 1)[1].strip()
    except PrinterError:
        pass

    return {"available": True, "printers": printers, "default": default}


#: USB device class 7 is "Printer". The number is in the device's own
#: descriptor and stays there even while CUPS holds the port - unlike
#: /dev/usb/lp0, which can disappear during a print.
_USB_PRINTER_CLASS = "07"
_USB_DEVICES = Path("/sys/bus/usb/devices")


def usb_printer_attached() -> bool | None:
    """Is a USB printer attached to this machine?

    None means: cannot be told from here (no sysfs, on a Mac for instance).
    """
    if not _USB_DEVICES.is_dir():
        return None
    try:
        for datei in _USB_DEVICES.glob("*/bInterfaceClass"):
            if datei.read_text().strip() == _USB_PRINTER_CLASS:
                return True
    except OSError:
        return None
    return False


def device_uris() -> dict[str, str]:
    """Welche Warteschlange an welchem Anschluss haengt."""
    if not cups_available():
        return {}
    out: dict[str, str] = {}
    try:
        for line in _run(["lpstat", "-v"]).splitlines():
            # Format: "device for NAME: usb://Canon/SELPHY%20CP1500?serial=..."
            if not line.startswith("device for ") or ":" not in line:
                continue
            kopf, rest = line[len("device for "):].split(":", 1)
            out[kopf.strip()] = rest.strip()
    except PrinterError as exc:
        log.debug("Could not read the device URIs: %s", exc)
    return out


def presence() -> dict[str, Any]:
    """Whether printing is possible - really possible.

    CUPS keeps a queue forever once it has been set up. "idle, enabled"
    therefore only means somebody created it, not that a device is on the end
    of the cable: this box reported a printer that was not there at all. The
    question is about the device, so sysfs is checked as well for an actual
    USB printer.

    "attached" is None when that cannot be answered - for a network printer,
    say. The queue then has the last word, because nobody knows more.
    """
    info = list_printers()
    if not info.get("available"):
        return {"ready": False, "queue": None, "attached": None,
                "reason": info.get("note") or "CUPS fehlt"}
    namen = [d["name"] for d in info.get("printers") or []]
    if not namen:
        return {"ready": False, "queue": None, "attached": None,
                "reason": "keine Warteschlange eingerichtet"}
    name = info.get("default") if info.get("default") in namen else namen[0]
    uri = device_uris().get(name, "")
    if uri.startswith("usb:"):
        angesteckt = usb_printer_attached()
    else:
        angesteckt = None          # Netzdrucker: nicht am Kabel zu erkennen
    bereit = angesteckt is not False
    return {"ready": bereit, "queue": name, "attached": angesteckt, "uri": uri,
            "reason": "" if bereit else "kein Drucker am USB-Anschluss"}


def queue() -> list[str]:
    if not cups_available():
        return []
    try:
        return [line for line in _run(["lpstat", "-o"]).splitlines() if line.strip()]
    except PrinterError as exc:
        return [f"Fehler: {exc}"]


def print_file(path: Path, printer: str = "", media: str = "", extra: list[str] | None = None) -> dict[str, Any]:
    if not cups_available():
        raise PrinterError("CUPS ist nicht installiert (lpstat/lp fehlen).")
    if not path.exists():
        raise PrinterError(f"Datei nicht gefunden: {path}")

    args = ["lp"]
    if printer:
        args += ["-d", printer]
    if media:
        args += ["-o", f"media={media}"]
    for option in extra or []:
        args += ["-o", option]
    args.append(str(path))

    output = _run(args).strip()
    log.info("Print job submitted: %s", output)
    return {"command": " ".join(args), "output": output}


def build_test_page(target: Path, size: tuple[int, int] = (1800, 1200)) -> Path:
    """Renders a 10x15 test page at 300 dpi.

    Deliberately includes a frame right at the paper edge and corner markers:
    if any of them is missing on the print, the media setting or the bleed
    configuration is wrong.
    """
    from PIL import Image, ImageDraw  # noqa: PLC0415

    width, height = size
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    # Outer frame, 1 mm in from the edge at 300 dpi.
    inset = 12
    draw.rectangle([inset, inset, width - inset - 1, height - inset - 1],
                   outline=(0, 0, 0), width=4)

    # Corner markers - if one is cut off, the page is being scaled or cropped.
    marker = 120
    for x0, y0, x1, y1 in (
        (0, 0, marker, marker),
        (width - marker, 0, width, marker),
        (0, height - marker, marker, height),
        (width - marker, height - marker, width, height),
    ):
        draw.rectangle([x0, y0, x1, y1], fill=(220, 0, 0))

    # Grey wedge to judge tonal response of the dye sublimation ribbon.
    steps = 11
    wedge_h = 160
    wedge_y = height // 2 - wedge_h // 2
    for index in range(steps):
        value = int(255 * index / (steps - 1))
        x0 = inset + 40 + index * ((width - 2 * inset - 80) / steps)
        x1 = x0 + ((width - 2 * inset - 80) / steps)
        draw.rectangle([x0, wedge_y, x1, wedge_y + wedge_h], fill=(value, value, value))

    # Primary colour patches.
    colours = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (0, 255, 255), (255, 0, 255), (255, 255, 0)]
    patch_h = 140
    patch_y = wedge_y + wedge_h + 40
    for index, colour in enumerate(colours):
        x0 = inset + 40 + index * ((width - 2 * inset - 80) / len(colours))
        x1 = x0 + ((width - 2 * inset - 80) / len(colours))
        draw.rectangle([x0, patch_y, x1, patch_y + patch_h], fill=colour)

    draw.text((inset + 40, inset + 40), "EventPics Fotobox - Druckertest", fill=(0, 0, 0))
    draw.text((inset + 40, inset + 60),
              f"{width}x{height} px @ 300 dpi = 15,2 x 10,2 cm", fill=(0, 0, 0))
    draw.text((inset + 40, inset + 80),
              "Alle vier roten Ecken und der Rahmen müssen sichtbar sein.", fill=(0, 0, 0))

    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, format="JPEG", quality=95)
    return target
