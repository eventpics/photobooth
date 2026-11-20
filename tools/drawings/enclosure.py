# -*- coding: utf-8 -*-
"""Workshop drawings for the build guide. Run from the repository root:
       python3 tools/drawings/enclosure.py
Everything is drawn in millimetres, one unit is one millimetre, and the
numbers are the ones measured on the booth itself.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
DOCS = pathlib.Path(__file__).resolve().parent.parent.parent / "docs"
from svgkit import Draw, INK, THIN

WOODF = "#FBF7EE"
WOOD = "#E9D8A6"
W, H = 1180, 1000
d = Draw(W, H)
d.title(60, 44, "EventPics Fotobox: Gehäuse")
d.note(60, 66, ["Alle Maße in Millimetern. Holz 15 mm, bei mir Eiche massiv. "
                "Außenmaß 410 × 290 × 180, Tiefe mit Tür."])

def leader(x1, y1, x2, y2, text, size=10, anchor="start", dx=5):
    d.line(x1, y1, x2, y2, stroke=THIN, sw=1)
    d.circle(x1, y1, 1.6, fill=THIN, stroke=THIN, sw=0.6)
    d.text(x2 + (dx if anchor == "start" else -dx), y2 + 3.5, text, size=size, anchor=anchor)

# ------------------------------------------------------------------ front
ax, ay = 80, 130
d.text(ax, ay - 14, "Vorderseite", size=13, weight="600")
d.rect(ax, ay, 410, 290, fill=WOODF, sw=2)
ox, oy, ow, oh = ax + 34, ay + 60, 342, 190
d.rect(ox, oy, ow, oh, fill="#374151", sw=1.6)
d.text(ox + ow / 2, oy + oh / 2 + 4, "Bildschirmausschnitt", size=12, anchor="middle", fill="#E5E7EB")
d.circle(ax + 205, ay + 43, 4, fill="#111827")
leader(ax + 205, ay + 43, ax + 150, ay + 30, "Kamera Ø 8, mittig", anchor="end")
d.dim_h(ax, ox, ay + 320, "34")
d.dim_h(ox, ox + ow, ay + 320, "342")
d.dim_h(ax, ax + 410, ay + 352, "410")
d.dim_v(ay, ay + 290, ax - 28, "290")
d.dim_v(oy, oy + oh, ox - 18, "190")
d.dim_v(ay, oy, ax + 432, "60")
d.dim_v(oy + oh, ay + 290, ax + 432, "40")
d.dim_v(ay, ay + 43, ax + 205 + 14, "43")
d.note(ax, ay + 386, [
    "Der Ausschnitt gehört zum eigenen Panel, hier ein Waveshare 15,6″",
    "Einbau-Display. Von hinten liegt es in einer 9 mm tiefen Tasche,",
    "damit das Glas bündig in der Front steht."])

# ---------------------------------------------------------------- section
bx, by = 650, 130
d.text(bx, by - 14, "Schnitt von rechts", size=13, weight="600")
d.rect(bx, by, 180, 15, fill=WOOD)                     # top
d.rect(bx, by + 275, 180, 15, fill=WOOD)               # bottom
d.rect(bx, by + 15, 15, 260, fill=WOOD)                # front
d.rect(bx + 165, by + 15, 15, 260, fill=WOOD)          # door
d.rect(bx + 15, by + 60, 22, 190, fill="#9CA3AF", sw=1.2)   # screen
d.rect(bx + 45, by + 34, 70, 12, fill="#D1D5DB", sw=1.2)    # rail
d.rect(bx + 60, by + 22, 34, 12, fill="#6B7280", sw=1.2)    # pi mount
d.circle(bx + 7.5, by + 43, 3.5, fill="#111827")
leader(bx + 7.5, by + 43, bx + 215, by + 18, "Kameraloch in der Front")
leader(bx + 26, by + 140, bx + 215, by + 110, "screen in der Tasche")
leader(bx + 77, by + 28, bx + 215, by + 48, "pi mount auf der Leiste")
leader(bx + 110, by + 230, bx + 215, by + 200, "Netzteile, Verteiler, Kabel")
leader(bx + 172, by + 240, bx + 215, by + 250, "door, 2 Scharniere")
d.dim_h(bx, bx + 15, by - 26, "15")
d.dim_h(bx + 165, bx + 180, by - 26, "15")
d.dim_h(bx, bx + 180, by + 352, "180")
d.dim_v(by, by + 290, bx - 28, "290")

# ------------------------------------------------------------------- door
cx, cy = 80, 620
d.text(cx, cy - 14, "Tür von innen", size=13, weight="600")
d.rect(cx, cy, 410, 290, fill=WOODF, sw=2)
d.rect(cx + 175, cy + 22, 60, 60, fill="#D1D5DB")
for y in (cy + 118, cy + 205):
    d.rect(cx + 60, y, 320, 35, fill=WOOD, sw=1.2)
for y in (cy + 55, cy + 195):
    d.rect(cx + 395, y, 15, 45, fill="#9CA3AF", sw=1.2)
d.circle(cx + 22, cy + 145, 9.5, fill="#FFFFFF")
d.text(cx + 205, cy + 100, "Lüftungsgitter 60 × 60", size=10, anchor="middle")
d.text(cx + 220, cy + 140, "Querleisten gegen das Werfen", size=10, anchor="middle")
d.text(cx + 220, cy + 227, "Querleisten gegen das Werfen", size=10, anchor="middle")
d.text(cx + 388, cy + 45, "2 × surface hinge", size=10, anchor="end")
d.text(cx + 40, cy + 149, "cam lock Ø 19", size=10)
d.dim_h(cx, cx + 410, cy + 320, "410")
d.dim_v(cy, cy + 290, cx - 28, "290")

# ----------------------------------------------------------- cutting list
tx, ty = 650, 620
d.text(tx, ty - 14, "Zuschnitt, 15 mm Holz", size=13, weight="600")
rows = [
    ("front", "410 × 290", "1", "Ausschnitt und Tasche für das Panel"),
    ("door", "410 × 290", "1", "Gitter, Schloss, Scharniere"),
    ("top / bottom", "410 × 150", "2", "Deckel mit Bohrung für die Leuchte"),
    ("side", "260 × 150", "2", "zwischen Deckel und Boden"),
    ("rails", "ca. 350 × 40", "2", "innen, tragen pi mount und Netzteile"),
    ("shelf", "400 × 210", "1", "Ablage für den Drucker"),
    ("shelf rails", "210 × 40", "2", "bilden die Klemme, Abstand 37"),
    ("shelf block", "60 × 37", "1", "schließt die Klemme hinten"),
]
d.line(tx, ty + 6, tx + 460, ty + 6, stroke=THIN, sw=1)
for i, (teil, mass, n, bem) in enumerate(rows):
    y = ty + 26 + i * 25
    d.text(tx, y, teil, size=12, weight="600")
    d.text(tx + 120, y, mass, size=12)
    d.text(tx + 205, y, n + "×", size=12)
    d.text(tx + 235, y, bem, size=11, fill="#4B5563")
    d.line(tx, y + 7, tx + 460, y + 7, stroke="#E5E7EB", sw=1)
d.note(tx, ty + 26 + len(rows) * 25 + 20, [
    "Vorder- und Rückseite liegen stumpf auf dem Rahmen aus Deckel,",
    "Boden und Seiten. Wer die Stöße anders macht, ändert nur die",
    "Teile des Rahmens, nicht das Außenmaß."])

d.save(str(DOCS / "drawing-enclosure.svg"))
