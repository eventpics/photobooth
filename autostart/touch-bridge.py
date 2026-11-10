#!/usr/bin/env python3
"""Turns a touchscreen stuck in mouse mode into a real touchscreen.

Many cheap USB touchscreens do register a multitouch interface, but send
their data exclusively over a second interface that pretends to be a mouse:
absolute position plus left button. Linux turns that into a mouse pointer.
Swiping then means "hold the button and drag", and that scrolls no page.

Measured on the development box's screen (wch.cn TouchScreen, 27c0:0859): on
touch, 0 bytes arrived on the multitouch interface and 52 kB on the mouse
interface, carrying ABS_X, ABS_Y and BTN_LEFT.

This bridge reads the mouse interface exclusively and replays the same
touches as a virtual touchscreen. The interface gets real touch events and
scrolls like a tablet.

Hidden by grabbing rather than by a udev rule, on purpose: if the bridge dies
the kernel releases the device and the screen works as a mouse again. Worse
to use, but never dead.
"""

from __future__ import annotations

import logging
import signal
import sys
import time

import evdev
from evdev import AbsInfo, UInput, ecodes as e

log = logging.getLogger("touch-bridge")

NAME = "Fotobox Touchscreen"

#: Physical size, for when the device reports nonsense. Only relevant to
#: thresholds like "when does this become a swipe", not to the position.
#: 15,3 Zoll im Format 16:10 sind rund 330 x 206 mm.
BREITE_MM = 330
HOEHE_MM = 206


def ist_maus_touchscreen(geraet: evdev.InputDevice) -> bool:
    """A device that calls itself a touchscreen but sends like a mouse."""
    if geraet.name == NAME:
        return False                      # die eigene virtuelle Ausgabe
    # absinfo=False: otherwise the axes come back as (code, range) pairs and
    # the search for ABS_X never finds anything.
    faehig = geraet.capabilities(absinfo=False)
    achsen = faehig.get(e.EV_ABS, [])
    tasten = faehig.get(e.EV_KEY, [])
    return ("touch" in geraet.name.lower()
            and e.ABS_X in achsen and e.ABS_Y in achsen
            and e.ABS_MT_SLOT not in achsen
            and e.BTN_LEFT in tasten)


def ist_maus(geraet: evdev.InputDevice) -> bool:
    """Sends like a mouse: absolute position plus buttons, no touches."""
    faehig = geraet.capabilities(absinfo=False)
    achsen = faehig.get(e.EV_ABS, [])
    return (geraet.name != NAME
            and e.ABS_X in achsen and e.ABS_Y in achsen
            and e.ABS_MT_SLOT not in achsen
            and e.BTN_LEFT in faehig.get(e.EV_KEY, []))


def hat_echten_zwilling(geraet: evdev.InputDevice,
                        alle: list[evdev.InputDevice]) -> bool:
    """Does this device have a real multitouch interface as well?

    The same hardware registers under the same vendor and product id. If one
    of those interfaces has ABS_MT_SLOT, the screen can do proper touch - and
    the mouse interface is just a second route for the same fingers.
    """
    kennung = (geraet.info.vendor, geraet.info.product)
    for anderes in alle:
        if anderes.path == geraet.path or (anderes.info.vendor,
                                           anderes.info.product) != kennung:
            continue
        if e.ABS_MT_SLOT in anderes.capabilities(absinfo=False).get(e.EV_ABS, []):
            return True
    return False


def finde_quelle() -> tuple[evdev.InputDevice, str]:
    """Waits for a screen and says what is to be done with it.

    Two cases, both ending at the same mouse interface:

    "uebersetzen"  The screen can only do mouse. Its events are replayed as
                   touches, or nothing scrolls.
    "schlucken"    The screen does proper multitouch and sends mouse events
                   on top. Every finger then arrives twice: the interface
                   begins a swipe and sees a dragged mouse pointer at the
                   same time. Here the mouse interface is merely swallowed.
    """
    gemeldet = False
    while True:
        geraete = []
        for pfad in evdev.list_devices():
            try:
                geraete.append(evdev.InputDevice(pfad))
            except OSError:
                continue
        for geraet in geraete:
            if not ist_maus(geraet):
                continue
            echt = hat_echten_zwilling(geraet, geraete)
            if echt or "touch" in geraet.name.lower():
                for anderes in geraete:
                    if anderes.path != geraet.path:
                        anderes.close()
                return geraet, "schlucken" if echt else "uebersetzen"
        for geraet in geraete:
            geraet.close()
        if not gemeldet:
            log.info("Kein passender Bildschirm gefunden - warte")
            gemeldet = True
        time.sleep(3)


def baue_ziel(quelle: evdev.InputDevice) -> UInput:
    ax = quelle.absinfo(e.ABS_X)
    ay = quelle.absinfo(e.ABS_Y)
    # Auflösung in Einheiten je Millimeter. Die Geräte melden hier oft
    # Unsinn; libinput rechnet damit Wischschwellen aus.
    rx = max(1, round((ax.max - ax.min) / BREITE_MM))
    ry = max(1, round((ay.max - ay.min) / HOEHE_MM))
    x = AbsInfo(value=0, min=ax.min, max=ax.max, fuzz=0, flat=0, resolution=rx)
    y = AbsInfo(value=0, min=ay.min, max=ay.max, fuzz=0, flat=0, resolution=ry)
    faehig = {
        e.EV_KEY: [e.BTN_TOUCH],
        e.EV_ABS: [
            (e.ABS_X, x),
            (e.ABS_Y, y),
            (e.ABS_MT_SLOT, AbsInfo(0, 0, 0, 0, 0, 0)),
            (e.ABS_MT_TRACKING_ID, AbsInfo(0, 0, 65535, 0, 0, 0)),
            (e.ABS_MT_POSITION_X, x),
            (e.ABS_MT_POSITION_Y, y),
        ],
    }
    return UInput(faehig, name=NAME, input_props=[e.INPUT_PROP_DIRECT])


def uebersetze(quelle: evdev.InputDevice, ziel: UInput) -> None:
    """Reads mouse events and writes touches.

    Within one packet up to SYN_REPORT, the button can come before or after
    the coordinates. So everything is collected first and decided at the end
    of the packet - otherwise a touch would sometimes begin at the old spot.
    """
    x = y = 0
    unten = False
    kennung = 0
    taste: bool | None = None
    bewegt = False

    def position() -> None:
        ziel.write(e.EV_ABS, e.ABS_MT_POSITION_X, x)
        ziel.write(e.EV_ABS, e.ABS_MT_POSITION_Y, y)
        ziel.write(e.EV_ABS, e.ABS_X, x)
        ziel.write(e.EV_ABS, e.ABS_Y, y)

    for ereignis in quelle.read_loop():
        if ereignis.type == e.EV_ABS:
            if ereignis.code == e.ABS_X:
                x, bewegt = ereignis.value, True
            elif ereignis.code == e.ABS_Y:
                y, bewegt = ereignis.value, True
        elif ereignis.type == e.EV_KEY and ereignis.code in (e.BTN_LEFT, e.BTN_TOUCH):
            taste = bool(ereignis.value)
        elif ereignis.type == e.EV_SYN and ereignis.code == e.SYN_REPORT:
            if taste is True and not unten:
                kennung = (kennung + 1) % 65535
                ziel.write(e.EV_ABS, e.ABS_MT_SLOT, 0)
                ziel.write(e.EV_ABS, e.ABS_MT_TRACKING_ID, kennung)
                position()
                ziel.write(e.EV_KEY, e.BTN_TOUCH, 1)
                ziel.syn()
                unten = True
            elif taste is False and unten:
                ziel.write(e.EV_ABS, e.ABS_MT_SLOT, 0)
                if bewegt:
                    position()
                ziel.write(e.EV_ABS, e.ABS_MT_TRACKING_ID, -1)
                ziel.write(e.EV_KEY, e.BTN_TOUCH, 0)
                ziel.syn()
                unten = False
            elif unten and bewegt:
                ziel.write(e.EV_ABS, e.ABS_MT_SLOT, 0)
                position()
                ziel.syn()
            # Movement with no button held does not exist on a touchscreen -
            # a finger does not hover. Such packets are dropped.
            taste = None
            bewegt = False


def schlucke(quelle: evdev.InputDevice) -> None:
    """Drain the mouse interface and do nothing with it.

    It is still read, so the kernel buffer does not fill up.
    """
    for _ in quelle.read_loop():
        pass


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    quelle, art = finde_quelle()
    ziel = baue_ziel(quelle) if art == "uebersetzen" else None
    try:
        # Read exclusively: otherwise the interface would get the mouse
        # events as well, and the pointer would trail the touches.
        quelle.grab()
        if art == "schlucken":
            log.info("Maus-Schnittstelle von %s (%s) wird weggefangen - "
                     "der Bildschirm kann selbst Multitouch", quelle.name, quelle.path)
            schlucke(quelle)
        else:
            ax, ay = quelle.absinfo(e.ABS_X), quelle.absinfo(e.ABS_Y)
            log.info("Brücke: %s (%s) -> %s, X 0..%d, Y 0..%d",
                     quelle.name, quelle.path, NAME, ax.max, ay.max)
            uebersetze(quelle, ziel)
    except OSError as fehler:
        # Screen unplugged. systemd restarts the bridge, which then waits
        # until it is back.
        log.warning("Touchscreen verloren: %s", fehler)
        return 1
    finally:
        try:
            quelle.ungrab()
        except OSError:
            pass
        if ziel is not None:
            ziel.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
