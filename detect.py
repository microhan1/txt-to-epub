"""Encoding detection and decoding for txt-to-epub.

Order of trust: a byte-order mark, then a strict UTF-8 decode, then
charset-normalizer for the legacy code pages (EUC-KR/CP949, Shift_JIS,
GB18030, Big5, ...). CP949 is a superset of EUC-KR, so anything detected as
EUC-KR is decoded as CP949; the extended Hangul that EUC-KR lacks is common
in Korean text files and would otherwise turn into replacement characters.
"""
from __future__ import annotations

import codecs
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
                 "gb18030": "GB18030", "big5": "Big5", "latin-1": "Latin-1"}

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


def _bom(data: bytes) -> str | None:
    if data.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if data.startswith(codecs.BOM_UTF16_LE):
        return "utf-16"
    if data.startswith(codecs.BOM_UTF16_BE):
        return "utf-16"
    return None


def _looks_utf16(data: bytes) -> str | None:
    """UTF-16 without a BOM shows up as NUL bytes in every other position."""
    head = data[:4096]
    if len(head) < 4:
        return None
    even_nul = sum(1 for b in head[0::2] if b == 0)
    odd_nul = sum(1 for b in head[1::2] if b == 0)
    half = len(head) // 2
    if odd_nul > half * 0.3 and even_nul < half * 0.05:
        return "utf-16-le"
    if even_nul > half * 0.3 and odd_nul < half * 0.05:
        return "utf-16-be"
    return None


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
        sample.decode("utf-8")
        return Detection("utf-8", 100 if len(data) <= SAMPLE_BYTES else 99)
    except UnicodeDecodeError:
        pass
    # A strict CP949 decode of the whole sample is stronger evidence than any
    # statistical guess for Korean text, which is what this tool mostly sees.
    cp949_bad = _bad_count(sample, "cp949")
    cp949_ok = cp949_bad == 0
    # A few damaged bytes must not disqualify CP949: 1% of the sample, at least 2.
    cp949_near = cp949_bad <= max(2, int(len(sample) * NEAR_VALID))
    guess = _normalizer_guess(sample)
    if guess is None:
        if cp949_ok:
            return Detection("cp949", 75)
        return Detection("cp949", _near_conf(cp949_bad, len(sample))) if cp949_near else Detection("utf-8", 0)
    enc, conf = guess
    if enc == "cp949":
        return Detection(enc, max(conf, 90) if cp949_ok else min(conf, 60))
    if cp949_ok and enc in _OTHER_DBCS and conf < 85:
        # charset-normalizer is unsure and the bytes are valid CP949: prefer Korean
        return Detection("cp949", 70)
    if not cp949_ok and cp949_near and enc != "utf-8":
        # A Korean file with a few damaged bytes: charset-normalizer wanders off
        # to another code page. If that guess is no cleaner than CP949, keep
        # CP949 and let the damaged bytes show as U+FFFD.
        if _bad_count(sample, enc) >= cp949_bad:
            return Detection("cp949", _near_conf(cp949_bad, len(sample)))
    return Detection(enc, conf)


NEAR_VALID = 0.01            # up to 1% undecodable bytes still counts as "nearly valid"
_OTHER_DBCS = ("shift_jis", "euc-jp", "gb18030", "big5", "latin-1")


def _near_conf(bad: int, size: int) -> int:
    """Confidence for CP949 text with a few damaged bytes: 85 when fewer than
    one byte in a thousand is bad, otherwise 60 (below LOW_CONFIDENCE, so the
    GUI asks the user to look)."""
    return 85 if bad * 1000 <= size else 60


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
