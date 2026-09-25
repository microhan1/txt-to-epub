"""Encoding detection and decoding for txt-to-epub.

Order of trust: a byte-order mark, then a strict UTF-8 decode, then
charset-normalizer for the legacy code pages (EUC-KR/CP949, Shift_JIS,
GB18030, Big5, ...). CP949 is a superset of EUC-KR, so anything detected as
EUC-KR is decoded as CP949; the extended Hangul that EUC-KR lacks is common
in Korean text files and would otherwise turn into replacement characters.
"""
from __future__ import annotations

import codecs
import re
import threading
from dataclasses import dataclass

AUTO = "auto"

# Encodings the user may force. The first entry is the auto mode.
ENCODINGS = (AUTO, "utf-8", "utf-8-sig", "cp949", "euc-kr", "utf-16", "utf-16-le", "utf-16-be",
             "shift_jis", "euc-jp", "gb18030", "big5", "latin-1")

# How detected names are shown and which codec actually decodes them.
_CANONICAL = {
    "utf_8": "utf-8", "utf8": "utf-8", "ascii": "utf-8",
    "euc_kr": "cp949", "euckr": "cp949", "cp949": "cp949", "ks_c_5601-1987": "cp949", "uhc": "cp949",
    "utf_16": "utf-16", "utf_16_le": "utf-16-le", "utf_16_be": "utf-16-be",
    "shift_jis": "shift_jis", "sjis": "shift_jis", "cp932": "shift_jis", "mskanji": "shift_jis",
    "euc_jp": "euc-jp", "eucjp": "euc-jp",
    "gb2312": "gb18030", "gbk": "gb18030", "gb18030": "gb18030", "cp936": "gb18030",
    "big5": "big5", "cp950": "big5", "big5hkscs": "big5",
    "latin_1": "latin-1", "iso8859_1": "latin-1", "cp1252": "latin-1",
}
DISPLAY_NAMES = {"cp949": "EUC-KR / CP949", "utf-8": "UTF-8", "utf-8-sig": "UTF-8 (BOM)",
                 "utf-16": "UTF-16", "utf-16-le": "UTF-16 LE", "utf-16-be": "UTF-16 BE",
                 "euc-kr": "EUC-KR", "shift_jis": "Shift_JIS", "euc-jp": "EUC-JP",
                 "gb18030": "GB18030", "big5": "Big5", "latin-1": "Latin-1",
                 "euc_jis_2004": "EUC-JP", "cp932": "Shift_JIS"}

LOW_CONFIDENCE = 70          # below this the GUI shows the preview with a red border
SAMPLE_BYTES = 1 << 20       # detection looks at the first 1 MB only; enough for any code page
WARN_SIZE = 100 * 1024 * 1024


class EmptyFile(Exception):
    """The file has no content (0 bytes, or only a BOM / whitespace)."""


@dataclass
class Detection:
    encoding: str      # codec name usable with bytes.decode()
    confidence: int    # 0-100

    @property
    def display(self) -> str:
        return DISPLAY_NAMES.get(self.encoding, self.encoding)


def canonical(name: str) -> str:
    key = name.lower().replace("-", "_")
    return _CANONICAL.get(key, name.lower())


def display_name(encoding: str) -> str:
    return DISPLAY_NAMES.get(encoding, encoding)


def _trim_partial_tail(sample: bytes) -> bytes:
    """Drop a multibyte character that the sample cut in half at its end, so
    the legacy code pages are not blamed for one bogus error."""
    for enc in ("cp949", "shift_jis", "gb18030", "big5", "euc-jp"):
        try:
            sample.decode(enc)
            return sample
        except UnicodeDecodeError as exc:
            if exc.start >= len(sample) - 4:
                return sample[: exc.start]
    return sample


def _bom(data: bytes) -> str | None:
    if data.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if data.startswith(codecs.BOM_UTF16_LE):
        return "utf-16"
    if data.startswith(codecs.BOM_UTF16_BE):
        return "utf-16"
    return None


_PLAUSIBLE = re.compile("[\t\r\n\x20-\x7e\u00c0-\u024f\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff"
                        "\uac00-\ud7a3\uf900-\ufaff\uff00-\uffef]")
# Letters and CJK only: Latin-1 symbols (U+00A0-00BF) and general punctuation are
# what the wrong endianness of Hangul bytes decodes to, so they do not count.


def _looks_utf16(data: bytes) -> str | None:
    """UTF-16 without a BOM: every ASCII character contributes a NUL byte, so
    a text with no NULs at all is not UTF-16. Which endianness is right is
    decided by decoding both ways: the wrong one yields code points all over
    the map (or fails outright), the right one yields ordinary text."""
    head = data[:4096]
    head = head[: len(head) - len(head) % 2]
    if len(head) < 4 or head.count(b"\x00") < max(2, len(head) * 0.01):
        return None
    best, best_score = None, 0.0
    for enc in ("utf-16-le", "utf-16-be"):
        try:
            text = head.decode(enc)
        except UnicodeDecodeError:
            continue
        if not text:
            continue
        score = len(_PLAUSIBLE.findall(text)) / len(text)
        if score > best_score:
            best, best_score = enc, score
    return best if best_score >= 0.9 else None


def detect(data: bytes) -> Detection:
    """Guess the encoding of *data*. Never raises; falls back to UTF-8 at 0%."""
    if not data:
        return Detection("utf-8", 100)
    bom = _bom(data)
    if bom:
        return Detection(bom, 100)
    sample = data[:SAMPLE_BYTES]
    utf16 = _looks_utf16(sample)
    if utf16:
        return Detection(utf16, 95)
    try:
        data.decode("utf-8")  # whole file: a sample cut inside a multibyte character would fail wrongly
        return Detection("utf-8", 100)
    except UnicodeDecodeError:
        pass
    if len(sample) < len(data):
        sample = _trim_partial_tail(sample)
    # A strict CP949 decode of the whole sample is stronger evidence than any
    # statistical guess for Korean text, which is what this tool mostly sees.
    cp949_text, cp949_bad = _try_decode(sample, "cp949")
    cp949_ok = cp949_bad == 0
    # A few damaged bytes must not disqualify CP949: 1% of the sample, at least 2.
    cp949_near = cp949_bad <= max(2, int(len(sample) * NEAR_VALID))
    korean = _looks_korean(cp949_text)
    if cp949_near and korean is True:
        # Real Korean text: the CP949 decoding is full of the everyday syllables.
        return Detection("cp949", 90 if cp949_ok else _near_conf(cp949_bad, len(sample)))
    guess = _normalizer_guess(sample)
    if guess is not None and guess[0].startswith(("utf-16", "utf-32", "utf_16", "utf_32")):
        guess = None  # no NUL pattern was found above, so a UTF-16/32 guess on a short sample is noise
    if guess is None:
        if cp949_near and korean is None:
            return Detection("cp949", 75 if cp949_ok else _near_conf(cp949_bad, len(sample)))
        alt = _cjk_alternative(sample)
        return alt or Detection("utf-8", 0)
    enc, conf = guess
    if cp949_near and not _is_multibyte(enc):
        # Valid double-byte text never becomes a single-byte code page such as
        # iso8859-x or cp125x; that guess is noise from an unusual sample.
        if korean is False:
            return _cjk_alternative(sample) or Detection("cp949", 60)
        return Detection("cp949", (90 if korean else 75) if cp949_ok else _near_conf(cp949_bad, len(sample)))
    if enc == "cp949":
        if korean is False:
            # Valid CP949 bytes that read as random syllables and Hanja: this is
            # Chinese or Japanese in an EUC code page that shares the byte ranges.
            alt = _cjk_alternative(sample)
            if alt is not None:
                return alt
        return Detection(enc, max(conf, 90) if cp949_ok else min(conf, 60))
    if cp949_ok and korean is None and enc in _OTHER_DBCS and conf < 85:
        # too little text to judge and charset-normalizer is unsure: prefer
        # Korean, but stay under LOW_CONFIDENCE so the preview gets flagged
        return Detection("cp949", 60)
    if not cp949_ok and cp949_near and korean is None and enc != "utf-8":
        if _bad_count(sample, enc) >= cp949_bad:
            return Detection("cp949", _near_conf(cp949_bad, len(sample)))
    return Detection(enc, conf)


NEAR_VALID = 0.01            # up to 1% undecodable bytes still counts as "nearly valid"
_OTHER_DBCS = ("shift_jis", "euc-jp", "gb18030", "big5", "latin-1")
MIN_SYLLABLES = 8            # fewer Hangul syllables than this and the Korean test abstains
COMMON_SHARE = 0.15          # Korean prose scores 0.35-0.75; CJK misread as CP949 scores ~0.02

# The most frequent Korean syllables (particles, endings, common stems). Their
# share among all Hangul syllables is high for any Korean prose and near zero
# for Chinese or Japanese bytes decoded as CP949.
_COMMON_SYLLABLES = frozenset(
    "\ub2e4\uc774\ub294\uc744\uc5d0\uc758\uac00\ud558\uace0\uc9c0\ub97c\uc740\ub85c\uc5b4\uadf8"
    "\ud55c\uc11c\uae30\ub3c4\ub098\uc0ac\ub9ac\uac83\ub2c8\uac8c\uc544\uc788\ub300\uc790\uc2dc"
    "\uc778\uc218\ub418\ub9cc\ub4e4\uc5c6\uc73c\uc57c\uc694\uc5ec\ub2e8\uc740\uc774\uc9c0\ub3c4")
_SYLLABLE = re.compile("[\uac00-\ud7a3]")
_KANA_RX = re.compile("[\u3040-\u30ff]")
_HAN_RX = re.compile("[\u4e00-\u9fff\u3400-\u4dbf]")


def _is_multibyte(enc: str) -> bool:
    return enc in _OTHER_DBCS or enc.startswith(("cp949", "euc", "utf", "gb", "big5", "shift", "cp932", "cp936", "cp950"))


def _looks_korean(text: str) -> bool | None:
    """True when the everyday syllables are common enough, False when they are
    rare *and* there is other evidence (a Hanja-heavy mix, or plenty of text),
    None when the text is too short to say. Short Korean lines can miss the
    common syllables by chance, so "False" needs the extra evidence."""
    head = text[:200000]
    syllables = _SYLLABLE.findall(head)
    if len(syllables) < MIN_SYLLABLES:
        return None
    share = sum(1 for c in syllables if c in _COMMON_SYLLABLES) / len(syllables)
    if share >= COMMON_SHARE:
        return True
    hanja = len(_HAN_RX.findall(head))
    # Misread Chinese or Japanese spreads over many different syllables (the
    # bytes are effectively random); real Korean, even a repetitive one, does not.
    spread = len(set(syllables)) >= len(syllables) * 0.3
    if share < COMMON_SHARE / 2 and (hanja >= len(syllables) * 0.2 or (spread and len(syllables) >= 40)):
        return False
    return None


def _cjk_alternative(sample: bytes) -> Detection | None:
    """Pick a Japanese or Chinese code page for bytes that are valid but not
    Korean. Japanese always shows kana; Chinese shows none."""
    for enc in ("euc-jp", "shift_jis", "gb18030", "big5"):
        text, bad = _try_decode(sample, enc)
        if bad:
            continue
        kana = len(_KANA_RX.findall(text))
        han = len(_HAN_RX.findall(text))
        if kana + han == 0:
            continue
        japanese = kana / (kana + han) >= 0.05
        if enc in ("euc-jp", "shift_jis") and japanese:
            return Detection(enc, 70)
        if enc in ("gb18030", "big5") and not japanese:
            return Detection(enc, 70)
    return None


def _near_conf(bad: int, size: int) -> int:
    """Confidence for CP949 text with a few damaged bytes: 85 when at most one
    byte in a thousand (or a single damaged spot, which costs up to 3 errors)
    is bad, otherwise 60 (below LOW_CONFIDENCE, so the GUI asks the user to look)."""
    return 85 if bad <= max(3, size // 1000) else 60


def _try_decode(data: bytes, encoding: str) -> tuple[str, int]:
    try:
        return decode(data, encoding)
    except LookupError:
        return "", len(data)


def _bad_count(data: bytes, encoding: str) -> int:
    """Number of undecodable positions (0 = strictly valid)."""
    try:
        _, bad = decode(data, encoding)
    except LookupError:
        return len(data)
    return bad


def _normalizer_guess(sample: bytes) -> tuple[str, int] | None:
    try:
        from charset_normalizer import from_bytes
    except ImportError:  # pragma: no cover - dependency missing
        return None
    try:
        best = from_bytes(sample).best()
    except Exception:  # pragma: no cover - library internals
        return None
    if best is None:
        return None
    enc = canonical(best.encoding)
    # chaos is the share of "mess" in the decoded text; coherence how much it
    # looks like a real language. Both are 0..1.
    conf = int(round((1.0 - float(best.chaos)) * 100))
    if best.coherence < 0.2:
        conf = min(conf, 75)
    return enc, max(0, min(100, conf))


# --- decoding with a replacement-character count --------------------------

_local = threading.local()


def _count_replace(exc: UnicodeError):
    if not isinstance(exc, UnicodeDecodeError):
        raise exc
    _local.count = getattr(_local, "count", 0) + 1
    return "\ufffd", exc.end


codecs.register_error("txt2epub_count", _count_replace)


def decode(data: bytes, encoding: str) -> tuple[str, int]:
    """Decode *data*; return (text, number of undecodable characters replaced)."""
    _local.count = 0
    text = data.decode(encoding, errors="txt2epub_count")
    bad = _local.count
    _local.count = 0
    if text.startswith("\ufeff"):
        text = text[1:]
    return text, bad


def read_file(path: str, encoding: str = AUTO) -> tuple[str, Detection, int]:
    """Read *path* fully. Returns (text, detection, replaced_count).

    Raises EmptyFile for an empty file and OSError if it cannot be read.
    """
    with open(path, "rb") as f:
        data = f.read()
    if not data.strip(b"\x00\t\r\n \xef\xbb\xbf\xff\xfe\x1a"):
        raise EmptyFile(path)
    det = detect(data)
    enc = det.encoding if encoding == AUTO else encoding
    text, bad = decode(data, enc)
    if not text.strip():
        raise EmptyFile(path)
    return text, det, bad
