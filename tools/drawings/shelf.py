# -*- coding: utf-8 -*-
"""Workshop drawings for the build guide. Run from the repository root:
       python3 tools/drawings/shelf.py
Everything is drawn in millimetres, one unit is one millimetre, and the
numbers are the ones measured on the booth itself.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
DOCS = pathlib.Path(__file__).resolve().parent.parent.parent / "docs"
from svgkit import Draw, INK, THIN
WOODF, WOOD = "#FBF7EE", "#E9D8A6"
d = Draw(1120, 640)
d.title(60, 44, "EventPics Fotobox: Ablage für den Drucker")
d.note(60, 66, ["Die Ablage klemmt auf dem Rohr des Ständers. Zwei Leisten bilden eine Gabel, "
                "hinten schließt ein Klotz, vorn hält eine Schraube M8 × 90 mit Flügelmutter."])

# --------------------------------------------------- top view
ax, ay = 80, 130
d.text(ax, ay - 14, "Ablage von oben", size=13, weight="600")
d.rect(ax, ay, 210, 400, fill=WOODF, sw=2)
d.rect(ax + 18, ay + 30, 170, 200, fill="none", stroke=THIN, sw=1.2, dash="6 4")
d.text(ax + 103, ay + 125, "printer", size=11, anchor="middle", fill="#6B7280")
d.circle(ax + 105, ay + 300, 17.5, fill="#E5E7EB")
d.text(ax + 105, ay + 304, "Rohr", size=9, anchor="middle", fill="#4B5563")
d.dim_h(ax, ax + 210, ay + 430, "210")
d.dim_v(ay, ay + 400, ax - 28, "400")

# --------------------------------------------------- bottom view
bx, by = 420, 130
d.text(bx, by - 14, "Ablage von unten", size=13, weight="600")
d.rect(bx, by, 210, 400, fill=WOODF, sw=2)
# two rails running across the 210 direction, 37 apart
d.rect(bx, by + 162, 210, 40, fill=WOOD, sw=1.4)
d.rect(bx, by + 239, 210, 40, fill=WOOD, sw=1.4)
d.rect(bx, by + 202, 55, 37, fill="#D6BE7A", sw=1.4)        # block closes the fork
d.circle(bx + 170, by + 220, 4.5, fill="#FFFFFF")
d.line(bx + 170, by + 150, bx + 170, by + 292, stroke=INK, sw=1.2, dash="5 4")
d.text(bx + 180, by + 150, "Bohrung Ø 9 durch beide Leisten", size=10)
d.text(bx + 27, by + 224, "block", size=10, anchor="middle")
d.dim_v(by + 202, by + 239, bx + 95, "37")
d.text(bx + 105, by + 320, "Gabel offen zur Vorderkante", size=10, anchor="middle")
d.dim_h(bx, bx + 210, by + 430, "210")

# --------------------------------------------------- clamp detail
cx, cy = 760, 160
d.text(cx, cy - 44, "Klemme, von vorn", size=13, weight="600")
d.rect(cx, cy, 300, 22, fill=WOODF, sw=2)                 # the board, edge on
d.text(cx + 150, cy - 8, "shelf 15 mm", size=10, anchor="middle")
d.rect(cx + 60, cy + 22, 40, 120, fill=WOOD, sw=1.4)
d.rect(cx + 197, cy + 22, 40, 120, fill=WOOD, sw=1.4)
d.circle(cx + 148, cy + 90, 17.5, fill="#E5E7EB")
d.text(cx + 148, cy + 94, "Ø 35", size=10, anchor="middle", fill="#4B5563")
d.line(cx + 60, cy + 125, cx + 237, cy + 125, stroke=INK, sw=3)
d.circle(cx + 52, cy + 125, 7, fill="#9CA3AF")
d.circle(cx + 245, cy + 125, 7, fill="#9CA3AF")
d.text(cx + 150, cy + 160, "M8 × 90 mit Flügelmutter", size=11, anchor="middle")
d.dim_h(cx + 100, cx + 197, cy + 185, "37")
d.note(cx - 10, cy + 230, [
    "Das Rohr des Ständers misst 35 mm, die Gabel 37 mm.",
    "Die Schraube liegt vor dem Rohr: anziehen, und die",
    "Ablage sitzt in jeder Höhe fest.",
    "",
    "Der Drucker steht lose darauf. Für den Transport",
    "nimmt man ihn herunter, die Ablage bleibt."])
d.save(str(DOCS / "drawing-shelf.svg"))
