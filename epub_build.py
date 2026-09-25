"""EPUB2 assembly for txt-to-epub. Shared by the GUI and the CLI.

Everything the two front ends need lives here: Options, loading and decoding
a text file, chapter detection, and writing the EPUB. The EPUB is EPUB 2
only (OPF 2.0 + NCX), the structure that stores such as upaper still check.
"""
from __future__ import annotations

import codecs
import datetime as _dt
import os
import re
import threading
import uuid
import zipfile
from dataclasses import dataclass, field
from string import Template
from xml.sax.saxutils import escape, quoteattr

import chapters as chap
import cover as cover_mod
import detect
from chapters import Chapter, Section
from i18n import resource_dir

TEXT_LANGS = ("ko", "en", "zh", "ja")
LINE_HEIGHTS = ("", "1.4", "1.6", "1.8")
COVER_MODES = ("none", "file", "auto")
LANG_AUTO = "auto"

MAX_TITLE_CHARS = 300
TEXT_EXTS = (".txt",)


class Cancelled(Exception):
    """The user cancelled; no output file was written."""


@dataclass
class Options:
    encoding: str = detect.AUTO
    pattern: str = chap.DEFAULT_PATTERN
    split_chapters: bool = True
    paragraph_mode: str = "auto"
    text_lang: str = LANG_AUTO          # "auto" picks by script; else ko/en/zh/ja
    author: str = ""
    publisher: str = ""
    cover_mode: str = "none"
    cover_path: str = ""
    indent: bool = True
    line_height: str = ""

    def validated(self) -> "Options":
        o = Options(**self.__dict__)
        if o.encoding not in detect.ENCODINGS:
            try:
                codecs.lookup(o.encoding)
            except (LookupError, TypeError):
                o.encoding = detect.AUTO
        try:
            chap.compile_pattern(o.pattern)
        except chap.BadPattern:
            o.pattern = chap.DEFAULT_PATTERN
        if not o.pattern.strip():
            o.pattern = chap.DEFAULT_PATTERN
        if o.paragraph_mode not in chap.PARAGRAPH_MODES:
            o.paragraph_mode = "auto"
        if o.text_lang not in TEXT_LANGS + (LANG_AUTO,):
            o.text_lang = LANG_AUTO
        if o.cover_mode not in COVER_MODES:
            o.cover_mode = "none"
        if o.line_height not in LINE_HEIGHTS:
            o.line_height = ""
        o.author = o.author.strip()[:MAX_TITLE_CHARS]
        o.publisher = o.publisher.strip()[:MAX_TITLE_CHARS]
        o.split_chapters = bool(o.split_chapters)
        o.indent = bool(o.indent)
        return o


@dataclass
class Loaded:
    path: str
    size: int
    detection: detect.Detection
    encoding: str          # what was actually used to decode
    text: str
    lines: list[str]
    replaced: int          # undecodable characters replaced with U+FFFD


@dataclass
class FileResult:
    output_path: str
    chapters: int          # heading chapters (what the user sees as "N chapters")
    files: int             # XHTML files written (more than sections when a chapter was split)
    replaced: int
    no_chapters: bool
    cover_small: bool = False
    text_lang: str = ""
    nav: int = 0           # NCX entries (chapters plus a front section, if any)


# --- loading ----------------------------------------------------------------

def collect_txts(paths: list[str]) -> list[str]:
    """Expand folders recursively, keep .txt of any case, drop duplicates."""
    out: list[str] = []
    seen: set[str] = set()

    def add(p: str) -> None:
        key = os.path.normcase(os.path.abspath(p))
        if key not in seen:
            seen.add(key)
            out.append(os.path.abspath(p))

    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs.sort()
                for name in sorted(files):
                    if name.lower().endswith(TEXT_EXTS):
                        add(os.path.join(root, name))
        elif os.path.isfile(p) and p.lower().endswith(TEXT_EXTS):
            add(p)
    return out


def load_text(path: str, encoding: str = detect.AUTO) -> Loaded:
    """Read and decode. Raises detect.EmptyFile, OSError, LookupError."""
    size = os.path.getsize(path)
    text, det, replaced = detect.read_file(path, encoding)
    used = det.encoding if encoding == detect.AUTO else encoding
    return Loaded(path, size, det, used, text, chap.normalize(text), replaced)


def default_title(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


_HANGUL = re.compile("[\uac00-\ud7a3\u3131-\u318e]")
_KANA = re.compile("[\u3040-\u30ff]")
_HAN = re.compile("[\u4e00-\u9fff\u3400-\u4dbf]")
_LATIN = re.compile("[A-Za-z]")


def guess_text_lang(text: str) -> str:
    """Pick ko/ja/zh/en from the script used in the first part of the text."""
    sample = text[:20000]
    hangul, kana, han, latin = (len(rx.findall(sample)) for rx in (_HANGUL, _KANA, _HAN, _LATIN))
    total = hangul + kana + han + latin
    if total == 0:
        return "en"
    # Korean or Japanese novels quote English freely; English novels never
    # contain Hangul or kana. So a small share of those scripts decides.
    if hangul >= total * 0.05:
        return "ko"
    if kana >= total * 0.05:
        return "ja"
    if han >= total * 0.05:
        return "zh"
    return "en"


# --- naming -----------------------------------------------------------------

def output_path_for(input_path: str) -> str:
    """<name>.epub beside the input; (2), (3), ... if the name is taken, even by a folder."""
    return free_output_name(os.path.splitext(input_path)[0] + ".epub")


_NUMBERED = re.compile(r"^(.*)\((\d+)\)\.epub$", re.DOTALL)


def free_output_name(candidate: str) -> str:
    """First of candidate, base(2).epub, base(3).epub ... that does not exist."""
    m = _NUMBERED.match(candidate)
    base = m.group(1) if m else candidate[:-5]
    n = int(m.group(2)) + 1 if m else 2
    while os.path.lexists(candidate):
        candidate = f"{base}({n}).epub"
        n += 1
    return candidate


# --- templates --------------------------------------------------------------

_template_cache: dict[str, Template] = {}


def _template(name: str) -> Template:
    if name not in _template_cache:
        path = os.path.join(resource_dir(), "templates", name)
        with open(path, "r", encoding="utf-8") as f:
            _template_cache[name] = Template(f.read())
    return _template_cache[name]


def _xhtml(title: str, body: str, language: str) -> bytes:
    return _template("chapter.xhtml").substitute(title=escape(title), body=body, language=language).encode("utf-8")


def _paragraphs_html(paragraphs: list[str]) -> list[str]:
    return [f"  <p>{escape(p)}</p>" for p in paragraphs]


def _split_body(heading_html: str, para_html: list[str], limit: int) -> list[str]:
    """Group paragraph markup into bodies no larger than *limit* bytes each."""
    bodies: list[str] = []
    cur: list[str] = [heading_html] if heading_html else []
    size = len(heading_html.encode("utf-8"))
    for p in para_html:
        n = len(p.encode("utf-8")) + 1
        if cur and size + n > limit and any(x.startswith("  <p>") for x in cur):
            bodies.append("\n".join(cur))
            cur, size = [], 0
        cur.append(p)
        size += n
    if cur or not bodies:
        bodies.append("\n".join(cur))
    return bodies


# --- building ---------------------------------------------------------------

def build_epub(output_path: str, title: str, author: str, language: str, sections: list[Section],
               publisher: str = "", cover: cover_mod.CoverImage | None = None, indent: bool = True,
               line_height: str = "", progress=None, cancel: threading.Event | None = None,
               split_bytes: int = chap.CHAPTER_SPLIT_BYTES) -> tuple[str, int, int]:
    """Write the EPUB atomically. Returns (path written, nav entries, xhtml files)."""
    uid = str(uuid.uuid4())
    title = title.strip() or default_title(output_path)
    manifest: list[str] = []
    spine: list[str] = []
    navpoints: list[str] = []
    guide: list[str] = []
    files: list[tuple[str, bytes]] = []

    css = _template("style.css").substitute(
        indent="1em" if indent else "0",
        line_height=f" line-height: {line_height};" if line_height else "")
    files.append(("OEBPS/style.css", css.encode("utf-8")))

    if cover is not None:
        img_name = f"images/cover.{cover.ext}"
        files.append((f"OEBPS/{img_name}", cover.data))
        manifest.append(f'    <item id="cover-image" href="{img_name}" media-type="{cover.media_type}"/>')
        cover_html = _template("cover.xhtml").substitute(title=escape(title), alt=quoteattr(title),
                                                         image=img_name, language=language)
        files.append(("OEBPS/cover.xhtml", cover_html.encode("utf-8")))
        manifest.append('    <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>')
        spine.append('    <itemref idref="cover" linear="yes"/>')
        guide.append('    <reference type="cover" title="Cover" href="cover.xhtml"/>')

    play = 0
    total = max(len(sections), 1)
    for idx, sec in enumerate(sections, 1):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        tag = "h1" if not sec.heading else "h2"
        heading_html = f"  <{tag}>{escape(sec.title)}</{tag}>" if sec.title else ""
        bodies = _split_body(heading_html, _paragraphs_html(sec.paragraphs), split_bytes)
        for part, body in enumerate(bodies, 1):
            name = f"ch{idx:04d}.xhtml" if part == 1 else f"ch{idx:04d}-{part}.xhtml"
            fid = os.path.splitext(name)[0]
            files.append((f"OEBPS/{name}", _xhtml(sec.title or title, body, language)))
            manifest.append(f'    <item id="{fid}" href="{name}" media-type="application/xhtml+xml"/>')
            spine.append(f'    <itemref idref="{fid}"/>')
            if part == 1:
                play += 1
                label = escape(sec.title or title)
                navpoints.append(
                    f'    <navPoint id="np{play}" playOrder="{play}">\n'
                    f'      <navLabel><text>{label}</text></navLabel>\n'
                    f'      <content src="{name}"/>\n'
                    f'    </navPoint>')
        if progress:
            progress(idx, total)

    if guide and navpoints:
        guide.append(f'    <reference type="text" title="Text" href="ch0001.xhtml"/>')

    extra_meta = []
    if publisher.strip():
        extra_meta.append(f"    <dc:publisher>{escape(publisher.strip())}</dc:publisher>")
    if cover is not None:
        extra_meta.append('    <meta name="cover" content="cover-image"/>')

    opf = _template("content.opf").substitute(
        title=escape(title), author=escape(author.strip()), language=language, uid=uid,
        date=_dt.date.today().isoformat(), extra_meta="\n".join(extra_meta),
        manifest="\n".join(manifest), spine="\n".join(spine),
        guide=("  <guide>\n" + "\n".join(guide) + "\n  </guide>") if guide else "")
    ncx = _template("toc.ncx").substitute(uid=uid, title=escape(title), author=escape(author.strip()),
                                         navpoints="\n".join(navpoints))
    files.append(("OEBPS/content.opf", opf.encode("utf-8")))
    files.append(("OEBPS/toc.ncx", ncx.encode("utf-8")))

    if cancel is not None and cancel.is_set():
        raise Cancelled()
    written = _write_zip(output_path, files)
    return written, play, sum(1 for name, _ in files if name.endswith(".xhtml") and name != "OEBPS/cover.xhtml")


def _reserve_output(output_path: str) -> str:
    """Create the first free <name>.epub / <name>(n).epub exclusively and return it."""
    candidate = output_path
    while True:
        candidate = free_output_name(candidate)
        try:
            with open(candidate, "xb"):
                return candidate
        except FileExistsError:
            continue


def _write_zip(output_path: str, files: list[tuple[str, bytes]]) -> str:
    """mimetype first and stored, then everything else deflated. Written to a
    .part file in the same folder and renamed, so a crash never leaves a
    truncated .epub behind."""
    tmp = f"{output_path}.{os.getpid()}-{threading.get_ident()}.part"
    try:
        with zipfile.ZipFile(tmp, "w") as z:
            info = zipfile.ZipInfo("mimetype", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            z.writestr(info, b"application/epub+zip")
            z.writestr("META-INF/container.xml", _template("container.xml").template.encode("utf-8"),
                       compress_type=zipfile.ZIP_DEFLATED)
            for name, data in files:
                z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
        # Another run may have taken the name while this one was building:
        # claim the first free name atomically, then move the result onto it.
        final = _reserve_output(output_path)
        try:
            os.replace(tmp, final)
        except BaseException:
            try:
                os.remove(final)
            except OSError:
                pass
            raise
        return final
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


# --- one file, end to end ---------------------------------------------------

def plan_chapters(loaded: Loaded, opts: Options, title: str) -> list[Chapter]:
    if not opts.split_chapters:
        return chap.build_chapters(loaded.lines, [], title)
    return chap.detect_chapters(loaded.lines, opts.pattern, title)


def convert(loaded: Loaded, opts: Options, title: str = "", chapters: list[Chapter] | None = None,
            progress=None, cancel: threading.Event | None = None,
            output_path: str | None = None) -> FileResult:
    """Build one EPUB from an already loaded text.

    *chapters* lets the GUI pass the user-adjusted list; otherwise the pattern
    from *opts* is applied. Raises Cancelled, chapters.BadPattern, OSError.
    """
    opts = opts.validated()
    title = (title or default_title(loaded.path)).strip()[:MAX_TITLE_CHARS]
    if chapters is None:
        chapters = plan_chapters(loaded, opts, title)
    chapters = [c for c in chapters if c.enabled] if any(c.heading for c in chapters) else chapters
    if not any(c.heading for c in chapters):
        chapters = chap.build_chapters(loaded.lines, [], title)
    mode = chap.choose_paragraph_mode(loaded.lines, opts.paragraph_mode)
    sections = chap.sections_of(loaded.lines, chapters, mode)
    if not sections:
        sections = [Section(title, [], heading=False)]
    lang = opts.text_lang if opts.text_lang != LANG_AUTO else guess_text_lang(loaded.text)

    cover_img = None
    cover_small = False
    if opts.cover_mode == "file" and opts.cover_path:
        cover_img = cover_mod.load_cover(opts.cover_path)
        cover_small = cover_img.too_small
    elif opts.cover_mode == "auto":
        cover_img = cover_mod.make_cover(title, opts.author, lang)

    out = output_path or output_path_for(loaded.path)
    out, nav, nfiles = build_epub(out, title, opts.author, lang, sections, publisher=opts.publisher,
                             cover=cover_img, indent=opts.indent, line_height=opts.line_height,
                             progress=progress, cancel=cancel)
    headings = sum(1 for c in chapters if c.heading)
    return FileResult(out, headings, nfiles, loaded.replaced, headings == 0, cover_small, lang, nav)


def convert_file(path: str, opts: Options, title: str = "", progress=None,
                 cancel: threading.Event | None = None) -> FileResult:
    """CLI convenience: load, detect chapters, build."""
    loaded = load_text(path, opts.validated().encoding)
    return convert(loaded, opts, title, None, progress, cancel)
