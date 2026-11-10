"""Building blocks of the interface: buttons, pictures, overlays.

Everything is painted by hand rather than styled with stylesheets. That keeps
the shapes exact - stadium buttons, shadows, pressed states - and costs less on
the Pi than Qt stylesheets, which are re-evaluated on every repaint.
"""

from __future__ import annotations

import logging
import shutil
from collections import OrderedDict
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QImageReader, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QWidget

from . import theme

log = logging.getLogger(__name__)


@lru_cache(maxsize=32)
def qr_svg(text: str) -> bytes | None:
    """Ein QR-Code als SVG, oder nichts, wenn qrencode fehlt."""
    if not text or not shutil.which("qrencode"):
        return None
    try:
        done = subprocess.run(["qrencode", "-t", "SVG", "-m", "1", "-o", "-", text],
                              capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        log.warning("qrencode failed", exc_info=True)
        return None
    return done.stdout if done.returncode == 0 and done.stdout else None


# -- Bilder --------------------------------------------------------------------
#: Zuletzt benutzte Bilder in Anzeigegroesse, die aeltesten fliegen zuerst raus.
#: Begrenzt nach Speicher, nicht nach Anzahl: ein Ergebnisbild in voller
#: A full-screen picture takes over 6 MB, a gallery thumbnail 0.1 MB. Eighty
#: entries counted without regard to size came to several hundred MB on a Pi
#: with 1 GB.
_cache: "OrderedDict[tuple[str, int, int, bool, float], QPixmap]" = OrderedDict()
_CACHE_BYTES = 60 * 1024 * 1024


def _pixmap_bytes(pixmap: QPixmap) -> int:
    return pixmap.width() * pixmap.height() * 4


def load_picture(path: Path | str, width: int, height: int, cover: bool) -> QPixmap:
    """Load a picture at display size, scaled down during decoding already.

    A photograph from this box is 4608 x 3072 pixels. Decoding it in full and
    then shrinking it to a 192 x 128 thumbnail costs several times what the
    JPEG decoder needs when it scales while decoding.
    cover: fill the area completely and crop what hangs over; otherwise fit
    the whole picture inside.
    """
    path = Path(path)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return QPixmap()
    key = (str(path), width, height, cover, mtime)
    cached = _cache.get(key)
    if cached is not None:
        _cache.move_to_end(key)
        return cached
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and size.width() > 0 and size.height() > 0:
        mode = (Qt.AspectRatioMode.KeepAspectRatioByExpanding if cover
                else Qt.AspectRatioMode.KeepAspectRatio)
        target = size.scaled(QSize(width, height), mode)
        # Never decode larger than the file actually is.
        if target.width() < size.width():
            reader.setScaledSize(target)
    image: QImage = reader.read()
    if image.isNull():
        return QPixmap()
    if cover and (image.width() > width or image.height() > height):
        x = max(0, (image.width() - width) // 2)
        y = max(0, (image.height() - height) // 2)
        image = image.copy(x, y, min(width, image.width()), min(height, image.height()))
    pixmap = QPixmap.fromImage(image)
    _cache[key] = pixmap
    total = sum(_pixmap_bytes(p) for p in _cache.values())
    while total > _CACHE_BYTES and len(_cache) > 1:
        _, old = _cache.popitem(last=False)
        total -= _pixmap_bytes(old)
    return pixmap


def _rounded(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


_shadows: dict[tuple, QPixmap] = {}


def paint_shadow(painter: QPainter, rect: QRectF, radius: float, offset_y: float,
                 blur: float, colour: QColor, alpha: float) -> None:
    """A soft shadow, like box-shadow in a browser.

    The blur runs once per size; after that it is just a finished image. A
    QGraphicsDropShadowEffect would recompute the whole widget on every
    repaint - too expensive on the Pi for a shadow.
    """
    w, h = round(rect.width()), round(rect.height())
    key = (w, h, round(radius), round(blur), colour.rgb(), round(alpha * 100))
    pixmap = _shadows.get(key)
    if pixmap is None:
        pixmap = _build_shadow(w, h, radius, blur, colour, alpha)
        if len(_shadows) > 20:
            _shadows.clear()
        _shadows[key] = pixmap
    pad = round(blur)
    painter.drawPixmap(round(rect.x()) - pad, round(rect.y() + offset_y) - pad, pixmap)


def _build_shadow(w: int, h: int, radius: float, blur: float, colour: QColor,
                  alpha: float) -> QPixmap:
    from PIL import Image, ImageDraw, ImageFilter  # noqa: PLC0415

    pad = round(blur)
    mask = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    ImageDraw.Draw(mask).rounded_rectangle((pad, pad, pad + w - 1, pad + h - 1),
                                           radius=max(0, round(radius)),
                                           fill=round(255 * alpha))
    if blur > 0:
        # Im Browser entspricht blur ungefaehr der doppelten Standardabweichung.
        mask = mask.filter(ImageFilter.GaussianBlur(blur / 2))
    rgba = Image.new("RGBA", mask.size, (colour.red(), colour.green(), colour.blue(), 0))
    rgba.putalpha(mask)
    data = rgba.tobytes("raw", "RGBA")
    image = QImage(data, rgba.width, rgba.height, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(image)


# -- Knoepfe -------------------------------------------------------------------
class Button(QAbstractButton):
    """Ein gezeichneter Knopf: Form, Farben, Text oder Symbol.

    shape: "rect" (abgerundetes Rechteck), "pill" (ganz rund an den Enden) oder
    "circle".
    """

    def __init__(self, parent: QWidget, *, shape: str = "rect", radius: float = 11,
                 bg: QColor | None = theme.INK_2, fg: QColor = theme.BONE,
                 border: QColor | None = theme.LINE, border_w: float = 1.0,
                 font: QFont | None = None, text: str = "", subtext: str = "",
                 subfont: QFont | None = None, icon: str | None = None, icon_ratio: float = 0.46,
                 shadow: tuple[QColor, float, float, float] | None = (QColor(60, 50, 35), 0.08, 2, 8),
                 on_click: Callable[[], None] | None = None) -> None:
        super().__init__(parent)
        self.shape = shape
        self.radius = radius
        self.bg = bg
        self.fg = fg
        self.border = border
        self.border_w = border_w
        self.label_font = font or theme.font(24)
        self.subfont = subfont or theme.font(24, weight=QFont.Weight.DemiBold)
        self.label = text
        self.sublabel = subtext
        self.icon = icon
        self.icon_ratio = icon_ratio
        self.shadow = shadow
        self.dot: QColor | None = None
        #: Unsichtbarer Rand fuer den Schatten; siehe put().
        self.pad = (shadow[2] + shadow[3]) if shadow else 0
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if on_click is not None:
            self.clicked.connect(on_click)

    def set_text(self, text: str, subtext: str | None = None) -> None:
        changed = text != self.label or (subtext is not None and subtext != self.sublabel)
        self.label = text
        if subtext is not None:
            self.sublabel = subtext
        if changed:
            self.update()

    def natural_size(self, pad_x: float, pad_y: float) -> QSize:
        """Groesse aus Text und Innenabstand, wie ein Knopf im Browser."""
        fm = QFontMetricsF(self.label_font)
        w = fm.horizontalAdvance(self.label)
        h = fm.height() * 1.05
        if self.sublabel:
            sm = QFontMetricsF(self.subfont)
            w = max(w, sm.horizontalAdvance(self.sublabel))
            h += 3 + sm.height()
        return QSize(round(w + 2 * pad_x), round(h + 2 * pad_y))

    def hitButton(self, pos) -> bool:  # noqa: N802
        """Only the visible area counts as a press, not the shadow margin.

        A button carries a transparent margin around itself so its shadow has
        somewhere to land. Qt counts that margin as part of the button, which
        quietly undoes the safe margin: the bar buttons look 28 points from
        the edge and answered from 18 - close enough for a thumb resting on
        the bezel to set one off.
        """
        return self.rect().adjusted(self.pad, self.pad, -self.pad, -self.pad).contains(pos)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt name
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        m = self.pad
        body = QRectF(self.rect()).adjusted(m, m, -m, -m)
        if self.isDown():
            c = body.center()
            body = QRectF(c.x() - body.width() * 0.48, c.y() - body.height() * 0.48,
                          body.width() * 0.96, body.height() * 0.96)
        radius = self._radius(body)
        if self.shadow and self.isEnabled():
            colour, alpha, offset, spread = self.shadow
            paint_shadow(p, body, radius, offset, spread, colour, alpha)
        path = _rounded(body, radius)
        if self.bg is not None:
            p.fillPath(path, self.bg)
        if self.border is not None and self.border_w > 0:
            half = self.border_w / 2
            p.setPen(QPen(self.border, self.border_w))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(body.adjusted(half, half, -half, -half), radius - half, radius - half)

        if self.dot is not None:
            d = 22
            c = body.center()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 13))
            p.drawEllipse(c, d / 2 + 4, d / 2 + 4)
            p.setBrush(self.dot)
            p.drawEllipse(c, d / 2, d / 2)
        elif self.icon:
            side = min(body.width(), body.height()) * self.icon_ratio
            c = body.center()
            theme.draw_svg(p, self.icon, QRectF(c.x() - side / 2, c.y() - side / 2, side, side),
                           self.fg)
        else:
            p.setPen(self.fg)
            if self.sublabel:
                fm = QFontMetricsF(self.label_font)
                sm = QFontMetricsF(self.subfont)
                total = fm.height() * 1.05 + 3 + sm.height()
                top = body.center().y() - total / 2
                p.setFont(self.label_font)
                p.drawText(QRectF(body.left(), top, body.width(), fm.height() * 1.05),
                           Qt.AlignmentFlag.AlignCenter, self.label)
                sub = theme.with_alpha(self.fg, 0.85)
                p.setPen(sub)
                p.setFont(self.subfont)
                p.drawText(QRectF(body.left(), top + fm.height() * 1.05 + 3, body.width(), sm.height()),
                           Qt.AlignmentFlag.AlignCenter, self.sublabel)
            else:
                p.setFont(self.label_font)
                p.drawText(body, Qt.AlignmentFlag.AlignCenter, self.label)
        p.end()

    def _radius(self, body: QRectF) -> float:
        if self.shape in ("pill", "circle"):
            return min(body.width(), body.height()) / 2
        return self.radius


def place(widget: QWidget, x: float, y: float, w: float, h: float) -> None:
    widget.setGeometry(round(x), round(y), round(w), round(h))


def put(widget: QWidget, x: float, y: float, w: float, h: float) -> None:
    """Place the visible area at x, y, w, h, with the shadow margin outside it.

    A widget can only paint within its own bounds. Without that margin the
    shadow would be cut off at the edge of the button.
    """
    m = getattr(widget, "pad", 0)
    place(widget, x - m, y - m, w + 2 * m, h + 2 * m)


def put_centered(widget: QWidget, cx: float, cy: float, w: float, h: float) -> None:
    put(widget, cx - w / 2, cy - h / 2, w, h)


# -- Bilder als Elemente -------------------------------------------------------
class Picture(QAbstractButton):
    """Ein Bild mit abgerundeten Ecken, auf Wunsch antippbar und umrahmt."""

    def __init__(self, parent: QWidget, *, radius: float = 7, cover: bool = True,
                 shadow_alpha: float = 0.14, frame_colour: QColor | None = None,
                 frame_w: float = 0, background: QColor | None = None,
                 on_click: Callable[[], None] | None = None) -> None:
        super().__init__(parent)
        self.path: Path | None = None
        self.radius = radius
        self.cover = cover
        self.shadow_alpha = shadow_alpha
        self.frame_colour = frame_colour
        self.frame_w = frame_w
        self.selected = False
        self.background = background
        self.pad = (34 + 12) if (shadow_alpha and not cover) else (12 if shadow_alpha else 0)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if on_click is not None:
            self.clicked.connect(on_click)
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_path(self, path: Path | None) -> None:
        if path != self.path:
            self.path = path
            self.update()

    def set_selected(self, selected: bool) -> None:
        if selected != self.selected:
            self.selected = selected
            self.update()

    def image_rect(self) -> QRectF:
        """Wo das Bild tatsaechlich steht (bei cover=False kleiner als das Element)."""
        m = self.pad + self.frame_w
        area = QRectF(self.rect()).adjusted(m, m, -m, -m)
        if self.cover or self.path is None:
            return area
        pm = load_picture(self.path, round(area.width()), round(area.height()), cover=False)
        if pm.isNull():
            return area
        w, h = pm.width(), pm.height()
        return QRectF(area.center().x() - w / 2, area.center().y() - h / 2, w, h)

    def paintEvent(self, _event) -> None:  # noqa: N802
        if self.path is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.image_rect()
        if self.isDown():
            c = rect.center()
            rect = QRectF(c.x() - rect.width() * 0.485, c.y() - rect.height() * 0.485,
                          rect.width() * 0.97, rect.height() * 0.97)
        pm = load_picture(self.path, round(rect.width()), round(rect.height()), cover=self.cover)
        if self.shadow_alpha:
            paint_shadow(p, rect, self.radius, 2 if self.cover else 12, 10 if self.cover else 34,
                         QColor(60, 50, 35), self.shadow_alpha)
        clip = _rounded(rect, self.radius)
        if self.background is not None:
            p.fillPath(clip, self.background)
        p.setClipPath(clip)
        if not pm.isNull():
            p.drawPixmap(rect, pm, QRectF(pm.rect()))
        p.setClipping(False)
        if self.frame_w and self.selected and self.frame_colour is not None:
            # The frame goes around the picture, not on top of it.
            half = self.frame_w / 2
            p.setPen(QPen(self.frame_colour, self.frame_w))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(-half, -half, half, half),
                              self.radius + half, self.radius + half)
        p.end()


# -- Einblendungen -------------------------------------------------------------
class CountdownText(QWidget):
    """The big digit over the live image. Does not intercept touches."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.text = ""
        self.big = theme.font(408, bold=True, spacing=-20)
        self.medium = theme.font(54, bold=True)
        self.use_medium = False

    def set_text(self, text: str, medium: bool = False) -> None:
        if text != self.text or medium != self.use_medium:
            self.text = text
            self.use_medium = medium
            self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        if not self.text:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setFont(self.medium if self.use_medium else self.big)
        rect = QRectF(self.rect())
        # A soft dark halo, so the digit reads on any background.
        for dx, dy, a in ((0, 4, 60), (0, 2, 90), (-2, 2, 50), (2, 2, 50), (0, 8, 35)):
            p.setPen(QColor(0, 0, 0, a))
            p.drawText(rect.translated(dx, dy), Qt.AlignmentFlag.AlignCenter, self.text)
        p.setPen(QColor(255, 255, 255))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text)
        p.end()


class Flash(QWidget):
    """The flash at the shutter: almost white for a moment, then gone."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.level = 0.0
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(500)
        self.anim.setStartValue(0.0)
        self.anim.setKeyValueAt(0.1, 0.95)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(self._on_value)
        self.anim.finished.connect(self.hide)
        self.hide()

    def fire(self) -> None:
        self.raise_()
        self.show()
        self.anim.stop()
        self.anim.start()

    def _on_value(self, value: float) -> None:
        self.level = float(value)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), theme.with_alpha(QColor("#FFFDF6"), self.level))
        p.end()


class TimeBar(QWidget):
    """The thin bar at the bottom: how long this screen has left."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.fraction = 0.0

    def set_fraction(self, value: float) -> None:
        value = max(0.0, min(1.0, value))
        if abs(value - self.fraction) * self.width() >= 1 or (value == 0) != (self.fraction == 0):
            self.fraction = value
            self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        if self.fraction <= 0:
            return
        p = QPainter(self)
        p.fillRect(QRectF(0, 0, self.width() * self.fraction, self.height()), theme.AMBER)
        p.end()


class Toast(QWidget):
    """A short message at the bottom centre that disappears by itself."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.text = ""
        self.font_ = theme.font(17)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)
        self.hide()

    def show_text(self, text: str, ms: int = 3200) -> None:
        self.text = text
        fm = QFontMetricsF(self.font_)
        w = min(1536, fm.horizontalAdvance(text) + 40)
        h = fm.height() + 22
        parent = self.parentWidget()
        place(self, (parent.width() - w) / 2, parent.height() - 36 - h, w, h)
        self.raise_()
        self.show()
        self.update()
        self.timer.start(ms)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor("#E3C98F"), 1))
        p.setBrush(QColor("#FDF6E7"))
        p.drawRoundedRect(rect, 8, 8)
        p.setPen(QColor("#6B4A10"))
        p.setFont(self.font_)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text)
        p.end()


class Label(QWidget):
    """Ein Stueck Text ohne Hintergrund."""

    def __init__(self, parent: QWidget, font: QFont, colour: QColor,
                 align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.text = ""
        self.font_ = font
        self.colour = colour
        self.align = align

    def set_text(self, text: str) -> None:
        if text != self.text:
            self.text = text
            self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        if not self.text:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setPen(self.colour)
        p.setFont(self.font_)
        p.drawText(QRectF(self.rect()), self.align | Qt.TextFlag.TextWordWrap, self.text)
        p.end()


class RoundedCorners(QWidget):
    """Covers the four corners of a widget in the background colour.

    The live image comes off the GPU. A widget like that cannot be clipped
    with soft edges - a mask would give hard stair-steps. So instead,
    everything outside the rounded rectangle is painted over. That is
    antialiased and costs nothing.
    """

    def __init__(self, parent: QWidget, radius: float = 22,
                 colour: QColor | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.radius = radius
        self.colour = colour or theme.INK

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        aussen = QPainterPath()
        aussen.addRect(rect)
        innen = QPainterPath()
        innen.addRoundedRect(rect, self.radius, self.radius)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.colour)
        p.drawPath(aussen.subtracted(innen))
        p.end()


class Banner(QWidget):
    """A plainly readable notice over the live image, e.g. when the camera is gone."""

    def __init__(self, parent: QWidget, title: str, text: str) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # Without this Qt fills the box black first and paints the rounded
        # surface afterwards - black stays in the corners, and stays there
        # when the banner is hidden again, too.
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.title = title
        self.text = text

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(30, 25, 18, 225))
        p.drawRoundedRect(rect, 18, 18)
        p.setPen(QColor("#FFFFFF"))
        p.setFont(theme.font(40, bold=True))
        p.drawText(rect.adjusted(40, 34, -40, -rect.height() / 2), Qt.AlignmentFlag.AlignCenter,
                   self.title)
        p.setPen(QColor("#E6E0D6"))
        p.setFont(theme.font(24))
        p.drawText(rect.adjusted(40, rect.height() / 2, -40, -30),
                   int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
                   self.text)
        p.end()


class Panel(QWidget):
    """Ein weisser Kasten mit Rand, etwa fuer den QR-Code."""

    def __init__(self, parent: QWidget, radius: float = 12) -> None:
        super().__init__(parent)
        self.radius = radius

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(theme.LINE, 1))
        p.setBrush(theme.INK_2)
        p.drawRoundedRect(rect, self.radius, self.radius)
        p.end()


class SvgView(QWidget):
    """Ein SVG, etwa der QR-Code, scharf in jeder Groesse."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.renderer = None

    def set_svg(self, data: bytes | None) -> None:
        from PySide6.QtCore import QByteArray  # noqa: PLC0415
        from PySide6.QtSvg import QSvgRenderer  # noqa: PLC0415

        self.renderer = QSvgRenderer(QByteArray(data)) if data else None
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        if self.renderer is None or not self.renderer.isValid():
            return
        p = QPainter(self)
        self.renderer.render(p, QRectF(self.rect()))
        p.end()
