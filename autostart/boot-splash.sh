#!/bin/sh
# Put the pre-rendered start screen on the display, using nothing but dd.
#
#   boot-splash.sh boot       # the start screen, with the bar standing still
#   boot-splash.sh shutdown   # "you may pull the plug in a moment"
#
# Why this exists next to boot-splash.py, which can do the same thing: timing.
# Measured on the booth, the Python version put its picture on the screen 10
# to 16 seconds after its service started, even with the picture already
# rendered and waiting in the cache. None of that was drawing. It was the
# interpreter starting up while udev and the journal were saturating the SD
# card underneath it.
#
# So the first frame is written here, by dd, within milliseconds. The Python
# script then takes over for the moving bar, whenever it manages to load. By
# then the screen has been showing the right thing for ten seconds.
#
# The cache is built by `boot-splash.py --render`, which tools/deploy.sh runs
# after every transfer. If it is not there, this exits quietly and the Python
# script draws the screen the slow way.

set -eu

ROLLE="${1:-boot}"
CACHE=/var/cache/photobooth

[ -r /sys/class/graphics/fb0/virtual_size ] || exit 0

# "1920,1080" -> width and height. The framebuffer comes up at 32 bits on this
# Pi and is reconfigured to 16 a moment later, so the depth is read too and
# both are kept in the cache.
groesse=$(cat /sys/class/graphics/fb0/virtual_size)
breite=${groesse%,*}
hoehe=${groesse#*,}
tiefe=$(cat /sys/class/graphics/fb0/bits_per_pixel)

datei="$CACHE/$ROLLE-${breite}x${hoehe}-${tiefe}.raw"
[ -f "$datei" ] || exit 0

# On the way down, take the framebuffer away from the text console first.
#
# systemd writes its "Stopped ..." lines to the console while the machine goes
# down, and during a shutdown that console lands on the terminal the screen is
# showing. The picture ends up buried under a wall of white-on-black, which is
# exactly what it was put there to replace. Neither console=tty3 nor
# systemd.show_status=error stops it: the output simply reappears on the
# visible terminal.
#
# Unbinding fbcon disconnects the text console from the framebuffer, so
# nothing is drawn over the picture afterwards. It only lasts until the next
# boot, and the kernel still logs everywhere it logged before, the serial
# console included.
if [ "$ROLLE" = shutdown ]; then
    for vtcon in /sys/class/vtconsole/vtcon*; do
        case "$(cat "$vtcon/name" 2>/dev/null)" in
            *"frame buffer device"*) echo 0 > "$vtcon/bind" 2>/dev/null || true ;;
        esac
    done
fi

# conv=notrunc because /dev/fb0 is a device, not a file to be shortened.
dd if="$datei" of=/dev/fb0 bs=1M conv=notrunc status=none 2>/dev/null || exit 0
