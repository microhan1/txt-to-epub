"""tkinter GUI for txt-to-epub.

Flow: drop TXT -> encoding detected + preview -> chapter table -> metadata,
cover, style -> convert -> done + open result. Every string comes from
lang/*.json through i18n.t().
"""
from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

import webbrowser

import chapters as chap
import detect
import epub_build as core
import i18n
import prefs as prefs_mod
import update_check
import version
from epub_build import Options
from i18n import t

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _HAS_DND = True
except Exception:  # pragma: no cover - optional dependency
    _HAS_DND = False

PREVIEW_CHARS = 3000
CHECK = chr(0x2714)
UPDATE_BG, UPDATE_BORDER = "#fff6d6", "#d9b84a"  # the new-version line: a soft, non-modal band
LINK_FG = "#0645ad"
TIP_BG = "#ffffe1"  # the small note under the feedback link
LARGE_MB = detect.WARN_SIZE / (1024 * 1024)


def _saved_options(settings: dict) -> Options:
    """Options from settings.json, trusting nothing about its types. The file
    sits beside the exe where anyone can edit it; one wrong value must not
    stop the window from opening."""
    raw = settings.get("options")
    raw = raw if isinstance(raw, dict) else {}
    default = Options()

    def typed(key: str, kind: type):
        value = raw.get(key)
        ok = isinstance(value, kind) and (kind is bool or not isinstance(value, bool))
        return value if ok else getattr(default, key)

    return Options(
        encoding=detect.AUTO,  # never remembered: it is a per-file decision
        pattern=typed("pattern", str), split_chapters=typed("split_chapters", bool),
        paragraph_mode=typed("paragraph_mode", str), text_lang=typed("text_lang", str),
        author=typed("author", str), publisher=typed("publisher", str),
        cover_mode=typed("cover_mode", str), cover_path=typed("cover_path", str),
        indent=typed("indent", bool), line_height=typed("line_height", str),
    ).validated()


@dataclass
class FileState:
    path: str
    size: int
    title: str
    encoding: str = detect.AUTO        # user's choice; AUTO means the detected one
    loaded: core.Loaded | None = None
    error: str | None = None           # i18n key of a load error
    error_text: str = ""               # detail for err_file_failed
    loading: bool = False
    pattern_applied: str = ""
    split: bool = True
    detected: list[int] = field(default_factory=list)
    manual: set[int] = field(default_factory=set)
    disabled: set[int] = field(default_factory=set)
    gen: int = 0
    chars: int = 0                     # characters in the decoded text (shown in "one book" rows)
    included: bool = True              # "one book": this file is in
    merge_title: str | None = None     # "one book": the chapter title the user typed; None = from the file name

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    def starts(self) -> set[int]:
        if not self.split:
            return set()
        return set(self.detected) | self.manual

    def table(self) -> list[chap.Chapter]:
        """All candidate chapters, with enabled flags, for the tree view."""
        if not self.loaded:
            return []
        rows = chap.build_chapters(self.loaded.lines, sorted(self.starts()), self.title, self.manual)
        for r in rows:
            r.enabled = r.start not in self.disabled or not r.heading
        return rows

    def selected(self) -> list[chap.Chapter]:
        """Chapters that will be written: enabled headings only."""
        if not self.loaded:
            return []
        starts = sorted(self.starts() - self.disabled)
        return chap.build_chapters(self.loaded.lines, starts, self.title, self.manual)


class Tooltip:
    """A small note under a widget while the mouse is over it; tkinter only. The text
    is looked up on every show, so it follows the language switch."""

    DELAY_MS = 450
    WRAP = 320

    def __init__(self, widget: tk.Misc, key: str) -> None:
        self.widget, self.key = widget, key
        self.tip: tk.Toplevel | None = None
        self.label: tk.Label | None = None
        self._job: str | None = None
        widget.bind("<Enter>", lambda e: self._schedule(), add="+")
        for seq in ("<Leave>", "<ButtonPress>", "<Destroy>"):
            widget.bind(seq, lambda e: self.hide(), add="+")

    @property
    def text(self) -> str:
        return t(self.key)

    def _schedule(self) -> None:
        self._cancel()
        self._job = self.widget.after(self.DELAY_MS, self.show)

    def _cancel(self) -> None:
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def show(self) -> None:
        self._job = None
        if self.tip is None:
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_attributes("-topmost", True)
            self.label = tk.Label(self.tip, justify="left", background=TIP_BG, relief="solid", borderwidth=1,
                                  highlightthickness=0, padx=6, pady=3, wraplength=self.WRAP)
            self.label.pack()
        self.label.configure(text=self.text)
        self.place()

    def place(self) -> None:
        """Right edge under the widget's right edge, then pulled inside the window and
        the screen, so a narrow window or a link near the edge never cuts the note."""
        w, tip = self.widget, self.tip
        tip.update_idletasks()
        tw, th = tip.winfo_reqwidth(), tip.winfo_reqheight()
        x, y = w.winfo_rootx() + w.winfo_width() - tw, w.winfo_rooty() + w.winfo_height() + 4
        top = w.winfo_toplevel()
        left, right = top.winfo_rootx(), top.winfo_rootx() + top.winfo_width()
        if tw <= right - left:
            x = min(max(x, left), right - tw)
        x = min(max(x, 0), w.winfo_screenwidth() - tw)
        y = min(max(y, 0), w.winfo_screenheight() - th)
        tip.wm_geometry(f"+{x}+{y}")

    def refresh(self) -> None:
        """After a language switch: new words in the note that is showing."""
        if self.tip is not None and self.label is not None:
            self.label.configure(text=self.text)
            self.place()

    def hide(self) -> None:
        self._cancel()
        if self.tip is not None:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = self.label = None


class App:
    def __init__(self, initial_files: list[str] | None = None) -> None:
        self.root = TkinterDnD.Tk() if _HAS_DND else tk.Tk()
        self.root.geometry("1320x860")

        self.files: list[FileState] = []
        self.inputs: list[str] = []            # what was dropped or picked, for the one-book title default
        self.merge_title_user: str | None = None  # the book title typed in "one book"; None = default
        self.current: FileState | None = None
        self.outputs: list[str] = []
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self._texts: list[tuple[tk.Misc, str, str]] = []
        self._status_key = ""
        self._status_kwargs: dict = {}
        self._closing = False
        self._syncing = False

        saved = _saved_options(i18n.load_settings())
        self.prefs = prefs_mod.load()
        self._update_info: update_check.UpdateInfo | None = None
        self.var_update_check = tk.BooleanVar(value=self.prefs.update_check)
        self.var_merge = tk.StringVar(value=self.prefs.merge_mode)
        self.var_lang = tk.StringVar(value=i18n.LANG_NAMES[i18n.current_lang()])
        self.var_encoding = tk.StringVar(value=detect.AUTO)
        self.var_pattern = tk.StringVar(value=saved.pattern)
        self.var_split = tk.BooleanVar(value=saved.split_chapters)
        self.var_line_no = tk.StringVar()
        self.var_title = tk.StringVar()
        self.var_author = tk.StringVar(value=saved.author)
        self.var_text_lang = tk.StringVar(value=saved.text_lang)
        self.var_publisher = tk.StringVar(value=saved.publisher)
        self.var_cover_mode = tk.StringVar(value=saved.cover_mode)
        self.var_cover_path = tk.StringVar(value=saved.cover_path)
        self.var_paragraph = tk.StringVar(value=saved.paragraph_mode)
        self.var_indent = tk.BooleanVar(value=saved.indent)
        self.var_line_height = tk.StringVar(value=saved.line_height)

        self._build()
        self._apply_texts()
        # The window may not shrink below what the three panels ask for: at the old fixed minimum (1200x740)
        # the style block at the bottom of panel 3 was cut off (v0.1.1).
        self.root.update_idletasks()
        self._min_size = (max(1200, self.root.winfo_reqwidth()), max(740, self.root.winfo_reqheight()))
        self.root.minsize(*self._min_size)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        # once a day, 1.5 s after the window is up, on a background thread; silent on any failure
        update_check.check_async(self.root, version.UPDATE_SLUG, version.APP_VERSION, self.prefs,
                                 self._on_update_result)
        if initial_files:
            self.root.after(100, lambda: self.add_paths(initial_files))

    # ------------------------------------------------------------ building
    def _reg(self, widget: tk.Misc, key: str, attr: str = "text") -> tk.Misc:
        self._texts.append((widget, key, attr))
        return widget

    def _build(self) -> None:
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        # ---- header
        head = ttk.Frame(root, padding=(12, 10, 12, 4))
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)
        self._reg(ttk.Label(head, font=("", 15, "bold")), "app_title").grid(row=0, column=0, sticky="w")
        # a small link: opens the feedback box on the tool's page in the browser, nothing more.
        # A Tab stop before the checkbox: Enter or Space opens it, and a frame drawn while it
        # has focus shows where the focus is (the border is always there, flat when
        # unfocused, so the header does not shift).
        link_font = tkfont.nametofont("TkDefaultFont").copy()
        link_font.configure(underline=True)
        self.lnk_feedback = self._reg(ttk.Label(head, foreground=LINK_FG, cursor="hand2", font=link_font,
                                                takefocus=True, borderwidth=1, relief="flat", padding=(2, 0)),
                                      "btn_feedback")
        self.lnk_feedback.grid(row=0, column=1, padx=(0, 16))
        for seq in ("<Button-1>", "<Return>", "<KP_Enter>", "<space>"):
            self.lnk_feedback.bind(seq, lambda e: (self.send_feedback(), "break")[1])
        self.lnk_feedback.bind("<FocusIn>", lambda e: self.lnk_feedback.configure(relief="solid"))
        self.lnk_feedback.bind("<FocusOut>", lambda e: self.lnk_feedback.configure(relief="flat"))
        self.tip_feedback = Tooltip(self.lnk_feedback, "tip_feedback")
        self.chk_update = self._reg(ttk.Checkbutton(head, variable=self.var_update_check,
                                                    command=self._on_update_toggle), "opt_update_check")
        self.chk_update.grid(row=0, column=2, padx=(0, 16))
        self._reg(ttk.Label(head), "lbl_language").grid(row=0, column=3, padx=(0, 6))
        self.cmb_lang = ttk.Combobox(head, state="readonly", width=10, textvariable=self.var_lang,
                                     values=[i18n.LANG_NAMES[c] for c in i18n.LANGS])
        self.cmb_lang.grid(row=0, column=4)
        self.cmb_lang.bind("<<ComboboxSelected>>", self._on_lang)

        # ---- files
        files = self._reg(ttk.LabelFrame(root, padding=8), "lbl_files")
        files.grid(row=1, column=0, sticky="ew", padx=12, pady=4)
        files.columnconfigure(0, weight=1)
        self.lbl_drop = self._reg(ttk.Label(files, anchor="center", relief="groove", padding=6,
                                            foreground="#555"), "drop_hint")
        self.lbl_drop.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.lst_files = tk.Listbox(files, height=4, activestyle="none", exportselection=False)
        self.lst_files.grid(row=1, column=0, sticky="nsew")
        self.lst_files.bind("<<ListboxSelect>>", self._on_select_file)
        self.lst_files.bind("<Alt-Up>", lambda e: self.move_selected(-1) or "break")
        self.lst_files.bind("<Alt-Down>", lambda e: self.move_selected(1) or "break")
        btns = ttk.Frame(files)
        btns.grid(row=1, column=1, rowspan=2, sticky="ns", padx=(8, 0))
        self.btn_add = self._reg(ttk.Button(btns, command=self._add_files_dialog), "btn_add_files")
        self.btn_add.pack(fill="x")
        self.btn_remove = self._reg(ttk.Button(btns, command=self.remove_selected), "btn_remove")
        self.btn_remove.pack(fill="x", pady=4)
        self.btn_clear = self._reg(ttk.Button(btns, command=self.clear_files), "btn_clear")
        self.btn_clear.pack(fill="x")
        self._reg(ttk.Label(btns, foreground="#555"), "lbl_order").pack(fill="x", pady=(8, 0))
        self.btn_up = self._reg(ttk.Button(btns, command=lambda: self.move_selected(-1)), "btn_up")
        self.btn_up.pack(fill="x")
        self.btn_down = self._reg(ttk.Button(btns, command=lambda: self.move_selected(1)), "btn_down")
        self.btn_down.pack(fill="x", pady=(4, 0))
        # one EPUB per file (as before) or every file one chapter of a single book
        mode = ttk.Frame(files)
        mode.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.rad_each = self._reg(ttk.Radiobutton(mode, variable=self.var_merge, value="each",
                                                  command=self._on_merge_mode), "merge_each")
        self.rad_each.pack(side="left")
        self.rad_one = self._reg(ttk.Radiobutton(mode, variable=self.var_merge, value="one",
                                                 command=self._on_merge_mode), "merge_one")
        self.rad_one.pack(side="left", padx=(16, 0))
        if _HAS_DND:
            for w in (root, self.lbl_drop, self.lst_files):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)

        # ---- middle: encoding | chapters | metadata
        mid = ttk.Frame(root)
        mid.grid(row=2, column=0, sticky="nsew", padx=12, pady=4)
        mid.columnconfigure(0, weight=3, uniform="mid")
        mid.columnconfigure(1, weight=4, uniform="mid")
        mid.columnconfigure(2, weight=3, uniform="mid")
        mid.rowconfigure(0, weight=1)
        self._build_encoding(mid)
        self._build_chapters(mid)
        self._build_meta(mid)

        # ---- log
        logf = self._reg(ttk.LabelFrame(root, padding=4), "lbl_log")
        logf.grid(row=3, column=0, sticky="ew", padx=12, pady=4)
        logf.columnconfigure(0, weight=1)
        self.txt_log = tk.Text(logf, height=4, state="disabled", wrap="none")
        self.txt_log.grid(row=0, column=0, sticky="ew")
        sb = ttk.Scrollbar(logf, command=self.txt_log.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.txt_log.configure(yscrollcommand=sb.set)

        # ---- new-version notice: one line, hidden until the server says a newer version exists
        self.frm_update = tk.Frame(root, bg=UPDATE_BG, highlightthickness=1, highlightbackground=UPDATE_BORDER)
        self.lbl_update = tk.Label(self.frm_update, bg=UPDATE_BG, anchor="w")
        self.lbl_update.pack(side="left", fill="x", expand=True, padx=(10, 8), pady=5)
        self.btn_update_later = self._reg(ttk.Button(self.frm_update, command=self._update_later), "btn_later")
        self.btn_update_later.pack(side="right", padx=(6, 8), pady=4)
        self.btn_update_open = self._reg(ttk.Button(self.frm_update, command=self._update_open), "btn_update")
        self.btn_update_open.pack(side="right", pady=4)
        # gridded only when there is something to say (see _show_update_notice)

        # ---- bottom
        bot = ttk.Frame(root, padding=(12, 4, 12, 10))
        bot.grid(row=5, column=0, sticky="ew")
        bot.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(bot, mode="determinate")
        self.progress.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 6))
        self.lbl_status = ttk.Label(bot)
        self.lbl_status.grid(row=1, column=0, sticky="w")
        self.btn_open = self._reg(ttk.Button(bot, command=self.open_result, state="disabled"), "btn_open_result")
        self.btn_open.grid(row=1, column=1, padx=4)
        self.btn_cancel = self._reg(ttk.Button(bot, command=self.cancel, state="disabled"), "btn_cancel")
        self.btn_cancel.grid(row=1, column=2, padx=4)
        self.btn_run = self._reg(ttk.Button(bot, command=self.run), "btn_run")
        self.btn_run.grid(row=1, column=3, padx=(4, 0))
        self._set_status("status_ready")
        self._apply_mode()

    def _build_encoding(self, parent: ttk.Frame) -> None:
        f = self._reg(ttk.LabelFrame(parent, padding=6), "lbl_step_encoding")
        f.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        f.columnconfigure(1, weight=1)
        f.rowconfigure(3, weight=1)
        self.lbl_enc = ttk.Label(f, wraplength=340)
        self.lbl_enc.grid(row=0, column=0, columnspan=2, sticky="w")
        self._reg(ttk.Label(f), "enc_override").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.cmb_enc = ttk.Combobox(f, state="readonly", textvariable=self.var_encoding, width=14)
        self.cmb_enc.grid(row=1, column=1, sticky="w", pady=(4, 0), padx=(6, 0))
        self.cmb_enc.bind("<<ComboboxSelected>>", self._on_encoding)
        self.lbl_enc_warn = ttk.Label(f, foreground="#c00", wraplength=340)
        self.lbl_enc_warn.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.txt_preview = tk.Text(f, wrap="word", state="disabled", height=8, width=30,
                                   highlightthickness=2, highlightbackground="#ccc", highlightcolor="#ccc")
        self.txt_preview.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        self.lbl_preview_msg = ttk.Label(f, foreground="#555", wraplength=340)
        self.lbl_preview_msg.grid(row=4, column=0, columnspan=2, sticky="w")

    def _build_chapters(self, parent: ttk.Frame) -> None:
        f = self._reg(ttk.LabelFrame(parent, padding=6), "lbl_step_chapters")
        f.grid(row=0, column=1, sticky="nsew", padx=6)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(3, weight=1)
        top = ttk.Frame(f)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.columnconfigure(1, weight=1)
        self.chk_split = self._reg(ttk.Checkbutton(top, variable=self.var_split, command=self._on_split),
                                   "opt_split_chapters")
        self.chk_split.grid(row=0, column=0, columnspan=3, sticky="w")
        self._reg(ttk.Label(top), "chapter_pattern").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.cmb_pattern = ttk.Combobox(top, textvariable=self.var_pattern, values=list(chap.PRESET_PATTERNS))
        self.cmb_pattern.grid(row=1, column=1, sticky="ew", padx=6, pady=(4, 0))
        self.cmb_pattern.bind("<<ComboboxSelected>>", lambda e: self._redetect())
        self.cmb_pattern.bind("<Return>", lambda e: self._redetect())
        self.btn_redetect = self._reg(ttk.Button(top, command=self._redetect), "btn_redetect")
        self.btn_redetect.grid(row=1, column=2, pady=(4, 0))
        self.lbl_chapter_count = ttk.Label(f)
        self.lbl_chapter_count.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 2))
        self.lbl_pattern_err = ttk.Label(f, foreground="#c00", wraplength=380)
        self.lbl_pattern_err.grid(row=2, column=0, columnspan=2, sticky="w")

        cols = ("on", "no", "title", "line", "chars")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse", height=8)
        for c, w, anchor in (("on", 40, "center"), ("no", 40, "e"), ("title", 220, "w"),
                             ("line", 70, "e"), ("chars", 80, "e")):
            self.tree.column(c, width=w, minwidth=w, anchor=anchor, stretch=(c == "title"))
            self._reg(self.tree, f"col_{c}", attr=f"heading:{c}")
        self.tree.grid(row=3, column=0, sticky="nsew", pady=(2, 0))
        sb = ttk.Scrollbar(f, command=self.tree.yview)
        sb.grid(row=3, column=1, sticky="ns", pady=(2, 0))
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-1>", self._on_tree_double)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<space>", lambda e: self._toggle_selected())

        bottom = ttk.Frame(f)
        bottom.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.btn_toggle = self._reg(ttk.Button(bottom, command=self._toggle_selected), "btn_toggle")
        self.btn_toggle.grid(row=0, column=0, sticky="w")
        self.btn_jump = self._reg(ttk.Button(bottom, command=self._jump_preview), "btn_jump")
        self.btn_jump.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self._reg(ttk.Label(bottom), "lbl_line_no").grid(row=1, column=0, sticky="w", pady=(6, 0))
        line_row = ttk.Frame(bottom)
        line_row.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(6, 0))
        self.ent_line = ttk.Entry(line_row, textvariable=self.var_line_no, width=8)
        self.ent_line.pack(side="left")
        self.ent_line.bind("<Return>", lambda e: self._add_manual())
        self.btn_add_chapter = self._reg(ttk.Button(line_row, command=self._add_manual), "btn_add_chapter")
        self.btn_add_chapter.pack(side="left", padx=(4, 0))

    def _build_meta(self, parent: ttk.Frame) -> None:
        f = self._reg(ttk.LabelFrame(parent, padding=6), "lbl_step_meta")
        f.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        f.columnconfigure(1, weight=1)
        r = 0
        self._reg(ttk.Label(f), "meta_title").grid(row=r, column=0, sticky="w")
        self.ent_title = ttk.Entry(f, textvariable=self.var_title)
        self.ent_title.grid(row=r, column=1, sticky="ew", padx=(6, 0))
        self.var_title.trace_add("write", lambda *_: self._on_title_edit())
        r += 1
        self._reg(ttk.Label(f), "meta_author").grid(row=r, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(f, textvariable=self.var_author).grid(row=r, column=1, sticky="ew", padx=(6, 0), pady=(4, 0))
        r += 1
        self._reg(ttk.Label(f), "meta_lang").grid(row=r, column=0, sticky="w", pady=(4, 0))
        self.cmb_text_lang = ttk.Combobox(f, state="readonly", width=14)
        self.cmb_text_lang.grid(row=r, column=1, sticky="w", padx=(6, 0), pady=(4, 0))
        self.cmb_text_lang.bind("<<ComboboxSelected>>", self._on_text_lang)
        r += 1
        self._reg(ttk.Label(f), "meta_publisher").grid(row=r, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(f, textvariable=self.var_publisher).grid(row=r, column=1, sticky="ew", padx=(6, 0), pady=(4, 0))
        r += 1

        cov = self._reg(ttk.LabelFrame(f, padding=6), "cover_mode")
        cov.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        cov.columnconfigure(0, weight=1)
        for i, mode in enumerate(core.COVER_MODES):
            self._reg(ttk.Radiobutton(cov, variable=self.var_cover_mode, value=mode, command=self._on_cover_mode),
                      f"cover_{mode}").grid(row=i, column=0, columnspan=2, sticky="w")
        self.ent_cover = ttk.Entry(cov, textvariable=self.var_cover_path)
        self.ent_cover.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        self.btn_browse = self._reg(ttk.Button(cov, command=self._browse_cover), "btn_browse")
        self.btn_browse.grid(row=3, column=1, padx=(4, 0), pady=(4, 0))
        r += 1

        sty = self._reg(ttk.LabelFrame(f, padding=6), "lbl_style")
        sty.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        sty.columnconfigure(1, weight=1)
        self._reg(ttk.Label(sty), "opt_paragraph").grid(row=0, column=0, columnspan=2, sticky="w")
        pf = ttk.Frame(sty)
        pf.grid(row=1, column=0, columnspan=2, sticky="w", padx=(12, 0))
        for mode in chap.PARAGRAPH_MODES:
            self._reg(ttk.Radiobutton(pf, variable=self.var_paragraph, value=mode), f"para_{mode}")\
                .pack(side="left", padx=(0, 8))
        self._reg(ttk.Checkbutton(sty, variable=self.var_indent), "opt_indent")\
            .grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._reg(ttk.Label(sty), "opt_line_height").grid(row=3, column=0, sticky="w", pady=(4, 0))
        self.cmb_line_height = ttk.Combobox(sty, state="readonly", width=14)
        self.cmb_line_height.grid(row=3, column=1, sticky="w", pady=(4, 0))
        self.cmb_line_height.bind("<<ComboboxSelected>>", self._on_line_height)
        self._on_cover_mode()

    # ------------------------------------------------------------ texts
    def _apply_texts(self) -> None:
        self.root.title(t("app_title"))
        for widget, key, attr in self._texts:
            try:
                if attr.startswith("heading:"):
                    widget.heading(attr.split(":", 1)[1], text=t(key))
                else:
                    widget.configure(**{attr: t(key)})
            except tk.TclError:
                pass
        self.cmb_enc.configure(values=[t("enc_auto")] + [detect.display_name(e) for e in detect.ENCODINGS[1:]])
        self._sync_encoding_combo()
        self.cmb_text_lang.configure(values=[t("text_lang_auto")] + [t(f"text_lang_{c}") for c in core.TEXT_LANGS])
        self.cmb_text_lang.current((core.TEXT_LANGS + ("",)).index(self.var_text_lang.get()) + 1
                                   if self.var_text_lang.get() in core.TEXT_LANGS else 0)
        self.cmb_line_height.configure(values=[t("line_height_default")] + list(core.LINE_HEIGHTS[1:]))
        self.cmb_line_height.current(core.LINE_HEIGHTS.index(self.var_line_height.get()))
        self._refresh_file_panel()
        if self._status_key:
            self._set_status(self._status_key, **self._status_kwargs)
        if self._update_info is not None:
            self._show_update_notice()
        self.tip_feedback.refresh()

    def _set_status(self, key: str, **kwargs) -> None:
        self._status_key, self._status_kwargs = key, kwargs
        self.lbl_status.configure(text=t(key, **kwargs))

    def log(self, key: str, **kwargs) -> None:
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", t(key, **kwargs) + "\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _on_lang(self, _event=None) -> None:
        index = self.cmb_lang.current()
        if index >= 0:
            i18n.set_lang(i18n.LANGS[index])
        self._apply_texts()

    def _on_text_lang(self, _event=None) -> None:
        i = self.cmb_text_lang.current()
        self.var_text_lang.set(core.LANG_AUTO if i <= 0 else core.TEXT_LANGS[i - 1])

    def _on_line_height(self, _event=None) -> None:
        i = self.cmb_line_height.current()
        self.var_line_height.set(core.LINE_HEIGHTS[max(i, 0)])

    def _on_cover_mode(self) -> None:
        state = "normal" if self.var_cover_mode.get() == "file" else "disabled"
        self.ent_cover.configure(state=state)
        self.btn_browse.configure(state=state)

    def _browse_cover(self) -> None:
        p = filedialog.askopenfilename(filetypes=[(t("file_dialog_image"), "*.jpg *.jpeg *.png *.webp *.bmp *.gif")])
        if p:
            self.var_cover_path.set(p)

    def options(self) -> Options:
        return Options(
            encoding=detect.AUTO, pattern=self.var_pattern.get(), split_chapters=self.var_split.get(),
            paragraph_mode=self.var_paragraph.get(), text_lang=self.var_text_lang.get(),
            author=self.var_author.get(), publisher=self.var_publisher.get(),
            cover_mode=self.var_cover_mode.get(), cover_path=self.var_cover_path.get(),
            indent=self.var_indent.get(), line_height=self.var_line_height.get(),
            merge=self.merging(),
        ).validated()

    def _save_options(self) -> None:
        self.prefs.update_check = bool(self.var_update_check.get())
        settings = i18n.load_settings()
        settings["options"] = dataclasses.asdict(self.options())
        settings.update(dataclasses.asdict(self.prefs))
        i18n.save_settings(settings)

    # ------------------------------------------------------------ new version notice
    def _on_update_result(self, info: update_check.UpdateInfo | None, answered: bool) -> None:
        """Tk thread. The day is recorded only when the server answered, so an
        offline start asks again next time."""
        if self._closing:
            return
        if answered:
            self.prefs.update_check_last = update_check.today()
            self._save_options()
        if info is not None and self.var_update_check.get():
            self._update_info = info
            self._show_update_notice()

    def _show_update_notice(self) -> None:
        info = self._update_info
        if info is None:
            self.frm_update.grid_remove()
            return
        self.lbl_update.configure(text=t("update_available", latest=info.latest, current=info.current))
        if not self.frm_update.winfo_manager():
            self.frm_update.grid(row=4, column=0, sticky="ew", padx=12, pady=(2, 0))
            # The band takes its height from the middle row. At the minimum window size that
            # row has no slack, so the minimum grows by the band and the window follows.
            self.root.update_idletasks()
            w, h = self._min_size
            self.root.minsize(w, h + self.frm_update.winfo_reqheight() + 2)

    def _hide_update_notice(self) -> None:
        self._update_info = None
        self.frm_update.grid_remove()
        self.root.minsize(*self._min_size)

    def _update_open(self) -> None:
        """The tools page, never a download: the site serves the download."""
        info = self._update_info
        if info is not None:
            target = update_check.page_url(info, i18n.current_lang())
            if target.startswith(update_check.SITE):
                try:
                    webbrowser.open(target)
                except Exception:
                    pass
        self._hide_update_notice()

    def _update_later(self) -> None:
        if self._update_info is not None:
            self.prefs.update_check_skipped = self._update_info.latest  # a newer one is shown again
            self._save_options()
        self._hide_update_notice()

    def _on_update_toggle(self) -> None:
        self._save_options()
        if not self.var_update_check.get():
            self._hide_update_notice()

    # ------------------------------------------------------------ feedback
    def send_feedback(self) -> None:
        """Open the feedback box on the tool's page. Nothing is sent from here. When
        no browser opens, the address goes to the log and a message box, to copy."""
        self.tip_feedback.hide()  # the note would otherwise linger over the browser
        url =update_check.feedback_url(version.UPDATE_SLUG, version.APP_VERSION, i18n.current_lang())
        try:
            opened = webbrowser.open(url)
        except Exception:  # webbrowser.Error, OSError: the window must stay up
            opened = False
        if not opened:
            self.log("feedback_failed_log", url=url)
            messagebox.showwarning(t("btn_feedback"), t("feedback_failed", url=url), parent=self.root)

    # ------------------------------------------------------------ files
    def _on_drop(self, event) -> None:
        self.add_paths(list(self.root.tk.splitlist(event.data)))

    def _add_files_dialog(self) -> None:
        paths = filedialog.askopenfilenames(filetypes=[(t("file_dialog_txt"), "*.txt"), (t("file_dialog_all"), "*.*")])
        if paths:
            self.add_paths(list(paths))

    def add_paths(self, paths: list[str]) -> None:
        found = core.sort_natural(core.collect_txts(paths))  # 2, 3, ... 10, not 10 before 2
        for p in paths:
            if not os.path.exists(p):
                self.log("err_open_failed", name=p)
        if not found:
            self.log("err_no_txt_found")
            return
        self.inputs.extend(p for p in paths if os.path.exists(p))
        known = {os.path.normcase(f.path) for f in self.files}
        for path in found:
            if os.path.normcase(path) in known:
                continue
            name = os.path.basename(path)
            try:
                size = os.path.getsize(path)
            except OSError:
                self.log("err_open_failed", name=name)
                continue
            if size == 0:
                messagebox.showerror(t("dlg_error"), f"{name}: {t('err_empty')}", parent=self.root)
                self.log("log_empty", name=name)
                continue
            if size > detect.WARN_SIZE and not messagebox.askyesno(
                    t("dlg_confirm"), t("warn_large_file", name=name, size=f"{size / 1048576:.0f}"), parent=self.root):
                self.log("log_skipped", name=name)
                continue
            state = FileState(path=path, size=size, title=core.default_title(path))
            self.files.append(state)
            self.lst_files.insert("end", name)
            self._load_async(state)
        if self.current is None and self.files:
            self._select_index(len(self.files) - 1)

    def remove_selected(self) -> None:
        sel = self.lst_files.curselection()
        if not sel:
            return
        idx = sel[0]
        state = self.files.pop(idx)
        state.gen += 1
        self.lst_files.delete(idx)
        if self.current is state:
            self.current = None
        if self.files:
            self._select_index(min(idx, len(self.files) - 1))
        else:
            self._refresh_file_panel()

    def clear_files(self) -> None:
        for f in self.files:
            f.gen += 1
        self.files.clear()
        self.inputs.clear()
        self.merge_title_user = None
        self.current = None
        self.lst_files.delete(0, "end")
        self._refresh_file_panel()

    def move_selected(self, delta: int) -> None:
        """Move the selected file up (-1) or down (+1): the order of the chapters in "one book"."""
        sel = self.lst_files.curselection()
        if not sel or (self.worker and self.worker.is_alive()):
            return
        i = sel[0]
        j = i + delta
        if not 0 <= j < len(self.files):
            return
        self.files[i], self.files[j] = self.files[j], self.files[i]
        name = self.lst_files.get(i)
        self.lst_files.delete(i)
        self.lst_files.insert(j, name)
        self._select_index(j)

    def _select_index(self, idx: int) -> None:
        self.lst_files.selection_clear(0, "end")
        self.lst_files.selection_set(idx)
        self.lst_files.see(idx)
        self._on_select_file()

    def _on_select_file(self, _event=None) -> None:
        sel = self.lst_files.curselection()
        self.current = self.files[sel[0]] if sel and sel[0] < len(self.files) else None
        if self.current and self.current.loaded and self.current.pattern_applied != self._pattern_key():
            self._detect_for(self.current)
        self._refresh_file_panel()

    def _load_async(self, state: FileState, encoding: str | None = None) -> None:
        """Decode and detect chapters in a thread; the UI is refreshed via after()."""
        state.gen += 1
        gen = state.gen
        state.loading = True
        state.error = None
        if encoding is not None:
            state.encoding = encoding
        enc = state.encoding
        pattern_key = self._pattern_key()
        pattern = self.var_pattern.get()
        split = self.var_split.get()
        if state is self.current:
            self._refresh_file_panel()

        def work() -> None:
            loaded = None
            error = None
            error_text = ""
            bad_pattern = False
            starts: list[int] = []
            chars = 0
            try:
                loaded = core.load_text(state.path, enc)
                chars = sum(len(line) for line in loaded.lines)
                if split:
                    rx = chap.compile_pattern(pattern)
                    starts = chap.find_starts(loaded.lines, rx)
            except detect.EmptyFile:
                error = "err_empty"
            except chap.BadPattern:
                starts = []
                bad_pattern = True
            except (LookupError, UnicodeError):
                error = "err_decode_failed"
            except OSError:
                error = "err_open_failed"
            except Exception as exc:  # a bug must be visible, not hidden behind "cannot open"
                error = "err_file_failed"
                error_text = f"{type(exc).__name__}: {exc}"

            def done() -> None:
                if gen != state.gen:
                    return
                state.loading = False
                state.loaded = loaded
                state.error = error
                state.error_text = error_text
                state.chars = chars
                state.detected = starts
                state.split = split
                state.pattern_applied = pattern_key
                if bad_pattern:
                    self._detect_for(state)  # shows the regex error for the current file
                if loaded is not None:
                    self.log("log_added", name=state.name, enc=loaded.detection.display,
                             confidence=loaded.detection.confidence)
                    if loaded.replaced:
                        self.log("log_replaced", name=state.name, count=loaded.replaced)
                elif error:
                    self.log(error, name=state.name, error=error_text)
                if state is self.current:
                    self._refresh_file_panel()
                elif self.merging():
                    self._refresh_tree()

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ panel
    def _pattern_key(self) -> str:
        return f"{int(self.var_split.get())}|{self.var_pattern.get()}"

    def _detect_for(self, state: FileState) -> None:
        """Re-run heading detection on an already loaded file (pattern changed)."""
        if not state.loaded:
            return
        self.lbl_pattern_err.configure(text="")
        starts: list[int] = []
        if self.var_split.get():
            try:
                rx = chap.compile_pattern(self.var_pattern.get())
                starts = chap.find_starts(state.loaded.lines, rx)
            except chap.BadPattern as exc:
                if state is self.current:
                    self.lbl_pattern_err.configure(text=t("err_bad_pattern", error=str(exc)))
        state.detected = starts
        state.split = self.var_split.get()
        state.pattern_applied = self._pattern_key()

    # ------------------------------------------------------------ one book
    def merging(self) -> bool:
        return self.var_merge.get() == "one"

    def _on_merge_mode(self) -> None:
        mode = self.var_merge.get()
        self.prefs.merge_mode = mode if mode in prefs_mod.MERGE_MODES else "each"
        self._save_options()
        self.lbl_pattern_err.configure(text="")
        self._apply_mode()
        self._refresh_file_panel()

    def _apply_mode(self, running: bool = False) -> None:
        """Per file: the pattern tools work. One book: the order buttons work instead."""
        one = self.merging()
        for w in (self.chk_split, self.btn_redetect, self.ent_line, self.btn_add_chapter):
            w.configure(state="disabled" if one or running else "normal")
        self.cmb_pattern.configure(state="disabled" if one or running else "normal")
        for w in (self.btn_up, self.btn_down):
            w.configure(state="normal" if one and not running else "disabled")
        # "one book": the start-line column shows the file name and takes the room of the
        # character-count column, which is per-file information
        self.tree.configure(displaycolumns=("on", "no", "title", "line") if one else "#all")
        self.tree.column("line", width=170 if one else 70, anchor="w" if one else "e")

    def book_title(self) -> str:
        """The one-book title: what the user typed, else the folder's name or what the file names share."""
        if self.merge_title_user is not None:
            return self.merge_title_user
        return core.book_title_for(self.inputs, [f.path for f in self.files])

    def _merge_states(self) -> list[FileState]:
        return [f for f in self.files if f.loaded is not None and not f.loading]

    def merge_parts(self, states: list[FileState] | None = None) -> list[core.Part]:
        """Chapters of the one book, in file order, with the user's titles applied."""
        states = self._merge_states() if states is None else states
        parts = core.merge_parts([s.loaded for s in states], self.book_title(),
                                 lambda n: t("merge_chapter_n", n=n))
        for st, part in zip(states, parts):
            if st.merge_title is not None:
                part.title = st.merge_title
        return parts

    def set_chapter_title(self, index: int, title: str) -> None:
        """Rename the chapter made from files[index]; an empty title goes back to the file name."""
        self.files[index].merge_title = title.strip() or None
        self._refresh_tree()

    def _on_tree_select(self, _event=None) -> None:
        """In "one book" the chapter rows are the files: selecting a row selects the file."""
        if self._syncing or not self.merging():
            return
        sel = self.tree.selection()
        if sel and sel[0].startswith("F"):
            idx = int(sel[0][1:])
            if idx < len(self.files) and self.files[idx] is not self.current:
                self._select_index(idx)

    def _on_tree_double(self, event) -> None:
        if not self.merging() or self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#3":
            return
        iid = self.tree.identify_row(event.y)
        if iid:
            self._edit_title(iid)

    def _edit_title(self, iid: str) -> None:
        """An entry over the title cell; Return keeps the text, Escape drops it."""
        bbox = self.tree.bbox(iid, "title")
        if not bbox or not iid.startswith("F"):
            return
        idx = int(iid[1:])
        x, y, w, h = bbox
        var = tk.StringVar(value=self.tree.set(iid, "title"))
        ent = ttk.Entry(self.tree, textvariable=var)
        ent.place(x=x, y=y, width=w, height=h)
        ent.focus_set()
        ent.select_range(0, "end")
        done = []

        def finish(keep: bool) -> None:
            if done:
                return
            done.append(True)
            ent.destroy()
            if keep and idx < len(self.files):
                self.set_chapter_title(idx, var.get())

        ent.bind("<Return>", lambda e: finish(True))
        ent.bind("<Escape>", lambda e: finish(False))
        ent.bind("<FocusOut>", lambda e: finish(True))

    # ------------------------------------------------------------ panel (continued)
    def _refresh_file_panel(self) -> None:
        st = self.current
        self._syncing = True
        try:
            self.var_title.set(self.book_title() if self.merging() else (st.title if st else ""))
            self.var_encoding.set(st.encoding if st else detect.AUTO)
            self._sync_encoding_combo()
        finally:
            self._syncing = False
        self._refresh_preview()
        self._refresh_tree()

    def _sync_encoding_combo(self) -> None:
        enc = self.var_encoding.get()
        idx = detect.ENCODINGS.index(enc) if enc in detect.ENCODINGS else 0
        try:
            self.cmb_enc.current(idx)
        except tk.TclError:
            pass

    def _refresh_preview(self) -> None:
        st = self.current
        self.txt_preview.configure(state="normal")
        self.txt_preview.delete("1.0", "end")
        border = "#ccc"
        self.lbl_enc_warn.configure(text="")
        if st is None:
            self.lbl_enc.configure(text="")
            self.lbl_preview_msg.configure(text=t("preview_empty"))
        elif st.loading:
            self.lbl_enc.configure(text="")
            self.lbl_preview_msg.configure(text=t("preview_loading"))
        elif st.error or st.loaded is None:
            self.lbl_enc.configure(text="")
            self.lbl_preview_msg.configure(text=t(st.error or "err_open_failed", name=st.name, error=st.error_text))
        else:
            det = st.loaded.detection
            self.lbl_enc.configure(text=t("enc_detected", enc=det.display, confidence=det.confidence))
            self.lbl_preview_msg.configure(text=t("preview_using", enc=detect.display_name(st.loaded.encoding)))
            self.txt_preview.insert("1.0", st.loaded.text[:PREVIEW_CHARS])
            if det.confidence < detect.LOW_CONFIDENCE or st.loaded.replaced:
                border = "#d00"
                self.lbl_enc_warn.configure(text=t("enc_low_confidence"))
        self.txt_preview.configure(state="disabled", highlightbackground=border, highlightcolor=border)

    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        if self.merging():
            self._refresh_merge_tree()
            return
        self.tree.heading("line", text=t("col_line"))
        self.lbl_pattern_err.configure(foreground="#c00")
        st = self.current
        if st is None or st.loaded is None:
            self.lbl_chapter_count.configure(text="")
            return
        rows = st.table()
        n = 0
        for r in rows:
            if not r.heading:
                self.tree.insert("", "end", iid=f"L{r.start}", values=("-", "", r.title, r.start + 1, r.chars))
                continue
            n += 1
            self.tree.insert("", "end", iid=f"L{r.start}",
                             values=(CHECK if r.enabled else "", n, r.title, r.start + 1, r.chars))
        count = len([r for r in rows if r.heading and r.enabled])
        if count == 0:
            self.lbl_chapter_count.configure(text=t("chapter_none"))
        else:
            self.lbl_chapter_count.configure(text=t("chapter_count", count=count))

    def _refresh_merge_tree(self) -> None:
        """One row per loaded file, in file order: tick = in the book, title = chapter title."""
        self.tree.heading("line", text=t("col_file"))
        self.lbl_pattern_err.configure(text=t("merge_hint"), foreground="#555")
        states = self._merge_states()
        parts = self.merge_parts(states)
        current_iid = ""
        for n, (st, part) in enumerate(zip(states, parts), 1):
            iid = f"F{self.files.index(st)}"
            if st is self.current:
                current_iid = iid
            self.tree.insert("", "end", iid=iid,
                             values=(CHECK if st.included else "", n, part.title, st.name, st.chars))
        self.lbl_chapter_count.configure(
            text=t("merge_count", count=sum(1 for s in states if s.included)) if states else "")
        if current_iid:
            self._syncing = True
            try:
                self.tree.selection_set(current_iid)
                self.tree.see(current_iid)
            finally:
                self._syncing = False

    # ------------------------------------------------------------ chapter edits
    def _on_encoding(self, _event=None) -> None:
        if self._syncing or self.current is None:
            return
        enc = detect.ENCODINGS[max(self.cmb_enc.current(), 0)]
        self.var_encoding.set(enc)
        self.current.manual.clear()
        self.current.disabled.clear()
        self._load_async(self.current, enc)

    def _on_split(self) -> None:
        self._redetect()

    def _redetect(self) -> None:
        for st in self.files:
            st.pattern_applied = ""
        if self.current:
            self._detect_for(self.current)
        self._refresh_tree()

    def _on_title_edit(self) -> None:
        if self._syncing:
            return
        if self.merging():
            self.merge_title_user = self.var_title.get()
            self._refresh_tree()  # the chapter titles drop the book title from the file names
            return
        if self.current is not None:
            self.current.title = self.var_title.get()

    def _on_tree_click(self, event) -> None:
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":
            return
        iid = self.tree.identify_row(event.y)
        if iid:
            self._toggle(iid)

    def _toggle_selected(self) -> None:
        sel = self.tree.selection()
        if sel:
            self._toggle(sel[0])

    def _toggle(self, iid: str) -> None:
        if iid.startswith("F") and self.merging():
            idx = int(iid[1:])
            if idx < len(self.files):
                self.files[idx].included = not self.files[idx].included
                self._refresh_tree()
                self.tree.selection_set(iid)
            return
        st = self.current
        if st is None or not iid.startswith("L"):
            return
        start = int(iid[1:])
        if start not in st.starts():
            return
        if start in st.disabled:
            st.disabled.discard(start)
        else:
            st.disabled.add(start)
        self._refresh_tree()
        self.tree.selection_set(iid)
        self.tree.see(iid)

    def _add_manual(self) -> None:
        st = self.current
        if st is None or st.loaded is None:
            return
        raw = self.var_line_no.get().strip()
        max_line = len(st.loaded.lines)
        try:
            n = int(raw)
            if not 1 <= n <= max_line:
                raise ValueError
        except ValueError:
            messagebox.showerror(t("dlg_error"), t("err_bad_line", max=max_line), parent=self.root)
            return
        start = n - 1
        if not st.loaded.lines[start].strip():
            messagebox.showerror(t("dlg_error"), t("err_blank_line"), parent=self.root)
            return
        st.manual.add(start)
        st.disabled.discard(start)
        self.var_line_no.set("")
        self._refresh_tree()
        self.tree.selection_set(f"L{start}")
        self.tree.see(f"L{start}")

    def _jump_preview(self) -> None:
        """Show the selected chapter's opening in the preview box."""
        st = self.current
        sel = self.tree.selection()
        if st is None or st.loaded is None or not sel:
            return
        start = 0 if sel[0].startswith("F") else int(sel[0][1:])
        text = "\n".join(st.loaded.lines[start: start + 60])
        self.txt_preview.configure(state="normal")
        self.txt_preview.delete("1.0", "end")
        self.txt_preview.insert("1.0", text[:PREVIEW_CHARS])
        self.txt_preview.configure(state="disabled")
        self.lbl_preview_msg.configure(text=t("preview_from_line", line=start + 1))

    # ------------------------------------------------------------ running
    def run(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        ready = [f for f in self.files if f.loaded is not None and not f.loading]
        if not self.files:
            messagebox.showinfo(t("app_title"), t("msg_no_files"), parent=self.root)
            return
        if not ready:
            messagebox.showinfo(t("app_title"), t("msg_still_loading"), parent=self.root)
            return
        opts = self.options()
        self._save_options()
        if opts.cover_mode == "file":
            try:
                import cover as cover_mod

                img = cover_mod.load_cover(opts.cover_path)
                if img.too_small:
                    self.log("warn_cover_small", width=img.width)
            except Exception:
                messagebox.showerror(t("dlg_error"), t("err_cover_open", name=os.path.basename(opts.cover_path)),
                                     parent=self.root)
                return
        if self.merging():
            self._run_merge(opts)
            return
        jobs: list[tuple[FileState, list[chap.Chapter]]] = []
        for st in ready:
            if st.pattern_applied != self._pattern_key():
                self._detect_for(st)
            chapters = st.selected()
            count = chap.heading_count(chapters)
            if count > chap.MANY_CHAPTERS and not messagebox.askyesno(
                    t("dlg_confirm"), t("warn_many_chapters", name=st.name, count=count), parent=self.root):
                self.log("log_skipped", name=st.name)
                continue
            jobs.append((st, chapters))
        if not jobs:
            return
        self.cancel_event.clear()
        self.outputs = []
        self.progress.configure(maximum=len(jobs), value=0)
        self._set_controls(running=True)

        def work() -> None:
            count = 0
            replaced = 0
            for idx, (st, chapters) in enumerate(jobs, 1):
                self.root.after(0, lambda _i=idx, _n=st.name: self._on_progress(_i - 1, _i, len(jobs), _n))
                try:
                    result = core.convert(st.loaded, opts, st.title, chapters, cancel=self.cancel_event)
                except core.Cancelled:
                    self.root.after(0, lambda _n=st.name: self.log("log_cancelled", name=_n))
                    self.root.after(0, lambda _c=count, _r=replaced: self._finished(True, _c, _r))
                    return
                except Exception as exc:  # one bad file must not end the batch
                    self.root.after(0, lambda _n=st.name, _e=exc: self.log("err_file_failed", name=_n, error=str(_e)))
                    continue
                count += 1
                replaced += result.replaced
                self.outputs.append(result.output_path)
                self.root.after(0, lambda _r=result, _n=st.name: self._log_result(_n, _r))
                self.root.after(0, lambda _i=idx: self.progress.configure(value=_i))
            self.root.after(0, lambda _c=count, _r=replaced: self._finished(False, _c, _r))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _run_merge(self, opts: Options) -> None:
        """One EPUB from every ticked file, in list order. A file that could not be
        read is left out with a line in the log."""
        if any(f.loading for f in self.files):
            messagebox.showinfo(t("app_title"), t("msg_still_loading"), parent=self.root)
            return
        states = self._merge_states()
        for st in self.files:
            if st not in states:
                self.log("log_skipped", name=st.name)
        parts = [p for st, p in zip(states, self.merge_parts(states)) if st.included]
        if not parts:
            messagebox.showinfo(t("app_title"), t("err_merge_none"), parent=self.root)
            return
        title = self.book_title().strip() or core.default_title(parts[0].path)
        if len(parts) > core.MANY_FILES and not messagebox.askyesno(
                t("dlg_confirm"), t("warn_many_chapters", name=title, count=len(parts)), parent=self.root):
            return
        self.cancel_event.clear()
        self.outputs = []
        n = len(parts)
        self.progress.configure(maximum=n + 1, value=0)
        self._set_controls(running=True)

        def progress(phase: str, i: int, total: int, name: str) -> None:
            self.root.after(0, lambda: self._on_merge_progress(phase, i, total, name))

        def work() -> None:
            try:
                result = core.convert_many(parts, opts, title, progress=progress, cancel=self.cancel_event)
            except core.Cancelled:
                self.root.after(0, lambda: self.log("log_cancelled", name=title))
                self.root.after(0, lambda: self._finished(True, 0, 0))
                return
            except Exception as exc:
                self.root.after(0, lambda _e=exc: self.log("err_file_failed", name=title, error=str(_e)))
                self.root.after(0, lambda: self._finished(False, 0, 0))
                return
            self.outputs.append(result.output_path)
            self.root.after(0, lambda: self.log("log_merged", files=n, count=result.chapters))
            self.root.after(0, lambda: self.log("log_saved", path=result.output_path))
            self.root.after(0, lambda: self._finished(False, 1, result.replaced))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _on_merge_progress(self, phase: str, i: int, n: int, name: str) -> None:
        if phase == "read":
            self.progress.configure(value=i - 1)
            self._set_status("status_reading", file=i, files=n, name=name)
        else:
            self.progress.configure(value=n)
            self._set_status("status_writing")

    def _log_result(self, name: str, r: core.FileResult) -> None:
        if r.no_chapters:
            self.log("log_no_chapters", name=name)
        else:
            self.log("log_chapters", name=name, count=r.chapters)
        self.log("log_saved", path=r.output_path)

    def _on_progress(self, done: int, file_idx: int, files: int, name: str) -> None:
        self.progress.configure(value=done)
        self._set_status("status_processing", file=file_idx, files=files, name=name)

    def _finished(self, cancelled: bool, count: int, replaced: int) -> None:
        self._set_controls(running=False)
        if cancelled or self._closing:
            self._set_status("status_cancelled")
            return
        self._set_status("status_done")
        self.progress.configure(value=self.progress["maximum"])
        if self.outputs:
            self.btn_open.configure(state="normal")
        msg = t("msg_done", count=count)
        if replaced:
            msg += "\n" + t("msg_replaced", count=replaced)
        messagebox.showinfo(t("app_title"), msg, parent=self.root)

    def cancel(self) -> None:
        self.cancel_event.set()
        self.btn_cancel.configure(state="disabled")

    def _set_controls(self, running: bool) -> None:
        for w in (self.btn_run, self.btn_add, self.btn_remove, self.btn_clear, self.btn_toggle, self.btn_jump,
                  self.rad_each, self.rad_one):
            w.configure(state="disabled" if running else "normal")
        self._apply_mode(running)
        self.cmb_lang.configure(state="disabled" if running else "readonly")
        self.cmb_enc.configure(state="disabled" if running else "readonly")
        self.btn_cancel.configure(state="normal" if running else "disabled")
        if running:
            self.btn_open.configure(state="disabled")

    def open_result(self) -> None:
        if not self.outputs:
            return
        target = self.outputs[0]
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", os.path.normpath(target)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", target])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(target)])
        except OSError:
            pass

    def _on_close(self) -> None:
        self._closing = True
        self.cancel_event.set()
        try:
            self._save_options()
        except Exception:
            pass
        self._close_when_idle()

    def _close_when_idle(self) -> None:
        """Wait for the worker before tearing down: it is a daemon thread and
        exiting under it mid-write would leave a truncated file behind."""
        if self.worker and self.worker.is_alive():
            self.root.after(100, self._close_when_idle)
            return
        self.root.destroy()

    def mainloop(self) -> None:
        self.root.mainloop()


def launch(initial_files: list[str] | None = None) -> None:
    App(initial_files).mainloop()
