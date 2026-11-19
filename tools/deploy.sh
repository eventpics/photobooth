#!/usr/bin/env bash
# Copy the working tree to the booth and restart it.
#
#   tools/deploy.sh                # copy and restart
#   tools/deploy.sh --no-restart   # copy only
#   tools/deploy.sh --dry-run      # show what would happen, change nothing
#
# Why this exists instead of a hand-typed rsync: the booth holds files that
# live nowhere else. The Godox mesh keys, the configuration with the PIN and
# the API key, the journal database, the captures, the log. Every one of them
# is in .gitignore, so the repository has no copy, and a plain
# `rsync --delete` wipes them without a word. That happened once and the lamp
# had to be provisioned again from scratch.
#
# The exclude list below must therefore stay in step with .gitignore. It is
# written out rather than derived from it: rsync's dir-merge filter does not
# protect a destination directory whose counterpart is missing on this side,
# which is exactly the case that caused the loss. After the transfer the
# script checks that the irreplaceable files are still there.

set -euo pipefail

HOST="${PHOTOBOOTH_HOST:-fotobox}"
ZIEL="${PHOTOBOOTH_PATH:-/home/fotobox/Downloads/eventpics-fotobox-test}"
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

neustart=1
trocken=()
case "${1:-}" in
    --no-restart) neustart=0 ;;
    --dry-run)    neustart=0; trocken=(--dry-run --itemize-changes) ;;
    "")           ;;
    *)            echo "Unbekannte Option: $1" >&2; exit 2 ;;
esac

#: Everything that exists only on the booth, plus the usual build leftovers.
#: Keep in step with .gitignore.
NUR_AUF_DER_BOX=(
    --exclude='.git'
    --exclude='.DS_Store'
    --exclude='__pycache__'
    --exclude='*.pyc'
    --exclude='.venv'
    --exclude='venv'
    --exclude='vendor'                      # fetched by install-pi.sh
    --exclude='config.json'                 # holds the PIN and the API key
    --exclude='config.local.json'
    --exclude='godox-mesh-state.json'       # the lamp's mesh keys
    --exclude='godox-mesh-state.json.*'
    --exclude='captures'                    # photographs of real people
    --exclude='booth.db'
    --exclude='booth.db-shm'
    --exclude='booth.db-wal'
    --exclude='events.log'
    --exclude='.lgd-nfy*'                   # a named pipe, runtime only
)

#: The files that exist only on the booth. Checked before and after, because
#: a file that was already missing is not news - one that disappears during
#: the transfer is.
UNERSETZLICH="config.json godox-mesh-state.json booth.db \
              vendor/godox-mesh/src/godox_mesh_bt/controller.py"

bestand() {
    ssh "$HOST" "cd '$ZIEL' && for f in $UNERSETZLICH; do \
        [ -e \"\$f\" ] && echo \"\$f\"; done" | sort
}

vorher=$(bestand)

echo "Uebertrage $HIER -> $HOST:$ZIEL"
# The `+` form keeps `set -u` quiet when the array is empty, which bash 3.2
# on macOS otherwise treats as an unbound variable.
rsync -a --delete ${trocken[@]+"${trocken[@]}"} "${NUR_AUF_DER_BOX[@]}" \
      "$HIER/" "$HOST:$ZIEL/"

if [[ ${#trocken[@]:-0} -gt 0 ]]; then
    echo "Probelauf, es wurde nichts geaendert."
    exit 0
fi

verloren=$(comm -23 <(echo "$vorher") <(bestand))
if [[ -n "$verloren" ]]; then
    echo "Die Uebertragung hat Dateien geloescht, die es nur auf der Box gab:" >&2
    echo "$verloren" | sed "s/^/  /" >&2
    echo "Nicht neu starten, erst wiederherstellen." >&2
    exit 1
fi
echo "Nichts verloren, was nur auf der Box liegt."

# The start screen is a pre-rendered framebuffer dump. Building it takes about
# fourteen seconds on a booting Pi and a moment on an idle one, so it happens
# here rather than during the next boot.
echo "Rechne die Startbilder vor"
if ! ssh "$HOST" "sudo -n /usr/bin/python3 '$ZIEL/autostart/boot-splash.py' --render" \
        2>/dev/null; then
    # Not worth failing the deploy over: without the cache the splash renders
    # itself on the next boot, which is slow once and fast afterwards.
    echo "  ging nicht ohne Passwort. Auf der Box nachholen mit:" >&2
    echo "  sudo python3 $ZIEL/autostart/boot-splash.py --render" >&2
fi

if [[ $neustart == 1 ]]; then
    echo "Starte den Dienst neu"
    # -n rather than a prompt: this runs over ssh without a terminal, so a
    # password question would hang rather than ask. The booth's password
    # belongs to its owner and never to a file in this repository.
    if ssh "$HOST" 'sudo -n systemctl restart photobooth' 2>/dev/null; then
        sleep 10
        ssh "$HOST" 'systemctl is-active photobooth'
    else
        echo "  ging nicht ohne Passwort. Auf der Box nachholen mit:" >&2
        echo "  sudo systemctl restart photobooth" >&2
    fi
fi
