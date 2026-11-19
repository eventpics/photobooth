"""Start der nativen Oberflaeche."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

log = logging.getLogger(__name__)

#: Sign of life for the watchdog (autostart/watchdog.sh). In RAM, not on the
#: card: written every five seconds, all evening long.
HEARTBEAT = Path("/dev/shm/photobooth-alive")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EventPics Photobooth")
    parser.add_argument("--config", type=Path, default=None, help="Pfad zur config.json")
    parser.add_argument("--window", action="store_true",
                        help="Im Fenster statt im Vollbild (zum Entwickeln)")
    parser.add_argument("--scale", type=float, default=None,
                        help="Fester Zoomfaktor fuer die Buehne, etwa 0.5 am Laptop")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    if args.scale:
        os.environ["QT_SCALE_FACTOR"] = str(args.scale)

    from PySide6.QtCore import Qt, QTimer  # noqa: PLC0415
    from PySide6.QtWidgets import QApplication  # noqa: PLC0415

    app = QApplication(sys.argv[:1])
    app.setApplicationName("EventPics Photobooth")
    from PySide6.QtGui import QIcon  # noqa: PLC0415
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent.parent / "assets" / "icon.png")))

    if not args.window and not args.scale and "QT_SCALE_FACTOR" not in os.environ:
        factor = _stage_factor(app)
        if abs(factor - 1.0) > 0.005:
            # The stage is a fixed 1920 x 1080. On a different screen the
            # whole interface is scaled evenly. Qt can only take the factor
            # before it starts, so restart once - before the camera, so that
            # nothing gets opened twice.
            log.info("Screen needs a stage factor of %.3f, restarting with it", factor)
            os.environ["QT_SCALE_FACTOR"] = f"{factor:.4f}"
            os.execv(sys.executable, [sys.executable, *sys.argv])

    from booth.backend import build_backend  # noqa: PLC0415

    from .splash import SplashScreen  # noqa: PLC0415
    from .window import MainWindow  # noqa: PLC0415

    heartbeat()
    # The palette before anything is drawn - the splash screen is already
    # painted in it, and a screen that starts cream and turns dark a second
    # later looks like a fault.
    from booth.hardware.config import Config  # noqa: PLC0415

    from . import theme  # noqa: PLC0415

    theme.apply(Config(args.config))

    # Start screen first, camera second. Bringing the camera up takes about
    # ten seconds on a Pi 4, and the console used to sit there for all of it.
    # The mouse pointer goes at the same time - otherwise it sits in the
    # middle of the start screen.
    if not args.window:
        app.setOverrideCursor(Qt.CursorShape.BlankCursor)
    splash = SplashScreen()
    if args.window:
        splash.show()
    else:
        splash.showFullScreen()
    splash.present(app)
    splash.set_note("Kamera und Leuchte werden gestartet …")

    backend = build_backend(args.config)
    for note in backend.notes:
        log.warning(note)

    splash.set_note("Oberfläche wird aufgebaut …")
    window = MainWindow(backend)
    if args.window:
        window.show()
    else:
        window.showFullScreen()
    # Close it only once the window is up. A black screen in between is
    # exactly what the start screen exists to prevent.
    app.processEvents()
    splash.close()
    splash.deleteLater()

    # Shut down cleanly on Ctrl+C and on systemd's SIGTERM. Python only sees
    # signals while it is running itself - the timer makes sure it does.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(250)

    # The sign of life comes from the interface's own tick. If that hangs -
    # because the camera stopped answering, say - it stops, and the watchdog
    # restarts the app. A process that merely "is running" does not count.
    #
    # Not via systemd's own watchdog: the app runs inside cage's login
    # session, and systemd does not attribute notifications from that session
    # to the service - it would have restarted the box every minute.
    alive = QTimer()
    alive.timeout.connect(heartbeat)
    alive.start(5000)

    code = app.exec()
    _shutdown(backend)
    return code


def heartbeat() -> None:
    """Renew the watchdog timestamp (Linux only, where /dev/shm exists)."""
    if not HEARTBEAT.parent.is_dir():
        return
    try:
        HEARTBEAT.write_text(f"{time.time():.0f}\n")
    except OSError:
        log.debug("Heartbeat failed", exc_info=True)


def _stage_factor(app) -> float:
    """How much the stage has to be scaled to fit the screen whole.

    The stage fills the screen. The safe margin is not subtracted here but
    kept by the screens themselves - otherwise the dimmer behind an enlarged
    picture would no longer cover the screen, and there would be a border
    around everything that nobody asked for.
    """
    from booth.ui.theme import STAGE_H, STAGE_W  # noqa: PLC0415

    screen = app.primaryScreen()
    if screen is None:
        log.warning("No screen reported, stage left at 1:1")
        return 1.0
    size = screen.size()
    if size.width() <= 0 or size.height() <= 0:
        log.warning("Screen reports %dx%d, stage left at 1:1",
                    size.width(), size.height())
        return 1.0

    # Always in the log, because a screen that identifies itself wrongly is
    # not visible from the outside: the interface simply comes up at the
    # wrong proportions, with white bands where the stage does not reach.
    # Seen once on the booth after a loose display cable. Without this line
    # there was nothing afterwards to say what the screen had claimed to be.
    verhaeltnis = size.width() / size.height()
    log.info("Screen reports %dx%d (%.2f:1)", size.width(), size.height(),
             verhaeltnis)
    if not 1.2 <= verhaeltnis <= 2.4 or size.width() < 800 or size.height() < 450:
        log.warning("That is not a shape this booth is built for. If the "
                    "picture looks wrong, check the display cable and "
                    "restart.")
    return min(size.width() / STAGE_W, size.height() / STAGE_H)


def _shutdown(backend) -> None:
    """Light off, camera closed. A failure here must not hold up the exit."""
    for step in (lambda: backend.session.cancel(),
                 lambda: backend.light.stop(),
                 lambda: backend.camera.stop(),
                 lambda: backend.gpio.stop(),
                 lambda: backend.leds.stop(),
                 lambda: backend.sysmon.stop()):
        try:
            step()
        except Exception:  # noqa: BLE001
            log.debug("Shutdown step failed", exc_info=True)
