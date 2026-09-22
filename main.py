"""Entry point for txt-to-epub.

    python main.py                                   -> GUI
    python main.py novel.txt [more.txt ...]          -> CLI
    python main.py novel.txt --encoding auto --chapter-pattern REGEX \\
                   --title TITLE --author AUTHOR --lang ko [--cover cover.jpg]

--lang is the language of the *text* (dc:language in the EPUB), as the PRD
specifies. The interface language is --ui-lang.
"""
from __future__ import annotations

import argparse
import codecs
import os
import sys

import chapters as chap
import detect
import epub_build as core
import i18n
from i18n import t


def _preselect_lang(argv: list[str]) -> str | None:
    """--ui-lang has to be known before the parser is built, so help is translated."""
    for i, a in enumerate(argv):
        if a == "--ui-lang" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--ui-lang="):
            return a.split("=", 1)[1]
    return None


def _localize_argparse() -> None:
    """argparse's own labels go through gettext; route them to lang files."""
    table = {
        "usage: ": t("cli_usage"),
        "positional arguments": t("cli_positional"),
        "options": t("cli_options"),
        "show this help message and exit": t("cli_help"),
    }
    argparse._ = lambda s: table.get(s, s)  # type: ignore[attr-defined]


def build_parser() -> argparse.ArgumentParser:
    _localize_argparse()
    p = argparse.ArgumentParser(prog="txt-to-epub", description=t("cli_desc"))
    p.add_argument("inputs", nargs="*", help=t("cli_inputs"))
    p.add_argument("--encoding", default=detect.AUTO, metavar="ENC", help=t("cli_encoding"))
    p.add_argument("--chapter-pattern", default=chap.DEFAULT_PATTERN, metavar="REGEX", help=t("cli_chapter_pattern"))
    p.add_argument("--no-chapters", action="store_true", help=t("cli_no_chapters"))
    p.add_argument("--paragraph", choices=chap.PARAGRAPH_MODES, default="auto", help=t("cli_paragraph"))
    p.add_argument("--title", default="", help=t("cli_title"))
    p.add_argument("--author", default="", help=t("cli_author"))
    p.add_argument("--publisher", default="", help=t("cli_publisher"))
    p.add_argument("--lang", choices=core.TEXT_LANGS + (core.LANG_AUTO,), default=core.LANG_AUTO,
                   help=t("cli_text_lang"))
    p.add_argument("--cover", default="", metavar="IMAGE|auto", help=t("cli_cover"))
    g = p.add_mutually_exclusive_group()
    g.add_argument("--indent", dest="indent", action="store_true", default=True, help=t("cli_indent"))
    g.add_argument("--no-indent", dest="indent", action="store_false", help=t("cli_no_indent"))
    p.add_argument("--line-height", choices=core.LINE_HEIGHTS[1:], default="", help=t("cli_line_height"))
    p.add_argument("-y", "--yes", action="store_true", help=t("cli_yes"))
    p.add_argument("--ui-lang", choices=i18n.LANGS, help=t("cli_ui_lang"))
    p.add_argument("--gui", action="store_true", help=t("cli_gui"))
    return p


def _options_from(args: argparse.Namespace) -> core.Options:
    cover_mode, cover_path = "none", ""
    if args.cover.lower() == "auto":
        cover_mode = "auto"
    elif args.cover:
        cover_mode, cover_path = "file", args.cover
    return core.Options(
        encoding=args.encoding, pattern=args.chapter_pattern, split_chapters=not args.no_chapters,
        paragraph_mode=args.paragraph, text_lang=args.lang, author=args.author, publisher=args.publisher,
        cover_mode=cover_mode, cover_path=cover_path, indent=args.indent, line_height=args.line_height,
    )


def _confirm(question: str, yes: bool) -> bool:
    if yes or not sys.stdin.isatty():
        return yes
    answer = input(question + t("cli_confirm_hint")).strip().lower()
    return answer in ("y", "yes")


def run_cli(args: argparse.Namespace) -> int:
    files = core.collect_txts(args.inputs)
    for p in args.inputs:
        if not os.path.exists(p):
            print(t("err_open_failed", name=p), file=sys.stderr)
    if not files:
        print(t("cli_no_input"), file=sys.stderr)
        return 2
    try:
        chap.compile_pattern(args.chapter_pattern)
    except chap.BadPattern as exc:
        print(t("err_bad_pattern", error=str(exc)), file=sys.stderr)
        return 2
    if args.encoding != detect.AUTO:
        try:
            codecs.lookup(args.encoding)
        except LookupError:
            print(t("err_unknown_encoding", enc=args.encoding), file=sys.stderr)
            return 2
    opts = _options_from(args).validated()
    if opts.cover_mode == "file":
        try:
            import cover as cover_mod

            img = cover_mod.load_cover(opts.cover_path)
            if img.too_small:
                print(t("warn_cover_small", width=img.width), file=sys.stderr)
        except Exception:
            print(t("err_cover_open", name=os.path.basename(opts.cover_path)), file=sys.stderr)
            return 2

    failures = processed = 0
    for idx, path in enumerate(files, 1):
        name = os.path.basename(path)
        print(t("cli_processing", index=idx, total=len(files), name=name))
        try:
            size = os.path.getsize(path)
            if size > detect.WARN_SIZE and not _confirm(
                    t("warn_large_file", name=name, size=f"{size / 1048576:.0f}"), args.yes):
                print(t("log_skipped", name=name))
                continue
            loaded = core.load_text(path, opts.encoding)
        except detect.EmptyFile:
            print(f"{name}: {t('err_empty')}", file=sys.stderr)
            failures += 1
            continue
        except (LookupError, UnicodeError):
            print(t("err_decode_failed", name=name), file=sys.stderr)
            failures += 1
            continue
        except Exception:
            print(t("err_open_failed", name=name), file=sys.stderr)
            failures += 1
            continue
        print(t("cli_encoding_info", enc=loaded.detection.display, confidence=loaded.detection.confidence,
                used=detect.display_name(loaded.encoding)))
        if loaded.replaced:
            print(t("log_replaced", name=name, count=loaded.replaced))
        title = args.title if args.title and len(files) == 1 else core.default_title(path)
        chapters = core.plan_chapters(loaded, opts, title)
        count = chap.heading_count(chapters)
        if count == 0:
            print(t("chapter_none"))
        elif count > chap.MANY_CHAPTERS and not _confirm(t("warn_many_chapters", name=name, count=count), args.yes):
            print(t("log_skipped", name=name))
            continue
        try:
            result = core.convert(loaded, opts, title, chapters)
        except KeyboardInterrupt:
            print("\n" + t("status_cancelled"))
            return 130
        except Exception as exc:  # one bad file must not end the batch
            print(t("err_file_failed", name=name, error=exc), file=sys.stderr)
            failures += 1
            continue
        if not result.no_chapters:
            print(t("chapter_count", count=result.chapters))
        print(t("log_saved", path=result.output_path))
        processed += 1
    print(t("msg_done", count=processed))
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Windows consoles default to cp949; Chinese/Japanese file names would crash print().
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    i18n.init(_preselect_lang(argv))
    args = build_parser().parse_args(argv)
    if args.ui_lang:
        i18n.set_lang(args.ui_lang, persist=False)
    # A windowed exe has no console, so dropping files on it opens the GUI
    # with those files loaded instead of running the CLI into nowhere.
    headless = getattr(sys, "frozen", False) and sys.stdout is None
    if args.gui or headless or not args.inputs:
        import gui

        gui.launch(args.inputs or None)
        return 0
    return run_cli(args)


if __name__ == "__main__":
    sys.exit(main())
