"""What the lamp hangs off - and how the box brightens and dims it.

The booth knows four kinds of light, switchable through one setting:

    pwm     A 12 V panel on a MOSFET module, dimmed through the Pi's PWM.
            This is the home-made option: full control, at the price of
            soldering and one more power supply.
    dmx     Any lamp on a DMX bus - the standard of the events industry. It
            makes the box compatible with fixtures from practically any
            manufacturer, without anybody here reimplementing a protocol.
    godox   A Godox studio light, addressed over Bluetooth.
    none    A bought lamp with no remote control. The box does not touch it;
            the brightness is set on the lamp itself.

They all have the same methods, so the rest of the software need not know
which is working. Anyone who needs a fifth - a lamp with a network interface,
say - writes a class with set() and enters it in create_light(). Nothing more
is required.

The values for the modelling light and the capture light stay in the "gpio"
section of the configuration even where no GPIO is involved at all: they apply
to every dimmable lamp, and renaming the section would change every box
already out there.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: What may appear in the configuration under light.kind.
KINDS = ("pwm", "dmx", "godox", "none")


class LightBase:
    """The interface every kind of light shares."""

    kind = "base"

    #: Can the box change the brightness at all? If not, the interface hides
    #: its light controls - a slider that does nothing is worse than none.
    dimmable = True

    #: Does this kind of light have a link that can drop? Only then does the
    #: interface show a sign of life. A wire on a MOSFET does not fail
    #: invisibly; a radio link does.
    monitored = False

    #: Can the box change the colour temperature? A panel on a MOSFET is
    #: whatever white it was bought as, and a slider for it would be a lie.
    tunable = False

    def __init__(self, config) -> None:
        self.config = config
        self.value = 0.0
        self.note = ""
        #: Is the link up right now? Always True where there is no link -
        #: otherwise a lamp on a wire would report a fault constantly.
        self.connected = True
        #: When the box last had proof of that (timestamp).
        self.last_ok = 0.0
        #: Since when the present state has applied.
        self.since = time.time()

    def _verbindung(self, steht: bool) -> None:
        """Record the state - the timestamp only when it changes."""
        if steht:
            self.last_ok = time.time()
        if steht != self.connected:
            self.connected = steht
            self.since = time.time()

    def start(self) -> None:
        """Open the connection, if this kind of light needs one."""

    def set(self, duty: float) -> None:
        self.value = max(0.0, min(1.0, float(duty)))

    def stop(self) -> None:
        """Light off and connection closed."""


class PwmLight(LightBase):
    """The home-made panel on the MOSFET module.

    This class does almost nothing: the dimming lives in the Pi's PWM, which
    is in the GPIO module. It exists anyway, so that the sequence is the same
    for every kind of light.
    """

    kind = "pwm"

    def __init__(self, config, gpio) -> None:
        super().__init__(config)
        self.gpio = gpio

    def set(self, duty: float) -> None:
        super().set(duty)
        try:
            self.gpio.set_light(self.value)
        except Exception:  # noqa: BLE001 - the booth carries on without light
            log.debug("set_light failed", exc_info=True)

    def stop(self) -> None:
        try:
            self.gpio.set_light(0.0)
        except Exception:  # noqa: BLE001
            log.debug("Could not switch the light off", exc_info=True)


class NoLight(LightBase):
    """A bought lamp that nobody controls remotely.

    It burns all evening at whatever brightness was set on it. The box
    remembers the value it wanted anyway, so the sequence stays the same - it
    simply does nothing with it.
    """

    kind = "none"
    dimmable = False


class DmxLight(LightBase):
    """A lamp on a DMX bus.

    DMX512 is the standard of the events industry: 250000 baud, eight data
    bits, two stop bits, no parity. Every packet begins with a BREAK, then a
    start byte of 0x00 and up to 512 channel values. A receiver wants to see
    packets continuously or it falls to black after about a second - so a
    background thread here keeps sending regardless of whether anything
    changed.

    On the Pi a TTL to RS-485 converter is needed. Two routes:

      * A USB adapter (the common FTDI ones). The port then appears as
        /dev/ttyUSB0 and Bluetooth stays free.
      * A MAX485 on the Pi's serial port, i.e. /dev/serial0. Cheaper, but
        careful: the Pi's mini UART is tied to the core clock and does not
        hit 250000 baud reliably. That means putting the full UART on the
        header, and it is reserved for Bluetooth out of the box.

    The BREAK and MAB timings here come out longer than the 88 and 8
    microseconds of the standard, because Python cannot sleep that finely.
    That is allowed: the standard sets minimum times, not maximum ones.
    """

    kind = "dmx"

    #: Packets per second. The standard allows up to 44; more gains nothing.
    RATE = 30
    SLOTS = 512

    def __init__(self, config) -> None:
        super().__init__(config)
        cfg = config.section("light")
        self.port = str(cfg.get("dmx_port", "/dev/ttyUSB0") or "/dev/ttyUSB0")
        self.channel = max(1, min(self.SLOTS, int(cfg.get("dmx_channel", 1) or 1)))
        # Some fixtures want other channels set before the dimmer responds at
        # all - a mode channel, say. Those sit in the configuration as
        # {"channel": value}.
        self.extra: dict[int, int] = {}
        for schluessel, wert in (cfg.get("dmx_extra") or {}).items():
            try:
                self.extra[int(schluessel)] = max(0, min(255, int(wert)))
            except (TypeError, ValueError):
                log.warning("dmx_extra: %r=%r ist kein Kanalwert", schluessel, wert)
        self._frame = bytearray(self.SLOTS + 1)      # [0] is the start byte
        for kanal, wert in self.extra.items():
            if 1 <= kanal <= self.SLOTS:
                self._frame[kanal] = wert
        self._serial = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        import serial  # noqa: PLC0415 - only a DMX user needs the package

        self._serial = serial.Serial(
            self.port, baudrate=250000, bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_TWO, timeout=0)
        self._thread = threading.Thread(target=self._senden, name="dmx", daemon=True)
        self._thread.start()
        log.info("DMX on %s, channel %s", self.port, self.channel)

    def set(self, duty: float) -> None:
        super().set(duty)
        self._frame[self.channel] = round(self.value * 255)

    def _senden(self) -> None:
        takt = 1.0 / self.RATE
        while not self._stop.is_set():
            begonnen = time.monotonic()
            try:
                self._serial.break_condition = True
                time.sleep(0.0002)                 # BREAK, Norm: ab 88 us
                self._serial.break_condition = False
                time.sleep(0.00002)                # MAB, Norm: ab 8 us
                self._serial.write(bytes(self._frame))
            except Exception:  # noqa: BLE001 - an unplugged cable must not bring anything down
                log.debug("DMX frame failed", exc_info=True)
                self._stop.wait(1.0)
                continue
            rest = takt - (time.monotonic() - begonnen)
            if rest > 0:
                self._stop.wait(rest)

    def stop(self) -> None:
        self.set(0.0)
        time.sleep(2.0 / self.RATE)                # still send the blackout
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:  # noqa: BLE001
                log.debug("Could not close the DMX port", exc_info=True)


class GodoxLight(LightBase):
    """A Godox studio light, addressed over Bluetooth.

    These lamps are not simple Bluetooth devices but nodes in a Bluetooth
    mesh. The protocol has been reverse engineered; we use the library from
    github.com/hirpusnoctis/ha-godox-mesh (MIT), which install-pi.sh fetches
    into vendor/godox-mesh.

    Setup happens once on the command line - provisioning, binding the app
    key - and produces a file holding the mesh keys. This class takes the path
    to it from the configuration. The README explains how.

    **Why a thread of its own.** The library is asynchronous, our capture is
    not. More importantly, the connection must not be rebuilt per command:
    that takes one to three seconds on the Pi, while the light's lead time is
    a few hundred milliseconds. So a thread here holds an open connection and
    set() merely puts down the value it wants. Measured on the Pi: 3 ms per
    command, and the lamp confirms the value when asked.
    """

    kind = "godox"

    #: How long the first connection is waited for before startup carries on.
    #: The box must not get stuck on a lamp.
    CONNECT_TIMEOUT = 25.0

    #: Pause between two connection attempts, in case the lamp is switched off.
    RETRY_S = 15.0

    #: Head start for the mesh counter on every boot. Every command consumes
    #: a sequence number, and the lamp silently discards anything it has seen
    #: before - no error, it simply does nothing. If the box loses power
    #: before the last state was saved, the counter would be behind
    #: afterwards. Observed exactly like that on the Pi. The head start costs
    #: nothing: the counter is 24 bits wide.
    SEQUENCE_MARGIN = 2000

    #: How often the link is checked. If something happens anyway - a new
    #: brightness value - that counts as proof and the clock restarts.
    HEARTBEAT_S = 20.0

    #: Every how-manyth round the lamp itself is actually asked. In between,
    #: asking BlueZ is enough and costs nothing.
    PROBE_EVERY = 3

    #: How long the answer may take.
    PROBE_TIMEOUT = 4.0

    #: How often it may fail to arrive before the link counts as dead. One
    #: missing answer can also mean the lamp was simply busy.
    PROBE_MISSES = 2

    monitored = True
    tunable = True

    #: What the lamp is set to when nothing says otherwise. 5600 K is what a
    #: Godox leaves the factory on, so a box that never touches the setting
    #: behaves exactly as before.
    DEFAULT_CCT = 5600

    def __init__(self, config, base_dir=None) -> None:
        super().__init__(config)
        cfg = config.section("light")
        self.address = str(cfg.get("address", "") or "").strip()
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).resolve().parents[2]
        self.state_path = Path(str(cfg.get("mesh_state", "") or "")
                               or self.base_dir / "godox-mesh-state.json")
        self._loop: Any = None
        self._thread: threading.Thread | None = None
        self._wanted = 0.0
        self._changed: Any = None
        self._stop: Any = None
        self._ready = threading.Event()
        self._gesendet: Any = None
        self.connected = False
        self.since = time.time()
        #: Has this lamp ever answered a status request? Not every model
        #: does. One that never answers would otherwise have the box
        #: reconnecting every minute - so it stops being asked and only BlueZ
        #: is believed.
        self._antwortet = False

    # -- Start and end ---------------------------------------------------------
    def start(self) -> None:
        if not self.address:
            raise ValueError("keine Bluetooth-Adresse eingetragen (light.address)")
        if not self.state_path.exists():
            raise FileNotFoundError(f"{self.state_path} fehlt - Leuchte noch nicht eingerichtet")
        self._pfad_vorbereiten()
        self._thread = threading.Thread(target=self._faden, name="godox", daemon=True)
        self._thread.start()
        # Wait for the first connection, but not forever: if the lamp is off
        # the box should still come up and keep trying later.
        if not self._ready.wait(self.CONNECT_TIMEOUT):
            self.note = ("Godox-Leuchte noch nicht erreicht - die Box versucht es weiter. "
                         "Ist sie eingeschaltet?")

    def _pfad_vorbereiten(self) -> None:
        """Make the bundled library importable."""
        import sys  # noqa: PLC0415

        ort = self.base_dir / "vendor" / "godox-mesh" / "src"
        if ort.is_dir() and str(ort) not in sys.path:
            sys.path.insert(0, str(ort))

    def cct(self) -> int:
        """The colour temperature, read fresh from the configuration.

        Fresh rather than remembered from startup, so that moving the slider
        in the settings reaches the lamp without a restart.
        """
        try:
            wert = int(self.config.section("light").get("cct") or self.DEFAULT_CCT)
        except (TypeError, ValueError):
            return self.DEFAULT_CCT
        return max(2000, min(10000, wert))

    def nudge(self) -> None:
        """Send the present values again, even though nothing was dimmed.

        The settings call this after a colour temperature change: brightness
        has not moved, so the thread would otherwise see nothing to do.
        """
        self._gesendet = None
        if self._loop is not None and self._changed is not None:
            try:
                self._loop.call_soon_threadsafe(self._changed.set)
            except RuntimeError:
                log.debug("Godox loop is gone", exc_info=True)

    def set(self, duty: float) -> None:
        super().set(duty)
        self._wanted = self.value
        if self._loop is not None and self._changed is not None:
            # Only nudge - the sending happens on our own thread. The caller
            # is in the middle of a countdown and must not wait here.
            try:
                self._loop.call_soon_threadsafe(self._changed.set)
            except RuntimeError:
                log.debug("Godox loop is gone", exc_info=True)

    def stop(self) -> None:
        self._wanted = 0.0
        if self._loop is not None and self._stop is not None:
            try:
                self._loop.call_soon_threadsafe(self._stop.set)
            except RuntimeError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    # -- the thread ------------------------------------------------------------
    def _faden(self) -> None:
        import asyncio  # noqa: PLC0415

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._changed = asyncio.Event()
        self._stop = asyncio.Event()
        try:
            self._loop.run_until_complete(self._arbeiten())
        except Exception:  # noqa: BLE001 - the booth carries on without light
            log.exception("Godox thread died")
        finally:
            self._loop.close()

    def _vorsprung(self, zustand: Any) -> Any:
        """Raise the mesh counter and save it immediately.

        MeshState is immutable, hence a new state rather than an assignment -
        otherwise the increment quietly goes nowhere.
        """
        import dataclasses  # noqa: PLC0415

        try:
            neuer = dataclasses.replace(
                zustand, sequence_number=int(zustand.sequence_number) + self.SEQUENCE_MARGIN)
        except (AttributeError, TypeError, ValueError):
            log.debug("No sequence number to raise", exc_info=True)
            return zustand
        self._schluessel_sichern(neuer)
        log.info("Godox mesh counter raised to %s", neuer.sequence_number)
        return neuer

    def _schluessel_sichern(self, zustand: Any) -> None:
        """Save the mesh keys in a way that cannot lose them.

        The library writes the sequence number out with every command. If it
        writes straight into the file and the box loses power at that moment,
        what is left is an empty file - and the lamp has to be provisioned
        again. Observed exactly like that on the Pi. So: write beside it
        first, then rename, which is one step as far as the filesystem is
        concerned.
        """
        vorlaeufig = self.state_path.with_suffix(".json.tmp")
        try:
            vorlaeufig.write_text(zustand.to_json(), encoding="utf-8")
            vorlaeufig.replace(self.state_path)
        except Exception:  # noqa: BLE001 - an old number beats no file at all
            log.warning("Could not save the mesh state", exc_info=True)

    async def _suchen(self) -> None:
        """A short scan, so BlueZ knows the lamp.

        Without it, connecting after a reboot fails with "Device not found":
        BlueZ only resolves an address it has seen recently. Observed exactly
        like that on the Pi - it only connected while a manual scan had been
        run shortly beforehand.
        """
        from bleak import BleakScanner  # noqa: PLC0415

        gefunden = await BleakScanner.find_device_by_address(self.address, timeout=12.0)
        if gefunden is None:
            raise ConnectionError(f"{self.address} nicht in Reichweite")

    async def _arbeiten(self) -> None:
        import asyncio  # noqa: PLC0415

        from godox_mesh_bt import GodoxController  # noqa: PLC0415
        from godox_mesh_bt.state import MeshState  # noqa: PLC0415

        while not self._stop.is_set():
            try:
                await self._suchen()
                zustand = self._vorsprung(MeshState.load(self.state_path))
                async with GodoxController(self.address, state=zustand,
                                           state_writer=self._schluessel_sichern) as leuchte:
                    self._verbindung(True)
                    self.note = ""
                    self._ready.set()
                    log.info("Godox light connected (%s)", self.address)
                    self._gesendet = None
                    runde, verpasst = 0, 0
                    while not self._stop.is_set():
                        jetzt = (self._wanted, self.cct())
                        if self._gesendet != jetzt:
                            self._gesendet = jetzt
                            # Brightness and colour temperature travel in one
                            # vendor command, so sending both costs no more
                            # than sending one.
                            await leuchte.set_params(brightness=round(jetzt[0] * 100),
                                                     cct=jetzt[1])
                            self._verbindung(True)
                        self._changed.clear()
                        try:
                            await asyncio.wait_for(self._changed.wait(),
                                                   timeout=self.HEARTBEAT_S)
                            continue      # a new value - that is proof enough
                        except asyncio.TimeoutError:
                            pass
                        # Heartbeat. The cheap question to BlueZ first.
                        if not leuchte.is_connected:
                            raise ConnectionError("Bluetooth-Verbindung ist weg")
                        runde += 1
                        if runde % self.PROBE_EVERY or (runde > self.PROBE_EVERY
                                                        and not self._antwortet):
                            self._verbindung(True)
                            continue
                        # Then the lamp itself. BlueZ still reports a
                        # half-open connection as connected; only the missing
                        # answer gives it away.
                        try:
                            await leuchte.request_status(timeout=self.PROBE_TIMEOUT)
                        except Exception as still:  # noqa: BLE001
                            if not self._antwortet:
                                # This model does not answer. Stop asking, or
                                # this ends in a loop of reconnections.
                                log.info("Godox light does not answer status requests "
                                         "(%s) - relying on the Bluetooth link alone", still)
                                continue
                            verpasst += 1
                            log.debug("Godox heartbeat missed (%s/%s): %s",
                                      verpasst, self.PROBE_MISSES, still)
                            if verpasst >= self.PROBE_MISSES:
                                raise ConnectionError(
                                    f"keine Antwort mehr ({verpasst} Versuche)") from still
                        else:
                            self._antwortet = True
                            verpasst = 0
                            self._verbindung(True)
                    await leuchte.set_params(brightness=0)
            except Exception as fehler:  # noqa: BLE001 - a lamp switched off is normal
                self._verbindung(False)
                self.note = f"Godox-Leuchte nicht erreichbar: {fehler}"
                log.warning("Godox light unreachable (%s), retrying", fehler)
                self._ready.set()         # do not hold up the start any longer
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.RETRY_S)
                except asyncio.TimeoutError:
                    pass
            finally:
                if self._stop.is_set():
                    self._verbindung(False)


def create_light(config, gpio=None) -> LightBase:
    """Build the kind of light named in the configuration."""
    cfg = config.section("light")
    kind = str(cfg.get("kind", "pwm") or "pwm").strip().lower()
    if kind not in KINDS:
        log.warning("Unknown light kind %r, using pwm", kind)
        kind = "pwm"
    if kind == "dmx":
        light = DmxLight(config)
    elif kind == "godox":
        light = GodoxLight(config)
    elif kind == "none":
        light = NoLight(config)
    else:
        light = PwmLight(config, gpio)
    try:
        light.start()
    except Exception as fehler:  # noqa: BLE001 - better without light than not at all
        log.warning("Light %s did not start (%s)", kind, fehler)
        light.note = light.note or f"Licht {kind} liess sich nicht starten: {fehler}"
        light.dimmable = False
    log.info("Light: %s%s", kind, "" if light.dimmable else " (nicht dimmbar)")
    return light


def describe(light: LightBase) -> dict[str, Any]:
    """What the interface needs to know about the lamp."""
    return {"kind": light.kind, "dimmable": bool(light.dimmable),
            "note": light.note, "value": light.value, **connection(light)}


def connection(light: LightBase) -> dict[str, Any]:
    """The lamp's sign of life.

    "monitored" says whether the answer is worth anything at all: the box
    cannot interrogate a lamp on a wire, so that one always counts as
    present. Only a radio link knows of itself whether it is still up.
    """
    return {"monitored": bool(getattr(light, "monitored", False)),
            "connected": bool(getattr(light, "connected", True)),
            "last_ok": float(getattr(light, "last_ok", 0.0) or 0.0),
            "since": float(getattr(light, "since", 0.0) or 0.0)}
