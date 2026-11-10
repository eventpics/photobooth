# Welcher Raspberry Pi — und warum der Browser das Problem ist

Stand: 11.09.2026. Gemessen auf einem Pi 4 Model B mit 1 GB, Debian Trixie,
Bildschirm 1920×1080, Kamera IMX708.

## Die entscheidende Messung

Dieselbe Box, einmal mit und einmal ohne den Browser auf dem eigenen
Bildschirm:

    ohne Chromium      6 % CPU    296 MB belegt    65 °C
    mit  Chromium     91 % CPU    790 MB belegt    76 °C

Die Fotobox selbst — Kamera, Weboberfläche, Bildmontage, Upload — ist
federleicht: **51 MB Arbeitsspeicher und ein paar Prozent Rechenzeit.** Alles
andere ist der Browser, der die Oberfläche anzeigt.

Das ist wichtig für jede Optimierung: An der Anwendung zu sparen bringt fast
nichts, weil dort fast nichts verbraucht wird.

## Woran der Browser sich abarbeitet

Am Livebild. Es kommt als JPEG-Strom, und Chromium dekodiert jedes einzelne
Bild in Software. Bei 1800×1200 und 20 Bildern je Sekunde sind das
43 Megapixel pro Sekunde.

Messreihe, jeweils nach einem Neustart und 30 Sekunden Einschwingen:

    1800x1200  20 fps    91 % CPU    76,0 °C
    1620x1080  20 fps    81 %        74,5 °C
    1620x1080  15 fps    64 %        72,1 °C
    1440x960   15 fps    55 %        70,6 °C
    1620x1080  12 fps    55 %        73,0 °C
    1296x864   15 fps    56 %        72,1 °C
    1296x864   12 fps    49 %        70,6 °C

Die Rechenzeit folgt fast genau dem Produkt aus Bildpunkten und Bildrate.

**Gewählt: 1440×960 bei 15 Bildern je Sekunde.** Das halbiert die Last
gegenüber vorher und sieht auf dem Schirm unverändert aus. Mehr Auflösung
bringt nichts: Größer als 1620×1080 wird die Vorschau nie angezeigt — im
Countdown wächst sie auf `min(100vw, 100vh × 1,5)`, und das ist auf einem
1920×1080-Schirm genau dieser Wert.

## Reicht ein Pi 4 mit 1 GB?

Ja, aber ohne Reserve.

    Rechenzeit      56 %, keine Drosselung (throttled=0x0, Takt 1500 MHz)
    Temperatur      72 °C  (Drosselung beginnt bei 80 °C)
    Arbeitsspeicher 192 MB frei, dazu 226 MB komprimiert ausgelagert

Über 83 Minuten mitgeschrieben, eine Zeile je Minute: **kein Wachstum, kein
Leck, kein einziger Absturz.** Der freie Speicher schwankte zwischen 73 und
490 MB und pendelte sich bei rund 120 MB ein.

Eine Voraussetzung dafür steht in `/boot/firmware/config.txt`. Voreingestellt
reserviert Pi OS auf einem 1-GB-Gerät **512 MB** für Kamera und Grafik — die
Hälfte des Speichers. Damit wurde Chromium dreimal vom Kernel abgeschossen.
Mit `dtoverlay=vc4-kms-v3d,cma-256` bleiben statt 393 MB nun 648 MB für alles
andere, und seitdem ist nichts mehr abgestürzt.

## Empfehlung für die Bauanleitung

**Empfohlen wird der Raspberry Pi 5.** Er ist das aktuelle Modell, und es gibt
keinen guten Grund, in einer Anleitung von 2026 ein älteres zu nennen. Das
passende Kamerakabel liegt den Kameramodulen bei, und der Lüfter kommt vom
Hersteller selbst — das sind Teile aus demselben Regal, keine Bastelei.

Mit den Zahlen von oben ist er auch der ruhigere Weg: Der einzige Verbraucher
ist der Browser, und der hätte dort mehr Kerne, mehr Takt und deutlich mehr
Speicher zur Verfügung. Nichts von dem, was auf den folgenden Seiten steht —
Speicherreservierung heruntersetzen, Vorschau verkleinern, Wächter über die
Anzeige — wird dort zur Pflicht.

**Der Pi 4 bleibt genannt, nicht empfohlen.** Wer einen herumliegen hat,
bekommt eine laufende Box: Die Entwicklungsbox läuft auf einem Pi 4 mit 1 GB,
gemessen bei 56 % Rechenzeit und 72 °C. Wer neu kauft, kauft einen Pi 5.

### Was auf die Einkaufsliste gehört

    Raspberry Pi 5              4 GB genügen; 8 GB schaden nicht
    Netzteil                    27 W USB-C (5 V / 5 A) vom Hersteller
    Aktive Kühlung              der offizielle Lüfter, im Gehäuse Pflicht
    Kameramodul 3               Kabel für den Pi 5 liegt bei
    microSD                     32 GB, besser eine A2-Karte

### Läuft die Software auf einem Pi 5?

Nachgesehen, nicht vermutet — die drei Stellen, an denen es hätte klemmen
können:

**Die GPIO-Pins.** `gpiozero` 2.0.1 wählt von selbst die Pin-Fabrik
`LGPIOFactory`. Genau die wird auf dem Pi 5 gebraucht; das alte `RPi.GPIO`
spricht dort nicht mehr mit der Hardware. Es ist also schon die richtige.

**Der LED-Streifen.** Läuft über SPI, nicht über die übliche DMA-Bibliothek.
Das war von Anfang an die Absicht: DMA braucht root, streitet mit dem Tonteil
und funktioniert auf dem Pi 5 nicht mehr. Ein Bitmuster aus dem SPI-Ausgang
funktioniert auf beiden.

**Die Kamera.** picamera2 und libcamera sind auf dem Pi 5 dieselben. Das
IMX708 wird dort genauso erkannt.

Bleibt eine Kleinigkeit für die Anleitung: `dtparam=spi=on` muss in
`config.txt` stehen, sonst gibt es kein `/dev/spidev0.0` und der LED-Streifen
bleibt dunkel. Das gilt auf beiden Geräten.

Die Reservierung `dtoverlay=vc4-kms-v3d,cma-256` ist dagegen **nur für kleine
Geräte** gedacht. Auf einem Pi 5 mit 4 GB gibt es nichts zurückzuholen; dort
bleibt die Voreinstellung stehen.

## Nachtrag: der Browser ist weg

Der Hebel von oben ist seit Version 0.7 umgesetzt, und zwar gründlicher als hier
vorgesehen: Nicht nur das Livebild, die ganze Oberfläche läuft ohne Browser. Das
Livebild geht über OpenGL direkt von der Kamera auf den Bildschirm. Die Gründe
und Messungen stehen in decision-native-ui.md.

Die Empfehlung für den Pi 5 bleibt trotzdem stehen: mehr Reserve, der neuere
Kameraanschluss und der Lüfter vom Hersteller.
