"""Draw the start-up picture assets/splash.png for the one-file exe (build.bat --splash).

    python tools/make_splash.py [assets/splash.png]

Same size and look as the other Chaekgalpi tools (TrimPDF): 300x104, a white card,
a small drawing and the tool's name. The only text is "txt-to-epub", which reads the
same in all four interface languages, so no translation is needed.
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFont

SCALE = 4                                   # drawn large, then shrunk for smooth edges
W, H = 300, 104
INK, ACCENT, RULE, PAGE = "#17202B", "#0F766E", "#D9E0E6", "#DDF0EC"
FONT = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeuib.ttf")


def main(path: str) -> None:
    s = SCALE
    img = Image.new("RGB", (W * s, H * s), "white")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W * s - 1, H * s - 1), outline=RULE, width=s)

    # a text page on the left: four lines of "text"
    x0, y0, x1, y1 = 24 * s, 26 * s, 56 * s, 78 * s
    d.rectangle((x0, y0, x1, y1), fill=PAGE, outline=INK, width=s)
    for k in range(4):
        yy = y0 + (10 + k * 10) * s
        d.rectangle((x0 + 6 * s, yy, x1 - (6 + (k == 3) * 10) * s, yy + 3 * s), fill=ACCENT)

    # an arrow in the middle
    ax, ay = 62 * s, 52 * s
    d.line((ax, ay, ax + 14 * s, ay), fill=INK, width=2 * s)
    d.polygon(((ax + 14 * s, ay - 5 * s), (ax + 14 * s, ay + 5 * s), (ax + 20 * s, ay)), fill=INK)

    # an open book on the right: two pages with a spine
    bx0, by0, bx1, by1 = 90 * s, 28 * s, 134 * s, 76 * s
    mid = (bx0 + bx1) // 2
    d.rounded_rectangle((bx0, by0, bx1, by1), radius=3 * s, fill="white", outline=INK, width=s)
    d.line((mid, by0, mid, by1), fill=INK, width=s)
    for k in range(3):
        yy = by0 + (10 + k * 11) * s
        d.rectangle((bx0 + 6 * s, yy, mid - 5 * s, yy + 3 * s), fill=ACCENT)
        d.rectangle((mid + 5 * s, yy, bx1 - 6 * s, yy + 3 * s), fill=ACCENT)

    font = ImageFont.truetype(FONT, 28 * s)
    d.text((148 * s, 52 * s), "txt-to-epub", font=font, fill=INK, anchor="lm")
    img.resize((W, H), Image.LANCZOS).save(path, optimize=True)
    print(path, os.path.getsize(path), "bytes")


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "assets", "splash.png"))
