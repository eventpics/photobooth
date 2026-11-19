"""Uploading into an EventPics gallery.

The route has two steps, exactly as the API demo at
event.pics/en/tutorial/api-demo.html shows them:

    POST /getuploadurl   {apiKey, linkId, fileName, takenAt, albumId?}
                         -> {uploadUrl}
    PUT  <uploadUrl>     the file contents

The second step does not go to EventPics but to the storage behind it - the
URL is short-lived and carries the authorisation within itself.

Order is not decoration here: a gallery shows pictures in the order they
arrive. This class therefore only ever uploads one file at a time, and the
queue in front of it (see journal.claim_next with strict_order) lets no later
picture past one that is stuck.

Deliberately without an extra dependency: urllib from the standard library is
enough, and on a device somebody assembles themselves from instructions, one
library fewer is one source of failure fewer.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

BASIS = "https://api.event.pics"

#: User agent for every request. Without one, urllib sends "Python-urllib/3.x",
#: and EventPics has a firewall in front of it: on 25.09.2026 every upload came
#: back with "HTTP 403 error code: 1010" - Cloudflare's block on known
#: programmatic agents. Tested on the Pi: any other agent string got through.
AGENT = "EventPics-Photobooth/0.7.0"


class EventPicsError(RuntimeError):
    pass


def maskieren(schluessel: str, sichtbar: int = 4) -> str:
    """Show only the beginning, cover the rest.

    The key appears in a web interface reachable on the event network. Enough
    stays visible to tell two keys apart.
    """
    schluessel = (schluessel or "").strip()
    if not schluessel:
        return ""
    if len(schluessel) <= sichtbar:
        return "*" * len(schluessel)
    return schluessel[:sichtbar] + "*" * (len(schluessel) - sichtbar)


#: Name of the file on the USB stick the credentials are read from.
SETUP_DATEI = "fotobox-eventpics.txt"


def zugang_lesen(text: str) -> dict[str, str]:
    """Pull credentials out of a piece of text.

    Deliberately accepts several spellings, because the text may come from a
    QR code, a text file or the clipboard, and nobody should have to memorise
    one particular shape:

        abcd1234...                        the key on its own
        apikey=abcd1234...                 lines with = or :
        key: abcd1234...
        event=abcd1234
        {"apiKey": "...", "linkId": "..."} JSON
        eventpics://setup?apiKey=...&linkId=...
    """
    text = (text or "").strip()
    if not text:
        return {}
    gefunden: dict[str, str] = {}

    # Only the key is carried over. Event and album come from the API itself -
    # dragging them along here would mean maintaining the same fact in two
    # places, and the second one would be stale sooner or later.
    namen = {
        "apikey": "api_key", "api_key": "api_key", "key": "api_key",
        "schluessel": "api_key", "schlüssel": "api_key",
    }

    if text.startswith("{"):
        try:
            roh = json.loads(text)
            if isinstance(roh, dict):
                for k, v in roh.items():
                    ziel = namen.get(str(k).strip().lower())
                    if ziel and v:
                        gefunden[ziel] = str(v).strip()
                return gefunden
        except ValueError:
            pass

    if "://" in text and "?" in text:
        try:
            abfrage = urllib.parse.parse_qs(urllib.parse.urlparse(text).query)
            for k, v in abfrage.items():
                ziel = namen.get(k.strip().lower())
                if ziel and v and v[0]:
                    gefunden[ziel] = v[0].strip()
            if gefunden:
                return gefunden
        except ValueError:
            pass

    for zeile in text.splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#"):
            continue
        for trenner in ("=", ":"):
            if trenner in zeile:
                name, _, wert = zeile.partition(trenner)
                ziel = namen.get(name.strip().lower())
                if ziel and wert.strip():
                    gefunden[ziel] = wert.strip()
                break
        else:
            # A line with no separator: that is the key itself.
            gefunden.setdefault("api_key", zeile)
    return gefunden


class EventPicsTarget:
    def __init__(self, config, events=None, timeout: float = 45.0) -> None:
        self.config = config
        self.events = events
        self.timeout = timeout

    # -- settings ----------------------------------------------------------
    @property
    def cfg(self) -> dict[str, Any]:
        return self.config.section("eventpics")

    @property
    def basis(self) -> str:
        """Normally the real API. Configurable so the whole route can be
        checked against a stand-in server, without loading other people's
        pictures into a real gallery."""
        return str(self.cfg.get("base_url") or BASIS).rstrip("/")

    @property
    def api_key(self) -> str:
        return str(self.cfg.get("api_key", "")).strip()

    @property
    def link_id(self) -> str:
        return str(self.cfg.get("link_id", "")).strip()

    def enabled(self) -> bool:
        return bool(self.cfg.get("enabled", False)) and bool(self.api_key) and bool(self.link_id)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.cfg.get("enabled", False)),
            "configured": bool(self.api_key and self.link_id),
            "api_key_masked": maskieren(self.api_key),
            "link_id": self.link_id,
            "album_id": str(self.cfg.get("album_id", "")),
            "event_title": str(self.cfg.get("event_title", "")),
        }

    # -- setup without a keyboard -----------------------------------------
    def uebernehmen(self, gefunden: dict[str, str]) -> list[str]:
        """Write the key that was found into the configuration."""
        geaendert = []
        for schluessel in ("api_key",):
            wert = gefunden.get(schluessel)
            if wert and self.cfg.get(schluessel) != wert:
                self.cfg[schluessel] = wert
                geaendert.append(schluessel)
        if geaendert:
            self.config.save()
        return geaendert

    def vom_stick(self, usb) -> dict[str, Any]:
        """Take credentials from a file on the USB stick.

        The second route, for when the camera is not up to it. On the stick
        the key sits in a text file that takes a second to write at a
        computer. Only the key is taken over.

        The file is deleted afterwards: an access key has no business on a
        stick that later ends up among guests.
        """
        mount = usb.find_mount() if usb else None
        if mount is None:
            return {"ok": False, "error": "Kein USB-Stick angesteckt"}
        datei = Path(mount) / SETUP_DATEI
        if not datei.exists():
            return {"ok": False, "error": f"Keine Datei {SETUP_DATEI} auf dem Stick"}
        try:
            text = datei.read_text(encoding="utf-8", errors="ignore")[:2000]
        except OSError as exc:
            return {"ok": False, "error": f"Datei nicht lesbar: {exc}"}
        gefunden = zugang_lesen(text)
        if not gefunden.get("api_key"):
            return {"ok": False, "error": "In der Datei steht kein Schlüssel"}
        geaendert = self.uebernehmen(gefunden)
        try:
            datei.unlink(missing_ok=True)
        except OSError:
            log.warning("Setup-Datei liess sich nicht loeschen")
        if self.events is not None:
            self.events.add("EventPics-Zugang vom USB-Stick übernommen", "good")
        return {"ok": True, "uebernommen": geaendert, "quelle": "USB-Stick"}

    @staticmethod
    def qr_moeglich() -> bool:
        import shutil  # noqa: PLC0415
        return shutil.which("zbarimg") is not None

    def dekodieren(self, pixels) -> str:
        """Read a code off one camera frame. Empty text if there is none.

        Written out as a grey PGM rather than encoded as a JPEG: zbar wants a
        file, a code has no colour, and a header plus the raw bytes is the
        cheapest file there is.
        """
        import subprocess  # noqa: PLC0415
        import tempfile  # noqa: PLC0415

        if pixels is None or not self.qr_moeglich():
            return ""
        feld = pixels
        if getattr(feld, "ndim", 2) == 3:
            # The live image arrives with four channels, the fourth carries no
            # picture. Grey is the mean of the other three.
            feld = feld[:, :, :3].mean(axis=2)
        grau = feld.astype("uint8")
        hoehe, breite = grau.shape[0], grau.shape[1]
        with tempfile.NamedTemporaryFile(suffix=".pgm", delete=False) as fh:
            fh.write(b"P5\n%d %d\n255\n" % (breite, hoehe))
            fh.write(grau.tobytes())
            pfad = Path(fh.name)
        try:
            ergebnis = subprocess.run(["zbarimg", "--quiet", "--raw", "-1", str(pfad)],
                                      capture_output=True, text=True, timeout=10)
            return (ergebnis.stdout or "").strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.warning("zbarimg failed: %s", exc)
            return ""
        finally:
            try:
                pfad.unlink(missing_ok=True)
            except OSError:
                pass

    def vom_bild(self, pixels) -> dict[str, Any]:
        """Take the credentials from one frame of the live image."""
        text = self.dekodieren(pixels)
        if not text:
            return {"ok": False, "gefunden": False}
        gefunden = zugang_lesen(text)
        if not gefunden.get("api_key"):
            return {"ok": False, "gefunden": True,
                    "error": "In dem Code steht kein Schlüssel."}
        geaendert = self.uebernehmen(gefunden)
        if self.events is not None:
            self.events.add("EventPics-Zugang vom QR-Code übernommen", "good")
        return {"ok": True, "gefunden": True, "uebernommen": geaendert, "quelle": "QR-Code"}

    # -- API ---------------------------------------------------------------
    def _anfrage(self, url: str, *, method: str = "GET", daten: bytes | None = None,
                 kopf: dict[str, str] | None = None) -> tuple[int, bytes]:
        req = urllib.request.Request(url, data=daten, method=method,
                                     headers={"User-Agent": AGENT, **(kopf or {})})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as antwort:
                return antwort.status, antwort.read()
        except urllib.error.HTTPError as exc:
            körper = b""
            try:
                körper = exc.read()[:500]
            except Exception:  # noqa: BLE001
                pass
            raise EventPicsError(
                f"HTTP {exc.code} {körper.decode('utf-8', 'replace').strip()}".strip()) from exc
        except urllib.error.URLError as exc:
            raise EventPicsError(f"Keine Verbindung: {exc.reason}") from exc
        except TimeoutError as exc:
            raise EventPicsError("Zeitüberschreitung") from exc

    def events_and_albums(self) -> dict[str, Any]:
        """The account's events and albums, for the picker in the settings."""
        if not self.api_key:
            raise EventPicsError("Kein API-Schlüssel eingetragen")
        status, körper = self._anfrage(
            f"{self.basis}/geteventsandalbums",
            kopf={"Authorization": f"Bearer {self.api_key}"})
        try:
            return json.loads(körper.decode("utf-8"))
        except ValueError as exc:
            raise EventPicsError("Unerwartete Antwort beim Laden der Events") from exc

    # -- One direct link per picture --------------------------------------
    #: A file beside the captures holding file name -> media id.
    LINK_DATEI = "eventpics-links.json"

    def _links_pfad(self) -> Path:
        return Path(self.cfg.get("link_store") or "eventpics-links.json")

    def links_lesen(self) -> dict[str, Any]:
        try:
            return json.loads(self._links_pfad().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def link_merken(self, name: str, adresse: str, herunterladen: str = "") -> str:
        """Record the URL of this one picture.

        The URL arrives ready-made from the API. Assembling it here from a
        linkId and a document id would mean reimplementing a rule that belongs
        to the server - and that would quietly go stale on its next rebuild.

        The QR code is made from it, the one a guest uses to pull their own
        picture onto their phone without opening everyone else's gallery.
        """
        daten = self.links_lesen()
        daten[name] = {"url": adresse, "download_url": herunterladen or "",
                       "at": time.time()}
        # Keep only the most recent entries - the file must not grow forever.
        if len(daten) > 400:
            aeltest = sorted(daten.items(), key=lambda kv: kv[1].get("at", 0))
            for schluessel, _ in aeltest[:len(daten) - 400]:
                daten.pop(schluessel, None)
        try:
            ziel = self._links_pfad()
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
        except OSError:
            log.warning("Linkliste liess sich nicht schreiben")
        return adresse

    def link_fuer(self, name: str) -> str | None:
        eintrag = self.links_lesen().get(name)
        return eintrag.get("url") if eintrag else None

    def _upload_url(self, pfad: Path) -> tuple[str, dict[str, Any]]:
        rumpf = {
            "apiKey": self.api_key,
            "linkId": self.link_id,
            "fileName": pfad.name,
            # In milliseconds, as in the demo. The capture time decides where
            # the picture is sorted into the gallery.
            "takenAt": int(pfad.stat().st_mtime * 1000),
        }
        album = str(self.cfg.get("album_id", "")).strip()
        if album:
            rumpf["albumId"] = album
        status, körper = self._anfrage(
            f"{self.basis}/getuploadurl", method="POST",
            daten=json.dumps(rumpf).encode("utf-8"),
            kopf={"Content-Type": "application/json"})
        try:
            antwort = json.loads(körper.decode("utf-8"))
        except ValueError as exc:
            raise EventPicsError("Unerwartete Antwort auf getuploadurl") from exc
        url = antwort.get("uploadUrl")
        if not url:
            raise EventPicsError(f"Keine uploadUrl erhalten: {antwort}")
        return str(url), antwort

    @staticmethod
    def _inhaltstyp(url: str, pfad: Path) -> str:
        """The storage behind the URL often dictates the content type itself.

        If it is a parameter in the URL, exactly that type has to be sent -
        otherwise the signature check rejects the upload.
        """
        try:
            aus_url = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("Content-Type")
            if aus_url and aus_url[0]:
                return aus_url[0]
        except ValueError:
            pass
        geraten, _ = mimetypes.guess_type(pfad.name)
        return geraten or "application/octet-stream"

    def upload(self, pfad: Path, kind: str = "result", session: str = "") -> None:
        """Upload one file. Raises on any failure - the queue retries later and
        lets nothing past until then."""
        if not self.enabled():
            raise EventPicsError("EventPics ist nicht eingerichtet")
        pfad = Path(pfad)
        if not pfad.exists():
            raise EventPicsError(f"{pfad.name} gibt es nicht mehr")

        beginn = time.monotonic()
        url, antwort = self._upload_url(pfad)
        typ = self._inhaltstyp(url, pfad)
        inhalt = pfad.read_bytes()
        status, _ = self._anfrage(url, method="PUT", daten=inhalt,
                                  kopf={"Content-Type": typ,
                                        "Content-Length": str(len(inhalt))})
        if status >= 300:
            raise EventPicsError(f"PUT {status}")

        # Recorded only after a successful upload: a URL for a picture that
        # never arrived would be a link into nothing.
        # mediaUrl and not photoUrl: video goes through the same interface, and
        # a field should not be named after what it only sometimes is.
        adresse = str(antwort.get("mediaUrl") or "").strip()
        if adresse:
            self.link_merken(pfad.name, adresse,
                             str(antwort.get("downloadUrl") or "").strip())
        else:
            adresse = None
        log.info("EventPics: %s hochgeladen (%.1f kB, %.1f s)%s",
                 pfad.name, len(inhalt) / 1024, time.monotonic() - beginn,
                 f" -> {adresse}" if adresse
                 else " - ohne Link, dafuer gibt es keinen QR-Code")
