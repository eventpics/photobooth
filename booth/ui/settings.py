"""The settings area, native.

Laid out like the old settings page: the sheet preview with caption, layout
and background at the top, then camera, EventPics, the remaining groups and
"Erweitert". Every change takes effect at once; there is no save button anyone
could forget to press.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea,
                               QScroller, QScrollerProperties, QVBoxLayout, QWidget)

from booth import palette
from booth.admin import apply_settings, read_settings

from . import theme
from .controls import (Card, ChoiceControl, ChooserOverlay, ColourDot,
                       ColourPickerOverlay, ConfirmOverlay,
                       LayoutTile, MenuRow, NumberControl, SchemeTile, SliderControl,
                       SwatchTile,
                       TextControl, Toggle,
                       button, field, grid, label, set_on, style)
from .keyboard import KeyboardOverlay
from .shot import ShotScreen

log = logging.getLogger(__name__)

CONTENT_W = 1644          # 1700 wide with a 28 inset - as on the web page
#: The start page is a list, and a list that stretches 1644 pixels wide leaves
#: the title at one end and the chevron at the other, with nothing between
#: them. Eight entries read better in a column you can take in at once.
MENU_W = 920
#: A fixed set of caption colours. A gradient picker is near impossible to hit
#: with a finger; these go with the sheet backgrounds the box offers.
CAPTION_COLOURS = [("#1E1B18", "Schwarz"), ("#3C3129", "Dunkelbraun"), ("#4A5568", "Schiefer"),
                   ("#8A6A2F", "Gold"), ("#5E7A5A", "Salbei"), ("#9C5B63", "Altrosa"),
                   ("#2F4A6B", "Nachtblau"), ("#FFFFFF", "Weiß")]


#: The sub-pages, in the order they are listed on the start page. Key, title,
#: and the one line underneath it.
#:
#: One long scrolling page had everything on it, which meant finding anything
#: required reading past everything else. A list of eight entries is read in a
#: glance, and each page is then short enough to need no scrolling at all.
PAGES: list[tuple[str, str, str]] = [
    ("picture", "Bild und Druck",
     "Beschriftung, Aufteilung, Hintergrund und Drucken"),
    ("capture", "Kamera und Licht",
     "Einmessen, Testfoto, Belichtung, Fokus und die Leuchte"),
    ("eventpics", "EventPics-Galerie",
     "Zugang, Event und was hochgeladen wird"),
    ("wlan", "WLAN",
     "Netz suchen und verbinden, ohne Kabel und ohne Tastatur"),
    ("flow", "Ablauf",
     "Countdown und wie lange die Box auf etwas wartet"),
    ("colours", "Farben",
     "Farbschema und einzelne Farben der Oberfläche"),
    ("log", "Meldungen",
     "Was die Box gemeldet hat, mit Uhrzeit"),
    ("advanced", "Erweitert",
     "Anschlüsse, DMX, Bluetooth und USB-Stick"),
]

PAGE_TITLES = {key: title for key, title, _ in PAGES}


class _Bridge(QObject):
    preview = Signal(object)
    wlan = Signal(dict)
    swatch = Signal(str, object)
    eventpics = Signal(str, dict)


class Header(QFrame):
    """The bar above every settings page.

    The back button means one thing on a sub-page and another on the start
    page - one step back, or out of the settings entirely. Both read as
    "back", which is what people press without thinking about where they are.
    """

    def __init__(self, on_back: Callable[[], None],
                 on_power: Callable[[], None]) -> None:
        super().__init__()
        self.setObjectName("header")
        # Tall enough for the buttons plus the safe margin above them: nothing
        # you can press comes closer than 5 mm to the edge of the screen, here
        # as everywhere else.
        self.setFixedHeight(theme.SAFE_MARGIN_PX + 58 + 14)
        row = QHBoxLayout(self)
        row.setContentsMargins(theme.SAFE_MARGIN_PX, theme.SAFE_MARGIN_PX,
                               theme.SAFE_MARGIN_PX, 14)
        row.setSpacing(16)
        self.back = button("‹  Zurück", "back", on_back)
        row.addWidget(self.back)
        self.title = label("Einstellungen")
        self.title.setStyleSheet("font-size: 21px; font-weight: 600;")
        row.addWidget(self.title)
        self.saved = label("")
        self.saved.setStyleSheet(f"font-size: 16px; color: {theme.OK_INK.name()};")
        row.addWidget(self.saved)
        row.addStretch(1)
        # Only on the start page. On a sub-page nobody is looking for it, and
        # a filled button next to the settings they are changing invites the
        # one press that cannot be taken back.
        self.power = button("Box herunterfahren", "power", on_power)
        row.addWidget(self.power)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self.saved.setText(""))

    def show_page(self, title: str, start: bool) -> None:
        self.title.setText(title)
        self.back.setText("‹  Zurück" if start else "‹  Einstellungen")
        self.power.setVisible(start)

    def flash(self, text: str = "Gespeichert", bad: bool = False) -> None:
        self.saved.setText(text)
        self.saved.setStyleSheet("font-size: 16px; color: "
                                 f"{(theme.ERR_INK if bad else theme.OK_INK).name()};")
        self.timer.start(1800)


class PreviewImage(QWidget):
    """The sheet, exactly as it would print."""

    def __init__(self) -> None:
        super().__init__()
        self.pixmap: QPixmap | None = None
        self.message = "Vorschau wird erzeugt …"
        self.setMinimumHeight(380)

    def set_path(self, path: Path | None) -> None:
        if path is None:
            self.pixmap = None
            self.message = "Für diese Aufteilung gibt es keine Vorschau."
        else:
            self.pixmap = QPixmap(str(path))
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        area = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.INK_3)
        p.drawRoundedRect(area, 10, 10)
        inner = area.adjusted(18, 18, -18, -18)
        if self.pixmap is None or self.pixmap.isNull():
            p.setPen(theme.FAINT)
            p.setFont(theme.font(14))
            p.drawText(inner, Qt.AlignmentFlag.AlignCenter, self.message)
        else:
            size = self.pixmap.size().scaled(round(inner.width()), round(inner.height()),
                                             Qt.AspectRatioMode.KeepAspectRatio)
            target = QRectF(inner.center().x() - size.width() / 2,
                            inner.center().y() - size.height() / 2, size.width(), size.height())
            p.drawPixmap(target, self.pixmap, QRectF(self.pixmap.rect()))
        p.end()


class SettingsScreen(QWidget):
    def __init__(self, parent: QWidget, backend, on_close: Callable[[], None]) -> None:
        super().__init__(parent)
        self.setObjectName("settingsRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setGeometry(0, 0, theme.STAGE_W, theme.STAGE_H)
        self.setStyleSheet(style())
        self.backend = backend
        self.on_close = on_close
        self.data: dict[str, Any] = {}
        self.controls: dict[str, QWidget] = {}
        self.capture_light = False
        self.bridge = _Bridge()
        self.bridge.preview.connect(self._preview_ready)
        self.bridge.swatch.connect(self._swatch_ready)
        self.bridge.eventpics.connect(self._eventpics_result)
        self.bridge.wlan.connect(self._wlan_ready)
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(300)
        self.preview_timer.timeout.connect(self._compose_preview)
        self.preview_busy = False
        self.preview_again = False
        self.epevents: list[dict[str, Any]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        #: Which page is open. "" is the start page with the list.
        self.page = ""
        self.log_page: Any = None
        self.header = Header(self._back, self._power_ask)
        outer.addWidget(self.header)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self.scroll, 1)
        self._touch_scrolling()

        self.keyboard = KeyboardOverlay(self)
        self.chooser = ChooserOverlay(self)
        self.colour_picker = ColourPickerOverlay(self)
        self.confirm = ConfirmOverlay(self)
        self.shot = ShotScreen(self, backend, on_close=self._shot_closed,
                               on_calibrated=self._calibrated)
        self.camera_slot: QWidget | None = None
        self.hide()

    def _touch_scrolling(self) -> None:
        """Swiping scrolls like a tablet, with no overshoot past the edge.

        Qt's defaults are made for a mouse and feel sluggish under a finger: a
        firm swipe barely moves, because velocity is capped at 0.635 m/s, and
        whatever is moving comes to a stop again quickly. The values below are
        the adjustments for that - each explained on its own, so it is clear
        which way to turn it when it still does not feel right.
        """
        M = QScrollerProperties.ScrollMetric
        viewport = self.scroll.viewport()
        QScroller.grabGesture(viewport, QScroller.ScrollerGestureType.TouchGesture)
        scroller = QScroller.scroller(viewport)
        props = scroller.scrollerProperties()
        off = QScrollerProperties.OvershootPolicy.OvershootAlwaysOff
        props.setScrollMetric(M.VerticalOvershootPolicy, off)
        props.setScrollMetric(M.HorizontalOvershootPolicy, off)
        # Where a tap turns into a drag. Small, so the page follows the very
        # first millimetre. Smaller still and a tap starts to slide.
        props.setScrollMetric(M.DragStartDistance, 0.002)
        # How fast a swipe is allowed to get. Qt caps it at 0.635, which is
        # the main reason it feels weak. Larger = flies further.
        props.setScrollMetric(M.MaximumVelocity, 1.4)
        # How hard the momentum is braked. Smaller = longer glide.
        props.setScrollMetric(M.DecelerationFactor, 0.08)
        # How sluggishly velocity is measured. Smaller = the page picks up
        # momentum faster, but reacts more jitterily.
        props.setScrollMetric(M.DragVelocitySmoothingFactor, 0.6)
        # Below this a swipe counts as a tap and nothing flies at all.
        props.setScrollMetric(M.MinimumVelocity, 0.05)
        # Snap a diagonal swipe onto the stronger axis. Without it a long
        # list drifts sideways while being dragged.
        props.setScrollMetric(M.AxisLockThreshold, 0.7)
        props.setScrollMetric(M.FrameRate, QScrollerProperties.FrameRates.Fps60)
        scroller.setScrollerProperties(props)

    # -- opening ---------------------------------------------------------------------
    def open(self) -> None:
        self.page = ""
        self.data = read_settings(self.backend.config)
        self._build()
        self.raise_()
        self.show()

    def go(self, page: str) -> None:
        """Switch to a sub-page, or back to the list with an empty key."""
        if self.capture_light and page != "capture":
            self._toggle_capture_light()
        self._stop_log()
        self.page = page
        # Fresh values on every switch: a sub-page may have changed something
        # another one shows, and there is no cheap way to know which.
        self.data = read_settings(self.backend.config)
        self._build()
        if page == "picture":
            self._compose_soon(0)
            self._load_swatches()

    def _back(self) -> None:
        if self.page:
            self.go("")
        else:
            self.close_screen()

    def close_screen(self) -> None:
        if self.capture_light:
            self._toggle_capture_light()
        self._stop_log()
        self.keyboard.hide()
        self.chooser.hide()
        self.confirm.hide()
        self.hide()
        self.on_close()

    # -- building --------------------------------------------------------------------
    def _build(self) -> None:
        # The page is rebuilt every time it opens, so it shows what currently
        # applies. The live image goes home first: it may be sitting inside
        # the page that is about to be deleted.
        fenster = self.window()
        if hasattr(fenster, "reclaim_preview"):
            fenster.reclaim_preview()
        old = self.scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        # The slot went with the old page; holding on to it would leave a
        # reference to a widget Qt has already taken down.
        self.camera_slot = None
        self.controls = {}
        content = QWidget()
        content.setObjectName("scrollContent")
        page = QHBoxLayout(content)
        page.setContentsMargins(0, 24, 0, 80)
        column_host = QWidget()
        column_host.setFixedWidth(MENU_W if not self.page else CONTENT_W)
        column = QVBoxLayout(column_host)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(24)
        page.addStretch(1)
        page.addWidget(column_host)
        page.addStretch(1)

        schema = self.data["schema"]
        if not self.page:
            column.addWidget(self._menu_card())
        elif self.page == "picture":
            column.addLayout(self._top_row())
            column.addWidget(self._group_card("Bilder und Druck",
                                              schema.get("Bilder und Druck", [])))
        elif self.page == "capture":
            column.addWidget(self._camera_card(schema.get("Licht", [])))
        elif self.page == "eventpics":
            self.ep_card = self._eventpics_card(schema.get("EventPics-Galerie", []))
            column.addWidget(self.ep_card)
        elif self.page == "wlan":
            column.addWidget(self._wlan_card())
        elif self.page == "flow":
            column.addWidget(self._group_card("Ablauf", schema.get("Ablauf", []),
                                              title=False))
        elif self.page == "colours":
            column.addWidget(self._colours_card())
        elif self.page == "log":
            column.addWidget(self._log_card())
        elif self.page == "advanced":
            for name, fields in self.data["advanced"].items():
                column.addWidget(self._group_card(name, fields))

        column.addStretch(1)
        self.scroll.setWidget(content)
        self.scroll.verticalScrollBar().setValue(0)
        self.header.show_page(PAGE_TITLES.get(self.page, "Einstellungen"), not self.page)
        if self.page == "eventpics":
            self._show_eventpics_card()
        # Only the camera page gets the live image, and only once its slot
        # exists - which is the moment the page has been built.
        if self.page == "capture" and self.camera_slot is not None \
                and hasattr(fenster, "lend_preview"):
            fenster.lend_preview(self.camera_slot)

    def _menu_card(self) -> Card:
        """The start page: nothing but the way on.

        No values and no switches, not even the ones people change most. A
        start page that also settles two things is a page you have to read
        before you can navigate it.
        """
        card = Card()
        card.box.setContentsMargins(28, 10, 28, 14)
        for i, (key, title, note) in enumerate(PAGES):
            row = MenuRow(title, note, last=(i == len(PAGES) - 1))
            row.clicked.connect(lambda _=False, k=key: self.go(k))
            card.box.addWidget(row)
        return card

    def _log_card(self) -> QWidget:
        from .log import LogPage  # noqa: PLC0415

        # Rebuilt with the page, like everything else - but it keeps its own
        # timer, so it has to be told when it is no longer on screen.
        self.log_page = LogPage(self.backend.events)
        self.log_page.start()
        return self.log_page

    def _stop_log(self) -> None:
        """Stop the log page's timer, if there still is a log page.

        Rebuilding a page deletes its widgets, but the attribute pointing at
        this one survives. Touching it afterwards raised "Internal C++ object
        already deleted" and took the settings screen down with it, on the
        way out of the settings of all places.
        """
        seite, self.log_page = self.log_page, None
        if seite is None:
            return
        try:
            seite.stop()
        except RuntimeError:
            pass          # already gone with its page

    def _top_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(24)
        left = Card("So sieht das Bild aus")
        self.preview_image = PreviewImage()
        self.preview_image.setMinimumHeight(640)
        left.box.addWidget(self.preview_image, 1)
        row.addWidget(left, 135)

        right = QVBoxLayout()
        right.setSpacing(24)
        right.addWidget(self._caption_card())
        right.addWidget(self._layout_card())
        right.addWidget(self._background_card())
        right.addStretch(1)
        row.addLayout(right, 100)
        row.setAlignment(left, Qt.AlignmentFlag.AlignTop)
        return row

    def _caption_card(self) -> Card:
        card = Card("Beschriftung")
        event = self.data["event"]
        caption = self.data["caption"]
        self.title_ctl = TextControl(self.keyboard, "Titel", event.get("title", ""), "Anna & Michael")
        self.title_ctl.changed.connect(lambda v: self._save({"event": {"title": v}}, preview=True))
        self.subtitle_ctl = TextControl(self.keyboard, "Untertitel", event.get("subtitle", ""),
                                        "12.07.2026")
        self.subtitle_ctl.changed.connect(lambda v: self._save({"event": {"subtitle": v}},
                                                               preview=True))
        fonts = [(f["id"], f["name"]) for f in self.data["fonts"]]
        self.font_ctl = ChoiceControl(self.chooser, "Schrift", fonts, caption.get("font", "serif"))
        self.font_ctl.changed.connect(lambda v: self._save({"caption": {"font": v}}, preview=True))
        self.size_ctl = NumberControl(self.keyboard, "Größe", float(caption.get("size_mm", 4.5)),
                                      2, 16, step=0.5, unit="mm", decimals=1)
        self.size_ctl.changed.connect(self._size_changed)

        colours = QWidget()
        colour_row = QHBoxLayout(colours)
        colour_row.setContentsMargins(0, 0, 0, 0)
        colour_row.setSpacing(6)
        self.auto_colour = button("Automatisch", "quiet", lambda: self._pick_colour(""))
        colour_row.addWidget(self.auto_colour)
        self.colour_dots: list[ColourDot] = []
        for code, name in CAPTION_COLOURS:
            dot = ColourDot(code, name)
            dot.clicked.connect(lambda _=False, c=code: self._pick_colour(c))
            self.colour_dots.append(dot)
            colour_row.addWidget(dot)
        colour_row.addStretch(1)
        self.colour_hint = label("", "help")
        self._show_colour(caption.get("colour", ""))

        card.box.addWidget(grid([
            field("Titel", "", self.title_ctl),
            field("Untertitel", "", self.subtitle_ctl),
            field("Schrift", "", self.font_ctl),
            field("Größe", "Höhe der Großbuchstaben auf dem 10 × 15 cm Abzug. Das Textfeld "
                  "wächst mit, die Bilder werden entsprechend kleiner.", self.size_ctl),
        ], 2))
        card.box.addSpacing(18)
        card.box.addWidget(label("Farbe"))
        card.box.addSpacing(6)
        card.box.addWidget(colours)
        card.box.addSpacing(4)
        card.box.addWidget(self.colour_hint)
        return card

    def _show_colour(self, colour: str) -> None:
        self.data["caption"]["colour"] = colour
        set_on(self.auto_colour, not colour)
        for dot in self.colour_dots:
            dot.set_selected(dot.colour.lower() == (colour or "").lower())
        self.colour_hint.setText("Feste Farbe" if colour else "Passt sich dem Hintergrund an")

    def _pick_colour(self, colour: str) -> None:
        self._show_colour(colour)
        self._save({"caption": {"colour": colour}}, preview=True)

    def _size_changed(self, value: float) -> None:
        self._save({"caption": {"size_mm": value}}, preview=True)
        # A taller caption band leaves less room for the pictures, and the
        # layout tiles have to show that.
        fresh = read_settings(self.backend.config)["layouts"]
        by_id = {lay["id"]: lay for lay in fresh}
        for tile in self.layout_tiles:
            if tile.layout_data["id"] in by_id:
                tile.set_layout(by_id[tile.layout_data["id"]])

    def _layout_card(self) -> Card:
        card = Card("Aufteilung")
        self.layout_tiles: list[LayoutTile] = []
        for lay in self.data["layouts"]:
            tile = LayoutTile(lay)
            tile.set_selected(lay["id"] == self.data["active_layout"])
            tile.clicked.connect(lambda _=False, lid=lay["id"]: self._pick_layout(lid))
            self.layout_tiles.append(tile)
        card.box.addWidget(grid(self.layout_tiles, 4, 12, 12))
        return card

    def _pick_layout(self, layout_id: str) -> None:
        self.data["active_layout"] = layout_id
        for tile in self.layout_tiles:
            tile.set_selected(tile.layout_data["id"] == layout_id)
        self._save({"active_layout": layout_id}, preview=True)

    def _background_card(self) -> Card:
        card = Card("Hintergrund")
        card.box.addWidget(label("Zu sehen zwischen den Bildern und als Rahmen. Beim randlosen "
                                 "Einzelbild ohne Wirkung.", "sub", wrap=True))
        card.box.addSpacing(12)
        self.swatches: list[SwatchTile] = []
        for bg in self.data["backgrounds"]:
            tile = SwatchTile(bg)
            tile.set_selected(bg["id"] == self.data["active_background"])
            tile.clicked.connect(lambda _=False, bid=bg["id"]: self._pick_background(bid))
            self.swatches.append(tile)
        card.box.addWidget(grid(self.swatches, 5, 10, 10))
        return card

    def _pick_background(self, bg_id: str) -> None:
        self.data["active_background"] = bg_id
        for tile in self.swatches:
            tile.set_selected(tile.bg["id"] == bg_id)
        self._save({"active_background": bg_id}, preview=True)

    def _load_swatches(self) -> None:
        art = [bg["id"] for bg in self.data["backgrounds"] if bg.get("art")]

        def work() -> None:
            for style in art:
                try:
                    self.bridge.swatch.emit(style, self.backend.background_swatch(style))
                except Exception:  # noqa: BLE001
                    log.debug("Swatch %s failed", style, exc_info=True)

        threading.Thread(target=work, name="ui-swatches", daemon=True).start()

    def _swatch_ready(self, style: str, path) -> None:
        for tile in getattr(self, "swatches", []):
            if tile.bg["id"] == style:
                tile.set_pixmap(QPixmap(str(path)))

    # -- camera ----------------------------------------------------------------------
    def _camera_card(self, light_fields: list[dict[str, Any]]) -> Card:
        """Camera and light together, because nobody sets one without the other.

        The lamp sits directly under the live picture: its sliders change the
        light at once, and the effect is in view while the finger is still on
        the slider. The camera's own values go beside it, so that everything
        fits on the screen without scrolling the picture out of sight.
        """
        card = Card()
        row = QHBoxLayout()
        row.setSpacing(22)

        left = QVBoxLayout()
        left.setSpacing(0)
        self.camera_slot = QWidget()
        # Exactly 3:2, like the preview on the guest screen. Anything else and
        # the widget letterboxes the sensor's frame, which shows up as a bright
        # line along one edge.
        self.camera_slot.setFixedSize(576, 384)
        left.addWidget(self.camera_slot, 0, Qt.AlignmentFlag.AlignTop)
        left.addSpacing(22)
        trenner = QFrame()
        trenner.setFixedHeight(1)
        trenner.setStyleSheet(f"background: {theme.LINE.name()};")
        left.addWidget(trenner)
        left.addSpacing(16)
        self.light_fields = light_fields
        self.light_body = QVBoxLayout()
        self.light_body.setContentsMargins(0, 0, 0, 0)
        self.light_body.setSpacing(18)
        left.addLayout(self.light_body)
        self._fill_light()
        left.addStretch(1)
        row.addLayout(left, 0)

        side = QVBoxLayout()
        side.setSpacing(0)
        side.addWidget(label("Stell jemanden auf den späteren Standabstand und lass die Box "
                             "einmessen. Belichtung, Weißabgleich und Fokus werden festgehalten "
                             "und gelten dann den ganzen Abend.", "sub", wrap=True))
        side.addSpacing(14)
        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addWidget(button("Automatisch einmessen", "action", lambda: self._open_shot("calibrate")))
        buttons.addWidget(button("Testfoto", "quiet", lambda: self._open_shot("photo")))
        self.light_btn = button("Aufnahmelicht", "quiet", self._toggle_capture_light)
        buttons.addWidget(self.light_btn)
        buttons.addStretch(1)
        side.addLayout(buttons)
        side.addSpacing(10)
        self.measured = label("", "measured", wrap=True)
        side.addWidget(self.measured)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {theme.LINE.name()};")
        side.addSpacing(8)
        side.addWidget(line)
        side.addSpacing(18)
        for spec in self.data["schema"].get("Kamera", []):
            side.addWidget(self._field(spec))
            side.addSpacing(20)
        side.addStretch(1)
        row.addLayout(side, 1)
        card.box.addLayout(row)
        return card

    def _toggle_capture_light(self) -> None:
        """While aiming, see what it will look like at the moment of the shot.

        Only sets the light, not the stored value: once closed, the modelling
        light applies again.
        """
        self.capture_light = not self.capture_light
        self.backend.set_light_preset("capture" if self.capture_light else "idle")
        if self.light_btn is not None:
            set_on(self.light_btn, self.capture_light)
            self.light_btn.setText("Aufnahmelicht aus" if self.capture_light else "Aufnahmelicht")

    def _open_shot(self, mode: str) -> None:
        self.shot.open(mode)

    def _shot_closed(self) -> None:
        """After a test shot or a calibration, back to the light that was on."""
        if self.capture_light:
            self.backend.set_light_preset("capture")

    def _calibrated(self, values: str) -> None:
        self.measured.setText(values.replace("\n", " · "))
        self.header.flash("Eingemessen")
        # The measured values are in the configuration now; the sliders
        # should show them.
        fresh = read_settings(self.backend.config)["values"]
        for path, ctl in self.controls.items():
            if isinstance(ctl, SliderControl) and fresh.get(path) is not None:
                ctl.set_value(float(fresh[path]))
        self.data["values"] = fresh

    # -- EventPics -------------------------------------------------------------------
    def _eventpics_card(self, fields: list[dict[str, Any]]) -> Card:
        """Everything about the gallery on one card.

        The switch is always there, everything under it only when the switch is
        on - otherwise half the page would be buttons that lead nowhere.
        """
        specs = {spec["key"]: spec for spec in fields}
        card = Card("EventPics-Galerie")
        card.box.addWidget(self._field(specs["enabled"]))
        self.ep_body = QWidget()
        box = QVBoxLayout(self.ep_body)
        box.setContentsMargins(0, 20, 0, 0)
        box.setSpacing(0)
        card.box.addWidget(self.ep_body)

        self.ep_status = label("", "sub", wrap=True)
        box.addWidget(self.ep_status)
        box.addSpacing(14)
        way = QFrame()
        way.setObjectName("keyway")
        way_box = QVBoxLayout(way)
        way_box.setContentsMargins(16, 16, 16, 16)
        way_box.setSpacing(12)
        way_box.addWidget(label("API-Schlüssel", "label"))
        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        self.qr_btn = button("QR-Code scannen", "action", lambda: self._eventpics_task("qr"))
        buttons.addWidget(self.qr_btn)
        buttons.addWidget(button("Vom USB-Stick lesen", "quiet", lambda: self._eventpics_task("usb")))
        buttons.addWidget(button("Eintippen", "quiet", self._type_key))
        buttons.addStretch(1)
        way_box.addLayout(buttons)
        self.qr_hint = label("", "help", wrap=True)
        way_box.addWidget(self.qr_hint)
        box.addWidget(way)
        box.addSpacing(16)
        actions = QHBoxLayout()
        actions.setSpacing(12)
        actions.addWidget(button("Events laden", "action", lambda: self._eventpics_task("events")))
        actions.addWidget(button("Verbindung prüfen", "quiet", lambda: self._eventpics_task("status")))
        actions.addStretch(1)
        box.addLayout(actions)
        box.addSpacing(16)
        ep = self.data["eventpics"]
        self.event_ctl = ChoiceControl(self.chooser, "Event",
                                       [(ep["link_id"], ep["event_title"] or ep["link_id"])]
                                       if ep["link_id"] else [], ep["link_id"])
        self.event_ctl.changed.connect(self._event_chosen)
        self.album_ctl = ChoiceControl(self.chooser, "Album", [("", "Kein Album")], ep["album_id"])
        self.album_ctl.changed.connect(lambda _v: self._save_event())
        self.ep_choice = grid([field("Event", "", self.event_ctl),
                               field("Album", "", self.album_ctl)], 2)
        box.addWidget(self.ep_choice)
        box.addSpacing(18)
        box.addWidget(self._field(specs["upload_shots"]))
        self._eventpics_task("status")
        return card

    def _show_eventpics_card(self) -> None:
        values = read_settings(self.backend.config)["values"]
        self.ep_body.setVisible(bool(values.get("eventpics.enabled")))

    def _type_key(self) -> None:
        self.keyboard.ask_text("API-Schlüssel", "", self._key_typed,
                               hint="Aus deinem EventPics-Konto", secret=True)

    def _key_typed(self, text: str) -> None:
        text = text.strip()
        if text:
            self._save({"values": {"eventpics.api_key": text}})
            self._eventpics_task("status")

    def _eventpics_task(self, what: str) -> None:
        texts = {"qr": "QR-Code wird gesucht … Schlüssel vom Telefon in die Kamera halten.",
                 "usb": "Stick wird gelesen …", "events": "Events werden geladen …",
                 "status": "Verbindung wird geprüft …"}
        self.ep_status.setText(texts[what])
        self.ep_status.setStyleSheet("")
        backend = self.backend

        def work() -> None:
            try:
                if what in ("qr", "usb"):
                    result = backend.eventpics_setup(what)
                elif what == "events":
                    result = backend.eventpics_events()
                else:
                    result = {"ok": True, **backend.eventpics_status()}
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "error": str(exc)}
            self.bridge.eventpics.emit(what, result)

        threading.Thread(target=work, name=f"ui-eventpics-{what}", daemon=True).start()

    def _eventpics_result(self, what: str, result: dict) -> None:
        def status(text: str, bad: bool = False) -> None:
            self.ep_status.setText(text)
            self.ep_status.setStyleSheet(f"color: {theme.ERR_INK.name()};" if bad else "")

        if not result.get("ok"):
            status(result.get("error") or "Fehlgeschlagen", True)
            return
        if what in ("qr", "usb"):
            status(f"Übernommen vom {result.get('quelle', what)}: "
                   f"{', '.join(result.get('uebernommen') or [])}")
            self.epevents = []
            return
        if what == "events":
            self.epevents = result.get("events") or []
            if not self.epevents:
                status("Keine Events im Konto gefunden.", True)
                return
            active = self.backend.config.section("eventpics").get("link_id", "")
            known = any(e["linkId"] == active for e in self.epevents)
            # If the stored event is not in the list, nothing is preselected:
            # otherwise the evening's pictures would quietly go to a different
            # gallery.
            self.event_ctl.set_options([(e["linkId"], e["title"] or e["linkId"])
                                        for e in self.epevents], active if known else "")
            self._fill_albums()
            if known or not active:
                status(f"{len(self.epevents)} Event(s) geladen.")
            else:
                status(f"Das gespeicherte Event ({active}) ist im Konto nicht mehr da. "
                       "Bitte neu wählen.", True)
            return
        self.qr_btn.setVisible(bool(result.get("qr_possible")))
        self.qr_hint.setText(
            "" if result.get("qr_possible") else
            "QR-Erkennung fehlt. Mit „sudo apt install zbar-tools“ nachrüsten. "
            "Sonst den Schlüssel in die Datei fotobox-eventpics.txt auf einem USB-Stick schreiben"
            + (", Stick erkannt." if result.get("usb_present") else "."))
        if not result.get("configured"):
            status("Es fehlt noch der Schlüssel oder das Event.", True)
            return
        queue = result.get("queue") or {}
        status(f"Eingerichtet für {result.get('event_title') or result.get('link_id')} · "
               f"Schlüssel {result.get('api_key_masked')} · {queue.get('done', 0)} geladen, "
               f"{queue.get('pending', 0)} offen"
               + (f" · zuletzt: {queue['last_error']}" if queue.get("last_error") else ""),
               bool(queue.get("last_error")))

    def _selected_event(self) -> dict[str, Any] | None:
        for ev in self.epevents:
            if ev["linkId"] == self.event_ctl.current:
                return ev
        return None

    def _fill_albums(self) -> None:
        ev = self._selected_event() or {}
        active = self.backend.config.section("eventpics").get("album_id", "")
        options = [("", "Kein Album")] + [(a["id"], a["title"] or a["id"])
                                          for a in ev.get("albums") or []]
        self.album_ctl.set_options(options, active if any(o[0] == active for o in options) else "")

    def _event_chosen(self, _value: str) -> None:
        self._fill_albums()
        self._save_event()

    def _save_event(self) -> None:
        ev = self._selected_event()
        if ev is None:
            self.ep_status.setText("Bitte zuerst Events laden und ein Event wählen.")
            return
        self._save({"eventpics": {"link_id": ev["linkId"], "album_id": self.album_ctl.current,
                                  "event_title": ev.get("title", "")}})

    # -- groups ----------------------------------------------------------------------
    def _colours_card(self) -> Card:
        """Scheme first, single colours after.

        Almost everyone stops at the first row. Anyone who does go on changes
        one colour, not eight - so the eight sit underneath as what they are,
        the scheme's own values, and an edited one says so.
        """
        card = Card()
        self.scheme_tiles: list[SchemeTile] = []
        reihe = QHBoxLayout()
        reihe.setSpacing(14)
        for key in theme.SCHEMES:
            tile = SchemeTile(key, theme.SCHEME_NAMES.get(key, key))
            tile.clicked.connect(lambda _=False, k=key: self._pick_scheme(k))
            self.scheme_tiles.append(tile)
            reihe.addWidget(tile)
        reihe.addStretch(1)
        card.box.addLayout(reihe)

        card.box.addSpacing(22)
        card.box.addWidget(label("EINZELNE FARBEN", "h3"))
        card.box.addSpacing(12)
        self.role_dots: dict[str, ColourDot] = {}
        self.role_marks: dict[str, QLabel] = {}
        raster = QGridLayout()
        raster.setHorizontalSpacing(18)
        raster.setVerticalSpacing(14)
        for i, role in enumerate(theme.ROLES):
            dot = ColourDot("#000000", role, size=46)
            dot.clicked.connect(lambda _=False, r=role: self._pick_role(r))
            self.role_dots[role] = dot
            beschriftung = QVBoxLayout()
            beschriftung.setSpacing(0)
            beschriftung.addWidget(label(theme.ROLE_NAMES.get(role, role), "label"))
            marke = label("", "help")
            self.role_marks[role] = marke
            beschriftung.addWidget(marke)
            zelle = QHBoxLayout()
            zelle.setSpacing(12)
            zelle.addWidget(dot)
            zelle.addLayout(beschriftung)
            zelle.addStretch(1)
            wrap = QWidget()
            wrap.setLayout(zelle)
            raster.addWidget(wrap, i // 4, i % 4)
        host = QWidget()
        host.setLayout(raster)
        card.box.addWidget(host)
        card.box.addSpacing(14)
        card.box.addWidget(label(
            "Die übrigen Töne werden daraus gerechnet: Kacheln, Linien, graue "
            "Schrift und die lesbaren Varianten von Grün, Orange und Rot. "
            "Deshalb bleibt Text lesbar, auch auf dunklem Grund.", "help", wrap=True))
        self._show_colours()
        return card

    def _show_colours(self) -> None:
        cfg = self.backend.config.section("theme")
        aktiv = str(cfg.get("scheme") or theme.DEFAULT_SCHEME)
        for tile in self.scheme_tiles:
            tile.set_selected(tile.scheme == aktiv)
        gewaehlt = palette.chosen(self.backend.config)
        for role, dot in self.role_dots.items():
            dot.colour = gewaehlt[role]
            dot.update()
            eigen = bool(str(cfg.get(role) or "").strip())
            self.role_marks[role].setText("eigene Farbe" if eigen else gewaehlt[role])

    def _pick_scheme(self, scheme: str) -> None:
        # A new scheme discards the individual colours. Otherwise a red from
        # the old one would stay behind and nobody could work out where it
        # came from.
        payload = {"theme": {"scheme": scheme}}
        payload["theme"].update({role: "" for role in theme.ROLES})
        self._save(payload)
        self._apply_palette()

    def _pick_role(self, role: str) -> None:
        jetzt = palette.chosen(self.backend.config)[role]
        self.colour_picker.ask(theme.ROLE_NAMES.get(role, role), jetzt,
                               lambda value, r=role: self._role_chosen(r, value))

    def _role_chosen(self, role: str, value: str) -> None:
        self._save({"theme": {role: value}})
        self._apply_palette()

    def _apply_palette(self) -> None:
        """Put the new colours on screen without a restart.

        Everything paints straight from the live colour objects, so rewriting
        them and asking for a repaint is enough. Only the stylesheet has to be
        handed over again - Qt copied the old values into it when it parsed it.
        """
        theme.apply(self.backend.config)
        self.setStyleSheet(style())
        # The live image keeps the backing colour it was built with, so it has
        # to be told as well - otherwise a strip of the old background stays
        # along its edge.
        from .preview import set_preview_background  # noqa: PLC0415

        fenster = self.window()
        gaeste = getattr(fenster, "guest", None)
        if gaeste is not None:
            set_preview_background(gaeste.preview, theme.INK)
        self._show_colours()
        oben = self.window()
        if oben is not None:
            oben.update()
        for kind in self.findChildren(QWidget):
            kind.update()

    # -- WLAN --------------------------------------------------------------------
    def _wlan_card(self) -> Card:
        """Scan for networks and join one, right on the screen.

        The booth may do this without any extra privilege: it runs in a real
        local login session, and polkit grants such a session the network
        rights by itself. The same command over SSH would be refused.
        """
        card = Card()
        self.wlan_status = label("", "sub", wrap=True)
        card.box.addWidget(self.wlan_status)
        card.box.addSpacing(14)

        reihe = QHBoxLayout()
        reihe.setSpacing(12)
        self.wlan_scan_btn = button("Netze suchen", "action", self._wlan_scan)
        reihe.addWidget(self.wlan_scan_btn)
        self.wlan_trennen_btn = button("Trennen", "quiet", self._wlan_trennen)
        reihe.addWidget(self.wlan_trennen_btn)
        reihe.addStretch(1)
        card.box.addLayout(reihe)
        card.box.addSpacing(18)

        self.wlan_liste = QVBoxLayout()
        self.wlan_liste.setContentsMargins(0, 0, 0, 0)
        self.wlan_liste.setSpacing(0)
        card.box.addLayout(self.wlan_liste)

        self._wlan_zeigen()
        self._wlan_scan()
        return card

    def _wlan_zeigen(self) -> None:
        """Build the status line and the network list from the last scan."""
        daten = getattr(self, "wlan_daten", None) or {}
        zustand = daten.get("status") or {}
        netze = daten.get("networks") or []
        busy = bool(daten.get("busy"))

        if not daten:
            text = "Wird gesucht …"
        elif not zustand.get("available"):
            text = "Diese Box hat kein WLAN-Modul. Sie läuft am Netzwerkkabel."
        elif zustand.get("connected") and zustand.get("ssid"):
            ip = zustand.get("ip")
            text = f"Verbunden mit {zustand['ssid']}" + (f", {ip}" if ip else "")
        elif busy:
            text = daten.get("note") or "Einen Moment …"
        else:
            text = "Nicht verbunden. Am Kabel läuft die Box trotzdem."
        if daten.get("error"):
            text = daten["error"]
        self.wlan_status.setText(text)
        self.wlan_status.setStyleSheet(
            f"color: {theme.ERR_INK.name()};" if daten.get("error") else "")

        self.wlan_scan_btn.setEnabled(not busy and zustand.get("available", True))
        self.wlan_trennen_btn.setVisible(bool(zustand.get("connected")))

        while self.wlan_liste.count():
            item = self.wlan_liste.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, netz in enumerate(netze):
            teile = [f"{netz['signal']} %"]
            teile.append("gesichert" if netz["secure"] else "offen")
            if netz["saved"]:
                teile.append("gespeichert")
            if netz["active"]:
                teile.append("verbunden")
            zeile = MenuRow(netz["ssid"], " · ".join(teile), last=(i == len(netze) - 1))
            zeile.setEnabled(not busy)
            zeile.clicked.connect(lambda _=False, n=netz: self._wlan_gewaehlt(n))
            self.wlan_liste.addWidget(zeile)

    # -- In the background, never on the paint thread ------------------------------
    def _wlan_arbeit(self, auftrag, note: str) -> None:
        """One Wi-Fi job on its own thread, the result delivered by signal.

        A scan takes seconds, connecting takes longer because DHCP has to
        answer as well. On the paint thread the screen would stand still.
        """
        self.wlan_daten = {**(getattr(self, "wlan_daten", None) or {}),
                           "busy": True, "note": note, "error": ""}
        self._wlan_zeigen()
        brücke = self.bridge

        def arbeit() -> None:
            from booth.hardware import wifi  # noqa: PLC0415

            ergebnis: dict[str, Any] = {"busy": False, "error": ""}
            try:
                fehler = auftrag(wifi)
                if fehler:
                    ergebnis["error"] = fehler
                ergebnis["status"] = wifi.status()
                ergebnis["networks"] = wifi.networks(rescan=False)
            except Exception as exc:  # noqa: BLE001 - must not take the screen down
                log.exception("WLAN task failed")
                ergebnis["error"] = str(exc) or exc.__class__.__name__
            brücke.wlan.emit(ergebnis)

        threading.Thread(target=arbeit, name="ui-wlan", daemon=True).start()

    def _wlan_ready(self, ergebnis: dict) -> None:
        self.wlan_daten = ergebnis
        if self.page == "wlan":
            self._wlan_zeigen()

    def _wlan_scan(self) -> None:
        def auftrag(wifi) -> str:
            if not wifi.device():
                return ""
            if not wifi.radio_on():
                wifi.set_radio(True)
            wifi.networks(rescan=True)
            return ""
        self._wlan_arbeit(auftrag, "Wird gesucht …")

    def _wlan_gewaehlt(self, netz: dict) -> None:
        """A network was tapped: join it, and only ask when that is needed."""
        if netz["active"]:
            return
        if not netz["secure"] or netz["saved"]:
            self._wlan_verbinden(netz["ssid"], None)
            return
        self.keyboard.ask_text(f"Passwort für {netz['ssid']}", "",
                               lambda wert, s=netz["ssid"]: self._wlan_verbinden(s, wert),
                               hint="Mindestens 8 Zeichen", secret=True)

    def _wlan_verbinden(self, ssid: str, passwort: str | None) -> None:
        def auftrag(wifi) -> str:
            ergebnis = wifi.connect(ssid, passwort)
            return "" if ergebnis.get("ok") else (ergebnis.get("error") or "Verbinden fehlgeschlagen")
        self._wlan_arbeit(auftrag, f"Verbinde mit {ssid} …")

    def _wlan_trennen(self) -> None:
        def auftrag(wifi) -> str:
            wifi.disconnect()
            return ""
        self._wlan_arbeit(auftrag, "Wird getrennt …")

    def _group_card(self, name: str, fields: list[dict[str, Any]], title: bool = True) -> QWidget:
        card = Card(name if title else "")
        widgets = [self._field(spec) for spec in fields]
        columns = max(1, min(len(widgets), 4))
        card.box.addWidget(grid(widgets, columns))
        return card

    def _fill_light(self) -> None:
        """Refill the light block: after a change of kind it looks different.

        The choice of lamp is always there, even for one with no remote
        control. Otherwise the block would vanish the moment somebody picked
        "no control", and with it the only way back.
        """
        while self.light_body.count():
            item = self.light_body.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        art = [spec for spec in self.light_fields if spec["key"] == "kind"]
        regler = [spec for spec in self.light_fields if spec["key"] != "kind"]
        # A home-built panel on a MOSFET is the white it was bought as. A
        # kelvin field for it would be a setting without an effect.
        if not getattr(self.backend.light, "tunable", False):
            regler = [spec for spec in regler if spec["key"] != "cct"]
        if art:
            self.light_body.addWidget(grid([self._field(art[0])], 1))
        note = (getattr(self.backend.light, "note", "") or "").strip()
        if note:
            hinweis = label(note, "help", wrap=True)
            hinweis.setStyleSheet(f"font-size: 13px; color: {theme.ERR.name()};")
            self.light_body.addWidget(hinweis)
        if getattr(self.backend.light, "dimmable", True):
            self.light_body.addWidget(grid([self._field(spec) for spec in regler], 1))
        else:
            self.light_body.addWidget(label(
                "Diese Leuchte regelt die Box nicht. Sie brennt den ganzen Abend mit der "
                "Helligkeit, die du an ihr eingestellt hast, auch die drei Lichtknöpfe "
                "auf der Gästeseite sind dann weg.", "help", wrap=True))

    def _power_ask(self) -> None:
        """The question before powering off.

        The computer has no power button: after a shutdown the only way back is
        pulling the plug and putting it in again. So it says that here, before
        anyone presses.
        """
        self.confirm.ask(
            "Box ausschalten",
            "Fährt das System sauber herunter. Warte, bis der Bildschirm dunkel ist, dann "
            "kannst du den Strom trennen. Zum Einschalten steckst du die Box einfach wieder "
            "an, einen Einschaltknopf hat sie nicht.",
            "Herunterfahren", self._power_now)

    def _power_now(self) -> None:
        self._power_goodbye()
        try:
            self.backend.shutdown()
        except Exception as fehler:  # noqa: BLE001
            log.exception("Shutdown failed")
            self.header.flash(f"Herunterfahren fehlgeschlagen: {fehler}", bad=True)

    def _power_goodbye(self) -> None:
        """A full-screen farewell, for as long as the screen is still on."""
        schirm = QWidget(self)
        schirm.setGeometry(0, 0, theme.STAGE_W, theme.STAGE_H)
        schirm.setStyleSheet(f"background: {theme.INK.name()};")
        box = QVBoxLayout(schirm)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gross = label("Die Box fährt herunter", "h1")
        gross.setStyleSheet(f"font-size: 64px; font-weight: 700; color: {theme.BONE.name()};")
        gross.setAlignment(Qt.AlignmentFlag.AlignCenter)
        klein = label("Warte, bis der Bildschirm dunkel ist, dann Strom trennen.\n"
                      "Zum Einschalten einfach wieder anstecken.", "sub", wrap=True)
        klein.setStyleSheet(f"font-size: 30px; color: {theme.DIM.name()};")
        klein.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(gross)
        box.addSpacing(24)
        box.addWidget(klein)
        schirm.show()
        schirm.raise_()
        schirm.repaint()

    def _field(self, spec: dict[str, Any]) -> QWidget:
        path = f"{spec['section']}.{spec['key']}"
        value = self.data["values"].get(path)
        # `type` is what the value means, `widget` what it is operated with.
        # A percentage can perfectly well be a slider.
        kind = spec.get("widget") or spec["type"]
        if kind == "bool":
            ctl = Toggle(spec["label"], spec.get("help", ""), bool(value))
            ctl.toggled.connect(lambda on, p=path: self._value_changed(p, on))
            self.controls[path] = ctl
            return ctl
        if kind in ("slider", "distance"):
            ctl = SliderControl(spec, value)
            ctl.changed.connect(lambda v, p=path: self._value_changed(p, v))
        elif kind in ("number", "percent"):
            step = float(spec.get("step", 1))
            ctl = NumberControl(self.keyboard, spec["label"], value, spec.get("min"), spec.get("max"),
                                step=step, unit=str(spec.get("unit", "")),
                                decimals=0 if step >= 1 else 1)
            ctl.changed.connect(lambda v, p=path: self._value_changed(p, v))
        elif kind == "choice":
            ctl = ChoiceControl(self.chooser, spec["label"],
                                [(str(wert), name) for wert, name in spec["options"]],
                                str(value or ""))
            ctl.changed.connect(lambda v, p=path: self._value_changed(p, v))
        elif kind == "secret":
            ctl = TextControl(self.keyboard, spec["label"], value or "", "nicht eingetragen",
                              secret=True, hint=spec.get("help", ""))
            ctl.changed.connect(lambda v, p=path: self._value_changed(p, v))
        else:
            ctl = TextControl(self.keyboard, spec["label"], value or "")
            ctl.changed.connect(lambda v, p=path: self._value_changed(p, v))
        self.controls[path] = ctl
        return field(spec["label"], spec.get("help", ""), ctl)

    # -- saving ----------------------------------------------------------------------
    def _value_changed(self, path: str, value: Any) -> None:
        self._save({"values": {path: value}})
        if path == "eventpics.enabled":
            self._show_eventpics_card()
            if value:
                self._eventpics_task("status")
        if path == "eventpics.api_key":
            self._eventpics_task("status")
        if path in ("gpio.light_idle_duty", "gpio.light_capture_duty"):
            # Camera and light share a page so that the lamp can be judged in
            # the live picture beside the slider. For that it has to follow the
            # slider at once, not on the next shot.
            self.backend.set_light_preset("capture" if self.capture_light else "idle")
        if path == "light.cct":
            # The brightness has not moved, so the lamp's thread would see
            # nothing to do. Push the new colour temperature at it.
            stupsen = getattr(self.backend.light, "nudge", None)
            if stupsen is not None:
                stupsen()
            self.header.flash("Farbtemperatur gesetzt, bitte neu einmessen")
        if path == "light.kind":
            # Without this the change would only take effect on the next start.
            try:
                self.backend.reload_light()
            except Exception as fehler:  # noqa: BLE001
                log.exception("Switching the light failed")
                self.header.flash(f"Leuchte nicht umgestellt: {fehler}", bad=True)
            self._fill_light()

    def _save(self, payload: dict[str, Any], preview: bool = False) -> None:
        try:
            result = apply_settings(self.backend.config, self.backend.camera, payload)
        except Exception as exc:  # noqa: BLE001 - a failure must not take the screen down
            log.exception("Saving settings failed")
            self.header.flash(f"Nicht gespeichert: {exc}", bad=True)
            return
        if result.get("rejected"):
            self.header.flash("Ein Wert war ungültig", bad=True)
        else:
            self.header.flash()
        if preview:
            self._compose_soon()

    # -- preview ---------------------------------------------------------------------
    def _compose_soon(self, delay: int = 300) -> None:
        self.preview_timer.start(delay)

    def _compose_preview(self) -> None:
        if self.preview_busy:
            self.preview_again = True
            return
        self.preview_busy = True
        booth = self.backend.config.section("booth")
        layout_id = (booth.get("enabled_layouts") or ["grid4"])[0]
        args = (layout_id, str(booth.get("background_style", "creme")),
                str(booth.get("event_title", "")), str(booth.get("event_subtitle", "")),
                str(booth.get("caption_font", "serif")), str(booth.get("caption_colour", "")),
                float(booth.get("caption_size_mm", 4.5)))

        def work() -> None:
            started = time.monotonic()
            try:
                path = self.backend.compose_preview(*args)
            except Exception:  # noqa: BLE001
                log.exception("Preview failed")
                path = None
            log.debug("Preview in %.0f ms", (time.monotonic() - started) * 1000)
            self.bridge.preview.emit(path)

        threading.Thread(target=work, name="ui-preview", daemon=True).start()

    def _preview_ready(self, path) -> None:
        self.preview_busy = False
        self.preview_image.set_path(Path(path) if path else None)
        if self.preview_again:
            self.preview_again = False
            self._compose_soon(0)

