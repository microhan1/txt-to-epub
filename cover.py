"""Cover handling for txt-to-epub: load a user image, or paint a plain
single-colour cover with the title and author.
"""
from __future__ import annotations

import hashlib
import io
import os
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

COVER_W, COVER_H = 800, 1200      # 2:3, inside the 600-1000 px width most stores ask for
MIN_COVER_WIDTH = 600             # smaller user images get a warning only
JPEG_QUALITY = 88

# Muted book-cover colours; picked by a hash of the title so the same book
# always gets the same cover.
_PALETTE = [
    (44, 62, 80), (52, 73, 94), (127, 140, 141), (39, 55, 70), (20, 90, 50),
    (108, 52, 131), (146, 43, 33), (183, 149, 11), (30, 132, 73), (17, 122, 101),
    (40, 55, 71), (110, 44, 0), (74, 35, 90), (21, 67, 96), (120, 40, 31),
]

# Fonts that can draw CJK. Ordered by text language; the first that exists wins.
_FONT_DIRS = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
              "/usr/share/fonts", "/usr/share/fonts/truetype", "/System/Library/Fonts", "/Library/Fonts"]
_FONTS_BY_LANG = {
    "ko": ["malgunbd.ttf", "malgun.ttf", "NotoSansKR-VF.ttf", "NanumGothicBold.ttf", "NanumGothic.ttf",
           "AppleSDGothicNeo.ttc", "NotoSansCJK-Bold.ttc"],
    "ja": ["YuGothB.ttc", "YuGothM.ttc", "meiryob.ttc", "meiryo.ttc", "msgothic.ttc", "NotoSansCJK-Bold.ttc"],
    "zh": ["msyhbd.ttc", "msyh.ttc", "simhei.ttf", "simsun.ttc", "NotoSansCJK-Bold.ttc"],
    "en": ["arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "Helvetica.ttc"],
}


@dataclass
class CoverImage:
    data: bytes
    media_type: str   # image/jpeg or image/png
    ext: str          # jpg or png
    width: int
    height: int

    @property
    def too_small(self) -> bool:
        return self.width < MIN_COVER_WIDTH


def _find_font(lang: str) -> str | None:
    names = list(_FONTS_BY_LANG.get(lang, [])) + [n for k, v in _FONTS_BY_LANG.items() if k != lang for n in v]
    for d in _FONT_DIRS:
        for n in names:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
    return None


def _font(path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover - Pillow < 10.1
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """Wrap by words when there are spaces, else by characters (CJK)."""
    lines: list[str] = []
    for raw in text.splitlines() or [text]:
        units = raw.split(" ") if " " in raw else list(raw)
        glue = " " if " " in raw else ""
        cur = ""
        for u in units:
            cand = (cur + glue + u) if cur else u
            if draw.textlength(cand, font=font) <= max_width or not cur:
                cur = cand
            else:
                lines.append(cur)
                cur = u
        if cur:
            lines.append(cur)
    return lines


def make_cover(title: str, author: str, lang: str = "ko") -> CoverImage:
    """Paint a plain-colour cover with the title and author. Always JPEG."""
    title = title.strip() or " "
    idx = int(hashlib.md5(title.encode("utf-8")).hexdigest(), 16) % len(_PALETTE)
    bg = _PALETTE[idx]
    img = Image.new("RGB", (COVER_W, COVER_H), bg)
    draw = ImageDraw.Draw(img)
    fpath = _find_font(lang)
    margin = int(COVER_W * 0.1)
    max_w = COVER_W - 2 * margin

    size = 72
    while size > 28:
        font = _font(fpath, size)
        lines = _wrap(draw, title, font, max_w)
        if len(lines) <= 6:
            break
        size -= 6
    font = _font(fpath, size)
    lines = _wrap(draw, title, font, max_w)[:8]
    line_h = int(size * 1.35)
    y = int(COVER_H * 0.30)
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((COVER_W - w) / 2, y), line, fill=(255, 255, 255), font=font)
        y += line_h
    # thin rule under the title
    draw.rectangle([margin, y + 20, COVER_W - margin, y + 23], fill=(255, 255, 255))
    if author.strip():
        afont = _font(fpath, 40)
        alines = _wrap(draw, author.strip(), afont, max_w)[:3]
        ay = y + 60
        for line in alines:
            w = draw.textlength(line, font=afont)
            draw.text(((COVER_W - w) / 2, ay), line, fill=(235, 235, 235), font=afont)
            ay += 54
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return CoverImage(buf.getvalue(), "image/jpeg", "jpg", COVER_W, COVER_H)


def load_cover(path: str) -> CoverImage:
    """Read a user-chosen image. JPEG and PNG are stored as they are; anything
    else is converted to JPEG so every EPUB2 reader can show it.

    Raises OSError / ValueError if the file is not an image.
    """
    with Image.open(path) as im:
        im.load()
        width, height = im.size
        fmt = (im.format or "").upper()
        if fmt in ("JPEG", "PNG"):
            with open(path, "rb") as f:
                data = f.read()
            return CoverImage(data, "image/jpeg" if fmt == "JPEG" else "image/png",
                              "jpg" if fmt == "JPEG" else "png", width, height)
        rgb = im.convert("RGB")
    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=JPEG_QUALITY)
    return CoverImage(buf.getvalue(), "image/jpeg", "jpg", width, height)
