"""Product pictures without their background (product page "poster", owner's video, 2026-11-27).

Shop photos are mostly studio shots on a plain white or light grey background. The background is whatever plain
colour touches the picture's edges: it is filled from the edges (a few steps of tolerance for soft shadows and JPEG
noise) and made transparent, the edge is softened by one pixel, and the picture is cut to the product. A photo whose
background is not plain (a scene, a box, a banner) is left as it is: None is returned and the page keeps the original.
Only Pillow is needed.
"""
from __future__ import annotations

import io

from PIL import Image, ImageChops, ImageDraw, ImageFilter

MARK = (1, 254, 3)  # a colour no product photo uses: where the fill reached
TOLERANCE = 34      # how far from the edge colour a pixel may be and still count as background


def _edge_colour(im: Image.Image) -> tuple[int, int, int]:
    w, h = im.size
    px = [im.getpixel((x, y)) for x in range(0, w, max(1, w // 40)) for y in (0, h - 1)]
    px += [im.getpixel((x, y)) for y in range(0, h, max(1, h // 40)) for x in (0, w - 1)]
    px.sort(key=sum)
    return px[len(px) // 2]


def cut(data: bytes, size: int = 900) -> bytes | None:
    """PNG bytes of the product on a transparent background, or None when the background is not plain."""
    im = Image.open(io.BytesIO(data))
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        flat = Image.new("RGBA", im.size, (255, 255, 255, 255))
        flat.alpha_composite(im)
        im = flat
    im = im.convert("RGB")
    im.thumbnail((size, size))
    edge = _edge_colour(im)
    if sum(edge) < 3 * 170:          # dark or coloured edges: a scene or a banner, not a studio background
        return None
    # one pixel of the edge colour all round, so one fill from a corner reaches every bit of background
    w, h = im.size
    work = Image.new("RGB", (w + 2, h + 2), edge)
    work.paste(im, (1, 1))
    ImageDraw.floodfill(work, (0, 0), MARK, thresh=TOLERANCE)
    work = work.crop((1, 1, w + 1, h + 1))
    # background = exactly the mark colour
    diff = ImageChops.difference(work, Image.new("RGB", work.size, MARK)).convert("L")
    alpha = diff.point(lambda v: 0 if v == 0 else 255)
    gone = alpha.histogram()[0] / (w * h)
    if gone < 0.08 or gone > 0.96:   # almost nothing or almost everything removed: not a plain background
        return None
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))  # no light halo, soft edge
    out = im.convert("RGBA")
    out.putalpha(alpha)
    box = alpha.point(lambda v: 255 if v > 24 else 0).getbbox()
    if not box:
        return None
    out = out.crop(box)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()
