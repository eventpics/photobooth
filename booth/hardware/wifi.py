"""Wi-Fi, driven through NetworkManager's own command line tool.

The booth may do this without any extra privilege, and that is worth writing
down because it looks surprising. It runs under cage in a real local login
session on seat0 - that is what `PAMName=login` and `TTYPath=/dev/tty1` in
photobooth.service are for - and polkit grants an active local session
`network-control` and `settings.modify.system` by default. Checked with
pkcheck against the running process: all allowed.

The same commands from an SSH session are refused with "System policy prevents
control of network connections". So this cannot be tested over SSH; it has to
be tried on the box itself.

The password never travels in argv, where every local process could read it
out of `ps`. `nmcli --ask` asks for it on standard input, and that is where it
is fed in.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from typing import Any

log = logging.getLogger(__name__)

#: Scanning takes a moment, connecting can take a good deal longer: DHCP has to
#: answer as well. Beyond this the attempt counts as failed.
SCAN_TIMEOUT = 20.0
CONNECT_TIMEOUT = 45.0
SHORT_TIMEOUT = 8.0

#: What nmcli says when the password was wrong. It does not say so plainly -
#: from outside, a wrong key and a lamp out of range look much the same.
_FEHLER_TEXTE = [
    ("secrets were required", "Passwort fehlt"),
    ("no network with ssid", "Netz nicht gefunden"),
    ("not authorized", "Keine Berechtigung"),
    ("system policy prevents", "Keine Berechtigung"),
    ("802-11-wireless-security.psk", "Passwort zu kurz (mindestens 8 Zeichen)"),
    ("timeout", "Zeitüberschreitung"),
]


def _lauf(args: list[str], eingabe: str | None = None,
          timeout: float = SHORT_TIMEOUT) -> tuple[int, str]:
    """One nmcli call. Returns the exit code and output, never raises."""
    if not shutil.which("nmcli"):
        return 127, "nmcli ist nicht installiert"
    try:
        fertig = subprocess.run(["nmcli", *args], input=eingabe, capture_output=True,
                                text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except OSError as fehler:
        return 1, str(fehler)
    return fertig.returncode, (fertig.stdout + fertig.stderr).strip()


def _felder(zeile: str) -> list[str]:
    """Split one -t line into its fields.

    nmcli separates with a colon and escapes a colon inside a value as `\\:`.
    A plain split() would tear an SSID like "Bar:Grill" in half.
    """
    felder, jetzt, schraeg = [], [], False
    for zeichen in zeile:
        if schraeg:
            jetzt.append(zeichen)
            schraeg = False
        elif zeichen == "\\":
            schraeg = True
        elif zeichen == ":":
            felder.append("".join(jetzt))
            jetzt = []
        else:
            jetzt.append(zeichen)
    felder.append("".join(jetzt))
    return felder


def _klartext(ausgabe: str) -> str:
    """Turn an nmcli complaint into something a host can act on."""
    klein = ausgabe.lower()
    for muster, text in _FEHLER_TEXTE:
        if muster in klein:
            return text
    # The last line is usually the actual complaint; the ones before it are
    # progress notes.
    zeilen = [z.strip() for z in ausgabe.splitlines() if z.strip()]
    return zeilen[-1] if zeilen else "Verbinden fehlgeschlagen"


def device() -> str:
    """The name of the Wi-Fi device, or "" when the box has none."""
    code, aus = _lauf(["-t", "-f", "DEVICE,TYPE", "device", "status"])
    if code:
        return ""
    for zeile in aus.splitlines():
        teile = _felder(zeile)
        if len(teile) >= 2 and teile[1] == "wifi":
            return teile[0]
    return ""


def radio_on() -> bool:
    code, aus = _lauf(["radio", "wifi"])
    return code == 0 and aus.strip().lower().startswith("enabled")


def set_radio(an: bool) -> bool:
    code, _ = _lauf(["radio", "wifi", "on" if an else "off"])
    return code == 0


def status() -> dict[str, Any]:
    """What the box is connected to right now.

    `available` is False when there is no Wi-Fi device at all. The settings
    then leave the page out rather than showing an empty list.
    """
    gerät = device()
    if not gerät:
        return {"available": False, "radio": False, "connected": False,
                "ssid": "", "signal": 0, "ip": "", "device": ""}

    daten = {"available": True, "radio": radio_on(), "device": gerät,
             "connected": False, "ssid": "", "signal": 0, "ip": ""}
    code, aus = _lauf(["-t", "-f", "GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS",
                       "device", "show", gerät])
    if code:
        return daten
    for zeile in aus.splitlines():
        teile = _felder(zeile)
        if len(teile) < 2:
            continue
        schlüssel, wert = teile[0], ":".join(teile[1:]).strip()
        if schlüssel.startswith("GENERAL.STATE"):
            daten["connected"] = "connected" in wert.lower() and "dis" not in wert.lower()
        elif schlüssel.startswith("GENERAL.CONNECTION"):
            daten["ssid"] = "" if wert in ("--", "") else wert
        elif schlüssel.startswith("IP4.ADDRESS") and wert and wert != "--":
            daten["ip"] = wert.split("/")[0]
    for netz in networks(rescan=False):
        if netz["active"]:
            daten["signal"] = netz["signal"]
            break
    return daten


def saved() -> set[str]:
    """The networks the box already knows the password for."""
    code, aus = _lauf(["-t", "-f", "NAME,TYPE", "connection", "show"])
    if code:
        return set()
    namen = set()
    for zeile in aus.splitlines():
        teile = _felder(zeile)
        if len(teile) >= 2 and "wireless" in teile[1]:
            namen.add(teile[0])
    return namen


def networks(rescan: bool = True) -> list[dict[str, Any]]:
    """Everything in range, strongest first, one entry per name.

    A network often answers on several channels at once, 2.4 and 5 GHz under
    the same name. Showing it three times would only make the list longer, so
    the strongest of them wins.
    """
    code, aus = _lauf(["-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi",
                       "list", "--rescan", "yes" if rescan else "no"],
                      timeout=SCAN_TIMEOUT if rescan else SHORT_TIMEOUT)
    if code:
        log.debug("Wi-Fi scan failed: %s", aus)
        return []
    bekannt = saved()
    beste: dict[str, dict[str, Any]] = {}
    for zeile in aus.splitlines():
        teile = _felder(zeile)
        if len(teile) < 4:
            continue
        benutzt, ssid, stärke, sicherheit = teile[0], teile[1], teile[2], teile[3]
        if not ssid:
            continue        # a hidden network has nothing to tap on
        try:
            signal = int(stärke)
        except ValueError:
            signal = 0
        eintrag = {"ssid": ssid, "signal": signal,
                   "secure": bool(sicherheit.strip()),
                   "security": sicherheit.strip(),
                   "active": benutzt.strip() == "*",
                   "saved": ssid in bekannt}
        alt = beste.get(ssid)
        if alt is None or eintrag["signal"] > alt["signal"]:
            if alt is not None:
                eintrag["active"] = eintrag["active"] or alt["active"]
            beste[ssid] = eintrag
    return sorted(beste.values(), key=lambda n: (-n["active"], -n["signal"], n["ssid"].lower()))


def connect(ssid: str, password: str | None = None) -> dict[str, Any]:
    """Join a network. Takes seconds, so never call this on the UI thread.

    With no password, the stored profile is used - that is the case for a
    network the box has been on before.
    """
    if not ssid:
        return {"ok": False, "error": "Kein Netz gewählt"}
    if not radio_on():
        set_radio(True)
        time.sleep(1.5)

    if password:
        # --ask makes nmcli read the secret from standard input instead of
        # taking it from the command line, where `ps` would show it to every
        # process on the box.
        code, aus = _lauf(["--ask", "device", "wifi", "connect", ssid],
                          eingabe=password + "\n", timeout=CONNECT_TIMEOUT)
    else:
        code, aus = _lauf(["device", "wifi", "connect", ssid], timeout=CONNECT_TIMEOUT)

    if code == 0:
        jetzt = status()
        return {"ok": True, "ssid": jetzt.get("ssid") or ssid, "ip": jetzt.get("ip", "")}
    # A failed attempt leaves a profile behind that would be retried on every
    # boot. Away with it, or a mistyped password haunts the box.
    if password:
        forget(ssid)
    return {"ok": False, "error": _klartext(aus)}


def disconnect() -> bool:
    gerät = device()
    if not gerät:
        return False
    code, _ = _lauf(["device", "disconnect", gerät], timeout=SHORT_TIMEOUT)
    return code == 0


def forget(ssid: str) -> bool:
    """Delete the stored profile, so the box stops joining this network."""
    if not ssid:
        return False
    code, _ = _lauf(["connection", "delete", ssid], timeout=SHORT_TIMEOUT)
    return code == 0
