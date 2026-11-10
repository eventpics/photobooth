#!/usr/bin/env bash
# Sets the PIN for the booth's settings - without knowing the old one.
#
#   bash set-pin.sh               enter a new PIN
#   bash set-pin.sh --if-default  only ask while the default 1234 still applies
#
# Anyone with a console here is holding the box anyway. There is deliberately
# no other way back into the settings; see docs/decision-admin-pin.md.
set -euo pipefail
cd "$(dirname "$0")"

KONFIG=config.json
DIENST=photobooth.service
VORGABE=1234

aktuelle_pin() {
    python3 -c "import json;print(json.load(open('$KONFIG')).get('booth',{}).get('pin','$VORGABE'))"
}

if [ "${1:-}" = "--if-default" ]; then
    if [ "$(aktuelle_pin)" != "$VORGABE" ]; then
        echo "PIN ist bereits gesetzt. Aendern mit:  bash set-pin.sh"
        exit 0
    fi
    if [ ! -t 0 ]; then
        echo "Keine Eingabe moeglich - die PIN bleibt $VORGABE. Aendern mit:  bash set-pin.sh"
        exit 0
    fi
fi

echo "PIN fuer die Einstellungen der Fotobox (genau vier Ziffern)."
while true; do
    read -r -s -p "Neue PIN:          " PIN; echo
    if ! [[ "$PIN" =~ ^[0-9]{4}$ ]]; then
        echo "Bitte genau vier Ziffern."; continue
    fi
    if [ "$PIN" = "$VORGABE" ]; then
        echo "$VORGABE ist die Voreinstellung und fuer jeden nachzulesen. Bitte eine andere."; continue
    fi
    read -r -s -p "PIN wiederholen:   " PIN2; echo
    [ "$PIN" = "$PIN2" ] && break
    echo "Die beiden Eingaben stimmen nicht ueberein."
done

# A running booth keeps the settings in memory and writes them back to the file
# on every change. If it keeps running it could overwrite the new PIN with the
# old one on its next save. Hence: stop, write, start again.
LIEF=0
if systemctl cat "$DIENST" >/dev/null 2>&1; then
    if systemctl is-active --quiet "$DIENST"; then
        LIEF=1
        sudo systemctl stop "$DIENST"
    fi
elif pgrep -f "python.*photobooth\.py" >/dev/null; then
    echo "Die Fotobox laeuft gerade von Hand gestartet."
    echo "Bitte dort mit Strg+C beenden und diesen Befehl noch einmal ausfuehren."
    exit 1
fi

PIN="$PIN" python3 - "$KONFIG" <<'PY'
import json, os, sys
pfad = sys.argv[1]
with open(pfad, encoding="utf-8") as f:
    daten = json.load(f)
daten.setdefault("booth", {})["pin"] = os.environ["PIN"]
# Write into the same file, so owner and permissions are preserved.
with open(pfad, "w", encoding="utf-8") as f:
    json.dump(daten, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY

# Only restart what was running before - a box stopped on purpose stays off.
if [ "$LIEF" = 1 ]; then
    sudo systemctl start "$DIENST"
fi
echo "PIN gesetzt."
