# Zugang zum Einstellbereich — Stand der Überlegung

Stand: 16.09.2026 (zuerst 10.09.2026). Diese Notiz hält fest, **warum** es
zurzeit nur eine feste PIN gibt, damit die Frage nicht in einem Jahr von vorn
diskutiert wird.

## Wie es heute ist

Eine vierstellige PIN, im Klartext in `config.json`.

- **Beim Einrichten** fragt `autostart/setup.sh` nach der PIN, solange noch die
  Voreinstellung `1234` gilt. Keine Box geht so versehentlich mit einer PIN in
  Betrieb, die in jeder Anleitung steht.
- **Vergessen?** `bash set-pin.sh` auf der Konsole des Pi setzt eine neue PIN,
  ohne die alte zu kennen. Das Skript hält den Dienst dafür kurz an: Der
  laufende Server hält die Einstellungen im Speicher und würde die neue PIN beim
  nächsten Speichern sonst mit der alten überschreiben.

**Bis 16.09.2026** gab es zusätzlich eine Zurücksetzung über eine Datei auf
einem USB-Stick, gültig zehn Minuten nach dem Einschalten, mit einem Hinweis
dazu auf dem Anmeldebildschirm. Beides ist entfernt. Der Weg über die Konsole
setzt dieselbe Nähe zur Box voraus, braucht aber keine Anleitung auf dem
Bildschirm, die jeder Gast lesen kann.

## Warum keine Hashes, kein Recovery-Code, keine signierten Dateien

Drei Gründe, in dieser Reihenfolge.

**Die eigentliche Grenze ist das Betriebssystem, nicht die Anwendung.** Auf dem
Testgerät steht es so:

    Autologin        fotobox        Desktop startet ohne Passwort
    Kiosk-Sperre     keine
    sudo für fotobox ja
    SSH              aktiv

Wer eine Tastatur ansteckt, hat in Sekunden den EventPics-Schlüssel und über
`sudo` das ganze System. Ein signiertes Reset-Verfahren darüber wäre eine
Panzertür in einer Wand aus Pappe. **Zuerst kommt die Kiosk-Absicherung**:
eigener Benutzer ohne `sudo`, kein Desktop, nur die Fotobox im Vollbild. Alles
andere ist bis dahin Zierrat.

**Eine gehashte vierstellige PIN schützt nichts.** Vier Ziffern sind 10 000
Möglichkeiten. Nachgemessen: **2,8 Millisekunden**, um alle durchzuprobieren.
Wer die Datei lesen kann, hat die PIN — ob gehasht oder nicht. Für einen langen
zufälligen Recovery-Code gilt das nicht; dort wäre ein Hash sinnvoll.

**Die Box gehört zurzeit einer Person.** Sie wird nicht vermietet, sondern vom
Eigentümer selbst zu Veranstaltungen mitgenommen. Der Bedrohungsfall „Gast auf
der Feier greift den Einstellbereich an" ist abgedeckt: Ohne PIN und ohne
Konsole kommt er nicht hinein.

## Was tatsächlich schützenswert ist

Nicht die Kameraeinstellungen — die sind Ärgernis, kein Schaden. Der Wert ist
der **EventPics-API-Schlüssel**: Damit kann jemand in *jedes* Event des Kontos
hochladen, nicht nur in das eingestellte. Deshalb steht er im Einstellbereich
nur maskiert, und `config.json` hat inzwischen `600`.

## Wenn vermietet wird, ändert sich der Bedrohungsfall

Dann ist der Betreiber nicht der Nutzer, und der Mieter hat tagelang physischen
Zugriff. Dafür sind zwei Dinge nötig, in dieser Reihenfolge:

1. **Rücksetzen zwischen den Vermietungen.** Ein Skript, das PIN, API-Schlüssel,
   Bilder und Protokoll auf Auslieferungszustand bringt. Das löst „nach zehn
   Vermietungen kennen zehn Kunden die PIN" — kein Recovery-Verfahren tut das.
   Und ohne dieses Skript bekommt der nächste Kunde die Fotos des vorigen mit.
2. **Signierte Reset-Dateien.** Deren Vorteil ist *nicht* höhere kryptografische
   Stärke — gegenüber einem langen Zufallsgeheimnis sind sie gleich stark,
   solange die Datei nicht durch fremde Hände muss. Ihr echter Vorteil ist
   **ein privater Schlüssel für viele Boxen**: Bei zehn Geräten im Umlauf will
   niemand zehn Geheimnisse verwalten.

## Für die kostenlose DIY-Software

Ein Recovery-Code bei der Ersteinrichtung (Variante 1) wäre die passende
Ergänzung — offline, ohne Server, ohne zweites Werkzeug. Mit einer Auflage: Der
Code muss im Einstellbereich jederzeit wieder anzeigbar sein, solange man noch
angemeldet ist, und auf den USB-Stick schreibbar. Sonst ist er genau das, was
man verliert, und man merkt es erst, wenn man ihn braucht.

Signierte Dateien gehören dort **nicht** hin: Sie verlangen ein zweites
Programm auf einem Rechner, das gebaut, dokumentiert und unterstützt werden
müsste — für einen Bedrohungsfall, den die fehlende Kiosk-Absicherung ohnehin
offen lässt.

## Entscheidung

Vorerst bleibt es bei der einen PIN. Wieder aufzugreifen, sobald das erste Gerät
vermietet wird — dann in der Reihenfolge: Kiosk-Absicherung, Rücksetz-Skript,
Recovery-Code, signierte Dateien.
