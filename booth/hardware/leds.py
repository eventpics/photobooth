"""Addressable LED strip (WS2812B / NeoPixel) driven over SPI.

Why SPI and not the usual DMA library: rpi_ws281x needs root, collides with
the onboard audio and does not work on the Pi 5 at all. Pushing the bit
pattern out of the SPI MOSI pin needs no root, works on Pi 4 and Pi 5 and
costs nothing but a lookup table.

Each WS2812B data bit becomes three SPI bits at 2.4 MHz: 0b100 is a zero
(417 ns high, spec wants ~400 ns) and 0b110 is a one (833 ns high, spec wants
~800 ns). A run of zero bytes at the end holds the line low as the reset.

This is meant for status and countdown light. It is deliberately NOT the main
photo light: RGB pixels mix white out of three narrow spectral peaks, which
renders skin badly, and their internal PWM beats against short exposures.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# One data byte expands to three SPI bytes.
_LUT: list[bytes] = []
for _value in range(256):
    _bits = 0
    for _i in range(7, -1, -1):
        _bits = (_bits << 3) | (0b110 if (_value >> _i) & 1 else 0b100)
    _LUT.append(_bits.to_bytes(3, "big"))

_RESET_BYTES = b"\x00" * 100  # comfortably above the 50 us the datasheet wants


class LedStripBase:
    """Common interface for the real and the mock strip."""

    backend = "base"

    def __init__(self, config) -> None:
        self.config = config
        self.lock = threading.RLock()
        self.pixels: list[tuple[int, int, int]] = []
        self.last_error: str | None = None
        self._animation: threading.Thread | None = None
        self._cancel = threading.Event()
        count = int(self.section().get("count", 12))
        self.pixels = [(0, 0, 0)] * count

    def section(self) -> dict[str, Any]:
        return self.config.section("leds")

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        self.off()

    def _write(self) -> None:
        raise NotImplementedError

    # -- drawing -----------------------------------------------------------
    def set_all(self, red: int, green: int, blue: int) -> None:
        self._stop_animation()
        with self.lock:
            self.pixels = [(red, green, blue)] * len(self.pixels)
            self._write()

    def set_pixel(self, index: int, red: int, green: int, blue: int) -> None:
        self._stop_animation()
        with self.lock:
            if not 0 <= index < len(self.pixels):
                raise IndexError(f"Pixel {index} liegt außerhalb von 0..{len(self.pixels) - 1}")
            self.pixels[index] = (red, green, blue)
            self._write()

    def off(self) -> None:
        self.set_all(0, 0, 0)

    # -- animations --------------------------------------------------------
    def _stop_animation(self) -> None:
        self._cancel.set()
        thread = self._animation
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._animation = None
        self._cancel.clear()

    def countdown(self, seconds: int = 3, red: int = 255, green: int = 120, blue: int = 0) -> dict[str, Any]:
        """Ring empties over `seconds`, then one white flash. Runs in the background."""
        self._stop_animation()
        count = len(self.pixels)

        def run() -> None:
            steps = max(count, 1)
            for step in range(steps, 0, -1):
                if self._cancel.is_set():
                    return
                with self.lock:
                    self.pixels = [(red, green, blue)] * step + [(0, 0, 0)] * (count - step)
                    self._write()
                if self._cancel.wait(seconds / steps):
                    return
            with self.lock:
                self.pixels = [(255, 255, 255)] * count
                self._write()
            if self._cancel.wait(0.25):
                return
            with self.lock:
                self.pixels = [(0, 0, 0)] * count
                self._write()

        self._animation = threading.Thread(target=run, name="led-countdown", daemon=True)
        self._animation.start()
        return {"seconds": seconds, "pixels": count}

    def chase(self, cycles: int = 2) -> dict[str, Any]:
        """One dot runs around the strip - the quickest way to see wiring order."""
        self._stop_animation()
        count = len(self.pixels)

        def run() -> None:
            for _ in range(cycles):
                for index in range(count):
                    if self._cancel.is_set():
                        return
                    with self.lock:
                        self.pixels = [(0, 0, 0)] * count
                        self.pixels[index] = (255, 255, 255)
                        self._write()
                    if self._cancel.wait(0.06):
                        return
            with self.lock:
                self.pixels = [(0, 0, 0)] * count
                self._write()

        self._animation = threading.Thread(target=run, name="led-chase", daemon=True)
        self._animation.start()
        return {"cycles": cycles, "pixels": count}

    def set_count(self, count: int) -> None:
        with self.lock:
            count = max(1, min(600, int(count)))
            self.section()["count"] = count
            self.pixels = [(0, 0, 0)] * count
            self._write()

    def status(self) -> dict[str, Any]:
        cfg = self.section()
        return {
            "backend": self.backend,
            "count": len(self.pixels),
            "brightness": cfg.get("brightness", 0.3),
            "spi": f"/dev/spidev{cfg.get('spi_bus', 0)}.{cfg.get('spi_device', 0)}",
            "data_pin": "GPIO 10 (Pin 19, SPI MOSI)",
            "on": any(p != (0, 0, 0) for p in self.pixels),
            "last_error": self.last_error,
        }

    def _encoded(self) -> bytes:
        """Scale by brightness and expand to the SPI bit pattern. Order is GRB."""
        brightness = float(self.section().get("brightness", 0.3))
        brightness = max(0.0, min(1.0, brightness))
        out = bytearray()
        for red, green, blue in self.pixels:
            for value in (green, red, blue):
                out += _LUT[max(0, min(255, int(value * brightness)))]
        return bytes(out) + _RESET_BYTES


class SpiLedStrip(LedStripBase):
    backend = "spidev"

    def __init__(self, config) -> None:
        super().__init__(config)
        self._spi = None

    def start(self) -> None:
        import spidev  # noqa: PLC0415 - Pi only import

        cfg = self.section()
        device = Path(f"/dev/spidev{int(cfg.get('spi_bus', 0))}.{int(cfg.get('spi_device', 0))}")
        if not device.exists():
            raise RuntimeError(
                f"{device} fehlt - SPI ist nicht aktiviert. "
                "Einschalten mit: sudo raspi-config nonint do_spi 0 && sudo reboot"
            )
        self._spi = spidev.SpiDev()
        self._spi.open(int(cfg.get("spi_bus", 0)), int(cfg.get("spi_device", 0)))
        self._spi.max_speed_hz = int(cfg.get("spi_hz", 2_400_000))
        self._spi.mode = 0
        self._write()
        log.info("LED strip ready on SPI, %s pixels", len(self.pixels))

    def stop(self) -> None:
        try:
            self.off()
        finally:
            if self._spi is not None:
                self._spi.close()
                self._spi = None

    def _write(self) -> None:
        if self._spi is None:
            return
        try:
            self._spi.writebytes2(self._encoded())
            self.last_error = None
        except Exception as exc:  # noqa: BLE001 - surface to the UI
            self.last_error = str(exc)
            log.exception("Writing to the LED strip failed")


class MockLedStrip(LedStripBase):
    backend = "mock"

    def start(self) -> None:
        log.info("Mock LED strip started (%s pixels)", len(self.pixels))

    def _write(self) -> None:
        pass


def create_leds(config, use_mock: bool) -> LedStripBase:
    return MockLedStrip(config) if use_mock else SpiLedStrip(config)
