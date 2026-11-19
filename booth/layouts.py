"""Layout definitions and image composition.

One paper format, always: 10x15 cm landscape, 1800x1200 at 300 dpi. Landscape
because a 2x2 grid then has cells close to 3:2, which suits the 16:9 sensor -
in portrait, half the width of every photo would be cropped away.

A layout is data, not code: frame rectangles plus an optional text area, all in
fractions of the canvas. Three pieces are drawn in order, and each is optional:

    background  ->  photos  ->  overlay  ->  caption

The background is what shows through the gaps between pictures; the overlay
sits on top of everything for borders and logos.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: 10x15 cm at 600 dpi, landscape. The only sheet the booth produces.
#:
#: The printer only needs 300 dpi, i.e. 1800 x 1200 - on paper there is no
#: visible difference. But the sheet also goes to the gallery, where it gets
#: stretched to full window width on a desktop; at 1800 pixels that turns to
#: mush. Everything on the sheet is measured as a fraction of the area and the
#: lettering is in millimetres, so nothing about the look changes.
CANVAS = (3600, 2400)

#: The paper itself, in millimetres. Type size is set in millimetres on this
#: sheet, so the resolution of the canvas can change without the caption
#: changing size.
PAPER_MM = (152.4, 101.6)

#: The IMX708 delivers 16:9. Frames keep a landscape shape close to that and
#: are centred inside their slot, so nothing is cropped hard.
FRAME_ASPECT = 3 / 2


@dataclass
class Frame:
    x: float
    y: float
    w: float
    h: float

    def px(self, canvas: tuple[int, int]) -> tuple[int, int, int, int]:
        return (round(self.x * canvas[0]), round(self.y * canvas[1]),
                round(self.w * canvas[0]), round(self.h * canvas[1]))


@dataclass
class Layout:
    id: str
    name: str
    shots: int
    frames: list[Frame]
    #: Where title and date are set. None means the picture carries no text.
    text_area: Frame | None = None
    #: Full bleed layouts leave no border, so the background never shows.
    full_bleed: bool = False
    canvas: tuple[int, int] = CANVAS
    background_colour: str = "#FFFFFF"
    description: str = ""
    #: A strip-style layout could be printed twice per sheet. Kept at one here;
    #: duplication belongs to printing, never to the stored picture.
    print_copies_across: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "shots": self.shots,
            "canvas": list(self.canvas), "full_bleed": self.full_bleed,
            "has_text": self.text_area is not None,
            "frames": [[f.x, f.y, f.w, f.h] for f in self.frames],
            "text_area": ([self.text_area.x, self.text_area.y,
                           self.text_area.w, self.text_area.h] if self.text_area else None),
            "print_copies_across": self.print_copies_across,
            "description": self.description,
        }


def _fit_aspect(slot: Frame, canvas: tuple[int, int], aspect: float) -> Frame:
    """Shrink a slot to the target shape, centred, so nothing is over-cropped."""
    slot_w, slot_h = slot.w * canvas[0], slot.h * canvas[1]
    if slot_w / slot_h > aspect:
        new_w = (slot_h * aspect) / canvas[0]
        return Frame(slot.x + (slot.w - new_w) / 2, slot.y, new_w, slot.h)
    new_h = (slot_w / aspect) / canvas[1]
    return Frame(slot.x, slot.y + (slot.h - new_h) / 2, slot.w, new_h)


def _cells(cols: int, rows: int, margin: float, gap: float,
           bottom: float = 0.0) -> list[Frame]:
    """Grid cells inside the margins, leaving `bottom` free for a caption."""
    usable_h = 1.0 - 2 * margin - bottom
    w = (1.0 - 2 * margin - gap * (cols - 1)) / cols
    h = (usable_h - gap * (rows - 1)) / rows
    return [Frame(margin + c * (w + gap), margin + r * (h + gap), w, h)
            for r in range(rows) for c in range(cols)]


def band_fraction(caption_mm: float) -> float:
    """How much of the sheet the caption band needs at that type size.

    Title, gap and subtitle together come to roughly 2.8 times the height of a
    capital, plus the bottom margin. The band grows with the type instead of the
    type being squeezed into a fixed band - otherwise every setting above about
    six millimetres does nothing at all, which is exactly how it behaved before.

    Never more than 45 % of the sheet: past that it has stopped being a caption.
    """
    needed_mm = caption_mm * 2.8 + 4.0
    return min(0.45, max(0.12, needed_mm / PAPER_MM[1]))


def build_layouts(caption_mm: float = 4.5) -> dict[str, Layout]:
    """The four sheets the booth can produce. The host picks one per event.

    The caption size is a parameter because it changes the geometry: a taller
    band leaves less room for the pictures above it.
    """
    margin, gap = .035, .022
    band = band_fraction(caption_mm)   # caption band along the bottom

    grid = _cells(2, 2, margin, gap, bottom=band)
    grid_full = _cells(2, 2, margin, gap)          # no band: text sits in a cell

    return {
        "single": Layout(
            id="single", name="Einzelbild randlos", shots=1,
            frames=[Frame(0.0, 0.0, 1.0, 1.0)],
            text_area=None, full_bleed=True,
            description="Ein Bild über das ganze Blatt, ohne Rahmen und ohne Text",
        ),
        "single_caption": Layout(
            id="single_caption", name="Einzelbild mit Text", shots=1,
            frames=[_fit_aspect(Frame(margin, margin, 1 - 2 * margin,
                                      1 - 2 * margin - band), CANVAS, FRAME_ASPECT)],
            text_area=Frame(margin, 1 - band, 1 - 2 * margin, band - margin),
            description="Ein Bild, darunter Namen und Datum, Hintergrund als Rahmen",
        ),
        "grid4": Layout(
            id="grid4", name="Vier Bilder", shots=4,
            frames=[_fit_aspect(c, CANVAS, FRAME_ASPECT) for c in grid],
            text_area=Frame(margin, 1 - band, 1 - 2 * margin, band - margin),
            description="Zwei mal zwei, darunter Namen und Datum",
        ),
        "grid3_text": Layout(
            id="grid3_text", name="Drei Bilder und Text", shots=3,
            frames=[_fit_aspect(c, CANVAS, FRAME_ASPECT) for c in grid_full[:3]],
            text_area=grid_full[3],
            description="Zwei Bilder oben, eines unten links, rechts unten der Text",
        ),
    }


#: Corner radius of a framed picture, as a fraction of its shorter side.
CORNER_RADIUS = .045


def _fit_cover(image, target_w: int, target_h: int):
    """Scale and centre-crop so the frame is filled without distortion."""
    from PIL import Image  # noqa: PLC0415

    src_w, src_h = image.size
    if (src_w, src_h) == (target_w, target_h):
        return image          # already right - a 1:1 LANCZOS only costs time
    scale = max(target_w / src_w, target_h / src_h)
    new = (max(1, round(src_w * scale)), max(1, round(src_h * scale)))
    image = image.resize(new, Image.LANCZOS)
    left, top = (new[0] - target_w) // 2, (new[1] - target_h) // 2
    return image.crop((left, top, left + target_w, top + target_h))


def _load_fitted(path: Path, target_w: int, target_h: int):
    """Open a photo and fit it to the frame, decoding no more than needed.

    A JPEG can be unpacked at half, quarter or eighth size directly in the
    decoder. The sensor delivers 2304x1296 and a grid cell wants roughly a
    third of that, so full decoding throws away most of the work.
    """
    from PIL import Image  # noqa: PLC0415

    with Image.open(path) as image:
        # draft picks the largest reduction that still covers the target, so
        # the following LANCZOS step has the detail it needs.
        image.draft("RGB", (target_w, target_h))
        return _fit_cover(image.convert("RGB"), target_w, target_h)


#: The decoded background sheet, kept for the next composition. Only one entry:
#: a booth uses one style at a time, and a 1800x1200 sheet is a few megabytes.
_BACKGROUND_CACHE: dict[str, Any] = {}


def _background_image(path: Path, size: tuple[int, int]):
    """The background, decoded once and kept until the file changes."""
    from PIL import Image  # noqa: PLC0415

    key = (str(path), path.stat().st_mtime, size)
    if _BACKGROUND_CACHE.get("key") == key:
        return _BACKGROUND_CACHE["image"]
    with Image.open(path) as raw:
        image = _fit_cover(raw.convert("RGB"), *size)
    _BACKGROUND_CACHE.clear()
    _BACKGROUND_CACHE.update(key=key, image=image)
    return image


#: Masks are keyed by size only, and every cell of a grid has the same size -
#: drawing the same rounded rectangle once per picture was pure repetition.
_MASK_CACHE: dict[tuple[int, int], Any] = {}


def _rounded_mask(size: tuple[int, int]):
    """Alpha mask with rounded corners, drawn oversized and scaled down so the
    curve stays smooth instead of showing the staircase of a 1:1 draw."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    cached = _MASK_CACHE.get(size)
    if cached is not None:
        return cached
    factor = 4
    big = (size[0] * factor, size[1] * factor)
    radius = round(min(big) * CORNER_RADIUS)
    mask = Image.new("L", big, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, big[0] - 1, big[1] - 1],
                                           radius=radius, fill=255)
    smooth = mask.resize(size, Image.LANCZOS)
    if len(_MASK_CACHE) > 16:          # a change of layout must not grow without bound
        _MASK_CACHE.clear()
    _MASK_CACHE[size] = smooth
    return smooth


def compose(layout: Layout, shot_paths: list[Path],
            background_path: Path | None = None,
            overlay_path: Path | None = None,
            title: str = "", subtitle: str = "",
            caption_font: str = "serif", caption_colour: str = "",
            caption_size_mm: float = 4.5,
            output_path: Path | None = None, jpeg_quality: int = 92) -> Path:
    """Background, photos, overlay, caption - in that order."""
    from PIL import Image  # noqa: PLC0415

    from .overlays import draw_caption  # noqa: PLC0415

    if len(shot_paths) < layout.shots:
        raise ValueError(f"{layout.id} braucht {layout.shots} Aufnahmen, "
                         f"bekommen hat es {len(shot_paths)}")

    # The sheet grows to the width of the shots. The area in the template is
    # only the lower bound for printing (10x15 cm at 600 dpi); if the shots
    # are larger, scaling them down would be pure loss. Especially for the
    # borderless single picture: nothing but the photograph is on that sheet,
    # and 3888x2592 down to 3600x2400 throws away a seventh of the width for
    # nothing.
    #
    # Growing to fit rather than a second constant that has to match
    # capture_size: pairs like that have already drifted apart twice today.
    canvas_size = layout.canvas
    breiteste = 0
    for pfad in shot_paths[:layout.shots]:
        try:
            with Image.open(pfad) as roh:
                breiteste = max(breiteste, roh.width)
        except OSError:
            continue
    if breiteste > canvas_size[0]:
        canvas_size = (breiteste, round(breiteste * layout.canvas[1] / layout.canvas[0]))
    canvas = Image.new("RGB", canvas_size, layout.background_colour)

    if background_path and Path(background_path).exists() and not layout.full_bleed:
        canvas.paste(_background_image(Path(background_path), canvas_size), (0, 0))

    for frame, path in zip(layout.frames, shot_paths):
        x, y, w, h = frame.px(canvas_size)
        tile = _load_fitted(Path(path), w, h)
        # A picture sitting on a background gets rounded corners; a full
        # bleed print has no background to round against.
        canvas.paste(tile, (x, y), None if layout.full_bleed else _rounded_mask((w, h)))

    if overlay_path and Path(overlay_path).exists():
        with Image.open(overlay_path) as raw:
            overlay = raw.convert("RGBA")
            if overlay.size != canvas_size:
                overlay = overlay.resize(canvas_size, Image.LANCZOS)
            canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")

    if layout.text_area is not None and (title or subtitle):
        dpi = canvas_size[0] / (PAPER_MM[0] / 25.4)
        draw_caption(canvas, layout.text_area.px(canvas_size), title, subtitle,
                     font_style=caption_font, colour=caption_colour,
                     size_mm=caption_size_mm, dpi=dpi)

    output_path = Path(output_path) if output_path else Path(f"{layout.id}.jpg")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "JPEG", quality=jpeg_quality, optimize=True)
    log.info("Composed %s -> %s %s", layout.id, output_path.name, canvas.size)
    return output_path


def prepare_for_print(layout: Layout, image_path: Path,
                      output_path: Path | None = None) -> Path:
    """Lay the finished picture out for the sheet.

    Only here may a picture be repeated across the paper. Everything that is
    kept, copied or uploaded stays the single picture the guests approved.
    """
    from PIL import Image  # noqa: PLC0415

    if layout.print_copies_across <= 1:
        return Path(image_path)

    with Image.open(image_path) as single:
        single = single.convert("RGB")
        sheet = Image.new("RGB", (single.width * layout.print_copies_across, single.height),
                          layout.background_colour)
        for index in range(layout.print_copies_across):
            sheet.paste(single, (index * single.width, 0))
    output_path = Path(output_path) if output_path else Path(image_path).with_name(
        Path(image_path).stem + "-druck.jpg")
    sheet.save(output_path, "JPEG", quality=92, optimize=True)
    return output_path
