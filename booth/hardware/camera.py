"""Camera interface: live preview plus full resolution stills.

On a Raspberry Pi this drives picamera2/libcamera; the live picture goes straight
from the camera to the graphics chip through the preview widget of the UI. Everywhere
else a mock camera renders a synthetic test pattern so the UI stays testable.

The manual controls exposed here are the ones that actually matter for a
photo booth: fixed exposure, fixed gain and fixed white balance, so every
photo of an evening looks the same. Auto modes are available for comparison
but should not be used in production.
"""

from __future__ import annotations

import io
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class FrameBuffer:
    """The newest frame of the mock camera, for the preview on a computer."""

    def __init__(self) -> None:
        self.frame: bytes | None = None
        self.frame_count = 0
        self.lock = threading.Lock()

    def write(self, buf: bytes) -> int:
        with self.lock:
            self.frame = bytes(buf)
            self.frame_count += 1
        return len(buf)


class CameraBase:
    """Common interface shared by the real and the mock camera."""

    backend = "base"
    has_autofocus = False

    def __init__(self, config, capture_dir: Path) -> None:
        self.config = config
        self.capture_dir = capture_dir
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.buffer = FrameBuffer()
        self.lock = threading.RLock()
        self.running = False
        self.last_error: str | None = None
        self.last_capture: dict[str, Any] | None = None

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    # -- controls ----------------------------------------------------------
    def apply_controls(self, controls: dict[str, Any]) -> None:
        raise NotImplementedError

    def capture_still(self) -> dict[str, Any]:
        raise NotImplementedError

    def wait_for_writes(self, timeout: float = 30.0) -> None:
        """Warten, bis alle Aufnahmen wirklich auf der Karte stehen."""

    def measure_white_balance(self, timeout: float = 14.0) -> dict[str, Any]:
        raise NotImplementedError

    def measure_exposure(self, timeout: float = 14.0) -> dict[str, Any]:
        raise NotImplementedError

    def set_capture_size(self, width: int, height: int) -> None:
        """Change the still resolution without restarting the camera.

        Useful on boards with little memory: a full resolution still needs a
        large contiguous buffer, and the binned modes need a quarter of it.
        """
        self.config.section("camera")["capture_size"] = [int(width), int(height)]

    def status(self) -> dict[str, Any]:
        cam = self.config.section("camera")
        return {
            "backend": self.backend,
            "running": self.running,
            "frames": self.buffer.frame_count,
            "preview_size": cam.get("preview_size"),
            "preview_sensor_size": cam.get("preview_sensor_size"),
            "capture_size": cam.get("capture_size"),
            "last_error": self.last_error,
            "last_capture": self.last_capture,
            "sensor": cam.get("sensor", "unbekannt"),
            "has_autofocus": self.has_autofocus,
        }

    def _capture_path(self, suffix: str = ".jpg") -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
        return self.capture_dir / f"capture-{stamp}{suffix}"


_MIN_SETTLE_S = 2.0


def _close(a: tuple[float, float], b: tuple[float, float], tolerance: float = 0.02) -> bool:
    return all(abs(x - y) < tolerance * max(x, 1.0) for x, y in zip(a, b))


#: How long a value has to stay put before it counts as found. Two consecutive
#: frames are not enough: while auto exposure or auto white balance walks slowly
#: towards its answer - and in a dim room it walks very slowly - two neighbouring
#: frames always look alike, so the old test declared victory halfway there and
#: stored whatever the algorithm happened to be passing through.
_HOLD_S = 1.5


def _await_stable(read, tolerance: float, timeout: float,
                  hold_s: float = _HOLD_S) -> tuple[Any, bool, int]:
    """Poll `read` until its value stops moving for `hold_s`.

    Returns (value, settled, samples). A False `settled` means the deadline
    passed while the value was still travelling. Such a reading must not be
    kept: it is a snapshot of an algorithm mid-flight, not a measurement.
    """
    started = time.monotonic()
    deadline = started + timeout
    value = first = anchor = None
    stable_since = started
    samples = 0
    moved = False

    while time.monotonic() < deadline:
        current = read()
        samples += 1
        if current is None:
            time.sleep(0.15)
            continue
        value = current
        if first is None:
            first = current
        elif not _close(current, first, tolerance):
            moved = True
        now = time.monotonic()
        if anchor is None or not _close(current, anchor, tolerance):
            anchor = current            # weggewandert: die Haltezeit beginnt neu
            stable_since = now
        elif now - stable_since >= hold_s and (moved or now - started >= _MIN_SETTLE_S):
            return current, True, samples
        time.sleep(0.15)
    return value, False, samples


def lens_position_to_metres(position: float) -> float | None:
    """LensPosition is given in dioptres, i.e. 1 / distance in metres."""
    return None if position <= 0 else round(1.0 / position, 2)


def build_libcamera_controls(settings: dict[str, Any], include_af: bool = False) -> dict[str, Any]:
    """Map our flat settings dict onto libcamera control names.

    include_af is only set for sensors that actually have a focus motor. The
    Camera Module 3 has one, the HQ Camera does not, and sending AfMode to a
    fixed focus sensor raises.
    """
    controls: dict[str, Any] = {}

    if settings.get("ae_enable"):
        controls["AeEnable"] = True
    else:
        controls["AeEnable"] = False
        controls["ExposureTime"] = int(settings.get("exposure_time_us", 8000))
        controls["AnalogueGain"] = float(settings.get("analogue_gain", 1.0))

    if settings.get("awb_enable"):
        controls["AwbEnable"] = True
    else:
        controls["AwbEnable"] = False
        controls["ColourGains"] = (
            float(settings.get("colour_gain_red", 1.8)),
            float(settings.get("colour_gain_blue", 1.6)),
        )

    for key, name in (
        ("brightness", "Brightness"),
        ("contrast", "Contrast"),
        ("saturation", "Saturation"),
        ("sharpness", "Sharpness"),
    ):
        if key in settings:
            controls[name] = float(settings[key])

    if include_af:
        af_mode = int(settings.get("af_mode", 0))
        controls["AfMode"] = af_mode
        if af_mode == 0:
            # Manual focus is what a booth wants: guests always stand at the
            # same distance, and a hunting autofocus in dim light misses.
            controls["LensPosition"] = float(settings.get("lens_position", 0.5))

    return controls


class PiCamera(CameraBase):
    """picamera2 backed implementation."""

    backend = "picamera2"

    def __init__(self, config, capture_dir: Path) -> None:
        super().__init__(config, capture_dir)
        self.picam2 = None
        self._video_config = None
        self._still_config = None
        self._writes: list[threading.Thread] = []
        self._write_errors: list[str] = []

    def start(self) -> None:
        """Start the camera once the preview widget is attached to it.

        picamera2 then delivers frames to that widget. Start the camera first
        and picamera2 creates its own empty preview instead, and the widget in
        the interface never gets a frame.
        """
        with self.lock:
            if self.picam2 is None:
                raise RuntimeError("Kamera ist nicht vorbereitet")
            self.picam2.start()
            self.running = True
        self.apply_controls(self.config.section("camera").get("controls", {}))
        log.info("picamera2 started")

    def prepare(self) -> None:
        """Open and configure the camera, but start nothing yet."""
        from libcamera import Transform  # noqa: PLC0415 - Pi only import
        from picamera2 import Picamera2  # noqa: PLC0415

        cam = self.config.section("camera")
        transform = Transform(
            hflip=bool(cam.get("hflip", False)),
            vflip=bool(cam.get("vflip", False)),
        )

        with self.lock:
            self.picam2 = Picamera2()
            # The paper is 3:2, the sensor is 16:9 and has no 3:2 mode - every
            # mode of the IMX708 is 4608x2592 or a binned version of it. So the
            # shape has to come from using less of the sensor, and it has to
            # happen here rather than later: cropping at print time would show
            # guests a wider picture than they get, and cut people off at the
            # edges without warning. ScalerCrop applies to preview and still
            # alike, so the screen shows exactly what the printer receives.
            crop = self._frame_crop(float(cam.get("frame_aspect", 1.5)))
            # The sensor mode matters here, not just the output size: the small
            # IMX708 modes read only the centre of the sensor (1536x864 uses a
            # 3072x1728 crop), so a preview left to pick its own mode shows a
            # tighter field of view than the still - guests frame themselves
            # against a picture that is not the one being taken. Pinning the raw
            # size to a full-sensor mode makes preview and capture agree.
            preview_size = tuple(cam.get("preview_size", [1440, 960]))
            sensor_size = tuple(cam.get("preview_sensor_size", [2304, 1296]))
            base = {
                "main": {"size": preview_size},
                "controls": {"FrameRate": float(cam.get("preview_fps", 30)),
                             "ScalerCrop": crop},
                "transform": transform,
            }
            try:
                self._video_config = self.picam2.create_video_configuration(
                    raw={"size": sensor_size}, **base)
            except Exception as exc:  # noqa: BLE001 - fall back to the default mode
                log.warning("Sensor mode %s unavailable (%s), using default", sensor_size, exc)
                self._video_config = self.picam2.create_video_configuration(**base)
            self._still_config = self.picam2.create_still_configuration(
                main={"size": tuple(cam.get("capture_size", [1944, 1296]))},
                controls={"ScalerCrop": crop},
                transform=transform,
            )
            self.picam2.configure(self._video_config)

    def _frame_crop(self, aspect: float) -> tuple[int, int, int, int]:
        """The part of the sensor that has the shape of the paper.

        Returned in full sensor coordinates, centred. Going from 16:9 to 3:2
        costs about a sixth of the width - that width was never printed anyway,
        it was only shown.
        """
        array = self.picam2.camera_properties.get("PixelArraySize") or (4608, 2592)
        width, height = int(array[0]), int(array[1])
        if width / height > aspect:
            keep_w, keep_h = int(round(height * aspect)), height
        else:
            keep_w, keep_h = width, int(round(width / aspect))
        crop = ((width - keep_w) // 2, (height - keep_h) // 2, keep_w, keep_h)
        log.info("Sensor %dx%d -> %s for %.3f:1", width, height, crop, aspect)
        return crop

    def stop(self) -> None:
        with self.lock:
            self.running = False
            if self.picam2 is not None:
                try:
                    self.picam2.stop()
                except Exception:  # noqa: BLE001 - shutdown must not raise
                    log.exception("Stopping the camera failed")
                self.picam2.close()
                self.picam2 = None

    @property
    def has_autofocus(self) -> bool:
        if self.picam2 is None:
            return False
        try:
            return "AfMode" in self.picam2.camera_controls
        except Exception:  # noqa: BLE001 - never let probing break the UI
            return False

    def apply_controls(self, settings: dict[str, Any]) -> None:
        controls = build_libcamera_controls(settings, include_af=self.has_autofocus)
        with self.lock:
            if self.picam2 is None:
                return
            try:
                self.picam2.set_controls(controls)
                self.last_error = None
            except Exception as exc:  # noqa: BLE001 - surface to the UI
                self.last_error = f"set_controls: {exc}"
                log.exception("Applying camera controls failed")

    def autofocus(self) -> dict[str, Any]:
        """Run one autofocus cycle and report the position it settled on.

        The intended workflow: put someone at the real standing distance, run
        this once, then copy the value into the manual field and lock it.
        """
        with self.lock:
            if self.picam2 is None:
                raise RuntimeError("Kamera ist nicht gestartet")
            if not self.has_autofocus:
                raise RuntimeError("Diese Kamera hat keinen Fokusmotor (z. B. HQ Camera).")
        self._let_controls_land()
        with self.lock:
            self.picam2.set_controls({"AfMode": 1})
            success = bool(self.picam2.autofocus_cycle())
            metadata = self.picam2.capture_metadata()
        position = float(metadata.get("LensPosition", 0.0))
        controls = self.config.section("camera").setdefault("controls", {})
        controls["af_mode"] = 0
        controls["lens_position"] = round(position, 3)
        self.apply_controls(controls)
        self.config.save()
        return {
            "success": success,
            "lens_position": round(position, 3),
            "distance_m": lens_position_to_metres(position),
        }

    def measure_white_balance(self, timeout: float = 14.0) -> dict[str, Any]:
        """Let the auto white balance settle once, then keep what it found.

        ColourGains only carries red and blue - green is the fixed reference
        at 1.0. Guessed gains that are too low therefore show up as a green
        cast, which is why these values have to be measured under the light
        that will actually be used rather than estimated.
        """
        with self.lock:
            if self.picam2 is None:
                raise RuntimeError("Kamera ist nicht gestartet")
        self._let_controls_land()
        with self.lock:
            self.picam2.set_controls({"AwbEnable": True})

        temperature = None

        def read():
            nonlocal temperature
            metadata = self.picam2.capture_metadata()
            temperature = metadata.get("ColourTemperature", temperature)
            raw = metadata.get("ColourGains")
            return (float(raw[0]), float(raw[1])) if raw else None

        gains, settled, samples = _await_stable(read, 0.02, timeout)

        controls = self.config.section("camera").setdefault("controls", {})
        controls["awb_enable"] = False

        if gains is None:
            self.apply_controls(controls)
            raise RuntimeError("Die Kamera hat keine ColourGains gemeldet")

        if not settled:
            # Half converged is worse than not measured at all: gains caught in
            # flight turn the picture magenta or green. Keep what was set and
            # say so, rather than storing a number nobody can trust.
            self.apply_controls(controls)
            log.warning("White balance did not settle within %.0fs (last %s)", timeout, gains)
            return {
                "colour_gain_red": controls.get("colour_gain_red"),
                "colour_gain_blue": controls.get("colour_gain_blue"),
                "colour_temperature_k": int(temperature) if temperature else None,
                "settled": False,
                "samples": samples,
                "note": ("Der Weißabgleich kam nicht zur Ruhe. Bei sehr wenig Licht "
                         "braucht die Kamera länger - mehr Licht machen und noch "
                         "einmal einmessen. Die bisherigen Werte bleiben erhalten."),
            }

        controls["colour_gain_red"] = round(gains[0], 3)
        controls["colour_gain_blue"] = round(gains[1], 3)
        self.apply_controls(controls)
        # Measured values are meant to be kept - otherwise a restart
        # silently reverts to the defaults that were just replaced.
        self.config.save()

        return {
            "colour_gain_red": round(gains[0], 3),
            "colour_gain_blue": round(gains[1], 3),
            "colour_temperature_k": int(temperature) if temperature else None,
            "settled": True,
            "samples": samples,
        }

    def _let_controls_land(self, frames: int = 4) -> None:
        """Wait a few frames until previously set values really apply.

        picamera2 batches everything set before the next frame into one
        packet. If a fixed white balance from the previous calibration step
        was still in it, that immediately switched off what had just been
        switched on - and the measurement then reported the old values as
        newly measured. Observed exactly like that on the Pi.
        """
        for _ in range(frames):
            try:
                self.picam2.capture_metadata()
            except Exception:  # noqa: BLE001
                return

    @staticmethod
    def _write_jpeg(pixels, path: Path, quality: int) -> None:
        """Write the JPEG under another name first: half a picture must never be left behind."""
        try:
            import simplejpeg  # noqa: PLC0415 - kommt mit picamera2
            data = simplejpeg.encode_jpeg(pixels, quality=quality, colorspace="RGB")
        except ImportError:
            import io as _io  # noqa: PLC0415
            from PIL import Image  # noqa: PLC0415
            buffer = _io.BytesIO()
            Image.fromarray(pixels).save(buffer, format="JPEG", quality=quality)
            data = buffer.getvalue()
        partial = path.with_suffix(".part")
        partial.write_bytes(data)
        partial.replace(path)

    def current_lux(self) -> float | None:
        """The brightness the sensor currently estimates - even at fixed exposure."""
        if self.picam2 is None or not self.running:
            return None
        try:
            lux = self.picam2.capture_metadata().get("Lux")
        except Exception:  # noqa: BLE001 - a readout, nothing more
            return None
        return round(float(lux), 1) if lux else None

    def measure_exposure(self, timeout: float = 14.0) -> dict[str, Any]:
        """Let auto exposure settle once, then keep the values it found.

        Measured in the mode the photograph is taken in, not in the one the
        preview runs in. The two differ: the preview reads the sensor at
        2304x1296 with pixels combined, the still at 3888x2592 without. At
        the same exposure time and the same gain the still therefore comes
        out darker, measured on the booth by between 1.4 and 1.8 times,
        depending on how bright the scene is. Measuring in the preview mode
        produced a correct-looking preview and an underexposed photograph,
        which is exactly the complaint that led here.

        The factor is not constant, so it cannot be corrected afterwards with
        a stored number: the tone curve is not a straight line. Measuring in
        the right mode avoids the question.

        Also reports the estimated illuminance in lux, which answers the
        question this whole build hinges on: is there enough light?
        """
        with self.lock:
            if self.picam2 is None:
                raise RuntimeError("Kamera ist nicht gestartet")
            still, video = self._still_config, self._video_config

        gewechselt = False
        if still is not None:
            try:
                with self.lock:
                    self.picam2.switch_mode(still)
                gewechselt = True
            except Exception as fehler:  # noqa: BLE001 - measuring beats not measuring
                log.warning("Could not switch to the capture mode to measure (%s), "
                            "measuring in the preview mode instead", fehler)

        try:
            return self._belichtung_messen(timeout)
        finally:
            if gewechselt and video is not None:
                try:
                    with self.lock:
                        self.picam2.switch_mode(video)
                except Exception:  # noqa: BLE001
                    log.exception("Could not switch back to the preview mode")

    def _belichtung_messen(self, timeout: float) -> dict[str, Any]:
        """The measurement itself, whatever mode the camera is currently in."""
        self._let_controls_land()
        with self.lock:
            self.picam2.set_controls({"AeEnable": True})

        lux = None

        def read():
            nonlocal lux
            metadata = self.picam2.capture_metadata()
            lux = metadata.get("Lux", lux)
            exposure = metadata.get("ExposureTime")
            gain = metadata.get("AnalogueGain")
            return (float(exposure), float(gain)) if exposure and gain else None

        current, settled, samples = _await_stable(read, 0.03, timeout)

        controls = self.config.section("camera").setdefault("controls", {})
        controls["ae_enable"] = False

        if current is None:
            self.apply_controls(controls)
            raise RuntimeError("Die Kamera hat keine Belichtungswerte gemeldet")

        if not settled:
            self.apply_controls(controls)
            log.warning("Exposure did not settle within %.0fs (last %s)", timeout, current)
            return {
                "exposure_time_us": controls.get("exposure_time_us"),
                "analogue_gain": controls.get("analogue_gain"),
                "lux": round(lux, 1) if lux else None,
                "settled": False,
                "samples": samples,
                "note": ("Die Belichtung kam nicht zur Ruhe. Das passiert bei sehr "
                         "wenig Licht oder wenn sich im Bild etwas bewegt. Die "
                         "bisherigen Werte bleiben erhalten."),
            }

        controls["exposure_time_us"] = int(round(current[0]))
        controls["analogue_gain"] = round(current[1], 2)
        if lux:
            # Remembered so that a later change of light can be noticed.
            controls["calibrated_lux"] = round(float(lux), 1)
        self.apply_controls(controls)
        # Measured values are meant to be kept - otherwise a restart
        # silently reverts to the defaults that were just replaced.
        self.config.save()

        return {
            "exposure_time_us": int(round(current[0])),
            "analogue_gain": round(current[1], 2),
            "lux": round(float(lux), 1) if lux else None,
            "settled": settled,
            "samples": samples,
        }

    def set_capture_size(self, width: int, height: int) -> None:
        from libcamera import Transform  # noqa: PLC0415

        super().set_capture_size(width, height)
        cam = self.config.section("camera")
        with self.lock:
            if self.picam2 is None:
                return
            self._still_config = self.picam2.create_still_configuration(
                main={"size": (int(width), int(height))},
                # Without the crop the capture falls back to 16:9 while the
                # preview shows 3:2 - exactly the difference nobody notices
                # until somebody comes out of the printer cut in half.
                controls={"ScalerCrop": self._frame_crop(
                    float(cam.get("frame_aspect", 1.5)))},
                transform=Transform(
                    hflip=bool(cam.get("hflip", False)),
                    vflip=bool(cam.get("vflip", False)),
                ),
            )
        log.info("Still resolution set to %sx%s", width, height)

    def capture_still(self) -> dict[str, Any]:
        cam = self.config.section("camera")
        path = self._capture_path()
        started = time.monotonic()

        with self.lock:
            if self.picam2 is None:
                raise RuntimeError("Kamera ist nicht gestartet")
            # picamera2 switches to full resolution, grabs a frame and goes
            # back to preview mode. That happens on the interface's thread,
            # because that is where the live image receives camera frames - so
            # this is never called from the interface itself, or the call
            # would be waiting on itself.
            #
            # Only the pixels are copied there. picamera2 used to encode and
            # write the JPEG on that thread too. If the card happened to be
            # busy - with the previous series' sheet, say - the interface
            # stalled with it, and a shot took up to 3.5 seconds in the stress
            # test instead of 0.3.
            try:
                pixels = self.picam2.switch_mode_and_capture_array(self._still_config, "main")
            finally:
                self.apply_controls(cam.get("controls", {}))
        switched = time.monotonic()
        info = {
            "file": path.name,
            "duration_ms": round((switched - started) * 1000),
            "camera_ms": round((switched - started) * 1000),
            "save_ms": None,
            "size": cam.get("capture_size"),
        }
        # Writing happens in the background. With a busy card that took up to
        # two seconds in the stress test - and for that whole time the guests
        # were looking at a "0" on the screen. Anyone who needs the file waits
        # for it with wait_for_writes().
        quality = int(cam.get("jpeg_quality", 90))

        def write() -> None:
            began = time.monotonic()
            try:
                self._write_jpeg(pixels, path, quality)
                info["bytes"] = path.stat().st_size
            except Exception as exc:  # noqa: BLE001
                log.exception("Writing %s failed", path.name)
                self._write_errors.append(f"{path.name}: {exc}")
            info["save_ms"] = round((time.monotonic() - began) * 1000)
            log.info("Still captured: %s", info)

        writer = threading.Thread(target=write, name="jpeg-writer")
        writer.start()
        self._writes = [t for t in self._writes if t.is_alive()] + [writer]
        self.last_capture = info
        return info

    def wait_for_writes(self, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        for writer in list(self._writes):
            writer.join(max(0.0, deadline - time.monotonic()))
        self._writes = [t for t in self._writes if t.is_alive()]
        if self._writes:
            raise RuntimeError("Aufnahme ließ sich nicht rechtzeitig speichern")
        if self._write_errors:
            errors, self._write_errors = self._write_errors, []
            raise RuntimeError("Aufnahme nicht gespeichert: " + "; ".join(errors))


class MockCamera(CameraBase):
    """Synthetic camera so the UI can be exercised without hardware.

    The generated frame reacts to the exposure and gain settings, which makes
    the settings form testable end to end before the real camera arrives.
    """

    backend = "mock"
    has_autofocus = True

    def __init__(self, config, capture_dir: Path) -> None:
        super().__init__(config, capture_dir)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self.running = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="mock-camera", daemon=True)
        self._thread.start()
        log.info("Mock camera started (no hardware detected)")

    def stop(self) -> None:
        self.running = False
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        cam = self.config.section("camera")
        fps = float(cam.get("preview_fps", 20))
        while not self._stop.is_set():
            size = tuple(cam.get("preview_size", [1440, 960]))
            frame = self._render(size, live=True)
            self.buffer.write(frame)
            self._stop.wait(1.0 / max(fps, 1.0))

    def _exposure_factor(self) -> float:
        """Rough stand-in for how bright the sensor image would be."""
        settings = self.config.section("camera").get("controls", {})
        if settings.get("ae_enable"):
            return 1.0
        exposure = float(settings.get("exposure_time_us", 8000))
        gain = float(settings.get("analogue_gain", 1.0))
        # 8000 us at gain 2.0 is treated as a correctly exposed reference.
        return max(0.05, min(4.0, (exposure / 8000.0) * (gain / 2.0)))

    def _render(self, size: tuple[int, int], live: bool) -> bytes:
        from PIL import Image, ImageDraw  # noqa: PLC0415

        width, height = int(size[0]), int(size[1])
        factor = self._exposure_factor()
        settings = self.config.section("camera").get("controls", {})
        r_gain = float(settings.get("colour_gain_red", 1.8))
        b_gain = float(settings.get("colour_gain_blue", 1.6))

        image = Image.new("RGB", (width, height), (20, 20, 24))
        draw = ImageDraw.Draw(image)

        # Colour bars, scaled by the simulated exposure and white balance.
        bars = [
            (255, 255, 255), (255, 255, 0), (0, 255, 255), (0, 255, 0),
            (255, 0, 255), (255, 0, 0), (0, 0, 255), (40, 40, 40),
        ]
        bar_w = width / len(bars)
        for index, (r, g, b) in enumerate(bars):
            r = min(255, int(r * factor * (r_gain / 1.8)))
            g = min(255, int(g * factor))
            b = min(255, int(b * factor * (b_gain / 1.6)))
            draw.rectangle(
                [index * bar_w, 0, (index + 1) * bar_w, height * 0.6],
                fill=(r, g, b),
            )

        # A moving marker so it is obvious the stream is live, not a still.
        if live:
            phase = (time.time() % 3.0) / 3.0
            x = int(phase * (width - 60))
            draw.ellipse([x, height * 0.65, x + 60, height * 0.65 + 60], fill=(255, 140, 0))

        lines = [
            "MOCK-KAMERA - keine Hardware erkannt",
            f"{width}x{height}  Belichtung {settings.get('exposure_time_us')} us  "
            f"Gain {settings.get('analogue_gain')}",
            f"AWB {'auto' if settings.get('awb_enable') else f'fix R{r_gain} B{b_gain}'}",
            f"Fokus {'manuell' if int(settings.get('af_mode', 0)) == 0 else 'auto'} "
            f"LensPosition {settings.get('lens_position')} "
            f"(~{lens_position_to_metres(float(settings.get('lens_position', 0.5)))} m)",
            datetime.now().strftime("%H:%M:%S.%f")[:-3],
        ]
        for index, text in enumerate(lines):
            draw.text((16, height * 0.8 + index * 16), text, fill=(255, 255, 255))

        out = io.BytesIO()
        image.save(out, format="JPEG", quality=int(self.config.section("camera").get("jpeg_quality", 90)))
        return out.getvalue()

    def apply_controls(self, settings: dict[str, Any]) -> None:
        # Nothing to send anywhere; the renderer reads the config directly.
        log.info("Mock camera controls: %s", build_libcamera_controls(settings, include_af=True))
        self.last_error = None

    def autofocus(self) -> dict[str, Any]:
        # Pretend the motor settled on the configured booth distance.
        position = float(self.config.section("camera").get("controls", {}).get("lens_position", 0.5))
        time.sleep(0.6)
        return {
            "success": True,
            "lens_position": round(position, 3),
            "distance_m": lens_position_to_metres(position),
            "note": "Mock: kein echter Fokusmotor",
        }

    def measure_white_balance(self, timeout: float = 14.0) -> dict[str, Any]:
        time.sleep(0.8)
        controls = self.config.section("camera").setdefault("controls", {})
        controls["awb_enable"] = False
        return {
            "colour_gain_red": controls.get("colour_gain_red"),
            "colour_gain_blue": controls.get("colour_gain_blue"),
            "colour_temperature_k": None,
            "settled": True,
            "samples": 0,
            "note": "Mock: kein echter Sensor",
        }

    def measure_exposure(self, timeout: float = 14.0) -> dict[str, Any]:
        time.sleep(0.8)
        controls = self.config.section("camera").setdefault("controls", {})
        controls["ae_enable"] = False
        return {
            "exposure_time_us": controls.get("exposure_time_us"),
            "analogue_gain": controls.get("analogue_gain"),
            "lux": None,
            "settled": True,
            "samples": 0,
            "note": "Mock: kein echter Sensor",
        }

    def capture_still(self) -> dict[str, Any]:
        cam = self.config.section("camera")
        size = tuple(cam.get("capture_size", [4056, 3040]))
        path = self._capture_path()
        started = time.monotonic()
        # Render at a sane size; a 12 MP mock frame is pointless and slow.
        preview = tuple(cam.get("preview_size", [1440, 960]))
        path.write_bytes(self._render(preview, live=False))
        info = {
            "file": path.name,
            "bytes": path.stat().st_size,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "size": list(size),
            "note": "Mock: Datei hat Vorschaugröße, nicht die konfigurierte Aufnahmegröße",
        }
        self.last_capture = info
        return info


def create_camera(config, capture_dir: Path, use_mock: bool) -> CameraBase:
    if use_mock:
        return MockCamera(config, capture_dir)
    return PiCamera(config, capture_dir)
