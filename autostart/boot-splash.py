#!/usr/bin/env python3
"""Paint the start screen into the framebuffer, long before the interface runs.

The booth takes about half a minute to come up on a Pi 4, and the console is
deliberately silent: `quiet`, `loglevel=3`, `logo.nologo`. So the screen stays
black the whole way, which looks exactly like a box that is not starting at
all. A host standing in front of guests does not know whether to wait or to
pull the plug.

This draws the same picture the Qt start screen shows - white, black mark,
"EventPics Fotobox" - with a bar underneath that keeps moving, so the screen
says "working" rather than "dead".

**Why the picture is cached.** The first version built it here with Pillow,
and on the booth it reached the screen 20 seconds into a 23 second boot: the
service was up after 5.7 seconds and spent the next 14 importing numpy and
Pillow and rendering text, all while udev and the journal were hammering the
same SD card. So the picture is rendered once, by `--render`, into a raw
framebuffer dump under /var/cache/photobooth. At boot this reads that file and
writes it out - no numpy, no Pillow, no fonts, nothing but open() and write().
Those imports only ever happen in `rendern()`, never on the fast path.

If the cache is missing, or the screen has a shape no cached file matches, it
renders on the spot and saves the result, so the next boot is fast again.

The same picture serves at the other end. `--once` draws one frame and
returns, which is what photobooth-shutdown.service calls while the system is
going down. That screen earns its keep: the booth has no power button, so
somebody has to be told when pulling the plug is safe. Doing it too early is
how a filesystem ends up needing a repair on the next boot.

It stops when photobooth.service starts; `ExecStartPre` in that unit does the
stopping. Nothing clears the framebuffer in between, so the last frame stays
on the screen until cage paints over it. The join is invisible.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

#: The stage the interface is designed for. The picture is built at this size
#: and scaled to whatever the framebuffer actually is.
STAGE_W, STAGE_H = 1920, 1080

PAPER = (255, 255, 255)
MARK = (0, 0, 0)
MARK_DIM = (107, 107, 107)          # theme's #6B6B6B
BAR_BG = (226, 226, 226)

ICON_PX = 190
FONT_PFADE = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

HIER = Path(__file__).resolve().parent.parent
ICON = HIER / "booth" / "assets" / "icon.png"
CACHE = Path("/var/cache/photobooth")

NOTE_START = "wird gestartet"
NOTE_ENDE = "wird heruntergefahren\nGleich kannst du den Strom trennen"

#: Give up after this long. A splash that outlived the boot would sit on top
#: of a working booth if the unit were ever started by hand.
MAX_S = 240.0
FRAME_S = 0.08
#: How often the whole picture is written again. Four seconds into the boot
#: the display mode may not be set yet, and setting it clears the framebuffer.
VOLLBILD_S = 1.0


def seit_start() -> str:
    """Seconds since the machine booted, for the journal line."""
    try:
        return "%.1f" % float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError):
        return "?"


def framebuffer() -> tuple[int, int, int, int]:
    """Width, height, bits per pixel and bytes per line of /dev/fb0."""
    basis = Path("/sys/class/graphics/fb0")
    breite, hoehe = (int(n) for n in
                     (basis / "virtual_size").read_text().strip().split(","))
    tiefe = int((basis / "bits_per_pixel").read_text().strip())
    schritt = int((basis / "stride").read_text().strip())
    return breite, hoehe, tiefe, schritt


def name(rolle: str, geo: tuple[int, int, int, int]) -> Path:
    """One cache file per role and screen shape.

    The name is spelled out rather than hashed because boot-splash.sh has to
    find the same file with nothing but shell arithmetic, and that runs before
    anything as expensive as Python is loaded.
    """
    return CACHE / ("%s-%dx%d-%d" % (rolle, geo[0], geo[1], geo[2]))


# -- the slow path: Pillow, numpy, fonts ---------------------------------------

def rendern(geo: tuple[int, int, int, int], note: str,
            balken: bool) -> tuple[bytes, tuple[int, int, int, int]]:
    """Build the picture and return framebuffer bytes plus the bar's place.

    Everything expensive lives in here, and here alone: the imports are local
    so that a boot which finds a cached file never pays for them.
    """
    import numpy as np                                     # noqa: PLC0415
    from PIL import Image, ImageDraw, ImageFont, ImageOps  # noqa: PLC0415

    breite, hoehe, tiefe, schritt = geo
    skala = min(breite / STAGE_W, hoehe / STAGE_H)
    bild = Image.new("RGB", (breite, hoehe), PAPER)
    zeichner = ImageDraw.Draw(bild)

    def schrift(groesse: int, fett: bool = False):
        for pfad in (FONT_PFADE if fett else FONT_PFADE[::-1]):
            if Path(pfad).exists():
                return ImageFont.truetype(pfad, groesse)
        return ImageFont.load_default()

    def mittig(text, font, y: int, farbe) -> None:
        links, hoch, rechts, _ = zeichner.textbbox((0, 0), text, font=font)
        zeichner.text(((breite - (rechts - links)) / 2 - links, y - hoch),
                      text, font=font, fill=farbe)

    # Same arrangement as booth/ui/splash.py: the group sits above centre,
    # because dead centre reads as too low on a screen at head height.
    oben = hoehe * 0.33

    if ICON.exists():
        # The file is plain RGB, a dark mark on white, with no alpha at all.
        # The start screen turns it into a stencil the same way: grey values
        # inverted become the mask, so dark ink is opaque and the white
        # around it disappears. Then the stencil is filled with the mark
        # colour. Doing it any other way would paste a white square.
        marke = Image.open(ICON).convert("L")
        kante = round(ICON_PX * skala)
        marke.thumbnail((kante, kante), Image.LANCZOS)
        flaeche = Image.new("RGB", marke.size, MARK)
        bild.paste(flaeche, (round(breite / 2 - marke.width / 2), round(oben)),
                   ImageOps.invert(marke))
        oben += marke.height + 54 * skala

    mittig("EventPics Fotobox", schrift(round(64 * skala), fett=True),
           round(oben + 12 * skala), MARK)
    oben += (86 + 18) * skala

    for zeile in note.split("\n"):
        mittig(zeile, schrift(round(28 * skala)), round(oben + 6 * skala), MARK_DIM)
        oben += 44 * skala

    bar = (0, 0, 0, 0)
    if balken:
        # Thin, wide, quiet. It carries the whole message, namely that
        # something is still happening.
        bar_b = round(420 * skala)
        bar_h = max(4, round(8 * skala))
        bar_x = round((breite - bar_b) / 2)
        bar_y = round(oben + 40 * skala)
        zeichner.rounded_rectangle([bar_x, bar_y, bar_x + bar_b, bar_y + bar_h],
                                   radius=bar_h // 2, fill=BAR_BG)
        bar = (bar_x, bar_y, bar_b, bar_h)

    feld = np.asarray(bild)
    if tiefe == 16:
        r = (feld[:, :, 0].astype(np.uint16) >> 3) << 11
        g = (feld[:, :, 1].astype(np.uint16) >> 2) << 5
        b = feld[:, :, 2].astype(np.uint16) >> 3
        roh = (r | g | b).astype("<u2").tobytes()
        je_zeile = breite * 2
    else:
        bgra = np.zeros((hoehe, breite, 4), dtype=np.uint8)
        bgra[:, :, 0] = feld[:, :, 2]
        bgra[:, :, 1] = feld[:, :, 1]
        bgra[:, :, 2] = feld[:, :, 0]
        bgra[:, :, 3] = 255
        roh = bgra.tobytes()
        je_zeile = breite * 4

    if schritt != je_zeile:
        fuellung = b"\0" * (schritt - je_zeile)
        roh = b"".join(roh[i * je_zeile:(i + 1) * je_zeile] + fuellung
                       for i in range(hoehe))
    return roh, bar


def holen(geo: tuple[int, int, int, int], rolle: str, note: str,
          balken: bool) -> tuple[bytes, tuple[int, int, int, int]]:
    """The cached picture, rendered and saved first if it is not there yet."""
    basis = name(rolle, geo)
    roh_datei, masse_datei = basis.with_suffix(".raw"), basis.with_suffix(".txt")
    try:
        roh = roh_datei.read_bytes()
        masse = tuple(int(n) for n in masse_datei.read_text().split())
        if len(roh) == geo[3] * geo[1] and len(masse) == 4:
            return roh, masse                        # type: ignore[return-value]
    except (OSError, ValueError):
        pass

    roh, masse = rendern(geo, note, balken)
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        roh_datei.write_bytes(roh)
        masse_datei.write_text(" ".join(str(n) for n in masse))
    except OSError as fehler:
        print("Startbild nicht zwischengespeichert: %s" % fehler, file=sys.stderr)
    return roh, masse


# -- the fast path -------------------------------------------------------------

def zeichnen(note: str, once: bool, schluss: float) -> bool:
    """Draw until `schluss`. True means the screen changed shape, try again."""
    try:
        geo = framebuffer()
        breite, hoehe, tiefe, schritt = geo
        if tiefe not in (16, 32):
            return False
        roh, (bar_x, bar_y, bar_b, bar_h) = holen(
            geo, "shutdown" if once else "boot", note, not once)
    except (OSError, ValueError) as fehler:
        # The display is being reconfigured; even sysfs can refuse for a
        # moment. Worth one line, never a stack trace: this runs on a screen
        # a host is watching, and the journal is read by whoever fixes it.
        print("Startbild noch nicht lesbar: %s" % fehler, file=sys.stderr)
        return True
    je_pixel = 2 if tiefe == 16 else 4
    schwarz = b"\0\0" if tiefe == 16 else b"\0\0\0\xff"
    laeufer = max(40, bar_b // 4)
    streifen_grund = roh[bar_y * schritt:(bar_y + bar_h) * schritt]

    try:
        with open("/dev/fb0", "wb", buffering=0) as fb:
            fb.seek(0)
            fb.write(roh)
            # One line in the journal saying when the screen actually had
            # something on it. Without it there is no way to tell whether the
            # picture was late or never drawn at all.
            print("Startbildschirm steht nach %s s Laufzeit" % seit_start(),
                  file=sys.stderr, flush=True)
            if once:
                # The picture stays until something paints over it, and at
                # shutdown nothing does. Holding the process here would only
                # delay the shutdown it is announcing.
                return False

            begonnen = time.monotonic()
            letzte_volle = begonnen
            while time.monotonic() < schluss:
                jetzt = time.monotonic()
                if jetzt - letzte_volle >= VOLLBILD_S:
                    if framebuffer() != geo:
                        return True       # the mode changed; build it again
                    fb.seek(0)
                    fb.write(roh)
                    letzte_volle = jetzt

                # Back and forth rather than wrapping round: a runner that
                # jumps back to the start looks like a restart.
                phase = ((jetzt - begonnen) / 1.6) % 2.0
                anteil = phase if phase <= 1.0 else 2.0 - phase
                x = bar_x + round(anteil * (bar_b - laeufer))
                streifen = bytearray(streifen_grund)
                for zeile in range(bar_h):
                    a = zeile * schritt + x * je_pixel
                    streifen[a:a + laeufer * je_pixel] = schwarz * laeufer
                fb.seek(bar_y * schritt)
                fb.write(bytes(streifen))
                time.sleep(FRAME_S)
    except (OSError, ValueError) as fehler:
        # Worth a line in the journal. Swallowed in silence once, and the
        # screen stayed black with nothing to say why.
        print("Startbildschirm nicht gezeichnet: %s" % fehler, file=sys.stderr)
        # Usually the display mode changed under us and the picture no
        # longer fits. Saying so is the caller's cue to build it again.
        try:
            return framebuffer() != geo
        except (OSError, ValueError):
            return True
    return False


def main() -> int:
    zerleger = argparse.ArgumentParser(description="EventPics Photobooth splash")
    zerleger.add_argument("--note", default=NOTE_START,
                          help="the grey line under the name; \\n splits it")
    zerleger.add_argument("--once", action="store_true",
                          help="draw one frame without the bar and return")
    zerleger.add_argument("--render", action="store_true",
                          help="build and cache both pictures, draw nothing")
    # A flag rather than a --note on the unit line: systemd has escape rules
    # of its own, and a newline that survives them is not worth the risk. The
    # wording has to match NOTE_ENDE exactly or the cache misses and the slow
    # path runs during a shutdown.
    zerleger.add_argument("--shutdown", action="store_true",
                          help="the shutdown wording, drawn once")
    args = zerleger.parse_args()
    note = NOTE_ENDE if args.shutdown else args.note.replace("\\n", "\n")
    einmal = args.once or args.shutdown

    if args.render:
        breite, hoehe, _, _ = framebuffer()
        # Both colour depths. On this Pi the framebuffer comes up at 32 bits
        # early in the boot and is reconfigured to 16 a moment later, and a
        # cache that holds only the depth seen from a running system misses
        # at exactly the moment it is needed - which cost fourteen seconds
        # and then an EFBIG when the 8 MB dump met a 4 MB framebuffer.
        for tiefe in (16, 32):
            geo = (breite, hoehe, tiefe, breite * tiefe // 8)
            for rolle, text, balken in (("boot", NOTE_START, True),
                                        ("shutdown", NOTE_ENDE, False)):
                holen(geo, rolle, text, balken)
                print("vorgerechnet: %s" % name(rolle, geo).with_suffix(".raw"))
        return 0

    for _ in range(50):                      # udev may not be there yet
        if Path("/dev/fb0").exists():
            break
        time.sleep(0.2)
    else:
        return 0                             # no screen, nothing to say

    schluss = time.monotonic() + MAX_S
    for _ in range(20):
        if time.monotonic() >= schluss or not zeichnen(note, einmal, schluss):
            break
        # The display mode was set while we were drawing, which resizes the
        # framebuffer. Build the picture again at the new size. Counted, so
        # that a fault which never settles cannot spin for four minutes.
        time.sleep(0.3)
    return 0


if __name__ == "__main__":
    sys.exit(main())
