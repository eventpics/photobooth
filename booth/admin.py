"""Settings behind a PIN.

There is deliberately no master key. The software is downloadable, so a
universal key would sit in the ZIP and open every booth ever built. A forgotten
PIN is reset on the console instead, with set-pin.sh: whoever can open a shell
on the box already has it in hand, and needs no PIN for anything else either.
The setup script asks for the PIN, so no box keeps the default by accident.

The PIN is stored in plain text. For a four digit code the threat is a guest at
a party, not someone holding the config file - and if they hold the config file
they hold the whole box anyway. Being able to read it back is worth more here
than the illusion of protection.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from booth import palette


log = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
LOCKOUT_S = 60


def _num(section, key, label, help_="", **kw):
    return {"section": section, "key": key, "label": label, "help": help_,
            "type": "number", **kw}


def _pct(section, key, label, help_="", **kw):
    """A fraction stored as 0..1 but shown as a percentage - nobody thinks in 0,15.

    `type` says what the value is and how it is stored; `widget` says what the
    finger gets. They are separate because the percentage has to be converted
    back to a fraction on the way into the configuration either way, and
    hanging that conversion on the choice of control would tie the two
    together for no reason.
    """
    return {"section": section, "key": key, "label": label, "help": help_,
            "type": "percent", "min": 0, "max": 100, "step": 5,
            "unit": "%", **kw}


def _slider(section, key, label, help_="", **kw):
    """A value you judge by looking at the picture, not by reading the number."""
    return {"section": section, "key": key, "label": label, "help": help_,
            "type": "slider", **kw}


def _distance(section, key, label, help_="", **kw):
    """Focus, shown in metres. Stored as dioptres, which is 1 divided by metres."""
    return {"section": section, "key": key, "label": label, "help": help_,
            "type": "distance", "min": 0.3, "max": 5.0, "step": 0.1, **kw}


def _choice(section, key, label, options, help_=""):
    """A choice among fixed options.

    Not a text field: anyone typing here will mistype, and the keyboard covers
    exactly the explanation they need while they do it.
    """
    return {"section": section, "key": key, "label": label, "help": help_,
            "type": "choice", "options": list(options)}


def _text(section, key, label, help_=""):
    return {"section": section, "key": key, "label": label, "help": help_, "type": "text"}


def _secret(section, key, label, help_=""):
    """A value that is shown but not given away.

    Only the first few characters go out, the rest as asterisks. If exactly
    that mask comes back, nobody typed anything and the stored value stays.
    """
    return {"section": section, "key": key, "label": label, "help": help_,
            "type": "secret"}


def _bool(section, key, label, help_=""):
    return {"section": section, "key": key, "label": label, "help": help_, "type": "bool"}


#: Only what a host actually decides. Anything that has one sensible answer is
#: no longer a setting: every picture is triggered by the guests, an unanswered
#: picture is kept, and whether a frame is drawn follows from the layout.
SCHEMA: dict[str, list[dict[str, Any]]] = {
    "Kamera": [
        _slider("camera", "exposure_time_us", "Belichtungszeit",
                "Länger heißt heller, aber auch verwackelter", min=1000, max=120000,
                step=500, unit="µs", log=True, nested="controls"),
        _slider("camera", "analogue_gain", "Verstärkung",
                "Höher heißt heller, aber körniger", min=1, max=16, step=0.1,
                nested="controls"),
        _slider("camera", "colour_gain_red", "Farbe Rot", "", min=0.5, max=4,
                step=0.05, nested="controls"),
        _slider("camera", "colour_gain_blue", "Farbe Blau", "", min=0.5, max=4,
                step=0.05, nested="controls"),
        _distance("camera", "lens_position", "Fokus",
                  "Entfernung, in der scharf gestellt wird", nested="controls"),
    ],
    "Ablauf": [
        _num("booth", "countdown_s", "Countdown je Bild", "Sekunden", min=1, max=15),
        _num("booth", "await_s", "Warten auf den Auslöser",
             "Sekunden. Danach wird die Sitzung verworfen.", min=10, max=300),
        _num("booth", "review_s", "Bild zur Prüfung zeigen",
             "Sekunden. Die Gäste können jederzeit selbst weiter.", min=5, max=180),
        _num("booth", "done_s", "Ergebnis zeigen", "Sekunden", min=5, max=180),
    ],
    "Bilder und Druck": [
        _bool("booth", "printing_enabled", "Drucken erlauben",
              "Zeigt auf dem Ergebnisbildschirm einen Druckknopf, sobald ein Drucker da ist"),
        _bool("booth", "gallery_enabled", "Letzte Bilder auf der Startseite",
              "Zeigt sie neben dem Livebild, zum Nachdrucken. Aus gutem Grund aus: "
              "jeder an der Box sieht damit die Bilder aller Vorgänger."),
        # Six at most: seven would be 968 pixels tall and would hit the bar
        # at the top. Six a side is twelve - divisible by three and by four,
        # so every series is shown complete.
        _num("booth", "gallery_count", "Bilder je Seite",
             "Wie viele links und rechts stehen", min=1, max=6),
    ],
    "EventPics-Galerie": [
        _bool("eventpics", "enabled", "Bilder in die Galerie laden",
              "Nach dem Behalten, eines nach dem anderen und in der Reihenfolge der Aufnahme"),
        _secret("eventpics", "api_key", "API-Schlüssel",
                "Aus deinem EventPics-Konto. Sichtbar bleiben nur die ersten vier Zeichen."),
        _bool("eventpics", "upload_shots", "Auch die Einzelaufnahmen laden",
              "Sonst kommt nur das fertige Blatt in die Galerie"),
    ],
    "Licht": [
        _choice("light", "kind", "Art der Leuchte", [
            ("godox", "Godox über Bluetooth"),
            ("dmx", "Scheinwerfer am DMX-Bus"),
            ("pwm", "Selbstgebaute 12-V-Fläche am MOSFET"),
            ("none", "Keine Steuerung, die Leuchte brennt durch"),
        ], "Woran die Box die Helligkeit regelt. Die Einzelheiten zu DMX und "
           "Bluetooth stehen unter Erweitert."),
        # Sliders, not number pads: brightness is judged by looking at the
        # live picture beside it, never by reading a figure. Both sit on the
        # same page as the camera preview for exactly that reason.
        # Step of one, not the five the other percentages use: between 20 and
        # 25 per cent there is a visible difference in the picture, and the
        # live view next to the slider is what the value is judged by.
        _pct("gpio", "light_idle_duty", "Einstelllicht",
             "Brennt dauerhaft. Auch auf der Gästeseite oben rechts verstellbar.",
             widget="slider", step=1),
        _pct("gpio", "light_capture_duty", "Aufnahmelicht",
             "Nur im Moment der Aufnahme", widget="slider", step=1),
        # Buttons and a number pad rather than a slider: here one exact value
        # matters, 4000 and not somewhere between 3900 and 4100, and a finger
        # does not hit that on a slider.
        _num("light", "cct", "Farbtemperatur",
             "Nur bei Leuchten, die sie können. Wärmer passt besser zu einem "
             "Saal am Abend; 5600 K ist Tageslicht und wirkt drinnen kalt. "
             "Nach jeder Änderung neu einmessen, der Weißabgleich steht fest.",
             min=2800, max=6500, step=100, unit="K"),
    ],
}

#: The caption band grows with the type, but only until it takes 45 % of the
#: sheet. Past that the setting would have no visible effect at all.
CAPTION_MM_MIN, CAPTION_MM_MAX = 2.0, 16.0

#: Rarely touched, hidden until someone asks for it.
ADVANCED: dict[str, list[dict[str, Any]]] = {
    "Anschlüsse": [
        _num("gpio", "light_pin", "Licht (PWM)", "GPIO-Nummer, Vorgabe 18", min=0, max=27),
        _num("gpio", "shutter_pin", "Auslöseknopf", "GPIO-Nummer, Vorgabe 17", min=0, max=27),
        _num("gpio", "light_pwm_frequency", "PWM-Frequenz",
             "Hertz. Zu niedrig gibt Streifen im Bild, zu hoch kommt das MOSFET-Modul "
             "nicht mehr mit und das Dimmen wird unbrauchbar. 2000 ist gemessen gut.",
             min=1, max=20000, step=10),
        _num("gpio", "light_ramp_ms", "Vorlaufzeit des Lichts",
             "Millisekunden, die das Aufnahmelicht vor dem Auslösen angeht. Kurz ist "
             "angenehmer für die Gäste und spart Wärme; eine Leuchte, die über Funk "
             "angesprochen wird, braucht mehr Vorlauf als eine am GPIO.",
             min=100, max=2000, step=50),
    ],
    "Licht": [
        _text("light", "dmx_port", "DMX-Anschluss",
              "Nur bei dmx. /dev/ttyUSB0 für einen USB-Adapter, /dev/serial0 für einen "
              "MAX485 am Stiftleistenstecker."),
        _num("light", "dmx_channel", "DMX-Kanal",
             "Nur bei dmx. Der Kanal, auf dem der Dimmer des Scheinwerfers liegt.",
             min=1, max=512),
        _text("light", "address", "Bluetooth-Adresse",
              "Nur bei godox. Steht nach dem Einrichten im Protokoll, Form AA:BB:CC:DD:EE:FF."),
        _text("light", "mesh_state", "Mesh-Schlüsseldatei",
              "Nur bei godox. Leer lassen für godox-mesh-state.json neben der Software."),
    ],
    "USB-Stick": [
        _bool("usb", "require_marker", "Nur den eigenen Stick beschreiben",
              "Verhindert, dass der Stick eines Gastes den ganzen Abend bekommt"),
    ],
}


def all_fields() -> dict[str, dict[str, Any]]:
    out = {}
    for groups in (SCHEMA, ADVANCED):
        for group in groups.values():
            for field in group:
                out[f"{field['section']}.{field['key']}"] = field
    return out


_PIN_RE = re.compile(r"^\d{4}$")


class AdminAuth:
    """PIN check with a lockout. A forgotten PIN is reset with set-pin.sh."""

    def __init__(self, config) -> None:
        self.config = config
        self._failures = 0
        self._locked_until = 0.0

    # -- pin ---------------------------------------------------------------
    @property
    def pin(self) -> str:
        return str(self.config.section("booth").get("pin", "1234"))

    def set_pin(self, new: str) -> dict[str, Any]:
        if not _PIN_RE.match(new or ""):
            return {"ok": False, "error": "Die PIN muss aus genau vier Ziffern bestehen"}
        self.config.section("booth")["pin"] = new
        self.config.save()
        log.info("Admin PIN changed")
        return {"ok": True}

    def locked_for(self) -> float:
        return max(0.0, round(self._locked_until - time.monotonic(), 1))

    def login(self, pin: str) -> dict[str, Any]:
        if self.locked_for() > 0:
            return {"ok": False, "error": f"Gesperrt, noch {self.locked_for():.0f} Sekunden"}
        if pin != self.pin:
            self._failures += 1
            if self._failures >= MAX_ATTEMPTS:
                self._locked_until = time.monotonic() + LOCKOUT_S
                self._failures = 0
                return {"ok": False, "error": f"Zu viele Versuche, {LOCKOUT_S} Sekunden gesperrt"}
            left = MAX_ATTEMPTS - self._failures
            return {"ok": False, "error": f"Falsche PIN, noch {left} Versuche"}
        self._failures = 0
        return {"ok": True}


def _eventpics_info(config) -> dict[str, Any]:
    """What the interface needs to know about the gallery - minus the key."""
    from .eventpics import maskieren  # noqa: PLC0415

    cfg = config.section("eventpics")
    schluessel = str(cfg.get("api_key", "")).strip()
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "configured": bool(schluessel and str(cfg.get("link_id", "")).strip()),
        "api_key_masked": maskieren(schluessel),
        "link_id": str(cfg.get("link_id", "")),
        "album_id": str(cfg.get("album_id", "")),
        "event_title": str(cfg.get("event_title", "")),
    }


def read_settings(config) -> dict[str, Any]:
    """Everything the settings area shows, in display units.

    Per cent instead of 0..1, metres instead of dioptres, the key masked. The
    web page and the native interface read the same thing.
    """
    values: dict[str, Any] = {}
    for path, field in all_fields().items():
        section = config.section(field["section"])
        if field.get("nested"):
            section = section.get(field["nested"], {})
        raw = section.get(field["key"])
        if field["type"] == "percent" and raw is not None:
            raw = round(float(raw) * 100)
        elif field["type"] == "distance" and raw:
            raw = round(1.0 / float(raw), 2)
        elif field["type"] == "secret":
            from .eventpics import maskieren  # noqa: PLC0415
            raw = maskieren(str(raw or ""))
        values[path] = raw
    from .layouts import build_layouts  # noqa: PLC0415
    from .overlays import BACKGROUNDS, FONTS  # noqa: PLC0415
    booth_cfg = config.section("booth")
    return {
        "schema": SCHEMA,
        "advanced": ADVANCED,
        "values": values,
        "event": {"title": booth_cfg.get("event_title", ""),
                  "subtitle": booth_cfg.get("event_subtitle", "")},
        "layouts": [lay.to_dict() for lay in
                    build_layouts(float(booth_cfg.get("caption_size_mm", 4.5))).values()],
        "active_layout": (booth_cfg.get("enabled_layouts") or [None])[0],
        "backgrounds": [{"id": k, "name": v["name"],
                         "base": "#%02X%02X%02X" % v["base"],
                         "art": bool(v.get("art"))}
                        for k, v in BACKGROUNDS.items()],
        "active_background": booth_cfg.get("background_style", "creme"),
        "eventpics": _eventpics_info(config),
        "fonts": [{"id": k, "name": v["name"]} for k, v in FONTS.items()],
        "caption": {"font": booth_cfg.get("caption_font", "serif"),
                    "colour": booth_cfg.get("caption_colour", ""),
                    "size_mm": booth_cfg.get("caption_size_mm", 4.5)},
    }


def apply_settings(config, camera, payload: dict[str, Any]) -> dict[str, Any]:
    """Take over changed settings and save them.

    One unusable value does not take the whole save down: it lands in
    "rejected", everything else is applied.
    """
    known = all_fields()
    changed: list[str] = []
    rejected: list[str] = []
    for path, raw in (payload.get("values") or {}).items():
        field = known.get(path)
        if field is None:
            continue
        # One unusable value must not take the whole save down with it -
        # the host would lose every other change they just made.
        try:
            if field["type"] == "secret":
                from .eventpics import maskieren  # noqa: PLC0415
                text = str(raw or "").strip()
                alt_wert = str(config.section(field["section"]).get(field["key"], ""))
                # The mask handed back means nothing was typed.
                if not text or text == maskieren(alt_wert):
                    continue
                value: Any = text
            elif field["type"] == "bool":
                value = bool(raw)
            elif field["type"] in ("number", "percent", "slider", "distance"):
                if raw is None or raw == "":
                    raise ValueError("leer")
                value = float(raw)
                if field.get("min") is not None:
                    value = max(float(field["min"]), value)
                if field.get("max") is not None:
                    value = min(float(field["max"]), value)
                if value == int(value) and float(field.get("step", 1)) >= 1:
                    value = int(value)
                if field["type"] == "percent":
                    value = round(value / 100.0, 3)
                elif field["type"] == "distance":
                    value = round(1.0 / max(0.05, value), 3)
            elif field["type"] == "choice":
                value = str(raw if raw is not None else "")
                if value not in [wert for wert, _ in field["options"]]:
                    raise ValueError(f"{value!r} steht nicht zur Wahl")
            else:
                value = str(raw if raw is not None else "")
        except (TypeError, ValueError):
            rejected.append(path)
            continue
        section = config.section(field["section"])
        if field.get("nested"):
            section = section.setdefault(field["nested"], {})
        if section.get(field["key"]) != value:
            section[field["key"]] = value
            changed.append(path)
    ep = payload.get("eventpics")
    if isinstance(ep, dict):
        ep_cfg = config.section("eventpics")
        for schluessel in ("link_id", "album_id", "event_title"):
            if schluessel in ep:
                wert = str(ep[schluessel])[:120]
                if ep_cfg.get(schluessel) != wert:
                    ep_cfg[schluessel] = wert
                    changed.append(f"eventpics.{schluessel}")

    farben = payload.get("theme")
    if isinstance(farben, dict):
        theme_cfg = config.section("theme")
        for key, raw in farben.items():
            if key == "scheme":
                wert = str(raw or "")
                if wert not in palette.SCHEMES:
                    rejected.append("theme.scheme")
                    continue
            elif key in palette.ROLES:
                # Empty is valid and means "use the scheme's value again" -
                # that is the way back, without a button of its own.
                wert = str(raw or "").strip()
                if wert and not palette.is_colour(wert):
                    rejected.append(f"theme.{key}")
                    continue
            else:
                continue
            if theme_cfg.get(key) != wert:
                theme_cfg[key] = wert
                changed.append(f"theme.{key}")

    booth_cfg = config.section("booth")

    def put(key: str, value: Any) -> None:
        """Write only what really differs, so the log names actual changes
        and the card is not rewritten for every keystroke."""
        if booth_cfg.get(key) != value:
            booth_cfg[key] = value
            changed.append(f"booth.{key}")

    if "active_layout" in payload:
        put("enabled_layouts", [str(payload["active_layout"])])
    if "active_background" in payload:
        put("background_style", str(payload["active_background"]))
    for key, target in (("event_title", "title"), ("event_subtitle", "subtitle")):
        if target in (payload.get("event") or {}):
            put(key, str(payload["event"][target]))
    for key, target, cast in (("caption_font", "font", str),
                              ("caption_colour", "colour", str),
                              ("caption_size_mm", "size_mm", float)):
        if target in (payload.get("caption") or {}):
            value = cast(payload["caption"][target])
            if key == "caption_size_mm":
                # Above 16 mm the band hits its ceiling and nothing more
                # happens - a setting that does nothing must not be storable.
                value = round(max(CAPTION_MM_MIN, min(CAPTION_MM_MAX, value)), 1)
            put(key, value)
    if changed:
        config.save()
    # Camera values only take effect once they are pushed to the sensor.
    if any(p.startswith("camera.") for p in changed):
        camera.apply_controls(config.section("camera").get("controls", {}))
    log.info("Settings changed: %s", ", ".join(changed) or "nothing")
    if rejected:
        log.warning("Settings rejected: %s", ", ".join(rejected))
    return {"ok": True, "changed": changed, "rejected": rejected}
