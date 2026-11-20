# -*- coding: utf-8 -*-
"""Workshop drawing of the printer shelf. Run from the repository root:
       python3 tools/drawings/shelf.py
Everything is drawn in millimetres, one unit is one millimetre, and the
numbers are the ones measured on the booth itself.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
DOCS = pathlib.Path(__file__).resolve().parent.parent.parent / "docs"

from svgkit import Draw, INK, THIN

WOODF, WOOD, DARK = "#FBF7EE", "#E9D8A6", "#D6BE7A"
d = Draw(1120, 780)
d.title(60, 44, "EventPics Fotobox: Ablage für den Drucker")
d.note(60, 66, ["Die Ablage hängt an der hinteren Kante am Rohr des Ständers. Zwei Leisten stehen "
                "über die Kante hinaus und bilden eine Gabel, ein Klotz schließt sie zum Brett hin."])

# ----------------------------------------------------- Draufsicht
ax, ay = 80, 150
d.text(ax, ay - 16, "Von oben", size=13, weight="600")
d.rect(ax, ay, 400, 210, fill=WOODF, sw=2)
d.rect(ax + 30, ay + 20, 210, 170, fill="none", stroke=THIN, sw=1.2, dash="6 4")
d.text(ax + 135, ay + 110, "printer", size=11, anchor="middle", fill="#6B7280")
# Rohr liegt hinter der Kante, nur angeschnitten sichtbar
d.circle(ax + 200, ay + 210, 18.5, fill="#E5E7EB")
d.text(ax + 200, ay + 248, "Rohr Ø 37, hinter der Kante", size=10, anchor="middle")
d.dim_h(ax, ax + 400, ay + 272, "400")
d.dim_v(ay, ay + 210, ax - 26, "210")

# ----------------------------------------------------- Von unten
bx, by = 580, 150
d.text(bx, by - 16, "Von unten", size=13, weight="600")
d.rect(bx, by, 400, 210, fill=WOODF, sw=2)
# zwei Leisten quer zur hinteren Kante, 80 stehen darüber hinaus
d.rect(bx + 181 - 20, by + 80, 20, 210, fill=WOOD, sw=1.4)
d.rect(bx + 219, by + 80, 20, 210, fill=WOOD, sw=1.4)
d.rect(bx + 181, by + 80, 38, 60, fill=DARK, sw=1.4)          # Klotz, innen
d.circle(bx + 200, by + 212, 18.5, fill="#E5E7EB", sw=1.2)    # Rohr an der Kante
d.circle(bx + 200, by + 262, 4.5, fill="#FFFFFF")             # Bohrung für M8
d.line(bx + 150, by + 262, bx + 250, by + 262, stroke=INK, sw=1.2, dash="5 4")
d.text(bx + 256, by + 266, "Bohrung Ø 9 für M8 × 90", size=10)
d.text(bx + 200, by + 116, "block", size=9, anchor="middle")
d.text(bx + 258, by + 216, "Rohr", size=10)
d.dim_h(bx + 181, bx + 219, by + 170, "37")
d.dim_v(by + 210, by + 290, bx + 140, "80")
d.line(bx, by + 210, bx + 400, by + 210, stroke=THIN, sw=1, dash="5 4")
d.text(bx + 8, by + 204, "hintere Kante des Bretts", size=10)
d.dim_v(by + 80, by + 290, bx + 330, "210")
d.dim_h(bx, bx + 400, by + 330, "400")

# ----------------------------------------------------- Schnitt
cx, cy = 300, 560
d.text(cx - 220, cy - 26, "Schnitt durch die Gabel, von hinten gesehen", size=13, weight="600")
d.rect(cx - 220, cy, 440, 15, fill=WOODF, sw=2)
d.text(cx + 230, cy + 11, "shelf 15 mm", size=10)
d.rect(cx - 40, cy + 15, 20, 40, fill=WOOD, sw=1.4)
d.rect(cx + 17, cy + 15, 20, 40, fill=WOOD, sw=1.4)
d.circle(cx - 1.5, cy + 36, 18.5, fill="#E5E7EB", sw=1.2)
d.dim_h(cx - 20, cx + 17, cy + 76, "37")
d.text(cx + 60, cy + 40, "Leisten 20 × 40", size=10)
d.note(cx + 300, cy - 40, [
    "Das Rohr misst auf dieser Höhe etwa 37 mm, genau",
    "wie die Gabel: Die Ablage klemmt von selbst, aufschieben",
    "genügt. Eine Schraube M8 × 90 mit Flügelmutter quer",
    "durch beide Leisten sichert sie zusätzlich.",
    "",
    "Der Drucker steht lose darauf. Für den Transport nimmt",
    "man ihn herunter, die Ablage bleibt am Rohr.",
])
d.save(str(DOCS / "drawing-shelf.svg"))
