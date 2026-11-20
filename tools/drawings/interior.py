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
d = Draw(1120, 560)
d.title(60, 44, "EventPics Fotobox: Innenausbau")
d.note(60, 66, ["Blick in die offene Box von hinten. Die Tür ist abgenommen, "
                "links und rechts die Seitenwände."])
ax, ay = 110, 130
d.rect(ax - 15, ay - 15, 440, 320, fill=WOOD, sw=2)
d.rect(ax, ay, 410, 290, fill=WOODF, sw=1.4)
# screen back
d.rect(ax + 40, ay + 57, 330, 196, fill="#D1D5DB", sw=1.4)
d.text(ax + 205, ay + 150, "Rückseite des Bildschirms", size=11, anchor="middle", fill="#374151")
d.rect(ax + 60, ay + 205, 290, 40, fill="#93A3BC", sw=1.2)
d.text(ax + 205, ay + 229, "Treiberplatine mit HDMI, USB, 12 V", size=10, anchor="middle", fill="#1F2937")
# top rail with pi mount, camera, psus
d.rect(ax + 15, ay + 15, 380, 36, fill=WOOD, sw=1.2)
d.text(ax + 20, ay + 11, "Leiste quer, trägt alles Schwere", size=10)
d.rect(ax + 150, ay + 18, 70, 30, fill="#4B5563", sw=1.2)
d.text(ax + 185, ay + 37, "pi mount", size=9, anchor="middle", fill="#F9FAFB")
d.circle(ax + 120, ay + 33, 15, fill="#9CA3AF", sw=1.2)
d.text(ax + 120, ay + 36, "cam", size=9, anchor="middle")
d.rect(ax + 25, ay + 18, 70, 30, fill="#374151", sw=1.2)
d.text(ax + 60, ay + 37, "5 V · Pi", size=9, anchor="middle", fill="#F9FAFB")
d.rect(ax + 300, ay + 18, 85, 30, fill="#374151", sw=1.2)
d.text(ax + 342, ay + 37, "12 V · screen", size=9, anchor="middle", fill="#F9FAFB")
# junction box and gland
d.circle(ax + 60, ay + 255, 22, fill="#F97316", sw=1.4)
d.text(ax + 60, ay + 259, "Verteiler", size=9, anchor="middle", fill="#111827")
d.circle(ax + 130, ay + 258, 10, fill="#9CA3AF", sw=1.2)
d.text(ax + 130, ay + 285, "M20 zur Leuchte", size=9, anchor="middle")
d.rect(ax + 250, ay + 258, 120, 24, fill="#E5E7EB", sw=1.2)
d.text(ax + 310, ay + 274, "Kabel zum Boden", size=9, anchor="middle")

tx = 600
d.text(tx, 150, "Was wo sitzt", size=13, weight="600")
items = [
    ("screen", "liegt von vorn in der Tasche, von hinten verschraubt"),
    ("pi mount", "3D-Druckteil auf der Querleiste, Pi liegt waagrecht"),
    ("camera", "Camera Module 3 auf einer Scheibe, schaut durch die Front"),
    ("5 V · Pi", "originales Raspberry-Pi-Netzteil, USB-C zum Pi"),
    ("12 V · screen", "Netzteil des Displays, Hohlstecker zur Treiberplatine"),
    ("Verteiler", "Dose mit Steckklemme, von hier geht alles 230 V ab"),
    ("M20", "Durchführung im Deckel, Kabel zur Leuchte"),
    ("Boden", "Kaltgerätebuchse, Steckdose, USB-Buchse"),
]
for i, (a, b) in enumerate(items):
    y = 178 + i * 34
    d.text(tx, y, a, size=12, weight="600")
    d.text(tx, y + 15, b, size=11, fill="#4B5563")
d.save(str(DOCS / "drawing-interior.svg"))

# ------------------------------------------------------------- wiring
w = Draw(1120, 620)
w.title(60, 44, "EventPics Fotobox: Kabelplan")
w.note(60, 66, ["Drei Gruppen: 230 V nur im unteren Streifen, Niederspannung in der Mitte, "
                "Daten oben. Nichts kreuzt, was es nicht muss."])

def box(x, y, bw, bh, label, sub="", fill="#FFFFFF", stroke=INK):
    w.rect(x, y, bw, bh, fill=fill, stroke=stroke, sw=1.6, rx=6)
    w.text(x + bw / 2, y + (bh / 2 + 1 if not sub else bh / 2 - 4), label,
           size=12, anchor="middle", weight="600")
    if sub:
        w.text(x + bw / 2, y + bh / 2 + 13, sub, size=10, anchor="middle", fill="#4B5563")

def wire(x1, y1, x2, y2, colour, label="", dash=None, lx=None, ly=None):
    w.line(x1, y1, x2, y2, stroke=colour, sw=2.4, dash=dash)
    if label:
        w.text(lx if lx else (x1 + x2) / 2, ly if ly else (y1 + y2) / 2 - 6, label,
               size=10, anchor="middle", fill=colour)

RED, BLUE, GREEN = "#B91C1C", "#1D4ED8", "#047857"
# data row
box(80, 120, 150, 54, "camera", "Flachband")
box(300, 120, 150, 54, "raspberry pi", "4B, 2 GB+")
box(520, 120, 170, 54, "screen", "15,6″ Touch")
box(760, 120, 170, 54, "usb coupler", "Buchse im Boden")
box(940, 190, 140, 54, "usb stick", "Sicherung")
box(760, 260, 170, 54, "printer", "Selphy CP1500")
wire(230, 147, 300, 147, GREEN)
wire(450, 134, 520, 134, GREEN, "HDMI", ly=128)
wire(450, 160, 520, 160, GREEN, "USB Touch", ly=176)
wire(450, 147, 760, 147, GREEN, "USB", lx=600, ly=112)
wire(930, 147, 1010, 190, GREEN)
wire(845, 174, 845, 260, GREEN)
# low voltage
box(300, 260, 150, 54, "psu 5 V", "3 A, USB-C")
box(520, 260, 170, 54, "psu 12 V", "für das Display")
wire(375, 260, 375, 174, BLUE, "5 V", lx=360)
wire(605, 260, 605, 174, BLUE, "12 V", lx=620)
# mains
w.rect(60, 400, 1000, 170, fill="#FEF2F2", stroke="#FCA5A5", sw=1.4, rx=10)
w.text(76, 422, "230 V, nur in diesem Streifen", size=11, fill="#B91C1C", weight="600")
box(90, 440, 170, 54, "iec inlet", "Schalter + Sicherung")
box(330, 440, 170, 54, "junction box", "Steckklemme")
box(570, 440, 170, 54, "socket", "Schuko im Boden, Drucker")
box(810, 440, 170, 54, "light", "Godox LP400Bi")
wire(260, 467, 330, 467, RED)
wire(500, 467, 570, 467, RED)
wire(415, 494, 415, 530, RED)
wire(415, 530, 895, 530, RED, "durch die M20-Durchführung im Deckel", lx=650, ly=524)
wire(895, 530, 895, 494, RED)
wire(415, 440, 415, 314, RED)
wire(605, 440, 605, 314, RED)
for lx, col, lab in ((90, RED, "230 V"), (210, BLUE, "Niederspannung"),
                     (390, GREEN, "Daten")):
    w.line(lx, 586, lx + 24, 586, stroke=col, sw=3)
    w.text(lx + 32, 590, lab, size=11, fill=col)
w.save(str(DOCS / "drawing-wiring.svg"))
