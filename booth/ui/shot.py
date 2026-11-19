"""Full screen for the test shot and for calibration.

Whoever sets the box up is standing at the screen - directly under the camera
and in the wrong light. So first a notice with a start button, then three
seconds to walk across, and only then the measurement or the shutter.
Everything is large, because it is read from two metres away.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme
from .widgets import Picture

COUNTDOWN_S = 3
#: Calibration normally takes about five seconds. If nothing settles it can be
#: up to forty - with no running display that would look like a crash.
#: Measured on the booth at 11.7 seconds without the light search, matching
#: the capture to the preview included. The limit is for the case where a step
#: never settles.
CALIBRATE_LIMIT_S = 75

STYLE = """
QLabel { color: #F2F4F7; background: transparent; font-family: "DejaVu Sans"; }
QLabel#title { font-size: 44px; font-weight: 600; }
QLabel#hint { font-size: 26px; color: #C9CDD4; }
QLabel#count { font-size: 300px; font-weight: 700; }
QLabel#busy { font-size: 44px; font-weight: 500; }
QLabel#clock { font-size: 22px; color: #8A9099; }
QLabel#verdict { font-size: 38px; font-weight: 600; }
QLabel#detail { font-size: 21px; color: #C9CDD4; }
QLabel#values { font-family: "DejaVu Sans Mono"; font-size: 17px; color: #8A9099; }
QPushButton { font-family: "DejaVu Sans"; font-size: 22px; border-radius: 10px; padding: 18px 34px; }
QPushButton#go { background: #FFFFFF; color: #111827; border: 0; font-weight: 600; }
QPushButton#go:pressed { background: #D1D5DB; }
QPushButton#quiet { background: #23262B; color: #E6E8EC; border: 1px solid #3A3F47; }
QPushButton#quiet:pressed { background: #30343A; }
"""


def fraction(us: float | None) -> str:
    if not us:
        return "?"
    n = round(1_000_000 / us)
    return f"1/{n} s" if n >= 1 else f"{us / 1000:.0f} ms"


class _Bridge(QObject):
    done = Signal(dict)


#: Width of the wrapped text fields on the stage.
WRAP_W = 1100


class ShotScreen(QWidget):
    def __init__(self, parent: QWidget, backend, on_close: Callable[[], None],
                 on_calibrated: Callable[[str], None]) -> None:
        super().__init__(parent)
        self.setGeometry(0, 0, theme.STAGE_W, theme.STAGE_H)
        self.setStyleSheet(STYLE)
        self.backend = backend
        self.on_close = on_close
        self.on_calibrated = on_calibrated
        self.mode = "photo"
        self.running = False
        self.bridge = _Bridge()
        self.bridge.done.connect(self._done)

        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(60, 40, 60, 40)
        self.column.setSpacing(22)
        self.column.addStretch(1)
        self.title = self._label("title")
        self.hint = self._label("hint", wrap=True)
        self.count = self._label("count")
        self.busy = self._label("busy", wrap=True)
        self.clock = self._label("clock")
        self.picture = Picture(self, radius=10, cover=False, shadow_alpha=0)
        self.picture.setFixedSize(900, 600)
        self.picture.setParent(self)
        self.verdict = self._label("verdict", wrap=True)
        self.detail = self._label("detail", wrap=True)
        # No wrapping, one line per value: wrapped text in this column
        # wurde abgeschnitten.
        self.values = self._label("values")
        for w in (self.title, self.hint, self.count, self.busy, self.clock):
            self.column.addWidget(w, 0, Qt.AlignmentFlag.AlignHCenter)
        self.column.addWidget(self.picture, 0, Qt.AlignmentFlag.AlignHCenter)
        for w in (self.verdict, self.detail, self.values):
            self.column.addWidget(w, 0, Qt.AlignmentFlag.AlignHCenter)

        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(14)
        self.go = self._button("Start", "go", self._start)
        self.again = self._button("Noch eins", "go", self._start)
        self.close_btn = self._button("Schließen", "quiet", self.close_screen)
        self.revert = self._button("Altes Licht behalten", "quiet", self._licht_zurueck)
        self.buttons.addStretch(1)
        for b in (self.go, self.again, self.revert, self.close_btn):
            self.buttons.addWidget(b)
        self.buttons.addStretch(1)
        self.column.addLayout(self.buttons)
        self.column.addStretch(1)

        self.tick = QTimer(self)
        self.tick.timeout.connect(self._tick)
        self.left = 0
        self.started = 0.0
        #: The value that "Altes Licht behalten" puts back.
        self._licht_vorher: float | None = None
        #: Search for the light on the next calibration? Only reverting turns
        #: this off, so that the reverted value is not changed straight back.
        self._licht_suchen = True
        self.hide()

    def _label(self, name: str, wrap: bool = False) -> QLabel:
        lab = QLabel(self)
        lab.setObjectName(name)
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setWordWrap(wrap)
        if wrap:
            # A fixed width: otherwise the layout picks the smallest it can
            # and wraps every other word.
            lab.setFixedWidth(WRAP_W)
        return lab

    def _say(self, lab: QLabel, text: str) -> None:
        """Put text into a wrapped field - and work out the height with it.

        A word-wrapping QLabel often reports the height of a single line to the
        vertical layout; the rest is cut off and overlaps the field above. That
        is exactly how "Automatisch einmessen" came to sit half over its own
        help text. The width is fixed, so the height can be computed rather
        than guessed.
        """
        lab.setText(text)
        if not lab.wordWrap():
            return
        # Let Qt do the arithmetic, not QFontMetrics(lab.font()): the font
        # size comes from the stylesheet and is not in font(). Computed by
        # hand it came out too small, and the text was still cut off - just
        # less obviously.
        lab.ensurePolished()
        hoehe = lab.heightForWidth(WRAP_W)
        if hoehe > 0:
            lab.setMinimumHeight(hoehe + 8)

    def _button(self, text: str, name: str, on_click) -> QPushButton:
        btn = QPushButton(text, self)
        btn.setObjectName(name)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.clicked.connect(lambda _=False: on_click())
        return btn

    def _show_only(self, *widgets: QWidget) -> None:
        for w in (self.title, self.hint, self.count, self.busy, self.clock, self.picture,
                  self.verdict, self.detail, self.values, self.go, self.again,
                  self.revert, self.close_btn):
            w.setVisible(w in widgets)

    # -- sequence --------------------------------------------------------------------
    def open(self, mode: str) -> None:
        self.mode = mode
        self.title.setText("Testfoto" if mode == "photo" else "Automatisch einmessen")
        self._say(
            self.hint,
            "Stell dich dorthin, wo später die Gäste stehen. Nach dem Start zählt die Box "
            "drei Sekunden herunter und löst dann mit dem vollen Aufnahmelicht aus."
            if mode == "photo" else
            "Stell dich dorthin, wo später die Gäste stehen. Nach dem Start zählt die Box "
            "drei Sekunden herunter und misst dann Belichtung, Weißabgleich und Fokus, mit "
            "dem vollen Aufnahmelicht. Das dauert etwa eine halbe Minute, bitte still stehen "
            "bleiben.")
        self._show_only(self.title, self.hint, self.go, self.close_btn)
        self.raise_()
        self.show()

    def close_screen(self) -> None:
        if self.running:
            return
        self.tick.stop()
        self.hide()
        self.on_close()

    def _start(self) -> None:
        if self.running:
            return
        self.running = True
        self.left = COUNTDOWN_S
        self.count.setText(str(self.left))
        self._say(self.busy, "")
        self._show_only(self.count)
        if self.mode == "photo":
            # For a test shot the sequence does its own counting and switches
            # the light as it goes; it starts straight away.
            self._run(lambda: self.backend.test_shot(COUNTDOWN_S))
        self.started = time.monotonic()
        self.tick.start(200)

    def _tick(self) -> None:
        elapsed = time.monotonic() - self.started
        left = COUNTDOWN_S - int(elapsed)
        if left > 0:
            self.count.setText(str(left))
            return
        if self.busy.isHidden():
            if self.mode == "photo":
                self._say(self.busy, "Moment …")
            else:
                self._say(self.busy, "Wird eingemessen, bitte still stehen bleiben …")
                # After a revert, once without the light search, or the booth
                # would set exactly what was just discarded.
                suchen = self._licht_suchen
                self._licht_suchen = True
                self._run(lambda: self.backend.calibrate(tune_light=suchen))
            self._show_only(self.busy, self.clock)
        waited = elapsed - COUNTDOWN_S
        self.clock.setText(f"{round(waited)} s")
        if self.mode == "calibrate" and waited > CALIBRATE_LIMIT_S:
            self.tick.stop()
            self.running = False
            self._failed(f"Keine Antwort nach {round(waited)} Sekunden. "
                         "Schau in die Meldungen, dort steht der Grund.")

    def _run(self, work: Callable[[], dict[str, Any]]) -> None:
        # Never on the UI thread: the camera events run there too.
        def target() -> None:
            try:
                result = work()
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "error": str(exc) or exc.__class__.__name__}
            self.bridge.done.emit(result)

        threading.Thread(target=target, name=f"ui-{self.mode}", daemon=True).start()

    def _done(self, result: dict) -> None:
        if not self.running:
            return
        if self.mode == "photo" and time.monotonic() - self.started < COUNTDOWN_S:
            # The photo arrived before our own count finished - wait a moment.
            QTimer.singleShot(200, lambda: self._done(result))
            return
        self.tick.stop()
        self.running = False
        if not result or result.get("ok") is False:
            self._failed((result or {}).get("error") or "Fehlgeschlagen")
            return
        if self.mode == "photo":
            path = result.get("path")
            self.picture.set_path(Path(path) if path else None)
            self._show_only(self.picture, self.again, self.close_btn)
            return
        verdict, detail, values, level = self.judge(result)
        self._say(self.verdict, verdict)
        self.verdict.setStyleSheet({"good": "color:#86EFAC;", "bad": "color:#FCA5A5;"}.get(level, ""))
        self._say(self.detail, detail)
        self.values.setText(values)
        licht = result.get("light") or {}
        geaendert = bool(licht) and abs(licht.get("after", 0) - licht.get("before", 0)) > 0.005
        self._licht_vorher = licht.get("before") if geaendert else None
        # After calibrating, only close: "Noch eins" would otherwise start a
        # second measurement before anyone has even looked at the picture.
        # The one exception is the light: the box changed a setting by itself,
        # so there has to be a way back.
        if geaendert:
            self._show_only(self.verdict, self.detail, self.values,
                            self.revert, self.close_btn)
        else:
            self._show_only(self.verdict, self.detail, self.values, self.close_btn)
        self.on_calibrated(values)

    def _licht_zurueck(self) -> None:
        """Put the old capture light back - and measure again under it.

        Measuring again is not politeness, it is the only consistent thing to
        do: the exposure that was just stored was measured under the new
        brightness. Keeping one and dropping the other would leave the box
        calibrated for a light it no longer uses.
        """
        if self._licht_vorher is None:
            return
        self.backend.config.section("gpio")["light_capture_duty"] = self._licht_vorher
        self.backend.config.save()
        self._licht_vorher = None
        self._licht_suchen = False
        self._start()

    def _failed(self, text: str) -> None:
        self._say(self.verdict, text)
        self.verdict.setStyleSheet("color:#FCA5A5;")
        self._show_only(self.verdict, self.again, self.close_btn)

    def _lichtrat(self) -> str:
        """What the host should do when the exposure comes out too long.

        "Only a brighter lamp helps here" used to stand in this spot always,
        even when the capture light was set to 30 per cent. The booth measures
        under exactly that value, so that is the first thing to turn, not the
        lamp.
        """
        try:
            duty = float(self.backend.config.section("gpio")
                         .get("light_capture_duty", 1.0))
        except (TypeError, ValueError):
            duty = 1.0
        if duty < 0.9:
            return (f"Das Aufnahmelicht steht erst auf {round(duty * 100)} %, "
                    "dreh es höher und miss noch einmal ein.")
        return "Das Aufnahmelicht ist schon fast voll aufgedreht; hier hilft nur " \
               "eine hellere Leuchte oder ein kürzerer Abstand."

    def judge(self, result: dict[str, Any]) -> tuple[str, str, str, str]:
        e = result.get("exposure") or {}
        w = result.get("white_balance") or {}
        f = result.get("focus") or {}
        c = result.get("capture") or {}
        problems = []
        for name, part in (("Belichtung", e), ("Weißabgleich", w), ("Fokus", f),
                           ("Aufnahme", c)):
            if part.get("error"):
                problems.append(f"{name}: {part['error']}")
            elif part.get("note"):
                problems.append(str(part["note"]))
        us = e.get("exposure_time_us")
        if problems:
            verdict, level, detail = "Einmessen unvollständig", "bad", " ".join(problems)
        elif us is None:
            verdict, level, detail = "Eingemessen", "", ""
        elif us > 25000:
            verdict, level = "Eingemessen, aber zu dunkel", "bad"
            detail = (f"Bei {fraction(us)} verwischt jeder, der sich bewegt. "
                      + self._lichtrat())
        elif us > 12000:
            verdict, level = "Eingemessen, Licht ist knapp", ""
            detail = (f"Bei {fraction(us)} reicht es für ruhige Posen, nicht für "
                      "Bewegung. " + self._lichtrat())
        else:
            verdict, level = "Passt, die Box ist eingemessen", "good"
            detail = f"Bei {fraction(us)} wird Bewegung eingefroren."
        values = []
        if e.get("lux") is not None:
            values.append(f"Helligkeit {e['lux']} lx")
        if us is not None:
            values.append(f"Verschlusszeit {fraction(us)}")
        if e.get("analogue_gain") is not None:
            values.append(f"Verstärkung {e['analogue_gain']}")
        if w.get("colour_gain_red") is not None:
            values.append(f"Weißabgleich R {w['colour_gain_red']} / B {w.get('colour_gain_blue')}")
        if f.get("distance_m") is not None:
            values.append(f"Scharf auf {f['distance_m']} m")
        if c.get("gain_factor"):
            # The one line that answers "why is the photo darker than the
            # preview". Close to 100 percent is right; far below it means the
            # light was not enough even at full amplification.
            values.append("Foto wie Vorschau ({} %)".format(
                round(float(c.get("ratio", 0)) * 100)))
        licht = result.get("light") or {}
        if licht and abs(licht.get("after", 0) - licht.get("before", 0)) > 0.005:
            values.append("Aufnahmelicht {} → {} %".format(
                round(licht["before"] * 100), round(licht["after"] * 100)))
        lines = [" · ".join(values[i:i + 3]) for i in range(0, len(values), 3)]
        return verdict, detail, "\n".join(lines), level

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0B0C0E"))
        p.end()
