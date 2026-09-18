#!/usr/bin/env python3
"""
Prepare a photo as the site's portrait: images/profile.webp

    python3 scripts/make_portrait.py path/to/photo.jpg
    python3 scripts/make_portrait.py path/to/photo.jpg --focus 0.4   # face higher in the frame

The same treatment is applied every time, so a new photo will match the site:

  1. crop to 4:5 around the centre (or the --focus point),
  2. a light colour grade toward the site's slate/petrol palette,
  3. an oval shape with a soft, fading edge.

Needs Pillow:  pip install pillow
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "images" / "profile.webp"

W, H = 800, 1000            # 4:5
PETROL = (0x37, 0x7D, 0x8E)

# The grade. Nudge these if a photo needs more or less.
SATURATION = 0.88           # 1.0 = unchanged
RED_GAIN, BLUE_GAIN = 0.97, 1.03   # slightly cooler white balance
PETROL_WASH = 0.06          # share of petrol blended in
BRIGHTNESS = 1.03

EDGE_INSET = 28             # px the oval sits inside the frame
EDGE_SOFTNESS = 22          # blur radius of the fading edge


def crop_4_5(im: Image.Image, focus: float) -> Image.Image:
    """Centre-crop to 4:5. focus = vertical position of the crop centre (0 top … 1 bottom)."""
    w, h = im.size
    if w / h > 4 / 5:                       # too wide: trim sides
        new_w = int(h * 4 / 5)
        left = (w - new_w) // 2
        return im.crop((left, 0, left + new_w, h))
    new_h = int(w * 5 / 4)                  # too tall: trim top/bottom around the focus
    top = int(max(0, min(h - new_h, focus * h - new_h / 2)))
    return im.crop((0, top, w, top + new_h))


def grade(im: Image.Image) -> Image.Image:
    im = ImageEnhance.Color(im).enhance(SATURATION)
    r, g, b = im.split()
    r = r.point(lambda v: int(v * RED_GAIN))
    b = b.point(lambda v: min(255, int(v * BLUE_GAIN)))
    im = Image.merge("RGB", (r, g, b))
    im = Image.blend(im, Image.new("RGB", im.size, PETROL), PETROL_WASH)
    return ImageEnhance.Brightness(im).enhance(BRIGHTNESS)


def oval_fade(im: Image.Image) -> Image.Image:
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).ellipse((EDGE_INSET, EDGE_INSET, W - EDGE_INSET, H - EDGE_INSET), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(EDGE_SOFTNESS))
    out = im.convert("RGBA")
    out.putalpha(mask)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photo", help="source photo (jpg, png, heic if Pillow supports it)")
    ap.add_argument("--focus", type=float, default=0.5,
                    help="vertical position of the face in the source, 0 = top, 1 = bottom (default 0.5)")
    ap.add_argument("--out", default=str(OUTPUT), help=f"output file (default {OUTPUT.relative_to(ROOT)})")
    args = ap.parse_args()

    im = Image.open(args.photo)
    im = ImageOps.exif_transpose(im).convert("RGB")
    im = crop_4_5(im, args.focus).resize((W, H), Image.LANCZOS)
    im = oval_fade(grade(im))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    im.save(args.out, quality=86, method=6)
    print(f"wrote {args.out} ({Path(args.out).stat().st_size // 1024} kB)")


if __name__ == "__main__":
    main()
