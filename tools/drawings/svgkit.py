"""Just enough SVG to draw a readable workshop sketch. All numbers in mm."""

HEAD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" '
        'height="{h}" font-family="DejaVu Sans, Verdana, sans-serif">\n'
        '<rect width="{w}" height="{h}" fill="#FFFFFF"/>\n')

WOOD = "#C9A227"
INK = "#1F2937"
THIN = "#9CA3AF"


class Draw:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.parts = [HEAD.format(w=w, h=h)]

    def add(self, s):
        self.parts.append(s + "\n")

    def rect(self, x, y, w, h, fill="none", stroke=INK, sw=1.6, rx=0, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
                 f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def circle(self, cx, cy, r, fill="none", stroke=INK, sw=1.4):
        self.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" '
                 f'stroke="{stroke}" stroke-width="{sw}"/>')

    def line(self, x1, y1, x2, y2, stroke=INK, sw=1.2, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                 f'stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def text(self, x, y, s, size=11, anchor="start", fill=INK, weight="normal"):
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" '
                 f'fill="{fill}" font-weight="{weight}">{s}</text>')

    def title(self, x, y, s, size=16):
        self.text(x, y, s, size=size, weight="600")

    # dimension lines ---------------------------------------------------
    def dim_h(self, x1, x2, y, label, size=11, tick=4, colour=THIN):
        self.line(x1, y, x2, y, stroke=colour, sw=1)
        for x in (x1, x2):
            self.line(x, y - tick, x, y + tick, stroke=colour, sw=1)
        self.text((x1 + x2) / 2, y - 5, label, size=size, anchor="middle", fill="#4B5563")

    def dim_v(self, y1, y2, x, label, size=11, tick=4, colour=THIN):
        self.line(x, y1, x, y2, stroke=colour, sw=1)
        for y in (y1, y2):
            self.line(x - tick, y, x + tick, y, stroke=colour, sw=1)
        self.add(f'<text x="{x - 6:.1f}" y="{(y1 + y2) / 2:.1f}" font-size="{size}" '
                 f'text-anchor="middle" fill="#4B5563" '
                 f'transform="rotate(-90 {x - 6:.1f} {(y1 + y2) / 2:.1f})">{label}</text>')

    def note(self, x, y, lines, size=11, colour="#4B5563"):
        for i, s in enumerate(lines):
            self.text(x, y + i * (size + 4), s, size=size, fill=colour)

    def save(self, path):
        self.parts.append("</svg>\n")
        open(path, "w", encoding="utf-8").write("".join(self.parts))
        print("geschrieben:", path)
