"""PIN entry in front of the settings.

A forgotten PIN is reset at the box with set-pin.sh. There is deliberately no
hint of that here, so the idea does not occur to a guest.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import theme
from .keyboard import ACCENT, BG, CARD, FG, LINE, LINE_2, MUTED

#: Red for a wrong PIN - the readable variant, so it works on a dark scheme too.
ERR = theme.ERR_INK
KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "⌫"]


class PinScreen(QWidget):
    def __init__(self, parent: QWidget, auth, on_success: Callable[[], None],
                 on_back: Callable[[], None]) -> None:
        super().__init__(parent)
        self.setGeometry(0, 0, theme.STAGE_W, theme.STAGE_H)
        self.auth = auth
        self.on_success = on_success
        self.on_back = on_back
        self.entered = ""
        self.error = ""
        self.pressed: str | None = None
        # The safe margin, like everywhere else - it used to sit 16 points
        # from the corner, closer than anything else on the box.
        self.back_rect = QRectF(theme.SAFE_MARGIN_PX, theme.SAFE_MARGIN_PX, 176, 64)
        width, height, gap = 150, 112, 16
        left = (theme.STAGE_W - (3 * width + 2 * gap)) / 2
        top = 360
        self.key_rects = {}
        for i, key in enumerate(KEYS):
            if key:
                r, c = divmod(i, 3)
                self.key_rects[key] = QRectF(left + c * (width + gap), top + r * (height + gap),
                                             width, height)
        self.lock_timer = QTimer(self)
        self.lock_timer.timeout.connect(self._refresh_lock)
        self.hide()

    def open(self) -> None:
        self.entered = ""
        self.error = ""
        self._refresh_lock()
        self.lock_timer.start(1000)
        self.raise_()
        self.show()
        self.update()

    def close_screen(self) -> None:
        self.lock_timer.stop()
        self.hide()

    def _refresh_lock(self) -> None:
        locked = self.auth.locked_for()
        if locked > 0:
            self.error = f"Gesperrt, noch {int(locked + 0.99)} Sekunden"
            self.update()
        elif self.error.startswith("Gesperrt"):
            self.error = ""
            self.update()

    def _hit(self, pos) -> str | None:
        if self.back_rect.contains(pos):
            return "back"
        for key, rect in self.key_rects.items():
            if rect.contains(pos):
                return key
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.pressed = self._hit(event.position())
        event.accept()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        key, self.pressed = self.pressed, None
        event.accept()
        if key is None or self._hit(event.position()) != key:
            self.update()
            return
        if key == "back":
            self.close_screen()
            self.on_back()
            return
        if key == "⌫":
            self.entered = self.entered[:-1]
        elif len(self.entered) < 4:
            self.entered += key
            if len(self.entered) == 4:
                self.update()
                QTimer.singleShot(120, self._submit)
        self.update()

    def _submit(self) -> None:
        result = self.auth.login(self.entered)
        self.entered = ""
        if result.get("ok"):
            self.error = ""
            self.close_screen()
            self.on_success()
            return
        self.error = result.get("error") or "Falsche PIN"
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.fillRect(self.rect(), BG)

        down = self.pressed == "back"
        p.setPen(QPen(LINE, 1))
        p.setBrush(theme.PRESSED if down else CARD)
        p.drawRoundedRect(self.back_rect, 10, 10)
        p.setPen(MUTED)
        p.setFont(theme.font(20))
        p.drawText(self.back_rect, Qt.AlignmentFlag.AlignCenter, "‹  Zurück")

        p.setPen(FG)
        p.setFont(theme.font(34, weight=QFont.Weight.DemiBold))
        p.drawText(QRectF(0, 150, theme.STAGE_W, 50), Qt.AlignmentFlag.AlignCenter, "Einstellungen")
        p.setPen(MUTED)
        p.setFont(theme.font(20))
        p.drawText(QRectF(0, 204, theme.STAGE_W, 34), Qt.AlignmentFlag.AlignCenter,
                   "Vierstellige PIN eingeben")

        dot, gap = 24, 22
        left = (theme.STAGE_W - (4 * dot + 3 * gap)) / 2
        for i in range(4):
            r = QRectF(left + i * (dot + gap), 278, dot, dot)
            if i < len(self.entered):
                p.setPen(QPen(ACCENT, 3))
                p.setBrush(ACCENT)
            else:
                p.setPen(QPen(LINE_2, 3))
                p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(r)

        for key, rect in self.key_rects.items():
            pressed = key == self.pressed
            p.setPen(QPen(LINE, 1))
            p.setBrush(theme.PRESSED if pressed else CARD)
            p.drawRoundedRect(rect, 14, 14)
            p.setPen(FG)
            p.setFont(theme.font(40 if key != "⌫" else 38, mono=key != "⌫"))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, key)

        if self.error:
            p.setPen(ERR)
            p.setFont(theme.font(22))
            bottom = max(r.bottom() for r in self.key_rects.values())
            p.drawText(QRectF(0, bottom + 30, theme.STAGE_W, 40), Qt.AlignmentFlag.AlignCenter,
                       self.error)
        p.end()
