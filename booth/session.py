"""The photo session: one run from pressing start to keeping or discarding.

The server owns the state and the timing, the screen only renders what it is
told. That way a tap on the display and a press on the physical button take
exactly the same path, and the countdown can never drift away from the light
and the shutter.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .layouts import build_layouts, compose
from .overlays import build_background

log = logging.getLogger(__name__)

IDLE = "idle"
CHOOSE = "choose"
READY = "ready"
AWAIT = "await"
COUNTDOWN = "countdown"
CAPTURING = "capturing"
COMPOSING = "composing"
REVIEW = "review"
DONE = "done"
FAILED = "failed"

#: Test shots live here, apart from the pictures of the party.
TEST_DIR_NAME = "test"
#: How many to keep - enough to compare against the previous try.
TEST_SHOTS_KEPT = 5


@dataclass
class BoothSettings:
    event_title: str = "Fotobox"
    event_subtitle: str = ""
    enabled_layouts: list[str] = field(default_factory=lambda: ["single", "strip4"])
    countdown_s: int = 3
    review_s: float = 20.0
    #: How long the booth waits for the next trigger before giving up.
    await_s: float = 30.0
    done_s: float = 9.0
    background_style: str = "creme"
    caption_font: str = "serif"
    caption_colour: str = ""
    caption_size_mm: float = 4.5
    #: Printing straight from the guest screen.
    printing_enabled: bool = True
    #: Gallery of the last pictures on the start screen. Off, because it shows
    #: everyone at the screen the pictures of everyone before them and allows
    #: unlimited reprints - both are things you only want on purpose.
    gallery_enabled: bool = False
    #: Six a side, so twelve in all. Twelve divides by three and by four - so a
    #: series is always shown complete, whether it is three shots or four.
    gallery_count: int = 6
    pin: str = "1234"

    @classmethod
    def from_config(cls, config) -> "BoothSettings":
        raw = config.section("booth")
        known = {f: raw[f] for f in cls.__dataclass_fields__ if f in raw}
        return cls(**known)


class BoothSession:
    """Runs one photo session in the background and reports its state."""

    def __init__(self, config, camera, gpio, capture_dir: Path,
                 on_keep: Callable[[Path, list[Path], str | None], None] | None = None,
                 events=None, light=None, usb=None) -> None:
        self.config = config
        self.camera = camera
        #: The USB stick. Without it no session starts - the pictures would
        #: have nowhere they belong.
        self.usb = usb
        self.gpio = gpio
        self.light = light
        self.capture_dir = capture_dir
        self.result_dir = capture_dir / "sessions"
        self.result_dir.mkdir(parents=True, exist_ok=True)
        self.on_keep = on_keep
        self.events = events

        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        #: Aborted rather than merely ended: the shots taken so far are then
        #: deleted. Set on the UI thread, cleaned up on the session thread -
        #: only there is it certain that no more will arrive.
        self._abort = threading.Event()
        #: Discard this one shot only. The series stays and waits for the
        #: next shutter press.
        self._skip = threading.Event()
        self._advance = threading.Event()

        self.state = IDLE
        self.layout_id: str | None = None
        self.shot = 0
        self.shots = 0
        self.countdown = 0
        self.shot_paths: list[Path] = []
        self.result_path: Path | None = None
        self.error: str | None = None
        self.deadline: float | None = None
        #: Absolute moment of the shutter, while the countdown is running.
        self.shutter_at: float | None = None

    # -- settings ----------------------------------------------------------
    @property
    def settings(self) -> BoothSettings:
        return BoothSettings.from_config(self.config)

    def available_layouts(self) -> list[dict[str, Any]]:
        settings = self.settings
        allowed = settings.enabled_layouts
        # With the configured caption size, so the tiles in the settings show
        # the real layout - a larger caption leaves less room for pictures.
        return [lay.to_dict() for key, lay in build_layouts(settings.caption_size_mm).items()
                if key in allowed]

    # -- public API --------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            settings = self.settings
            layouts = self.available_layouts()
            remaining = None
            if self.deadline:
                remaining = max(0.0, round(self.deadline - time.monotonic(), 1))
            return {
                "state": self.state,
                "layout": self.layout_id,
                "shot": self.shot,
                "shots": self.shots,
                "countdown": self.countdown,
                # Seconds until the shutter. The display counts on its own
                # clock from this and does not depend on every poll.
                "countdown_in": (max(0.0, round(self.shutter_at - time.monotonic(), 2))
                                 if self.shutter_at else None),
                "result_url": (f"/booth/result/{self.result_path.name}"
                               if self.result_path else None),
                # The individual shots behind the result. On the result screen
                # it should be possible to print just one of them.
                "shot_urls": [f"/captures/{p.name}" for p in self.shot_paths],
                "error": self.error,
                "remaining_s": remaining,
                "event": {"title": settings.event_title, "subtitle": settings.event_subtitle},
                "layouts": layouts,
                "single_layout": layouts[0]["id"] if len(layouts) == 1 else None,
                "light": round(self._light_value(), 2),
                "printing_enabled": bool(settings.printing_enabled),
                "gallery": {"enabled": bool(settings.gallery_enabled),
                            "count": int(settings.gallery_count)},
            }

    def view(self) -> dict[str, Any]:
        """The raw state, for an interface inside the same process.

        Like snapshot(), but without layouts and URLs: the native interface
        asks ten times a second and needs file paths, not URLs.
        """
        with self._lock:
            return {
                "state": self.state,
                "layout": self.layout_id,
                "shot": self.shot,
                "shots": self.shots,
                "shot_paths": list(self.shot_paths),
                "result_path": self.result_path,
                "error": self.error,
                "deadline": self.deadline,
                "shutter_at": self.shutter_at,
            }

    #: States a new session may begin from. CHOOSE belongs here: picking a tile
    #: on the selection screen is the second half of one start, not a new one.
    STARTABLE = (IDLE, CHOOSE, DONE, FAILED)

    def start(self, layout_id: str | None = None) -> dict[str, Any]:
        if not self.stick_da():
            return {"ok": False, "error": "Ohne USB-Stick keine Aufnahme"}
        with self._lock:
            if self.state not in self.STARTABLE:
                return {"ok": False, "error": f"Läuft bereits ({self.state})"}
            layouts = self.available_layouts()
            if not layouts:
                return {"ok": False, "error": "Kein Layout freigegeben"}
            if layout_id is None:
                # Never show a choice with one option.
                if len(layouts) > 1:
                    self._reset()
                    self.state = CHOOSE
                    self._arm(30)
                    return {"ok": True, "state": self.state}
                layout_id = layouts[0]["id"]
            if layout_id not in {lay["id"] for lay in layouts}:
                return {"ok": False, "error": f"Layout {layout_id} ist nicht freigegeben"}

            self._reset()
            self.layout_id = layout_id
            self.shots = build_layouts()[layout_id].shots
            self._cancel.clear()
            self._skip.clear()
            self._thread = threading.Thread(target=self._run, name="booth-session", daemon=True)
            self._thread.start()
            return {"ok": True, "state": self.state, "layout": layout_id}

    def next_shot(self) -> dict[str, Any]:
        """Guests trigger every picture of a series themselves."""
        with self._lock:
            if self.state != AWAIT:
                return {"ok": False, "error": "Gerade wird kein Bild erwartet"}
        self._advance.set()
        return {"ok": True, "state": COUNTDOWN}

    def redo_last(self) -> dict[str, Any]:
        """Take back the shot just taken.

        Only while waiting, i.e. exactly when the guests are standing in front
        of the screen anyway, thinking about the next pose. It costs no extra
        time, because the pause is already there - and it is the only action
        that makes any sense here: the sheet needs its pictures, so "discard"
        could not mean anything at this point except "again".
        """
        with self._lock:
            if self.state != AWAIT:
                return {"ok": False, "error": "Gerade wird nicht gewartet"}
            if not self.shot_paths:
                return {"ok": False, "error": "Es gibt noch keine Aufnahme"}
            weg = self.shot_paths.pop()
            self.shot = len(self.shot_paths) + 1
            # The waiting period starts over: somebody who retakes should not
            # lose the whole session to a timeout straight afterwards.
            self._arm(self.settings.await_s)
        # Delete in the background: the file may still be being written, and
        # this is called from the interface, which must not wait.
        def delete_repeated() -> None:
            try:
                self.camera.wait_for_writes()
            except Exception:  # noqa: BLE001 - the file is being discarded anyway
                log.debug("Waiting for the repeated shot failed", exc_info=True)
            try:
                Path(weg).unlink(missing_ok=True)
            except OSError:
                log.warning("Could not delete the repeated shot %s", weg)

        threading.Thread(target=delete_repeated, name="delete-repeated", daemon=True).start()
        # Start at once. Somebody retaking has already decided - having to tap
        # start again would be a click that says nothing, and the countdown is
        # the preparation time anyway.
        self._advance.set()
        self._note(f"Aufnahme wiederholt: {Path(weg).name}", "warn")
        return {"ok": True, "shot": self.shot, "shots": self.shots}

    def keep(self) -> dict[str, Any]:
        with self._lock:
            if self.state != REVIEW:
                return {"ok": False, "error": "Gerade gibt es nichts zu behalten"}
            self.state = DONE
            self._arm(self.settings.done_s)
            result, shots = self.result_path, list(self.shot_paths)
        if result:
            self._merke_sitzung(result, shots)
        self._note(f"Bild behalten: {result.name if result else '?'}", "good")
        if self.on_keep and result:
            try:
                self.on_keep(result, shots, self.layout_id)
            except Exception:  # noqa: BLE001 - a queue problem must not break the booth
                log.exception("on_keep handler failed")
        return {"ok": True, "state": DONE}

    def discard(self) -> dict[str, Any]:
        with self._lock:
            if self.state != REVIEW:
                return {"ok": False, "error": "Gerade gibt es nichts zu verwerfen"}
            for path in [*self.shot_paths, self.result_path]:
                if path:
                    try:
                        Path(path).unlink(missing_ok=True)
                    except OSError:
                        log.warning("Could not delete %s", path)
            # Straight back to the start. A separate "Geloescht" screen with
            # "Nochmal" and "Fertig" offered two routes to the same place:
            # Nochmal was the same as START, and Fertig went there anyway.
            self._reset()
        self._set_light(self._idle_duty())
        self._note("Bild verworfen und gelöscht", "warn")
        return {"ok": True, "state": IDLE}

    def cancel(self) -> dict[str, Any]:
        self._cancel.set()
        self._advance.set()
        with self._lock:
            self._reset()
        self._set_light(self._idle_duty())
        return {"ok": True, "state": IDLE}

    def abort(self) -> dict[str, Any]:
        """The abort button. What it ends depends on what is running.

        If a shot is running - the countdown or the shutter itself - that is
        what is meant: it is discarded, the series stays and waits for the
        next shutter press. If none is running, the series is meant, and the
        box goes home.

        That is the least surprising reading: you interrupt what is in front
        of you. And anyone who wants out entirely presses again - nothing is
        running then, and the same button ends the series.

        Ending deletes the shots taken so far. They belong to a sheet that
        will never exist, and would otherwise sit on the stick without anyone
        having wanted them.

        The cleaning up does not happen here but on the session thread. That
        thread may have the camera open at this very moment; deleting and
        resetting in parallel here would have it write the next shot into a
        list that already belongs to the next session.
        """
        with self._lock:
            state = self.state
            laeuft = self._thread is not None and self._thread.is_alive()
        if state == IDLE:
            return {"ok": True, "state": IDLE, "scope": "none"}
        if laeuft and state in (COUNTDOWN, CAPTURING):
            self._skip.set()
            return {"ok": True, "state": state, "scope": "shot"}
        self._note("Durchgang abgebrochen", "warn")
        if laeuft:
            self._abort.set()
            self._cancel.set()
            self._advance.set()
            return {"ok": True, "state": state, "scope": "session"}
        # No thread any more - selection, review or result. Nothing is half
        # finished there, only the way home.
        return {**self.cancel(), "scope": "session"}

    def _aufnahme_verworfen(self, pfad: Path | None = None) -> None:
        """Drop a single shot. The series carries on.

        Afterwards the loop continues at the top, and because a shot is
        already behind us it lands in the wait for the shutter - the same slot
        is offered again.
        """
        self._skip.clear()
        self._set_light(self._idle_duty())
        if pfad is not None:
            # Aborted during the shutter: the picture has already been written.
            try:
                self.camera.wait_for_writes()
            except Exception:  # noqa: BLE001 - it is being deleted anyway
                log.debug("Waiting for writes failed", exc_info=True)
            try:
                Path(pfad).unlink(missing_ok=True)
            except OSError:
                log.warning("Could not delete %s", pfad)
        self._note("Aufnahme abgebrochen, die Serie läuft weiter", "warn")

    def _abgebrochen(self, nachzuegler: Path | None = None) -> None:
        """Clean up after a cancel. Runs on the session thread."""
        if not self._abort.is_set():
            return          # an ordinary cancel(), which cleaned up already
        self._abort.clear()
        with self._lock:
            if nachzuegler is not None:
                self.shot_paths.append(nachzuegler)
            blatt = self.result_path
        self._drop_partial()
        # If the abort only arrived once the sheet had been composed, that has
        # to go too - otherwise the one piece the guests explicitly did not
        # want would be the one left lying around.
        if blatt is not None:
            try:
                Path(blatt).unlink(missing_ok=True)
            except OSError:
                log.warning("Could not delete %s", blatt)

    def test_shot(self, countdown_s: float = 3.0) -> dict[str, Any]:
        """One picture under the real capture light, for setting the booth up.

        Whoever sets the box up stands at the screen, which sits right under the
        camera - the wrong distance, and lit only by the modelling light. This
        runs the same countdown and the same light as a real picture, so there
        is time to step back to where the guests will stand and see what they
        will actually get. Nothing is composed, kept, copied or uploaded: it is
        a look through the lens, not a session.
        """
        with self._lock:
            if self.state not in self.STARTABLE:
                return {"ok": False, "error": f"Läuft bereits ({self.state})"}
            self.state = COUNTDOWN
            self.shot, self.shots = 1, 1
            self._arm(None)
        # A cancel left over from an earlier session would end this one before
        # it starts.
        self._cancel.clear()

        try:
            settings = self.settings
            self._aufloesung_setzen()

            self._set_light(self._idle_duty())
            # The same sequence as a real shot, so the test photo really is
            # lit the way the guests will be later.
            schuss_um = time.monotonic() + max(1, int(countdown_s))
            licht_an_um = schuss_um - self._light_ramp_s()
            licht_an = False
            for number in range(max(1, int(countdown_s)), 0, -1):
                with self._lock:
                    self.countdown = number
                ziel = schuss_um - (number - 1)
                if not licht_an and licht_an_um <= ziel:
                    if self._warten(licht_an_um):
                        return {"ok": False, "error": "Abgebrochen"}
                    self._set_light(self._capture_duty())
                    licht_an = True
                if self._warten(ziel):
                    return {"ok": False, "error": "Abgebrochen"}

            with self._lock:
                self.state = CAPTURING
                self.countdown = 0
            info = self.camera.capture_still()
            self.camera.wait_for_writes()
            path = self._park_test_shot(self.capture_dir / info["file"])
            self._note("Testfoto erstellt")
            return {"ok": True, "file": path.name,
                    "url": f"/captures/{TEST_DIR_NAME}/{path.name}"}

        except Exception as exc:  # noqa: BLE001 - a test must never wedge the booth
            log.exception("Test shot failed")
            self._note(f"Testfoto fehlgeschlagen: {exc}", "error")
            return {"ok": False, "error": str(exc) or exc.__class__.__name__}
        finally:
            self._set_light(self._idle_duty())
            with self._lock:
                self._reset()

    def _merke_sitzung(self, result: Path, shots: list[Path]) -> None:
        """Put a small sidecar note next to every finished sheet.

        It records which individual shots belong to it. Without that there
        would be no way to tell later which of the many capture files belong
        to which sheet - and the gallery could only ever show the sheet.
        """
        try:
            beischrift = result.with_suffix(".json")
            beischrift.write_text(json.dumps({
                "at": time.time(),
                "result": result.name,
                "shots": [p.name for p in shots if p and Path(p).exists()],
            }, ensure_ascii=False), encoding="utf-8")
        except OSError:
            log.warning("Could not write the session note for %s", result.name)

    def recent(self, limit: int = 6) -> list[dict[str, Any]]:
        """Die zuletzt behaltenen Blaetter, neueste zuerst."""
        eintraege: list[dict[str, Any]] = []
        try:
            noten = sorted(self.result_dir.glob("*.json"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError:
            return eintraege
        for note in noten[:limit]:
            try:
                daten = json.loads(note.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            blatt = self.result_dir / str(daten.get("result", ""))
            if not blatt.exists():
                continue
            eintraege.append({
                "at": daten.get("at"),
                "result_url": f"/booth/result/{blatt.name}",
                "shot_urls": [f"/captures/{n}" for n in daten.get("shots", [])
                              if (self.capture_dir / n).exists()],
            })
        return eintraege

    def _park_test_shot(self, path: Path) -> Path:
        """Put a test picture aside and keep only the last few.

        A test shot is not a photograph of the party: it must not turn up in the
        list of captures, must not be printed or copied, and must not quietly
        fill the card. It is kept only long enough to look at and to compare
        with the one before.
        """
        target_dir = self.capture_dir / TEST_DIR_NAME
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / path.name
        try:
            path.replace(target)
        except OSError:
            log.warning("Could not move the test shot to %s", target_dir)
            return path

        kept = sorted(target_dir.glob("capture-*.jpg"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        for old in kept[TEST_SHOTS_KEPT:]:
            try:
                old.unlink()
            except OSError:
                log.debug("Could not delete the old test shot %s", old)
        return target

    def tick(self) -> None:
        """Called by the poll: sends the session home when a screen times out."""
        with self._lock:
            if self.deadline is None or time.monotonic() < self.deadline:
                return
            state = self.state
        if state == REVIEW:
            # An unanswered picture is kept: a spare one is easier to live
            # with than a lost one.
            self.keep()
        elif state in (DONE, CHOOSE, FAILED):
            self.cancel()
        # AWAIT runs its own clock inside the session thread.

    # -- internals ---------------------------------------------------------
    def stick_da(self) -> bool:
        """Is a stick plugged in? No stick, no photographs.

        The pictures belong to the guest, and the guest takes them away on the
        stick. Without it, shots would be made that nobody collects and that
        stay behind on the card - exactly what this box must not do.
        """
        if self.usb is None:
            return True
        try:
            return bool(self.usb.status().get("present"))
        except Exception:  # noqa: BLE001 - lieber fotografieren als blockieren
            log.debug("USB-Zustand nicht lesbar", exc_info=True)
            return True

    def _aufloesung_setzen(self) -> None:
        """Take the capture size from the camera configuration.

        This once existed twice: a "capture_size" key under "booth" and one
        under "camera". The camera read the one under "camera"; the session
        set the one under "booth" before every run - and so silently
        overwrote the other. Anyone changing the camera size saw the old one
        again on the next picture. Only the one under "camera" is left.
        """
        size = self.config.section("camera").get("capture_size")
        if size:
            self.camera.set_capture_size(int(size[0]), int(size[1]))

    def _note(self, text: str, level: str = "info") -> None:
        if self.events is not None:
            self.events.add(text, level)

    def _reset(self) -> None:
        self.state = IDLE
        self.layout_id = None
        self.shot = 0
        self.shots = 0
        self.countdown = 0
        self.shot_paths = []
        self.result_path = None
        self.error = None
        self.deadline = None
        self.shutter_at = None

    def _arm(self, seconds: float) -> None:
        self.deadline = time.monotonic() + seconds if seconds else None

    def _idle_duty(self) -> float:
        return float(self.config.section("gpio").get("light_idle_duty", 0.15))

    def _capture_duty(self) -> float:
        return float(self.config.section("gpio").get("light_capture_duty", 1.0))

    def _light_value(self) -> float:
        if self.light is not None:
            return self.light.value
        return getattr(self.gpio, "light_duty", 0.0)

    def _set_light(self, duty: float) -> None:
        """Set the lamp - whichever one happens to be connected."""
        try:
            if self.light is not None:
                self.light.set(duty)
            else:
                self.gpio.set_light(duty)
        except Exception:  # noqa: BLE001 - no light hardware yet, must not stop the flow
            log.debug("set_light failed", exc_info=True)

    def _light_ramp_s(self) -> float:
        """How long before the shutter the capture light comes on.

        Keep it short: the guests should not stand dazzled for seconds on end,
        and the lamp should not heat for longer than necessary. It must not be
        too short either - a lamp addressed over radio needs its response
        time.
        """
        try:
            ms = float(self.config.section("gpio").get("light_ramp_ms", 400))
        except (TypeError, ValueError):
            ms = 400.0
        return max(0.0, min(ms, 5000.0)) / 1000.0

    def _warten(self, bis: float) -> str:
        """Wait until a given moment.

        Returns the reason the wait ended: "" means the time is up. "cancel"
        means the whole run was aborted, "skip" only this one shot. Both are
        falsy while waiting and truthy as soon as something intervenes - so
        callers that only want to know whether can still read the return value
        as a yes/no.

        The wait happens in small slices, so an abort arrives at once rather
        than at the next digit. The moment itself stays accurate to the
        millisecond regardless: the last slice ends exactly when the shutter
        is due.
        """
        while True:
            if self._cancel.is_set():
                return "cancel"
            if self._skip.is_set():
                return "skip"
            rest = bis - time.monotonic()
            if rest <= 0:
                return ""
            self._cancel.wait(min(rest, 0.05))

    def _run(self) -> None:
        settings = self.settings
        try:
            self._aufloesung_setzen()

            self._set_light(self._idle_duty())

            # The counter hangs off the shots already taken, not off a fixed
            # loop. That is the only way a retake can take a shot back: the
            # next pass fills the same slot.
            erste = True
            while len(self.shot_paths) < self.shots:
                index = len(self.shot_paths) + 1
                # Guests trigger every picture of a series. Pressing start is
                # that trigger for the first one - asking twice for the same
                # picture only makes people wonder what they did wrong.
                if not erste:
                    with self._lock:
                        self.shot = index
                        self.state = AWAIT
                        self._arm(settings.await_s)
                    self._advance.clear()
                    # Wait for the trigger, but not forever: an abandoned session
                    # must leave nothing behind.
                    waited = 0.0
                    while not self._advance.is_set():
                        if self._cancel.wait(0.1):
                            return self._abgebrochen()
                        waited += 0.1
                        if waited >= settings.await_s:
                            self._note("Sitzung abgebrochen, niemand hat ausgelöst", "warn")
                            self._drop_partial()
                            return
                erste = False
                self._advance.clear()
                # After a retake during the wait, the number has shifted.
                index = len(self.shot_paths) + 1

                # Everything hangs off one absolute moment rather than a chain
                # of one second sleeps. Sleeping five times for "about a second"
                # drifts, and the screen skips numbers; with a fixed deadline
                # each digit lasts exactly one second and the shutter fires when
                # the display reaches zero.
                shutter_at = time.monotonic() + settings.countdown_s
                with self._lock:
                    self.shot = index
                    self.state = COUNTDOWN
                    self.shutter_at = shutter_at
                    self._arm(None)
                licht_an_um = shutter_at - self._light_ramp_s()
                licht_an = False
                grund = ""
                for number in range(settings.countdown_s, 0, -1):
                    with self._lock:
                        self.countdown = number
                    ziel = shutter_at - (number - 1)
                    # The capture light only comes on shortly before the shutter.
                    # If that moment falls inside this second, the wait is
                    # split here: up to the light, then up to the next digit.
                    if not licht_an and licht_an_um <= ziel:
                        grund = self._warten(licht_an_um)
                        if grund:
                            break
                        self._set_light(self._capture_duty())
                        licht_an = True
                    grund = self._warten(ziel)
                    if grund:
                        break

                if grund == "cancel":
                    return self._abgebrochen()
                if grund == "skip":
                    self._aufnahme_verworfen()
                    continue

                with self._lock:
                    self.state = CAPTURING
                    self.countdown = 0
                    self.shutter_at = None
                info = self.camera.capture_still()
                self._set_light(self._idle_duty())
                pfad = self.capture_dir / info["file"]
                if self._cancel.is_set():
                    # The abort arrived while the camera had already fired.
                    # This picture still belongs to it and goes with it.
                    return self._abgebrochen(pfad)
                if self._skip.is_set():
                    # The same thing one size down: only this shot goes.
                    self._aufnahme_verworfen(pfad)
                    continue
                with self._lock:
                    self.shot_paths.append(pfad)


            with self._lock:
                self.state = COMPOSING
            # The last shots may still be being written.
            self.camera.wait_for_writes()
            self.result_path = self._compose()
            # Composing cannot be interrupted; anyone who aborts during it is
            # picked up here.
            if self._cancel.is_set():
                return self._abgebrochen()
            self._note(f"Bild erstellt: {self.result_path.name} ({self.shots} Aufnahmen)")

            with self._lock:
                self.state = REVIEW
                self._arm(settings.review_s)

        except Exception as exc:  # noqa: BLE001 - always leave a usable state
            log.exception("Session failed")
            self._set_light(self._idle_duty())
            with self._lock:
                self.error = str(exc) or exc.__class__.__name__
                self.state = FAILED
                self._arm(8)
            self._note(f"Sitzung fehlgeschlagen: {self.error}", "error")

    def _drop_partial(self) -> None:
        """Delete the shots of a session nobody finished."""
        with self._lock:
            paths = list(self.shot_paths)
            self._reset()
        try:
            self.camera.wait_for_writes()
        except Exception:  # noqa: BLE001 - the pictures are being deleted anyway
            log.debug("Waiting for writes failed", exc_info=True)
        for path in paths:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                log.warning("Could not delete %s", path)
        self._set_light(self._idle_duty())

    def _compose(self) -> Path:
        settings = self.settings
        layout = build_layouts(settings.caption_size_mm)[self.layout_id]
        background = None
        if not layout.full_bleed:
            background = build_background(
                layout.canvas, settings.background_style,
                self.result_dir / f"bg-{settings.background_style}.png")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        return compose(
            layout, self.shot_paths,
            background_path=background,
            title=settings.event_title, subtitle=settings.event_subtitle,
            caption_font=settings.caption_font,
            caption_colour=settings.caption_colour,
            caption_size_mm=settings.caption_size_mm,
            output_path=self.result_dir / f"{stamp}-{layout.id}.jpg")
