"""Background, overlay and caption - the parts a host can style.

Three separate things, because they sit in different places:

  * background: fills the sheet and shows through the gaps between pictures
  * overlay:    a transparent PNG laid over everything, for borders or a logo
  * caption:    title and date, drawn into the text area the layout reserves

Until real designs are uploaded, plain defaults are generated so the mechanism
can be seen and the geometry checked.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

#: A few unobtrusive backgrounds, so a host has something to pick before
#: uploading their own artwork.
BACKGROUNDS = {
    "weiss":      {"name": "Weiß",       "base": (255, 255, 255)},
    "creme":      {"name": "Creme",      "base": (248, 243, 232)},
    "sand":       {"name": "Sand",       "base": (238, 228, 210)},
    "rose":       {"name": "Altrosa",    "base": (245, 232, 230)},
    "eukalyptus": {"name": "Eukalyptus", "base": (231, 238, 231)},
    "anthrazit":  {"name": "Anthrazit",  "base": (34, 32, 29)},
    "schwarz":    {"name": "Schwarz",    "base": (16, 16, 16)},
    # The watercolour designs from the photo challenge editor, so a booth print
    # and the printed challenge cards of the same wedding look related.
    "botanical-full":  {"name": "Botanisch, rundum", "base": (253, 252, 249),
                        "art": "botanical-full.webp"},
    "botanical-soft":  {"name": "Botanisch, zart",   "base": (253, 252, 249),
                        "art": "botanical-soft.webp"},
    "botanical-sides": {"name": "Botanisch, seitlich", "base": (253, 252, 249),
                        "art": "botanical-sides.webp"},
}

ASSET_DIR = Path(__file__).resolve().parent / "assets" / "backgrounds"


#: What a host can choose for the caption, ordered from festive to plain.
#:
#: Every entry lists candidate files: the Raspberry Pi first, then the places a
#: development Mac keeps its equivalents. The URW and GFS families come with
#: Debian's ghostscript and font packages, so nothing has to be shipped or
#: downloaded - and they are the classic book faces, which is exactly what an
#: invitation or a print for a wedding wants.
FONTS = {
    "script": {
        "name": "Kalligrafie",
        "files": ["/usr/share/fonts/opentype/urw-base35/Z003-MediumItalic.otf",
                  "/System/Library/Fonts/Supplemental/Snell Roundhand.ttc",
                  "/System/Library/Fonts/Supplemental/Apple Chancery.ttf"],
    },
    "palatino_italic": {
        "name": "Palatino, kursiv",
        "files": ["/usr/share/fonts/opentype/urw-base35/P052-Italic.otf",
                  "/System/Library/Fonts/Supplemental/Palatino.ttc"],
        "bold":  ["/usr/share/fonts/opentype/urw-base35/P052-BoldItalic.otf"],
    },
    "palatino": {
        "name": "Palatino, warm",
        "files": ["/usr/share/fonts/opentype/urw-base35/P052-Roman.otf",
                  "/System/Library/Fonts/Supplemental/Palatino.ttc"],
        "bold":  ["/usr/share/fonts/opentype/urw-base35/P052-Bold.otf"],
    },
    "century": {
        "name": "Schulbuch-Antiqua",
        "files": ["/usr/share/fonts/opentype/urw-base35/C059-Roman.otf"],
        "bold":  ["/usr/share/fonts/opentype/urw-base35/C059-Bold.otf"],
    },
    "bookman": {
        "name": "Bookman, kräftig",
        "files": ["/usr/share/fonts/opentype/urw-base35/URWBookman-Light.otf"],
        "bold":  ["/usr/share/fonts/opentype/urw-base35/URWBookman-Demi.otf"],
    },
    "times": {
        "name": "Times",
        "files": ["/usr/share/fonts/opentype/urw-base35/NimbusRoman-Regular.otf",
                  "/System/Library/Fonts/Times.ttc"],
        "bold":  ["/usr/share/fonts/opentype/urw-base35/NimbusRoman-Bold.otf"],
    },
    "serif": {
        "name": "Serifen",
        "files": ["DejaVuSerif.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
                  "/System/Library/Fonts/Supplemental/Georgia.ttf"],
        "bold":  ["DejaVuSerif-Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
                  "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"],
    },
    "gothic": {
        "name": "Geometrisch",
        "files": ["/usr/share/fonts/opentype/urw-base35/URWGothic-Book.otf",
                  "/System/Library/Fonts/Supplemental/Futura.ttc"],
        "bold":  ["/usr/share/fonts/opentype/urw-base35/URWGothic-Demi.otf"],
    },
    "nunito": {
        "name": "Modern, leicht",
        "files": ["/usr/share/fonts/truetype/nunito-sans/"
                  "NunitoSans-VariableFont_YTLC,opsz,wdth,wght.ttf",
                  "/System/Library/Fonts/Supplemental/Avenir Next.ttc"],
    },
    "sans": {
        "name": "Serifenlos",
        "files": ["DejaVuSans.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                  "/System/Library/Fonts/Supplemental/Arial.ttf"],
        "bold":  ["DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
    },
    "mono": {
        "name": "Schreibmaschine",
        "files": ["DejaVuSansMono.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                  "/System/Library/Fonts/Menlo.ttc"],
    },
}

def _named_font(style: str, size: int, bold: bool):
    """The chosen face, in its bold cut when the family has one.

    A calligraphic face has a single weight - asking for bold there would fall
    back to a completely different typeface, so the regular cut is used and the
    title simply comes out larger than the line below it.
    """
    from PIL import ImageFont  # noqa: PLC0415

    spec = FONTS.get(style) or FONTS["serif"]
    candidates = list(spec.get("bold") or []) if bold else []
    candidates += list(spec.get("files") or [])
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return _font(size, bold)


def _font(size: int, bold: bool = False):
    from PIL import ImageFont  # noqa: PLC0415

    for name in _FONT_CANDIDATES[bold]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)   # Pillow 10.1 and newer
    except TypeError:
        log.warning("No scalable font found, caption will render tiny")
        return ImageFont.load_default()


def build_background(size: tuple[int, int], style: str, target: Path) -> Path:
    """The sheet behind the pictures: a plain colour, or a watercolour design.

    No drawn border any more - a frame belongs to the design, not to every
    background by default.
    """
    from PIL import Image  # noqa: PLC0415

    spec = BACKGROUNDS.get(style, BACKGROUNDS["creme"])

    # The sheet behind the pictures depends on nothing but style and size, yet
    # it was redrawn and written to the card for every single preview - by far
    # the most expensive part of composing a layout. Reuse it when it is still
    # current, and treat this file as newer than both the artwork and the
    # palette in this module.
    if target.exists():
        try:
            sources = [Path(__file__).resolve()]
            if spec.get("art"):
                sources.append(ASSET_DIR / spec["art"])
            newest = max(p.stat().st_mtime for p in sources if p.exists())
            if target.stat().st_mtime >= newest:
                with Image.open(target) as done:
                    if done.size == tuple(size):
                        return target
        except (OSError, ValueError):
            pass          # ein unlesbarer Zwischenstand wird einfach neu gebaut

    image = Image.new("RGB", size, spec["base"])

    art_name = spec.get("art")
    if art_name:
        art_path = ASSET_DIR / art_name
        if art_path.exists():
            with Image.open(art_path) as raw:
                art = raw.convert("RGBA")
                # Cover the sheet: these designs carry their motif at the edges,
                # so scaling to fit would leave bare strips exactly there.
                scale = max(size[0] / art.width, size[1] / art.height)
                art = art.resize((max(1, round(art.width * scale)),
                                  max(1, round(art.height * scale))), Image.LANCZOS)
                left = (art.width - size[0]) // 2
                top = (art.height - size[1]) // 2
                art = art.crop((left, top, left + size[0], top + size[1]))
                image = Image.alpha_composite(image.convert("RGBA"), art).convert("RGB")
        else:
            log.warning("Background art %s missing", art_path)

    target.parent.mkdir(parents=True, exist_ok=True)
    # This PNG is an intermediate step, not a result: hunting for the smallest
    # possible file costs more time here than it saves on reading later.
    image.save(target, "PNG", compress_level=1)
    return target


def _size_for_cap_height(style: str, target_px: float, bold: bool) -> int:
    """The font size at which a capital letter is `target_px` tall.

    A font size names the em, not the letter. Setting 4.5 mm and getting 3.3 mm
    of visible letter is exactly the kind of number nobody can work with, so the
    size is calibrated against a real capital of the chosen face - which also
    keeps two different fonts at the same setting looking equally large.
    """
    probe = 100
    font = _named_font(style, probe, bold)
    box = font.getbbox("H")
    cap = box[3] - box[1]
    if cap <= 0:
        return max(8, round(target_px))
    return max(8, round(probe * target_px / cap))


def draw_caption(canvas, area: tuple[int, int, int, int], title: str, subtitle: str,
                 font_style: str = "serif", colour: str = "",
                 size_mm: float = 4.5, dpi: float = 300.0) -> None:
    """Set title and date inside the area the layout reserved for them.

    The size is the height of a capital letter in millimetres on the finished
    print, because that is the only figure a host can hold a ruler against. It
    used to be a percentage of a size derived from the height of the text area -
    so the same setting produced a 4 mm title on one layout and an 8 mm title on
    another, which nobody could have guessed.

    If the text will not fit its area, it is scaled down until it does: a
    caption that runs over the edge is worse than one a little smaller than
    asked for.
    """
    from PIL import ImageDraw  # noqa: PLC0415

    x, y, w, h = area
    if w <= 0 or h <= 0:
        return
    draw = ImageDraw.Draw(canvas)

    def measure(title_size: int):
        title_font = _named_font(font_style, title_size, True)
        sub_font = _named_font(font_style, max(7, round(title_size * 0.55)), False)
        rows = [(text, font) for text, font in ((title, title_font), (subtitle, sub_font))
                if text]
        heights = [draw.textbbox((0, 0), text, font=font)[3] for text, font in rows]
        widths = [draw.textbbox((0, 0), text, font=font)[2] for text, font in rows]
        gap = round(title_size * 0.45)
        total = sum(heights) + gap * max(0, len(rows) - 1)
        return rows, heights, gap, total, (max(widths) if widths else 0)

    title_size = _size_for_cap_height(font_style, size_mm / 25.4 * dpi, True)
    rows, heights, gap, total, widest = measure(title_size)
    if not rows:
        return
    # Shrink to fit, in one step - the relationship is close enough to linear.
    if total > h or widest > w:
        shrink = min(h / total if total else 1.0, w / widest if widest else 1.0)
        title_size = max(8, int(title_size * shrink * 0.98))
        rows, heights, gap, total, widest = measure(title_size)

    cursor = y + (h - total) / 2

    if colour:
        fill = tuple(int(colour.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    else:
        # No colour chosen: read the sheet underneath so the text keeps contrast
        # on a dark background as well as a light one.
        patch = canvas.crop((x, y, x + w, y + h)).resize((1, 1))
        r, g, b = patch.getpixel((0, 0))
        fill = (28, 22, 16) if (r * 299 + g * 587 + b * 114) / 1000 > 140 else (250, 246, 238)

    for (text, font), height in zip(rows, heights):
        box = draw.textbbox((0, 0), text, font=font)
        draw.text((x + (w - (box[2] - box[0])) / 2 - box[0], cursor - box[1]),
                  text, font=font, fill=fill)
        cursor += height + gap
