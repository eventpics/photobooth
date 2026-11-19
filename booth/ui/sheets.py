"""Panels over the start screen: status, modelling light, enlarged picture.

Each sits on a dimmed surface covering the whole stage. A tap beside it closes
it again - the same gesture as on the earlier web interface.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import theme
from .widgets import Button, Panel, Picture, SvgView, Label, place, put, qr_svg

SHADOW = QColor(60, 50, 35)


class Overlay(QWidget):
    """The dimmed area. A tap on it, but not on the content, closes."""

    closed = Signal()

    def __init__(self, parent: QWidget, dim: float) -> None:
        super().__init__(parent)
        self.dim = dim
        place(self, 0, 0, theme.STAGE_W, theme.STAGE_H)
        self.hide()

    def open(self) -> None:
        self.raise_()
        self.show()

    def close_overlay(self) -> None:
        if self.isVisible():
            self.hide()
            self.closed.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        # On release, not on press: otherwise the rest of the touch would be
        # delivered to whatever lies under the panel once it has closed.
        if self.childAt(event.position().toPoint()) is None:
            self.close_overlay()
        event.accept()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(30, 25, 18, round(255 * self.dim)))
        p.end()


class Card(QWidget):
    """Weisser Kasten mit weichem Schatten, faengt Beruehrungen ab."""

    def __init__(self, parent: QWidget, radius: float = 12) -> None:
        super().__init__(parent)
        self.radius = radius

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        event.accept()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(theme.LINE, 1))
        p.setBrush(theme.INK_2)
        p.drawRoundedRect(rect, self.radius, self.radius)
        p.end()


# -- state -----------------------------------------------------------------------------
LEVEL_COLOUR = {"ok": theme.OK, "warn": theme.WARN, "bad": theme.ERR, "": theme.FAINT}
#: The lettering of the value. Amber means "missing" and should catch the eye
#: without alarming - red is kept for what actually stops the box.
VALUE_COLOUR = {"bad": theme.ERR_INK, "warn": theme.WARN_INK}


def level(value: float | None, warn: float, bad: float) -> str:
    if value is None:
        return ""
    return "bad" if value >= bad else "warn" if value >= warn else "ok"


def uptime_text(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    h = int(seconds // 3600)
    m = round((seconds % 3600) / 60)
    return f"{h} h {m} min" if h > 0 else f"{m} min"


def clock_text(system: dict[str, Any]) -> str:
    """The clock is always shown next to its ceiling.

    The Pi throttles itself when it gets too hot or is fed too little power.
    The number only means something beside the figure it could have been.
    """
    mhz, top = system.get("cpu_mhz"), system.get("cpu_mhz_max")
    if not mhz:
        return ""
    if not top:
        return f"Takt {mhz} MHz"
    return f"Takt {mhz} von {top} MHz" + (", gedrosselt" if mhz < top * 0.9 else "")


def seit_text(stempel: Any) -> str:
    """How long the present state has been the case."""
    try:
        seit = time.time() - float(stempel or 0)
    except (TypeError, ValueError):
        return ""
    if not stempel or seit < 0:
        return ""
    if seit < 90:
        return f"seit {round(seit)} s"
    if seit < 5400:
        return f"seit {round(seit / 60)} min"
    return f"seit {round(seit / 3600, 1)} h".replace(".", ",")


def status_rows(status: dict[str, Any]) -> dict[str, Any]:
    """Every value of the status sheet, ready to be drawn."""
    system = status.get("system") or {}
    usb = status.get("usb") or {}
    cards = []
    ok = bool(status.get("camera_ok"))
    light = status.get("light") or {}
    lux, calibrated = light.get("lux"), light.get("calibrated_lux")
    too_bright = bool(ok and not light.get("auto") and lux and calibrated and lux > 3 * calibrated)
    if too_bright:
        cards.append(("Kamera", "warn", "zu hell", "neu einmessen"))
    else:
        cards.append(("Kamera", "ok" if ok else "bad", "bereit" if ok else "fehlt",
                      "Livebild läuft" if ok else "kein Bild"))
    present, pending = bool(usb.get("present")), usb.get("pending") or 0
    angesteckt = bool(usb.get("attached"))
    # Three states, not two. Red, not amber, when nothing is there: with no
    # stick the box takes no pictures at all, which is what separates it from
    # printer, lamp and network. But a stick that is plugged in and not yet
    # mounted is a fourth of a minute of patience, not a fault - at power-on
    # the udev rule needs its time, and saying "missing" there is a lie.
    if present:
        stufe = "warn" if pending else "ok"
        wert = f"{pending} warten" if pending else "bereit"
        klein = (f"{usb.get('free_gb')} GB frei" if usb.get("free_gb") is not None
                 else "eingebunden")
    elif angesteckt:
        stufe, wert, klein = "warn", "wird eingebunden", "steckt, noch nicht bereit"
    else:
        stufe, wert, klein = "bad", "fehlt", "nicht angesteckt"
    cards.append(("USB-Stick", stufe, wert, klein))
    # The printer. CUPS keeps a queue forever, so "configured" says nothing
    # about whether a device is on the end of the cable. Both are shown apart.
    drucker = status.get("printer") or {}
    if not drucker.get("queue"):
        cards.append(("Drucker", "warn", "keiner", "nicht eingerichtet"))
    elif drucker.get("attached") is False:
        cards.append(("Drucker", "warn", "kein Gerät", "Kabel prüfen"))
    elif drucker.get("attached") is None:
        cards.append(("Drucker", "ok", "bereit", "über Netzwerk"))
    else:
        cards.append(("Drucker", "ok", "bereit", "angesteckt"))

    # The lamp, but only when it hangs off a link that can actually drop. A
    # wire on a MOSFET reports nothing back, and a tile that always says "ok"
    # for it would be a lie.
    lampe = status.get("lamp") or {}
    if lampe.get("monitored"):
        seit = seit_text(lampe.get("since"))
        if lampe.get("connected"):
            cards.append(("Leuchte", "ok", "verbunden", seit))
        else:
            cards.append(("Leuchte", "warn", "getrennt", seit))

    # The network. The box shoots, prints and writes to the stick without it;
    # only the uploading waits. Hence amber, never red.
    netz = status.get("network") or {}
    if not netz.get("up"):
        cards.append(("Netz", "warn", "getrennt", "kein Kabel, kein WLAN"))
    elif netz.get("online") is False:
        cards.append(("Netz", "warn", netz.get("kind") or "verbunden",
                      "ohne Weg nach draußen"))
    else:
        art = netz.get("kind") or "verbunden"
        cards.append(("Netz", "ok", art,
                      netz.get("ssid") or netz.get("device") or ""))

    # The way into the gallery. With no key nothing uploads, but the pictures
    # are safe regardless - they are on the stick.
    ep = status.get("eventpics") or {}
    warteschlange = (ep.get("queue") or {})
    offen = (warteschlange.get("pending") or 0) + (warteschlange.get("failed") or 0)
    if not ep.get("configured"):
        cards.append(("EventPics", "warn", "kein Schlüssel", "nicht eingerichtet"))
    elif not ep.get("enabled"):
        cards.append(("EventPics", "warn", "aus", "Hochladen abgeschaltet"))
    elif offen:
        cards.append(("EventPics", "warn", f"{offen} warten",
                      ep.get("event_title") or "noch nicht hochgeladen"))
    else:
        cards.append(("EventPics", "ok", "verbunden",
                      ep.get("event_title") or "bereit"))

    rings = []
    t = system.get("temperature_c")
    rings.append(("Temperatur", None if t is None else (t - 30) / 55,
                  "-" if t is None else f"{round(t)}°", level(t, 70, 80), "Warnung ab 70 °C"))
    ram = system.get("memory_used_percent")
    rings.append(("Arbeitsspeicher", None if ram is None else ram / 100,
                  "-" if ram is None else f"{round(ram)}%", level(ram, 80, 90),
                  f"{system.get('memory_used_mb')} von {system.get('memory_total_mb')} MB"
                  if system.get("memory_used_mb") is not None else ""))
    cpu = system.get("cpu_percent")
    rings.append(("Prozessor", None if cpu is None else cpu / 100,
                  "-" if cpu is None else f"{round(cpu)}%", level(cpu, 85, 96), clock_text(system)))

    def used(free, total):
        # The bar shows the USED share: full means "getting tight", the same
        # way round as the rings.
        return max(0.0, (total - free) / total) if (free is not None and total) else None

    bars = []
    free, total = system.get("disk_free_gb"), system.get("disk_total_gb")
    bars.append(("Speicherkarte", used(free, total), "-" if free is None else f"{free} GB frei",
                 "" if free is None else "bad" if free < 0.5 else "warn" if free < 2 else "ok"))
    bars.append(("USB-Stick", used(usb.get("free_gb"), usb.get("total_gb")),
                 (f"{usb.get('free_gb')} von {usb.get('total_gb')} GB frei"
                  if usb.get("free_gb") is not None else "angesteckt") if present
                 else "nicht angesteckt",
                 "ok" if present else "warn"))

    levels = [c[1] for c in cards] + [r[3] for r in rings] + [b[3] for b in bars]
    worst = "bad" if "bad" in levels else "warn" if "warn" in levels else "ok"
    swap = system.get("swap_used_mb")
    return {"cards": cards, "rings": rings, "bars": bars, "overall": worst,
            "footer": f"Läuft seit {uptime_text(system.get('uptime_s'))}"
                      + (f" · Auslagerung {swap} MB" if swap else "")}


def overall(status: dict[str, Any]) -> str:
    return status_rows(status)["overall"] if status else "warn"


OVERALL_TEXT = {"ok": "Alles in Ordnung", "warn": "Etwas beachten", "bad": "Störung"}
def overall_style(level: str) -> tuple[QColor, QColor]:
    """Fill and lettering of the verdict pill, derived from the palette.

    These used to be three hand-mixed pairs. They cannot stay hand-mixed once
    the background is a setting: #E8F3E4 on a dark scheme is a glowing white
    blob, and #356B2C on it is unreadable.
    """
    farbe = LEVEL_COLOUR.get(level, theme.FAINT)
    tinte = {"ok": theme.OK_INK, "warn": theme.WARN_INK,
             "bad": theme.ERR_INK}.get(level, theme.DIM)
    return theme.mix(theme.INK_2, farbe, 0.16), tinte


class StatusCard(Card):
    """State as rings and bars: one second to see whether anything is stuck."""

    W = 660
    PAD_X, PAD_Y = 18, 16
    GAP = 10
    KARTEN_PRO_REIHE = 3
    KARTE_H = 82

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.rows: dict[str, Any] = status_rows({})
        self.resize(self.W, self._height())

    def set_status(self, status: dict[str, Any]) -> None:
        self.rows = status_rows(status)
        # The lamp tile comes and goes with how the lamp is wired, and with
        # it the number of rows. The card grows to match.
        hoehe = self._height()
        if hoehe != self.height():
            self.resize(self.W, hoehe)
        self.update()

    def _karten_h(self, anzahl: int) -> float:
        reihen = max(1, -(-anzahl // self.KARTEN_PRO_REIHE))
        return reihen * self.KARTE_H + (reihen - 1) * self.GAP

    def _height(self) -> int:
        return round(self.PAD_Y + 34 + 14 + self._karten_h(len(self.rows["cards"]))
                     + self.GAP + 168 + 2 * (self.GAP + 56)
                     + 12 + 20 + self.PAD_Y)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rows = self.rows
        x0, inner = self.PAD_X, self.W - 2 * self.PAD_X
        y = self.PAD_Y

        # Head: title and overall verdict
        p.setPen(theme.BONE)
        p.setFont(theme.font(19, weight=QFont.Weight.DemiBold))
        p.drawText(QRectF(x0, y, 300, 34), Qt.AlignmentFlag.AlignVCenter, "Zustand")
        worst = rows["overall"]
        text = OVERALL_TEXT[worst]
        f = theme.font(13.5, weight=QFont.Weight.DemiBold)
        pill_w = QFontMetricsF(f).horizontalAdvance(text) + 28 + 18
        pill = QRectF(x0 + inner - pill_w, y + 2, pill_w, 30)
        bg, fg = overall_style(worst)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(pill, 15, 15)
        p.setBrush(LEVEL_COLOUR[worst])
        p.drawEllipse(QRectF(pill.left() + 14, pill.center().y() - 5, 10, 10))
        p.setPen(fg)
        p.setFont(f)
        p.drawText(pill.adjusted(32, 0, -14, 0), Qt.AlignmentFlag.AlignVCenter, text)
        y += 34 + 14

        col_w = (inner - 2 * self.GAP) / 3
        # Tiles, three to a row. There are five or six depending on the
        # wiring - they all used to sit side by side, which made them so narrow
        # that "nicht eingerichtet" no longer fitted.
        karten = rows["cards"]
        karten_w = col_w
        for i, (title, lvl, value, small) in enumerate(karten):
            spalte, reihe = i % self.KARTEN_PRO_REIHE, i // self.KARTEN_PRO_REIHE
            box = QRectF(x0 + spalte * (karten_w + self.GAP),
                         y + reihe * (self.KARTE_H + self.GAP), karten_w, self.KARTE_H)
            self._tile(p, box)
            self._h4(p, box, title)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(LEVEL_COLOUR[lvl])
            p.drawEllipse(QRectF(box.left() + 13, box.top() + 11 + 23 + 5, 9, 9))
            p.setPen(VALUE_COLOUR.get(lvl, theme.BONE))
            p.setFont(theme.font(14, mono=True, bold=True))
            p.drawText(QRectF(box.left() + 29, box.top() + 11 + 23, karten_w - 40, 19),
                       Qt.AlignmentFlag.AlignVCenter, value)
            p.setPen(theme.FAINT)
            p.setFont(theme.font(11.5, mono=True))
            p.drawText(QRectF(box.left() + 13, box.top() + 11 + 23 + 22, karten_w - 20, 16),
                       Qt.AlignmentFlag.AlignVCenter, self._elide(small, karten_w - 26))
        y += self._karten_h(len(karten)) + self.GAP

        # Ringe
        for i, (title, fraction, centre, lvl, small) in enumerate(rows["rings"]):
            box = QRectF(x0 + i * (col_w + self.GAP), y, col_w, 168)
            self._tile(p, box)
            self._h4(p, box, title)
            size = 104
            ring = QRectF(box.center().x() - size / 2, box.top() + 11 + 23, size, size)
            stroke = size * 9 / 120
            r = ring.adjusted(stroke / 2 + size * 7.5 / 120, stroke / 2 + size * 7.5 / 120,
                              -stroke / 2 - size * 7.5 / 120, -stroke / 2 - size * 7.5 / 120)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(theme.LINE, stroke))
            p.drawEllipse(r)
            a = max(0.0, min(1.0, fraction or 0.0))
            if a > 0:
                p.setPen(QPen(LEVEL_COLOUR[lvl or "ok"], stroke, Qt.PenStyle.SolidLine,
                              Qt.PenCapStyle.RoundCap))
                p.drawArc(r, 90 * 16, -round(a * 360 * 16))
            p.setPen(theme.BONE)
            p.setFont(theme.font(19 * size / 120, mono=True, bold=True))
            p.drawText(ring, Qt.AlignmentFlag.AlignCenter, centre)
            p.setPen(theme.FAINT)
            p.setFont(theme.font(11.5, mono=True))
            p.drawText(QRectF(box.left() + 6, ring.bottom() + 2, col_w - 12, 16),
                       Qt.AlignmentFlag.AlignCenter, self._elide(small, col_w - 12))
        y += 168

        # Balken
        for title, fraction, text, lvl in rows["bars"]:
            y += self.GAP
            box = QRectF(x0, y, inner, 56)
            self._tile(p, box)
            p.setPen(theme.BONE)
            p.setFont(theme.font(13))
            p.drawText(QRectF(box.left() + 13, box.top() + 9, 250, 20),
                       Qt.AlignmentFlag.AlignVCenter, title)
            p.setFont(theme.font(13.5, mono=True, bold=True))
            p.drawText(QRectF(box.left() + 13, box.top() + 9, inner - 26, 20),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, text)
            track = QRectF(box.left() + 13, box.top() + 36, inner - 26, 9)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.LINE)
            p.drawRoundedRect(track, 4.5, 4.5)
            a = max(0.0, min(1.0, fraction or 0.0))
            if a > 0:
                p.setBrush(LEVEL_COLOUR[lvl or "ok"])
                p.drawRoundedRect(QRectF(track.left(), track.top(), max(9, track.width() * a), 9),
                                  4.5, 4.5)
            y += 56

        p.setPen(theme.DIM)
        p.setFont(theme.font(13.5))
        p.drawText(QRectF(x0, y + 12, inner, 20), Qt.AlignmentFlag.AlignVCenter, rows["footer"])
        p.end()

    @staticmethod
    def _tile(p: QPainter, box: QRectF) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.INK_3)
        p.drawRoundedRect(box, 11, 11)

    @staticmethod
    def _h4(p: QPainter, box: QRectF, title: str) -> None:
        p.setPen(theme.DIM)
        p.setFont(theme.font(12.5, weight=QFont.Weight.DemiBold))
        p.drawText(QRectF(box.left() + 13, box.top() + 11, box.width() - 26, 16),
                   Qt.AlignmentFlag.AlignVCenter, title)

    @staticmethod
    def _elide(text: str, width: float) -> str:
        fm = QFontMetricsF(theme.font(11.5, mono=True))
        return fm.elidedText(text, Qt.TextElideMode.ElideRight, width)


# -- modelling light -------------------------------------------------------------------
class Slider(QWidget):
    """A slider a finger can actually hit."""

    moved = Signal(int)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.value = 0

    def set_value(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        if value != self.value:
            self.value = value
            self.update()

    def _from_x(self, x: float) -> int:
        knob = self.height() / 2
        span = max(1.0, self.width() - 2 * knob)
        return round(max(0.0, min(1.0, (x - knob) / span)) * 100)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag(event)

    def _drag(self, event: QMouseEvent) -> None:
        value = self._from_x(event.position().x())
        event.accept()
        if value != self.value:
            self.value = value
            self.update()
            self.moved.emit(value)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        knob = h / 2
        cy = h / 2
        track = QRectF(knob, cy - 4, self.width() - 2 * knob, 8)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.LINE)
        p.drawRoundedRect(track, 4, 4)
        x = track.left() + track.width() * self.value / 100
        p.setBrush(theme.AMBER)
        p.drawRoundedRect(QRectF(track.left(), track.top(), x - track.left(), 8), 4, 4)
        r = h * 0.36
        p.setBrush(theme.AMBER)
        p.drawEllipse(QRectF(x - r, cy - r, 2 * r, 2 * r))
        p.setBrush(theme.INK_2)
        p.drawEllipse(QRectF(x - r * 0.45, cy - r * 0.45, r * 0.9, r * 0.9))
        p.end()


class LightCard(Card):
    """The modelling light, under the guests' fingers.

    Brightness only. Colour temperature stood here once and went away again:
    this sheet is reachable by guests, and the brightness of the modelling
    light has no effect on the picture. The colour does, because the white
    balance is calibrated against it. Anyone turning it in passing would tint
    every picture of the evening without a soul noticing. It therefore sits in
    the settings, behind the PIN.
    """

    W = 420
    HINT = ("Das Licht zwischen den Aufnahmen. Für die Aufnahme selbst schaltet die Box "
            "auf das Aufnahmelicht aus den Einstellungen um.")

    def __init__(self, parent: QWidget, on_change: Callable[[int], None]) -> None:
        super().__init__(parent)
        inner = self.W - 36
        self.title = Label(self, theme.font(16, weight=QFont.Weight.DemiBold), theme.BONE,
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.title.set_text("Einstelllicht")
        place(self.title, 18, 16, inner, 24)
        hint_font = theme.font(13.5)
        hint_h = QFontMetricsF(hint_font).boundingRect(
            QRectF(0, 0, inner, 400), int(Qt.TextFlag.TextWordWrap), self.HINT).height()
        self.hint = Label(self, hint_font, theme.DIM,
                          Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.hint.set_text(self.HINT)
        place(self.hint, 18, 50, inner, hint_h + 2)
        y = 50 + hint_h + 14
        self.big = Label(self, theme.font(34, mono=True, weight=QFont.Weight.DemiBold), theme.BONE)
        place(self.big, 18, y, inner, 46)
        y += 46 + 8
        self.slider = Slider(self)
        place(self.slider, 18 - 6, y, inner + 12, 56)
        self.slider.moved.connect(self._moved)
        self.on_change = on_change
        self.resize(self.W, round(y + 56 + 14))

    def set_value(self, percent: int) -> None:
        self.big.set_text(f"{percent} %")
        self.slider.set_value(percent)

    def _moved(self, value: int) -> None:
        self.big.set_text(f"{value} %")
        self.on_change(value)


# -- picture full size ----------------------------------------------------------------
class PictureCard(Card):
    """One gallery picture full size, with QR code and printing."""

    MAX_W, MAX_H = 1200, 780

    def __init__(self, parent: QWidget, on_print: Callable[[Path], None]) -> None:
        super().__init__(parent, radius=14)
        self.path: Path | None = None
        self.picture = Picture(self, radius=8, cover=True, shadow_alpha=0)
        self.qr_panel = Panel(self)
        self.qr = SvgView(self.qr_panel)
        place(self.qr, 14, 14, 190, 190)
        self.qr_text = Label(self.qr_panel, theme.font(16), theme.DIM)
        self.qr_text.set_text("Scannen und\naufs Handy holen")
        place(self.qr_text, 0, 212, 218, 46)
        self.print_btn = Button(self, shape="pill", bg=theme.SAGE, fg=theme.SAGE_TEXT, border=None,
                                font=theme.font(30, bold=True), text="Drucken",
                                subfont=theme.font(15, weight=QFont.Weight.DemiBold),
                                shadow=None, on_click=lambda: self.path and on_print(self.path))

    def show_picture(self, path: Path, aspect: float, link: str | None,
                     can_print: bool, reason: str) -> None:
        self.path = path
        if self.MAX_W / self.MAX_H > aspect:
            img_w, img_h = self.MAX_H * aspect, self.MAX_H
        else:
            img_w, img_h = self.MAX_W, self.MAX_W / aspect
        svg = qr_svg(link) if link else None
        qr_w = 218 + 16 if svg else 0

        self.print_btn.set_text("Drucken", "" if can_print else reason)
        self.print_btn.setEnabled(can_print)
        self.print_btn.bg = theme.SAGE if can_print else theme.INK_3
        self.print_btn.fg = theme.SAGE_TEXT if can_print else theme.FAINT
        pb = self.print_btn.natural_size(60, 22 if can_print else 14)
        row_w, row_h = pb.width(), pb.height()

        w = max(img_w + qr_w, row_w) + 32
        h = 16 + img_h + 12 + row_h + 16
        self.resize(round(w), round(h))
        left = (w - img_w - qr_w) / 2
        self.picture.set_path(path)
        place(self.picture, left, 16, img_w, img_h)
        if svg:
            self.qr.set_svg(svg)
            place(self.qr_panel, left + img_w + 16, 16 + img_h / 2 - 135, 218, 270)
            self.qr_panel.show()
        else:
            self.qr_panel.hide()
        x = (w - row_w) / 2
        cy = 16 + img_h + 12 + row_h / 2
        put(self.print_btn, x, cy - pb.height() / 2, pb.width(), pb.height())
