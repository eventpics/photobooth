"""Input widgets of the settings area, built for a fingertip.

Numbers get plus and minus and open a keypad when tapped, text fields open the
on-screen keyboard, choices open a large list. None of it needs a real
keyboard.
"""

from __future__ import annotations

import math
from typing import Any, Callable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from . import theme

# The settings screen used to carry its own palette - a cool grey one, while
# the guest screen was warm. Two palettes in one program means the second one
# is always the one nobody updates. These are the same live objects as in
# theme, so a scheme change reaches here too.
CARD = theme.INK_2
LINE = theme.LINE
LINE_2 = theme.LINE_2
FG = theme.BONE
MUTED = theme.DIM
FAINT = theme.FAINT
#: The emphasis colour of the settings screen. Deliberately the text colour and
#: not the primary: the settings are a workbench, and a wall of amber buttons
#: there competes with the one amber button that matters, START.
ACCENT = theme.BONE
OK = theme.OK_INK
ERR = theme.ERR_INK


def style() -> str:
    """The settings screen stylesheet, built from the palette.

    A function and not a constant, because the colours are only known once a
    scheme has been applied, and they change again when someone picks another
    one.
    """
    t = theme
    tint = t.mix(t.INK_2, t.AMBER, 0.12)   # the marked row in a list
    return f"""
* {{ font-family: "DejaVu Sans", "Helvetica Neue", Arial; color: {FG.name()}; }}
#settingsRoot, QScrollArea, #scrollContent {{ background: {t.INK.name()}; border: 0; }}
QFrame#card {{ background: {CARD.name()}; border: 1px solid {LINE.name()}; border-radius: 14px; }}
QLabel#h2 {{ font-size: 13px; font-weight: 600; color: {MUTED.name()}; letter-spacing: 1px; }}
QLabel#h3 {{ font-size: 13px; font-weight: 600; color: {MUTED.name()}; letter-spacing: 1px; }}
QLabel#label {{ font-size: 15px; font-weight: 500; }}
QLabel#help {{ font-size: 13px; color: {MUTED.name()}; }}
QLabel#sub {{ font-size: 14px; color: {MUTED.name()}; }}
QLabel#mono {{ font-family: "DejaVu Sans Mono", Menlo; font-size: 14px; font-weight: 600; }}
QLabel#measured {{ font-family: "DejaVu Sans Mono", Menlo; font-size: 13px; color: {MUTED.name()}; }}
QPushButton {{ font-size: 16px; border-radius: 9px; padding: 13px 22px; }}
QPushButton#action {{ background: {ACCENT.name()}; color: {t.INK_2.name()}; border: 0;
                      font-weight: 600; }}
QPushButton#action:pressed {{ background: {t.mix(ACCENT, t.INK, 0.18).name()}; }}
QPushButton#action:disabled {{ background: {FAINT.name()}; }}
QPushButton#quiet {{ background: {CARD.name()}; color: {FG.name()};
                     border: 1px solid {LINE_2.name()}; }}
QPushButton#quiet:pressed {{ background: {t.PRESSED.name()}; }}
QPushButton#quiet[on="true"] {{ background: {ACCENT.name()}; color: {t.INK_2.name()};
                                border-color: {ACCENT.name()}; }}
QPushButton#input {{ background: {CARD.name()}; border: 1px solid {LINE_2.name()};
                     border-radius: 8px; text-align: left; padding: 12px 14px;
                     font-size: 16px; }}
QPushButton#input:pressed {{ border-color: {t.AMBER.name()}; }}
QPushButton#step {{ background: {CARD.name()}; border: 1px solid {LINE_2.name()};
                    border-radius: 8px; font-size: 24px; padding: 0;
                    min-width: 52px; max-width: 52px; min-height: 48px; max-height: 48px; }}
QPushButton#step:pressed {{ background: {t.PRESSED.name()}; }}
QPushButton#power {{ background: {t.ERR.name()}; color: {t.on(t.ERR).name()}; border: 0;
                     font-size: 17px; font-weight: 600; padding: 17px 26px; }}
QPushButton#power:pressed {{ background: {t.mix(t.ERR, t.BONE, 0.22).name()}; }}
QPushButton#back {{ background: {CARD.name()}; color: {FG.name()};
                    border: 1px solid {LINE_2.name()}; font-size: 18px;
                    font-weight: 500; padding: 17px 26px 17px 20px; }}
QPushButton#back:pressed {{ background: {t.PRESSED.name()}; }}
QPushButton#header {{ background: transparent; color: {MUTED.name()};
                      border: 1px solid transparent; font-size: 17px;
                      padding: 16px 20px; }}
QPushButton#header:pressed {{ background: {CARD.name()}; border-color: {LINE.name()}; }}
QPushButton#row {{ background: {CARD.name()}; border: 0;
                   border-bottom: 1px solid {LINE.name()}; border-radius: 0;
                   text-align: left; padding: 22px 28px; font-size: 20px; }}
QPushButton#row:pressed {{ background: {t.INK.name()}; }}
QPushButton#row[on="true"] {{ font-weight: 700; background: {tint.name()}; }}
QFrame#header {{ background: {t.INK.name()}; border: 0;
                 border-bottom: 1px solid {LINE.name()}; }}
QFrame#keyway {{ background: {t.INK.name()}; border: 1px solid {LINE.name()};
                 border-radius: 11px; }}
QFrame#previewBox {{ background: {t.INK_3.name()}; border-radius: 10px; }}
QScrollBar:vertical {{ width: 10px; background: transparent; }}
QScrollBar::handle:vertical {{ background: {LINE_2.name()}; border-radius: 5px;
                               min-height: 60px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


def label(text: str, name: str = "label", wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName(name)
    lab.setWordWrap(wrap)
    lab.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    return lab


def amp(text: str) -> str:
    """An & in a button label is a Qt accelerator and would vanish otherwise."""
    return str(text).replace("&", "&&")


def button(text: str, name: str = "quiet", on_click: Callable[[], None] | None = None) -> QPushButton:
    btn = QPushButton(amp(text))
    btn.setObjectName(name)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    if on_click is not None:
        btn.clicked.connect(lambda _=False: on_click())
    return btn


def set_on(btn: QPushButton, on: bool) -> None:
    btn.setProperty("on", "true" if on else "false")
    btn.style().unpolish(btn)
    btn.style().polish(btn)


class Card(QFrame):
    def __init__(self, title: str = "") -> None:
        super().__init__()
        self.setObjectName("card")
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(24, 22, 24, 24)
        self.box.setSpacing(0)
        if title:
            head = label(title.upper(), "h2")
            self.box.addWidget(head)
            self.box.addSpacing(18)


def field(title: str, help_text: str, control: QWidget) -> QWidget:
    """Beschriftung, Hinweis, Eingabe - eng beieinander."""
    wrap = QWidget()
    box = QVBoxLayout(wrap)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(3)
    box.addWidget(label(title))
    if help_text:
        box.addWidget(label(help_text, "help", wrap=True))
    box.addSpacing(4)
    box.addWidget(control)
    box.addStretch(1)
    return wrap


# -- number -----------------------------------------------------------------------------
class NumberControl(QWidget):
    changed = Signal(float)

    def __init__(self, keyboard, title: str, value: float | None, minimum: float | None,
                 maximum: float | None, step: float = 1, unit: str = "",
                 decimals: int = 0) -> None:
        super().__init__()
        self.keyboard = keyboard
        self.title = title
        self.minimum, self.maximum, self.step = minimum, maximum, step
        self.decimals = decimals
        self.value = value if value is not None else (minimum or 0)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.minus = button("−", "step", lambda: self._nudge(-1))
        self.shown = button("", "input", self._type)
        self.shown.setMinimumHeight(48)
        self.plus = button("+", "step", lambda: self._nudge(1))
        row.addWidget(self.minus)
        row.addWidget(self.shown, 1)
        row.addWidget(self.plus)
        if unit:
            row.addWidget(label(unit, "sub"))
        self._show()

    def set_value(self, value: float) -> None:
        self.value = value
        self._show()

    def _clamp(self, value: float) -> float:
        if self.minimum is not None:
            value = max(float(self.minimum), value)
        if self.maximum is not None:
            value = min(float(self.maximum), value)
        return round(value, self.decimals) if self.decimals else round(value)

    def _show(self) -> None:
        text = f"{self.value:.{self.decimals}f}" if self.decimals else str(int(round(self.value)))
        self.shown.setText(text.replace(".", ","))

    def _nudge(self, direction: int) -> None:
        new = self._clamp(self.value + direction * self.step)
        if new != self.value:
            self.value = new
            self._show()
            self.changed.emit(float(new))

    def _type(self) -> None:
        hint = ""
        if self.minimum is not None and self.maximum is not None:
            hint = f"Von {self.minimum:g} bis {self.maximum:g}".replace(".", ",")
        self.keyboard.ask_number(self.title, self.value, self._typed, hint=hint,
                                 decimal=self.decimals > 0)

    def _typed(self, text: str) -> None:
        try:
            new = self._clamp(float(text))
        except ValueError:
            return
        if new != self.value:
            self.value = new
            self._show()
            self.changed.emit(float(new))


# -- switches ---------------------------------------------------------------------------
class Toggle(QAbstractButton):
    """A box with text beside it; the whole row is tappable."""

    def __init__(self, title: str, help_text: str, checked: bool) -> None:
        super().__init__()
        self.setCheckable(True)
        self.setChecked(bool(checked))
        self.title = title
        self.help_text = help_text
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        text_w = max(50, width - 46)
        h = QFontMetricsF(theme.font(15)).height()
        if self.help_text:
            h += 3 + QFontMetricsF(theme.font(13)).boundingRect(
                QRectF(0, 0, text_w, 1000), int(Qt.TextFlag.TextWordWrap), self.help_text).height()
        return round(max(34, h + 14))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(300, self.heightForWidth(300))

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        box = QRectF(1, 7, 28, 28)
        if self.isChecked():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ACCENT)
            p.drawRoundedRect(box, 6, 6)
            pen = QPen(QColor("#FFFFFF"), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                       Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            x0, y0 = box.left(), box.top()
            p.drawPolyline([QPointF(x0 + 7, y0 + 15), QPointF(x0 + 12, y0 + 20),
                            QPointF(x0 + 21, y0 + 9)])
        else:
            p.setPen(QPen(LINE_2 if not self.isDown() else ACCENT, 2))
            p.setBrush(CARD)
            p.drawRoundedRect(box.adjusted(1, 1, -1, -1), 6, 6)
        x = 46
        p.setPen(FG)
        p.setFont(theme.font(15))
        fm = QFontMetricsF(theme.font(15))
        p.drawText(QRectF(x, 7, self.width() - x, fm.height()), Qt.AlignmentFlag.AlignLeft,
                   self.title)
        if self.help_text:
            p.setPen(MUTED)
            p.setFont(theme.font(13))
            p.drawText(QRectF(x, 7 + fm.height() + 3, self.width() - x, self.height()),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap), self.help_text)
        p.end()


# -- sliders ----------------------------------------------------------------------------
class SliderControl(QWidget):
    """Ein Regler mit Wert daneben. Belichtungszeit auf Wunsch logarithmisch."""

    changed = Signal(float)
    STEPS = 400

    def __init__(self, spec: dict[str, Any], value: float | None) -> None:
        super().__init__()
        self.spec = spec
        self.minimum = float(spec["min"])
        self.maximum = float(spec["max"])
        self.step = float(spec.get("step", 1))
        self.log = bool(spec.get("log"))
        self.value = float(value) if value is not None else self.minimum
        self.pos = self._to_pos(self.value)
        self.dragging = False
        self.setMinimumHeight(52)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.emit_timer = QTimer(self)
        self.emit_timer.setSingleShot(True)
        self.emit_timer.setInterval(350)
        self.emit_timer.timeout.connect(lambda: self.changed.emit(self.value))

    def set_value(self, value: float) -> None:
        if self.dragging:
            return
        self.value = float(value)
        self.pos = self._to_pos(self.value)
        self.update()

    def _to_pos(self, value: float) -> int:
        value = max(self.minimum, min(self.maximum, value))
        if self.log:
            lo, hi = math.log(self.minimum), math.log(self.maximum)
            return round((math.log(value) - lo) / (hi - lo) * self.STEPS)
        return round((value - self.minimum) / (self.maximum - self.minimum) * self.STEPS)

    def _from_pos(self, pos: int) -> float:
        t = pos / self.STEPS
        if self.log:
            value = math.exp(math.log(self.minimum) + t * (math.log(self.maximum) - math.log(self.minimum)))
        else:
            value = self.minimum + t * (self.maximum - self.minimum)
        return round(value / self.step) * self.step

    def text(self) -> str:
        v = self.value
        if self.spec.get("type") == "distance":
            return f"{v:.1f} m".replace(".", ",")
        if self.spec.get("unit"):
            return f"{round(v)} {self.spec['unit']}"
        return f"{round(v * 100) / 100:g}".replace(".", ",")

    def _track(self) -> QRectF:
        return QRectF(16, self.height() / 2 - 4, self.width() - 16 - 150, 8)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.dragging = True
        self._drag(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag(event)
        self.dragging = False
        self.emit_timer.start(0)

    def _drag(self, event: QMouseEvent) -> None:
        track = self._track()
        t = max(0.0, min(1.0, (event.position().x() - track.left()) / max(1.0, track.width())))
        pos = round(t * self.STEPS)
        event.accept()
        if pos != self.pos:
            self.pos = pos
            self.value = self._from_pos(pos)
            self.update()
            self.emit_timer.start()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = self._track()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(LINE)
        p.drawRoundedRect(track, 4, 4)
        x = track.left() + track.width() * self.pos / self.STEPS
        p.setBrush(ACCENT)
        p.drawRoundedRect(QRectF(track.left(), track.top(), x - track.left(), 8), 4, 4)
        p.drawEllipse(QRectF(x - 15, self.height() / 2 - 15, 30, 30))
        p.setPen(FG)
        p.setFont(theme.font(15, mono=True, weight=QFont.Weight.DemiBold))
        p.drawText(QRectF(self.width() - 140, 0, 140, self.height()),
                   int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), self.text())
        p.end()


# -- text -------------------------------------------------------------------------------
class TextControl(QPushButton):
    changed = Signal(str)

    def __init__(self, keyboard, title: str, value: str, placeholder: str = "",
                 secret: bool = False, hint: str = "") -> None:
        super().__init__()
        self.setObjectName("input")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.keyboard = keyboard
        self.title = title
        self.value = value or ""
        self.placeholder = placeholder
        self.secret = secret
        self.hint = hint
        self.setMinimumHeight(48)
        self.clicked.connect(self._open)
        self._show()

    def set_value(self, value: str) -> None:
        self.value = value or ""
        self._show()

    def _show(self) -> None:
        self.setText(amp(self.value or self.placeholder))
        self.setStyleSheet("" if self.value else f"color: {FAINT.name()};")

    def _open(self) -> None:
        # A secret is never pre-filled: the mask is not the key.
        start = "" if self.secret else self.value
        self.keyboard.ask_text(self.title, start, self._typed, hint=self.hint,
                               secret=self.secret)

    def _typed(self, text: str) -> None:
        text = text.strip() if self.secret else text
        if self.secret and not text:
            return
        if text != self.value:
            self.value = text
            self._show()
            self.changed.emit(text)


# -- choosing ---------------------------------------------------------------------------
class ChoiceControl(QPushButton):
    """Shows the choice; a tap opens a large list."""

    changed = Signal(str)

    def __init__(self, chooser, title: str, options: list[tuple[str, str]], current: str) -> None:
        super().__init__()
        self.setObjectName("input")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.chooser = chooser
        self.title = title
        self.options = options
        self.current = current
        self.setMinimumHeight(48)
        self.clicked.connect(lambda: self.chooser.ask(self.title, self.options, self.current,
                                                      self._chosen))
        self._show()

    def set_options(self, options: list[tuple[str, str]], current: str) -> None:
        self.options, self.current = options, current
        self._show()

    def _show(self) -> None:
        names = dict(self.options)
        self.setText(amp(names.get(self.current) or "bitte wählen") + "   ▾")

    def _chosen(self, value: str) -> None:
        if value != self.current:
            self.current = value
            self._show()
            self.changed.emit(value)


class ChooserOverlay(QWidget):
    """A list to pick from, big enough for a fingertip."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setGeometry(0, 0, theme.STAGE_W, theme.STAGE_H)
        self.panel = QFrame(self)
        self.panel.setObjectName("card")
        self.box = QVBoxLayout(self.panel)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(0)
        self.on_done: Callable[[str], None] | None = None
        self.hide()

    def ask(self, title: str, options: list[tuple[str, str]], current: str,
            on_done: Callable[[str], None]) -> None:
        while self.box.count():
            item = self.box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        head = label(title, "label")
        head.setStyleSheet("font-size: 22px; font-weight: 600; padding: 24px 28px 18px;")
        self.box.addWidget(head)
        for value, name in options:
            row = button(name, "row")
            set_on(row, value == current)
            row.clicked.connect(lambda _=False, v=value: self._pick(v))
            self.box.addWidget(row)
        cancel = button("Abbrechen", "row")
        cancel.setStyleSheet(f"color: {MUTED.name()};")
        cancel.clicked.connect(lambda: self._pick(None))
        self.box.addWidget(cancel)
        self.on_done = on_done
        height = min(theme.STAGE_H - 100, 76 + 72 * (len(options) + 1))
        self.panel.setGeometry((theme.STAGE_W - 720) // 2, (theme.STAGE_H - height) // 2, 720, height)
        self.raise_()
        self.show()

    def _pick(self, value: str | None) -> None:
        self.hide()
        callback, self.on_done = self.on_done, None
        if value is not None and callback is not None:
            callback(value)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self.panel.geometry().contains(event.position().toPoint()):
            self._pick(None)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        event.accept()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(16, 24, 40, 120))
        p.end()


class ConfirmOverlay(QWidget):
    """A question with two buttons.

    The button that does something sits on the right and is red; there is
    always a cancel next to it. A tap beside the panel cancels as well - on a
    touchscreen that is the commonest way of dismissing a question.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setGeometry(0, 0, theme.STAGE_W, theme.STAGE_H)
        self.panel = QFrame(self)
        self.panel.setObjectName("card")
        self.box = QVBoxLayout(self.panel)
        self.box.setContentsMargins(34, 30, 34, 26)
        self.box.setSpacing(0)
        self.hide()

    def ask(self, title: str, text: str, confirm: str,
            on_confirm: Callable[[], None], cancel: str = "Abbrechen") -> None:
        while self.box.count():
            item = self.box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        head = label(title, "label")
        head.setStyleSheet("font-size: 24px; font-weight: 700;")
        self.box.addWidget(head)
        self.box.addSpacing(14)
        body = label(text, "sub", wrap=True)
        body.setStyleSheet("font-size: 17px;")
        self.box.addWidget(body)
        self.box.addSpacing(28)
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(12)
        line.addStretch(1)
        line.addWidget(button(cancel, "quiet", lambda: self._close(None)))
        ja = button(confirm, "quiet", lambda: self._close(on_confirm))
        ja.setStyleSheet(f"background: {theme.ERR.name()}; color: {theme.on(theme.ERR).name()}; font-weight: 700;")
        line.addWidget(ja)
        self.box.addWidget(row)

        breite = 760
        self.panel.setFixedWidth(breite)
        self.panel.adjustSize()
        hoehe = max(240, self.panel.sizeHint().height())
        self.panel.setGeometry((theme.STAGE_W - breite) // 2,
                               (theme.STAGE_H - hoehe) // 2, breite, hoehe)
        self.raise_()
        self.show()

    def _close(self, callback: Callable[[], None] | None) -> None:
        self.hide()
        if callback is not None:
            callback()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self.panel.geometry().contains(event.position().toPoint()):
            self._close(None)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        event.accept()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(16, 24, 40, 120))
        p.end()


# -- tiles ------------------------------------------------------------------------------
class LayoutTile(QAbstractButton):
    """The layout as a sketch, in the sheet's true proportions."""

    def __init__(self, layout: dict[str, Any]) -> None:
        super().__init__()
        self.layout_data = layout
        self.selected = False
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedHeight(214)

    def set_layout(self, layout: dict[str, Any]) -> None:
        self.layout_data = layout
        self.update()

    def set_selected(self, on: bool) -> None:
        self.selected = on
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.selected:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(31, 41, 55, 20))
            p.drawRoundedRect(rect, 13, 13)
            rect = rect.adjusted(3, 3, -3, -3)
        p.setPen(QPen(ACCENT if self.selected else LINE, 2))
        p.setBrush(CARD if not self.isDown() else theme.PRESSED)
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 11, 11)
        inner = rect.adjusted(12, 12, -12, -12)
        thumb = QRectF(inner.left(), inner.top(), inner.width(), inner.width() / 1.5)
        if thumb.height() > inner.height() - 64:
            thumb.setHeight(inner.height() - 64)
            thumb.setWidth(thumb.height() * 1.5)
        # Deliberately outside the palette: this little thumbnail shows a sheet
        # of photo paper with pictures on it, not part of the interface. Paper
        # stays paper-coloured whichever scheme the screen is set to.
        p.setPen(QPen(LINE, 1))
        p.setBrush(QColor("#EFEBE1"))
        p.drawRoundedRect(thumb, 5, 5)
        frame_colour = QColor("#41506A") if self.selected else QColor("#8C97A6")
        p.setPen(Qt.PenStyle.NoPen)
        for f in self.layout_data.get("frames") or []:
            p.setBrush(frame_colour)
            p.drawRoundedRect(QRectF(thumb.left() + f[0] * thumb.width(), thumb.top() + f[1] * thumb.height(),
                                     f[2] * thumb.width(), f[3] * thumb.height()), 2, 2)
        t = self.layout_data.get("text_area")
        if t:
            area = QRectF(thumb.left() + t[0] * thumb.width(), thumb.top() + t[1] * thumb.height(),
                          t[2] * thumb.width(), t[3] * thumb.height())
            p.setBrush(QColor("#5B6472"))
            for i, share in enumerate((0.56, 0.34)):
                w = area.width() * share
                p.drawRoundedRect(QRectF(area.center().x() - w / 2, area.center().y() - 4 + i * 6, w, 2), 1, 1)
        y = thumb.bottom() + 8
        p.setPen(FG)
        name_font = theme.font(13.5, weight=QFont.Weight.DemiBold)
        p.setFont(name_font)
        name_rect = QFontMetricsF(name_font).boundingRect(
            QRectF(inner.left(), y, inner.width(), 60), int(Qt.TextFlag.TextWordWrap),
            self.layout_data.get("name", ""))
        p.drawText(QRectF(inner.left(), y, inner.width(), name_rect.height()),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap),
                   self.layout_data.get("name", ""))
        shots = int(self.layout_data.get("shots", 1))
        p.setPen(MUTED)
        p.setFont(theme.font(12))
        p.drawText(QRectF(inner.left(), y + name_rect.height() + 1, inner.width(), 18),
                   Qt.AlignmentFlag.AlignLeft, f"{shots} Bild" if shots == 1 else f"{shots} Bilder")
        p.end()


class SwatchTile(QAbstractButton):
    def __init__(self, bg: dict[str, Any]) -> None:
        super().__init__()
        self.bg = bg
        self.selected = False
        self.pixmap: QPixmap | None = None
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedHeight(112)

    def set_selected(self, on: bool) -> None:
        self.selected = on
        self.update()

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self.pixmap = pixmap
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(ACCENT if self.selected else LINE, 2))
        p.setBrush(CARD if not self.isDown() else theme.PRESSED)
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 10, 10)
        chip_h = rect.height() - 16 - 7 - 18
        chip = QRectF(rect.center().x() - chip_h * 0.75, rect.top() + 8, chip_h * 1.5, chip_h)
        p.setPen(QPen(LINE, 1))
        p.setBrush(QColor(self.bg.get("base", "#FFFFFF")))
        p.drawRoundedRect(chip, 5, 5)
        if self.pixmap is not None and not self.pixmap.isNull():
            from PySide6.QtGui import QPainterPath  # noqa: PLC0415
            path = QPainterPath()
            path.addRoundedRect(chip, 5, 5)
            p.setClipPath(path)
            p.drawPixmap(chip, self.pixmap, QRectF(self.pixmap.rect()))
            p.setClipping(False)
        p.setPen(MUTED)
        small = theme.font(11.5)
        p.setFont(small)
        text = QFontMetricsF(small).elidedText(self.bg.get("name", ""), Qt.TextElideMode.ElideRight,
                                               rect.width() - 8)
        p.drawText(QRectF(rect.left(), chip.bottom() + 5, rect.width(), 20),
                   Qt.AlignmentFlag.AlignCenter, text)
        p.end()


class ColourDot(QAbstractButton):
    def __init__(self, colour: str, name: str, size: int = 52) -> None:
        super().__init__()
        self.colour = colour
        self.name = name
        self.selected = False
        self.setFixedSize(size, size)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_selected(self, on: bool) -> None:
        self.selected = on
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        if self.selected:
            p.setPen(QPen(theme.AMBER, 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5))
        p.setPen(QPen(LINE_2, 1))
        p.setBrush(QColor(self.colour))
        p.drawEllipse(rect.adjusted(3, 3, -3, -3))
        p.end()


#: Eight hues across five lightness levels, plus a row of neutrals. Generated
#: rather than listed: forty hand-picked hex codes drift apart over time, and
#: a grid that steps evenly is easier to pick a matching pair from.
SWATCH_HUES = [0, 28, 45, 95, 165, 205, 260, 330]
SWATCH_LEVELS = [(0.94, 0.52), (0.82, 0.58), (0.60, 0.60), (0.42, 0.58), (0.25, 0.52)]
SWATCH_NEUTRALS = ["#FFFFFF", "#FAF3E4", "#F5F3EE", "#E6DAC0",
                   "#8C8375", "#4A443B", "#241F18", "#17161C"]


def swatches() -> list[list[str]]:
    """The picker grid, row by row."""
    reihen = []
    for hell, satt in SWATCH_LEVELS:
        reihen.append([QColor.fromHslF(h / 360.0, satt, hell).name() for h in SWATCH_HUES])
    reihen.append(list(SWATCH_NEUTRALS))
    return reihen


class ColourPickerOverlay(QWidget):
    """Pick one colour for one role, with a finger.

    No hue wheel and no hex field. Both need precision that a fingertip on a
    15 inch panel does not have, and neither answers the question that is
    actually being asked here, which is "something a bit warmer than this".
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setGeometry(0, 0, theme.STAGE_W, theme.STAGE_H)
        self.panel = QFrame(self)
        self.panel.setObjectName("card")
        self.box = QVBoxLayout(self.panel)
        self.box.setContentsMargins(28, 24, 28, 22)
        self.box.setSpacing(0)
        self.on_done: Callable[[str | None], None] | None = None
        self.hide()

    def ask(self, title: str, current: str,
            on_done: Callable[[str | None], None]) -> None:
        while self.box.count():
            item = self.box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        head = label(title, "label")
        head.setStyleSheet("font-size: 22px; font-weight: 600;")
        self.box.addWidget(head)
        self.box.addSpacing(16)

        jetzt = (current or "").lower()
        for reihe in swatches():
            zeile = QHBoxLayout()
            zeile.setSpacing(8)
            for code in reihe:
                dot = ColourDot(code, code, size=62)
                dot.set_selected(code.lower() == jetzt)
                dot.clicked.connect(lambda _=False, c=code: self._pick(c))
                zeile.addWidget(dot)
            zeile.addStretch(1)
            self.box.addLayout(zeile)
            self.box.addSpacing(6)

        self.box.addSpacing(12)
        fuss = QHBoxLayout()
        fuss.setSpacing(12)
        zurueck = button("Aus dem Schema", "quiet")
        zurueck.clicked.connect(lambda: self._pick(""))
        fuss.addWidget(zurueck)
        fuss.addStretch(1)
        abbruch = button("Abbrechen", "quiet")
        abbruch.clicked.connect(lambda: self._pick(None))
        fuss.addWidget(abbruch)
        self.box.addLayout(fuss)

        self.on_done = on_done
        breite, hoehe = 8 * 62 + 7 * 8 + 56, 24 + 30 + 16 + 6 * 68 + 12 + 56 + 22
        self.panel.setGeometry((theme.STAGE_W - breite) // 2,
                               (theme.STAGE_H - hoehe) // 2, breite, hoehe)
        self.raise_()
        self.show()

    def _pick(self, value: str | None) -> None:
        self.hide()
        callback, self.on_done = self.on_done, None
        if value is not None and callback is not None:
            callback(value)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self.panel.geometry().contains(event.position().toPoint()):
            self._pick(None)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        event.accept()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(16, 24, 40, 120))
        p.end()


class MenuRow(QAbstractButton):
    """One entry on the settings start page.

    Painted rather than built from a stylesheet, because it carries two lines
    of different weight plus a chevron, and a QPushButton with a rich-text
    label gets the vertical centring wrong as soon as the text wraps.

    The whole row is the target. At 92 pixels tall - about 16 mm on the panel -
    nobody has to aim.
    """

    H = 92

    def __init__(self, title: str, note: str, last: bool = False) -> None:
        super().__init__()
        self.title = title
        self.note = note
        self.last = last
        self.setFixedHeight(self.H)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = QRectF(self.rect())
        if self.isDown():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.PRESSED)
            p.drawRoundedRect(rect.adjusted(-10, 0, 10, 0), 10, 10)

        p.setPen(FG)
        p.setFont(theme.font(20, weight=QFont.Weight.DemiBold))
        p.drawText(QRectF(rect.left(), rect.top() + 20, rect.width() - 40, 26),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.title)
        p.setPen(MUTED)
        p.setFont(theme.font(14))
        p.drawText(QRectF(rect.left(), rect.top() + 48, rect.width() - 40, 22),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.note)

        # Chevron: the only hint that a page opens behind this row. Drawn by
        # hand so that it matches the text colour.
        x, y = rect.right() - 20, rect.center().y()
        p.setPen(QPen(FAINT, 2.4, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolyline([QPointF(x - 7, y - 7), QPointF(x, y), QPointF(x - 7, y + 7)])

        if not self.last:
            p.setPen(QPen(LINE, 1))
            p.drawLine(QPointF(rect.left(), rect.bottom()), QPointF(rect.right(), rect.bottom()))
        p.end()


class SchemeTile(QAbstractButton):
    """A ready-made scheme, shown as the four colours that carry it."""

    def __init__(self, scheme: str, name: str) -> None:
        super().__init__()
        self.scheme = scheme
        self.name = name
        self.colours = theme.SCHEMES[scheme]
        self.selected = False
        self.setFixedSize(168, 104)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_selected(self, on: bool) -> None:
        self.selected = on
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        p.setPen(QPen(ACCENT if self.selected else LINE, 2 if self.selected else 1))
        p.setBrush(QColor(self.colours["background"]))
        p.drawRoundedRect(rect, 10, 10)
        # Three dabs: surface, primary button, confirm. A scheme is recognised
        # by those faster than by its name.
        x = rect.left() + 14
        for role in ("surface", "primary", "confirm"):
            p.setPen(QPen(QColor(self.colours["text"]), 1))
            p.setBrush(QColor(self.colours[role]))
            p.drawEllipse(QRectF(x, rect.top() + 18, 26, 26))
            x += 34
        p.setPen(QColor(self.colours["text"]))
        p.setFont(theme.font(16, weight=QFont.Weight.DemiBold))
        p.drawText(QRectF(rect.left() + 14, rect.bottom() - 36, rect.width() - 28, 24),
                   Qt.AlignmentFlag.AlignVCenter, self.name)
        p.end()


def grid(widgets: list[QWidget], columns: int, h_gap: int = 18, v_gap: int = 18) -> QWidget:
    wrap = QWidget()
    lay = QGridLayout(wrap)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setHorizontalSpacing(h_gap)
    lay.setVerticalSpacing(v_gap)
    for i, w in enumerate(widgets):
        r, c = divmod(i, columns)
        lay.addWidget(w, r, c, Qt.AlignmentFlag.AlignTop)
    for c in range(columns):
        lay.setColumnStretch(c, 1)
    return wrap
