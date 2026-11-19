"""Everything behind the booth's interface, minus the interface itself.

Camera, GPIO, LED strip, the sequence of a shot, the queue, the USB stick and
EventPics are wired together here. The interface only displays things and
calls what is in this module - it knows nothing of GPIO pins or queues.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from booth.hardware import printer as printer_mod
from booth.hardware.camera import create_camera
from booth.hardware.config import Config
from booth.hardware.gpio import create_gpio
from booth.hardware.leds import create_leds
from booth.hardware.light import connection as light_connection
from booth.hardware.light import create_light
from booth.hardware.system import network_status, touch_status
from booth.hardware.platform_probe import resolve_mock
from booth.hardware.system import SystemMonitor
from booth.layouts import build_layouts
from booth.admin import AdminAuth
from booth.session import BoothSession
from booth.journal import Journal
from booth.usb import UsbTarget
from booth.eventpics import EventPicsTarget
from booth.eventlog import EventLog
from booth.workers import SinkWorker

log = logging.getLogger(__name__)


@dataclass
class Backend:
    config: Any
    camera: Any
    gpio: Any
    leds: Any
    light: Any
    sysmon: Any
    events: Any
    journal: Any
    usb: Any
    eventpics: Any
    session: Any
    auth: Any
    capture_dir: Path
    base_dir: Path
    mock: bool
    printer_ok: Callable[[], bool]
    printer_state: Callable[[], dict[str, Any]]
    workers: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    #: Set while guests may operate the box - not while the settings are open.
    guests_allowed: threading.Event = field(default_factory=threading.Event)

    # -- The actions every front end needs -------------------------------------
    def set_idle_light(self, value: float) -> float:
        """The modelling light, which anyone at the box may change.

        Deliberately not the capture light: that is tied to the calibrated
        exposure, and a guest who changes it ruins every picture afterwards.
        """
        value = round(max(0.0, min(1.0, float(value))), 2)
        self.config.section("gpio")["light_idle_duty"] = value
        self.config.save()
        if self.session.state in ("idle", "await", "choose"):
            self.session._set_light(value)
        self.events.add(f"Einstelllicht auf {round(value * 100)} % gestellt")
        return value

    def idle_light(self) -> float:
        return float(self.config.section("gpio").get("light_idle_duty", 0.2))

    def picture(self, name: str) -> Path | None:
        """A picture of this box's, from the two folders it writes to itself."""
        name = Path(str(name or "")).name
        if not name.lower().endswith(".jpg"):
            return None
        for folder in (self.session.result_dir, self.session.capture_dir):
            candidate = folder / name
            if candidate.exists() and candidate.parent == folder:
                return candidate
        return None

    def print_picture(self, name: str) -> dict[str, Any]:
        path = self.picture(name)
        if path is None:
            return {"ok": False, "error": "Bild nicht gefunden"}
        if not self.printer_ok():
            return {"ok": False, "error": "Kein Drucker eingerichtet"}
        cfg = self.config.section("printer")
        try:
            result = printer_mod.print_file(
                path, printer=str(cfg.get("name", "")), media=str(cfg.get("media", "")),
                extra=list(cfg.get("extra_options", [])))
        except Exception as exc:  # noqa: BLE001 - a printer problem must not stop the box
            log.exception("Printing %s failed", path.name)
            self.events.add(f"Druck fehlgeschlagen: {path.name}: {exc}", "error")
            return {"ok": False, "error": str(exc) or "Druck fehlgeschlagen"}
        self.events.add(f"Gedruckt: {path.name}", "good")
        return {"ok": True, **(result or {})}

    def link_for(self, name: str) -> str | None:
        """The direct link to an uploaded picture, and nothing else."""
        try:
            return self.eventpics.link_fuer(Path(name).name) or None
        except Exception:  # noqa: BLE001 - no link is a perfectly normal state
            return None

    # -- settings area --------------------------------------------------------------
    # Everything here can take seconds and waits on camera frames. The native
    # interface therefore never calls it from its own thread: the camera
    # events run there too, and the call would be waiting on itself.

    def set_light_preset(self, preset: str) -> None:
        """Modelling or capture light for aiming, without storing anything."""
        key = "light_capture_duty" if preset == "capture" else "light_idle_duty"
        duty = float(self.config.section("gpio").get(key, 0.2))
        self.session._set_light(max(0.0, min(1.0, duty)))

    #: What the light search aims for. 8 ms is 1/125 s, which freezes an arm
    #: being thrown around, and it sits well under the 12 ms at which the
    #: screen starts calling the light tight.
    LIGHT_TARGET_US = 8000.0
    #: Close enough to stop searching. Chasing the last few per cent would
    #: cost another measurement for a difference nobody sees.
    LIGHT_TOLERANCE = 0.25
    #: Below this the lamp is off in all but name.
    LIGHT_MIN_DUTY = 0.05
    #: Measurements the search may spend. Each one costs a few seconds.
    LIGHT_TRIES = 3

    def _tune_capture_light(self, start: float, ramp_s: float) -> dict[str, Any]:
        """Find the dimmest capture light that still freezes movement.

        Two things pull against each other. Too little light and the exposure
        grows until everyone who moves is a smear. Too much and the guests are
        dazzled - the complaint that started all of this. The best setting is
        the *lowest* one that still hits the target, not the brightest the
        lamp can manage.

        The camera reports what it needed: exposure time multiplied by gain is
        how short of light it was. That scales with the lamp, so one
        measurement predicts the next setting.

        Two rules keep this honest. Every value it can return has been
        measured - an earlier version handed back the last extrapolation and
        proposed 100 % off the back of a reading taken at 56 %. And if more
        lamp does not mean less demand, something else is lighting the scene -
        daylight through a window - and the search gives up instead of
        chasing a number it cannot influence.
        """
        messungen: list[dict[str, Any]] = []

        def miss(wert: float) -> float | None:
            self.session._set_light(wert)
            time.sleep(max(ramp_s, 0.4))
            try:
                m = self.camera.measure_exposure()
            except Exception:  # noqa: BLE001 - the search is a bonus, not the job
                log.exception("Light search: measuring failed")
                return None
            us = m.get("exposure_time_us")
            if not us:
                return None
            gain = float(m.get("analogue_gain") or 1.0)
            bedarf = float(us) * gain
            messungen.append({"duty": round(wert, 2), "exposure_time_us": us,
                              "analogue_gain": round(gain, 2), "demand": round(bedarf)})
            return bedarf

        duty = max(self.LIGHT_MIN_DUTY, min(1.0, float(start)))
        bedarf = miss(duty)
        if bedarf is None:
            return {"duty": round(duty, 2), "steps": messungen, "note": "keine Messung"}

        hinweis = ""
        for _ in range(self.LIGHT_TRIES - 1):
            neu = duty * bedarf / self.LIGHT_TARGET_US
            neu = max(self.LIGHT_MIN_DUTY, min(1.0, neu))
            if abs(neu - duty) < 0.03:
                break
            neu_bedarf = miss(neu)
            if neu_bedarf is None:
                break
            if neu > duty and neu_bedarf > bedarf * 0.92:
                # More lamp, no less demand: this scene is lit by something
                # the box does not control. Keep what the host had.
                hinweis = "umgebungslicht"
                break
            duty, bedarf = neu, neu_bedarf

        if hinweis:
            return {"duty": round(float(start), 2), "steps": messungen, "note": hinweis}
        grenze = self.LIGHT_TARGET_US * (1 + self.LIGHT_TOLERANCE)
        taugt = [m["duty"] for m in messungen if m["demand"] <= grenze]
        gewaehlt = min(taugt) if taugt else max(m["duty"] for m in messungen)
        return {"duty": gewaehlt, "steps": messungen,
                "note": "" if taugt else "reicht nicht"}

    def calibrate(self, tune_light: bool = True) -> dict[str, Any]:
        """Measure exposure, white balance and focus, and pin them down.

        Under the capture light, not the modelling light: measured under the
        weaker one, every real picture would be overexposed.

        With `tune_light`, the capture light is searched for first and the
        measurement then happens under what was found. The two belong
        together: an exposure measured under one brightness is wrong under
        another, so either both are kept or neither is.
        """
        gpio_cfg = self.config.section("gpio")
        capture_duty = float(gpio_cfg.get("light_capture_duty", 1.0))
        ramp_s = float(gpio_cfg.get("light_ramp_ms", 200)) / 1000.0
        result: dict[str, Any] = {}
        if tune_light:
            gefunden = self._tune_capture_light(capture_duty, ramp_s)
            result["light"] = {"before": round(capture_duty, 2),
                               "after": gefunden["duty"], "steps": gefunden["steps"]}
            capture_duty = gefunden["duty"]
        result["measured_at_duty"] = capture_duty
        self.session._set_light(capture_duty)
        time.sleep(max(ramp_s, 0.3))
        camera = self.camera
        try:
            for name, func in (("exposure", camera.measure_exposure),
                               ("white_balance", camera.measure_white_balance),
                               ("focus", camera.autofocus)):
                try:
                    result[name] = func()
                except Exception as exc:  # noqa: BLE001 - report per step
                    log.exception("Calibration step %s failed", name)
                    result[name] = {"error": str(exc) or exc.__class__.__name__}
        finally:
            self.session._set_light(self.idle_light())
        for name, label in (("exposure", "Belichtung"), ("white_balance", "Weißabgleich"),
                            ("focus", "Fokus")):
            step = result.get(name) or {}
            if step.get("error"):
                self.events.add(f"Einmessen: {label} fehlgeschlagen: {step['error']}", "error")
            elif step.get("settled") is False:
                self.events.add(f"Einmessen: {label} kam nicht zur Ruhe, alter Wert bleibt",
                                "warn")
        exposure = result.get("exposure") or {}
        if exposure.get("settled"):
            self.events.add("Eingemessen: {} µs, Verstärkung {}, {} lx".format(
                exposure.get("exposure_time_us"), exposure.get("analogue_gain"),
                exposure.get("lux")), "good")
        licht = result.get("light")
        if licht and abs(licht["after"] - licht["before"]) > 0.005:
            gpio_cfg["light_capture_duty"] = licht["after"]
            self.events.add("Aufnahmelicht eingestellt: {} % statt {} %".format(
                round(licht["after"] * 100), round(licht["before"] * 100)), "good")
        # The measured values are in the configuration now.
        self.config.save()
        return {"ok": True, **result}

    def test_shot(self, countdown_s: float = 3.0) -> dict[str, Any]:
        result = self.session.test_shot(countdown_s)
        if result.get("ok"):
            result["path"] = self.capture_dir / "test" / result["file"]
        return result

    def _verbindungen_merken(self, data: dict[str, Any]) -> None:
        """Write every change into the log.

        If the radio link to the lamp drops halfway through the evening,
        nobody sees it - the pictures merely lack the capture light, and the
        next day no one knows when it started. So every change is listed
        under "Meldungen", with a time.
        """
        vorher = getattr(self, "_conn_seen", None)
        lampe = data["lamp"]
        drucker = data["printer"]
        tasten = data["touch"]
        jetzt = {"lamp": bool(lampe["connected"]) if lampe["monitored"] else None,
                 "printer": drucker["attached"],
                 "touch": tasten["present"]}
        if vorher is None:
            self._conn_seen = jetzt
            return
        if jetzt["lamp"] is not None and jetzt["lamp"] != vorher.get("lamp"):
            if jetzt["lamp"]:
                self.events.add("Leuchte wieder verbunden", "good")
            else:
                self.events.add("Verbindung zur Leuchte verloren", "error")
        if jetzt["touch"] is not None and jetzt["touch"] != vorher.get("touch"):
            if jetzt["touch"]:
                self.events.add("Touchscreen wieder da", "good")
            else:
                self.events.add("Touchscreen verloren", "error")
        if jetzt["printer"] != vorher.get("printer"):
            if jetzt["printer"]:
                self.events.add("Drucker angesteckt", "good")
            elif jetzt["printer"] is False:
                self.events.add("Drucker abgesteckt", "warn")
        self._conn_seen = jetzt

    def reload_light(self) -> dict[str, Any]:
        """Rebuild the lamp after the settings switched to a different kind.

        Without this the change would only take effect on the next start - and
        whoever just connected a lamp wants to try it now.
        """
        from booth.hardware.light import describe  # noqa: PLC0415

        try:
            self.light.stop()
        except Exception:  # noqa: BLE001 - the old lamp must not hold up the new one
            log.debug("Could not stop the old light", exc_info=True)
        neu = create_light(self.config, self.gpio)
        self.light = neu
        if self.session is not None:
            self.session.light = neu
        try:
            neu.set(self.idle_light())
        except Exception:  # noqa: BLE001
            log.debug("Could not set the modelling light after switching", exc_info=True)
        self.events.add(f"Leuchte umgestellt auf {neu.kind}")
        return describe(neu)

    def shutdown(self) -> dict[str, Any]:
        """Shut the system down cleanly.

        Via sudo with one narrowly scoped permission that setup.sh installs:
        the box does not run as root, and logind otherwise asks a confirmation
        for powering off that nobody can answer on a touchscreen. The light
        goes out first - otherwise a radio lamp keeps burning with nothing
        left to hear from the box.
        """
        import subprocess  # noqa: PLC0415
        import threading as _threading  # noqa: PLC0415

        self.events.add("Box wird heruntergefahren")
        try:
            self.light.stop()
        except Exception:  # noqa: BLE001 - das Herunterfahren hat Vorrang
            log.debug("Could not switch the light off before shutdown", exc_info=True)

        def spaeter() -> None:
            # A short wait, so the farewell notice still gets painted.
            time.sleep(0.8)
            for befehl in (["sudo", "-n", "/usr/sbin/shutdown", "-h", "now"],
                           ["systemctl", "poweroff"]):
                try:
                    subprocess.run(befehl, timeout=10, capture_output=True, check=True)
                    return
                except Exception:  # noqa: BLE001 - then try the next route
                    log.warning("Shutdown via %s failed", befehl[0], exc_info=True)

        _threading.Thread(target=spaeter, name="shutdown", daemon=True).start()
        return {"ok": True}

    def eventpics_events(self) -> dict[str, Any]:
        """The account's events and albums, to pick from instead of typing out."""
        from booth.eventpics import EventPicsError  # noqa: PLC0415

        try:
            data = self.eventpics.events_and_albums()
        except EventPicsError as exc:
            return {"ok": False, "error": str(exc)}
        events = []
        for ev in ((data.get("events") if isinstance(data, dict) else None) or []):
            events.append({
                "linkId": ev.get("linkId") or ev.get("id"),
                "title": ev.get("title") or ev.get("name") or "",
                "albums": [{"id": a.get("id") or a.get("albumId"),
                            "title": a.get("title") or a.get("name") or ""}
                           for a in (ev.get("albums") or [])],
            })
        return {"ok": True, "events": events}

    def eventpics_setup(self, source: str) -> dict[str, Any]:
        """Take the key from a QR code at the camera, or from the USB stick."""
        if source == "qr":
            return self.eventpics.vom_qr(self.camera)
        return self.eventpics.vom_stick(self.usb)

    def eventpics_status(self) -> dict[str, Any]:
        data = self.eventpics.status()
        data["queue"] = self.journal.stats("eventpics")
        data["qr_possible"] = self.eventpics.qr_moeglich()
        data["usb_present"] = bool(self.usb.status()["present"]) if self.usb else False
        return data

    def compose_preview(self, layout_id: str, background: str, title: str, subtitle: str,
                        font: str, colour: str, size_mm: float) -> Path | None:
        """One sheet with the built-in sample pictures, exactly as it would print."""
        from booth.layouts import build_layouts, compose  # noqa: PLC0415
        from booth.overlays import build_background  # noqa: PLC0415
        from booth.samples import sample_paths  # noqa: PLC0415

        layout = build_layouts(float(size_mm)).get(layout_id)
        shots = sample_paths(self.capture_dir / "beispiele")
        if layout is None or len(shots) < layout.shots:
            return None
        out_dir = self.capture_dir / "layouts"
        bg = None
        if not layout.full_bleed:
            bg = build_background(layout.canvas, background, out_dir / f"bg-{background}.png")
        return compose(layout, shots[:layout.shots], background_path=bg, title=title,
                       subtitle=subtitle, caption_font=font, caption_colour=colour,
                       caption_size_mm=float(size_mm), output_path=out_dir / f"{layout.id}.jpg")

    def background_swatch(self, style: str) -> Path:
        from booth.overlays import build_background  # noqa: PLC0415

        target = self.capture_dir / "layouts" / f"swatch-{style}.png"
        build_background((360, 240), style, target)
        return target

    def _netz_host(self) -> str:
        """Which host the network check tests against.

        Not some well-known server: all that counts is whether the box can
        reach the one it actually talks to. A guest network that lets Google
        through and nothing else would otherwise report "online".
        """
        from urllib.parse import urlparse  # noqa: PLC0415

        return urlparse(self.eventpics.basis).hostname or "api.event.pics"

    def status(self) -> dict[str, Any]:
        """Everything the status panel shows.

        Some values cost a process (printer, USB stick). The interface
        therefore does not fetch this on the paint tick but on a thread of its
        own.
        """
        drucker = self.printer_state()
        data: dict[str, Any] = {
            "camera_ok": getattr(self.camera, "backend", "") != "mock",
            "printer_ok": bool(drucker["ready"]),
            "printer": drucker,
            "lamp": light_connection(self.light),
            "touch": touch_status(),
            "network": network_status(self._netz_host()),
            "eventpics": self.eventpics.status(),
        }
        if self.journal is not None:
            data["eventpics"]["queue"] = self.journal.stats("eventpics")
        self._verbindungen_merken(data)
        # Calibrated once means: correct only as long as the light stays.
        # If it gets markedly brighter - daylight instead of evening light,
        # the ceiling light switched on - every picture is overexposed, and on
        # screen that only shows once the guests have already been
        # photographed. Only "brighter" can be said with confidence: the
        # measurement was taken under the capture light, and usually only the
        # weaker modelling light is burning now.
        # Not during a shot: the camera is switching modes then.
        lux_now = None
        if self.session.state in ("idle", "await", "review", "done"):
            lux_now = getattr(self.camera, "current_lux", lambda: None)()
        controls = self.config.section("camera").get("controls", {})
        data["light"] = {"lux": lux_now, "calibrated_lux": controls.get("calibrated_lux"),
                         "auto": bool(controls.get("ae_enable"))}
        if self.usb is not None:
            self.usb.poll_presence()
            usb_status = self.usb.status()
            stats = self.journal.stats("usb") if self.journal else {}
            data["usb"] = {"present": usb_status["present"],
                           "free_gb": usb_status.get("free_gb"),
                           "total_gb": usb_status.get("total_gb"),
                           "pending": stats.get("pending", 0) + stats.get("failed", 0)}
        sysmon = self.sysmon
        memory = sysmon.memory()
        disk = sysmon.disk()
        data["system"] = {
            "temperature_c": sysmon.temperature(),
            "cpu_percent": sysmon.cpu_percent(),
            "cpu_mhz": sysmon.cpu_mhz(),
            "cpu_mhz_max": sysmon.cpu_mhz_max(),
            "memory_used_percent": memory.get("used_percent"),
            "memory_used_mb": memory.get("used_mb"),
            "memory_total_mb": memory.get("total_mb"),
            "swap_used_mb": memory.get("swap_used_mb"),
            "disk_free_gb": disk.get("free_gb"),
            "disk_total_gb": disk.get("total_gb"),
            "uptime_s": sysmon.uptime_s(),
        }
        return data


def build_backend(config_path: Path | None = None) -> Backend:
    """Builds everything and starts the background workers.

    The real camera is only prepared, not started: the interface first
    attaches its preview widget to the camera and starts it itself. The other
    way round, picamera2 created an invisible preview of its own.
    """
    config = Config(config_path)
    use_mock = resolve_mock(config.get("app", "mock", "auto"))

    base_dir = Path(__file__).resolve().parent.parent
    capture_dir = base_dir / config.get("app", "capture_dir", "captures")

    camera, camera_note = _start_camera(config, capture_dir, use_mock)
    gpio, gpio_note = _start_gpio(config, use_mock)
    leds, leds_note = _start_leds(config, use_mock)
    # What the lamp hangs off is in the configuration: a home-made 12 V panel
    # on a MOSFET, a Godox over Bluetooth, or a bought one with no remote.
    _light_cfg = config.section("light")
    # "cct" has to be written out, not left to a default inside the lamp: the
    # slider in the settings clamps a missing value to its minimum, and the
    # screen would then claim 2800 K while the lamp burns at 5600.
    _ergaenzt = False
    for _schluessel, _vorgabe in (("kind", "pwm"), ("address", ""), ("mesh_state", ""),
                                  ("dmx_port", "/dev/ttyUSB0"), ("dmx_channel", 1),
                                  ("cct", 5600)):
        if _schluessel not in _light_cfg:
            _light_cfg[_schluessel] = _vorgabe
            _ergaenzt = True
    if _ergaenzt:
        # Written to the file, not just held in memory. Otherwise the file and
        # the screen disagree, and the next person to read the file by hand
        # draws the wrong conclusion.
        config.save()
    light = create_light(config, gpio)
    printer_state = _printer_probe(printer_mod)
    sysmon = SystemMonitor(capture_dir)
    sysmon.start()
    notes = [note for note in (camera_note, gpio_note, leds_note, light.note) if note]

    # One journal, several destinations. USB is the first; the gallery upload
    # plugs into exactly the same machinery.
    events = EventLog(base_dir / "events.log")
    events.add("Fotobox gestartet")

    # The caption size used to be a percentage of a size derived from the text
    # area, which meant the same number gave a different size on every layout.
    # It is millimetres on the print now; convert once so an existing box keeps
    # the look it had instead of silently changing.
    _booth_cfg = config.section("booth")
    if "caption_size_mm" not in _booth_cfg and "caption_scale" in _booth_cfg:
        try:
            # Only PAPER_MM is fetched locally. Importing build_layouts here
            # would make it a local of build_backend - and every nested
            # function would see it as conditionally assigned.
            from booth.layouts import PAPER_MM  # noqa: PLC0415

            active = (_booth_cfg.get("enabled_layouts") or ["grid4"])[0]
            layout = build_layouts().get(active)
            area = layout.text_area if layout else None
            if area is not None:
                _, _, area_w, area_h = area.px(layout.canvas)
                factor = 0.30 if area_w / max(area_h, 1) > 2.2 else 0.17
                px = area_h * factor * float(_booth_cfg["caption_scale"]) / 100.0
                dpi = layout.canvas[0] / (PAPER_MM[0] / 25.4)
                _booth_cfg["caption_size_mm"] = round(px / dpi * 25.4, 1)
            else:
                _booth_cfg["caption_size_mm"] = 4.5
        except Exception:  # noqa: BLE001 - a default is better than no start
            log.exception("Could not convert caption_scale, using the default")
            _booth_cfg["caption_size_mm"] = 4.5
        _booth_cfg.pop("caption_scale", None)
        config.save()
        log.info("caption_scale converted to %.1f mm", _booth_cfg["caption_size_mm"])

    # The modelling light belongs on from the moment the box is switched on -
    # it is what guests see when they walk up, and it was staying dark until
    # something else happened to set it.
    #
    # Through the light layer, not around it via GPIO: with a bought lamp
    # attached, the home-made panel on the GPIO would otherwise have come on
    # and stayed on all evening. Seen exactly like that on the Pi - both lamps
    # running at once.
    try:
        light.set(float(config.section("gpio").get("light_idle_duty", 0.2)))
    except Exception:  # noqa: BLE001 - no lamp is not a reason to fail the start
        log.debug("Could not set the modelling light at start", exc_info=True)
    journal = Journal(base_dir / "booth.db")
    journal.reset_working()
    usb = UsbTarget(config, events=events)
    eventpics = EventPicsTarget(config, events=events)
    # The link list belongs next to the captures, not in the working directory.
    config.section("eventpics").setdefault(
        "link_store", str(capture_dir / EventPicsTarget.LINK_DATEI))

    workers: list[SinkWorker] = []
    if config.section("usb").get("enabled", True):
        worker = SinkWorker(journal, "usb",
                            lambda path, kind, sess: usb.copy(path, kind, sess),
                            events=events, label="USB-Stick")
        worker.start()
        workers.append(worker)
    if eventpics.enabled():
        # Strictly in order: a gallery shows the pictures as they arrive.
        # After twelve failed attempts a picture is skipped, so one broken
        # file does not hold up the whole evening.
        worker = SinkWorker(journal, "eventpics",
                            lambda path, kind, sess: eventpics.upload(path, kind, sess),
                            events=events, label="EventPics",
                            strict_order=True, give_up_after=12)
        worker.start()
        workers.append(worker)

    def _warm_layout_preview() -> None:
        """Draw one sheet in the background right after the start.

        The first composition pays for everything that is only set up once:
        importing Pillow, finding a font, the rounded corner mask, the decoded
        background. Doing it here costs nobody any waiting - doing it on the
        host's first click costs a second and a half.
        """
        try:
            from booth.layouts import build_layouts, compose  # noqa: PLC0415
            from booth.overlays import build_background  # noqa: PLC0415
            from booth.samples import sample_paths  # noqa: PLC0415

            booth_cfg = config.section("booth")
            style = str(booth_cfg.get("background_style", "creme"))
            active = (booth_cfg.get("enabled_layouts") or ["grid4"])[0]
            caption_mm = float(booth_cfg.get("caption_size_mm", 4.5))
            layout = build_layouts(caption_mm).get(active)
            shots = sample_paths(capture_dir / "beispiele")
            if layout is None or len(shots) < layout.shots:
                return
            out_dir = capture_dir / "layouts"
            background = None
            if not layout.full_bleed:
                background = build_background(layout.canvas, style,
                                              out_dir / f"bg-{style}.png")
            compose(layout, shots[:layout.shots], background_path=background,
                    title=str(booth_cfg.get("event_title", "")),
                    subtitle=str(booth_cfg.get("event_subtitle", "")),
                    caption_font=str(booth_cfg.get("caption_font", "serif")),
                    caption_colour=str(booth_cfg.get("caption_colour", "")),
                    caption_size_mm=float(booth_cfg.get("caption_size_mm", 4.5)),
                    output_path=out_dir / f"{layout.id}.jpg")
            log.info("Layout preview warmed up (%s)", layout.id)
        except Exception:  # noqa: BLE001 - a cold cache must never stop the booth
            log.debug("Preview warm-up failed", exc_info=True)

    threading.Thread(target=_warm_layout_preview, name="preview-warmup",
                     daemon=True).start()

    def _on_keep(result: Path, shots: list[Path], layout_id: str | None = None) -> None:
        """A picture is only queued once the guests decided to keep it.

        The individual shots go first, in the order they were taken, and only
        then the finished sheet. The sheet used to come first - which goes
        unnoticed on a USB stick but not in a gallery, where the result would
        appear before its parts.

        Each destination also decides for itself whether it wants the
        individual shots. That used to hang off one USB setting that applied
        to everybody.
        """
        vorhanden = {w.sink for w in workers}
        if not vorhanden:
            return
        will_shots = {
            "usb": bool(config.section("usb").get("copy_shots", True)),
            "eventpics": bool(config.section("eventpics").get("upload_shots", True)),
        }

        def ziele(kind: str) -> list[str]:
            if kind == "result":
                return sorted(vorhanden)
            return sorted(z for z in vorhanden if will_shots.get(z, True))

        # For a borderless single picture the sheet IS the photograph: no
        # frame, no text, no background. Sending both would mean putting the
        # same picture into the gallery twice and onto the stick twice -
        # which is exactly how it ended up there, once at 3888x2592 and once
        # scaled down.
        from booth.layouts import build_layouts  # noqa: PLC0415

        vorlage = build_layouts().get(layout_id or "")
        nur_blatt = bool(vorlage and vorlage.full_bleed and vorlage.shots == 1
                         and vorlage.text_area is None)

        stamp = result.stem
        for shot in [] if nur_blatt else shots:
            if not shot.exists():
                continue
            z = ziele("shot")
            if z:
                journal.add(shot, "shot", z, session=stamp,
                            taken_at=shot.stat().st_mtime)
        z = ziele("result")
        if z:
            journal.add(result, "result", z, session=stamp,
                        taken_at=result.stat().st_mtime)

    session = BoothSession(config, camera, gpio, capture_dir, on_keep=_on_keep,
                           events=events, light=light, usb=usb)
    guests_allowed = threading.Event()
    guests_allowed.set()

    def _on_button() -> None:
        """One physical button for everything: start, each shot, keep."""
        # While somebody is in the settings the button triggers nothing - and
        # neither does it without a real camera, or test shots would pile up.
        if not guests_allowed.is_set():
            return
        if not use_mock and getattr(camera, "backend", "") == "mock":
            return
        if session.state == "await":
            session.next_shot()
        elif session.state in BoothSession.STARTABLE:
            session.start()

    gpio.on_press(_on_button)

    auth = AdminAuth(config)

    return Backend(config=config, camera=camera, gpio=gpio, leds=leds, light=light,
                   sysmon=sysmon,
                   events=events, journal=journal, usb=usb, eventpics=eventpics,
                   session=session, auth=auth, capture_dir=capture_dir,
                   base_dir=base_dir, mock=use_mock,
                   printer_ok=lambda: bool(printer_state()["ready"]),
                   printer_state=printer_state,
                   workers=workers, notes=notes, guests_allowed=guests_allowed)


def _start_camera(config, capture_dir: Path, use_mock: bool):
    """Start the real camera, fall back to the mock one if it will not come up.

    This is the normal situation while a booth is being built: the Pi is there
    but the camera module has not arrived yet. Everything else must still be
    testable, so a missing camera must never stop the tool from starting.
    """
    if not use_mock:
        camera = create_camera(config, capture_dir, use_mock=False)
        try:
            # Only prepare: it starts once the interface's preview widget is
            # attached to the camera. Right after a restart the previous
            # instance can still hold the camera for a moment ("Device or
            # resource busy") - so give up only after a few attempts.
            for attempt in range(5):
                try:
                    camera.prepare()
                    break
                except Exception as exc:  # noqa: BLE001
                    if attempt == 4:
                        raise
                    log.warning("Camera not ready (%s), retrying", exc)
                    try:
                        camera.stop()
                    except Exception:  # noqa: BLE001
                        pass
                    time.sleep(2)
            return camera, None
        except Exception as exc:  # noqa: BLE001 - degrade instead of dying
            log.warning("Real camera unavailable, falling back to mock: %s", exc)
            note = f"Kamera nicht verfügbar, Mock aktiv: {exc}"
            camera = create_camera(config, capture_dir, use_mock=True)
            camera.start()
            return camera, note

    camera = create_camera(config, capture_dir, use_mock=True)
    camera.start()
    return camera, None


def _printer_probe(printer_mod, ttl_s: float = 10.0):
    """What the printer is doing, asked at most every `ttl_s` seconds.

    presence() runs lpstat as a separate process. With no printer configured
    CUPS takes about a second over it, and the guest screen asks four times a
    second - this one call used to hold up every status update and make the
    countdown jump. A printer does not come and go between two pictures, so a
    remembered answer is not only faster but also closer to the truth.
    """
    import time as _time  # noqa: PLC0415

    leer = {"ready": False, "queue": None, "attached": None, "reason": "noch nicht gefragt"}
    state: dict[str, Any] = {"at": 0.0, "value": leer}

    def probe() -> dict[str, Any]:
        now = _time.monotonic()
        if now - state["at"] >= ttl_s:
            try:
                state["value"] = printer_mod.presence()
            except Exception as fehler:  # noqa: BLE001 - no printer is a perfectly normal state
                state["value"] = {"ready": False, "queue": None, "attached": None,
                                  "reason": str(fehler)}
            state["at"] = now
        return dict(state["value"])

    return probe


def _start_gpio(config, use_mock: bool):
    """Same idea for GPIO: a wiring problem must not take the whole tool down."""
    if not use_mock:
        gpio = create_gpio(config, use_mock=False)
        try:
            gpio.start()
            return gpio, None
        except Exception as exc:  # noqa: BLE001 - degrade instead of dying
            log.warning("Real GPIO unavailable, falling back to mock: %s", exc)
            note = f"GPIO nicht verfügbar, Mock aktiv: {exc}"
            gpio = create_gpio(config, use_mock=True)
            gpio.start()
            return gpio, note

    gpio = create_gpio(config, use_mock=True)
    gpio.start()
    return gpio, None


def _start_leds(config, use_mock: bool):
    """The LED strip is optional; missing hardware must not stop the tool."""
    if not use_mock:
        leds = create_leds(config, use_mock=False)
        try:
            leds.start()
            return leds, None
        except Exception as exc:  # noqa: BLE001 - degrade instead of dying
            log.warning("LED strip unavailable, falling back to mock: %s", exc)
            note = f"LED-Kette nicht verfügbar, Mock aktiv: {exc}"
            leds = create_leds(config, use_mock=True)
            leds.start()
            return leds, note

    leds = create_leds(config, use_mock=True)
    leds.start()
    return leds, None
