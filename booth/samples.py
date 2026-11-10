"""Four sample pictures for the settings preview.

A host sets the booth up before anyone has been photographed, so the preview
cannot use real captures. These stand-ins are deliberately stylised: they show
where a head lands in the frame without pretending to be a photograph.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

SIZE = (2304, 1296)          # same shape as a real capture

#: Four different tones and head positions, so a 2x2 grid does not look like
#: the same picture repeated four times.
_SAMPLES = [
    {"sky": (206, 214, 205), "floor": (150, 163, 150), "skin": (226, 196, 172),
     "shirt": (72, 84, 96), "x": .46, "scale": 1.00},
    {"sky": (224, 210, 190), "floor": (176, 156, 128), "skin": (232, 202, 176),
     "shirt": (110, 78, 66), "x": .58, "scale": .92},
    {"sky": (205, 213, 226), "floor": (146, 158, 176), "skin": (222, 190, 168),
     "shirt": (58, 70, 92), "x": .40, "scale": 1.06},
    {"sky": (226, 208, 212), "floor": (178, 152, 158), "skin": (234, 204, 182),
     "shirt": (92, 66, 78), "x": .54, "scale": .96},
]


def _draw_one(spec: dict, target: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFilter  # noqa: PLC0415

    width, height = SIZE
    image = Image.new("RGB", SIZE, spec["sky"])
    draw = ImageDraw.Draw(image)

    horizon = round(height * .62)
    draw.rectangle([0, horizon, width, height], fill=spec["floor"])

    cx = round(width * spec["x"])
    scale = spec["scale"]
    head_r = round(height * .17 * scale)
    head_cy = round(height * .40)

    # Shoulders first, head over them.
    shoulder_w = round(head_r * 3.1)
    shoulder_top = head_cy + round(head_r * 1.05)
    draw.ellipse([cx - shoulder_w, shoulder_top, cx + shoulder_w, height + head_r * 3],
                 fill=spec["shirt"])
    draw.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r],
                 fill=spec["skin"])

    image = image.filter(ImageFilter.GaussianBlur(radius=height * .004))
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, "JPEG", quality=86)
    return target


def sample_paths(cache_dir: Path) -> list[Path]:
    """The four sample pictures, drawn once and kept."""
    paths = []
    for index, spec in enumerate(_SAMPLES, 1):
        path = Path(cache_dir) / f"beispiel-{index}.jpg"
        if not path.exists():
            _draw_one(spec, path)
        paths.append(path)
    return paths
