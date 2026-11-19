"""GPIO interface: digital outputs, PWM light dimming and the shutter input.

Uses gpiozero, which talks to lgpio on the Pi 5. RPi.GPIO is deliberately not
used here because it does not work on the Pi 5.

A note that matters for the real booth software: PWM dimmed light and short
camera exposures beat against each other and produce uneven brightness. The
flash sequence below therefore drives the light to a solid 100 percent duty
for the moment of the capture instead of dimming it.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class HardwarePwm:
    """The processor's own PWM unit instead of one generated in software.

    lgpio produces its PWM signal on a thread of its own. That is fine while
    the box is idle; under load the edges slip. Measured on a Pi 4 with the
    light at 5 per cent: idle, brightness wandered by 1.8 per cent; with four
    cores loaded it jumped up by as much as 20 per cent every few seconds.
    That is what you see as the lamp flickering.

    The PWM unit in the chip does not have that problem: it keeps running with
    no help from the CPU, however busy that is. It does need the right overlay
    loaded, or there is no /sys/class/pwm at all:

        dtoverlay=pwm,pin=18,func=2

    The interface is deliberately the same as gpiozero's PWMOutputDevice -
    value, frequency, close - so the rest of the module need not know which of
    the two is currently working.
    """

    BASE = Path("/sys/class/pwm")

    #: Which channel belongs to which GPIO. The overlay handles no more pins.
    CHANNELS = {12: 0, 18: 0, 13: 1, 19: 1}

    #: Which alternate function hangs the pin off the PWM block. The Pi 4 and
    #: the Pi 5 number these differently, so they are tried in turn.
    ALT = {12: ("a0", "a3"), 13: ("a0", "a3"), 18: ("a5", "a3"), 19: ("a5", "a3")}

    def __init__(self, pin: int, frequency: float, initial_value: float = 0.0) -> None:
        self.channel = self.CHANNELS[int(pin)]
        self.chip = self._find_chip(self.channel)
        self.path = self.chip / f"pwm{self.channel}"
        if not self.path.exists():
            (self.chip / "export").write_text(str(self.channel))
        # After the export the files belong to root at first. A udev rule
        # hands them to the gpio group, and that takes a moment. Waiting for
        # readability is not enough - reading is allowed straight away,
        # writing is not.
        enable = self.path / "enable"
        for _ in range(100):
            if enable.exists() and os.access(enable, os.W_OK):
                break
            time.sleep(0.03)
        else:
            raise PermissionError(f"{enable} wurde nicht beschreibbar")
        self._route(int(pin))
        self._frequency = 0.0
        self._value = 0.0
        self._write("enable", 0)
        self.frequency = frequency
        self.value = initial_value
        self._write("enable", 1)

    def _route(self, pin: int) -> None:
        """Hang the pin back onto the PWM block.

        The overlay does this at boot. But it only takes something else
        claiming the pin as an ordinary output once - this class's own
        software fallback, for example - and afterwards the PWM block keeps
        running while its signal arrives nowhere. Seen exactly like that on
        the Pi: registers set cleanly, lamp dark.
        """
        if not shutil.which("pinctrl"):
            return                      # then the overlay will have to do
        for alt in self.ALT.get(pin, ()):
            subprocess.run(["pinctrl", "set", str(pin), alt],
                           capture_output=True, timeout=5)
            gelesen = subprocess.run(["pinctrl", "get", str(pin)], capture_output=True,
                                     text=True, timeout=5).stdout.upper()
            if "PWM" in gelesen:
                return
        raise OSError(f"GPIO {pin} laesst sich nicht auf die PWM-Funktion legen")

    @classmethod
    def _find_chip(cls, channel: int) -> Path:
        """The Pi 4 reports pwmchip0, the Pi 5 a different one - so look."""
        for chip in sorted(cls.BASE.glob("pwmchip*")):
            try:
                if int((chip / "npwm").read_text().strip()) > channel:
                    return chip
            except OSError:
                continue
        raise FileNotFoundError("keine PWM-Einheit gefunden (fehlt der Overlay?)")

    def _write(self, name: str, value: Any) -> None:
        (self.path / name).write_text(str(int(value)))

    # -- the same names gpiozero uses ------------------------------------------
    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, duty: float) -> None:
        duty = max(0.0, min(1.0, float(duty)))
        self._write("duty_cycle", round(self._period_ns() * duty))
        self._value = duty

    @property
    def frequency(self) -> float:
        return self._frequency

    @frequency.setter
    def frequency(self, hz: float) -> None:
        hz = max(1.0, float(hz))
        # Duty cycle to zero first, or the driver rejects a new period that
        # would be shorter than the duty cycle currently set.
        self._write("duty_cycle", 0)
        self._write("period", round(1_000_000_000 / hz))
        self._frequency = hz
        self.value = self._value

    def _period_ns(self) -> int:
        return round(1_000_000_000 / self._frequency) if self._frequency else 0

    def close(self) -> None:
        try:
            self._write("duty_cycle", 0)
            self._write("enable", 0)
            (self.chip / "unexport").write_text(str(self.channel))
        except OSError:
            log.debug("Could not release the hardware PWM", exc_info=True)


class GpioBase:
    """Common interface shared by the real and the mock GPIO controller."""

    backend = "base"

    def __init__(self, config) -> None:
        self.config = config
        self.lock = threading.RLock()
        self.outputs: dict[int, bool] = {}
        self.light_duty = 0.0
        self.press_count = 0
        self.last_press_at: float | None = None
        self.last_error: str | None = None
        self._press_listeners: list[Any] = []

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    # -- outputs -----------------------------------------------------------
    def set_output(self, pin: int, value: bool) -> None:
        raise NotImplementedError

    def get_output(self, pin: int) -> bool:
        return bool(self.outputs.get(int(pin), False))

    # -- light -------------------------------------------------------------
    def set_light(self, duty: float) -> None:
        raise NotImplementedError

    def set_light_frequency(self, hz: float) -> None:
        raise NotImplementedError

    def flash_sequence(self, ramp_ms: int | None = None, hold_ms: int = 400) -> dict[str, Any]:
        """Idle level -> full power -> hold -> back to idle.

        This is the sequence the real booth will run around a capture: bring
        the light up shortly before the shutter so guests are not blinded all
        evening, then drop back to a soft modelling light.
        """
        gpio = self.config.section("gpio")
        ramp_ms = int(gpio.get("light_ramp_ms", 200)) if ramp_ms is None else int(ramp_ms)
        idle = float(gpio.get("light_idle_duty", 0.15))
        full = float(gpio.get("light_capture_duty", 1.0))

        started = time.monotonic()
        steps = max(1, ramp_ms // 20)
        for step in range(1, steps + 1):
            self.set_light(idle + (full - idle) * (step / steps))
            time.sleep(ramp_ms / 1000.0 / steps)
        time.sleep(hold_ms / 1000.0)
        self.set_light(idle)
        return {
            "ramp_ms": ramp_ms,
            "hold_ms": hold_ms,
            "idle_duty": idle,
            "full_duty": full,
            "total_ms": round((time.monotonic() - started) * 1000),
        }

    # -- input -------------------------------------------------------------
    def read_shutter(self) -> bool:
        raise NotImplementedError

    def on_press(self, callback) -> None:
        self._press_listeners.append(callback)

    def _fire_press(self) -> None:
        with self.lock:
            self.press_count += 1
            self.last_press_at = time.time()
        log.info("Shutter button pressed (count=%s)", self.press_count)
        for callback in list(self._press_listeners):
            try:
                callback()
            except Exception:  # noqa: BLE001 - a listener must not kill GPIO
                log.exception("Press listener failed")

    # -- status ------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        gpio = self.config.section("gpio")
        return {
            "backend": self.backend,
            "shutter_pin": gpio.get("shutter_pin"),
            "shutter_pressed": self.read_shutter(),
            "press_count": self.press_count,
            "last_press_at": self.last_press_at,
            "light_pin": gpio.get("light_pin"),
            "light_duty": round(self.light_duty, 3),
            "light_frequency": gpio.get("light_pwm_frequency"),
            "outputs": {str(pin): value for pin, value in sorted(self.outputs.items())},
            "last_error": self.last_error,
        }


class PiGpio(GpioBase):
    """gpiozero backed implementation."""

    backend = "gpiozero"

    def __init__(self, config) -> None:
        super().__init__(config)
        self._devices: dict[int, Any] = {}
        self._light = None
        self._button = None

    def start(self) -> None:
        from gpiozero import Button, DigitalOutputDevice, PWMOutputDevice  # noqa: PLC0415

        gpio = self.config.section("gpio")

        light_pin = int(gpio.get("light_pin", 18))
        light_hz = int(gpio.get("light_pwm_frequency", 2000))
        self._light = None
        try:
            self._light = HardwarePwm(light_pin, light_hz)
            log.info("Light on the hardware PWM (GPIO %s, %s Hz)", light_pin, light_hz)
        except (KeyError, OSError, ValueError) as fehler:
            # No overlay, no suitable pin - software it is, then. The box
            # works; the light just flickers occasionally under load.
            log.warning("No hardware PWM for GPIO %s (%s), falling back to software",
                        light_pin, fehler)
            self._light = PWMOutputDevice(light_pin, frequency=light_hz, initial_value=0.0)

        self._button = Button(
            int(gpio.get("shutter_pin", 17)),
            pull_up=bool(gpio.get("shutter_pull_up", True)),
            bounce_time=float(gpio.get("shutter_bounce_s", 0.05)),
        )
        self._button.when_pressed = self._fire_press

        pins = [int(gpio.get("button_led_pin", 27))]
        pins += [int(p) for p in gpio.get("extra_output_pins", [])]
        for pin in pins:
            if pin in self._devices:
                continue
            self._devices[pin] = DigitalOutputDevice(pin, initial_value=False)
            self.outputs[pin] = False

        log.info("GPIO ready: light=%s shutter=%s outputs=%s",
                 gpio.get("light_pin"), gpio.get("shutter_pin"), sorted(self._devices))

    def stop(self) -> None:
        for device in self._devices.values():
            device.close()
        self._devices.clear()
        if self._light is not None:
            self._light.close()
            self._light = None
        if self._button is not None:
            self._button.close()
            self._button = None

    def set_output(self, pin: int, value: bool) -> None:
        from gpiozero import DigitalOutputDevice  # noqa: PLC0415

        pin = int(pin)
        with self.lock:
            device = self._devices.get(pin)
            if device is None:
                # Allow testing an arbitrary pin that is not in the config.
                device = DigitalOutputDevice(pin, initial_value=False)
                self._devices[pin] = device
            device.value = bool(value)
            self.outputs[pin] = bool(value)
        log.info("GPIO %s set to %s", pin, value)

    def set_light(self, duty: float) -> None:
        duty = max(0.0, min(1.0, float(duty)))
        with self.lock:
            if self._light is not None:
                self._light.value = duty
            self.light_duty = duty

    def set_light_frequency(self, hz: float) -> None:
        hz = max(1.0, float(hz))
        with self.lock:
            if self._light is not None:
                self._light.frequency = hz
            self.config.section("gpio")["light_pwm_frequency"] = hz

    def read_shutter(self) -> bool:
        return bool(self._button.is_pressed) if self._button is not None else False


class MockGpio(GpioBase):
    """In-memory GPIO so the UI works without hardware."""

    backend = "mock"

    def __init__(self, config) -> None:
        super().__init__(config)
        self._shutter = False

    def start(self) -> None:
        gpio = self.config.section("gpio")
        pins = [int(gpio.get("button_led_pin", 27))]
        pins += [int(p) for p in gpio.get("extra_output_pins", [])]
        for pin in pins:
            self.outputs[pin] = False
        log.info("Mock GPIO started (no hardware detected)")

    def stop(self) -> None:
        self.outputs.clear()

    def set_output(self, pin: int, value: bool) -> None:
        self.outputs[int(pin)] = bool(value)
        log.info("Mock GPIO %s set to %s", pin, value)

    def set_light(self, duty: float) -> None:
        self.light_duty = max(0.0, min(1.0, float(duty)))

    def set_light_frequency(self, hz: float) -> None:
        self.config.section("gpio")["light_pwm_frequency"] = max(1.0, float(hz))

    def read_shutter(self) -> bool:
        return self._shutter

    def simulate_press(self) -> None:
        """Lets the UI exercise the shutter path without a physical button."""
        self._shutter = True
        self._fire_press()
        threading.Timer(0.2, self._release).start()

    def _release(self) -> None:
        self._shutter = False


def create_gpio(config, use_mock: bool) -> GpioBase:
    if use_mock:
        return MockGpio(config)
    return PiGpio(config)
