"""The booth's own messages, to read back in the settings.

A page of the settings rather than a panel over them. The messages are a place
you go to - "when did the lamp drop out?" - not something you glance at, and a
panel that covers the screen reads like an interruption.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QScroller, QVBoxLayout, QWidget

from . import theme
from .controls import Card, button


def level_colour(level: str):
    """The lettering of one line, by how bad it is."""
    return {"error": theme.ERR_INK, "warn": theme.WARN_INK,
            "good": theme.OK_INK}.get(level, theme.BONE)


class LogPage(Card):
    """Every message since the box was started, newest at the bottom."""

    def __init__(self, events) -> None:
        super().__init__()
        self.events = events
        self.last_id = 0
        self.box.setSpacing(14)

        # No heading of its own: the bar above already says "Meldungen".
        head = QHBoxLayout()
        head.addStretch(1)
        head.addWidget(button("Alle löschen", "quiet", self._clear))
        self.box.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setMinimumHeight(760)
        QScroller.grabGesture(self.scroll.viewport(), QScroller.ScrollerGestureType.TouchGesture)
        self.list_host = QWidget()
        self.list_host.setStyleSheet(f"background: {theme.INK_2.name()};")
        self.rows = QVBoxLayout(self.list_host)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(0)
        self.rows.addStretch(1)
        self.scroll.setWidget(self.list_host)
        self.box.addWidget(self.scroll, 1)

        # The log keeps growing while the page is open: a lamp that drops out
        # should appear without anyone leaving and coming back.
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._pull)

    def start(self) -> None:
        self._pull()
        self.timer.start(2000)
        QTimer.singleShot(60, self._to_bottom)

    def stop(self) -> None:
        self.timer.stop()

    def hideEvent(self, event) -> None:  # noqa: N802
        self.timer.stop()
        super().hideEvent(event)

    def _pull(self) -> None:
        items = self.events.recent(400, self.last_id)
        for item in items:
            self.last_id = item["id"]
            row = QLabel()
            stamp = time.strftime("%H:%M:%S", time.localtime(item["at"]))
            colour = level_colour(item.get("level", "")).name()
            row.setText(f'<span style="color:{theme.FAINT.name()}; '
                        f'font-family:DejaVu Sans Mono">{stamp}</span>'
                        f'&nbsp;&nbsp;<span style="color:{colour}">'
                        f'{_escape(item["text"])}</span>')
            row.setWordWrap(True)
            row.setStyleSheet("font-size: 16px; padding: 9px 4px; "
                              f"border-bottom: 1px solid {theme.LINE.name()};")
            self.rows.insertWidget(self.rows.count() - 1, row)
        while self.rows.count() > 401:
            old = self.rows.takeAt(0)
            if old.widget():
                old.widget().deleteLater()
        if items and self.isVisible():
            QTimer.singleShot(50, self._to_bottom)

    def _to_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _clear(self) -> None:
        count = self.events.clear()
        while self.rows.count() > 1:
            old = self.rows.takeAt(0)
            if old.widget():
                old.widget().deleteLater()
        self.events.add(f"Meldungen gelöscht ({count})")
        self._pull()


def _escape(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
