# Warum die Oberfläche kein Browser mehr ist

Stand: September 2026, Version 0.7.0

Bis Version 0.6 bestand die Fotobox aus zwei Teilen: einem Webserver (Flask)
mit Kamera und Ablauf, und Chromium im Vollbild, der die Oberfläche als Webseite
anzeigte. Seit 0.7 ist die Oberfläche ein eigenes Programm mit Qt (PySide6), und
es gibt keinen Server mehr.

## Die Gründe

**Wer die Adresse kannte, konnte mitbedienen.** Auslösen, Behalten, Verwerfen und
Drucken nahmen Befehle von jedem Gerät im Netz an, ohne PIN. Auf einer Feier
steht die Box oft im selben WLAN wie die Gäste. Jemand, der nicht vor der Box
steht, konnte in eine laufende Aufnahme hineinfunken. Eine Sperre auf
„nur vom Gerät selbst“ half dagegen, machte die Fernbedienung aber ohnehin
nutzlos – dann braucht es auch den Server nicht.

**Der Browser war der teuerste Teil der Box.** Das Livebild kam als JPEG-Strom:
die Kamera kodierte jedes Bild, Chromium dekodierte es wieder und zeichnete es.
Gemessen auf dem Pi 4 mit 1 GB (siehe decision-hardware.md): mit Chromium 80 bis
100 % CPU und bis zu 790 MB belegt, ohne ihn 6 %.

Jetzt zeichnet picamera2 die Kamerabilder über OpenGL direkt auf den Bildschirm
(`QGlSide6Picamera2`, ohne Umkopieren). Gemessen im ersten Versuch auf demselben
Pi 4: 27,6 Bilder je Sekunde bei rund 7 % CPU für die ganze Box, die fertige
Oberfläche mit Galerie und Zustandsabfrage im Leerlauf um 20 % eines Kerns.

**Ein Programm statt drei.** Server, Kiosk-Browser, Browser-Regeln, unsichtbarer
Mauszeiger und ein Wächter, der per HTTP prüfte, ob die Seite noch lebt – das
waren fünf Stellen, an denen etwas schiefgehen konnte. Übrig sind die App in
cage, die Touch-Brücke und ein Wächter, der einen Zeitstempel liest.

## Was dabei anders geworden ist

- **Das Livebild gibt es nur einmal.** Es wandert zwischen Startbildschirm und
  Einstellungen hin und her, statt zweimal geöffnet zu werden. Auf dem Pi
  getestet: das Umhängen kostet nichts und funktioniert auch in der scrollbaren
  Einstellungsseite.
- **Nichts, was auf die Kamera wartet, läuft im Oberflächen-Thread.** picamera2
  liefert seine Bilder über die Ereignisschleife von Qt. Eine Aufnahme oder
  Messung aus diesem Thread würde auf sich selbst warten. Aufnahme, Testfoto,
  Einmessen, QR-Erkennung, Upload und Druck laufen in eigenen Threads.
- **Aufnahmen laufen zur Hälfte im Oberflächen-Takt.** picamera2 schaltet dort
  in den Aufnahmemodus und holt das Bild. Kodieren und Schreiben des JPEG liegen
  deshalb in einem eigenen Thread: Im Stresstest auf dem Pi 4 brauchte das
  Speichern bei beschäftigter Karte bis zu 2 Sekunden, und solange stand die
  Oberfläche. Seitdem höchstens 0,36 s vom Auslösen bis zum nächsten Schritt
  (72 Aufnahmen, vorher 4 von 99 über 0,8 s).
- **Eine Bildschirmtastatur.** Im Browser ließen sich Titel und
  EventPics-Schlüssel nur über Umwege eingeben (Telefon, USB-Stick). Jetzt tippt
  man sie am Touchscreen.
- **Der Wächter liest einen Zeitstempel.** Die App schreibt alle fünf Sekunden
  aus dem Takt ihrer Oberfläche nach `/dev/shm/photobooth-alive`; ist er älter
  als eine Minute, startet `watchdog.sh` sie neu. Vorher fragte das Skript per
  HTTP, ob der Browser noch Anfragen stellt. Der eingebaute Watchdog von systemd
  (`WatchdogSec`) wäre einfacher gewesen, funktioniert hier aber nicht: die App
  läuft in der Anmeldesitzung von cage, und systemd ordnet ihre Meldungen nicht
  dem Dienst zu. Auf dem Pi ausprobiert – er startete die Box jede Minute neu.
- **Keine eigene Python-Umgebung.** PySide6, picamera2 und PyOpenGL kommen aus
  den Paketquellen von Raspberry Pi OS. Flask war der einzige Grund für die
  virtuelle Umgebung.

## Was verloren ging

Die Einstellungen lassen sich nicht mehr von einem Laptop oder Telefon aus
öffnen. Das war Absicht: bedient wird die Box an ihrem Bildschirm, und wer dort
steht, hat sie ohnehin in der Hand. Für die Arbeit an der Software läuft die App
am Rechner im Fenster mit simulierter Kamera (`photobooth.py --window`).
