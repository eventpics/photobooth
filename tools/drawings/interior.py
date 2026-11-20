# -*- coding: utf-8 -*-
"""Workshop drawings for the build guide. Run from the repository root:
       python3 tools/drawings/interior.py
Everything is drawn in millimetres, one unit is one millimetre, and the
numbers are the ones measured on the booth itself.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
DOCS = pathlib.Path(__file__).resolve().parent.parent.parent / "docs"
from svgkit import Draw, INK, THIN
WOODF, WOOD = "#FBF7EE", "#E9D8A6"

# ------------------------------------------------------------ interior
d = Draw(1120, 580)
d.title(60, 44, "EventPics Fotobox: Innenausbau")
d.note(60, 66, ["Blick in die offene Box von hinten. Die T\u00fcr ist abgenommen, "
                "links und rechts die Seitenw\u00e4nde."])
ax, ay = 110, 130
d.rect(ax - 15, ay - 15, 440, 320, fill=WOOD, sw=2)
d.rect(ax, ay, 410, 290, fill=WOODF, sw=1.4)
# screen back
d.rect(ax + 34, ay + 60, 342, 190, fill="#D1D5DB", sw=1.4)
d.text(ax + 205, ay + 140, "R\u00fcckseite des Bildschirms", size=11, anchor="middle", fill="#374151")
d.rect(ax + 60, ay + 196, 290, 36, fill="#93A3BC", sw=1.2)
d.text(ax + 205, ay + 219, "Treiberplatine mit HDMI, USB, Strom", size=10, anchor="middle", fill="#1F2937")
# top rail with pi mount, camera, two power supplies
d.rect(ax + 15, ay + 12, 380, 36, fill=WOOD, sw=1.2)
d.text(ax + 20, ay + 8, "Leiste quer, tr\u00e4gt alles Schwere", size=10)
d.rect(ax + 150, ay + 15, 70, 30, fill="#4B5563", sw=1.2)
d.text(ax + 185, ay + 34, "pi mount", size=9, anchor="middle", fill="#F9FAFB")
d.circle(ax + 120, ay + 30, 15, fill="#9CA3AF", sw=1.2)
d.text(ax + 120, ay + 33, "cam", size=9, anchor="middle")
d.rect(ax + 25, ay + 15, 70, 30, fill="#374151", sw=1.2)
d.text(ax + 60, ay + 34, "5 V \u00b7 pi", size=9, anchor="middle", fill="#F9FAFB")
d.rect(ax + 295, ay + 15, 90, 30, fill="#374151", sw=1.2)
d.text(ax + 340, ay + 34, "20 V \u00b7 light", size=9, anchor="middle", fill="#F9FAFB")
# bottom row: junction box, gland, screen supply
d.circle(ax + 52, ay + 262, 22, fill="#F97316", sw=1.4)
d.text(ax + 52, ay + 266, "Verteiler", size=9, anchor="middle", fill="#111827")
d.circle(ax + 118, ay + 264, 10, fill="#9CA3AF", sw=1.2)
d.text(ax + 118, ay + 286, "M20", size=9, anchor="middle")
d.rect(ax + 170, ay + 250, 110, 28, fill="#374151", sw=1.2)
d.text(ax + 225, ay + 269, "psu screen", size=9, anchor="middle", fill="#F9FAFB")
d.rect(ax + 300, ay + 250, 95, 28, fill="#E5E7EB", sw=1.2)
d.text(ax + 347, ay + 269, "zum Boden", size=9, anchor="middle")

tx = 600
d.text(tx, 150, "Was wo sitzt", size=13, weight="600")
items = [
    ("screen", "liegt von vorn in der Tasche, von hinten verschraubt"),
    ("pi mount", "3D-Druckteil auf der Querleiste, Pi liegt waagrecht"),
    ("camera", "Camera Module 3 auf einer Scheibe, schaut durch die Front"),
    ("5 V \u00b7 pi", "originales Raspberry-Pi-Netzteil, USB-C zum Pi"),
    ("20 V \u00b7 light", "Netzteil der Leuchte, Gleichstrom nach oben durch die M20"),
    ("psu screen", "drittes Netzteil, Hohlstecker zur Treiberplatine"),
    ("Verteiler", "Dose mit Steckklemme, von hier geht alles 230 V ab"),
    ("zum Boden", "Kaltger\u00e4tebuchse, Steckdose, USB-Buchse"),
]
for i, (a, b) in enumerate(items):
    y = 178 + i * 34
    d.text(tx, y, a, size=12, weight="600")
    d.text(tx, y + 15, b, size=11, fill="#4B5563")
d.save(str(DOCS / "drawing-interior.svg"))

# ------------------------------------------------------------- wiring
w = Draw(1120, 660)
w.title(60, 44, "EventPics Fotobox: Kabelplan")
w.note(60, 66, ["Drei Gruppen: 230 V nur im unteren Streifen, Niederspannung in der Mitte, "
                "Daten oben. Drei Netzteile, jedes mit seiner eigenen Spannung."])

def box(x, y, bw, bh, label, sub="", fill="#FFFFFF", stroke=INK):
    w.rect(x, y, bw, bh, fill=fill, stroke=stroke, sw=1.6, rx=6)
    w.text(x + bw / 2, y + (bh / 2 + 1 if not sub else bh / 2 - 4), label,
           size=12, anchor="middle", weight="600")
    if sub:
        w.text(x + bw / 2, y + bh / 2 + 13, sub, size=10, anchor="middle", fill="#4B5563")

def wire(x1, y1, x2, y2, colour, label="", lx=None, ly=None):
    w.line(x1, y1, x2, y2, stroke=colour, sw=2.4)
    if label:
        w.text(lx if lx else (x1 + x2) / 2, ly if ly else (y1 + y2) / 2 - 6, label,
               size=10, anchor="middle", fill=colour)

RED, BLUE, GREEN = "#B91C1C", "#1D4ED8", "#047857"
# --- data
box(60, 110, 170, 54, "camera", "Flachband")
box(280, 110, 170, 54, "raspberry pi", "4B, 2 GB oder mehr")
box(500, 110, 170, 54, "screen", "15,6\u2033 Touch")
box(720, 110, 170, 54, "usb coupler", "Buchse im Boden")
box(940, 50, 150, 54, "usb stick", "Sicherung")
box(940, 170, 150, 54, "printer", "Selphy CP1500")
wire(230, 137, 280, 137, GREEN)
wire(450, 124, 500, 124, GREEN, "HDMI", ly=118)
wire(450, 150, 500, 150, GREEN, "USB Touch", ly=166)
w.line(365, 110, 365, 82, stroke=GREEN, sw=2.4)
w.line(365, 82, 805, 82, stroke=GREEN, sw=2.4)
w.line(805, 82, 805, 110, stroke=GREEN, sw=2.4)
w.text(585, 76, "USB zum Drucker und zum Stick", size=10, anchor="middle", fill=GREEN)
w.line(890, 137, 915, 137, stroke=GREEN, sw=2.4)
w.line(915, 77, 915, 197, stroke=GREEN, sw=2.4)
w.line(915, 77, 940, 77, stroke=GREEN, sw=2.4)
w.line(915, 197, 940, 197, stroke=GREEN, sw=2.4)
# --- low voltage
box(280, 250, 170, 54, "psu 5 V", "f\u00fcr den Pi")
box(500, 250, 170, 54, "psu screen", "f\u00fcr das Display")
box(720, 250, 170, 54, "psu 20 V", "f\u00fcr die Leuchte")
box(940, 250, 150, 54, "light", "Godox LP400Bi")
wire(365, 250, 365, 164, BLUE, "5 V", lx=350)
wire(585, 250, 585, 164, BLUE, "", lx=570)
wire(890, 277, 940, 277, BLUE)
w.text(890, 332, "20 V durch die M20-Verschraubung im Deckel", size=10,
       anchor="end", fill=BLUE)
# --- mains
w.rect(40, 390, 1040, 190, fill="#FEF2F2", stroke="#FCA5A5", sw=1.4, rx=10)
w.text(58, 412, "230 V, nur in diesem Streifen", size=11, fill=RED, weight="600")
box(80, 430, 170, 54, "iec inlet", "Schalter + Sicherung")
box(320, 430, 170, 54, "junction box", "Steckklemme")
box(560, 430, 170, 54, "socket", "Schuko im Boden")
wire(250, 457, 320, 457, RED)
wire(490, 457, 560, 457, RED)
# junction box up to the three supplies
w.line(405, 430, 405, 350, stroke=RED, sw=2.4)
w.line(365, 350, 805, 350, stroke=RED, sw=2.4)
for x in (365, 585, 805):
    w.line(x, 304, x, 350, stroke=RED, sw=2.4)
# printer cord
w.line(730, 457, 1015, 457, stroke=RED, sw=2.4)
w.line(1015, 457, 1015, 224, stroke=RED, sw=2.4)
w.text(880, 450, "Netzkabel des Druckers", size=10, anchor="middle", fill=RED)
for lx, col, lab in ((80, RED, "230 V"), (200, BLUE, "Niederspannung"),
                     (380, GREEN, "Daten")):
    w.line(lx, 616, lx + 24, 616, stroke=col, sw=3)
    w.text(lx + 32, 620, lab, size=11, fill=col)
w.save(str(DOCS / "drawing-wiring.svg"))
