"""The start screen, for as long as the box is not ready yet.

Roughly ten seconds pass on a Pi 4 between power-on and the live image: the
camera comes up, the interface is built. That time used to show the console -
kernel messages and four raspberries. Now it shows the box itself.

Deliberately without motion. The main thread blocks while the camera starts,
and an animation that freezes halfway looks more broken than a still picture.
A line of text says what is happening instead.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from . import theme

ICON = Path(__file__).resolve().parent.parent / "assets" / "icon.png"

#: The start screen keeps its own two colours and ignores the palette on
#: purpose. It is the logo, and a logo does not change colour with a setting -
#: black on white, the way it is printed and the way it stands on the website.
PAPER = QColor("#FFFFFF")
MARK = QColor("#000000")
MARK_DIM = QColor("#6B6B6B")

#: Edge length of the mark on the stage.
ICON_PX = 190


class SplashScreen(QWidget):
    """Logo, name, and one line about what the box is busy with."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("splash")
        self.setFixedSize(theme.STAGE_W, theme.STAGE_H)
        self.note = "startet …"
        self.icon = self._symbol()

    @staticmethod
    def _symbol() -> QPixmap:
        """Cut the icon out of its background and tint it black.

        The file is black line art on white. With no alpha channel it would
        sit on the page as a white box. Brightness is therefore turned into
        opacity: white becomes transparent, black stays solid. Qt does that in
        C++ rather than pixel by pixel here - every tenth of a second counts
        during startup.
        """
        if not ICON.exists():
            return QPixmap()
        bild = QImage(str(ICON))
        if bild.isNull():
            return QPixmap()
        maske = bild.convertToFormat(QImage.Format.Format_Grayscale8)
        maske.invertPixels()
        flaeche = QImage(bild.size(), QImage.Format.Format_ARGB32)
        flaeche.fill(MARK)
        flaeche.setAlphaChannel(maske)
        return QPixmap.fromImage(flaeche).scaled(
            ICON_PX, ICON_PX, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)

    def present(self, app: QApplication, timeout_s: float = 2.5) -> None:
        """Wait until the screen is actually up.

        Under Wayland a window is not visible the moment show() returns: the
        compositor has to attach the surface and paint it, and that takes a
        few turns of the event loop. Without this wait the caller goes
        straight into the long step, the loop never gets another turn, and the
        start screen would appear only once it is no longer needed. Measured,
        not assumed.
        """
        ende = time.monotonic() + timeout_s
        while time.monotonic() < ende:
            app.processEvents()
            fenster = self.windowHandle()
            if fenster is not None and fenster.isExposed():
                # Two more turns, so it is genuinely painted and not just mapped.
                app.processEvents()
                app.processEvents()
                return
            time.sleep(0.02)

    def set_note(self, text: str) -> None:
        """Set the line under the name and paint it right away.

        Right away, because the caller goes into a long step immediately
        afterwards and the event loop will not get another turn.
        """
        self.note = text
        self.repaint()
        app = QApplication.instance()
        if app is not None:
            for _ in range(3):
                app.processEvents()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.fillRect(self.rect(), PAPER)

        mitte_x = theme.STAGE_W / 2
        # The group sits a little above centre: on a screen at head height,
        # dead centre looks too low.
        oben = theme.STAGE_H * 0.33

        if not self.icon.isNull():
            p.drawPixmap(round(mitte_x - self.icon.width() / 2), round(oben),
                         self.icon)
            oben += self.icon.height() + 54

        p.setPen(MARK)
        p.setFont(theme.font(64, weight=QFont.Weight.DemiBold))
        p.drawText(QRectF(0, oben, theme.STAGE_W, 86),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   "EventPics Fotobox")
        oben += 86 + 18

        p.setPen(MARK_DIM)
        p.setFont(theme.font(28))
        p.drawText(QRectF(0, oben, theme.STAGE_W, 44),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   self.note)
        p.end()
