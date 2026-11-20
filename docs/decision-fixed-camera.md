# Kameraeinstellungen bleiben fest — Stand der Überlegung

Stand: 11.09.2026.

## Die Entscheidung

Belichtung, Weißabgleich und Fokus werden **vor der Veranstaltung einmal
eingemessen** und bleiben dann, bis jemand sie ändert. Die Kamera regelt
nichts selbst nach.

## Warum nicht automatisch

Eine Automatik regelt auf das, was gerade im Bild ist. Bei einer Fotobox ist
das mal ein dunkler Anzug, mal ein weißes Brautkleid, mal fünf Leute dicht
gedrängt. Jedes Bild sähe anders aus als das vorige — und ein Streifen aus
vier Aufnahmen, in dem jede Aufnahme eine andere Hauttonfarbe hat, ist
unbrauchbar. Feste Werte liefern denselben Look den ganzen Abend.

Dazu kommt: Die Beleuchtung an einer Fotobox ist **gemacht**, nicht
vorgefunden. Das Aufnahmelicht schaltet sich für den Auslöser ein. Genau
darauf wird eingemessen — und genau das ändert sich während des Abends nicht.

## Was daraus folgt

**Eingemessen wird unter dem Licht, unter dem später fotografiert wird.**
Deshalb fährt die Messung das Aufnahmelicht hoch. Ein Abgleich bei Ruhelicht
ergäbe Werte, die beim ersten Blitz nicht mehr stimmen.

**Die Werte gelten nur für diesen Raum und diese Tageszeit.** Wer nachmittags
bei Tageslicht einmisst und abends im Saal fotografiert, bekommt zu dunkle
Bilder — und umgekehrt ein weißes Nichts. Das ist kein Fehler der Software,
sondern die Kehrseite fester Werte.

**Das Livebild sieht dann auch falsch aus.** Es benutzt dieselben Werte.
Steht die Box mittags am Fenster, während eingemessen wurde, als es dunkel
war, ist die Vorschau überstrahlt. Das ist die ehrliche Anzeige dessen, was
die Kamera gerade täte — und damit der Hinweis, dass neu eingemessen gehört.

## Nachtrag 20.11.2026: Das Foto war dunkler als die Vorschau

Mit gleich eingestelltem Einstell- und Aufnahmelicht kam das Foto sichtbar
dunkler heraus als das Livebild davor. Die erste Vermutung, die Aufnahme
missachte die eingemessenen Werte und regle selbst, war falsch. Gemessen am Pi:

```
Vorschau (2304x1296, gebündelt)   Mittelwert 146,4
Foto     (4608x2592, ganzer Chip) Mittelwert 100,4   also 0,686 davon
```

Die Ursache ist der Sensormodus. Das Livebild fasst vier Fotodioden zu einem
Bildpunkt zusammen, die Aufnahme liest jede einzeln. Bei gleicher Zeit und
gleicher Verstärkung sammelt ein Bildpunkt der Aufnahme also etwa die Hälfte
des Lichts. Dazu kommt die Gammakurve der Bildverarbeitung, nach der der
Ausgabewert etwa mit Licht hoch 0,63 wächst.

**Entschieden: messen statt rechnen.** Der Zusammenhang hängt an Sensor,
Treiber und Firmware, und eine Formel, die auf einem Chip stimmt, stimmt auf
dem nächsten nicht. Das Einmessen macht darum am Ende echte Aufnahmen,
vergleicht sie mit dem Livebild und legt das Ergebnis als
`capture_gain_factor` in der Konfiguration ab. Auf der Testbox sind es 1,91,
und das Foto liegt danach bei 97,7 % der Vorschau, gemessen durch die fertige
JPEG-Datei hindurch.

Unterwegs kam ein echter Fehler mit heraus: Werte, die kurz vor dem
Moduswechsel an die laufende Kamera geschickt werden, erreichen die Aufnahme
nicht. Sie müssen in der Konfiguration des Aufnahmemodus stehen, sonst
verwirft der Wechsel sie.

## Nachtrag 20.11.2026: Wie hell ein Bild sein soll, ist Geschmack

Das Einmessen hat eine Zielhelligkeit, und es behandelte sie als Messwert:
Was darunter lag, galt als zu dunkel, und die Lichtsuche drehte die Leuchte
hoch. Bei einem Aufnahmelicht von 17 % hätte sie auf etwa 98 % gestellt. Das
sind zwei Blendenstufen mehr als gewollt: An der Testbox sind 30 bis 40 %
gewünscht, und die Bilder dürfen eher dunkler sein.

Daraus zwei Felder statt einer Automatik:

- **Bildhelligkeit** (`exposure_bias_ev`), in Viertelstufen von -2 bis +1.
  Verschiebt das Ziel, nicht das Ergebnis. Minus macht die Fotos dunkler.
- **Aufnahmelicht selbst suchen** (`light_auto_search`). Aus heißt: Der
  eingestellte Wert bleibt stehen, es wird nur darunter gemessen.

Dazu neue Worte auf dem Ergebnisbildschirm. Eine lange Belichtungszeit heißt
nicht mehr „zu dunkel“, sondern „Bewegung wird verwischen“, denn das ist, was
sie wirklich kostet. Der Ratschlag zum Licht steht jetzt als Angebot da
(„Wenn du das willst: …“) und nennt den eingestellten Wert, statt eine hellere
Leuchte zu verlangen.

## Für die Anleitung

Der Ablauf vor jeder Veranstaltung, in dieser Reihenfolge:

1. Box aufstellen, wo sie stehen bleibt
2. Licht einschalten, wie es am Abend sein wird
3. Weißabgleich und Belichtung messen lassen
4. Ein Probebild machen und ansehen

Vier Schritte, zwei Minuten. Wer sie überspringt, merkt es am ersten
Gästefoto.
