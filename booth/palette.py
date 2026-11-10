"""The colour roles of the user interface, and the ready-made schemes.

Deliberately free of Qt. The settings logic has to validate what arrives from
the screen, and it must not pull a widget toolkit in to do that - the same
module is imported when the box runs its self test with no display attached.

Everything that gets drawn lives in booth/ui/theme.py, which takes the eight
values from here and computes the rest.
"""

from __future__ import annotations

import re

#: What the settings screen offers. The order is the order shown there.
ROLES = ("background", "surface", "text", "primary", "confirm", "good", "warn", "bad")

#: Names for those roles on screen. English keys, German labels - the same
#: split as everywhere else in this project.
ROLE_NAMES = {
    "background": "Hintergrund",
    "surface": "Karten",
    "text": "Schrift",
    "primary": "Hauptknopf",
    "confirm": "Bestätigen",
    "good": "Gut",
    "warn": "Achtung",
    "bad": "Störung",
}

SCHEMES: dict[str, dict[str, str]] = {
    "warm": {
        "background": "#FAF3E4", "surface": "#FFFCF2", "text": "#241F18",
        "primary": "#C97A16", "confirm": "#4C7A42",
        "good": "#72C05C", "warn": "#D9A21B", "bad": "#B3382F",
    },
    "paper": {
        "background": "#F5F3EE", "surface": "#FFFFFF", "text": "#241F18",
        "primary": "#C97A16", "confirm": "#4C7A42",
        "good": "#72C05C", "warn": "#D9A21B", "bad": "#B3382F",
    },
    "night": {
        "background": "#17161C", "surface": "#232128", "text": "#F2EEE6",
        "primary": "#E09A33", "confirm": "#5FA552",
        "good": "#86D471", "warn": "#E8B63B", "bad": "#E0584C",
    },
    "ocean": {
        "background": "#EEF2F6", "surface": "#FFFFFF", "text": "#16202B",
        "primary": "#2B6CB0", "confirm": "#2F855A",
        "good": "#4FC38A", "warn": "#C98A14", "bad": "#C0392B",
    },
    # "warm" with more yellow in the ground, for rooms lit by tungsten.
    "warmer": {
        "background": "#FBEFD4", "surface": "#FFFAEA", "text": "#241B10",
        "primary": "#C96A10", "confirm": "#4C7A42",
        "good": "#72C05C", "warn": "#D9A21B", "bad": "#B3382F",
    },
    # The next two take their main colour from the EventPics star vote at
    # event.pics/en/brand/star-color-vote.html - candidates 4 and 10. The star
    # is a gradient there; a button is one colour, so each takes the first stop.
    "star4": {
        "background": "#FDF6EC", "surface": "#FFFFFF", "text": "#1C1710",
        "primary": "#FF6A2B", "confirm": "#3E8A55",
        "good": "#55B374", "warn": "#FFC93C", "bad": "#D93025",
    },
    "star10": {
        "background": "#FFF6F3", "surface": "#FFFFFF", "text": "#1E1218",
        "primary": "#FF3D8B", "confirm": "#2F8F6B",
        "good": "#45B892", "warn": "#FF7A2F", "bad": "#D81B4A",
    },
    # The logo's own colours. Nothing competes with the photographs, and the
    # one amber thing on screen - START - becomes black instead.
    "mono": {
        "background": "#F6F5F3", "surface": "#FFFFFF", "text": "#000000",
        "primary": "#111111", "confirm": "#3C3C3C",
        "good": "#4E9C5B", "warn": "#9A6B00", "bad": "#B3261E",
    },
}

SCHEME_NAMES = {"warm": "Warm", "warmer": "Warm kräftig", "paper": "Papier",
                "night": "Nacht", "ocean": "Kühl", "star4": "Stern 4",
                "star10": "Stern 10", "mono": "Schwarzweiß"}

DEFAULT_SCHEME = "warm"

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def is_colour(value: str) -> bool:
    """True for #abc and #aabbcc, nothing else.

    Qt would also take "cornflowerblue" and a dozen other spellings. Keeping
    one shape means the stored file always reads the same, and a typo cannot
    turn into some faint named colour nobody chose.
    """
    return bool(_HEX.match(str(value or "").strip()))


def chosen(config=None) -> dict[str, str]:
    """The eight colours in force: the scheme, with single overrides on top."""
    if config is None:
        return dict(SCHEMES[DEFAULT_SCHEME])
    cfg = config.section("theme") if hasattr(config, "section") else dict(config or {})
    werte = dict(SCHEMES.get(str(cfg.get("scheme") or DEFAULT_SCHEME),
                             SCHEMES[DEFAULT_SCHEME]))
    for role in ROLES:
        wert = str(cfg.get(role) or "").strip()
        if is_colour(wert):
            werte[role] = wert
    return werte
