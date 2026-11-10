"""On-screen keyboard for text and numbers.

There is no keyboard at the box. The web interface therefore only had detours
for titles and keys - a phone, a USB stick. Natively you type on the screen.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import theme

# The same live colour objects as everywhere else. This module and the PIN
# screen used to carry a third palette of their own - a cool grey one - which
# meant both stayed bright white while the rest of the box went dark.
BG = theme.INK
CARD = theme.INK_2
LINE = theme.LINE
LINE_2 = theme.LINE_2
FG = theme.BONE
MUTED = theme.DIM
#: The emphasis colour here is the text colour, not the primary: a keyboard of
#: amber keys would shout louder than anything it is used to type.
ACCENT = theme.BONE
FOCUS = theme.AMBER

ROWS_LOWER = ["1234567890ß", "qwertzuiopü", "asdfghjklöä", "yxcvbnm,.-"]
ROWS_UPPER = ["!\"§$%&/()=?", "QWERTZUIOPÜ", "ASDFGHJKLÖÄ", "YXCVBNM;:_"]
ROWS_SYMBOL = ["1234567890@", "#+*'&/()[]\\", "<>{}|~^°€£", "!?;:_\"…–"]
NUMPAD = ["789", "456", "123"]


class _Key:
    def __init__(self, rect: QRectF, label: str, action: str) -> None:
        self.rect = rect
        self.label = label
        self.action = action


class KeyboardOverlay(QWidget):
    """Covers the whole stage: the field at the top, the keys below."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setGeometry(0, 0, theme.STAGE_W, theme.STAGE_H)
        self.title = ""
        self.hint = ""
        self.text = ""
        self.numeric = False
        self.decimal = False
        self.secret = False
        self.max_len = 200
        self.mode = "lower"
        self.keys: list[_Key] = []
        self.pressed: _Key | None = None
        self.on_done: Callable[[str], None] | None = None
        self.hide()

    # -- Oeffnen und Schliessen ----------------------------------------------------
    def ask_text(self, title: str, value: str, on_done: Callable[[str], None],
                 hint: str = "", secret: bool = False, max_len: int = 200) -> None:
        self.numeric, self.decimal, self.secret = False, False, secret
        self._open(title, value, on_done, hint, max_len)

    def ask_number(self, title: str, value: float | int | None, on_done: Callable[[str], None],
                   hint: str = "", decimal: bool = False) -> None:
        self.numeric, self.decimal, self.secret = True, decimal, False
        text = "" if value is None else (f"{value:g}".replace(".", ",") if decimal else str(int(value)))
        self._open(title, text, on_done, hint, 12)

    def _open(self, title: str, value: str, on_done, hint: str, max_len: int) -> None:
        self.title, self.hint, self.text = title, hint, value
        self.on_done, self.max_len = on_done, max_len
        self.mode = "lower"
        self._layout()
        self.raise_()
        self.show()
        self.update()

    def _finish(self, accept: bool) -> None:
        self.hide()
        callback, self.on_done = self.on_done, None
        if accept and callback is not None:
            callback(self.text.replace(",", ".") if self.numeric else self.text)

    # -- Tasten --------------------------------------------------------------------
    def _layout(self) -> None:
        self.keys = []
        if self.numeric:
            size, gap = 120, 14
            width = 3 * size + 2 * gap + gap + 220
            left = (theme.STAGE_W - width) / 2
            top = 470
            for r, row in enumerate(NUMPAD):
                for c, ch in enumerate(row):
                    self.keys.append(_Key(QRectF(left + c * (size + gap), top + r * (size + gap),
                                                 size, size), ch, "char"))
            y = top + 3 * (size + gap)
            if self.decimal:
                self.keys.append(_Key(QRectF(left, y, size, size), ",", "char"))
                self.keys.append(_Key(QRectF(left + size + gap, y, size, size), "0", "char"))
            else:
                self.keys.append(_Key(QRectF(left, y, 2 * size + gap, size), "0", "char"))
            self.keys.append(_Key(QRectF(left + 2 * (size + gap), y, size, size), "⌫", "back"))
            x = left + 3 * (size + gap) + gap
            self.keys.append(_Key(QRectF(x, top, 220, 2 * size + gap), "Übernehmen", "ok"))
            self.keys.append(_Key(QRectF(x, top + 2 * (size + gap), 220, 2 * size + gap),
                                  "Abbrechen", "cancel"))
            return

        rows = {"lower": ROWS_LOWER, "upper": ROWS_UPPER, "symbol": ROWS_SYMBOL}[self.mode]
        size, gap = 116, 12
        top = 430
        for r, row in enumerate(rows):
            width = len(row) * size + (len(row) - 1) * gap
            extra = 0
            if r == 3:
                extra = 2 * (180 + gap)
            left = (theme.STAGE_W - width - extra) / 2
            if r == 3:
                label = "⇧" if self.mode != "upper" else "⇩"
                self.keys.append(_Key(QRectF(left, top + r * (size + gap), 180, size), label,
                                      "shift"))
                left += 180 + gap
            for c, ch in enumerate(row):
                self.keys.append(_Key(QRectF(left + c * (size + gap), top + r * (size + gap),
                                             size, size), ch, "char"))
            if r == 3:
                x = left + width + gap
                self.keys.append(_Key(QRectF(x, top + r * (size + gap), 180, size), "⌫", "back"))
        y = top + 4 * (size + gap)
        full = 11 * size + 10 * gap
        left = (theme.STAGE_W - full) / 2
        self.keys.append(_Key(QRectF(left, y, 220, size), "?123" if self.mode != "symbol" else "abc",
                              "symbols"))
        self.keys.append(_Key(QRectF(left + 220 + gap, y, full - 2 * (220 + gap) - 280 - gap, size),
                              "Leerzeichen", "space"))
        self.keys.append(_Key(QRectF(left + full - 280 - gap - 220, y, 280, size), "Abbrechen",
                              "cancel"))
        self.keys.append(_Key(QRectF(left + full - 220, y, 220, size), "Übernehmen", "ok"))

    def _key_at(self, pos) -> _Key | None:
        for key in self.keys:
            if key.rect.contains(pos):
                return key
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.pressed = self._key_at(event.position())
        event.accept()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        key = self.pressed
        self.pressed = None
        event.accept()
        if key is None or not key.rect.contains(event.position()):
            self.update()
            return
        if key.action == "char":
            if len(self.text) < self.max_len:
                if self.numeric and key.label == "," and "," in self.text:
                    pass
                else:
                    self.text += key.label
            if self.mode == "upper":
                self.mode = "lower"
                self._layout()
        elif key.action == "back":
            self.text = self.text[:-1]
        elif key.action == "space":
            if len(self.text) < self.max_len:
                self.text += " "
        elif key.action == "shift":
            self.mode = "lower" if self.mode == "upper" else "upper"
            self._layout()
        elif key.action == "symbols":
            self.mode = "lower" if self.mode == "symbol" else "symbol"
            self._layout()
        elif key.action == "ok":
            self._finish(True)
            return
        elif key.action == "cancel":
            self._finish(False)
            return
        self.update()

    # -- Zeichnen ------------------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.fillRect(self.rect(), QColor(16, 24, 40, 150))
        panel = QRectF(90, 80, theme.STAGE_W - 180, theme.STAGE_H - 140)
        p.setPen(QPen(LINE, 1))
        p.setBrush(BG)
        p.drawRoundedRect(panel, 18, 18)

        p.setPen(FG)
        p.setFont(theme.font(30, weight=QFont.Weight.DemiBold))
        p.drawText(QRectF(panel.left() + 60, 130, panel.width() - 120, 44),
                   Qt.AlignmentFlag.AlignVCenter, self.title)
        if self.hint:
            p.setPen(MUTED)
            p.setFont(theme.font(20))
            p.drawText(QRectF(panel.left() + 60, 178, panel.width() - 120, 34),
                       Qt.AlignmentFlag.AlignVCenter, self.hint)

        field = QRectF(panel.left() + 60, 240, panel.width() - 120, 110)
        p.setPen(QPen(FOCUS, 3))
        p.setBrush(CARD)
        p.drawRoundedRect(field, 12, 12)
        shown = self.text
        font = theme.font(46, mono=self.secret or self.numeric)
        p.setFont(font)
        fm = QFontMetricsF(font)
        inner = field.adjusted(28, 0, -28, 0)
        while fm.horizontalAdvance(shown) > inner.width() - 20 and len(shown) > 1:
            shown = shown[1:]
        p.setPen(FG)
        p.drawText(inner, Qt.AlignmentFlag.AlignVCenter, shown)
        cursor_x = inner.left() + fm.horizontalAdvance(shown) + 4
        p.fillRect(QRectF(cursor_x, field.center().y() - 30, 3, 60), FOCUS)

        for key in self.keys:
            down = key is self.pressed
            special = key.action in ("ok",)
            muted = key.action in ("shift", "back", "symbols", "cancel")
            bg = ACCENT if special else (theme.PRESSED if muted else CARD)
            if down:
                bg = (theme.mix(ACCENT, BG, 0.18) if special
                      else theme.mix(BG, FG, 0.22))
            p.setPen(QPen(LINE_2 if not special else ACCENT, 1))
            p.setBrush(bg)
            p.drawRoundedRect(key.rect.adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
            p.setPen(theme.INK_2 if special else FG)
            if key.action == "char":
                p.setFont(theme.font(40 if not self.numeric else 50))
            elif key.label in ("⌫", "⇧", "⇩"):
                p.setFont(theme.font(44))
            else:
                p.setFont(theme.font(26, weight=QFont.Weight.DemiBold))
            p.drawText(key.rect, Qt.AlignmentFlag.AlignCenter, key.label)
        p.end()
