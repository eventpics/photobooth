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

# conv=notrunc because /dev/fb0 is a device, not a file to be shortened.
dd if="$datei" of=/dev/fb0 bs=1M conv=notrunc status=none 2>/dev/null || exit 0
