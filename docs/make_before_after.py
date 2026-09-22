"""Draw docs/before_after.png: the EUC-KR sample as a reader shows it when the
encoding is wrong (left) and as the EPUB made by this tool shows it (right).

    python docs/make_before_after.py
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import cover  # noqa: E402  (font lookup)

W, H = 1200, 720
PANEL_W = 530
SRC = os.path.join(os.path.dirname(HERE), "samples", "euc-kr.txt")


def main() -> None:
    raw = open(SRC, "rb").read()
    # What a reader that assumes Latin-1/UTF-8 shows for CP949 bytes.
    broken = raw.decode("latin-1")
    good = raw.decode("cp949")
    font_path = cover._find_font("ko")
    title_font = ImageFont.truetype(font_path, 26)
    body_font = ImageFont.truetype(font_path, 20)
    small_font = ImageFont.truetype(font_path, 16)

    img = Image.new("RGB", (W, H), (245, 245, 247))
    d = ImageDraw.Draw(img)
    for x, label, text, sub in ((40, "TXT (EUC-KR) as a reader shows it", broken, "encoding not recognised"),
                                (W - PANEL_W - 40, "EPUB made by txt-to-epub", good, "EUC-KR detected, chapters split")):
        d.rounded_rectangle([x, 70, x + PANEL_W, H - 40], radius=14, fill=(255, 255, 255), outline=(200, 200, 205), width=2)
        d.text((x, 28), label, fill=(30, 30, 30), font=title_font)
        d.text((x + 20, 88), sub, fill=(120, 120, 125), font=small_font)
        y = 120
        for line in text.splitlines()[:26]:
            while line and d.textlength(line, font=body_font) > PANEL_W - 40:
                line = line[:-1]
            d.text((x + 20, y), line, fill=(40, 40, 40), font=body_font)
            y += 23
    arrow_font = ImageFont.truetype(font_path, 44)
    aw = d.textlength(chr(0x2192), font=arrow_font)
    d.text(((W - aw) / 2, H / 2 - 30), chr(0x2192), fill=(60, 120, 60), font=arrow_font)
    out = os.path.join(HERE, "before_after.png")
    img.save(out, optimize=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
