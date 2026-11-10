"""The window: the fixed stage, centred and bordered when the aspect differs.

The screens are stacked on it: guests, PIN, settings. There is only ever one
live image, and it moves back and forth between the guest screen and the
settings screen.
"""

from __future__ import annotations

import logging
import os
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from . import theme
from .guest import PREVIEW, GuestScreen
from .pin import PinScreen
from .settings import SettingsScreen
from .widgets import place

log = logging.getLogger(__name__)

#: Exit code the app uses to end itself on purpose, so that systemd restarts it.
RESTART_CODE = 3


class MainWindow(QWidget):
    def __init__(self, backend) -> None:
        super().__init__()
        self.setWindowTitle("EventPics Photobooth")
        self.backend = backend
        self.stage = QWidget(self)
        self.stage.setFixedSize(theme.STAGE_W, theme.STAGE_H)
        self.guest = GuestScreen(self.stage, backend, on_settings=self.open_pin)
        self.pin = PinScreen(self.stage, backend.auth, on_success=self.open_settings,
                             on_back=self.back_to_guests)
        self.settings = SettingsScreen(self.stage, backend, on_close=self.back_to_guests)
        self.resize(theme.STAGE_W, theme.STAGE_H)

        self.started = time.monotonic()
        self.failures_in_row = 0
        self.guest.on_state_change = self._state_changed
        self.health = QTimer(self)
        self.health.timeout.connect(self._check_health)
        self.health.start(5000)

    # -- Selbstheilung ---------------------------------------------------------------
    def _state_changed(self, state: str, previous: str | None) -> None:
        if state == "failed":
            self.failures_in_row += 1
        elif state == "review":
            self.failures_in_row = 0

    def _check_health(self) -> None:
        """Restart when the box can no longer take pictures by itself.

        Two cases: the camera was unavailable at startup (still held by the
        previous instance, for example), or two shots in a row failed - usually
        a camera that stopped answering halfway through the evening. A restart
        often gets it back either way. Only as a service, where systemd will
        start it again, and only while nobody is using the box.
        """
        if "INVOCATION_ID" not in os.environ:
            return
        if self.backend.session.state != "idle" or not self.backend.guests_allowed.is_set():
            return
        reason = None
        if self.guest.camera_lost() and time.monotonic() - self.started > 60:
            reason = "Kamera nicht erreichbar"
        elif self.failures_in_row >= 2:
            reason = f"{self.failures_in_row} Aufnahmen in Folge fehlgeschlagen"
        if reason is None:
            return
        log.error("Restarting the booth: %s", reason)
        self.backend.events.add(f"Neustart der Fotobox: {reason}", "error")
        QApplication.exit(RESTART_CODE)

    # -- Wechsel ---------------------------------------------------------------------
    def open_pin(self) -> None:
        # Only from the idle start screen: nobody has any business in the
        # settings halfway through a shot.
        if self.backend.session.state != "idle":
            return
        self.backend.guests_allowed.clear()
        self.pin.open()

    def open_settings(self) -> None:
        self.settings.open()

    def lend_preview(self, slot: QWidget) -> None:
        """Hand the one live image over to a slot on the settings screen.

        There is exactly one preview widget, because the camera delivers its
        frames to exactly one. So it is lent, not copied.
        """
        preview = self.guest.preview
        preview.setParent(slot)
        preview.setGeometry(0, 0, slot.width(), slot.height())
        preview.show()

    def reclaim_preview(self) -> None:
        """Take it back to the guest screen.

        Called before the settings rebuild a page as well as when they close.
        A page change deletes the whole page, and the live image must not be
        inside the part being deleted - taking it down would take the camera's
        only output with it.
        """
        preview = self.guest.preview
        if preview.parent() is not self.guest:
            preview.setParent(self.guest)
            place(preview, *PREVIEW)
            preview.stackUnder(self.guest.count)
            preview.setVisible(not self.guest.camera_lost())

    def back_to_guests(self) -> None:
        self.reclaim_preview()
        self.pin.hide()
        self.settings.hide()
        self.backend.guests_allowed.set()
        self.guest.refresh_after_settings()

    # -- Fenster ---------------------------------------------------------------------
    def resizeEvent(self, _event) -> None:  # noqa: N802
        # Qt does the scaling (QT_SCALE_FACTOR); all that is left here is
        # centring, in case the screen has a different aspect ratio.
        self.stage.move((self.width() - theme.STAGE_W) // 2,
                        (self.height() - theme.STAGE_H) // 2)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), theme.INK)
        p.end()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        # Only for working on a desktop with a keyboard. The box has none.
        if event.key() == Qt.Key.Key_Escape and not self.isFullScreen():
            self.close()
        else:
            super().keyPressEvent(event)
