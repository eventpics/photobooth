"""Full screen for reading the EventPics key off a code.

The key is thirty-odd random characters. Nobody types that on a touchscreen,
so the box reads it off a code held up to its camera - and that only works if
whoever holds it can see what the camera sees. The first version took one
blind photograph with the booth's own settings: focused on the spot where the
guests stand, exposed for the room. A phone held up to the lens was a bright
blur in it, and all the screen ever said was that nothing had been found.

So: the live image is here, large, with the camera focusing by itself, and
every frame is looked at until something is found or the time is up.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme

log = logging.getLogger(__name__)

#: Long enough to fetch the phone and hold it still, short enough that a box
#: nobody is standing at does not keep the camera on close-up all evening.
LIMIT_S = 90.0

#: Between two attempts. One attempt costs the frame plus zbar, so this is
#: not a frame rate - it is the pause that keeps one core free for the live
#: image.
INTERVAL_MS = 350

STYLE = """
QLabel { color: #F2F4F7; background: transparent; font-family: "DejaVu Sans"; }
QLabel#title { font-size: 40px; font-weight: 600; }
QLabel#hint { font-size: 24px; color: #C9CDD4; }
QLabel#status { font-size: 24px; font-weight: 500; }
QPushButton { font-family: "DejaVu Sans"; font-size: 22px; border-radius: 10px;
              padding: 16px 32px; background: #23262B; color: #E6E8EC;
              border: 1px solid #3A3F47; }
QPushButton:pressed { background: #30343A; }
"""

#: 3:2 like the sensor, so the live image fills the slot without bars.
SLOT = (960, 640)

#: Width of the wrapped text on the stage. Fixed, because a wrapping label
#: left to itself picks the narrowest width it can get away with.
WRAP_W = 1100


class _Bridge(QObject):
    done = Signal(dict)


class ScanScreen(QWidget):
    def __init__(self, parent: QWidget, backend, on_close: Callable[[], None],
                 on_found: Callable[[dict], None]) -> None:
        super().__init__(parent)
        self.setGeometry(0, 0, theme.STAGE_W, theme.STAGE_H)
        self.setStyleSheet(STYLE)
        self.backend = backend
        self.on_close = on_close
        self.on_found = on_found
        self.running = False
        self.busy = False
        self.versuche = 0
        self.bridge = _Bridge()
        self.bridge.done.connect(self._result)

        column = QVBoxLayout(self)
        column.setContentsMargins(60, 40, 60, 40)
        column.setSpacing(18)
        column.addStretch(1)

        self.title = self._label("title", "QR-Code scannen")
        self.hint = self._label("hint", "", wrap=True)
        self._say(self.hint,
                  "Halte den Code mit dem Schlüssel etwa eine Handbreit bis "
                  "einen Arm weit vor die Kamera. Die Box stellt dabei selbst "
                  "scharf. Ein Code auf dem Telefon geht genauso gut wie einer "
                  "auf Papier.")
        self.slot = QWidget(self)
        self.slot.setFixedSize(*SLOT)
        self.status = self._label("status", "", wrap=True)

        column.addWidget(self.title, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addWidget(self.hint, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addWidget(self.slot, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addWidget(self.status, 0, Qt.AlignmentFlag.AlignHCenter)

        buttons = QHBoxLayout()
        buttons.setSpacing(14)
        buttons.addStretch(1)
        self.close_btn = QPushButton("Abbrechen", self)
        self.close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_btn.clicked.connect(lambda _=False: self.close_screen())
        buttons.addWidget(self.close_btn)
        buttons.addStretch(1)
        column.addLayout(buttons)
        column.addStretch(1)

        self.tick = QTimer(self)
        self.tick.timeout.connect(self._try_once)
        self.clock = QTimer(self)
        self.clock.setSingleShot(True)
        self.clock.timeout.connect(self._timed_out)
        self.hide()

    def _label(self, name: str, text: str, wrap: bool = False) -> QLabel:
        lab = QLabel(text, self)
        lab.setObjectName(name)
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setWordWrap(wrap)
        if wrap:
            lab.setFixedWidth(WRAP_W)
        return lab

    def _say(self, lab: QLabel, text: str) -> None:
        """Put text in, and give the label the height that text really needs.

        A wrapping QLabel reports a single line's height to the layout and
        the rest is cut off. On this screen that clipped the last line of the
        hint and laid it over the title. Qt does the arithmetic, not
        QFontMetrics: the font size comes from the stylesheet and is not in
        font().
        """
        lab.setText(text)
        if not lab.wordWrap():
            return
        lab.ensurePolished()
        hoehe = lab.heightForWidth(WRAP_W)
        if hoehe > 0:
            lab.setMinimumHeight(hoehe + 8)

    # -- lifecycle ---------------------------------------------------------
    def open(self) -> None:
        self.versuche = 0
        self._say(self.status, "Die Kamera stellt scharf …")
        self.status.setStyleSheet("")
        self.close_btn.setText("Abbrechen")
        self.raise_()
        self.show()
        # The live image is lent, as it is to the camera page. There is only
        # one of it, and it goes back to the guest screen on the way out.
        fenster = self.window()
        if hasattr(fenster, "lend_preview"):
            fenster.lend_preview(self.slot)
        self.running = True
        self.backend.eventpics_scan_begin()
        # A moment for the autofocus before the first look, otherwise the
        # first attempts are spent on a blurred picture.
        self.tick.start(INTERVAL_MS)
        self.clock.start(int(LIMIT_S * 1000))

    def close_screen(self) -> None:
        self._stop()
        self.hide()
        fenster = self.window()
        if hasattr(fenster, "reclaim_preview"):
            fenster.reclaim_preview()
        self.on_close()

    def _stop(self) -> None:
        self.tick.stop()
        self.clock.stop()
        if self.running:
            self.running = False
            try:
                self.backend.eventpics_scan_end()
            except Exception:  # noqa: BLE001 - closing must not raise
                log.exception("Ending the close-up mode failed")

    # -- scanning ----------------------------------------------------------
    def _try_once(self) -> None:
        """One attempt, in the background.

        Never on the interface's thread: zbar takes a moment per frame, and
        the live image is drawn on this thread. Only one attempt at a time,
        or a slow one would be followed by a queue of them.
        """
        if self.busy or not self.running:
            return
        self.busy = True
        self.versuche += 1

        def work() -> None:
            try:
                result = self.backend.eventpics_scan_tick()
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "gefunden": False, "error": str(exc)}
            self.bridge.done.emit(result)

        threading.Thread(target=work, name="ui-scan", daemon=True).start()

    def _result(self, result: dict[str, Any]) -> None:
        self.busy = False
        if not self.running:
            return
        if result.get("ok"):
            self._stop()
            self._say(self.status, "Schlüssel übernommen.")
            self.status.setStyleSheet("color:#86EFAC;")
            self.close_btn.setText("Fertig")
            self.on_found(result)
            return
        fehler = result.get("error")
        if fehler and result.get("gefunden"):
            # A code was read, it simply was not a key. Saying so beats
            # leaving somebody holding up the wrong code for a minute.
            self._stop()
            self._say(self.status, str(fehler))
            self.status.setStyleSheet("color:#FCA5A5;")
            self.close_btn.setText("Schließen")
            return
        if fehler:
            self._stop()
            self._say(self.status, str(fehler))
            self.status.setStyleSheet("color:#FCA5A5;")
            self.close_btn.setText("Schließen")
            return
        self._say(self.status, "Es wird gesucht … %d Versuche" % self.versuche)

    def _timed_out(self) -> None:
        self._stop()
        self._say(self.status,
                  "Kein Code gefunden. Halte ihn ruhig und etwas näher, und achte "
                  "darauf, dass er im Livebild ganz zu sehen ist.")
        self.status.setStyleSheet("color:#FCA5A5;")
        self.close_btn.setText("Schließen")

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0B0C0E"))
        p.end()
