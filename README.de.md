# EventPics Photobooth

Software für eine selbst gebaute Fotobox auf dem Raspberry Pi: Livebild und
Countdown im Vollbild, Einzelbild oder Collage mit Rahmen und Namen, Druck auf
dem Canon Selphy, Sicherung auf einem USB-Stick und auf Wunsch Upload zu
EventPics mit einem QR-Code für jedes Bild. Bedient wird sie am Touchscreen, die
Einstellungen liegen hinter einer PIN.

Die Oberfläche ist ein eigenes Programm (Qt), kein Browser und kein Webserver.
Das Livebild geht direkt von der Kamera auf die Grafikkarte. Bedienen lässt sich
die Box nur an ihrem eigenen Bildschirm – niemand im Netz kann auslösen, löschen
oder drucken. Gebaut ist die Oberfläche für 1920 × 1200 und wird auf jedem
Bildschirm als Ganzes skaliert.

*This file in English: [README.md](README.md).*
Anleitung und Stückliste: <https://event.pics/de/fotobox-selber-bauen.html>

## Auf dem Raspberry Pi

Empfohlen ist **Raspberry Pi OS Lite (64-bit)**, geschrieben mit dem Raspberry
Pi Imager.

```bash
sudo apt update && sudo apt install -y unzip
curl -LO https://event.pics/downloads/EventPics-Photobooth-v0.7.0.zip
unzip EventPics-Photobooth-v0.7.0.zip
cd eventpics-photobooth
bash install-pi.sh          # Pakete, SPI
bash autostart/setup.sh     # Start beim Einschalten, Touch, USB-Stick, PIN
sudo reboot
```

Nach dem Neustart steht die Fotobox auf dem Bildschirm. Die Einstellungen
erreichst du über das Zahnrad mit der PIN, nach der `setup.sh` gefragt hat.
PIN vergessen? `bash set-pin.sh` setzt eine neue, ohne die alte zu kennen.

Alles kommt aus den Paketquellen von Raspberry Pi OS, nichts über pip, und es
gibt keine eigene Python-Umgebung: picamera2 und die Qt-Anbindung (PySide6) sind
dort passend für den Pi gebaut.

Nützlich im Betrieb:

```bash
systemctl status photobooth
journalctl -t photobooth -f        # Meldungen der App
sudo systemctl restart photobooth
```

## Am Rechner entwickeln

Läuft auf macOS und Linux mit einer simulierten Kamera und GPIO im Speicher. Der
Mock-Modus wird automatisch erkannt (`config.json` → `app.mock: "auto"`).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python photobooth.py --window --scale 0.5
```

`--window` öffnet ein Fenster statt des Vollbilds, `--scale` verkleinert die
Bühne passend für einen Laptop. Beenden mit Esc.

### Stresstest

`tools/stress_test.py` bedient die echte App wie Gäste auf einer Hochzeit:
Einzelbilder, 3er- und 4er-Serien, ein hektischer Block mit wechselnden
Layouts, dazwischen Wiederholen und Verwerfen. Jede Serie landet mit Dauer,
Aufnahmezeit, Speicher, Temperatur und Upload-Warteschlange in
`/tmp/stress.jsonl`. Wie er auf dem Pi gestartet wird, steht oben in der Datei.
Die Bilder werden dabei wirklich gespeichert und hochgeladen.

Auf dem Pi 4 mit 1 GB (September 2026): 40 hektische Serien ohne Fehler, vom
Auslösen bis zum nächsten Schritt im Median 0,27 s und höchstens 0,36 s,
290 bis 360 MB Speicher, höchstens 63 °C.

### Systemüberwachung

Der Punkt oben links auf dem Bildschirm öffnet den Zustand: Kamera, USB-Stick,
Drucker, Temperatur, Arbeitsspeicher, Prozessor und freier Platz. Damit
beantwortest du die Frage, die sich sonst erst am Eventabend stellt: Wird die
Box im geschlossenen Gehäuse zu heiß?

Der Takt beim Prozessor steht immer zusammen mit dem Höchstwert da. Liegt er
weit darunter, drosselt sich der Pi – wegen Hitze oder **Unterspannung**. Das ist
die mit Abstand häufigste Ursache dafür, dass sich ein Raspberry Pi ohne
erkennbaren Grund seltsam verhält: meist ein zu schwaches Netzteil, ein
schlechtes USB-C-Kabel oder ein Bildschirm, der über sein Touch-Kabel Strom aus
dem Pi zieht.

Der Pi drosselt ab etwa 80 °C. Bis 70 °C ist alles unauffällig.

### Wächter

Stürzt die App ab, startet systemd sie drei Sekunden später neu. Für den
schwierigeren Fall – sie läuft noch, tut aber nichts mehr, etwa weil die Kamera
nicht antwortet – schreibt sie alle fünf Sekunden aus dem Takt ihrer Oberfläche
einen Zeitstempel nach `/dev/shm/photobooth-alive`. Ist er älter als eine
Minute, startet `photobooth-watchdog.service` sie neu.

### Wenig Arbeitsspeicher (1 GB)

Raspberry Pi OS reserviert auf Geräten mit 1 GB 512 MB fest für Kamera und
Grafik; übrig bleiben rund 390 MB für alles andere. Wird es eng, halbiere die
Reservierung in `/boot/firmware/config.txt`:

```
dtoverlay=vc4-kms-v3d,cma-256
```

Danach neu starten.

### Kamera

Eingestellt ist das **Raspberry Pi Camera Module 3 Standard** (Sensor IMX708,
76° diagonal). Der Sensor liefert 4608×2592 im Format 16:9; für einen
10×15-Ausdruck wird daraus auf 3:2 beschnitten – im Livebild genauso wie im
Foto, damit der Bildschirm zeigt, was gedruckt wird.

```bash
rpicam-hello --list-cameras
```

Wird keine Kamera gefunden, stimmt meist das Flachbandkabel oder dessen
Ausrichtung nicht. Am Pi 3 und Pi 4 passt das 15-Pin-Kabel, am Pi 5 das Kabel von
15 auf 22 Pin. Der Kamera liegen meist beide bei.

**Einmessen.** Stell jemanden auf den echten Standabstand, dunkle den Raum ab
und tippe in den Einstellungen auf „Automatisch einmessen“. Die Box sucht sich
zuerst das **Aufnahmelicht** selbst: nicht das hellste, sondern das dunkelste,
das Bewegung noch einfriert (Ziel 1/125 s). Darunter werden Belichtung,
Weißabgleich und Fokus gemessen und bleiben fest. Weil eine Belichtung nur zu
der Helligkeit passt, unter der sie gemessen wurde, wird beides zusammen
übernommen – der Ergebnisbildschirm zeigt den gefundenen Wert und bietet
„Altes Licht behalten“ an, was den alten Wert zurücksetzt und neu misst.

`LensPosition` ist in Dioptrien angegeben, also 1 geteilt durch die Entfernung
in Metern – 2,0 m entsprechen 0,5, und 2,5 m entsprechen 0,4.

### Ton

Die Box ist still. Es gab einmal Töne über den HDMI-Anschluss des Bildschirms –
einen mitzählenden Countdown, ein Klacken beim Auslösen, einen Dreiklang zum
fertigen Blatt. Sie sind im Oktober 2026 wieder herausgeflogen: auf einer Feier
hört sie ohnehin niemand, und was man nicht hört, muss man auch nicht
einstellen, erklären oder reparieren.

Der Countdown steht groß auf dem Schirm, und der Blitz sagt, dass ausgelöst
wurde.

### Verkabelung

| Funktion | GPIO (BCM) | Header-Pin | Beschaltung |
|---|---|---|---|
| Auslöser-Taster | 17 | 11 | gegen GND, interner Pull-up |
| Taster-LED | 27 | 13 | über 330 Ω, bei 12-V-LED über MOSFET |
| Licht (PWM) | 18 | 12 | an das Gate des MOSFET-Moduls |
| Masse | GND | 6, 9, 14 … | gemeinsame Masse mit dem 12-V-Netzteil |

### Woran die Leuchte hängt

Die Box kennt vier Arten von Licht, eingestellt unter `light.kind` oder in den
Einstellungen unter „Erweitert“:

| `kind` | Leuchte | Dimmen |
|---|---|---|
| `pwm` | selbstgebaute 12-V-Fläche am MOSFET-Modul | über die PWM des Pi |
| `dmx` | beliebiger Scheinwerfer am DMX-Bus | über DMX512 |
| `godox` | Leuchte von Godox | über Bluetooth, Helligkeit und Farbtemperatur |
| `none` | gekaufte Leuchte ohne Fernsteuerung | gar nicht |

Kann die Box die Helligkeit nicht ändern, verschwinden die Lichtknöpfe auf dem
Gästebildschirm und die Licht-Karte in den Einstellungen. Kann sie die
Farbtemperatur nicht ändern – alles außer `godox` –, verschwindet deren Feld.
Ein Regler, der nichts bewirkt, verwirrt mehr, als er nützt.

**Die Farbtemperatur steht hinter der PIN**, nicht auf dem Gästebildschirm. Die
Helligkeit des Einstelllichts darf jeder verstellen, sie hat auf das Foto keinen
Einfluss. Die Farbe hat einen: Der Weißabgleich ist darauf eingemessen, und wer
im Vorbeigehen daran dreht, färbt jedes Bild des Abends ein.

**Godox über Bluetooth.** Die Leuchten sind Knoten in einem Bluetooth-Mesh,
keine einfachen BLE-Geräte. Das Protokoll ist nachgebaut; `install-pi.sh` holt
die Bibliothek nach `vendor/godox-mesh` (MIT). Eingerichtet wird einmalig auf
der Kommandozeile, die Leuchte muss dabei im Kopplungsmodus sein:

```bash
cd vendor/godox-mesh
export PYTHONPATH=src
python3 -m godox_mesh_bt scan --timeout 10          # Adresse suchen

# Ohne --address: der Befehl sucht selbst und verbindet sofort danach.
python3 -m godox_mesh_bt provision --output ../../godox-mesh-state.json

# Für die nächsten Befehle muss nebenher ein Suchlauf laufen, sonst scheitern
# sie mit „device not found“ – siehe unten.
(timeout 30 bluetoothctl scan on >/dev/null &) ; sleep 6
python3 -m godox_mesh_bt rebind --device <Adresse> --state ../../godox-mesh-state.json
python3 -m godox_mesh_bt set --device <Adresse> --state ../../godox-mesh-state.json \
    --brightness 50 --cct 4000
```

Danach `light.kind` auf `godox` und `light.address` auf die Adresse setzen. Das
**ersetzt die Kopplung mit der Godox-App** – die App sieht die Leuchte erst
wieder nach einem Zurücksetzen.

Drei Dinge, die wir am Pi gelernt haben und die die Software erledigt:

- **Erst suchen, dann verbinden.** BlueZ löst eine Adresse nur auf, wenn es das
  Gerät kürzlich gesehen hat; ohne Suchlauf scheitert jeder Start mit
  „Device not found“.
- **Der Mesh-Zähler darf nie zurückfallen.** Jeder Befehl verbraucht eine
  laufende Nummer, und die Leuchte verwirft stillschweigend alles, was sie schon
  gesehen hat – ohne Fehlermeldung, sie tut dann einfach nichts. Beim Start wird
  der Zähler deshalb um 2000 vorgezogen und sofort gesichert.
- **Die Schlüsseldatei wird atomar geschrieben.** Sie enthält die Mesh-Schlüssel;
  geht sie verloren, muss die Leuchte neu eingerichtet werden. Ein Stromausfall
  mitten im Schreiben hatte sie am Pi schon einmal auf null Bytes gekürzt.

Bluetooth muss dafür eingeschaltet bleiben – `optimize-boot.sh` schaltet es
deshalb **nicht** mehr ab.

**DMX.** DMX512 ist der Standard der Veranstaltungstechnik, damit lässt sich
praktisch jeder Scheinwerfer ansteuern. Am Pi braucht es einen Wandler von TTL
auf RS-485: entweder einen USB-Adapter mit FTDI-Chip, dann steht die
Schnittstelle als `/dev/ttyUSB0` da und Bluetooth bleibt frei, oder einen MAX485
an `/dev/serial0`. Der zweite Weg ist billiger, aber die kleine UART des Pi hängt
am Kerntakt und trifft 250000 Baud nicht zuverlässig – dafür müsste die große
UART an den Stecker, und die ist ab Werk für Bluetooth reserviert. Einstellungen:
`light.dmx_port`, `light.dmx_channel`, und für Scheinwerfer, die vor dem Dimmen
einen Betriebsart-Kanal gesetzt haben wollen, `light.dmx_extra` als
`{"Kanal": Wert}`. Es sendet ein Faden im Hintergrund mit 30 Paketen je Sekunde,
denn ein DMX-Empfänger fällt ohne Nachschub nach etwa einer Sekunde auf Schwarz.
Gebraucht wird `python3-serial`, das `install-pi.sh` mitinstalliert.

### Flimmern und PWM-Frequenz

Gedimmtes PWM-Licht und eine kurze Belichtung schlagen gegeneinander: Fällt in
eine Belichtung nur eine Handvoll Lichtpulse, entscheidet der Zufall, wie viele
es sind, und der zeilenweise auslesende Sensor malt daraus Streifen ins Bild.

Am Pi 4 mit einem D4184-Modul und 6,5 ms Belichtung gemessen, Streifenstärke im
Bild bei 30 % Dimmwert:

| PWM | Streifen bei 30 % | Streifen bei 3 % | Dimmkurve |
|---|---|---|---|
| 200 Hz | 19 % | 65 % | nahezu linear |
| 1 kHz | 7 % | – | leicht gestaucht |
| **2 kHz** | **2,5 %** | **8,5 %** | 3 % Dimmwert ergeben 20 % Licht |
| 5 kHz | 2,3 % | – | 30 % ergeben 68 % |
| 10 kHz | 2,9 % | – | 30 % ergeben 94 %, kaum noch dimmbar |

**2 kHz ist die Vorgabe.** Darunter sieht man Streifen, darüber kippt das
Dimmen: Das Gate des MOSFET wird über einen Widerstand entladen, und je kürzer
die Periode, desto weniger schafft er es, ganz abzuschalten. Mit einem Modul
mit echtem Gate-Treiber wären auch 10 kHz sauber und linear. Die Dimmkurve ist
dadurch gestaucht – 5 % Dimmwert ergeben rund 22 % Licht, 30 % ergeben 51 %.

### Hardware-PWM statt Software-PWM

Das Signal erzeugt die PWM-Einheit des Chips, nicht lgpio. Der Unterschied
zeigt sich erst unter Last: lgpio zählt seine Flanken in einem Thread, und wenn
die Kerne beschäftigt sind, verrutschen sie. Am Pi 4 gemessen, Licht auf 5 %,
Helligkeit des Livebildes über je 60 Sekunden:

| | im Leerlauf | mit vier Kernen unter Volllast |
|---|---|---|
| lgpio, in Software | ±1,8 % | **Sprünge bis +20 %, alle 4 Sekunden** |
| PWM-Einheit des Chips | ±0,4 % | ±0,2 % |

Das sieht man als kurzes Aufblitzen der Leuchte, mehrmals pro Minute. Dafür
braucht es eine Zeile in der `config.txt`, die `autostart/setup.sh` einträgt:

```
dtoverlay=pwm,pin=18,func=2
```

**Eine Falle dabei:** Der Overlay legt den Pin beim Hochfahren auf die
PWM-Funktion. Belegt ihn danach irgendetwas als gewöhnlichen Ausgang – etwa der
Software-Fallback, wenn der Start einmal schiefgeht –, dann läuft die
PWM-Einheit zwar weiter, ihr Signal kommt aber nicht mehr am Pin an: Register
sauber gesetzt, Leuchte dunkel, kein Fehler im Log. `HardwarePwm` legt den Pin
deshalb bei jedem Start selbst zurück (`pinctrl set 18 a5`) und prüft nach.

Gibt es die PWM-Einheit nicht, läuft das Licht wie früher über gpiozero. Dann
steht eine Warnung im Log.

Die Aufnahme selbst ist davon nicht betroffen: Eine Sekunde vor dem Auslösen
geht das Licht auf volle Leistung, und bei 100 % gibt es kein PWM mehr.
Gemessen bleiben dann 2,6 % Streuung übrig, und das ist Bildrauschen.

**Niemals 12 V auf einen GPIO-Pin.** Die Leuchte wird ausschließlich über den
MOSFET geschaltet, und die Masse des 12-V-Netzteils muss mit der Pi-Masse
verbunden sein.

### Adressierbare LED-Kette (WS2812B)

Optional, für Status- und Countdown-Licht. **Nicht als Hauptlicht** &ndash; RGB-Pixel
mischen Weiß aus drei schmalen Spektrallinien, darunter sehen Hauttöne schlecht
aus, und ihr internes PWM schlägt gegen kurze Belichtungszeiten.

Angesteuert wird über SPI statt über die übliche DMA-Bibliothek: Das braucht
keine Root-Rechte, kollidiert nicht mit der Onboard-Audioausgabe und
funktioniert auch auf dem Pi 5.

| Signal | Anschluss |
|---|---|
| Daten (DIN) | GPIO 10, Pin 19 (SPI MOSI) |
| Masse | GND, gemeinsam mit dem Netzteil der Kette |
| 5 V | eigenes Netzteil, **nicht** aus dem Pi bei mehr als ein paar LEDs |

`install-pi.sh` schaltet SPI ein. **Pegelwandler:** WS2812B erwarten rund 3,5 V
auf der Datenleitung, der Pi liefert 3,3 V. Kurze Ketten laufen oft trotzdem,
längere flackern. Sauber wird es mit einem 74AHCT125 als Pegelwandler.

**Falsche Farben?** Wenn Rot als Grün erscheint, hat dein Streifen eine andere
Byte-Reihenfolge als GRB &ndash; dann ist es kein WS2812B, sondern ein verwandter
Typ.

### Drucker einrichten

```bash
sudo lpinfo -v | grep -i canon          # angeschlossenes Gerät samt Seriennummer
sudo lpinfo -m | grep -i selphy         # passende Treiber
sudo lpadmin -p Selphy -E \
     -v "usb://Canon/SELPHY%20CP1500?serial=<Seriennummer>" \
     -m "gutenprint.5.3://canon-cp1300/expert"
sudo lpadmin -p Selphy -o PageSize=Postcard -o StpBorderless=True -o StpImageType=Photo
sudo lpadmin -d Selphy
lpstat -p -d
```

**Der CP1500 fehlt in Gutenprint 5.3.4** – der Treiber ist älter als der
Drucker. Nimm den **CP1300**: Dieselbe Protokollfamilie (`CMD:Raster3`), und der
CP1500 druckt damit. `StpBorderless=True` ist für Fotos Pflicht, sonst bleibt ein
weißer Rand; `StpImageType=Photo` schaltet die Rasterung um.

**Die Falle, die eine Stunde kostet:** `ipp-usb` greift sich beim Einstecken
jeden USB-Drucker und sucht IPP und einen Scanner. Beim Selphy findet es beides
nicht, setzt den Drucker zurück und lässt dabei gelegentlich eine Verbindung
offen. Danach meldet `lpinfo -v` gar kein USB-Gerät mehr, der Drucker steht
trotzdem in `lsusb`, und im Log steht nur `Failed to detach "usblp" module` –
was in die falsche Richtung zeigt, denn `usblp` ist unschuldig. `install-pi.sh`
legt deshalb `/etc/ipp-usb/quirks/photobooth.conf` an:

```
[Canon SELPHY *]
  blacklist = true
```

Danach steht beim Einstecken `Device is blacklisted` im Protokoll von ipp-usb,
und CUPS bekommt den Drucker.

Die Fotobox druckt auf den **Standarddrucker** von CUPS:

```bash
sudo lpadmin -d Selphy
```

`Postcard.Fullbleed` in `config.json` (`printer.media`) ist der übliche Wert für
10×15 cm randlos beim Selphy – falls der Ausdruck beschnitten wird, hier zuerst
ansetzen. Zum Testen ein Foto machen und auf „Drucken" tippen.

## Gut zu wissen

- **PWM-Licht und kurze Belichtung schlagen gegeneinander.** Ein gedimmter
  LED-Streifen erzeugt bei kurzen Belichtungszeiten sichtbare Helligkeits-
  schwankungen von Bild zu Bild. Deshalb fährt das Licht für die Aufnahme auf
  100 % Duty, also durchgehend an statt gedimmt.
- **Kein Xenon-Blitz.** Die Pi-Sensoren haben Rolling Shutter; ein kurzer Blitz
  belichtet nur einen Teil des Bildes.
- **Aufnahmen werden im Hintergrund gespeichert.** picamera2 arbeitet eine
  Aufnahme im Takt der Oberfläche ab. Früher kodierte und schrieb es dort auch
  das JPEG; war die Speicherkarte gerade beschäftigt, stand die Oberfläche mit,
  und jede zwanzigste Aufnahme dauerte bis zu 3,5 Sekunden. Jetzt werden dort nur
  die Pixel kopiert, geschrieben wird in einem eigenen Thread, und wer die Datei
  braucht, wartet mit `wait_for_writes()` darauf.

## Autostart

`bash autostart/setup.sh` richtet alles ein, was eine Fotobox ohne Tastatur
braucht. Rückgängig mit `bash autostart/setup.sh --remove`. Dienste einer
älteren Version mit Browser-Kiosk räumt es dabei mit weg.

| Datei | Wofür |
|---|---|
| `photobooth.service` | die Fotobox im Vollbild in cage, startet bei Absturz neu |
| `photobooth-watchdog.service`, `watchdog.sh` | startet die Fotobox neu, wenn die Oberfläche hängt |
| `hide-cursor.py` | unsichtbarer Mauszeiger, für Touchscreens, die sich als Maus melden |
| `photobooth-touch.service`, `touch-bridge.py` | Touchscreens, die sich als Maus melden |
| `99-photobooth-usb.rules`, `usb-mount.sh` | USB-Stick ohne Desktop einhängen |
| `50-photobooth-journal.conf` | Systemprotokoll überlebt einen Neustart |
| `optimize-boot.sh` | kürzerer Start, rückgängig mit `--undo` |

## Aufbau

```
photobooth.py               Einstiegspunkt
config.json                 alle veränderbaren Werte
install-pi.sh               Pakete, SPI
set-pin.sh                  PIN für die Einstellungen neu setzen
booth/
  backend.py                setzt Kamera, Ablauf, Upload und Sicherung zusammen
  session.py                Ablauf einer Aufnahme
  layouts.py, overlays.py   Collagen, Rahmen, Schriften
  eventpics.py              Upload und QR-Code je Bild
  usb.py, journal.py        Sicherung auf dem Stick, Warteschlange
  admin.py                  PIN und die Felder der Einstellungen
  hardware/                 Kamera (picamera2), GPIO (gpiozero/lgpio), LED-Kette,
                            Drucker (CUPS), Systemwerte - jeweils mit Simulation
  ui/                       die Oberfläche: Gäste, Einstellungen, Tastatur, PIN
autostart/                  Autostart, Wächter, Touch, USB, Startzeit
tools/stress_test.py        Stresstest mit echter Kamera
docs/                       Entscheidungen und ihre Gründe
captures/                   aufgenommene Bilder
```

RPi.GPIO wird bewusst nicht verwendet – es funktioniert auf dem Pi 5 nicht.
gpiozero greift dort auf lgpio zu.

## Sprache

Quelltext, Kommentare und Dateinamen sind englisch. Deutsch ist, was Gäste und
Nachbauer lesen: die Oberfläche, die Meldungen auf dem Schirm, die Beschriftungen
der Einstellungen und die Bauanleitung. Gespeicherte Werte und Optionsnamen sind
englisch, ihre Beschriftungen deutsch.

## Lizenz

GPL-3.0-or-later, siehe [LICENSE](LICENSE).

Du darfst die Software für alles verwenden, auch gewerblich. Wer sie verändert
und weitergibt, muss seinen Quelltext unter derselben Lizenz offenlegen. Genau
darum geht es: Ein Fotobox-Verleih darf darauf aufbauen, aber kein geschlossenes
Produkt daraus machen, bei dem der EventPics-Upload stillschweigend fehlt.

Die Bibliothek unter `vendor/godox-mesh` holt `install-pi.sh` und sie ist nicht
Teil dieses Repositorys. Sie hat ihre eigene MIT-Lizenz.
