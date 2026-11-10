#!/usr/bin/env bash
# Restarts the booth when its interface hangs.
#
# A crash is easy: the process ends and systemd starts it again by itself. The
# hard case is an app that is still running but doing nothing - because the
# camera stopped answering, say. From the outside that looks like a working
# box.
#
# So the app writes a timestamp to /dev/shm/photobooth-alive every five
# seconds, from the interface's own tick. If it is more than a minute old, the
# interface has hung.
set -u

DIENST=photobooth.service
DATEI=/dev/shm/photobooth-alive
STILLE_S=60
#: After a start the app gets time to bring up camera and interface.
ANLAUF_S=90

while sleep 10; do
    systemctl is-active --quiet "$DIENST" || continue

    seit_us="$(systemctl show "$DIENST" -p ActiveEnterTimestampMonotonic --value)"
    jetzt_s="$(cut -d. -f1 /proc/uptime)"
    [ -n "$seit_us" ] && [ "$seit_us" != 0 ] || continue
    laeuft_s=$(( jetzt_s - seit_us / 1000000 ))
    [ "$laeuft_s" -ge "$ANLAUF_S" ] || continue

    if [ -f "$DATEI" ]; then
        alter_s=$(( $(date +%s) - $(stat -c %Y "$DATEI") ))
    else
        alter_s=$laeuft_s
    fi
    # A timestamp from before this start does not count as a sign of life.
    [ "$alter_s" -gt "$laeuft_s" ] && alter_s=$laeuft_s

    if [ "$alter_s" -gt "$STILLE_S" ]; then
        echo "Kein Lebenszeichen seit $alter_s s - die Fotobox wird neu gestartet"
        systemctl restart "$DIENST"
    fi
done
