#!/usr/bin/env bash
# Sets the booth up so that it comes up on its own at power-on: the booth and
# nothing else on screen - no desktop, no task bar.
#
#   bash setup.sh           install
#   bash setup.sh --remove  put everything back, desktop as before
#
# Needs sudo.
set -euo pipefail

ORDNER="$(cd "$(dirname "$0")/.." && pwd)"
BENUTZER="$(id -un)"
UNITS=/etc/systemd/system

#: Services and files from earlier versions, when the interface was still a
#: web page in a browser. They are cleared away during setup, so that two
#: programs do not fight over the screen.
ALTE_DIENSTE=(photobooth-kiosk.service)
ALTE_DATEIEN=(/etc/chromium/policies/managed/photobooth.json /etc/sudoers.d/photobooth)

alte_weg() {
    sudo systemctl disable --now "${ALTE_DIENSTE[@]}" 2>/dev/null || true
    for dienst in "${ALTE_DIENSTE[@]}"; do
        sudo rm -f "$UNITS/$dienst"
    done
    sudo rm -f "${ALTE_DATEIEN[@]}"
}

entfernen() {
    echo "== Rueckbau =="
    bash "$ORDNER/autostart/optimize-boot.sh" --undo | sed 's/^/   /' || true
    sudo systemctl disable --now photobooth-watchdog.service photobooth-touch.service \
                                 photobooth.service 2>/dev/null || true
    sudo rm -f "$UNITS/photobooth.service" "$UNITS/photobooth-touch.service" \
               "$UNITS/photobooth-watchdog.service"
    alte_weg
    sudo rm -f /etc/udev/rules.d/99-photobooth-usb.rules
    sudo rm -f /etc/systemd/journald.conf.d/50-photobooth-journal.conf
    sudo udevadm control --reload-rules 2>/dev/null || true
    sudo systemctl daemon-reload
    sudo systemctl set-default graphical.target
    sudo systemctl enable lightdm.service 2>/dev/null || true
    echo "   Dienste entfernt, Desktop wieder eingeschaltet."
    echo "   Wirksam nach:  sudo reboot"
    exit 0
}

[ "${1:-}" = "--remove" ] && entfernen

echo "== Pakete =="
# cage shows a single program full screen; python3-evdev is needed by the
# touch bridge.
sudo apt-get install -y --no-install-recommends cage python3-evdev >/dev/null
echo "   cage, python3-evdev"

echo
echo "== Hardware-PWM fuer das Licht =="
# Without this overlay lgpio generates the PWM in software. That is fine while
# idle; under load the edges slip and the lamp flickers every few seconds. The
# chip's PWM block does not have that problem.
# Note: GPIO 18 shares the block with the analogue audio output. The box makes
# no sound at all, so that does not matter here.
FW=/boot/firmware
[ -f "$FW/config.txt" ] || FW=/boot
LICHT_PIN=$(sed -n 's/.*"light_pin"[^0-9]*\([0-9]*\).*/\1/p' "$ORDNER/config.json" | head -1)
LICHT_PIN=${LICHT_PIN:-18}
if grep -q "^dtoverlay=pwm,pin=$LICHT_PIN," "$FW/config.txt"; then
    echo "   war schon eingetragen (GPIO $LICHT_PIN)"
elif [ "$LICHT_PIN" = "12" ] || [ "$LICHT_PIN" = "13" ] || \
     [ "$LICHT_PIN" = "18" ] || [ "$LICHT_PIN" = "19" ]; then
    echo "dtoverlay=pwm,pin=$LICHT_PIN,func=2" | sudo tee -a "$FW/config.txt" >/dev/null
    echo "   eingetragen fuer GPIO $LICHT_PIN - wirksam nach dem naechsten Neustart"
else
    echo "   GPIO $LICHT_PIN kann keine Hardware-PWM, es bleibt bei der Software-PWM"
fi

echo
echo "== Herunterfahren vom Bildschirm aus =="
# The box does not run as root, and logind otherwise asks a confirmation for
# powering off that nobody can answer on a touchscreen. So: one narrowly
# scoped permission, exactly one command and nothing else.
printf '%s ALL=(root) NOPASSWD: /usr/sbin/shutdown -h now\n' "$BENUTZER" \
    | sudo tee /etc/sudoers.d/photobooth-poweroff >/dev/null
sudo chmod 440 /etc/sudoers.d/photobooth-poweroff
if sudo visudo -c -f /etc/sudoers.d/photobooth-poweroff >/dev/null 2>&1; then
    echo "   $BENUTZER darf die Box herunterfahren"
else
    sudo rm -f /etc/sudoers.d/photobooth-poweroff
    echo "   Regel war fehlerhaft und wurde wieder entfernt"
fi

echo
echo "== Aeltere Version =="
alte_weg
echo "   Browser-Kiosk entfernt, falls vorhanden"

echo
echo "== USB-Sticks =="
# With no desktop, nobody mounts a stick. The udev rule does it instead -
# otherwise the stick sits there and the box says "nicht angesteckt".
# Owned by root on purpose: a folder under /media owned by the user looks like
# a stick to the stick search itself - the box then reported the SD card's free
# space as space on the stick.
sudo install -d -m 755 -o root -g root "/media/$BENUTZER"
sed -e "s|@DIR@|$ORDNER|g" -e "s|@USER@|$BENUTZER|g" "$ORDNER/autostart/99-photobooth-usb.rules" \
    | sudo tee /etc/udev/rules.d/99-photobooth-usb.rules >/dev/null
sudo udevadm control --reload-rules
echo "   /etc/udev/rules.d/99-photobooth-usb.rules"

echo
echo "== Protokoll =="
# Pi OS forgets the system journal on every reboot. After a crash that would
# lose exactly what explains it.
sudo install -D -m 644 "$ORDNER/autostart/50-photobooth-journal.conf" \
     /etc/systemd/journald.conf.d/50-photobooth-journal.conf
sudo systemctl restart systemd-journald
echo "   dauerhaft, hoechstens 50 MB"

echo
echo "== Dienste =="
for datei in photobooth.service photobooth-touch.service photobooth-watchdog.service; do
    sed -e "s|@DIR@|$ORDNER|g" -e "s|@USER@|$BENUTZER|g" \
        "$ORDNER/autostart/$datei" | sudo tee "$UNITS/$datei" >/dev/null
    echo "   $datei"
done
sudo systemctl daemon-reload
sudo systemctl enable photobooth.service photobooth-touch.service \
                      photobooth-watchdog.service >/dev/null
echo "   alle eingeschaltet"

echo
echo "== Start beschleunigen =="
bash "$ORDNER/autostart/optimize-boot.sh" | sed 's/^/   /'

echo
echo "== Desktop abschalten =="
# Without this the display manager and the booth fight over the same screen -
# and the task bar would be back.
sudo systemctl disable lightdm.service >/dev/null 2>&1 || true
sudo systemctl set-default multi-user.target >/dev/null
echo "   lightdm aus, Startziel multi-user"

echo
echo "== PIN fuer die Einstellungen =="
# No box should go into service with the default 1234 that appears in every
# set of instructions. Forget the PIN later and set-pin.sh sets a new one.
bash "$ORDNER/set-pin.sh" --if-default

echo
echo "Fertig. Nach dem naechsten Einschalten startet die Box von selbst."
echo
echo "   Jetzt starten :  sudo systemctl start photobooth-touch photobooth photobooth-watchdog"
echo "   Nachsehen     :  systemctl status photobooth"
echo "   Protokoll     :  journalctl -t photobooth -f"
echo "   PIN vergessen :  bash set-pin.sh"
echo "   Alles zurueck :  bash autostart/setup.sh --remove"
