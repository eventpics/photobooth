# Fotobox selber bauen

Diese Anleitung beschreibt genau die Box auf den Bildern: eine Holzkiste mit
Touchscreen, Kamera, Leuchte und Drucker, auf einem Lautsprecherständer. Sie
nimmt auf, zeigt das Ergebnis, druckt es und lädt es auf Wunsch in eine
EventPics-Galerie. Bedient wird sie nur an ihrem eigenen Bildschirm.

Alle Teile heißen hier so, wie sie auch in der Software und in den Zeichnungen
heißen, also englisch: `front`, `door`, `shelf`, `pi mount`, `iec inlet`.

![Die fertige Box auf dem Ständer](images/booth-on-stand.jpg)

## Was dabei herauskommt

| | |
|---|---|
| Gehäuse | 410 × 290 × 180 mm, Eiche massiv 15 mm |
| Bildschirm | 15,6 Zoll, Touch, bündig in der Front |
| Kamera | Raspberry Pi Camera Module 3, schaut durch ein Loch Ø 8 mm |
| Rechner | Raspberry Pi 4B, liegt auf einem 3D-Druckteil |
| Licht | Godox LP400Bi auf dem Deckel |
| Druck | Canon Selphy CP1500 auf einer Ablage am Ständer |
| Strom | ein einziges Kaltgerätekabel in die Box |
| Aufbauzeit | etwa zehn Minuten |

![Die Box von vorn](images/booth-front.jpg)
![Die Box von der Seite](images/booth-side.jpg)

Die Box ist absichtlich schmal und hoch gebaut. Sie steht auf einem Ständer,
nicht auf einem Tisch, und muss zwischen zwei Veranstaltungen in ein Auto
passen.

## Stückliste

Preise vom November 2026, ohne Versand. Bildschirm, Pi, Kamera und Drucker sind
nicht von Amazon, der Rest schon.

### Rechner, Kamera, Bildschirm

| Teil | Was ich verbaut habe | Preis |
|---|---|---|
| `raspberry pi` | Raspberry Pi 4B, bei mir mit 1 GB. **Nimm 2 GB oder mehr**, mit 1 GB läuft es, aber ohne Luft nach oben | ca. 45 € |
| `camera` | Raspberry Pi Camera Module 3 Standard (75°), mit langem Flachbandkabel | ca. 30 € |
| `screen` | Waveshare 15,6″ Einbau-Display mit HDMI und kapazitivem Touch, BerryBase Art. 18207 | 159,58 € netto |
| Speicher | microSD 32 GB, schnelle Karte. Eine lahme Karte kostet beim Start Sekunden | ca. 12 € |
| `psu 5 V` | originales Raspberry-Pi-Netzteil USB-C, 5 V / 3 A | ca. 10 € |
| `psu 12 V` | Netzteil des Displays, liegt dem Panel bei | im Preis |

### Licht

| Teil | Was ich verbaut habe | Preis |
|---|---|---|
| `light` | Godox LP400Bi, 36 W, 2800 bis 6500 K, CRI ≥ 96, dimmbar, App-Steuerung | 89,00 € |
| `light mount` | NEEWER Wand- und Deckenhalterung mit 5/8″-Zapfen und 1/4″-Gewinde | 22,31 € |

### Druck

| Teil | Was ich verbaut habe | Preis |
|---|---|---|
| `printer` | Canon Selphy CP1500, Thermosublimation, 10 × 15 cm | ca. 150 € |
| Papier | Canon KP-108IN, 108 Blatt mit Farbband | ca. 35 € |
| `usb cable` | SUNGUY USB 3.0 A auf A, 0,3 m, vom Pi zur Einbaubuchse | 6,41 € |

### Ständer und Ablage

| Teil | Was ich verbaut habe | Preis |
|---|---|---|
| `stand` | GZGDLJQ Boxenständer, 89 bis 180 cm, Rohr 35 mm, bis 30 kg | 25,99 € |
| `pole flange` | Drall AD8BA Boxenflansch zum Anschrauben, für 35 mm | 13,20 € |
| `shelf screw` | Schraube M8 × 90 mit Flügelmutter und zwei Scheiben | ca. 2 € |

### Elektrik

| Teil | Was ich verbaut habe | Preis |
|---|---|---|
| `iec inlet` | Powice IEC-C14-Einbaubuchse 10 A mit Schalter und Sicherung, 2 Stück | 11,48 € |
| `power cord` | deleyCON Kaltgerätekabel C13 auf Schuko, 3 m | 9,78 € |
| `socket` | Schuko-Einbausteckdose, weiß, für den Drucker | ca. 6 € |
| `junction box` | Hohlwanddose Ø 68 mit Steckklemme, 5-polig | ca. 4 € |
| `usb coupler` | Duttek USB-Einbaukupplung, 2-fach, IP67 | 9,59 € |
| `power pigtail` | Leloco Eurokupplung flach mit 20 cm Kabel, 2 Stück | 6,99 € |
| `cable gland` | Verschraubung M20 für das Kabel zur Leuchte | ca. 3 € |

### Holz und Beschläge

| Teil | Was ich verbaut habe | Preis |
|---|---|---|
| Holz | Eiche massiv, 15 mm, etwa 0,6 m² | je nach Quelle |
| `hinge` | Wandefol Aufschraubscharnier mit Feder, 90°, 8 Stück im Satz | 13,99 € |
| `cam lock` | MUXHEL Möbelschloss Ø 19 mm zum Aufschrauben, Satz | ca. 10 € |
| `vent` | Lüftungsgitter 60 × 60 mm aus Metall | ca. 5 € |
| `pi mount` | 3D-Druckteil, Datei in dieser Anleitung | Filament |

Zusammen liegt das bei etwa **650 bis 700 Euro ohne Holz und ohne Papier**. Der
größte Posten ist der Bildschirm, der zweitgrößte der Drucker.

## Werkzeug

Tischkreissäge oder eine saubere Handkreissäge mit Schiene, Oberfräse für die
Tasche hinter dem Bildschirm, Bohrmaschine, Forstnerbohrer Ø 19 für das Schloss
und Ø 68 für die Dose, Stichsäge für den Bildschirmausschnitt, Schrauben
4 × 30, Leim, Schleifpapier, Hartwachsöl. Für die Elektrik eine Abisolierzange
und ein Spannungsprüfer.

## Das Gehäuse

![Zeichnung des Gehäuses](drawing-enclosure.svg)

Außen 410 × 290 × 180 mm, Holz überall 15 mm. Die Tiefe von 180 mm ist mit der
Tür gerechnet: Rahmen 150, Front 15, Tür 15.

**Der Ausschnitt für den Bildschirm gehört zu deinem Panel, nicht zu meinem.**
Miss das eigene Display aus, bevor du sägst. Bei mir sind es 330 × 196 mm, mit
40 mm Rand links und rechts, 57 mm oben und 37 mm unten. Von hinten ist die
Tasche 9 mm tief ausgefräst, damit das Glas bündig in der Front steht und kein
Rand übersteht, an dem Gäste hängen bleiben.

![Breite der Front, 410 mm](images/front-width.jpg)
![Höhe der Front, 290 mm](images/front-height.jpg)

Das Kameraloch sitzt mittig, 39 mm unter der Oberkante, und hat Ø 8 mm. Von
vorn ist es leicht angesenkt, damit das Objektiv frei schaut und die Kante
nicht ins Bild spiegelt. Bohre erst, wenn die Kamera da ist, und halte sie
vorher von innen an.

Die Tür geht über die ganze Rückseite und hängt an zwei Aufschraubscharnieren.
Innen halten zwei Querleisten das Brett gerade, oben sitzt ein Lüftungsgitter
60 × 60 mm, und ein Möbelschloss Ø 19 hält sie zu. Hinter der Tür liegt alles,
was niemand im Betrieb anfassen soll.

![Die Tür von innen](images/door-inside.jpg)
![Die Rückseite mit Gravur](images/back-panel.jpg)

Die Gravur auf der Tür ist Zierde und kein Muss. Wer eine Fräse hat, nimmt die
Vorlagen aus dem Repository, wer keine hat, lässt sie weg.

## Boden, Flansch und Ständer

In den Boden kommen vier Dinge: der Flansch für das Rohr, die
Kaltgerätebuchse mit Schalter, die Schuko-Steckdose für den Drucker und die
doppelte USB-Einbaubuchse.

![Der Boden der Box](images/bottom-panel.jpg)

Der Flansch wird mit vier Schrauben von außen verschraubt. Er trägt die ganze
Box, also schraube ihn in die volle Materialstärke und nicht in eine dünne
Platte. Das Rohr des Ständers steckt von unten hinein und wird mit der
Flügelschraube am Flansch geklemmt.

![Flansch für das Rohr](images/pole-flange.jpg)
![Buchsen im Boden](images/bottom-connectors.jpg)

Ein einziges Kabel geht in die Box, das Kaltgerätekabel. Der Schalter an der
Buchse ist der Hauptschalter der ganzen Box, die Sicherung sitzt gleich daneben.

![Stecker am Boden](images/inlet-plugged.jpg)

## Die Ablage für den Drucker

![Zeichnung der Ablage](drawing-shelf.svg)

Die Ablage ist ein Brett 400 × 210 mm mit zwei Leisten darunter, die eine Gabel
bilden. Hinten schließt ein Klotz die Gabel, vorn geht eine Schraube M8 × 90
durch beide Leisten, mit einer Flügelmutter darauf.

Das Rohr des Ständers misst 35 mm, die Gabel 37 mm. Die Ablage wird einfach auf
das Rohr geschoben, auf die gewünschte Höhe gebracht und mit der Flügelmutter
festgezogen. Kein Werkzeug, und die Höhe lässt sich am Veranstaltungsort noch
ändern.

![Die Ablage von oben](images/shelf-top.jpg)
![Die Ablage von unten mit Klemme](images/shelf-underside.jpg)
![Die Breite der Ablage, 210 mm](images/shelf-width.jpg)
![Klotz und Gabel von unten](images/shelf-clamp.jpg)
![Die Klemme am Rohr](images/shelf-on-pole.jpg)

Der Drucker steht lose darauf. Für den Transport nimmt man ihn herunter, die
Ablage bleibt am Rohr.

![Der Drucker auf der Ablage](images/printer-on-shelf.jpg)

## Der Einbau

![Zeichnung des Innenausbaus](drawing-interior.svg)

Alles Schwere hängt an einer Querleiste oben, nichts an der Rückwand des
Bildschirms. So lässt sich das Display später ausbauen, ohne dass der halbe
Innenraum mitkommt.

![Blick in die offene Box](images/inside-overview.jpg)

Von links nach rechts: das Netzteil des Pi, die Kamera auf ihrer Scheibe, der
Pi auf dem Druckteil, das Netzteil des Displays. Unten links die Verteilerdose,
daneben die Durchführung für das Kabel zur Leuchte.

![Der Innenraum von hinten](images/inside-from-back.jpg)

### Das Druckteil für den Pi

![Das Druckteil](images/pi-mount.png)

**Datei: [pi-mount.stl](pi-mount.stl)**

Eine Platte 108 × 66 × 3 mm mit vier Pfosten im Lochbild des Raspberry Pi
(58 × 49 mm), zwei Durchgangslöchern Ø 4,5 mm für die Holzschrauben und einem
Fenster in der Mitte für Luft und Kabel. Gesamthöhe 11,6 mm.

Gedruckt mit 0,2 mm Schichthöhe, drei Außenlinien, 20 % Füllung, ohne Stützen.
PLA reicht, PETG ist in einer Box, die in der Sonne im Auto steht, die
sicherere Wahl.

Der Pi liegt waagrecht darauf, die Anschlüsse zeigen nach unten zur Tür. So
kommt man im Notfall an HDMI und USB, ohne etwas auszubauen.

![Der Pi auf dem Druckteil](images/pi-on-mount.jpg)

### Kamera

![Das Kameramodul](images/camera-module.jpg)

Das Modul sitzt auf einer kleinen Scheibe hinter dem Loch in der Front. Das
Flachbandkabel ist empfindlich: nicht knicken, nicht spannen, und den Stecker am
Pi erst schließen, wenn das Band gerade liegt. Zwischen Kamera und
Bildschirmrückseite muss Luft bleiben, sonst sieht die Kamera später ihre eigene
Halterung im Bild.

### Netzteile und Kabel

![Die Netzteile](images/power-supplies.jpg)

Beide Netzteile liegen auf der Querleiste und sind mit einem Kabelbinder
gesichert. Für die Kabel sind kleine Kerben in die Leisten gefeilt, damit nichts
gequetscht wird, wenn die Tür zugeht.

![Kerbe für das Kabel](images/cable-groove.jpg)

## Strom und Kabel

![Kabelplan](drawing-wiring.svg)

> **230 Volt.** Was hinter der Kaltgerätebuchse liegt, ist Netzspannung in
> einer Holzkiste, die Gäste anfassen. Wenn du dir dabei nicht sicher bist,
> lass diesen Teil von jemandem machen, der es gelernt hat. Alle Klemmstellen
> gehören in die geschlossene Dose, keine freien Litzen, keine Lüsterklemme auf
> dem Boden der Box, und der Schutzleiter wird nirgends unterbrochen.

![Die Verteilerdose](images/junction-box.jpg)

Der Weg ist kurz: Kaltgerätebuchse mit Schalter und Sicherung, von dort in die
Verteilerdose mit der Steckklemme, und von der Dose aus an die Schuko-Steckdose
im Boden, an die beiden Netzteile und durch die M20-Verschraubung im Deckel zur
Leuchte.

Die Daten laufen getrennt davon: HDMI vom Pi zum Display, ein USB-Kabel zurück
für den Touch, das Flachband zur Kamera, und ein kurzes USB-Kabel vom Pi zur
Einbaubuchse im Boden. Dort steckt im Betrieb der Drucker, und daneben der
USB-Stick für die Sicherung.

## Die Leuchte

![Die Leuchte auf dem Deckel](images/light-mount.jpg)

Auf dem Deckel sitzt die Halterung mit 5/8-Zoll-Zapfen, darauf die Leuchte. Das
Panel lässt sich kippen, der Winkel bleibt stehen.

Die Leuchte ist bewusst nicht an der Box angeschraubt, sondern nur aufgesteckt.
Für den Transport kommt sie ab, und beim Aufbau wird sie zuletzt aufgesetzt.

In den Einstellungen der Box steht unter `light.kind`, wie die Leuchte
angesteuert wird. Bei einer Godox über Bluetooth ist das `godox`, bei einer
Leuchte, die nur von Hand gedimmt wird, `none`. Die Software blendet dann alle
Regler aus, die nichts bewirken würden.

## Die Software auf den Pi

### Image schreiben

Empfohlen ist **Raspberry Pi OS Lite (64-bit)**, geschrieben mit dem Raspberry
Pi Imager. Im Imager vor dem Schreiben auf das Zahnrad gehen und gleich setzen:

- Rechnername, zum Beispiel `fotobox`
- Benutzername und Passwort
- SSH einschalten
- WLAN deines Arbeitsplatzes eintragen, damit die Box beim ersten Start erreichbar ist

Der Desktop wird nicht gebraucht. Die Oberfläche der Box ist ein eigenes
Qt-Programm und startet ohne Desktop.

### Software holen und einrichten

Am Pi, über SSH oder mit Tastatur:

```bash
sudo apt update && sudo apt install -y unzip
curl -LO https://event.pics/downloads/EventPics-Photobooth-v0.7.0.zip
unzip EventPics-Photobooth-v0.7.0.zip
cd eventpics-photobooth
bash install-pi.sh
bash autostart/setup.sh
sudo reboot
```

`install-pi.sh` holt die Pakete aus den Quellen von Raspberry Pi OS, nichts über
pip: picamera2 und PySide6 sind dort passend für den Pi gebaut. `autostart/setup.sh`
richtet den Start beim Einschalten ein, den Touch, das Einhängen des USB-Sticks
und fragt nach der **PIN für die Einstellungen**. Die vier Ziffern merken, sie
sind später der einzige Weg in die Einstellungen.

Nach dem Neustart steht die Fotobox auf dem Bildschirm.

Wer die Software aus dem Repository nimmt statt aus dem ZIP:

```bash
git clone https://github.com/eventpics/photobooth.git eventpics-photobooth
```

### Nützlich im Betrieb

```bash
systemctl status photobooth
journalctl -t photobooth -f
sudo systemctl restart photobooth
```

## Die Box einrichten

Alles Weitere passiert am Bildschirm der Box, hinter dem Zahnrad und der PIN.

1. **WLAN.** Netz auswählen, Passwort auf der Tastatur eingeben. Die Box merkt
   sich das Netz.
2. **Drucker.** Den Selphy anstecken und einschalten, dann in den Einstellungen
   suchen lassen. Der Selphy meldet sich als USB-Drucker, nicht im Netz.
3. **Einmessen.** Stell jemanden dorthin, wo später die Gäste stehen, mach das
   Licht wie am Abend und tippe auf „Automatisch einmessen". Die Box sucht sich
   das Aufnahmelicht, misst Belichtung, Weißabgleich und Fokus und gleicht zum
   Schluss die Aufnahme an die Vorschau an. Das dauert etwa zwölf Sekunden.
4. **EventPics.** Den API-Schlüssel des Events per QR-Code vor die Kamera
   halten oder als Datei auf dem USB-Stick einlesen. Danach Event und Album
   auswählen.
5. **USB-Stick.** Einen Stick anstecken, die Box legt dort jede Aufnahme ab.
   Das ist die Sicherung, die auch ohne Netz funktioniert.

Die Einzelheiten zu jedem Punkt stehen in der [README](../README.de.md).

## WLAN unterwegs

Zum Hochladen braucht die Box Internet, und das WLAN des Veranstaltungsorts ist
selten brauchbar: ein Gästenetz mit Anmeldeseite, ein Passwort, das niemand
weiß, oder gar nichts. Darum gehört ein kleiner **travel router** ins Gepäck.

So sieht der Weg aus:

- Der Router baut ein eigenes WLAN auf, immer mit demselben Namen und demselben
  Passwort. Die Box kennt dieses Netz und verbindet sich beim Einschalten von
  selbst, egal wo sie steht.
- Der Router holt sich das Internet, wie er es gerade bekommt: über ein LTE-Modem
  mit eigener SIM, über ein Netzwerkkabel am Veranstaltungsort oder über das
  Gäste-WLAN, bei dem er die Anmeldeseite für alle einmal erledigt.
- Fällt das Internet aus, läuft die Box trotzdem weiter. Aufnehmen, Drucken und
  Sichern brauchen kein Netz, die Uploads stehen in der Warteschlange und gehen
  los, sobald wieder eine Verbindung da ist.

Meine Box hat den Router noch nicht. Wer ihn gleich mitplant, legt ihn zum
Drucker auf die Ablage und hängt ihn an die Schuko-Steckdose im Boden. Ein
Gerät mit eigenem Akku ist dabei angenehmer als eins mehr am Strom.

Ohne Router geht es auch: der Hotspot eines Telefons tut dasselbe, nur muss ihn
jemand einschalten, und der Name des Netzes ändert sich schnell einmal.

## Aufbauen und abbauen

**Aufbauen**, in dieser Reihenfolge:

1. Ständer aufstellen, Beine weit auseinander, auf festem Boden
2. Box aufsetzen und am Flansch klemmen
3. Ablage auf das Rohr schieben, Höhe wählen, Flügelmutter anziehen
4. Drucker darauf, Papier und Farbband einlegen
5. Leuchte aufstecken und ausrichten
6. Kaltgerätekabel anstecken, Schalter an
7. Einmessen, Probebild, fertig

**Abbauen** ist dieselbe Liste rückwärts. Den Drucker nie mit eingelegtem Papier
transportieren, und die Box nie am Bildschirm anheben.

## Mitmachen

Die Software steht unter der MIT-Lizenz im Repository
<https://github.com/eventpics/photobooth>. Zeichnungen, Druckteil und diese
Anleitung liegen im selben Repository unter `docs/`.

Wenn du die Box nachbaust und etwas anders löst, freue ich mich über einen
Hinweis. Besonders über Maße, die bei dir besser passen als meine.
