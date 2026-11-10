# Zwei Ausgaben: Bastler und Vermietung

Stand: Oktober 2026, geplant — noch nichts davon gebaut

Die Software, an der gearbeitet wird, ist **die für die Bastler**: Wer die
Anleitung auf event.pics nachbaut, lädt dieses ZIP und bekommt eine Box, die
ihm gehört. Daran ändert sich nichts.

Daneben soll später eine zweite Ausgabe entstehen, für die Boxen, die als
Mietgeräte verschickt werden. Die Unterschiede sind nicht kosmetisch, deshalb
steht hier, was sie ausmacht — damit die Trennung später nicht aus Versehen
entsteht.

## Was die Mietausgabe anders macht

**Feste Boxnummer.** Jedes Gerät hat eine Nummer, die nicht verstellt werden
kann. Sie steht in jedem Protokoll und in jeder Meldung nach Hause. Der Grund
ist Logistik: Ein Fulfilment-Betrieb führt keine Seriennummern (bei elogix etwa
gibt es nur Chargen und Haltbarkeiten). Wenn die Box selbst weiß, wer sie ist,
braucht sie das vom Lager nicht.

**Fernwartungskanal.** Die Box hat eine SIM-Karte und meldet sich laufend —
nicht erst beim Herunterfahren. Ein Bericht beim Abschalten ist genau der, den
man nicht bekommt, wenn es darauf ankommt: Stirbt die Box, sendet sie nie.
Also laufend senden, und „letztes Lebenszeichen" ist der Befund.

Inhalt ist das, was es schon gibt: Ereignisprotokoll (Leuchte verloren und
wieder verbunden, Drucker an- und abgesteckt, Touchscreen weg), dazu Zustand
— Kamera, Temperatur, Speicher, Platte, Laufzeit und `vcgencmd get_throttled`,
das auch rückwirkend sagt, ob Unterspannung anlag.

**Weniger Einstellungen.** Der Mieter soll Beschriftung, Aufteilung und
Hintergrund wählen können. Kamerawerte, Lichtart, DMX-Kanal, Tonausgang und
der ganze Bereich „Erweitert" gehören ihm nicht.

**PIN je Kunde.** Wird aus der Ferne für jede Vermietung neu gesetzt, nicht
beim Einrichten der Box festgelegt.

## Das EventPics-Paket

Zu jeder Vermietung gehört ein Paket von **70 GB für drei Monate**. Der Kunde
schaltet es frei, indem er einen QR-Code auf der Fotobox scannt; darin steht
ein eindeutiger Token, der vorher in der Datenbank gesetzt wurde.

Die 70 GB sind mit Absicht eine Größe, die man bei EventPics nicht kaufen
kann. Damit sind Fotoboxkunden in den Daten eindeutig zu erkennen, und
Missbrauch fällt auf — ein Konto mit genau diesem Paket, das nie an einer Box
war, stimmt nicht.

## Was gemeinsam bleibt

Kamera, Ablauf, Blattaufbau, Drucker, Lichtansteuerung, USB-Journal: alles,
was die Box zur Fotobox macht. Die Mietausgabe soll kein zweiter Quellbaum
werden, sondern dieselbe Software mit einem anderen Profil — sonst pflegt man
zweimal dieselben Fehler.

## Offen

Wie die Trennung technisch aussieht (Konfigurationsprofil, eigener Zweig,
Bauschalter), ist noch nicht entschieden. Erst wenn es die erste Mietbox
wirklich gibt.
