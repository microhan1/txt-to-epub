"""Text normalisation, chapter detection and paragraph building for txt-to-epub.

A chapter heading is a line that *alone* matches the pattern (the whole line,
after trimming). Text before the first heading becomes a front section.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from i18n import resource_dir

# Heading patterns live in patterns.json (next to lang/), so the code stays
# ASCII and users can add their own presets. The built-in default matches:
#   Korean   je-N-jang / je-N-hwa / je-N-pyeon / je-N-bu / je-N-hoe, N-hwa, "N. title"
#   English  Chapter N / CHAPTER XII / Part N / Prologue / Epilogue
#   CJK      di-N-zhang / di-N-hua / di-N-hui (Arabic or Chinese numerals)
#   plus the prologue/epilogue words in Korean, Chinese and Japanese.
_PATTERNS_FILE = os.path.join(resource_dir(), "patterns.json")


def _load_patterns() -> tuple[str, tuple[str, ...]]:
    with open(_PATTERNS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    default = str(data["default"])
    presets = tuple(str(p) for p in data.get("presets", []))
    return default, (default,) + presets


DEFAULT_PATTERN, PRESET_PATTERNS = _load_patterns()

MAX_HEADING_CHARS = 80        # a "heading" longer than this is body text that happened to match
MANY_CHAPTERS = 500           # warn above this: the pattern is probably too broad
CHAPTER_SPLIT_BYTES = 1 << 20  # XHTML bigger than this is split for slow readers

PARAGRAPH_MODES = ("auto", "blank", "line")


class BadPattern(ValueError):
    """The user's regular expression does not compile."""


@dataclass
class Chapter:
    title: str
    start: int            # 0-based line index of the heading (or 0 for the front section)
    end: int              # exclusive line index
    chars: int
    heading: bool = True  # False for the front section (text before the first heading)
    enabled: bool = True
    manual: bool = False  # added by the user via line number


@dataclass
class Section:
    """What actually goes into one XHTML file: a title and its paragraphs."""
    title: str
    paragraphs: list[str] = field(default_factory=list)
    heading: bool = True  # False: front matter / whole-book section titled with the book title


def normalize(text: str) -> list[str]:
    """Split into lines with line endings unified, tabs/NBSP as spaces, trailing
    whitespace removed, and characters XML 1.0 forbids dropped (an old DOS text
    file often ends with 0x1A)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _BAD_XML_CHARS.sub("", text)
    text = text.replace("\t", "    ").replace("\u00a0", " ").replace("\u3000", " ")
    return [line.rstrip() for line in text.split("\n")]


_BAD_XML_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ufffe\uffff]")


def compile_pattern(pattern: str) -> re.Pattern:
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise BadPattern(str(exc)) from exc


def is_heading(line: str, rx: re.Pattern) -> bool:
    s = line.strip()
    if not s or len(s) > MAX_HEADING_CHARS:
        return False
    return rx.match(s) is not None


def detect_chapters(lines: list[str], pattern: str = DEFAULT_PATTERN, book_title: str = "") -> list[Chapter]:
    """Return chapters in text order. If no heading matches, one chapter that
    spans the whole text is returned (with heading=False)."""
    rx = compile_pattern(pattern)
    starts = [i for i, line in enumerate(lines) if is_heading(line, rx)]
    return build_chapters(lines, starts, book_title)


def build_chapters(lines: list[str], starts: list[int], book_title: str = "",
                   manual: set[int] | None = None) -> list[Chapter]:
    """Cut *lines* at the given heading line indexes."""
    manual = manual or set()
    starts = sorted({s for s in starts if 0 <= s < len(lines)})
    chapters: list[Chapter] = []
    if not starts:
        return [Chapter(book_title, 0, len(lines), _count_chars(lines, 0, len(lines)), heading=False)]
    if starts[0] > 0 and any(l.strip() for l in lines[: starts[0]]):
        chapters.append(Chapter(book_title, 0, starts[0], _count_chars(lines, 0, starts[0]), heading=False))
    for idx, s in enumerate(starts):
        e = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        title = lines[s].strip() or book_title
        chapters.append(Chapter(title, s, e, _count_chars(lines, s + 1, e), manual=s in manual))
    return chapters


def _count_chars(lines: list[str], start: int, end: int) -> int:
    return sum(len(l.strip()) for l in lines[start:end])


def heading_count(chapters: list[Chapter]) -> int:
    return sum(1 for c in chapters if c.heading and c.enabled)


def apply_selection(lines: list[str], chapters: list[Chapter], book_title: str = "") -> list[Chapter]:
    """Re-cut after the user toggled chapters: disabled headings merge into the
    previous chapter; manual ones stay."""
    starts = [c.start for c in chapters if c.heading and c.enabled]
    manual = {c.start for c in chapters if c.manual}
    return build_chapters(lines, starts, book_title, manual)


# --- paragraphs -------------------------------------------------------------

def choose_paragraph_mode(lines: list[str], mode: str = "auto") -> str:
    """'auto' picks blank-line paragraphs when the text uses blank lines at all
    (at least one blank line per 40 lines), otherwise one paragraph per line."""
    if mode in ("blank", "line"):
        return mode
    if not lines:
        return "line"
    blank = sum(1 for l in lines if not l.strip())
    return "blank" if blank * 40 >= len(lines) else "line"


_CJK_NO_SPACE = re.compile(r"[\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")


def _join(a: str, b: str) -> str:
    """Join two wrapped lines. Chinese and Japanese have no word spaces, so a
    line break between two Han/Kana characters is nothing; everywhere else
    (Korean included) it stood for a space."""
    if a and b and _CJK_NO_SPACE.match(a[-1]) and _CJK_NO_SPACE.match(b[0]):
        return a + b
    return a + " " + b


def paragraphs_of(lines: list[str], mode: str) -> list[str]:
    """Turn body lines into paragraphs. Leading/trailing blanks and runs of
    blank lines are collapsed; leading indentation is dropped."""
    out: list[str] = []
    if mode == "line":
        for line in lines:
            s = line.strip()
            if s:
                out.append(_collapse(s))
        return out
    buf = ""
    for line in lines:
        s = line.strip()
        if not s:
            if buf:
                out.append(_collapse(buf))
                buf = ""
            continue
        buf = _join(buf, s) if buf else s
    if buf:
        out.append(_collapse(buf))
    return out


_MULTI_SPACE = re.compile(r"[ ]{2,}")


def _collapse(s: str) -> str:
    return _MULTI_SPACE.sub(" ", s)


def sections_of(lines: list[str], chapters: list[Chapter], mode: str) -> list[Section]:
    """Build the sections that become XHTML files, skipping empty ones."""
    result: list[Section] = []
    for ch in chapters:
        body_start = ch.start + 1 if ch.heading else ch.start
        paras = paragraphs_of(lines[body_start: ch.end], mode)
        if not paras and not ch.heading:
            continue
        result.append(Section(ch.title, paras, heading=ch.heading))
    return result
