#!/usr/bin/env bash
# Mounts a USB stick - or unmounts it again.
#
# On a Raspberry Pi with a desktop the file manager does this. The booth has no
# desktop: the screen only ever shows the booth itself. Without this script the
# stick sits there and nobody notices it.
#
# Called by udev as soon as a USB volume appears or disappears.
#   usb-mount.sh mount   sda1 <user>
#   usb-mount.sh unmount sda1 <user>
#
# The user comes from the udev rule, which the setup script fills in with the
# actual name. This used to say "fotobox" outright - on a freshly set up card
# with a different user name the stick was then never mounted.
set -u

WAS="${1:-}"
KERN="${2:-}"
BENUTZER="${3:-}"
[ -n "$BENUTZER" ] || exit 0
[ -n "$KERN" ] || exit 0

WURZEL="/media/$BENUTZER"
GERAET="/dev/$KERN"

# On removal the filesystem is already gone, so blkid says nothing. But
# /proc/mounts still knows where the stick was - the device name is in there.
aushaengen() {
    ZIEL="$(awk -v g="$GERAET" '$1==g{print $2; exit}' /proc/mounts \
            | sed 's/\\040/ /g')"
    [ -n "$ZIEL" ] || exit 0
    umount -l "$ZIEL" 2>/dev/null
    rmdir "$ZIEL" 2>/dev/null
    logger -t photobooth-usb "ausgehaengt: $GERAET von $ZIEL"
    exit 0
}

[ "$WAS" = "unmount" ] && aushaengen

[ -b "$GERAET" ] || exit 0

TYPE=""; LABEL=""
eval "$(blkid -o export "$GERAET" 2>/dev/null | grep -E '^(TYPE|LABEL)=')"
[ -n "$TYPE" ] || exit 0

KENNUNG="$(id -u "$BENUTZER" 2>/dev/null)" || exit 0
GRUPPE="$(id -g "$BENUTZER" 2>/dev/null)"

# Filesystems with no permissions of their own need the owner given at mount
# time - otherwise everything belongs to root and the booth may not write.
# Native Linux filesystems do not know these options and reject them.
case "$TYPE" in
    vfat|exfat|ntfs|ntfs3|msdos) OPTIONEN="uid=$KENNUNG,gid=$GRUPPE,umask=000" ;;
    *)                           OPTIONEN="" ;;
esac

# Mount under the stick's label, the way the file manager did - "USB-blau"
# reads better than "sda1". With no label, the device name has to do.
if [ -n "$LABEL" ]; then
    SAUBER="$(printf '%s' "$LABEL" | tr -c 'A-Za-z0-9._-' '_')"
else
    SAUBER="$KERN"
fi
ZIEL="$WURZEL/$SAUBER"

# A leftover from before would be in the way. Only when it is empty - a folder
# with something in it belongs to somebody, and you do not delete that
# unasked.
[ -d "$ZIEL" ] && ! mountpoint -q "$ZIEL" && rmdir "$ZIEL" 2>/dev/null
mkdir -p "$ZIEL"
if [ -n "$OPTIONEN" ]; then
    mount -o "$OPTIONEN" "$GERAET" "$ZIEL" || { rmdir "$ZIEL" 2>/dev/null; exit 0; }
else
    mount "$GERAET" "$ZIEL" || { rmdir "$ZIEL" 2>/dev/null; exit 0; }
    chown "$BENUTZER:$BENUTZER" "$ZIEL" 2>/dev/null
fi

logger -t photobooth-usb "eingehaengt: $GERAET ($TYPE${LABEL:+, $LABEL}) auf $ZIEL"
