"""Colours, fonts and icons of the user interface.

The values started out as the ones from the earlier web interface, so that the
box looked the same after the switch to a native screen. The colours have since
become a setting - see booth/palette.py for the roles and the ready-made
schemes, and apply() below for everything that is computed from them.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtSvg import QSvgRenderer

from booth import palette

#: The interface is built for exactly this surface and scaled as a whole.
#: Nothing inside it takes its size from the actual screen.
#:
#: 16:9, because nearly every HDMI touchscreen sold for the Pi is, including
#: the one fitted here. On a 16:10 panel there are narrow bands top and bottom
#: in the background colour; that is the rarer half of the market.
STAGE_W, STAGE_H = 1920, 1080

#: Safe margin in stage pixels. The stage fills the screen, but nothing you
#: can touch comes closer than this to the edge. Surfaces that are meant to
#: cover the whole screen - the dimmer behind an enlarged picture, say - do
#: not take it.
#:
#: Why a fixed number and not one computed from the physical size: the screen
#: lies. The EDID of the 15.6 inch panel fitted here claims "520x320 mm", and
#: it measures 345 x 194. Deriving millimetres from that would produce
#: nonsense on every other device.
#:
#: 28 pixels are 5 mm on this panel (1920 / 345.4 mm = 5.56 per mm). Anyone
#: fitting a different panel works it out the same way: width in pixels
#: divided by width in millimetres, times the millimetres wanted.
SAFE_MARGIN_PX = 28

# -- Palette -------------------------------------------------------------------------
#
# Eight colours are chosen, everything else is computed from them. That is the
# whole point: a palette with twenty knobs produces an unreadable screen on the
# second knob, because nobody checks contrast by eye. Pick a background and a
# text colour, and the muted greys, the hairlines and the readable variants of
# red, green and amber follow from them - on a light scheme and on a dark one.

# The eight roles, their names and the ready-made schemes live in
# booth/palette.py, which imports no Qt. They are re-exported here so that a
# drawing module only ever needs to look in one place.
ROLES = palette.ROLES
ROLE_NAMES = palette.ROLE_NAMES
SCHEMES = palette.SCHEMES
SCHEME_NAMES = palette.SCHEME_NAMES
DEFAULT_SCHEME = palette.DEFAULT_SCHEME


def mix(a: QColor, b: QColor, amount: float) -> QColor:
    """`amount` of b laid over a, straight linear blend."""
    amount = max(0.0, min(1.0, amount))
    return QColor(round(a.red() + (b.red() - a.red()) * amount),
                  round(a.green() + (b.green() - a.green()) * amount),
                  round(a.blue() + (b.blue() - a.blue()) * amount))


def _channel(value: float) -> float:
    value /= 255.0
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def luminance(colour: QColor) -> float:
    """Relative luminance as WCAG defines it: 0 is black, 1 is white."""
    return (0.2126 * _channel(colour.red())
            + 0.7152 * _channel(colour.green())
            + 0.0722 * _channel(colour.blue()))


def contrast(a: QColor, b: QColor) -> float:
    """WCAG contrast ratio, 1 to 21. Body text wants at least 4.5."""
    la, lb = luminance(a), luminance(b)
    hell, dunkel = max(la, lb), min(la, lb)
    return (hell + 0.05) / (dunkel + 0.05)


#: Button labels are large and bold, and WCAG lets large text stop at 3.0.
#: Below that a pale label on a pale fill starts to disappear at arm's length,
#: which is the distance people actually stand at.
_ON_MIN_CONTRAST = 3.0


def on(colour: QColor) -> QColor:
    """Text to put on top of a filled area of `colour`.

    Not plain white or black: a faint tint of the colour underneath reads as
    belonging to the button rather than stamped onto it.

    The light tint is preferred, because that is what the booth has always
    looked like - white lettering on an amber button. It is only abandoned
    when it stops being readable, which happens as soon as someone picks a
    bright primary: white on #E09A33 comes out at 2.2, and the word START
    turns into a smudge.
    """
    hell = mix(colour, QColor("#FFFFFF"), 0.93)
    if contrast(hell, colour) >= _ON_MIN_CONTRAST:
        return hell
    return mix(colour, QColor("#000000"), 0.82)


def readable(colour: QColor, background: QColor, target: float = 4.5) -> QColor:
    """The same hue, pushed until it is legible as text on `background`.

    A status colour has two jobs. As a dot it only has to be recognisable, and
    the pure colour is best for that. As a word it has to be read, and amber on
    cream fails that badly - which is why there was a hand-picked "AMBER_SOFT"
    next to "AMBER". Hand-picking stops working the moment the background is a
    setting, so the dark (or light) variant is computed instead.
    """
    if contrast(colour, background) >= target:
        return QColor(colour)
    ziel = QColor("#000000") if luminance(background) > 0.5 else QColor("#FFFFFF")
    schritt, ergebnis = 0.0, QColor(colour)
    while schritt <= 1.0:
        ergebnis = mix(colour, ziel, schritt)
        if contrast(ergebnis, background) >= target:
            return ergebnis
        schritt += 0.04
    return ergebnis


# The colours themselves. Every one is a live object: `apply()` rewrites them
# in place, so a module that did `theme.BONE` once keeps the right colour after
# a scheme change without re-importing anything.
INK = QColor("#FAF3E4")        # background: the page
INK_2 = QColor("#FFFCF2")      # surface: cards on it
INK_3 = QColor("#F3E9D5")      # derived: tiles inside cards
LINE = QColor("#E6DAC0")       # derived: hairlines and empty bars
BONE = QColor("#241F18")       # text
DIM = QColor("#6B6255")        # derived: secondary text
FAINT = QColor("#8C8375")      # derived: tertiary text
AMBER = QColor("#C97A16")      # primary: the main button
AMBER_SOFT = QColor("#8A5A10")  # derived: primary as readable text
SAGE = QColor("#4C7A42")       # confirm: the agreeing button
OK = QColor("#5A9B4C")         # good
WARN = QColor("#D9A21B")       # warn
ERR = QColor("#B3382F")        # bad
START_TEXT = QColor("#FFF8EC")  # derived: text on the primary button
SAGE_TEXT = QColor("#F2F8F0")  # derived: text on the confirm button
OK_INK = QColor("#356B2C")     # derived: good as readable text
WARN_INK = QColor("#7A5510")   # derived: warn as readable text
ERR_INK = QColor("#8E2B23")    # derived: bad as readable text
LINE_2 = QColor("#CFD4DB")     # derived: the stronger hairline, around inputs
PRESSED = QColor("#E5E7EB")    # derived: the fill of a button being held


def apply(config=None) -> dict[str, str]:
    """Put a palette into effect. Call before anything is drawn.

    The chosen eight are written straight in, the rest is derived. Returns what
    was chosen, so the caller can show it.
    """
    gewaehlt = palette.chosen(config)
    hintergrund = QColor(gewaehlt["background"])
    schrift = QColor(gewaehlt["text"])

    def setze(ziel: QColor, quelle: QColor) -> None:
        ziel.setRgb(quelle.red(), quelle.green(), quelle.blue(), quelle.alpha())

    setze(INK, hintergrund)
    setze(INK_2, QColor(gewaehlt["surface"]))
    setze(BONE, schrift)
    setze(AMBER, QColor(gewaehlt["primary"]))
    setze(SAGE, QColor(gewaehlt["confirm"]))
    setze(OK, QColor(gewaehlt["good"]))
    setze(WARN, QColor(gewaehlt["warn"]))
    setze(ERR, QColor(gewaehlt["bad"]))

    # Tiles and hairlines are the background nudged towards the text colour.
    # Nudged, not a fixed grey: on a dark scheme they have to go lighter, and
    # the same two numbers do that by themselves.
    setze(INK_3, mix(hintergrund, schrift, 0.07))
    setze(LINE, mix(hintergrund, schrift, 0.16))
    setze(DIM, mix(schrift, hintergrund, 0.32))
    setze(FAINT, mix(schrift, hintergrund, 0.46))

    setze(START_TEXT, on(AMBER))
    setze(SAGE_TEXT, on(SAGE))
    setze(AMBER_SOFT, readable(AMBER, hintergrund))
    setze(LINE_2, mix(hintergrund, schrift, 0.27))
    setze(PRESSED, mix(hintergrund, schrift, 0.10))
    setze(OK_INK, readable(OK, hintergrund))
    setze(WARN_INK, readable(WARN, hintergrund))
    setze(ERR_INK, readable(ERR, hintergrund))
    return gewaehlt

#: On the Pi the browser resolved every font the old web interface asked for
#: to DejaVu Sans anyway. Naming it here keeps the look identical.
_SANS = ["DejaVu Sans", "Verdana", "Helvetica Neue", "Arial"]
_MONO = ["DejaVu Sans Mono", "Menlo", "Courier New"]


def font(px: float, bold: bool = False, mono: bool = False,
         weight: QFont.Weight | None = None, spacing: float = 0.0) -> QFont:
    """A font sized in stage pixels, not in points."""
    f = QFont()
    f.setFamilies(_MONO if mono else _SANS)
    f.setPixelSize(max(1, round(px)))
    if weight is not None:
        f.setWeight(weight)
    elif bold:
        f.setWeight(QFont.Weight.Bold)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def with_alpha(colour: QColor, alpha: float) -> QColor:
    c = QColor(colour)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


# -- Symbole -----------------------------------------------------------------
# The same strokes as on the web interface. "currentColor" is swapped for the
# button's own colour when the icon is painted.
ICON_CHECK = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" '
              'stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 12.5l5 5L19.5 7"/></svg>')
ICON_TRASH = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" '
              'stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9.5 7V4.5h5V7'
              'M6.5 7l1 13h9l1-13M10 11v5.5M14 11v5.5"/></svg>')
ICON_REDO = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" '
             'stroke-linecap="round" stroke-linejoin="round"><path d="M3 4v6h6"/>'
             '<path d="M4.3 15a8.5 8.5 0 1 0 2-8.8L3 10"/></svg>')
ICON_CLOSE = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" '
              'stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>')
ICON_GEAR = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round">'
             '<path d="M12.2 2h-.4a2 2 0 0 0-2 2v.2a2 2 0 0 1-1 1.7l-.4.3a2 2 0 0 1-2 0l-.2-.1'
             'a2 2 0 0 0-2.7.7l-.2.4a2 2 0 0 0 .7 2.7l.2.1a2 2 0 0 1 1 1.7v.5a2 2 0 0 1-1 1.7'
             'l-.2.1a2 2 0 0 0-.7 2.7l.2.4a2 2 0 0 0 2.7.7l.2-.1a2 2 0 0 1 2 0l.4.3a2 2 0 0 1 1'
             ' 1.7v.2a2 2 0 0 0 2 2h.4a2 2 0 0 0 2-2v-.2a2 2 0 0 1 1-1.7l.4-.3a2 2 0 0 1 2 0'
             'l.2.1a2 2 0 0 0 2.7-.7l.2-.4a2 2 0 0 0-.7-2.7l-.2-.1a2 2 0 0 1-1-1.7v-.5a2 2 0 0 1'
             ' 1-1.7l.2-.1a2 2 0 0 0 .7-2.7l-.2-.4a2 2 0 0 0-2.7-.7l-.2.1a2 2 0 0 1-2 0l-.4-.3'
             'a2 2 0 0 1-1-1.7V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>')

_renderers: dict[tuple[str, str], QSvgRenderer] = {}


def draw_svg(painter: QPainter, svg: str, rect: QRectF, colour: QColor) -> None:
    key = (svg, colour.name())
    renderer = _renderers.get(key)
    if renderer is None:
        renderer = QSvgRenderer(QByteArray(svg.replace("currentColor", colour.name()).encode()))
        _renderers[key] = renderer
    renderer.render(painter, rect)
