"""The live image.

On the Pi, picamera2 draws the camera frames straight onto the GPU: no JPEG,
no browser, no copying in between. With no camera attached (on a development
machine) a plain widget shows the frames of the mock camera instead.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QWidget

log = logging.getLogger(__name__)


def set_preview_background(widget: QWidget, colour) -> None:
    """Repaint the letterbox bars when the colour scheme changes.

    The GL widget is handed its backing colour once, at construction, and
    keeps it. After a scheme change that left a strip of the previous
    background along the edge of the live image - cream on a dark page.
    """
    if not hasattr(widget, "bg_colour"):
        return
    widget.bg_colour = [colour.red() / 255.0, colour.green() / 255.0,
                        colour.blue() / 255.0, 1.0]
    widget.update()


def create_preview(parent: QWidget, camera) -> QWidget:
    """The right preview widget, with the camera running afterwards.

    The live image is mirrored, the way a mirror is: step left and you watch
    yourself step left. The photograph itself is not mirrored.
    """
    if getattr(camera, "backend", "") == "picamera2" and getattr(camera, "picam2", None) is not None:
        from libcamera import Transform  # noqa: PLC0415 - Pi only
        from picamera2.previews.qt import QGlSide6Picamera2  # noqa: PLC0415

        from .guest import PREVIEW  # noqa: PLC0415 - only for the size
        from . import theme  # noqa: PLC0415

        # Size and backing colour come from the interface, not from hard
        # coded numbers. Black as the backing would mean a black band wherever
        # the frame does not fill the widget - in the middle of a cream page.
        grund = theme.INK
        widget = QGlSide6Picamera2(camera.picam2, parent=parent,
                                   width=PREVIEW[2], height=PREVIEW[3],
                                   keep_ar=True,
                                   bg_colour=(grund.red(), grund.green(), grund.blue()),
                                   transform=Transform(hflip=1))
        camera.start()
        return widget
    return MockPreview(parent, camera)


class MockPreview(QWidget):
    """Zeigt die Bilder der Mock-Kamera, etwa 15 je Sekunde."""

    def __init__(self, parent: QWidget, camera) -> None:
        super().__init__(parent)
        self.camera = camera
        self.image = QImage()
        self.seen = -1
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._pull)
        self.timer.start(66)

    def _pull(self) -> None:
        buffer = getattr(self.camera, "buffer", None)
        if buffer is None or buffer.frame_count == self.seen or not self.isVisible():
            return
        self.seen = buffer.frame_count
        frame = buffer.frame
        if frame:
            image = QImage.fromData(frame, "JPEG")
            if not image.isNull():
                self.image = image.mirrored(True, False)
                self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.GlobalColor.black)
        if not self.image.isNull():
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(QRectF(self.rect()), self.image)
        p.end()
