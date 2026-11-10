"""The guest screen: start, countdown, review, result.

Every measurement is a pixel of the fixed 1920 x 1080 stage. The sequence
itself still lives in BoothSession; this screen only shows its state and calls
its actions - exactly as the web page did, only without a network in between.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImageReader, QPainter
from PySide6.QtWidgets import QWidget

from booth.session import BoothSession, BoothSettings

from . import theme
from .preview import create_preview
from .sheets import LightCard, Overlay, PictureCard, StatusCard, overall
from .widgets import (Banner, Button, CountdownText, Flash, Label, Panel, Picture,
                      RoundedCorners, SvgView, TimeBar, Toast, place, put, put_centered,
                      qr_svg)

log = logging.getLogger(__name__)

SHADOW = QColor(60, 50, 35)

# -- Geometrie der Buehne -----------------------------------------------------------
#: 5 mm stay clear all round (theme.SAFE_MARGIN_PX). Not by shrinking the
#: stage - that would stop the dimmer behind an enlarged picture covering the
#: screen - but by insetting the elements that far.
RAND = theme.SAFE_MARGIN_PX
BAR_X, BAR_Y, BAR_H = RAND, RAND, 68
#: The live image. It comes within 32 pixels of the galleries and leaves room
#: at the bottom for the START button, which floats over it.
#:
#: Exactly 3:2 (1392 / 928), which matters more than it looks. The widget
#: letterboxes whatever does not fit, and at 1394 x 930 the sensor's 3:2 frame
#: was 0.67 pixels too short - which came out as a single bright line along the
#: top edge. Any size here must divide cleanly by 3:2.
PREVIEW = (264, 108, 1392, 928)
#: Corner radius of the live image. Big enough to actually be seen.
PREVIEW_RADIUS = 48
#: During the shot: as large as it goes, but always 3:2.
PREVIEW_FULL = (192, RAND, 1536, 1024)
#: The finished sheet during review and at the end. Smaller than the live
#: image, because labelled buttons sit underneath it - and they must not cover
#: the picture that is being decided about.
STAGE_TOP, STAGE_H = 108, 790
ACTIONS_CY = 974
GALLERY_W, GALLERY_H, GALLERY_GAP = 192, 128, 12
#: The galleries line up with the bar buttons above them: flush left with the
#: status button, flush right with the plus button.
GALLERY_LEFT_X = RAND
GALLERY_RIGHT_X = 1920 - RAND - GALLERY_W
ROUND = 136
ROW_GAP = 38
THUMB_W, THUMB_H, THUMB_FRAME = 112, 75, 4

#: States in which only the picture matters: no buttons, no gallery.
ONLY_PICTURE = ("ready", "countdown", "capturing")

#: States in which a run is under way and nothing has been decided yet. The
#: abort button only appears there - review and result already have labelled
#: buttons that say the same thing more plainly.
ABBRECHBAR = ("ready", "await", "countdown", "capturing", "composing")


class _Bridge(QObject):
    """Bringt Ergebnisse aus Hintergrund-Threads zurueck in die Oberflaeche."""

    toast = Signal(str)
    status = Signal(dict)


class GuestScreen(QWidget):
    def __init__(self, parent: QWidget, backend, on_settings=None) -> None:
        super().__init__(parent)
        self.setFixedSize(theme.STAGE_W, theme.STAGE_H)
        self.backend = backend
        self.session: BoothSession = backend.session
        self.on_settings = on_settings
        #: Wird bei jedem Zustandswechsel gerufen: (neu, vorher).
        self.on_state_change = None

        self.state: str | None = None
        self.view: dict[str, Any] = {}
        self.settings = BoothSettings.from_config(backend.config)
        self.status: dict[str, Any] = {}
        self.gallery_key: tuple = ()
        self.gallery_read = 0.0
        self.selected: Path | None = None
        self.thumb_key: tuple = ()
        self.qr_for: tuple[str, str] | None = None
        self.links_checked = 0.0
        self.printing = False
        self.buttons_key: tuple = ()
        self.blink_on = True
        self._aspects: dict[Path, float] = {}

        self.bridge = _Bridge()
        self.bridge.toast.connect(self._toast)
        self.bridge.status.connect(self._on_status)

        self._build()
        self._layout_bar()

        self.poll = QTimer(self)
        self.poll.timeout.connect(self._tick)
        self.poll.start(100)
        #: The digit is driven by the clock, not by the poll - it jumped otherwise.
        self.count_timer = QTimer(self)
        self.count_timer.timeout.connect(self._update_count)
        self.blink = QTimer(self)
        self.blink.timeout.connect(self._blink)
        self.blink.start(800)

        threading.Thread(target=self._status_loop, name="ui-status", daemon=True).start()
        self._tick()

    # -- Aufbau ---------------------------------------------------------------------
    def _build(self) -> None:
        bar_shadow = (SHADOW, 0.08, 2, 8)
        self.lamp = Button(self, shadow=bar_shadow, on_click=self._on_lamp)
        self.lamp.dot = theme.FAINT
        self.gear = Button(self, icon=theme.ICON_GEAR, icon_ratio=0.48, shadow=bar_shadow,
                           on_click=self._on_settings)
        self.light_down = Button(self, text="−", font=theme.font(24), shadow=bar_shadow,
                                 on_click=lambda: self._light_step(-1))
        self.light_value = Button(self, text="", font=theme.font(16, mono=True), fg=theme.DIM,
                                  shadow=bar_shadow, on_click=self._on_light_value)
        self.light_up = Button(self, text="+", font=theme.font(24), shadow=bar_shadow,
                               on_click=lambda: self._light_step(1))
        self.bar = [self.lamp, self.gear, self.light_down, self.light_value, self.light_up]
        self._sync_light_buttons()

        self.gallery: list[Picture] = []

        self.preview = create_preview(self, self.backend.camera)
        place(self.preview, *PREVIEW)
        # Round off the corners of the live image. Sits above the image and
        # below everything that stands on it.
        self.preview_corners = RoundedCorners(self, radius=PREVIEW_RADIUS)
        place(self.preview_corners, *PREVIEW)
        # Explicitly raised: the live image is underneath and already exists,
        # otherwise the corners would have no effect.
        self.preview_corners.raise_()
        self.count = CountdownText(self)
        place(self.count, *PREVIEW)
        # On a Pi with no real camera: do not quietly show a test pattern,
        # say what is going on.
        self.camera_banner = Banner(self, "Kamera nicht erreichbar",
                                    "Die Box versucht es gleich noch einmal. Hilft das nicht: "
                                    "Kamerakabel prüfen und die Box neu starten.")
        place(self.camera_banner, PREVIEW[0] + 175, PREVIEW[1] + 300, PREVIEW[2] - 350, 300)
        self.camera_banner.setVisible(self.camera_lost())
        # No stick, no pictures. This has to sit above everything, the live
        # image and the buttons included - otherwise somebody taps START and
        # wonders why nothing happens.
        self.usb_banner = Banner(
            self, "USB-Stick fehlt",
            "Die Bilder gehören euch und ihr nehmt sie auf dem Stick mit. "
            "Ohne ihn macht die Box keine Aufnahmen. Steckt den Stick an, "
            "dann geht es sofort weiter.")
        place(self.usb_banner, theme.STAGE_W / 2 - 540, theme.STAGE_H / 2 - 190, 1080, 380)
        self.usb_banner.hide()

        self.result = Picture(self, radius=5, cover=False, shadow_alpha=0.22,
                              background=theme.INK_2)
        self.result.hide()

        self.qr_panel = Panel(self)
        self.qr = SvgView(self.qr_panel)
        place(self.qr, 14, 14, 190, 190)
        self.qr_text = Label(self.qr_panel, theme.font(16), theme.DIM)
        self.qr_text.set_text("Scannen und\naufs Handy holen")
        place(self.qr_text, 0, 212, 218, 46)
        self.qr_panel.resize(218, 270)
        self.qr_panel.hide()

        self.thumbs: list[Picture] = []

        self.kicker = Label(self, theme.font(15, mono=True, spacing=3), theme.AMBER_SOFT)
        self.start_btn = Button(self, shape="pill", bg=theme.AMBER, fg=theme.START_TEXT, border=None,
                                font=theme.font(57, bold=True), text="START",
                                subfont=theme.font(24, weight=QFont.Weight.DemiBold),
                                shadow=(theme.AMBER, 0.28, 6, 18), on_click=self._on_start)
        round_shadow = (SHADOW, 0.16, 6, 18)
        self.redo_btn = Button(self, shape="circle", bg=theme.INK_2, fg=theme.BONE,
                               border=theme.LINE, border_w=2, icon=theme.ICON_REDO,
                               icon_ratio=0.48, shadow=round_shadow,
                               on_click=lambda: self._act("redo_last"))
        self.keep_btn = Button(self, shape="circle", bg=theme.SAGE, fg=theme.SAGE_TEXT, border=None,
                               icon=theme.ICON_CHECK, shadow=round_shadow,
                               on_click=lambda: self._act("keep"))
        self.discard_btn = Button(self, shape="circle", bg=theme.INK_2, fg=theme.ERR,
                                  border=theme.LINE, border_w=2, icon=theme.ICON_TRASH,
                                  shadow=round_shadow, on_click=lambda: self._act("discard"))
        self.print_btn = Button(self, shape="pill", bg=theme.SAGE, fg=theme.SAGE_TEXT, border=None,
                                font=theme.font(30, bold=True), text="Drucken",
                                subfont=theme.font(15, weight=QFont.Weight.DemiBold),
                                shadow=None, on_click=self._on_print)
        # Abort, top right. One press, two meanings: if a shot is running it
        # alone is thrown away and the series waits on; if none is running the
        # series is meant. Deliberately without a confirmation - that would
        # cost exactly the seconds you press the button for.
        self.abort_btn = Button(self, shape="circle", bg=theme.with_alpha(theme.BONE, 0.72),
                                fg=QColor("#FFFFFF"), border=None, icon=theme.ICON_CLOSE,
                                icon_ratio=0.38, shadow=bar_shadow,
                                on_click=self._on_abort)
        place(self.abort_btn, theme.STAGE_W - RAND - 72, RAND, 72, 72)
        self.abort_btn.hide()
        self.done_btn = self._ghost("Fertig", lambda: self._act("cancel"))
        self.back_btn = self._ghost("Zurück", lambda: self._act("cancel"))
        self.layout_btns: list[Button] = []
        self.actions = [self.kicker, self.start_btn, self.redo_btn, self.keep_btn,
                        self.discard_btn, self.print_btn, self.done_btn, self.back_btn]
        for w in self.actions:
            w.hide()

        self.timebar = TimeBar(self)
        place(self.timebar, RAND, theme.STAGE_H - RAND - 4,
              theme.STAGE_W - 2 * RAND, 4)
        self.flash = Flash(self)
        place(self.flash, 0, 0, theme.STAGE_W, theme.STAGE_H)

        # The panels at top left and top right sit under the bar, in the same
        # place they had on the web page.
        self.status_overlay = Overlay(self, dim=0.25)
        self.status_card = StatusCard(self.status_overlay)
        self.status_card.move(RAND, 78)
        self.light_overlay = Overlay(self, dim=0.25)
        self.light_card = LightCard(self.light_overlay, self._light_dragged)
        self.light_card.move(theme.STAGE_W - RAND - self.light_card.width(), 78)
        self.picture_overlay = Overlay(self, dim=0.55)
        self.picture_card = PictureCard(self.picture_overlay, on_print=self._print)
        # Close as a round red button in the top right corner - that is where
        # people look for it, and at 88 pixels (about 15 mm) any finger hits it.
        self.picture_close = Button(self.picture_overlay, shape="circle", bg=theme.ERR,
                                    fg=QColor("#FFFFFF"), border=None, icon=theme.ICON_CLOSE,
                                    icon_ratio=0.42, shadow=(SHADOW, 0.25, 4, 14),
                                    on_click=lambda: self.picture_overlay.close_overlay())
        self.overlays = [self.status_overlay, self.light_overlay, self.picture_overlay]
        #: The light follows the finger at once; it is saved only once it rests.
        self.light_commit = QTimer(self)
        self.light_commit.setSingleShot(True)
        self.light_commit.setInterval(600)
        self.light_commit.timeout.connect(self._light_commit)
        self.light_pending: int | None = None

        self.toast = Toast(self)

    def _ghost(self, text: str, on_click) -> Button:
        return Button(self, shape="pill", bg=None, fg=theme.DIM, border=theme.LINE, border_w=2,
                      font=theme.font(20), text=text, shadow=None, on_click=on_click)

    def _sync_light_buttons(self) -> None:
        """The three light buttons only exist when the box can dim the lamp.

        With a bought lamp that nobody can control remotely, they disappear. A
        control that does nothing confuses more than it helps. Switch over in
        the settings and they are back immediately.
        """
        dimmbar = bool(getattr(self.backend.light, "dimmable", True))
        for knopf in (self.light_down, self.light_value, self.light_up):
            drin = knopf in self.bar
            if dimmbar and not drin:
                self.bar.append(knopf)
            elif not dimmbar and drin:
                self.bar.remove(knopf)
                knopf.hide()

    def _layout_bar(self) -> None:
        BW, GAP, WERT = 76, 14, 120
        put(self.lamp, BAR_X, BAR_Y, BW, BAR_H)
        put(self.gear, BAR_X + BW + GAP, BAR_Y, BW, BAR_H)
        right = theme.STAGE_W - BAR_X
        put(self.light_up, right - BW, BAR_Y, BW, BAR_H)
        put(self.light_value, right - BW - GAP - WERT, BAR_Y, WERT, BAR_H)
        put(self.light_down, right - BW - GAP - WERT - GAP - BW, BAR_Y, BW, BAR_H)
        self._show_light(self.backend.idle_light())

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), theme.INK)
        p.end()

    # -- Takt -----------------------------------------------------------------------
    def _zeige_stick_hinweis(self) -> None:
        """Show and hide the notice as the stick comes and goes."""
        usb = self.status.get("usb") or {}
        fehlt = usb.get("present") is False
        if fehlt == self.usb_banner.isVisible():
            return
        self.usb_banner.setVisible(fehlt)
        if fehlt:
            self.usb_banner.raise_()
        else:
            # Under the notice lies the live image, straight off the GPU. It
            # does not repaint itself when something above it disappears -
            # the outline would stay behind otherwise.
            self.preview.update()
            self.update()

    def _tick(self) -> None:
        self.session.tick()
        view = self.session.view()
        self.view = view
        state = view["state"]
        if state != self.state:
            previous, self.state = self.state, state
            self.settings = BoothSettings.from_config(self.backend.config)
            self._enter(state, previous)
        self._zeige_stick_hinweis()
        self._render(view)

    def camera_lost(self) -> bool:
        """Auf echter Hardware, aber mit der Ersatzkamera unterwegs."""
        return not self.backend.mock and getattr(self.backend.camera, "backend", "") == "mock"

    def _enter(self, state: str, previous: str | None) -> None:
        if self.on_state_change is not None:
            self.on_state_change(state, previous)
        # Loest jemand am Knopf aus, waehrend ein Fenster offen ist, gehoert
        # der Schirm wieder dem Ablauf.
        if previous is not None:
            for overlay in self.overlays:
                overlay.close_overlay()
        only_picture = state in ONLY_PICTURE
        # Status, settings and light exist only on the start screen. Halfway
        # through a series they distract, and tapping the gear there aborts
        # nothing - it only puzzles.
        for w in self.bar:
            w.setVisible(state == "idle")
        self.abort_btn.setVisible(state in ABBRECHBAR)
        self.abort_btn.raise_()
        if state == "capturing" and previous != "capturing":
            self.flash.fire()
        if state == "countdown":
            self.count_timer.start(20)
        else:
            self.count_timer.stop()

        rahmen = PREVIEW_FULL if only_picture else PREVIEW
        place(self.preview, *rahmen)
        place(self.preview_corners, *rahmen)
        place(self.count, *rahmen)
        showing_result = state in ("review", "done")
        # With no real camera, no test pattern for the guests - just the notice.
        bild_sichtbar = not showing_result and not self.camera_lost()
        self.preview.setVisible(bild_sichtbar)
        # The same condition, not isVisible() of the live image: that used to
        # sit here one pass too early, and while the window was not open yet
        # it reported False regardless. The corners stayed invisible.
        self.preview_corners.setVisible(bild_sichtbar)
        self.preview_corners.raise_()
        self.count.setVisible(state in ONLY_PICTURE)
        if state == "ready":
            self.count.set_text("Stellt euch auf!", medium=True)
        elif state == "capturing":
            self.count.set_text("0")
        elif state != "countdown":
            self.count.set_text("")
        if state == "countdown":
            self._update_count()

        if state != "done":
            self.selected = None
            self.thumb_key = ()
            self.qr_for = None
            self.qr_panel.hide()
            for t in self.thumbs:
                t.hide()
        if state == "idle":
            self.gallery_key = ()
        else:
            for g in self.gallery:
                g.hide()
        self.buttons_key = ()
        self.flash.raise_()
        for overlay in self.overlays:
            overlay.raise_()
        self.toast.raise_()

    def _render(self, view: dict[str, Any]) -> None:
        state = view["state"]
        if state == "idle":
            self._render_gallery()
        if state in ("review", "done"):
            self._render_result(view)
        else:
            self.result.hide()
        self._render_actions(view)
        self._render_timebar(view)

    # -- Countdown ------------------------------------------------------------------
    def _update_count(self) -> None:
        shutter_at = self.view.get("shutter_at") if self.view else None
        if self.state != "countdown" or shutter_at is None:
            return
        rest = shutter_at - time.monotonic()
        self.count.set_text(str(max(0, math.ceil(rest))))

    # -- Galerie --------------------------------------------------------------------
    def _render_gallery(self) -> None:
        settings = self.settings
        if not settings.gallery_enabled:
            if self.gallery_key != ("off",):
                self.gallery_key = ("off",)
                for g in self.gallery:
                    g.hide()
            return
        # The list lives on the SD card. Re-reading it ten times a second
        # only costs - new pictures appear every few seconds at best, and
        # going back to the start screen reads it immediately anyway.
        now = time.monotonic()
        if self.gallery_key and now - self.gallery_read < 2.0:
            return
        self.gallery_read = now
        per_side = max(1, int(settings.gallery_count or 6))
        pictures: list[Path] = []
        for entry in self.session.recent(per_side * 2):
            result = self.session.result_dir / Path(entry["result_url"]).name
            pictures.append(result)
            # A single-shot session yields exactly one picture. Newest first:
            # the sheet is made after the shots, the last one after the first.
            shots = [self.session.capture_dir / Path(u).name for u in entry.get("shot_urls", [])]
            if len(shots) > 1:
                pictures.extend(reversed(shots))
        pictures = pictures[:per_side * 2]
        key = tuple(pictures)
        if key == self.gallery_key:
            return
        self.gallery_key = key

        while len(self.gallery) < len(pictures):
            pic = Picture(self, radius=7, cover=True, shadow_alpha=0.14)
            pic.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            pic.clicked.connect(lambda _=False, p=pic: self._view_picture(p.path))
            pic.stackUnder(self.flash)
            self.gallery.append(pic)
        # Newest at top right, the next ones below it; the rest down the left.
        right, left = pictures[:per_side], pictures[per_side:per_side * 2]
        index = 0
        for column, x in ((right, GALLERY_RIGHT_X), (left, GALLERY_LEFT_X)):
            height = len(column) * GALLERY_H + max(0, len(column) - 1) * GALLERY_GAP
            top = PREVIEW[1] + PREVIEW[3] / 2 - height / 2
            for row, path in enumerate(column):
                pic = self.gallery[index]
                index += 1
                pic.set_path(path)
                put(pic, x, top + row * (GALLERY_H + GALLERY_GAP), GALLERY_W, GALLERY_H)
                pic.show()
        for pic in self.gallery[index:]:
            pic.hide()

    # -- Ergebnis -------------------------------------------------------------------
    def _render_result(self, view: dict[str, Any]) -> None:
        result: Path | None = view.get("result_path")
        if result is None:
            self.result.hide()
            return
        shots = [p for p in view.get("shot_paths") or []]
        state = view["state"]
        # With a single shot the sheet IS the photograph; showing both would
        # mean putting the same picture up twice.
        choices = [result, *shots] if (state == "done" and len(shots) >= 2) else []
        if self.selected is None or (choices and self.selected not in choices):
            self.selected = result
        link = self._link_for(self.selected) if state == "done" else None

        stage_h = STAGE_H
        if choices:
            stage_h = STAGE_H - (12 + THUMB_H + 2 * THUMB_FRAME) - 26
        # The picture area with the QR box beside it, centred as a group.
        qr_w = 218 if link else 0
        gap = 31 if link else 0
        max_w = theme.STAGE_W - 2 * 58 - qr_w - gap
        img_w, img_h = self._fit(self.selected, max_w, stage_h)
        group_w = img_w + gap + qr_w
        left = (theme.STAGE_W - group_w) / 2
        cy = STAGE_TOP + stage_h / 2
        self.result.set_path(self.selected)
        put(self.result, left, cy - img_h / 2, img_w, img_h)
        self.result.show()

        if link:
            self._show_qr(self.selected, link)
            place(self.qr_panel, left + img_w + gap, cy - 135, 218, 270)
            self.qr_panel.show()
        else:
            self.qr_panel.hide()

        key = tuple(choices)
        if key != self.thumb_key:
            self.thumb_key = key
            while len(self.thumbs) < len(choices):
                pic = Picture(self, radius=7, cover=True, shadow_alpha=0,
                              frame_colour=theme.AMBER, frame_w=THUMB_FRAME)
                pic.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
                pic.clicked.connect(lambda _=False, p=pic: self._select(p.path))
                pic.stackUnder(self.flash)
                self.thumbs.append(pic)
            full_w = THUMB_W + 2 * THUMB_FRAME
            full_h = THUMB_H + 2 * THUMB_FRAME
            row_w = len(choices) * full_w + max(0, len(choices) - 1) * 10
            x = (theme.STAGE_W - row_w) / 2
            y = STAGE_TOP + stage_h + 26 + 12
            for i, path in enumerate(choices):
                pic = self.thumbs[i]
                pic.set_path(path)
                place(pic, x + i * (full_w + 10), y, full_w, full_h)
                pic.show()
            for pic in self.thumbs[len(choices):]:
                pic.hide()
        for pic in self.thumbs[:len(choices)]:
            pic.set_selected(pic.path == self.selected)

    def _fit(self, path: Path | None, max_w: float, max_h: float) -> tuple[float, float]:
        """So gross wie moeglich in max_w x max_h, im Seitenverhaeltnis des Bildes."""
        aspect = self._aspect(path)
        if aspect is None:
            return max_w, max_h
        if max_w / max_h > aspect:
            return max_h * aspect, max_h
        return max_w, max_w / aspect

    def _aspect(self, path: Path | None) -> float | None:
        if path is None:
            return None
        aspect = self._aspects.get(path)
        if aspect is None:
            size = QImageReader(str(path)).size()
            if not size.isValid() or size.height() == 0:
                return None
            aspect = self._aspects[path] = size.width() / size.height()
        return aspect

    def _select(self, path: Path) -> None:
        """Eine Miniatur antippen: dieses Bild steht gross in der Mitte."""
        self.selected = path
        self._render(self.view)

    def _link_for(self, path: Path | None) -> str | None:
        if path is None:
            return None
        # Der Link entsteht erst nach dem Hochladen. Einmal je Sekunde nachsehen
        # genuegt; die Datei jedes Mal zu lesen waere Arbeit ohne Nutzen.
        now = time.monotonic()
        if self.qr_for and self.qr_for[0] == path.name and now - self.links_checked < 1.0:
            return self.qr_for[1]
        self.links_checked = now
        return self.backend.link_for(path.name)

    def _show_qr(self, path: Path, link: str) -> None:
        if self.qr_for == (path.name, link):
            return
        self.qr_for = (path.name, link)
        self.qr.set_svg(qr_svg(link))

    # -- Knoepfe unten --------------------------------------------------------------
    def _render_actions(self, view: dict[str, Any]) -> None:
        state = view["state"]
        shot, shots = view.get("shot", 0), view.get("shots", 0)
        n_taken = len(view.get("shot_paths") or [])
        printer = bool(self.status.get("printer_ok"))
        key = (state, shot, shots, n_taken, printer, self.settings.printing_enabled,
               view.get("error"))
        if key == self.buttons_key:
            return
        self.buttons_key = key
        for w in self.actions + self.layout_btns:
            w.hide()
        self.kicker.set_text("")

        row: list[tuple[QWidget, float, float]] = []
        if state == "idle" and self.camera_lost():
            # Ohne Kamera wuerde ein Testbild fotografiert, gedruckt und
            # hochgeladen. Lieber gar kein Start.
            pass
        elif state == "idle":
            layouts = self.session.available_layouts()
            count = layouts[0]["shots"] if len(layouts) == 1 else 0
            row.append(self._start_sized(self._counter(1, count)))
        elif state == "await":
            row.append(self._start_sized(self._counter(shot, shots)))
            if n_taken:
                row.append((self.redo_btn, ROUND, ROUND))
        elif state == "review":
            row += [(self.keep_btn, ROUND, ROUND), (self.discard_btn, ROUND, ROUND)]
        elif state == "done":
            can = printer and self.settings.printing_enabled
            reason = "" if can else ("in den Einstellungen ausgeschaltet"
                                     if not self.settings.printing_enabled
                                     else "kein Drucker angeschlossen")
            self.print_btn.set_text("Drucken", reason)
            self.print_btn.setEnabled(can)
            self.print_btn.bg = theme.SAGE if can else theme.INK_3
            self.print_btn.fg = theme.SAGE_TEXT if can else theme.FAINT
            size = self.print_btn.natural_size(60, 22)
            row.append((self.print_btn, size.width(), size.height()))
            size = self.done_btn.natural_size(44, 18)
            row.append((self.done_btn, size.width(), size.height()))
        elif state == "choose":
            self.kicker.set_text("WAS SOLL ES WERDEN?")
            layouts = self.session.available_layouts()
            while len(self.layout_btns) < len(layouts):
                btn = self._ghost("", None)
                btn.layout_id = None
                btn.clicked.connect(lambda _=False, b=btn: self._act("start", b.layout_id))
                self.layout_btns.append(btn)
            for btn, lay in zip(self.layout_btns, layouts):
                btn.set_text(lay["name"])
                btn.layout_id = lay["id"]
                size = btn.natural_size(44, 18)
                row.append((btn, size.width(), size.height()))
        elif state == "failed":
            self.kicker.set_text((view.get("error") or "Da ging etwas schief").upper())
            size = self.back_btn.natural_size(44, 18)
            row.append((self.back_btn, size.width(), size.height()))

        if not row:
            return
        total = sum(w for _, w, _ in row) + ROW_GAP * (len(row) - 1)
        x = (theme.STAGE_W - total) / 2
        # While the live image runs, the button row floats over it - like the
        # shutter of a camera app. That gives the image the full height. Not
        # during review or at the end: there a finished picture is being judged,
        # and a button on top of it covers exactly the face.
        schwebt = state in ("idle", "await")
        cy = ACTIONS_CY
        if schwebt:
            cy = PREVIEW[1] + PREVIEW[3] - 28 - max(h for _, _, h in row) / 2
        if self.kicker.text:
            tallest = max(h for _, _, h in row)
            cy = ACTIONS_CY + 14
            place(self.kicker, 0, cy - tallest / 2 - 12 - 22, theme.STAGE_W, 22)
            self.kicker.show()
        for widget, w, h in row:
            put_centered(widget, x + w / 2, cy, w, h)
            widget.show()
            x += w + ROW_GAP

    def _start_sized(self, subline: str) -> tuple[QWidget, float, float]:
        self.start_btn.set_text("START", subline)
        # Less padding when there is a subline, or the button hits the bottom.
        size = self.start_btn.natural_size(170, 26 if subline else 40)
        return self.start_btn, size.width(), size.height()

    @staticmethod
    def _counter(number: int, total: int) -> str:
        return f"Bild {number} von {total}" if total > 1 else ""

    def _render_timebar(self, view: dict[str, Any]) -> None:
        totals = {"review": self.settings.review_s, "done": self.settings.done_s,
                  "await": self.settings.await_s}
        deadline = view.get("deadline")
        total = totals.get(view["state"])
        if deadline is None or not total:
            self.timebar.set_fraction(0)
            return
        self.timebar.set_fraction((deadline - time.monotonic()) / total)

    # -- Handlungen -----------------------------------------------------------------
    def _act(self, name: str, *args) -> dict[str, Any]:
        try:
            result = getattr(self.session, name)(*args)
        except Exception as exc:  # noqa: BLE001 - one failure must not take the screen down
            log.exception("Action %s failed", name)
            result = {"ok": False, "error": str(exc)}
        if isinstance(result, dict) and result.get("ok") is False and result.get("error"):
            self._toast(result["error"])
        self._tick()
        return result if isinstance(result, dict) else {}

    def _on_abort(self) -> None:
        """Just the shot or the whole series - the session decides which.

        In the first case the box says what happened. Otherwise you are left
        in front of a screen waiting for the shutter again, with no way of
        knowing whether the press registered at all.
        """
        if self._act("abort").get("scope") == "shot":
            self._toast("Aufnahme abgebrochen – noch einmal auslösen, oder ✕ zum Beenden")

    def _on_start(self) -> None:
        if self.state == "await":
            self._act("next_shot")
        else:
            self._act("start")

    def _on_print(self) -> None:
        if self.selected is not None:
            self._print(self.selected)

    def _print_state(self) -> tuple[bool, str]:
        if not self.settings.printing_enabled:
            return False, "in den Einstellungen ausgeschaltet"
        if not self.status.get("printer_ok"):
            drucker = self.status.get("printer") or {}
            if drucker.get("queue") and drucker.get("attached") is False:
                return False, "Drucker eingerichtet, aber nicht angesteckt"
            return False, "kein Drucker angeschlossen"
        return True, ""

    def _print(self, path: Path) -> None:
        if self.printing:
            return
        self.printing = True
        name = path.name

        def run() -> None:
            try:
                res = self.backend.print_picture(name)
                self.bridge.toast.emit("Wird gedruckt …" if res.get("ok")
                                       else res.get("error") or "Druck fehlgeschlagen")
            finally:
                self.printing = False

        threading.Thread(target=run, name="ui-print", daemon=True).start()

    def _light_step(self, direction: int) -> None:
        current = round(self.backend.idle_light() * 100)
        value = max(0, min(100, current + direction * 5))
        self._show_light(self.backend.set_idle_light(value / 100))

    def _show_light(self, value: float) -> None:
        self.light_value.set_text(f"{round(value * 100)} %")

    def _on_light_value(self) -> None:
        self.light_card.set_value(round(self.backend.idle_light() * 100))
        self.light_overlay.open()
        self.toast.raise_()

    def _light_dragged(self, percent: int) -> None:
        self._show_light(percent / 100)
        if self.session.state in ("idle", "await", "choose"):
            self.session._set_light(percent / 100)
        self.light_pending = percent
        self.light_commit.start()

    def _light_commit(self) -> None:
        if self.light_pending is not None:
            self._show_light(self.backend.set_idle_light(self.light_pending / 100))
            self.light_pending = None

    def _on_lamp(self) -> None:
        self.status_card.set_status(self.status)
        self.status_overlay.open()
        self.toast.raise_()

    def _view_picture(self, path: Path | None) -> None:
        """Ein Bild aus der Galerie gross, mit QR-Code und Drucken - ohne den Ablauf."""
        if path is None or not path.exists():
            return
        can, reason = self._print_state()
        self.picture_card.show_picture(path, self._aspect(path) or 1.5,
                                       self.backend.link_for(path.name), can, reason)
        card = self.picture_card
        card.move((theme.STAGE_W - card.width()) // 2, (theme.STAGE_H - card.height()) // 2)
        size = 88
        put(self.picture_close, card.x() + card.width() - size / 2 - 12,
            card.y() - size / 2 + 12, size, size)
        self.picture_close.raise_()
        self.picture_overlay.open()
        self.toast.raise_()

    def _on_settings(self) -> None:
        if self.on_settings is not None:
            self.on_settings()

    def refresh_after_settings(self) -> None:
        """Zurueck aus den Einstellungen: alles neu lesen, was sich geaendert haben kann."""
        self.settings = BoothSettings.from_config(self.backend.config)
        self.gallery_key = ()
        self.buttons_key = ()
        self._sync_light_buttons()
        self._layout_bar()
        for knopf in self.bar:
            knopf.setVisible(self.state == "idle")
        self._show_light(self.backend.idle_light())
        self._tick()

    def _toast(self, text: str) -> None:
        self.toast.show_text(text)

    # -- Zustand der Box ------------------------------------------------------------
    def _status_loop(self) -> None:
        """Printer, USB stick, temperature - own thread, every three seconds.

        Some of these checks start processes and occasionally take a second.
        Doing that on the paint tick is what would make the countdown stutter.
        """
        while True:
            try:
                self.bridge.status.emit(self.backend.status())
            except Exception:  # noqa: BLE001
                log.debug("Status poll failed", exc_info=True)
            time.sleep(3)

    def _on_status(self, status: dict) -> None:
        self.status = status
        if self.status_overlay.isVisible():
            self.status_card.set_status(status)
        self.lamp.dot = {"ok": theme.OK, "warn": theme.WARN, "bad": theme.ERR}[overall(status)]
        self.lamp.update()

    def _blink(self) -> None:
        """A fault blinks, so it is noticed in passing too."""
        if not self.status or overall(self.status) != "bad":
            return
        self.blink_on = not self.blink_on
        self.lamp.dot = theme.ERR if self.blink_on else theme.with_alpha(theme.ERR, 0.35)
        self.lamp.update()
