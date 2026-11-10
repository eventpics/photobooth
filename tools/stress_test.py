"""A stress test like a wedding: the real app, real camera, real uploads.

A driver taps the buttons of the interface the way guests would - sometimes
slowly, sometimes in a rush, with retries, discards and layout changes. Every
series is logged (duration, capture time, memory, temperature, queue). The
layout is restored at the end.

Careful: the pictures really are saved, copied to the USB stick and - if that
is set up - uploaded to the EventPics gallery.

On the Pi, with the booth stopped:

    sudo systemctl stop photobooth
    sudo systemd-run --unit=stress --collect -p User=$USER -p PAMName=login \
         -p TTYPath=/dev/tty1 -p StandardInput=tty-fail \
         -p Environment=XDG_SESSION_TYPE=wayland \
         /usr/bin/cage -- /bin/sh -c "python3 $PWD/tools/stress_test.py > /tmp/stress.out 2>&1"
    tail -f /tmp/stress.jsonl
    sudo systemctl start photobooth

With --quick, only one series runs from each section.
"""
import json
import os
import random
import subprocess
import sys
import time
import traceback
from pathlib import Path

APP_DIR = Path(os.environ.get("APP_DIR", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(APP_DIR))
LOG = Path(os.environ.get("STRESS_LOG", "/tmp/stress.jsonl"))
SHOTS = Path(os.environ.get("STRESS_SHOTS", "/tmp/stress-shots"))
SHOTS.mkdir(exist_ok=True)

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from booth.admin import apply_settings  # noqa: E402
from booth.backend import build_backend  # noqa: E402
from booth.ui.app import heartbeat, _shutdown  # noqa: E402
from booth.ui.window import MainWindow  # noqa: E402

#: (layout, number of series, pace) - pace "gast" is leisurely, "hektik" is a
#: crowd that starts the next series immediately.
PLAN = [
    ("single", 6, "gast"),
    ("grid3_text", 6, "gast"),
    ("grid4", 6, "gast"),
    ("mixed", 18, "hektik"),
    ("grid4", 4, "gast"),
]
#: A plan of your own via the environment, e.g. STRESS_PLAN="grid4:10:hektik,single:5:gast".
if os.environ.get("STRESS_PLAN"):
    PLAN = [(lay, int(n), pace) for lay, n, pace in
            (part.split(":") for part in os.environ["STRESS_PLAN"].split(","))]


def rss_mb() -> float:
    if not Path("/proc/self/status").exists():
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1048576, 1)
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return round(int(line.split()[1]) / 1024, 1)
    return 0.0


def cma_free_mb() -> int | None:
    """Free memory for camera and graphics. When it runs short, switching to
    full resolution takes longer, because the kernel has to make room first."""
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("CmaFree:"):
                return int(line.split()[1]) // 1024
    except OSError:
        pass
    return None


def throttled() -> str:
    try:
        return subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True,
                              timeout=3).stdout.strip().split("=")[-1]
    except Exception:  # noqa: BLE001
        return "?"


def write(entry: dict) -> None:
    entry["t"] = time.strftime("%H:%M:%S")
    with LOG.open("a") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps(entry, ensure_ascii=False), flush=True)


class Driver:
    def __init__(self, app, window, backend, quick: bool) -> None:
        self.app, self.w, self.b = app, window, backend
        self.g = window.guest
        self.plan = [(lay, 1 if quick else n, pace) for lay, n, pace in PLAN]
        self.phase = 0
        self.done_in_phase = 0
        self.series = 0
        self.wait_until = 0.0
        self.last_state = None
        self.series_start = 0.0
        self.redos = 0
        self.captures: list[int] = []
        self.original_layout = (backend.config.section("booth").get("enabled_layouts") or ["grid3_text"])[0]
        self.errors = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.step)
        # How long the interface goes without a turn each time. picamera2
        # needs that tick to release camera frames - if it stalls, so does the
        # shot.
        self.lag_last = time.monotonic()
        self.lags: list[tuple[float, float]] = []
        self.lag_timer = QTimer()
        self.lag_timer.timeout.connect(self._lag)
        self.lag_timer.start(20)
        self.windows: list[tuple[float, float]] = []
        camera = backend.camera
        original = camera.capture_still

        def timed_capture():
            start = time.monotonic()
            try:
                return original()
            finally:
                self.windows.append((start, time.monotonic()))

        camera.capture_still = timed_capture
        self.stuck_since = time.monotonic()
        self._set_layout(self.plan[0][0])
        self.timer.start(200)

    def _lag(self) -> None:
        now = time.monotonic()
        gap = now - self.lag_last
        self.lag_last = now
        if gap > 0.12:
            self.lags.append((now - gap, now))
            self.lags = self.lags[-400:]

    def ui_block_ms(self, start: float, end: float) -> int:
        """Longest UI stall that overlaps with [start, end]."""
        worst = 0.0
        for a, b in self.lags:
            if b >= start and a <= end:
                worst = max(worst, b - a)
        return round(worst * 1000)

    # -- Hilfen ------------------------------------------------------------------------
    def pace(self) -> str:
        return self.plan[min(self.phase, len(self.plan) - 1)][2]

    def pause(self, calm: tuple[float, float], rush: tuple[float, float]) -> None:
        lo, hi = rush if self.pace() == "hektik" else calm
        self.wait_until = time.monotonic() + random.uniform(lo, hi)

    def _set_layout(self, layout: str) -> None:
        if layout == "mixed":
            layout = random.choice(["single", "single_caption", "grid3_text", "grid4"])
        apply_settings(self.b.config, self.b.camera, {"active_layout": layout})
        self.current_layout = layout

    def shot(self, name: str) -> None:
        try:
            subprocess.run(["grim", "-s", "0.5", str(SHOTS / f"{name}.png")], timeout=10,
                           capture_output=True)
        except (OSError, subprocess.TimeoutExpired):
            pass

    # -- Takt -------------------------------------------------------------------------
    def step(self) -> None:
        try:
            self._step()
        except Exception:  # noqa: BLE001
            self.errors += 1
            write({"event": "driver-error", "trace": traceback.format_exc()[-800:]})

    def _step(self) -> None:
        g = self.g
        state = g.state
        now = time.monotonic()
        if state != self.last_state:
            self.last_state = state
            self.stuck_since = now
            if state == "failed":
                write({"event": "FAILED", "error": g.view.get("error"), "series": self.series})
        # Nichts darf ewig in einem Zustand haengen, in dem Gaeste nichts tun koennen.
        if state in ("countdown", "capturing", "composing") and now - self.stuck_since > 40:
            write({"event": "STUCK", "state": state, "seconds": round(now - self.stuck_since)})
            self.shot(f"stuck-{self.series}-{state}")
            self.stuck_since = now
        if now < self.wait_until:
            return

        if state == "idle":
            if self.phase >= len(self.plan):
                return self.finish()
            layout, _, _ = self.plan[self.phase]
            if layout == "mixed" or self.current_layout != layout:
                self._set_layout(layout)
            self.series += 1
            self.series_start = now
            self.redos = 0
            self.captures = []
            g.start_btn.click()
            self.pause((0.5, 1), (0.2, 0.5))
        elif state == "countdown":
            # Kurz vor dem Ausloesen messen, einmal je Aufnahme.
            key = (self.series, len(self.b.session.shot_paths))
            if getattr(self, "cma_key", None) != key:
                self.cma_key = key
                self.cma_before = getattr(self, "cma_before", []) + [cma_free_mb()]
        elif state == "await":
            info = self.b.camera.last_capture or {}
            if info.get("duration_ms") and (not self.captures or self.captures[-1] != info.get("file")):
                self.captures.append(info.get("file"))
                self.capture_ms = getattr(self, "capture_ms", []) + [info["duration_ms"]]
                self.capture_parts = getattr(self, "capture_parts", []) + [[info.get("camera_ms"), info.get("save_ms")]]
            if g.redo_btn.isVisible() and random.random() < 0.12 and self.redos < 2:
                self.redos += 1
                g.redo_btn.click()
            else:
                g.start_btn.click()
            self.pause((1.5, 5), (0.2, 1))
        elif state == "review":
            info = self.b.camera.last_capture or {}
            if info.get("duration_ms") and (not self.captures or self.captures[-1] != info.get("file")):
                self.captures.append(info.get("file"))
                self.capture_ms = getattr(self, "capture_ms", []) + [info["duration_ms"]]
                self.capture_parts = getattr(self, "capture_parts", []) + [[info.get("camera_ms"), info.get("save_ms")]]
            if self.series % 7 == 3:
                self.shot(f"review-{self.series}-{self.current_layout}")
            keep = random.random() > (0.15 if self.pace() == "gast" else 0.3)
            (g.keep_btn if keep else g.discard_btn).click()
            self.review_choice = "keep" if keep else "discard"
            if not keep:
                self.end_series("discard")
            self.pause((2, 6), (0.3, 1))
        elif state == "done":
            if g.thumbs and random.random() < 0.4:
                visible = [t for t in g.thumbs if t.isVisible()]
                if visible:
                    random.choice(visible).click()
            if self.series % 7 == 3:
                self.shot(f"done-{self.series}-{self.current_layout}")
            g.done_btn.click()
            self.end_series("keep")
            self.pause((2, 8), (0.3, 1.5))
        elif state == "failed":
            g.back_btn.click()
            self.end_series("failed")
            self.pause((2, 3), (1, 2))

    def end_series(self, how: str) -> None:
        cams = getattr(self, "capture_ms", [])
        self.capture_ms = []
        cma = getattr(self, "cma_before", [])
        self.cma_before = []
        parts, self.capture_parts = getattr(self, "capture_parts", []), []
        windows, self.windows = self.windows, []
        capture_windows = [[round((b - a) * 1000), self.ui_block_ms(a, b)] for a, b in windows]
        stats = self.b.journal.stats("eventpics")
        system = self.b.sysmon
        write({"event": "series", "n": self.series, "phase": self.phase,
               "layout": self.current_layout, "pace": self.pace(), "result": how,
               "seconds": round(time.monotonic() - self.series_start, 1), "redos": self.redos,
               "capture_ms": cams, "captures_ui_block": capture_windows, "capture_parts": parts,
               "cma_free_before": cma, "cma_free_now": cma_free_mb(),
               "rss_mb": rss_mb(), "temp": system.temperature(),
               "cpu": system.cpu_percent(), "throttled": throttled(),
               "upload_pending": stats.get("pending"), "upload_failed": stats.get("failed"),
               "upload_done": stats.get("done"), "last_error": stats.get("last_error")})
        self.done_in_phase += 1
        if self.done_in_phase >= self.plan[self.phase][1]:
            self.phase += 1
            self.done_in_phase = 0

    def finish(self) -> None:
        self.timer.stop()
        apply_settings(self.b.config, self.b.camera, {"active_layout": self.original_layout})
        write({"event": "finished", "series": self.series, "driver_errors": self.errors,
               "restored_layout": self.original_layout, "rss_mb": rss_mb()})
        QTimer.singleShot(1000, self.app.quit)


def main() -> int:
    quick = "--quick" in sys.argv
    app = QApplication(sys.argv[:1])
    backend = build_backend(Path(os.environ["STRESS_CONFIG"]) if os.environ.get("STRESS_CONFIG") else None)
    window = MainWindow(backend)
    app.setOverrideCursor(Qt.CursorShape.BlankCursor)
    window.showFullScreen()
    alive = QTimer()
    alive.timeout.connect(heartbeat)
    alive.start(5000)
    write({"event": "start", "quick": quick, "rss_mb": rss_mb(), "throttled": throttled()})
    QTimer.singleShot(8000, lambda: setattr(main, "driver", Driver(app, window, backend, quick)))
    code = app.exec()
    _shutdown(backend)
    return code


if __name__ == "__main__":
    sys.exit(main())
