#!/usr/bin/env bash
# Installs everything the booth needs on Raspberry Pi OS.
# Safe to run as often as you like.
set -euo pipefail

echo "== Pakete =="
sudo apt update
# Everything from the distribution packages, nothing via pip: picamera2 and the
# Qt bindings are only built correctly for the Pi there. Hence no virtualenv
# either - the booth runs on the system Python.
#
#   picamera2, gpiozero, lgpio, spidev   camera, button, light, LED strip
#   pil                                   composing sheets
#   pyside6 + opengl + qt6-wayland        the interface, live image straight
#                                         onto the GPU
#   cups + gutenprint                     printing, e.g. the Canon Selphy
sudo apt install -y --no-install-recommends \
    python3-picamera2 python3-gpiozero python3-lgpio python3-spidev python3-pil \
    python3-pyside6.qtwidgets python3-pyside6.qtsvg \
    python3-pyside6.qtopengl python3-pyside6.qtopenglwidgets python3-opengl qt6-wayland \
    cups printer-driver-gutenprint

# SPI for the LED strip. Without it there is no /dev/spidev0.0 and the strip
# stays dark, with no error appearing anywhere.
if command -v raspi-config >/dev/null; then
    sudo raspi-config nonint do_spi 0
fi

# Fonts for the captions on the prints and for the interface. They are missing
# on Pi OS Lite, where the choice would collapse to a single face.
sudo apt install -y fonts-urw-base35 fonts-dejavu-core fonts-nunito-sans

# QR decoding: so the EventPics key can be photographed.
sudo apt install -y zbar-tools

# QR encoding: every uploaded picture gets a code with which guests fetch just
# their own picture onto their phone - without opening the whole gallery.
sudo apt install -y qrencode


# Serial port for DMX. Only needed when the lamp hangs off a DMX bus - the
# package is small and gets in nobody's way otherwise.
sudo apt install -y python3-serial

# Bluetooth for Godox lamps. python3-bleak is older than the library asks for -
# tested on the Pi against the actual lamp, and it works.
sudo apt install -y python3-bleak python3-cryptography

# The library for Godox's mesh protocol. Not via pip but as a copy beside the
# software: nothing touched in the system, a pinned revision, auditable at any
# time. MIT licence, authors in the directory.
GODOX_COMMIT=7b31234b2c888868220bef3f3308298ec79f9c6b
if [ ! -d vendor/godox-mesh/.git ]; then
    mkdir -p vendor
    git clone -q https://github.com/hirpusnoctis/ha-godox-mesh vendor/godox-mesh
fi
(cd vendor/godox-mesh && git fetch -q --depth 50 origin && git checkout -q "$GODOX_COMMIT" 2>/dev/null) \
    && echo "   Godox-Bibliothek auf $GODOX_COMMIT" \
    || echo "   Godox-Bibliothek konnte nicht geholt werden (nur noetig fuer Godox-Leuchten)"

# Keep ipp-usb away from Selphy printers. The service grabs every USB printer
# as it is plugged in, looks for IPP and a scanner, finds neither on a Selphy,
# resets it - and occasionally leaves a connection open while doing so.
# Afterwards CUPS cannot find the printer, with no error anywhere. Observed
# exactly like that on the Pi.
if [ -d /usr/share/ipp-usb ]; then
    sudo mkdir -p /etc/ipp-usb/quirks
    sudo tee /etc/ipp-usb/quirks/photobooth.conf >/dev/null <<'QUIRK'
# Selphy photo printers do not speak IPP over USB - printing goes through
# CUPS's USB backend with Gutenprint.
[Canon SELPHY *]
  blacklist = true
QUIRK
    sudo systemctl restart ipp-usb 2>/dev/null || true
    echo "   ipp-usb laesst den Selphy in Ruhe"
fi

echo
echo "== Pruefung =="
python3 - <<'PY'
import importlib, shutil
for name in ("PIL", "gpiozero", "picamera2", "spidev", "PySide6.QtWidgets", "PySide6.QtSvg",
             "PySide6.QtOpenGLWidgets", "OpenGL"):
    try:
        importlib.import_module(name)
        print(f"  ok      {name}")
    except Exception as exc:
        print(f"  FEHLT   {name}: {exc}")
# Helpers the box runs without - just with fewer options.
for werkzeug, wofuer in (("zbarimg",  "QR-Code fuer den EventPics-Schluessel"),
                         ("qrencode", "QR-Code zum Herunterladen der Bilder"),
                         ("lpstat",   "Drucker")):
    if shutil.which(werkzeug):
        print(f"  ok      {werkzeug}")
    else:
        print(f"  fehlt   {werkzeug} - ohne das kein {wofuer}")
PY
echo
echo "Fertig. Damit die Box beim Einschalten von selbst hochkommt:"
echo "   bash autostart/setup.sh"
