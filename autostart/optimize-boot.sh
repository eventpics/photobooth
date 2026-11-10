#!/usr/bin/env bash
# Shortens the booth's boot.
#
#   bash optimize-boot.sh         apply
#   bash optimize-boot.sh --undo  put everything back
#
# Measured on a Pi 4 with the Raspberry Pi OS desktop image: the page was up
# after about 53 seconds. The browser accounted for 2 of those, the server for
# 4. The rest went here:
#
#   20 s  initramfs and graphical splash, before the SD card is even mounted.
#         An initramfs is needed for encrypted volumes or for drivers that are
#         not in the kernel. In the Raspberry Pi kernel, SD card, ext4, USB
#         storage and NVMe are all built in.
#    9 s  waiting for the network to be "online". The booth does not need that
#         to start: uploads wait in their queue regardless.
#    4 s  cloud-init. On the very first boot it sets up the user and the Wi-Fi
#         from the Raspberry Pi Imager and does nothing afterwards.
#         Plus NFS, which the box never uses.
#
# Bluetooth used to be on this list too. It now stays on: the box controls a
# Godox lamp over Bluetooth and cannot find it when disabled. Anyone not using
# a radio lamp can put bluetooth.service back below and save just under a
# second at boot.
set -euo pipefail

FW=/boot/firmware
ENDUNG=vor-optimize-boot
DIENSTE=(
    rpcbind.service rpcbind.socket
    nfs-blkmap.service nfs-client.target
    NetworkManager-wait-online.service
    # These only download package lists; without unattended-upgrades they
    # install nothing. On a photo booth they only cost time at boot.
    apt-daily.timer apt-daily-upgrade.timer
)

#: Cannot be disabled, only masked: sysinit.target pulls these in, so
#: "disable" is a no-op for them.
MASKIERT=(plymouth-start.service)

zurueck() {
    echo "== Rueckbau =="
    for dienst in "${MASKIERT[@]}"; do
        sudo systemctl unmask "$dienst" >/dev/null 2>&1 || true
    done
    for datei in config.txt cmdline.txt; do
        if [ -f "$FW/$datei.$ENDUNG" ]; then
            sudo cp "$FW/$datei.$ENDUNG" "$FW/$datei"
            echo "   $datei wiederhergestellt"
        fi
    done
    sudo rm -f /etc/cloud/cloud-init.disabled
    for dienst in "${DIENSTE[@]}"; do
        sudo systemctl enable "$dienst" >/dev/null 2>&1 || true
    done
    echo "   Dienste wieder eingeschaltet. Wirksam nach:  sudo reboot"
    exit 0
}

[ "${1:-}" = "--undo" ] && zurueck

echo "== Sicherung =="
for datei in config.txt cmdline.txt; do
    # Back up on the first run only - a second run would otherwise overwrite
    # the backup with the already modified version.
    if [ ! -f "$FW/$datei.$ENDUNG" ]; then
        sudo cp "$FW/$datei" "$FW/$datei.$ENDUNG"
    fi
    echo "   $FW/$datei.$ENDUNG"
done

echo
echo "== Bootvorgang =="
# Boot without an initramfs - but only if the kernel can read the root
# filesystem itself. Otherwise the box will not boot again afterwards.
KERNEL="$(uname -r)"
EINGEBAUT="/lib/modules/$KERNEL/modules.builtin"
if grep -q '/ext4.ko' "$EINGEBAUT" && grep -q '/mmc_block.ko' "$EINGEBAUT" \
   && ! grep -qv '^\s*\(#\|$\)' /etc/crypttab 2>/dev/null; then
    if grep -q '^auto_initramfs=' "$FW/config.txt"; then
        sudo sed -i 's/^auto_initramfs=.*/auto_initramfs=0/' "$FW/config.txt"
    else
        echo 'auto_initramfs=0' | sudo tee -a "$FW/config.txt" >/dev/null
    fi
    echo "   ohne initramfs"
else
    echo "   initramfs bleibt: der Kernel liest die Wurzel nicht selbst"
fi
# The firmware's rainbow splash and the one second wait in front of it.
for zeile in disable_splash=1 boot_delay=0; do
    schluessel="${zeile%%=*}"
    if grep -q "^$schluessel=" "$FW/config.txt"; then
        sudo sed -i "s/^$schluessel=.*/$zeile/" "$FW/config.txt"
    else
        echo "$zeile" | sudo tee -a "$FW/config.txt" >/dev/null
    fi
done
echo "   ohne Farbbild der Firmware, ohne Wartezeit"
# Graphical boot splash: nobody sees it on the booth anyway, the booth takes
# over the screen.
sudo sed -i -e 's/ splash//g' -e 's/ plymouth\.ignore-serial-consoles//g' "$FW/cmdline.txt"
echo "   ohne grafischen Startbildschirm"

# Quieten the console. What disappears here is the four raspberries in the
# top left, the kernel messages at boot and the service lines at shutdown -
# everything that tells a guest there is a hobbyist computer in the box.
#
# Deliberately not "console=tty3": that would hide a genuine error too, and
# somebody building their first box needs a message at exactly that moment.
# "quiet" leaves errors standing and only clears away the routine. Everything
# can be read back with  journalctl -b  regardless.
#
# The line is split into words and reassembled rather than rewritten in place:
# that way every switch appears exactly once at the end, on a second run too,
# and the file stays the single line the kernel expects. "quiet" alone is not
# enough: it quietens the kernel, not systemd. The "[ OK ] Started ..." lines
# come from systemd itself and need their own switch - which is exactly what
# was still visible on the test box after raspberries and kernel messages had
# gone.
STILL="quiet loglevel=3 logo.nologo vt.global_cursor_default=0 systemd.show_status=0"
rest=""
for wort in $(cat "$FW/cmdline.txt"); do
    case "$wort" in
        quiet|loglevel=*|logo.nologo|vt.global_cursor_default=*|systemd.show_status=*) continue ;;
    esac
    rest="$rest $wort"
done
echo "${rest# } $STILL" | sudo tee "$FW/cmdline.txt" >/dev/null
echo "   Konsole still: ohne Himbeeren, ohne Kernelmeldungen, ohne Cursor"

echo
echo "== Dienste =="
sudo mkdir -p /etc/cloud
sudo touch /etc/cloud/cloud-init.disabled
echo "   cloud-init aus"
for dienst in "${DIENSTE[@]}"; do
    if systemctl cat "$dienst" >/dev/null 2>&1; then
        sudo systemctl disable "$dienst" >/dev/null 2>&1 || true
        echo "   $dienst aus"
    fi
done
# The system's graphical splash was dropped from the cmdline above, but the
# service kept starting and waiting on nothing - 6.5 seconds out of 28 on the
# test box (systemd-analyze blame). The booth brings its own start screen as
# soon as its window is up.
for dienst in "${MASKIERT[@]}"; do
    if systemctl cat "$dienst" >/dev/null 2>&1; then
        sudo systemctl mask "$dienst" >/dev/null 2>&1 || true
        echo "   $dienst maskiert"
    fi
done

echo
echo "Fertig. Wirksam nach dem naechsten Start:  sudo reboot"
echo "Messen danach:                            systemd-analyze"
echo "Alles zurueck:                            bash $0 --undo"
