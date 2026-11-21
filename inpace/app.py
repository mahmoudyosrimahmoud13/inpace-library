"""The local web app. Runs only on this computer (127.0.0.1)."""
from __future__ import annotations

import hashlib
import json
import zipfile
from . import __version__
from html import escape as html_escape
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time as _time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

from jinja2 import Environment, FileSystemBytecodeCache, FileSystemLoader, select_autoescape
from markupsafe import Markup
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.background import BackgroundTask
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import ai, books, builder, checks, clock, codenote, progress, editor, encourage, exchange, focus, folders, garden, integrations, langs, library, notifier, offline, organize, pace, races, record, reminders, roadmaps, updater
from . import mascot as mascot_mod
from .mascot import mascot
from .canon import now_utc, short
from .course import (HTML_EXT, MAX_MEDIA_PACK_BYTES, Course, CourseError, course_from_folder, course_to_pack,
                     files_from_folder, files_from_zip, lesson_parts, load_course, media_in_zip, strip_fences,
                     write_pack_with_media, youtube_parts)
from . import media as media_mod
from .exam import NoAnswers, build_exam, grade, new_seed
from .vault import COLORS, Vault, display_name, lesson_ahead

HERE = Path(__file__).parent
mimetypes.add_type("text/javascript", ".mjs")  # the PDF reader's scripts
SAMPLES = HERE / "sample_courses"
MEANINGFUL = {"lesson_done", "evidence_added", "writeup_saved", "quiz_taken", "exam_taken", "reflection_saved",
              "review_done", "commitment_set", "pause_started", "pause_ended"}

def _highlight(code: str, lang: str, attrs: str) -> str:
    """Colour code blocks on this computer (no internet needed)."""
    from html import escape
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name
    from pygments.util import ClassNotFound
    if lang == "mermaid":
        # A diagram: the page draws it (static/mermaid). Until then, and if it can't, the text shows.
        return f'<pre class="mermaid" dir="ltr">{escape(code)}</pre>'
    if not lang:
        return escape(code)
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        return escape(code)
    return highlight(code, lexer, HtmlFormatter(nowrap=True))


class _LazyMarkdown:
    """The lesson renderer, built the first time something is drawn from Markdown, not when inPace starts.
    (Importing markdown-it is one of the slower parts of starting, and many screens never need it.)"""
    _real = None

    def _get(self):
        if _LazyMarkdown._real is None:
            from markdown_it import MarkdownIt
            real = MarkdownIt("commonmark", {"html": False, "linkify": False, "highlight": _highlight}).enable("table")
            from . import mdfix
            mdfix.install(real)
            real.core.ruler.push("bidi", _bidi)
            _LazyMarkdown._real = real
        return _LazyMarkdown._real

    def render(self, src: str, env=None) -> str:
        from . import mdfix
        return self._get().render(src, env) if env is not None else mdfix.render(self._get(), src)

    def __getattr__(self, name):
        return getattr(self._get(), name)


md = _LazyMarkdown()

# Right to left: a lesson can mix Arabic and English. Every paragraph, heading, list, quote and table gets its
# own direction from the letters it mostly uses (code and links don't count), so an Arabic paragraph that
# starts with "Python" is still right to left, and English inside an Arabic course is left to right.
_RTL_LETTERS = re.compile(r"[\u0590-\u08FF\uFB1D-\uFDFF\uFE70-\uFEFF]")
_LTR_LETTERS = re.compile(r"[A-Za-z\u00C0-\u024F\u0370-\u03FF\u0400-\u04FF]")
_NOT_WORDS = re.compile(r"`[^`]*`|\]\([^)]*\)|https?://\S+")
_BIDI_BLOCKS = {"paragraph_open", "heading_open", "blockquote_open", "bullet_list_open", "ordered_list_open",
                "list_item_open", "table_open", "th_open", "td_open"}


def text_dir(text: str) -> str:
    """'rtl' or 'ltr', by which kind of words the text mostly has; 'auto' when it has none.
    Words, not letters: Arabic words are shorter, so "درس عن Python" is still right to left."""
    words = re.findall(r"\w+", _NOT_WORDS.sub(" ", text or ""))
    r = sum(1 for w in words if _RTL_LETTERS.search(w))
    l = sum(1 for w in words if not _RTL_LETTERS.search(w) and _LTR_LETTERS.search(w))
    return "rtl" if r > l else "ltr" if l > r else "auto"


def _bidi(state) -> None:
    toks = state.tokens
    for i, tok in enumerate(toks):
        if tok.type not in _BIDI_BLOCKS or tok.hidden:
            continue
        depth, words = 0, []
        for t in toks[i:]:
            depth += t.nesting
            if t.type == "inline":
                words.append(t.content)
            if depth <= 0:
                break
        tok.attrSet("dir", text_dir(" ".join(words)))


env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]),
                  extensions=["jinja2.ext.i18n"])
LOCALES = {p.stem: json.loads(p.read_text(encoding="utf-8"))
           for p in sorted((HERE / "locales").glob("*.json")) if langs.known(p.stem)}
CURRENT = {"lang": "en"}


def _patterns(table: dict) -> list:
    """Keys with {name} slots, like "Added {name}.", also translate messages built at run time."""
    out = []
    for key, val in table.items():
        if "{" in key and "}" in key:
            rx = re.escape(key)
            seen: set = set()

            def slot(m, seen=seen):
                name = m.group(1)
                if name in seen:
                    return f"(?P={name})"
                seen.add(name)
                return f"(?P<{name}>.+?)"
            rx = re.sub(r"\\\{(\w+)\\\}", slot, rx)
            out.append((len(re.sub(r"\{\w+\}", "", key)), re.compile(rx + r"\Z", re.S), val))
    out.sort(key=lambda x: -x[0])  # most specific first
    return [(rx, val) for _, rx, val in out]


PATTERNS = {lang: _patterns(t) for lang, t in LOCALES.items()}


def gettext(text: str) -> str:
    table = LOCALES.get(CURRENT["lang"])
    if not table or not text:
        return text
    hit = table.get(text)
    if hit is not None:
        return hit
    for rx, val in PATTERNS[CURRENT["lang"]]:
        m = rx.match(text)
        if m:
            parts = {}
            for k, v in m.groupdict().items():
                core = v.strip()
                tr = gettext(core) if core != text and any(c.isalpha() for c in core) else core
                parts[k] = v[: len(v) - len(v.lstrip())] + tr + v[len(v.rstrip()):]
            try:
                return val.format(**parts)
            except (KeyError, IndexError):
                return text
    return text


env.install_gettext_callables(gettext, lambda s, p, n: gettext(s if n == 1 else p), newstyle=False)
env.globals["_"] = gettext
env.globals["mascot"] = mascot
env.globals["island_plant"] = lambda k: garden.plant_svg(k, 1.0, False, 54)
env.globals["island_friend"] = lambda k: garden.friend_svg(k, 60)


def device_lang(accept_language: str | None) -> str:
    """The language inPace speaks before you choose one: whichever of its languages the device asks for first
    (the browser, or the phone's WebView, which sends the phone's language). Without the header, the computer's
    own locale. English when it asks for a language inPace doesn't have yet."""
    best, best_q = "", -1.0
    for part in (accept_language or "").split(","):
        tag, _, rest = part.strip().partition(";")
        code = langs.pick(tag.strip(), "")
        if not code:
            continue
        q = 1.0
        if rest.strip().startswith("q="):
            try:
                q = float(rest.strip()[2:])
            except ValueError:
                q = 0.0
        if q > best_q:  # equal weights: the first one listed wins
            best, best_q = code, q
    if best:
        return best
    import locale
    for value in (os.environ.get("LC_ALL"), os.environ.get("LC_MESSAGES"), os.environ.get("LANG"),
                  (locale.getlocale()[0] if hasattr(locale, "getlocale") else None)):
        if value and value not in ("C", "POSIX"):
            return langs.pick(value.split(".")[0], "en")
    return "en"


def say(msg: str, values: list | tuple = ()) -> str:
    text = gettext(msg)
    try:
        return text % tuple(values) if values else text.replace("%%", "%")
    except (TypeError, ValueError):
        return msg % tuple(values) if values else msg


env.globals["say"] = say
env.filters["short"] = short
# Color profiles for the whole app: (name, main colour, second colour) for the Settings preview.
ACCENTS = {
    "": ("Sunny", "#FFD43B", "#E6007E"),
    "ocean": ("Ocean", "#4DB8FF", "#FF6B35"),
    "mint": ("Mint", "#46D99A", "#7C3AED"),
    "rose": ("Rose", "#FF8FB1", "#2563EB"),
    "grape": ("Grape", "#B79CFF", "#F59E0B"),
    "nile": ("Nile", "#F4A259", "#0E7C86"),
    "mono": ("Ink", "#D4D4D4", "#111111"),
}

MONTHS = langs.MONTHS


def nice_date(s: str | None) -> str:
    """2026-11-11 -> "Nov 11, 2026" or "11 نوفمبر 2026"."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s or "")
    if not m:
        return (s or "")[:10]
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    lang = CURRENT["lang"]
    name = MONTHS.get(lang, MONTHS["en"])[mo - 1]
    return langs.DATE_ORDER.get(lang, langs.DATE_ORDER["en"]).format(d=d, m=name, y=y)


def tr_lines(text: str | None) -> str:
    """A message can be several sentences joined by new lines; translate each one."""
    return " ".join(gettext(x) for x in (text or "").split("\n") if x)


def t(text: str, **values) -> str:
    """Translate a sentence with {name} slots, then fill them in."""
    out = gettext(text)
    try:
        return out.format(**values)
    except (KeyError, IndexError, ValueError):
        return text.format(**values)


env.filters["date"] = nice_date
env.globals["T"] = t
env.globals["ACCENTS"] = ACCENTS
env.globals["display_name"] = display_name


def avatar(p: dict, size: int = 36) -> Markup:
    """A person's picture: their turtle when they made one, otherwise their first letter on their colour."""
    if p.get("avatar"):
        return Markup('<span class="avatar turtle" style="--s: {}px" aria-hidden="true">{}</span>').format(
            int(size), mascot_mod.buddy_head(p["avatar"], int(size)))
    color = p.get("color") or "#3A506B"
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        color = "#3A506B"
    letter = (display_name(p) or "?")[:1].upper()
    return Markup('<span class="avatar" style="--c: {}; --s: {}px" aria-hidden="true">{}</span>').format(
        color, int(size), letter)


env.globals["avatar"] = avatar


def chest(opened: bool, trophy: bool = False) -> Markup:
    """A little treasure chest (or the trophy at the end of a course) for the course rewards track."""
    if trophy:
        fill = "#FFD43B" if opened else "#E9E3D6"
        return Markup(f'<svg width="26" height="26" viewBox="-14 -40 28 42" aria-hidden="true"><path d="M-12 -38 H12 V-26 Q12 -12 0 -10 Q-12 -12 -12 -26 Z" fill="{fill}" stroke="#111" stroke-width="3" stroke-linejoin="round"/>'
                      f'<path d="M-3 -10 V-4 H3 V-10 M-9 0 H9 V-4 H-9 Z" fill="{fill}" stroke="#111" stroke-width="3" stroke-linejoin="round"/></svg>')
    if opened:
        return Markup('<svg width="26" height="24" viewBox="0 0 26 24" aria-hidden="true"><path d="M3 12 H23 V22 H3 Z" fill="#B5651D" stroke="#111" stroke-width="2"/>'
                      '<path d="M3 12 L6 3 H20 L23 12" fill="#985518" stroke="#111" stroke-width="2" stroke-linejoin="round"/>'
                      '<circle cx="10" cy="11" r="2.6" fill="#FFD43B" stroke="#111" stroke-width="1.2"/><circle cx="15" cy="10" r="2.6" fill="#F8BBD0" stroke="#111" stroke-width="1.2"/>'
                      '<path d="M3 16 H23" stroke="#FFD43B" stroke-width="2"/></svg>')
    return Markup('<svg width="26" height="24" viewBox="0 0 26 24" aria-hidden="true"><path d="M3 11 H23 V22 H3 Z" fill="#B5651D" stroke="#111" stroke-width="2"/>'
                  '<path d="M3 11 Q3 4 13 4 Q23 4 23 11 Z" fill="#985518" stroke="#111" stroke-width="2"/>'
                  '<path d="M3 13 H23" stroke="#FFD43B" stroke-width="2"/><rect x="11" y="11" width="4" height="5" fill="#FFD43B" stroke="#111" stroke-width="1.2"/></svg>')


env.globals["chest"] = chest

# Your colour follows your turtle's shell (the colours are close: green to green, blue to blue...).
COLOR_FOR_SHELL = [1, 4, 7, 3, 0, 5, 6, 2]
ACC_NAMES = {"none": "Nothing", "cap": "Cap", "beanie": "Beanie", "bow": "Bow", "glasses": "Glasses",
             "headphones": "Headphones", "flower": "Flower", "crown": "Crown", "wizard": "Wizard hat", "gradcap": "Graduation cap"}

_ICONS = {
    # the PDF reader and the picture viewer (v1.25)
    "zoom-in": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M8 11h6M11 8v6"/>',
    "zoom-out": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M8 11h6"/>',
    "fit-width": '<path d="M3 5v14M21 5v14M7 12h10M10 9l-3 3 3 3M14 9l3 3-3 3"/>',
    "fit-page": '<rect x="6" y="3" width="12" height="18" rx="1"/><path d="M9 8h6M9 12h6M9 16h4"/>',
    "rotate": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
    "expand": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    "actual": '<rect x="3" y="5" width="18" height="14" rx="1"/><path d="M8 10v5M12 10v.01M12 14v.01M16 10v5"/>',
    "back": '<path d="M15 5l-7 7 7 7"/>',
    "forward": '<path d="M9 5l7 7-7 7"/>',
    "home": '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"/>',
    "book": '<path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H20v15H5.5A1.5 1.5 0 0 0 4 19.5z"/><path d="M4 19.5A1.5 1.5 0 0 0 5.5 21H20"/>',
    "flag": '<path d="M5 21V4"/><path d="M5 4h11l-2 4 2 4H5"/>',
    "spark": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M21.5 20a6.5 6.5 0 0 0-4-6"/>',
    "open": '<path d="M3 19V6a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v2"/><path d="M3 19l3-8h15l-3 8z"/>',  # an open folder (v1.31.1: was the same as download)
    "chat": '<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9.5h8M8 12.5h5"/>',
    "discord": '<path fill="currentColor" stroke="none" d="M20.317 4.37a19.79 19.79 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.865-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.74 19.74 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.1 13.1 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.126-.094.252-.192.372-.291a.074.074 0 0 1 .078-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.3 12.3 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.84 19.84 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>',
    "telegram": '<path fill="currentColor" stroke="none" d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>',
    "upload": '<path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M4 17v3h16v-3"/>',
    "download": '<path d="M12 4v12"/><path d="m7 11 5 5 5-5"/><path d="M4 17v3h16v-3"/>',
    "pen": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
    "quiz": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6"/><path d="M12 17h.01"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "shield": '<path d="M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6z"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
    "send": '<path d="M21 3 10 14"/><path d="M21 3 14 21l-4-7-7-4z"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "moon": '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "settings": '<path d="M10.31 5.21 L10.66 2.49 L13.34 2.49 L13.69 5.21 L15.61 6.00 L17.78 4.33 L19.67 6.22 L18.00 8.39 L18.79 10.31 L21.51 10.66 L21.51 13.34 L18.79 13.69 L18.00 15.61 L19.67 17.78 L17.78 19.67 L15.61 18.00 L13.69 18.79 L13.34 21.51 L10.66 21.51 L10.31 18.79 L8.39 18.00 L6.22 19.67 L4.33 17.78 L6.00 15.61 L5.21 13.69 L2.49 13.34 L2.49 10.66 L5.21 10.31 L6.00 8.39 L4.33 6.22 L6.22 4.33 L8.39 6.00Z"/><circle cx="12" cy="12" r="3"/>',  # a gear (v1.25; it used to look like a sun)
    "file": '<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5"/>',
    "arrow": '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
    "up": '<path d="m6 15 6-6 6 6"/>',
    "down": '<path d="m6 9 6 6 6-6"/>',
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
    "play": '<path d="M7 4.5v15l13-7.5z"/>',
    "code": '<path d="m8 7-5 5 5 5"/><path d="m16 7 5 5-5 5"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "alert": '<path d="M12 3 2.5 20h19z"/><path d="M12 10v4.5M12 17.5v.01"/>',
    "shell": '<path d="M12 19.5 3.6 10.6q1-2.2 2.6-1.5.7-2.8 3.1-2.6Q10.4 4 12 4t2.7 2.5q2.4-.2 3.1 2.6 1.6-.7 2.6 1.5z"/><path d="M12 19.5V7M12 19.5 9 7.5M12 19.5l3-12M12 19.5 6.6 10M12 19.5 17.4 10"/><path d="M10 19.5h4l-.6 1.5h-2.8z"/>',
    "island": '<path d="M3 20c2-1.4 4-1.4 6 0s4 1.4 6 0 4-1.4 6 0"/><path d="M12 17V9"/><path d="M12 9c-1.5-2.5-4.5-3-7-1.5 2.6.2 4.6 1 7 1.5z"/><path d="M12 9c1.5-2.5 4.5-3 7-1.5-2.6.2-4.6 1-7 1.5z"/><path d="M12 9c-.5-2.6.6-4.6 3-6-.9 2.2-1.6 4-3 6z"/><path d="M7 17c1.5-1.8 8.5-1.8 10 0"/>',
    "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    "alarm": '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2 2M5 3 2 6M22 6l-3-3M6.4 18.7 4 21M17.6 18.7 20 21"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "library": '<path d="M4 4h4v16H4zM10 4h4v16h-4z"/><path d="m16 5.2 3.9-1 3.6 15.3-3.9 1z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "route": '<circle cx="6" cy="19" r="2.2"/><circle cx="18" cy="5" r="2.2"/><path d="M8.2 19H15a3.5 3.5 0 0 0 0-7H9a3.5 3.5 0 0 1 0-7h6.8"/>',
    "more": '<circle cx="5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="19" cy="12" r="1.3"/>',
    "grip": '<circle cx="9" cy="6" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="18" r="1"/>',
    "x": '<path d="M6 6l12 12M18 6 6 18"/>',
    "video": '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="m16 10 5-3v10l-5-3"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "timer": '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 2M9 2h6"/>',
    "pause": '<path d="M8 5v14M16 5v14"/>',
    "stop": '<rect x="6" y="6" width="12" height="12"/>',
    "popout": '<rect x="3" y="5" width="18" height="14"/><rect x="12" y="12" width="7" height="5" fill="currentColor"/>',
    "shrink": '<path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7"/>',
    "doc": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    "audio": '<path d="M9 18V6l10-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="16.5" cy="16" r="2.5"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/>',
}


def icon(name: str, size: int = 20) -> Markup:
    return Markup(
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        f'{_ICONS.get(name, "")}</svg>')


env.globals["icon"] = icon


def _static_stamp(name: str) -> str:
    """A short fingerprint of a file in static/: it changes whenever the file does, so after an update the
    app window loads the new script and styles instead of the copy it kept (they're cached for a year)."""
    try:
        return hashlib.sha256((HERE / "static" / name).read_bytes()).hexdigest()[:10]
    except OSError:
        return __version__


STATIC_V = {n: _static_stamp(n) for n in ("app.js", "style.css", "builder.js")}
env.globals["static_v"] = STATIC_V
env.globals["LANGS"] = langs.LANGS
env.globals["lang_dir"] = langs.direction
DISCORD_URL = "https://mahmoudyosrimahmoud13.github.io/inPace/discord.html"  # opens the server's invite
TELEGRAM_URL = "https://mahmoudyosrimahmoud13.github.io/inPace/telegram.html"  # opens the news channel, t.me/inPace_app


def cover(c, big: bool = False, sample: bool = False) -> Markup:
    """The course's picture, or a coloured tile with its first letter when it has none."""
    cls = "cover big" if big else "cover"
    img = (c.extra or {}).get("image")
    if img:
        base = "/sample-file" if sample else "/m"
        return Markup('<img class="{}" src="{}/{}/{}" alt="" loading="lazy">').format(cls, base, quote(c.id), quote(img))
    hue = sum(ord(ch) for ch in c.id) % 360
    letter = (c.title.strip()[:1] or "?").upper()
    return Markup('<span class="{} blank" style="--hue:{}" aria-hidden="true">{}</span>').format(cls, hue, letter)


env.globals["cover"] = cover


def filesize(n) -> str:
    n = float(n or 0)
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


env.filters["filesize"] = filesize
from .course import media_kind as _media_kind
env.globals["media_kind"] = _media_kind
from .offline import KEEP_FREE as _KEEP_FREE, nice_size as _nice_size  # noqa: E402
env.globals["nice_size"] = _nice_size
env.globals["keep_free"] = _KEEP_FREE
env.globals["on_phone"] = lambda: os.environ.get("INPACE_MOBILE") == "android"
env.globals["TASK_LABEL"] = {"practical": "Your work", "explain": "Explain it", "quiz": "Quiz"}
env.globals["TASK_ICON"] = {"practical": "upload", "explain": "pen", "quiz": "quiz"}


def _drop_title(content: str, title: str) -> str:
    """The page already shows the lesson title, so skip a first heading that repeats it."""
    lines = content.lstrip().splitlines()
    if lines and lines[0].startswith("#") and lines[0].lstrip("#").strip().lower() == title.strip().lower():
        return "\n".join(lines[1:])
    return content


_SAMPLE_CACHE: list = []


def _sample_courses() -> list:
    """The sample courses that come with inPace. They never change while the app runs, so they're read once
    (reading them on every visit made "My courses" the slowest page, most of all on phones)."""
    if not _SAMPLE_CACHE:
        found = []
        for p in sorted(SAMPLES.iterdir()):
            if p.is_dir():
                try:
                    found.append(load_course(files_from_folder(p)))
                except CourseError:
                    pass
        _SAMPLE_CACHE.extend(found or [None])
    return [c for c in _SAMPLE_CACHE if c is not None]


class NavMiddleware:
    """Two small rules for every response, so Back always shows the app as it is now.

    - Pages are never kept in the cache (no-store). Going back loads them again, so a page shows the
      language and colors you have now, and a finished quiz can't come back with your old answers.
    - A form sent by the app's own script (header X-InPace-Nav) gets {"go": url} instead of a
      redirect. The script then replaces the page, so one-off pages don't pile up behind Back.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        nav = False
        static = b""
        if scope.get("path", "").startswith("/static/"):
            static = (b"public, max-age=31536000, immutable" if b"v=" in scope.get("query_string", b"")
                      else b"public, max-age=86400")
        for k, val in scope.get("headers", []):
            if k == b"x-inpace-nav":
                nav = True
            elif k == b"cookie" and b"tz=" in val:
                clock.from_cookie(val)  # the island's sky follows the person's real clock
        state = {"swallow": False}

        async def wrapped(msg):
            if msg["type"] == "http.response.start":
                headers = list(msg.get("headers", []))
                found = {k.lower(): v for k, v in headers}
                if nav and msg["status"] in (301, 302, 303, 307, 308) and b"location" in found:
                    body = json.dumps({"go": found[b"location"].decode("latin-1")}).encode()
                    state["swallow"] = True
                    await send({"type": "http.response.start", "status": 200,
                                "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store"),
                                            (b"content-length", str(len(body)).encode())]})
                    await send({"type": "http.response.body", "body": body})
                    return
                if found.get(b"content-type", b"").startswith(b"text/html") and b"cache-control" not in found:
                    headers.append((b"cache-control", b"no-store"))
                    msg = {**msg, "headers": headers}
                elif static and msg["status"] == 200 and b"cache-control" not in found:
                    # inPace's own files (styles, script, fonts, icons). The page names styles and script with
                    # ?v=<number>, which changes with every release, so those can be kept for good: the window
                    # doesn't ask for them again on every page. The others are kept for a day.
                    headers.append((b"cache-control", static))
                    msg = {**msg, "headers": headers}
                await send(msg)
            elif not state["swallow"]:
                await send(msg)

        await self.app(scope, receive, wrapped)


def _library_groups(index: dict, entries: list[dict], lang: str) -> tuple[list[dict], list[dict]]:
    """The library list in sections (from the library's sections list), and the buttons above it.
    Inside a section: new courses first, then beginner to advanced, your language first, then by title.
    An older library without sections: one group, and the most shared tags as buttons."""
    rank = {"beginner": 0, "intermediate": 1, "advanced": 2}

    def order(e):
        tags = [str(x).lower() for x in (e.get("tags") or [])]
        lvl = min([rank[t] for t in tags if t in rank] or [1])
        return (not e.get("new"), lvl, e.get("language") != lang, str(e.get("title", "")).lower())

    secs = [x for x in (index.get("sections") or []) if isinstance(x, dict) and x.get("id")]
    if secs:
        known = {x["id"] for x in secs}
        groups = []
        for x in secs:
            items = sorted([e for e in entries if (e.get("section") if e.get("section") in known else "other") == x["id"]], key=order)
            if items:
                label = str(x.get(lang) or x.get("en") or x["id"])
                groups.append({"id": x["id"], "label": label, "entries": items})
        rest = [e for e in entries if e.get("section") not in known]
        if rest and not any(g["id"] == "other" for g in groups):
            groups.append({"id": "other", "label": "", "entries": sorted(rest, key=order)})
        return groups, [{"id": g["id"], "label": g["label"]} for g in groups if g["label"]]
    counts: dict[str, int] = {}
    for e in entries:
        for tag in {str(x).strip().lower() for x in (e.get("tags") or []) if str(x).strip()}:
            counts[tag] = counts.get(tag, 0) + 1
    tags = [tag for tag, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if n > 1][:10]
    return [{"id": "", "label": "", "entries": sorted(entries, key=lambda e: not e.get("new"))}], [{"id": t, "label": t} for t in tags]


# Roadmap thumbnails (v1.28.17): a neobrutalist card built from the covers of the roadmap's first courses, so every
# roadmap (library or your own) gets a picture without anyone drawing one. Pure HTML and CSS, works offline.
RM_THUMB_COLORS = ("#FFD43B", "#9ED8F0", "#FF8FC2", "#9EE6B8", "#C9B6FF", "#FFB86B")


def roadmap_thumb(rm: dict, pics: dict, big: bool = False) -> Markup:
    """pics: course id -> ("img", url) or ("blank", letter, hue). Up to three covers, fanned, plus the path."""
    steps = [s for s in (rm.get("steps") or []) if isinstance(s, dict) and s.get("course")]
    seed = sum(ord(ch) for ch in str(rm.get("id") or rm.get("title") or "rm"))
    color = RM_THUMB_COLORS[seed % len(RM_THUMB_COLORS)]
    cards = []
    for i, s in enumerate(steps[:3]):
        p = pics.get(s["course"])
        if p and p[0] == "img":
            inner = Markup('<img src="{}" alt="" loading="lazy" decoding="async">').format(p[1])
        else:
            letter = (p[1] if p else (str(s.get("title") or s["course"])[:1] or "?")).upper()
            hue = p[2] if p else sum(ord(ch) for ch in s["course"]) % 360
            inner = Markup('<b class="rt-blank" style="--hue:{}">{}</b>').format(hue, letter)
        cards.append(Markup('<span class="rt-c rt-c{}">{}</span>').format(i, inner))
    dots = Markup("").join(Markup("<i>{}</i>").format(n) for n in range(1, min(len(steps), 3) + 1))
    more = Markup('<i class="rt-more">+{}</i>').format(len(steps) - 3) if len(steps) > 3 else Markup("")
    n = len(steps)
    label = gettext("{n} courses").replace("{n}", str(n)) if n != 1 else gettext("1 course")
    return Markup('<span class="rt{}" style="--rt-bg:{}" aria-hidden="true"><span class="rt-dots"></span>'
                  '<span class="rt-stack rt-n{}">{}</span><span class="rt-path">{}{}<i class="rt-port">⚓</i></span>'
                  '<span class="rt-count">{}</span></span>').format(
        " big" if big else "", color, len(cards), Markup("").join(cards), dots, more, label)


def create_app(vault: Vault) -> Starlette:
    V = vault

    def _rm_pics(rm: dict, index: dict | None = None) -> dict:
        lib = {str(e.get("id")): e for e in (index or {}).get("courses") or [] if isinstance(e, dict)}
        pics = {}
        for s in (rm.get("steps") or [])[:3]:
            cid = s.get("course") if isinstance(s, dict) else None
            if not cid:
                continue
            c = V.get_course(cid)
            img = (c.extra or {}).get("image") if c else None
            if img:
                pics[cid] = ("img", f"/m/{quote(c.id)}/{quote(img)}")
            elif (lib.get(cid) or {}).get("cover"):
                pics[cid] = ("img", str(lib[cid]["cover"]))
            else:
                title = (c.title if c else (lib.get(cid) or {}).get("title")) or s.get("title") or cid
                pics[cid] = ("blank", (title.strip()[:1] or "?"), sum(ord(ch) for ch in cid) % 360)
        return pics

    def rm_thumb(rm: dict, index: dict | None = None, big: bool = False) -> Markup:
        try:
            return roadmap_thumb(rm, _rm_pics(rm, index), big)
        except Exception:  # a picture must never break the page
            return Markup("")

    env.globals["rm_thumb"] = rm_thumb
    from . import ytrules
    ytrules.use_home(V.home, pref=lambda: (V._meta("yt_ad_guard", "on") or "on") == "on",
                     block_pref=lambda: (V._meta("yt_ad_block", "on") or "on") == "on")
    # Pages are drawn from templates, and turning a template into Python takes time the first time (a lot of it
    # on a phone). Keep the compiled templates in the data folder, so the next start reuses them. Jinja checks
    # each template's source, so an updated inPace never uses an old copy.
    try:
        cache = V.home / "cache" / "templates"
        cache.mkdir(parents=True, exist_ok=True)
        env.bytecode_cache = FileSystemBytecodeCache(str(cache))
    except OSError:
        env.bytecode_cache = None  # a read-only folder: compile in memory, like before

    # Warm up (v1.30.12): a few seconds after the start, read every page's template in the background, slowly,
    # so the first visit to a page doesn't wait for it. On a phone that wait was up to a second per page.
    def _warm_templates():
        import time as _t
        _t.sleep(3)
        for name in env.list_templates(filter_func=lambda n: n.endswith(".html")):
            try:
                env.get_template(name)
            except Exception:
                pass
            _t.sleep(0.02)  # stay out of the way of a page being drawn
    if not os.environ.get("INPACE_NO_WARMUP") and "pytest" not in sys.modules:  # tests make many short-lived apps
        threading.Thread(target=_warm_templates, name="inpace-warm", daemon=True).start()

    # ---- helpers -------------------------------------------------------------
    def page(name: str, request: Request, **ctx) -> HTMLResponse:
        if V.is_set_up:
            CURRENT["lang"] = V._meta("lang", "en") or "en"
        else:  # first open: the language you picked on the welcome page, else the device's
            CURRENT["lang"] = V._meta("lang", "") or device_lang(request.headers.get("accept-language"))
        base = {"request": request, "msg": tr_lines(request.query_params.get("ok")) or None,
                "err": tr_lines(request.query_params.get("err")) or None, "lang": CURRENT["lang"],
                "theme": (V._meta("theme", "") or "") if V.is_set_up else "",
                "accent": (V._meta("accent", "") or "") if V.is_set_up else "",
                "black": V.is_set_up and V._meta("dark_style", "") == "black",
                "update": _update_info() if V.is_set_up else None,
                "update_news": _update_news() if V.is_set_up else None,
                "lib_new": (_look_for_courses() or len(_library_new())) if V.is_set_up else 0,
                "dl_now": _downloads_now(),
                "_yt": _yt_rules_later(),
                "yay": encourage.CELEBRATE.get(request.query_params.get("yay", ""))}
        if V.is_set_up:
            base["me"] = V.me
            base["checking"] = [
                {**p, "waiting": V.waiting_count(p["id"])} for p in V.people() if p["i_check"]
            ]
            base["active_path"] = request.url.path
            base["resume"] = _last_lesson()
            base["island_on"] = garden.is_on(V)
            try:  # the floating timer, on every page
                base["timer_json"] = json.dumps(_timer_live()).replace("<", "\\u003c")
            except Exception:
                base["timer_json"] = '{"on": false}'
            base["timer_look"] = focus.look(V)
            base["timer_here"] = _timer_here(request.url.path)
            if os.environ.get("INPACE_MOBILE"):
                try:
                    base["trip_live_json"] = json.dumps(_trip_live()).replace("<", "\\u003c")
                except Exception:
                    base["trip_live_json"] = "null"
            elif base["island_on"]:
                _arm_trip_timer()
            if base["island_on"] and not request.url.path.startswith("/island/trip"):
                try:
                    garden.decay(V)  # what the fog did while you were away
                    base["island_news"] = garden.news(V)
                except Exception:
                    base["island_news"] = []
            away = reminders.touch(V)
            if away:
                V._set_meta("welcome_back", str(away))
        base.update(ctx)
        return HTMLResponse(env.get_template(name).render(**base))

    def _timer_live() -> dict:
        d = focus.live(V)
        _arm_focus_timer(d)
        return d

    def _timer_here(path: str) -> dict:
        """What you're studying on this page, so a timer started here is labelled with it."""
        m = re.match(r"^/learn/([^/]+)", path)
        if not m:
            return {}
        try:
            j = V.journey(m.group(1))
            c = V.get_course(j["course_id"]) if j else None
            return {"journey": j["id"], "label": c.title} if c else {}
        except Exception:
            return {}

    _focus_timer: dict = {"key": None, "timer": None}

    def _arm_focus_timer(d: dict | None = None) -> None:
        """On a computer, say "time's up" the moment a plain timer ends, even if inPace is minimized.
        (A timer that grows a plant is an island trip: _arm_trip_timer says that one.)"""
        if os.environ.get("INPACE_MOBILE") or (os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("INPACE_TEST_TRIP_TIMER")):
            return
        try:
            d = d if d is not None else focus.live(V)
            key = f'{d["id"]}:{d["left"]:.0f}' if d.get("on") and d.get("kind") == "timer" and d["state"] == "running" else None
            if key and _focus_timer["key"] and _focus_timer["key"].split(":")[0] == d["id"] and _focus_timer["timer"]:
                return  # already set for this timer
            if _focus_timer["timer"]:
                _focus_timer["timer"].cancel()
            _focus_timer.update(key=key, timer=None)
            if key:
                tm = threading.Timer(max(1.0, d["left"] + 0.6), _focus_ring)
                tm.daemon = True
                tm.start()
                _focus_timer["timer"] = tm
            if d.get("kind") == "trip":
                _arm_trip_timer()
        except Exception:
            pass

    def _focus_ring() -> None:
        _focus_timer.update(key=None, timer=None)
        try:
            CURRENT["lang"] = V._meta("lang", "en") or "en"
            d = focus._load(V)
            if not d or focus.elapsed(d) < d["goal"] - 1:
                return  # paused or stopped meanwhile
            notifier.notify(say("Time's up!"), t("{n} minutes of focus. Take a short break.", n=round(d["goal"] / 60)),
                            "/", V.home)
        except Exception:
            pass

    async def timer_json(request: Request):
        return JSONResponse(_timer_live(), headers={"Cache-Control": "no-store"})

    async def timer_action(request: Request):
        """Start, pause, go on or stop the floating timer. Answers with the timer as it is now."""
        what = request.path_params["what"]
        form = await request.form()
        if what == "start":
            try:
                minutes = int(form.get("minutes") or 25)
            except ValueError:
                minutes = 25
            focus.start(V, minutes, plant=form.get("plant") == "1", label=str(form.get("label", "")),
                        journey=str(form.get("journey", "")))
        elif what == "pause":
            focus.pause(V)
        elif what == "resume":
            focus.resume(V)
        elif what == "stop":
            focus.stop(V)
        elif what == "add":
            focus.add(V, 5)
        else:
            return Response(status_code=404)
        if request.headers.get("accept", "").startswith("application/json") or request.headers.get("x-inpace-fetch"):
            return JSONResponse(_timer_live())
        return go(_back(request))

    async def window_popout(request: Request):
        """Open the pop-out mini window: a small inPace window that stays on top of your other apps.
        Answers {"ok": false} when this window can't make one (then the page uses the browser's own way)."""
        from . import window as win
        form = await request.form()
        url = str(form.get("url", ""))
        if not url.startswith("/"):
            return JSONResponse({"ok": False})
        base = f"{request.url.scheme}://{request.url.netloc}"
        return JSONResponse({"ok": win.popout(base + url)})

    async def window_popout_close(request: Request):
        from . import window as win
        return JSONResponse({"ok": win.close_popout()})

    async def timer_settings(request: Request):
        form = await request.form()
        if form.get("look"):
            focus.set_look(V, str(form.get("look")))
        if request.headers.get("x-inpace-fetch"):
            return Response(status_code=204)
        return go("/settings#timer", ok="Saved.")

    def _last_lesson() -> dict | None:
        """The lesson you opened last, for the "Continue" button in the side bar."""
        row = V.db.execute(
            "SELECT e.journey, e.data FROM events e JOIN journeys j ON j.id = e.journey "
            "WHERE e.type = 'lesson_opened' AND j.archived = 0 ORDER BY e.seq DESC LIMIT 1").fetchone()
        if not row:
            return None
        j = V.journey(row["journey"])
        c = V.get_course(j["course_id"]) if j else None
        found = c.find_lesson(json.loads(row["data"]).get("lesson", "")) if c else None
        if not found:
            return None
        return {"url": f"/learn/{j['id']}/lesson/{found[1]['id']}", "lesson": found[1]["title"], "course": c.title}

    async def nav_index(request: Request):
        """Everything you can jump to from the search box (Ctrl+K)."""
        items = [{"t": say(n), "u": u, "k": say("Page")} for n, u in (
            ("Home", "/"), ("My courses", "/courses"), ("Milestones", "/milestones"), ("Races", "/races"),
            ("Make a course with AI", "/ai"), ("Make one by hand", "/edit/new"), ("People", "/people"),
            ("Open a file", "/open"), ("Settings", "/settings"), ("Reminders and alarms", "/reminders"),
            ("Show the tour again", "/?tour=1"))]
        for c in V.courses():
            jid = V.journey_for_course(c.id)
            items.append({"t": c.title, "u": f"/learn/{jid}" if jid else "/courses", "k": say("Course")})
            items.append({"t": t("Edit {name}", name=c.title), "u": f"/edit/{c.id}", "k": say("Edit")})
            if jid:
                for m in c.modules:
                    for les in m["lessons"]:
                        items.append({"t": les["title"], "u": f"/learn/{jid}/lesson/{les['id']}",
                                      "k": f"{c.title} › {m['title']}"})
                    if m["requires"]:
                        items.append({"t": t("{name} tasks", name=m["title"]), "u": f"/learn/{jid}/module/{m['id']}",
                                      "k": c.title})
        for p in V.people():
            items.append({"t": display_name(p), "u": "/people", "k": say("Person")})
        return JSONResponse(items[:3000])

    async def set_accent(request: Request):
        form = await request.form()
        accent = str(form.get("accent", ""))
        V._set_meta("accent", accent if accent in ACCENTS else "")
        return go("/settings#colors", ok="Colors saved.")

    def go(url: str, ok: str | None = None, err: str | None = None, yay: str | None = None) -> RedirectResponse:
        """Redirect after a form, with a message. The message goes before any #section: after the "#" the
        browser would only scroll, not load the page again, so the change wouldn't show."""
        base, _, section = url.partition("#")
        extra = [f"{k}={quote(v)}" for k, v in (("yay", yay), ("ok", ok), ("err", err)) if v]
        if extra:
            base += ("&" if "?" in base else "?") + "&".join(extra)
        return RedirectResponse(base + ("#" + section if section else ""), status_code=303)

    def download(data: bytes, filename: str, mime: str = "application/octet-stream") -> Response:
        safe = re.sub(r"[^\w .,()-]+", "", filename, flags=re.UNICODE).strip() or "file"
        return Response(data, media_type=mime, headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe)}"})

    def journey_or_404(jid: str):
        j = V.journey(jid)
        if not j or not V.get_course(j["course_id"]):
            return None
        return j

    def has_new(jid: str) -> bool:
        return any(e["type"] in MEANINGFUL for e in V.events(jid, V.last_event_in_milestones(jid)))

    def journey_card(j: dict) -> dict:
        prog = V.progress(j["id"])
        ms = V.milestones(j["id"])
        last_ok = next((a for m in reversed(ms) for a in m["approvals"] if a["decision"] == "approved"), None)
        waiting = [m for m in ms if not any(a["decision"] == "approved" for a in m["approvals"])]
        exams = checks.my_exams(V, j["id"])
        evs = V.events(j["id"])
        card: dict
        wk = pace.weeks(evs, [m["body"]["created_at"] for m in ms])
        packed_at = V._meta(f"pack:{j['id']}", "") or ""
        card = {"journey": j, "progress": prog, "milestones": ms, "last_ok": last_ok, "waiting": waiting,
                "has_new": has_new(j["id"]), "chain_problems": V.check_my_chain(j["id"]),
                "exams_waiting": [x for x in exams if not x["taken"]],
                "requests": [r for r in checks.requests_for(V, j["id"]) if r["at"] > packed_at],
                "pace": wk, "paused": pace.is_paused(evs),
                "forecast": pace.forecast(j["started_at"], prog["percent"]),
                "due": len(pace.due_cards(V, j["course_id"])) if prog["course"].has_answers else 0}
        card["tempo"] = encourage.greeting(card)
        return card

    # ---- setup ---------------------------------------------------------------
    # ---- your turtle ------------------------------------------------------------------------------
    def _owned() -> set[str]:
        try:
            return set(json.loads(V._meta("island_owned", "[]") or "[]"))
        except ValueError:
            return set()

    def _turtle_from(form) -> dict:
        """The turtle from the maker's form. Hats bought with shells only if you own them."""
        def num(k):
            try:
                return int(form.get(k, 0))
            except (TypeError, ValueError):
                return 0
        av = mascot_mod.clean_avatar({"shell": num("shell"), "scarf": num("scarf"), "skin": num("skin"),
                                      "acc": str(form.get("acc", "none"))})
        if av["acc"] in mascot_mod.PAID_ACCESSORIES and f"accessory:{av['acc']}" not in _owned():
            av["acc"] = "none"
        return av

    def _maker(av: dict) -> dict:
        owned = _owned()
        base = str(mascot_mod.builder_svg(av))
        accs, locked_any = [], False
        for a in mascot_mod.ACCESSORIES:
            price = mascot_mod.PAID_ACCESSORIES.get(a)
            locked = bool(price) and f"accessory:{a}" not in owned
            locked_any = locked_any or locked
            head = str(mascot_mod.buddy_head({"acc": a}, 46))
            accs.append({"key": a, "name": say(ACC_NAMES[a]), "price": price, "locked": locked,
                         "head": Markup('<i data-tbase="{}">{}</i>').format(head, Markup(mascot_mod._recolor(head, av)))})
        return {"svg": Markup('<div data-tbase="{}">{}</div>').format(base, Markup(mascot_mod._recolor(base, av))),
                "shells": mascot_mod.SHELLS, "scarves": mascot_mod.SCARVES, "skins": mascot_mod.SKINS, "accs": accs,
                "locked_note": say("The crown and the wizard hat are in the shop on Tempo's island. Learning earns the shells.") if locked_any else "",
                "colors": {"base": [mascot_mod.SHELL, mascot_mod.SHELL_DARK, mascot_mod.SHELL_SHADE, mascot_mod.SHELL_LIGHT,
                                    mascot_mod.SCARF, mascot_mod.SCARF_DARK, mascot_mod.SKIN, mascot_mod.SKIN_DARK, mascot_mod.SKIN_FAR],
                           "shells": mascot_mod.SHELLS, "scarves": mascot_mod.SCARVES, "skins": mascot_mod.SKINS}}

    def _share_svg(av: dict, name: str) -> str:
        """A square picture of your turtle and your name, to share anywhere."""
        shell = mascot_mod.SHELLS[av["shell"]]
        turtle = str(mascot_mod.buddy(av, "wave", 860, name))
        safe = str(Markup.escape(name))[:60]
        line = str(Markup.escape(say("Slow and steady. Learning with inPace.")))
        return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1080" width="1080" height="1080">'
                '<rect width="1080" height="1080" fill="#F7F3EA"/>'
                f'<circle cx="540" cy="450" r="390" fill="{shell[3]}" stroke="#111" stroke-width="8"/>'
                f'<g transform="translate(110 150)">{turtle}</g>'
                f'<text x="540" y="955" text-anchor="middle" font-family="system-ui, -apple-system, Segoe UI, sans-serif" '
                f'font-size="84" font-weight="800" fill="#111">{safe}</text>'
                f'<text x="540" y="1028" text-anchor="middle" font-family="system-ui, -apple-system, Segoe UI, sans-serif" '
                f'font-size="38" fill="#5E5A52">{line}</text></svg>')

    async def setup(request: Request):
        start = mascot_mod.clean_avatar({})
        if V.is_set_up:
            return go("/")
        pick = request.query_params.get("lang")
        if langs.known(pick):  # the language buttons at the top of the welcome page
            V._set_meta("lang", pick)
            return go("/setup")
        if request.method == "POST":
            form = await request.form()
            if langs.known(str(form.get("lang", ""))):
                V._set_meta("lang", str(form.get("lang")))
            name = str(form.get("name", "")).strip()
            av = _turtle_from(form)
            if not name:
                return page("setup.html", request, maker=_maker(av), av=av, error="Please type your name.")
            if not V._meta("lang", ""):
                V._set_meta("lang", device_lang(request.headers.get("accept-language")))
            V.setup(name, COLORS[COLOR_FOR_SHELL[av["shell"]]])
            V.set_avatar(av, COLORS[COLOR_FOR_SHELL[av["shell"]]])
            return go("/", ok=f"Welcome, {name}! Pick a course to start.")
        return page("setup.html", request, maker=_maker(start), av=start)

    async def settings_turtle(request: Request):
        form = await request.form()
        av = _turtle_from(form)
        V.set_avatar(av, COLORS[COLOR_FOR_SHELL[av["shell"]]])
        return go("/settings#turtle", ok="Your turtle is saved. People see it the next time you send them your contact card.")

    async def my_turtle_svg(request: Request):
        av = mascot_mod.clean_avatar(V.me.get("avatar") or {})
        return download(_share_svg(av, V.me["name"]).encode(), f"{V.me['name']} - my turtle.svg", "image/svg+xml")

    async def my_turtle_png(request: Request):
        """The page draws the picture as a PNG (phones and chat apps don't take SVG) and sends it here to save."""
        form = await request.form()
        raw = _png_from_form(form)
        if raw is None:
            return go("/settings#turtle", err="The picture couldn't be made. Try the SVG instead.")
        return download(raw, f"{V.me['name']} - my turtle.png", "image/png")

    def _png_from_form(form) -> bytes | None:
        """The PNG the page drew on a canvas (phones and chat apps don't take SVG), or None if it isn't one."""
        data = str(form.get("png", ""))
        head = "data:image/png;base64,"
        if not data.startswith(head) or len(data) > 12_000_000:
            return None
        import base64 as _b64
        try:
            raw = _b64.b64decode(data[len(head):], validate=True)
        except ValueError:
            return None
        return raw if raw.startswith(b"\x89PNG") else None

    async def home(request: Request):
        if not V.is_set_up:
            return go("/setup")
        pending = V._meta("pending_link", "") or ""
        if pending:
            return go("/link?d=" + pending)
        cards = [journey_card(j) for j in V.journeys()]
        # The course you worked on last comes first: its "Continue" is the first thing on the page.
        last = {r[0]: r[1] or "" for r in V.db.execute("SELECT journey, MAX(at) FROM events GROUP BY journey")}
        cards.sort(key=lambda card: last.get(card["journey"]["id"], ""), reverse=True)
        show_tour = request.query_params.get("tour") == "1" or not V._meta("tour_done", "")
        rm_index = library.cached_index(V.home)
        road, rm_of = [], {}
        for rm in roadmaps.mine(V.home):
            for i, step in enumerate(rm["steps"], 1):
                rm_of.setdefault(step["course"], (rm, i))
            rst = roadmaps.status(V, rm, rm_index)
            if not rst["finished"]:
                road.append({"rm": rm, "st": rst})
        resp = page("home.html", request, cards=cards, checkers=V.my_checkers(), courses=V.courses(), road=road[:2], rm_of=rm_of,
                    tour=_tour_steps() if show_tour else None, welcome_back=_welcome_back(),
                    reminders_set=bool(reminders.load(V)["items"]),
                    island_trip=garden.active(V) if garden.is_on(V) else None,
                    island=_island_home() if garden.is_on(V) else None,
                    island_rewards={r["journey"]: r for r in garden.course_rewards(V)} if garden.is_on(V) else {})
        return resp

    def _island_home() -> dict | None:
        """Tempo's island on Home: a small picture, the weather and the villain, shells, the story so far,
        and what you unlock next. Reading only: chapters open on the island page itself."""
        try:
            lang = V._meta("lang", "en") or "en"
            rot = garden.decay(V)
            st = garden.stats(V)
            wx = garden.weather(V, goal_met=_goal_met())
            world = garden.story.world_for(V._meta("island_world", "") or "", lang)
            shown = garden.island(V, lang)
            have = garden.unlocked(V, st)
            labels = _island_labels()
            labels["villain"] = garden.story.villain_name(world, lang)
            picture = garden.island_svg(shown["plants"], have["friends"], 1 + shown["living"] // 10, st["blooming"],
                                        labels=labels, palette=shown["palette"], fog=wx["fog"], fair=wx["fair"],
                                        look=garden.looks(V, ""), title=shown["title"], villain=wx["threat"],
                                        season_now=garden.season(datetime.now().month),
                                        visitor=garden.visitor_today(V), fled=wx["fled"], trophies=st["courses"])
            opened = json.loads(V._meta("island_story", "[]") or "[]")
            chapters = [k for k, *_ in garden.story.CHAPTERS]
            done = len([k for k in opened if k in chapters])
            waiting = wx["fog"] < 2 and any(k not in opened and garden.story.opens(k, st) for k in chapters)
            coll = garden.collection(V, st)
            locked = [f for f in coll["friends"] + coll["plants"] if not f["have"] and f["goal"]]
            nxt = max(locked, key=lambda f: f["progress"] / f["goal"][1], default=None)
            return {"picture": Markup(picture), "title": shown["title"], "wx": wx, "rot": rot, "st": st,
                    "living": shown["living"], "friends": len(have["friends"]),
                    "shells": garden.wallet(V, st)["balance"], "chapter": done, "chapters": len(chapters),
                    "waiting": waiting, "next": nxt,
                    "taunt": garden.story.taunt(wx["threat"], world, lang, wx["wilt_in"] or 0)}
        except Exception:
            return None

    def _welcome_back() -> int | None:
        """Back after a while: Tempo says so once, on Home."""
        away = reminders.touch(V)
        if away:
            return away
        days = V._meta("welcome_back", "") or ""
        if days:
            V._set_meta("welcome_back", "")
        return int(days) if days.isdigit() else None

    def _tour_steps() -> list:
        """Tempo's welcome tour. Each step points at something on the screen (or nothing, for the middle of the screen)."""
        steps = [
            (None, "wave", "Hi, I'm Tempo!", "I'll show you around inPace. It takes about a minute. Slow and steady, like me."),
            ('.side a[href="/courses"], .tabbar a[href="/courses"]', "happy", "Your courses", "Everything you're learning lives here. Add a course from a file, a folder of videos you already have, a list of YouTube links, or try a sample course."),
            ('.side a[href="/add"], .tabbar a[href="/add"]', "think", "Add a course", "Add a folder of class material (inPace sorts it for you), a course file, a course from the library, or make one with simple forms or AI."),
            ('.side a[href="/milestones"], .tabbar a[href="/milestones"]', "proud", "Milestones", "When you finish part of a course, save a milestone. It's a signed snapshot of your progress that nobody can quietly change."),
            ('.side a[href="/people"], .more-sheet a[href="/people"]', "cheer", "Your checker", "Learning sticks when someone has your back. Add a friend, a parent or a mentor. Send them your milestone and they approve it. Swap friend codes on Telegram or WhatsApp."),
            ('.side a[href="/races"], .more-sheet a[href="/races"]', "cheer", "Races", "Race your friends to keep each other going. Only approved milestones count, so it stays fair."),
            ('.side-bottom a, .more-sheet a[href="/open"]', "think", "Open a file", "Anything someone sends you, like a course, a friend code or your checker's reply, opens here."),
            ('.top .theme-toggle, .more-sheet [data-theme-toggle]', "sleepy", "Light or dark", "Studying late? Switch to dark mode here."),
            ('.side a[href="/settings"], .more-sheet a[href="/settings"]', "happy", "Settings", "Language, backups and updates live here. You can also watch this tour again from here any time."),
            ('.side a[href="/island"], .more-sheet a[href="/island"]', "water", "Tempo's island", "Want a reward for studying? Turn on Tempo's island: every focus trip grows a plant on my shell, and friends move in as you learn."),
            (None, "proud", "You're all set!", "Start with a course and take the first step today. I'll be on your Home page, cheering you on."),
        ]
        return [{"target": tgt, "mood": mood, "title": say(title), "text": say(text)} for tgt, mood, title, text in steps]

    async def tour_done(request: Request):
        V._set_meta("tour_done", now_utc())
        return Response(status_code=204)

    async def tour_again(request: Request):
        V._set_meta("tour_done", "")
        return go("/?tour=1")

    # ---- courses ---------------------------------------------------------------
    # ---- the course builder: a whole course on one page ----------------------------------------------
    async def build_page(request: Request):
        import secrets
        cid = request.path_params.get("cid", "")
        data = None
        if cid:
            c = V.get_course(cid)
            if not c:
                return go("/courses", err="That course isn't installed.")
            data = builder.to_page(c)
        fdata = folders.load(V)
        return page("builder.html", request, data_json=json.dumps(data, ensure_ascii=False).replace("<", "\\u003c"),
                    draft="" if cid else secrets.token_hex(8), cid=cid, folder_list=fdata["folders"],
                    folder_now=fdata["of"].get(cid, "") if cid else "", lang=V._meta("lang", "en") or "en")

    def _build_draft_dir(token: str) -> Path | None:
        return _drafts() / f"build-{token}" if re.fullmatch(r"[0-9a-f]{16}", token or "") else None

    async def build_save(request: Request):
        try:
            data = await request.json()
        except ValueError:
            return JSONResponse({"ok": False, "problems": [say("Something went wrong. Try again.")]}, status_code=400)
        if not isinstance(data, dict):
            return JSONResponse({"ok": False, "problems": [say("Something went wrong. Try again.")]}, status_code=400)
        try:
            c = builder.save(V, data, _build_draft_dir(str(data.get("draft", ""))))
        except CourseError as e:
            return JSONResponse({"ok": False, "problems": [say(p) for p in e.problems]})
        fid = str(data.get("folder", ""))
        if str(data.get("new_folder", "")).strip():
            fid = folders.create(V, str(data["new_folder"]))
        if "folder" in data or fid:
            folders.move(V, c.id, fid)
        return JSONResponse({"ok": True, "cid": c.id, "data": builder.to_page(c), "folder": fid})

    async def build_upload(request: Request):
        """Files picked in the builder: copied into the course (or a draft folder until the course is saved)."""
        form = await request.form()
        cid = str(form.get("cid", ""))
        if cid:
            if not V.get_course(cid):
                return JSONResponse({"ok": False}, status_code=404)
            folder = V.media_dir(cid) / builder.UPLOAD_DIR
        else:
            folder = _build_draft_dir(str(form.get("draft", "")))
            if not folder:
                return JSONResponse({"ok": False}, status_code=400)
        out = []
        from .course import _nice_title
        for up in form.getlist("files"):
            if not getattr(up, "filename", ""):
                continue
            name = builder.safe_name(up.filename)
            if not _media_kind(name) or _media_kind(name) in ("link", "folder"):
                out.append({"ok": False, "name": name, "problem": say("inPace can't show this kind of file: %s", [name])})
                continue
            dst = builder.unique_path(folder, name)
            with open(dst, "wb") as f:
                while chunk := await up.read(4 * 1024 * 1024):
                    f.write(chunk)
            out.append({"ok": True, "media": f"{builder.UPLOAD_DIR}/{dst.name}", "title": _nice_title(dst.name),
                        "kind": _media_kind(dst.name)})
        return JSONResponse({"ok": True, "files": out})

    async def build_links(request: Request):
        """Links typed or pasted in the builder, read the same way as on the "course from links" page."""
        try:
            data = await request.json()
        except ValueError:
            data = {}
        from starlette.concurrency import run_in_threadpool
        try:
            groups = await run_in_threadpool(editor.parse_link_lines, str(data.get("text", "")), bool(data.get("fetch")))
        except CourseError as e:
            return JSONResponse({"ok": False, "problems": [say(p) for p in e.problems]})
        lessons = [{"title": les["title"], "media": les["media"], "minutes": int(les.get("minutes") or 0),
                    "kind": _media_kind(les["media"])} for _, ls in groups for les in ls]
        return JSONResponse({"ok": True, "lessons": lessons})

    async def courses(request: Request):
        installed = V.courses()
        have = {c.id for c in installed}
        samples = [c for c in _sample_courses() if c.id not in have]
        lang = V._meta("lang", "en") or "en"
        samples.sort(key=lambda c: c.language != lang)  # courses in your language first
        rows = []
        for c in installed:
            jid = V.journey_for_course(c.id)
            words = [c.title, c.description] + [m["title"] for m in c.modules] + \
                    [les["title"] for m in c.modules for les in m["lessons"]]
            prog = V.progress(jid) if jid else None
            rows.append({"course": c, "journey": jid,
                         "percent": prog["percent"] if prog else None,
                         "next": prog["next"] if prog else None,
                         "finished": bool(prog and prog["finished"]),
                         "search": " ".join(w for w in words if w).lower(),
                         "has_files": any(media_mod.media_refs(les) for m in c.modules for les in m["lessons"]),
                         "media_root": V.media_root(c.id)})
        # Courses you're in the middle of first, then ones not started, then finished ones.
        rows.sort(key=lambda r: 2 if r["finished"] else (0 if r["journey"] else 1))
        fdata = folders.load(V)
        return page("courses.html", request, rows=rows, samples=samples, groups=folders.group(V, rows),
                    folder_list=fdata["folders"], folder_of=fdata["of"])

    # ---- folders on My courses ------------------------------------------------
    async def folder_new(request: Request):
        f = await request.form()
        fid = folders.create(V, str(f.get("name", "")))
        if not fid:
            return go("/courses", err="Give the folder a name.")
        cid = str(f.get("course", ""))
        if cid and V.get_course(cid):
            folders.move(V, cid, fid)
        return go(f"/courses#folder-{fid}", ok="Folder ready.")

    async def folder_rename(request: Request):
        f = await request.form()
        fid = request.path_params["fid"]
        if not folders.rename(V, fid, str(f.get("name", ""))):
            return go("/courses", err="Give the folder a name.")
        return go(f"/courses#folder-{fid}", ok="Folder renamed.")

    async def folder_delete(request: Request):
        folders.delete(V, request.path_params["fid"])
        return go("/courses", ok="Folder deleted. Its courses are still here, under Not in a folder.")

    async def course_folder(request: Request):
        cid = request.path_params["cid"]
        if not V.get_course(cid):
            return go("/courses", err="That course isn't installed.")
        f = await request.form()
        fid = str(f.get("folder", ""))
        if str(f.get("new_name", "")).strip():
            fid = folders.create(V, str(f.get("new_name", "")))
        folders.move(V, cid, fid)
        return go(f"/courses#folder-{fid}" if fid else "/courses", ok="Moved.")

    async def add_links(request: Request):
        """A course from links: YouTube videos (a long one can be cut at its chapters), Udemy or any website."""
        lang = V._meta("lang", "en") or "en"
        flist = folders.load(V)["folders"]
        if request.method == "POST":
            f = await request.form()
            form = {k: str(v) for k, v in f.items()}
            try:
                if not form.get("links", "").strip():
                    raise CourseError(["Paste at least one link."])
                from starlette.concurrency import run_in_threadpool
                c = await run_in_threadpool(
                    editor.new_course, V, form.get("title", ""), form.get("description", ""), "", "", "",
                    form["links"], form.get("language", "en"), bool(form.get("fetch_titles")))
            except CourseError as e:
                return page("add_links.html", request, problems=e.problems, form=form, folder_list=flist, lang=lang)
            fid = form.get("folder", "")
            if form.get("new_folder", "").strip():
                fid = folders.create(V, form["new_folder"])
            if fid:
                folders.move(V, c.id, fid)
            return go(f"/courses#folder-{fid}" if fid else "/courses",
                      ok="Course added. Press it to start, or open More, then Edit to add tasks and questions.")
        return page("add_links.html", request, form={"fetch_titles": "1"}, folder_list=flist, lang=lang,
                    problems=None)

    # ---- the course library ---------------------------------------------------
    async def library_page(request: Request):
        """Courses other people shared in the inPace library. Only goes online when you open this page."""
        from starlette.concurrency import run_in_threadpool
        try:
            index = await run_in_threadpool(library.load_index, V.home, request.query_params.get("refresh") == "1")
        except library.LibraryProblem as e:
            return page("library.html", request, problem=str(e), entries=[], index={}, tab="courses", lib_roadmaps=[],
                        followed=set(), titles={})
        _note_library(index)
        new_ids = _library_new()
        entries = []
        for e in index.get("courses", []):
            local = V.get_course(str(e.get("id", "")))
            state = "add" if not local else ("have" if local.hash == e.get("hash") else "update")
            # The search looks at the title, tags, section, description, author, and every module and lesson title.
            outline = e.get("outline") if isinstance(e.get("outline"), list) else []
            lessons = " ".join(str(m.get("title", "")) + " " + " ".join(str(l.get("title", "")) for l in (m.get("lessons") or []))
                               for m in outline if isinstance(m, dict))
            words = " ".join(str(x) for x in [e.get("id"), e.get("title"), " ".join(e.get("tags") or []), e.get("section"),
                                                e.get("description"), e.get("author", {}).get("name"), lessons] if x).lower()
            tags = [str(x).lower() for x in (e.get("tags") or [])]
            level = next((t for t in ("beginner", "intermediate", "advanced") if t in tags), "")
            entries.append({**e, "state": state, "search": words, "level": level,
                            "search_title": (str(e.get("title", "")) + " " + " ".join(tags)).lower(),
                            "new": str(e.get("id", "")) in new_ids,
                            "hours": round(int(e.get("minutes") or 0) / 60) if e.get("minutes") else 0})
        lang = V._meta("lang", "en") or "en"
        groups, topics = _library_groups(index, entries, lang)
        tab = "roadmaps" if request.query_params.get("tab") == "roadmaps" else "courses"
        followed = {r["id"] for r in roadmaps.mine(V.home)}
        lib_roadmaps = roadmaps.library_list(index)
        lib_roadmaps.sort(key=lambda r: (r["id"] in followed, r.get("language") != lang))
        titles = {str(e.get("id")): e.get("title", "") for e in entries}
        entries.sort(key=lambda e: not e["new"])  # new courses first
        extra_groups = {"groups": groups}
        checked = (V.home / "library.json").stat().st_mtime if (V.home / "library.json").exists() else 0
        extra = {**extra_groups, "tab": tab, "lib_roadmaps": lib_roadmaps, "followed": followed, "titles": titles,
                 "new_count": sum(1 for e in entries if e["new"]),
                 "checked_min": int((_time.time() - checked) // 60) if checked else None}
        if new_ids and tab == "courses":
            V._set_meta("library_new", "[]")  # seen: the badge goes away, the "New" tags show this one time
        show = str(request.query_params.get("show", ""))
        if show and not any(e.get("id") == show for e in entries):
            # A friend's link to a course we don't have in our list yet: look again.
            if request.query_params.get("refresh") != "1":
                return go("/library?refresh=1&show=" + quote(show))
            return page("library.html", request, entries=entries, index=index, problem=None, report_url=library.REPORT_URL,
                        site=library.SITE, show="", missing=True, topics=topics, **extra)
        return page("library.html", request, entries=entries, index=index, problem=None,
                    report_url=library.REPORT_URL, site=library.SITE, show=show, topics=topics, **extra)

    async def library_course(request: Request):
        """One library course up close, before adding it: what's inside, its tasks, and a lesson to read."""
        from starlette.concurrency import run_in_threadpool
        cid = request.path_params["cid"]
        try:
            index = await run_in_threadpool(library.load_index, V.home)
        except library.LibraryProblem as e:
            return go("/library", err=str(e))
        e = library.find(index, cid)
        if not e:
            return go("/library", err="That course isn't in the library anymore.")
        local = V.get_course(cid)
        state = "add" if not local else ("have" if local.hash == e.get("hash") else "update")
        outline = e.get("outline") if isinstance(e.get("outline"), list) else []
        sample = e.get("sample") if isinstance(e.get("sample"), dict) else None
        sample_html = ""
        if sample and isinstance(sample.get("text"), str):
            sample_html = md.render(_drop_title(sample["text"][:12000], str(sample.get("title", ""))))
        minutes = int(e.get("minutes") or 0)
        on_rm = [r for r in roadmaps.library_list(index) if any(st["course"] == cid for st in r["steps"])]
        return page("library_course.html", request, e=e, state=state, outline=outline, sample=sample, on_rm=on_rm,
                    sample_html=sample_html, hours=round(minutes / 60) if minutes else 0, report_url=library.REPORT_URL,
                    dispose=None)

    async def library_add(request: Request):
        from starlette.concurrency import run_in_threadpool
        cid = request.path_params["cid"]
        try:
            index = await run_in_threadpool(library.load_index, V.home)
            entry = library.find(index, cid)
            if not entry:
                return go("/library", err="That course isn't in the library anymore.")
            token = _progress_token(await request.form())
            data = await run_in_threadpool(progress.within, token, {"title": entry.get("title", ""),
                                           "size": int(entry.get("size") or 0)}, library.download, entry)
        except library.LibraryProblem as e:
            return go("/library", err=str(e))
        import io as _io
        progress.report(token, state="installing")
        try:
            return _install_pack(request, _io.BytesIO(data), f"{cid}.zip")
        finally:
            progress.report(token, state="done")

    # ---- roadmaps (v1.24): a path through several courses ----------------------------------------------------
    async def _library_now(online: bool = True) -> dict:
        """The library's list: fresh when it's more than an hour old and we're online, else the last copy."""
        from starlette.concurrency import run_in_threadpool
        if not online:
            return library.cached_index(V.home)
        try:
            return await run_in_threadpool(library.load_index, V.home)
        except library.LibraryProblem:
            return library.cached_index(V.home)

    def _roadmap_where(rid: str, index: dict) -> tuple[dict | None, str]:
        """Your copy of a roadmap if you have one, else the library's. ("", None) if neither."""
        rm = roadmaps.get(V.home, rid)
        if rm:
            return rm, "mine"
        rm = roadmaps.library_find(index, rid)
        return (rm, "library") if rm else (None, "")

    def _picker_courses(index: dict) -> list[dict]:
        """Every course you can put on a roadmap: yours and the library's (each once)."""
        out, seen = [], set()
        for c in V.courses():
            e = library.find(index, c.id)
            out.append({"id": c.id, "title": c.title, "description": c.description, "language": c.language,
                        "tags": (e or {}).get("tags") or [], "where": "mine",
                        "minutes": sum(int(les.get("minutes") or 0) for m in c.modules for les in m["lessons"]),
                        "lessons": c.lesson_count, "library": bool(e)})
            seen.add(c.id)
        for e in index.get("courses") or []:
            if isinstance(e, dict) and e.get("id") and e["id"] not in seen:
                out.append({"id": e["id"], "title": e.get("title", ""), "description": e.get("description", ""),
                            "language": e.get("language", "en"), "tags": e.get("tags") or [], "where": "library",
                            "minutes": int(e.get("minutes") or 0), "lessons": int(e.get("lessons") or 0), "library": True})
                seen.add(e["id"])
        return out

    def _roadmap_card(rm: dict, index: dict) -> dict:
        return {"rm": rm, "st": roadmaps.status(V, rm, index)}

    async def roadmaps_page(request: Request):
        index = await _library_now(online=False)
        cards = [_roadmap_card(rm, index) for rm in roadmaps.mine(V.home)]
        cards.sort(key=lambda c: (c["st"]["finished"], 0))  # the ones you're on first
        followed = {c["rm"]["id"] for c in cards}
        lang = V._meta("lang", "en") or "en"
        lib = [r for r in roadmaps.library_list(index) if r["id"] not in followed]
        lib.sort(key=lambda r: r.get("language") != lang)
        titles = {str(e.get("id")): e.get("title", "") for e in index.get("courses") or [] if isinstance(e, dict)}
        return page("roadmaps.html", request, cards=cards, lib=lib[:6], lib_count=len(roadmaps.library_list(index)),
                    titles=titles, has_index=bool(index.get("courses")), index=index)

    async def roadmap_page(request: Request):
        rid = request.path_params["rid"]
        index = await _library_now()
        if request.query_params.get("fresh") == "1":  # "Check the library again": don't wait for the hour to pass
            from starlette.concurrency import run_in_threadpool
            try:
                index = await run_in_threadpool(library.load_index, V.home, True)
            except library.LibraryProblem:
                pass
        rm, where = _roadmap_where(rid, index)
        if not rm:
            if request.query_params.get("refresh") != "1" and not index.get("offline"):
                from starlette.concurrency import run_in_threadpool
                try:
                    await run_in_threadpool(library.load_index, V.home, True)
                    return go(f"/roadmaps/{quote(rid)}?refresh=1")
                except library.LibraryProblem:
                    pass
            return go("/roadmaps", err="That roadmap isn't on this device or in the library.")
        return _show_roadmap(request, rm, where, index)

    def _show_roadmap(request: Request, rm: dict, where: str, index: dict, shared_json: str = ""):
        st = roadmaps.status(V, rm, index)
        lib_copy = roadmaps.library_find(index, rm["id"])
        newer = bool(where == "mine" and rm.get("source") == "library" and lib_copy
                     and lib_copy["hash"] != rm.get("library_hash") and roadmaps.fingerprint(lib_copy) != roadmaps.fingerprint(rm))
        chart = garden.voyage_chart(st, labels=_voyage_labels(), compact=True)
        return page("roadmap.html", request, rm=rm, st=st, where=where, lib_copy=lib_copy, newer=newer,
                    chart=chart, shared_json=shared_json, island_on=garden.is_on(V), index=index,
                    in_library=bool(lib_copy and roadmaps.fingerprint(lib_copy) == roadmaps.fingerprint(rm)))

    async def roadmap_follow(request: Request):
        """Follow a library roadmap: keep a copy here so its progress shows on Home and on the island."""
        rid = request.path_params["rid"]
        index = await _library_now()
        lib_copy = roadmaps.library_find(index, rid)
        if not lib_copy:
            return go("/roadmaps", err="That roadmap isn't in the library anymore.")
        mine = roadmaps.get(V.home, rid)
        if mine and mine.get("source") == "mine":
            return go(f"/roadmaps/{rid}", err="You already have a roadmap with this name.")
        _follow_library(lib_copy, mine, index)
        return go(f"/roadmaps/{rid}", ok="Updated to the library's version." if mine else "You're following this roadmap. Add its first course to start.")

    def _follow_library(lib_copy: dict, mine: dict | None, index: dict) -> dict:
        """Keep a copy of a library roadmap here (following it)."""
        copy = {**lib_copy, "source": "library", "library_hash": lib_copy["hash"],
                "followed_at": (mine or {}).get("followed_at") or now_utc()}
        for s in copy["steps"]:  # remember course names, for before the courses are added
            e = library.find(index, s["course"])
            if e and not s.get("title"):
                s["title"] = e.get("title", "")
        roadmaps.save(V.home, copy)
        return copy

    async def roadmap_follow_shared(request: Request):
        """Follow a roadmap someone sent you as a link (the whole roadmap is inside the link)."""
        form = await request.form()
        try:
            data = json.loads(str(form.get("data", "")))
            rm = roadmaps.parse(data, "link")
        except (ValueError, roadmaps.RoadmapError):
            return go("/roadmaps", err="That roadmap link is damaged. Ask for it again.")
        existing = roadmaps.get(V.home, rm["id"])
        if existing and roadmaps.fingerprint(existing) != roadmaps.fingerprint(rm):
            rm["id"] = roadmaps.free_id(V.home, rm["id"])
        rm["followed_at"] = now_utc()
        roadmaps.save(V.home, rm)
        return go(f"/roadmaps/{rm['id']}", ok="You're following this roadmap.")

    async def roadmap_remove(request: Request):
        rid = request.path_params["rid"]
        rm = roadmaps.get(V.home, rid)
        roadmaps.delete(V.home, rid)
        msg = ("Deleted the roadmap. Its courses and your progress in them stay." if rm and rm.get("source") == "mine"
               else "You stopped following the roadmap. Its courses and your progress in them stay.")
        return go("/roadmaps", ok=msg)

    def _roadmap_has(rid: str, cid: str, index: dict) -> bool:
        rm = roadmaps.get(V.home, rid) or roadmaps.library_find(index, rid)
        return bool(rm and any(s["course"] == cid for s in rm["steps"]))

    async def roadmap_add_course(request: Request):
        """Add one course of a roadmap from the library, then come back to the roadmap."""
        from starlette.concurrency import run_in_threadpool
        rid, cid = request.path_params["rid"], request.path_params["cid"]
        if not _roadmap_has(rid, cid, library.cached_index(V.home)):
            return go(f"/roadmaps/{quote(rid)}", err="That course isn't on this roadmap.")
        try:
            index = await run_in_threadpool(library.load_index, V.home)
            entry = library.find(index, cid)
            if not entry:
                return go(f"/roadmaps/{rid}", err="That course isn't in the library anymore.")
            token = _progress_token(await request.form())
            data = await run_in_threadpool(progress.within, token, {"title": entry.get("title", ""),
                                           "size": int(entry.get("size") or 0)}, library.download, entry)
        except library.LibraryProblem as e:
            return go(f"/roadmaps/{rid}", err=str(e))
        import io as _io
        progress.report(token, state="installing")
        try:
            return _install_pack(request, _io.BytesIO(data), f"{cid}.zip", then=f"/roadmaps/{rid}")
        finally:
            progress.report(token, state="done")

    async def roadmap_add_all(request: Request):
        """Add every course of a roadmap that's in the library and not on this device yet, one after another. For
        people who want the whole path ready, say before they go offline. Courses you already have stay as they are."""
        import io as _io
        import zipfile
        from starlette.concurrency import run_in_threadpool
        rid = request.path_params["rid"]
        rm = roadmaps.get(V.home, rid)
        try:
            index = await run_in_threadpool(library.load_index, V.home)
        except library.LibraryProblem as e:
            return go(f"/roadmaps/{quote(rid)}", err=str(e))
        if not rm:  # a library roadmap you don't follow yet: one click follows it and downloads everything (v1.30.14)
            lib_copy = roadmaps.library_find(index, rid)
            if not lib_copy:
                return go("/roadmaps", err="That roadmap isn't in the library anymore.")
            rm = _follow_library(lib_copy, None, index)
        added, failed = [], []
        token = _progress_token(await request.form())
        todo = [s for s in roadmaps.status(V, rm, index)["to_add"] if not V.get_course(s["course"])]
        for n, s in enumerate(todo, 1):
            try:
                info = {"title": s["entry"].get("title", ""), "size": int(s["entry"].get("size") or 0), "n": n, "of": len(todo)}
                data = await run_in_threadpool(progress.within, token, info, library.download, s["entry"])
                progress.report(token, state="installing")
                zf = zipfile.ZipFile(_io.BytesIO(data))
                c = V.install_course(load_course(files_from_zip(_io.BytesIO(data))))
                _unpack_media(c, zf, media_in_zip(zf))
                added.append(c.title)
            except library.LibraryProblem as e:
                failed.append(str(e))
                if "internet" in str(e):
                    break  # offline: the next ones would fail the same way
            except (zipfile.BadZipFile, CourseError):
                failed.append(f"The library's file for “{s['title']}” couldn't be read.")
        progress.report(token, state="done")
        msg = {}
        if added:
            msg["ok"] = f"Added {len(added)} courses. Start each one when you get to it." if len(added) > 1 \
                else f"Added the course “{added[0]}”."
        if failed:
            msg["err"] = "Some courses weren't added:\n" + "\n".join(failed)
        return go(f"/roadmaps/{quote(rid)}", **(msg or {"ok": "All its courses are already on this device."}))

    async def roadmap_drop_missing(request: Request):
        """Take the courses you can't get (not on this device, not in the library) off a roadmap someone sent you,
        so you can still finish it. It becomes your own version. Only with a fresh library list: a course that only
        looked missing because you were offline is never taken off."""
        from starlette.concurrency import run_in_threadpool
        rid = request.path_params["rid"]
        rm = roadmaps.get(V.home, rid)
        if not rm:
            return go("/roadmaps", err="That roadmap isn't on this device.")
        if rm.get("source") == "library":
            return go(f"/roadmaps/{quote(rid)}?fresh=1", err="Library roadmaps only use library courses. Check for a newer version.")
        try:
            index = await run_in_threadpool(library.load_index, V.home, True)
        except library.LibraryProblem:
            return go(f"/roadmaps/{quote(rid)}", err="Connect to the internet first, so inPace can check the library.")
        gone = {s["course"] for s in roadmaps.status(V, rm, index)["missing"]}
        if not gone:
            return go(f"/roadmaps/{quote(rid)}", ok="Every course on this roadmap can be added now.")
        try:
            mine_now = roadmaps.without(rm, gone)
        except roadmaps.RoadmapError:
            return go(f"/roadmaps/{quote(rid)}", err="None of its required courses can be added, so nothing would be left. "
                                                      "Ask for the course files, or stop following it.")
        mine_now["made_at"] = rm.get("made_at") or now_utc()
        roadmaps.save(V.home, mine_now)
        return go(f"/roadmaps/{quote(rid)}", ok=f"Took {len(gone)} courses off. This is now your own version of the roadmap.")

    async def roadmap_start(request: Request):
        rid, cid = request.path_params["rid"], request.path_params["cid"]
        if not V.get_course(cid):
            return go(f"/roadmaps/{rid}", err="Add the course first.")
        return go(f"/learn/{V.start_journey(cid)}")

    def _roadmap_form_steps(form, index: dict) -> list[dict]:
        steps = []
        raw = str(form.get("steps", "") or "").strip()
        if raw:
            try:
                data = json.loads(raw)
                steps = [s for s in data if isinstance(s, dict)] if isinstance(data, list) else []
            except ValueError:
                steps = []
        else:  # without JavaScript: the ticked courses, in the order of the list
            steps = [{"course": str(x)} for x in form.getlist("pick")]
        titles = {c["id"]: c["title"] for c in _picker_courses(index)}
        for s in steps:
            s["title"] = titles.get(str(s.get("course", "")), s.get("title", ""))
        return steps

    async def roadmap_new(request: Request):
        return await _roadmap_maker(request, None)

    async def roadmap_edit(request: Request):
        rm = roadmaps.get(V.home, request.path_params["rid"])
        if not rm:
            return go("/roadmaps", err="That roadmap isn't on this device.")
        if rm.get("source") != "mine":
            return go(f"/roadmaps/new?copy={quote(rm['id'])}")
        return await _roadmap_maker(request, rm)

    async def _roadmap_maker(request: Request, rm: dict | None):
        index = await _library_now()
        courses = _picker_courses(index)
        lang = V._meta("lang", "en") or "en"
        if request.method == "POST":
            form = await request.form()
            draft = {"id": (rm or {}).get("id") or "", "title": form.get("title", ""), "description": form.get("description", ""),
                     "language": form.get("language", lang), "tags": str(form.get("tags", "")),
                     "author": V.me["name"] if V.me else "", "steps": _roadmap_form_steps(form, index)}
            try:
                if not draft["id"]:
                    draft["id"] = roadmaps.free_id(V.home, roadmaps.slug(str(draft["title"])))
                clean = roadmaps.parse(draft, "mine")
            except roadmaps.RoadmapError as e:
                return page("roadmap_edit.html", request, rm=rm, draft=draft, courses=courses, problems=e.problems,
                            goal="", suggested=False, lang=lang)
            clean["made_at"] = (rm or {}).get("made_at") or now_utc()
            roadmaps.save(V.home, clean)
            return go(f"/roadmaps/{clean['id']}", ok="Saved the roadmap." if rm else "Made your roadmap. Share it, or publish it to the library.")
        goal = str(request.query_params.get("goal", "")).strip()[:120]
        draft = dict(rm) if rm else {"title": "", "description": "", "language": lang, "tags": [], "steps": []}
        copy = roadmaps.get(V.home, str(request.query_params.get("copy", ""))) or (
            roadmaps.library_find(index, str(request.query_params.get("copy", ""))) if request.query_params.get("copy") else None)
        if copy and not rm:
            draft = {**copy, "id": "", "title": say("My version of “%s”", [copy["title"]])[:120], "source": "mine"}
        suggested = False
        if goal and not rm:
            ids = roadmaps.suggest(goal, courses, lang)
            titles = {c["id"]: c["title"] for c in courses}
            draft["steps"] = [{"course": i, "title": titles.get(i, i), "note": ""} for i in ids]
            if not draft.get("title"):
                draft["title"] = goal[:1].upper() + goal[1:]
            suggested = True
        return page("roadmap_edit.html", request, rm=rm, draft=draft, courses=courses, problems=None, goal=goal,
                    suggested=suggested, lang=lang)

    async def roadmap_share(request: Request):
        """Send a roadmap, or publish it to the library."""
        rid = request.path_params["rid"]
        index = await _library_now()
        rm, where = _roadmap_where(rid, index)
        if not rm:
            return go("/roadmaps", err="That roadmap isn't on this device or in the library.")
        lib_copy = roadmaps.library_find(index, rid)
        in_library = bool(lib_copy and roadmaps.fingerprint(lib_copy) == roadmaps.fingerprint(rm))
        share = exchange.share_links(say("A learning roadmap for you on inPace 🐢 Tap the link to see it:"),
                                     roadmaps.share_data(rm, in_library), say("A roadmap for you on inPace"))
        not_in_lib = [s for s in rm["steps"] if not library.find(index, s["course"])] if index.get("courses") else []
        text = roadmaps.to_yaml({**rm, "author": rm.get("author") or (V.me["name"] if V.me else "")})
        form_url = (f"{library.SUBMIT_URL}?template=submit-roadmap.yml&title={quote('Roadmap: ' + rm['title'])}"
                    f"&roadmap_title={quote(rm['title'])}&roadmap={quote(text)}")
        return page("roadmap_share.html", request, rm=rm, where=where, share=share, in_library=in_library,
                    not_in_lib=not_in_lib, text=text, form_url=form_url if len(form_url) < 7500 else "",
                    form_plain=f"{library.SUBMIT_URL}?template=submit-roadmap.yml", has_index=bool(index.get("courses")))

    async def roadmap_file(request: Request):
        rm = roadmaps.get(V.home, request.path_params["rid"])
        if not rm:
            return go("/roadmaps", err="That roadmap isn't on this device.")
        return download(roadmaps.to_yaml(rm).encode("utf-8"), f"{rm['id']}.roadmap.yaml", "text/yaml")

    def _voyage_labels() -> dict:
        return {"chart": say("Tempo's voyage along the roadmap"), "harbour": say("Harbour"), "you": say("You are here")}

    async def island_voyages(request: Request):
        """Tempo's island, voyage mode: every roadmap you follow is a sea route, and each course a port."""
        index = await _library_now(online=False)
        voyages = []
        for rm in roadmaps.mine(V.home):
            st = roadmaps.status(V, rm, index)
            voyages.append({"rm": rm, "st": st, "chart": garden.voyage_chart(st, labels=_voyage_labels())})
        voyages.sort(key=lambda x: (x["st"]["finished"], -x["st"]["percent"]))
        st_all = garden.stats(V)
        return page("island_voyages.html", request, voyages=voyages, on=garden.is_on(V), st=st_all,
                    gull=garden.friend_svg("gull", 72), has_gull=garden._have(garden.GULL_GOAL, st_all))

    async def share_course(request: Request):
        """Send a course to someone. If it's in the library, a small link that adds it from there."""
        cid = request.path_params["cid"]
        c = V.get_course(cid)
        if not c:
            return go("/courses", err="That course isn't installed.")
        entry = library.find(library.cached_index(V.home), cid)
        share = None
        if entry:
            share = exchange.share_links(say("Try this course on inPace 🐢 Tap the link to add it:"),
                                         library.share_data(entry), say("A course for you on inPace"))
        return page("share_course.html", request, c=c, entry=entry, share=share,
                    same=bool(entry and entry.get("hash") == c.hash))

    FEEDBACK_URL = "https://github.com/mahmoudyosrimahmoud13/inpace/issues/new"
    env.globals["DISCORD_URL"] = DISCORD_URL
    env.globals["TELEGRAM_URL"] = TELEGRAM_URL
    FEEDBACK_KINDS = [("Problem", "Something doesn't work"), ("Idea or suggestion", "An idea or a suggestion"),
                      ("Question", "A question"), ("Something else", "Something else")]

    def _system_line() -> str:
        import platform
        kind = updater.install_kind()
        where = {"android": "Android app", "windows": "Windows app", "mac": "Mac app", "deb": "Linux (.deb)",
                 "folder": "Linux (folder)", "deb-full": "Linux (.deb, own engine)",
                 "folder-full": "Linux (folder, own engine)",
                 "appimage": "Linux (AppImage)", "appimage-full": "Linux (AppImage, own engine)", "source": "from the code"}.get(kind, kind)
        osname = "Android" if kind == "android" else f"{platform.system()} {platform.release()}".strip()
        return f"{where} · {osname}"

    async def feedback_page(request: Request):
        """Send feedback or a suggestion: a short form here, sent as a GitHub issue that's already filled in."""
        kind = request.query_params.get("kind", "")
        return page("feedback.html", request, base=FEEDBACK_URL, kinds=FEEDBACK_KINDS,
                    kind=kind if kind in {k for k, _ in FEEDBACK_KINDS} else "Problem",
                    version=updater.__version__, system=_system_line(), page_from=request.query_params.get("from", "")[:200])

    async def share_pick(request: Request):
        """Share a course: pick one of yours, then publish it to the library."""
        index = library.cached_index(V.home)
        in_lib = {str(e.get("id")) for e in index.get("courses") or [] if isinstance(e, dict)}
        mine = [c for c in V.courses()]
        return page("share_pick.html", request, mine=mine, in_lib=in_lib)

    async def publish_course(request: Request):
        cid = request.path_params["cid"]
        c = V.get_course(cid)
        if not c:
            return go("/courses", err="That course isn't installed.")
        files = _course_files(c)
        size = sum(p.stat().st_size for p in files.values())
        img = c.extra.get("image")
        big = {k: p for k, p in files.items() if k != img}
        return page("publish.html", request, c=c, submit_url=library.submit_url(c), submit_base=library.SUBMIT_URL,
                    too_big=size > library.MAX_COURSE_BYTES and not c.extra.get("downloads"),
                    needs_downloads=bool(big) and not c.extra.get("downloads"),
                    big_size=sum(p.stat().st_size for p in big.values()),
                    has_answers=bool(c.has_answers), repo=library.REPO)

    async def publish_file(request: Request):
        cid = request.path_params["cid"]
        c = V.get_course(cid)
        if not c:
            return go("/courses", err="That course isn't installed.")
        media, _left = _shareable_files(_course_files(c))
        if sum(p.stat().st_size for p in media.values()) > library.MAX_COURSE_BYTES:
            # Too big to carry: keep only the picture; learners get the rest from the download links.
            img = c.extra.get("image")
            media = {img: media[img]} if img in media else {}
        try:
            data = library.make_submission(V.identity, V.me["name"], c, media)
        except library.LibraryProblem as e:
            return go(f"/courses/{cid}/publish", err=str(e))
        return download(data, f"{c.title} - for the inPace library.zip", "application/zip")

    async def sample_file(request: Request):
        """The picture of a sample course you haven't added yet."""
        cid, rel = request.path_params["cid"], request.path_params["path"]
        root = (SAMPLES / cid / "files").resolve()
        try:
            p = (root / rel).resolve()
            p.relative_to(root)
        except (ValueError, OSError):
            return Response("Not found", status_code=404)
        if not p.is_file() or _media_kind(p.name) != "image":
            return Response("Not found", status_code=404)
        return FileResponse(p, headers={"X-Content-Type-Options": "nosniff"})

    async def add_sample(request: Request):
        cid = request.path_params["cid"]
        folder = SAMPLES / cid
        if not folder.is_dir():
            return go("/courses", err="That sample course wasn't found.")
        c = V.install_course(load_course(files_from_folder(folder)))
        files = folder / "files"  # the course picture and any other files that come with it
        if files.is_dir():
            import shutil
            dest = V.media_dir(c.id)
            for f in files.rglob("*"):
                if f.is_file():
                    target = dest / f.relative_to(files)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(f, target)
        return go("/courses", ok=f"Added “{c.title}”. Press Start when you're ready.")

    async def start_course(request: Request):
        cid = request.path_params["cid"]
        if not V.get_course(cid):
            return go("/courses", err="That course isn't installed.")
        jid = V.start_journey(cid)
        return go(f"/learn/{jid}")

    async def export_course(request: Request):
        c = V.get_course(request.path_params["cid"])
        if not c:
            return go("/courses", err="That course isn't installed.")
        with_answers = request.query_params.get("answers") == "1"
        suffix = " (with answers)" if with_answers else ""
        if request.query_params.get("files") == "1":
            files, _left = _shareable_files(_course_files(c))
            total = sum(p.stat().st_size for p in files.values())
            if total > MAX_MEDIA_PACK_BYTES:
                return go("/courses", err="This course's files are too big to put in one file. Share the course without files, and send the folder another way.")
            import tempfile
            fd, tmp = tempfile.mkstemp(suffix=".lpack")
            import os as _os
            _os.close(fd)
            write_pack_with_media(c, with_answers, files, Path(tmp))
            safe = re.sub(r"[^\w .,()-]+", "", f"{c.title}{suffix} (with files).lpack", flags=re.UNICODE).strip()
            return FileResponse(tmp, filename=safe, media_type="application/zip",
                                background=BackgroundTask(lambda: Path(tmp).unlink(missing_ok=True)))
        img = c.extra.get("image")
        cov = V.find_media(c.id, img) if img else None
        if cov and cov.is_file():
            # The course picture always goes along: it's small, and the course looks right for the next person.
            import tempfile
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "c.lpack"
                write_pack_with_media(c, with_answers, {img: cov}, out)
                return download(out.read_bytes(), f"{c.title}{suffix}.lpack")
        return download(course_to_pack(c, with_answers), f"{c.title}{suffix}.lpack")

    def _course_files_view(cid: str):
        def resume(key: str) -> float:
            try:
                return float(V._meta(f"pos:{key}", "0") or 0)
            except ValueError:
                return 0.0
        try:
            speed = float(V._meta("video_speed", "1") or 1)
        except ValueError:
            speed = 1.0
        def yt_local(vid: str):
            return f"/yt/{quote(cid)}/{quote(vid)}" if offline.local_file(V, cid, vid) else None

        def yt_list(plist: str) -> list:
            return [{"id": it["id"], "title": it.get("title") or it["id"], "url": yt_local(it["id"])}
                    for it in offline.playlist_items(V, cid, plist) if yt_local(it["id"])]
        c = V.get_course(cid)
        book = (c.extra.get("book") or "") if c else ""
        items: dict = {}

        def yt_save(vid: str, plist: str):
            """What the download button under a lesson's YouTube video needs."""
            if not c:
                return None
            if not items:
                items.update({(it["kind"], it["id"]): it for it in offline.course_videos(c)})
            it = items.get(("video", vid) if vid else ("playlist", plist))
            if not it:
                return None
            q = V._meta(f"ytdlp_quality:{cid}", "") or V._meta("ytdlp_quality", "720") or "720"
            size = offline.item_size(V, c, it, q, guess=False)
            ask = f"vid={quote(vid)}" if vid else f"list={quote(plist)}"
            st = offline.video_state(V, c, vid, plist)
            if st.get("why"):
                st["why"] = _tr_why(st["why"])
            return {"action": f"/courses/{quote(cid)}/offline/video", "status": f"/courses/{quote(cid)}/offline/status?{ask}",
                    "size": offline.nice_size(size) if size else "", **st}
        def subs(media: str) -> list:
            return _subtitles(cid, media)
        kind = updater.install_kind()
        return media_mod.CourseFiles(lambda r: V.find_media(cid, r), resume, speed, yt_local, yt_list,
                                     book=book, book_link=f"/courses/{quote(cid)}/go#book", yt_save=yt_save,
                                     parts=youtube_parts(c) if c else {}, subs=subs,
                                     sub_action=f"/courses/{quote(cid)}/subs/add",
                                     open_action="" if kind == "android" else f"/courses/{quote(cid)}/open-media",
                                     system=_system_name())

    # ---- Subtitles: files next to a video, or ones you add (kept apart, never inside the course) -------------
    def _system_name() -> str:
        if updater.install_kind() == "android":
            return "android"
        return {"win32": "windows", "darwin": "mac"}.get(sys.platform, "linux")

    def _subs_dir(cid: str, media: str) -> Path:
        import hashlib
        return V.home / "subtitles" / re.sub(r"[^\w.-]", "_", cid) / hashlib.sha1(media.encode()).hexdigest()[:16]

    def _subtitles(cid: str, media: str) -> list:
        tracks = []
        base = f"/courses/{quote(cid)}/subs?media={quote(media, safe='')}"
        if media and not media.startswith("yt:"):
            p = V.find_media(cid, media)
            if p:
                for label, lang, f in media_mod.sibling_subs(p):
                    tracks.append({"label": label, "lang": lang, "src": f"{base}&f={quote(f.name, safe='')}"})
        d = _subs_dir(cid, media)
        if d.is_dir():
            for f in sorted(d.glob("*.vtt"))[:10]:
                tracks.append({"label": f.stem, "lang": "", "src": f"{base}&f={quote(f.name, safe='')}&u=1"})
        return tracks

    async def subtitle_file(request: Request):
        cid, media = request.path_params["cid"], request.query_params.get("media", "")
        name = request.query_params.get("f", "")
        if not name or "/" in name or "\\" in name or name.startswith("."):
            return Response("Not found", status_code=404)
        if request.query_params.get("u"):
            f = _subs_dir(cid, media) / name
        else:
            p = V.find_media(cid, media) if media and not media.startswith("yt:") else None
            f = next((x for _, _, x in media_mod.sibling_subs(p) if x.name == name), None) if p else None
        if not f or not f.is_file() or f.stat().st_size > 5_000_000:
            return Response("Not found", status_code=404)
        return Response(media_mod.srt_to_vtt(f.read_bytes()), media_type="text/vtt; charset=utf-8",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"})

    async def subtitle_add(request: Request):
        """"Add a subtitle file" in the player: kept in inPace's own folder, next to nothing of the course."""
        cid = request.path_params["cid"]
        form = await request.form()
        media, up = str(form.get("media", "")), form.get("file")
        fetch = request.headers.get("x-inpace-fetch")
        ok_media = media.startswith("yt:") or bool(V.find_media(cid, media))
        name = getattr(up, "filename", "") or ""
        if not V.get_course(cid) or not ok_media or not name.lower().endswith((".srt", ".vtt")):
            return JSONResponse({"ok": False}, status_code=400) if fetch else go(_back(request), err="Choose a .srt or .vtt file.")
        data = await up.read()
        if not data or len(data) > 5_000_000 or b"-->" not in data[:200_000]:
            return JSONResponse({"ok": False}, status_code=400) if fetch else go(_back(request), err="Choose a .srt or .vtt file.")
        d = _subs_dir(cid, media)
        d.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name.rsplit(".", 1)[0]).strip(" .")[:60] or "Subtitles"
        (d / f"{stem}.vtt").write_text(media_mod.srt_to_vtt(data), encoding="utf-8")
        return JSONResponse({"ok": True}) if fetch else go(_back(request), ok="Subtitles added.")

    async def open_media(request: Request):
        """"Open in your video player": for videos the app window can't play (MKV, AVI, H.265…)."""
        form = await request.form()
        p = V.find_media(request.path_params["cid"], str(form.get("media", "")))
        if not p or updater.install_kind() == "android":
            return JSONResponse({"ok": False}, status_code=404)
        try:
            if sys.platform == "win32":
                os.startfile(str(p))  # type: ignore[attr-defined]
            else:
                from .window import _clean_env
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(p)], env=_clean_env(),
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            return JSONResponse({"ok": False}, status_code=500)
        return JSONResponse({"ok": True})

    # ---- YouTube videos on this computer (downloaded with yt-dlp, or your own files) ----------------------------
    async def yt_file(request: Request):
        p = offline.local_file(V, request.path_params["cid"], request.path_params["vid"])
        if not p:
            return Response("Not found", status_code=404)
        return FileResponse(p, headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"})

    def _offline_course(request: Request):
        return V.get_course(request.path_params["cid"])

    def _back_to_course(cid: str) -> str:
        jid = V.journey_for_course(cid)
        return f"/learn/{jid}#offline" if jid else "/courses"

    async def offline_download(request: Request):
        c = _offline_course(request)
        if not c:
            return go("/courses", err="That course isn't installed.")
        if not offline.course_videos(c):
            return go(_back_to_course(c.id), err="This course has no YouTube videos.")
        form = await request.form()
        quality = str(form.get("quality", ""))
        if quality in offline.QUALITIES:
            V._set_meta(f"ytdlp_quality:{c.id}", quality)  # this course remembers its choice
        else:  # the small button at the top of the course page: the quality this course used before
            quality = V._meta(f"ytdlp_quality:{c.id}", "") or ""
        q = quality if quality in offline.QUALITIES else (V._meta("ytdlp_quality", "720") or "720")
        back = _back_to_course(c.id)
        if form.get("from") == "top":
            back = back.split("#")[0]
        need = offline.space_needed(V, c).get(q, 0)
        free = offline.free_space(offline.download_folder(V, c))
        if 0 <= free < need + offline.KEEP_FREE and not form.get("anyway"):
            return go(back, err=gettext(
                "Not enough space: these videos need about {need}, and only {free} is free there. inPace always leaves "
                "300 MB free so your device keeps working. Choose a lower quality or another folder, or free some space.").format(need=offline.nice_size(need), free=offline.nice_size(free)))
        offline.start_download(V, c, quality=quality)
        return go(back, ok="The videos are downloading. You can keep learning while they do.")

    async def offline_video(request: Request):
        """The download button under one lesson's video (or playlist)."""
        c = _offline_course(request)
        if not c:
            return go("/courses", err="That course isn't installed.")
        form = await request.form()
        vid, plist = str(form.get("vid", "")), str(form.get("list", ""))
        item = next((it for it in offline.course_videos(c)
                     if (vid and it["kind"] == "video" and it["id"] == vid)
                     or (plist and it["kind"] == "playlist" and it["id"] == plist)), None)
        as_json = "application/json" in request.headers.get("accept", "")
        ref = urlparse(request.headers.get("referer", "")).path
        back = ref if ref.startswith("/learn/") else _back_to_course(c.id)

        def answer(ok: str = "", err: str = ""):
            if as_json:
                state = offline.video_state(V, c, vid, plist) if item else {"state": "none"}
                if state.get("why"):
                    state["why"] = _tr_why(state["why"])
                return JSONResponse({"ok": not err, "message": gettext(ok or err), **state})
            return go(back, ok=ok) if not err else go(back, err=err)

        if not item:
            return answer(err="This video isn't part of the course.")
        quality = V._meta(f"ytdlp_quality:{c.id}", "") or ""
        q = quality if quality in offline.QUALITIES else (V._meta("ytdlp_quality", "720") or "720")
        need = offline.item_size(V, c, item, q)
        free = offline.free_space(offline.download_folder(V, c))
        if 0 <= free < need + offline.KEEP_FREE and not form.get("anyway"):
            return answer(err=gettext(
                "Not enough space: this video needs about {need}, and only {free} is free there. inPace always leaves "
                "300 MB free so your device keeps working. Free some space, or choose another folder on the course page.").format(need=offline.nice_size(need), free=offline.nice_size(free)))
        offline.start_download(V, c, quality=quality, only=[item])
        return answer(ok="The video is downloading. You can keep learning while it does.")

    # ---- Downloads (v1.30.14): every video download in one place -------------------------------------------
    offline.TRANSLATE[0] = gettext
    try:
        offline.load_settings(V)
    except Exception:
        pass

    def _downloads_now() -> int:
        """How many videos are downloading or waiting (the badge on Downloads in the menu)."""
        try:
            o = offline.overview()
            return (o["active"] + o["waiting"]) if o["running"] else 0
        except Exception:
            return 0

    def _dl_notice(o: dict) -> dict:
        """What the phone's notification says (in your language)."""
        busy = [c for c in o["courses"] if c["state"] == "running"]
        packs = progress.running()
        if packs and not busy:
            x = packs[0]
            pct = round(100 * x["got"] / x["size"]) if x.get("size") else 0
            return {"running": True, "title": gettext("Downloading courses") if x.get("of", 1) > 1 else gettext("Downloading a course"),
                    "body": f"{x.get('title', '')} · {pct}%" + (f" · {x['n']}/{x['of']}" if x.get("of", 1) > 1 else ""),
                    "percent": pct, "stop": "", "channel": gettext("Downloads")}
        if busy:
            first = next((a for c in busy for a in c["active"]), None)
            n = o["active"] + o["waiting"]
            title = gettext("Downloading {n} videos").replace("{n}", str(n)) if n != 1 else gettext("Downloading 1 video")
            body = (f"{first['title']} · {round(first.get('percent') or 0)}%" if first
                    else gettext("Getting ready…"))
            if o["speed"]:
                body += f" · {offline.nice_size(o['speed']).replace(' MB', ' MB/s').replace(' GB', ' GB/s')}"
            return {"running": True, "title": title, "body": body, "percent": round(o["percent"]),
                    "stop": gettext("Stop all"), "channel": gettext("Downloads")}
        saved = sum(c["saved"] for c in o["courses"])
        failed = sum(len(c["failed"]) for c in o["courses"])
        body = (gettext("{n} videos are ready to watch offline.").replace("{n}", str(saved)) if saved != 1
                else gettext("1 video is ready to watch offline."))
        if failed:
            body += " " + gettext("{n} didn't download.").replace("{n}", str(failed))
        return {"running": False, "title": gettext("Downloads finished"), "body": body, "saved": saved,
                "channel": gettext("Downloads")}

    def _tr_why(text: str) -> str:
        """Translate a download problem; "couldn't get yt-dlp" messages are two sentences, each translated."""
        text = text or ""
        if text.startswith(offline.NEED_TOOL):
            return gettext(offline.NEED_TOOL.strip()) + " " + gettext(text[len(offline.NEED_TOOL):])
        return gettext(text)

    def _dl_json() -> dict:
        o = offline.overview()
        for c in o["courses"]:
            for f in c["failed"]:
                f["why"] = _tr_why(offline.plain_why(f.get("why", "")))
            if c.get("error"):
                c["error"] = _tr_why(c["error"])
            if c.get("note"):
                c["note"] = gettext(c["note"])
        o["packs"] = {k: dict(x) for k, x in list(progress.PROGRESS.items())}
        o["notice"] = _dl_notice(o)
        return o

    async def downloads_page(request: Request):
        return page("downloads.html", request, data=_dl_json(), device=offline.on_device(V),
                    parallel=offline.SETTINGS["parallel"], rate=offline.SETTINGS.get("rate_key", "0"),
                    rates=list(offline.RATES), nice_size=offline.nice_size,
                    quality=V._meta("ytdlp_quality", "720") or "720", qualities=offline.QUALITIES,
                    is_android=updater.install_kind() == "android", tool=offline.version(V.home))

    async def downloads_json(request: Request):
        return JSONResponse(_dl_json(), headers={"Cache-Control": "no-store"})

    async def downloads_settings(request: Request):
        form = await request.form()
        offline.save_settings(V, form.get("parallel"), form.get("rate"))
        if str(form.get("quality", "")) in offline.QUALITIES:
            V._set_meta("ytdlp_quality", str(form.get("quality")))
        return go("/downloads", ok="Saved.")

    async def downloads_action(request: Request):
        """Stop, carry on, try the failed ones again, or clear finished ones from the list."""
        form = await request.form()
        action, cid = request.path_params["action"], str(form.get("course", ""))
        jobs = {k: j for k, j in offline.JOBS.items() if not cid or k == cid}
        if action == "stop":
            for k in jobs:
                offline.stop(k)
            return go("/downloads", ok="Stopping. Videos that finished stay.")
        if action == "clear":
            for k, j in jobs.items():
                if j.get("state") != "running":
                    offline.JOBS.pop(k, None)
            return go("/downloads")
        vid = str(form.get("video", ""))
        if action == "cancel" and cid and vid:
            offline.cancel_video(cid, vid)
            return go("/downloads", ok="Removed from the downloads.")
        if action == "next" and cid and vid:
            offline.download_next(cid, vid)
            return go("/downloads", ok="It downloads next.")
        if action == "retry" and cid and vid:
            c, j = V.get_course(cid), offline.JOBS.get(cid) or {}
            f = next((x for x in j.get("failed") or [] if x.get("id") == vid), None)
            if c and f:
                j["failed"] = [x for x in j["failed"] if x.get("id") != vid]
                offline.start_download(V, c, quality=j.get("quality") or "",
                                       only=[{"kind": "video", "id": vid, "title": f.get("title", ""), "lessons": [f.get("title", "")]}])
            return go("/downloads", ok="Trying again.")
        if action in ("resume", "retry"):
            started = 0
            for k, j in jobs.items():
                c = V.get_course(k)
                if not c or j.get("state") == "running":
                    continue
                items = offline.again_items(j, failed_only=action == "retry")
                if items == []:
                    continue
                offline.start_download(V, c, quality=j.get("quality") or "", only=items)
                started += 1
            return go("/downloads", ok="Downloading again." if started else "Nothing to download.")
        return go("/downloads")

    async def downloads_delete(request: Request):
        """Delete one course's downloaded videos (only files inPace downloaded itself)."""
        c = V.get_course(request.path_params["cid"])
        if not c:
            return go("/downloads")
        if (offline.JOBS.get(c.id) or {}).get("state") == "running":
            return go("/downloads", err="Stop the downloads first.")
        gone = offline.forget(V, c, delete_downloads=True)
        return go("/downloads", ok=gettext("Deleted {n} downloaded videos. Lessons play from YouTube again.").format(n=gone)
                  if gone else "Lessons play from YouTube again. Your files weren't touched.")

    async def downloads_open(request: Request):
        """Open the folder with a course's videos (on a computer)."""
        c = V.get_course(request.path_params["cid"])
        d = next((x for x in offline.on_device(V) if x["course"].id == request.path_params["cid"]), None) if c else None
        if not d or updater.install_kind() == "android":
            return go("/downloads")
        try:
            if sys.platform == "win32":
                os.startfile(d["folder"])  # type: ignore[attr-defined]
            else:
                from .window import _clean_env
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", d["folder"]], env=_clean_env(),
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            return go("/downloads", err="inPace couldn't open the folder.")
        return go("/downloads")

    async def downloads_delete_file(request: Request):
        """Delete one downloaded video (only a file inPace downloaded itself)."""
        form = await request.form()
        cid, vid = request.path_params["cid"], str(form.get("video", ""))
        p = offline.local_file(V, cid, vid)
        if p and (V._meta(f"ytdl:{cid}:{vid}", "") or "") == "1":
            try:
                p.unlink()
            except OSError:
                return go("/downloads", err="inPace couldn't delete the file.")
            offline.set_local_file(V, cid, vid, None)
            return go("/downloads", ok="Deleted. This lesson plays from YouTube again.")
        if p:  # your own file: inPace only stops using it
            offline.set_local_file(V, cid, vid, None)
            return go("/downloads", ok="Lessons play from YouTube again. Your files weren't touched.")
        return go("/downloads")

    async def offline_stop(request: Request):
        offline.stop(request.path_params["cid"])
        return go(_back_to_course(request.path_params["cid"]), ok="Stopping the downloads. Finished videos stay.")

    async def offline_status(request: Request):
        c = _offline_course(request)
        if not c:
            return JSONResponse({}, status_code=404)
        st = offline.status(V, c)
        job = {k: v for k, v in (st["job"] or {}).items() if k not in ("stop", "pending", "skip", "first", "titles", "completed")}
        if job.get("title"):
            job["title"] = gettext(job["title"])
        if job.get("error"):
            job["error"] = _tr_why(job["error"])
        out = {"have": st["have"], "total": st["total"], "job": job}
        vid, plist = request.query_params.get("vid", ""), request.query_params.get("list", "")
        if vid or plist:  # one lesson's download button asks how its video is doing
            out["video"] = offline.video_state(V, c, vid, plist)
            if out["video"].get("why"):
                out["video"]["why"] = _tr_why(out["video"]["why"])
        return JSONResponse(out)

    async def offline_match(request: Request):
        """Step 1 of "I already have the videos": look in the folder and suggest which file is which video."""
        c = _offline_course(request)
        if not c:
            return go("/courses", err="That course isn't installed.")
        form = await request.form()
        folder = Path(str(form.get("folder", "")).strip().strip('"')).expanduser()
        if not str(folder).strip() or not folder.is_dir():
            return go(_back_to_course(c.id), err="That folder wasn't found. Copy its full path and paste it here.")
        from starlette.concurrency import run_in_threadpool
        if form.get("lookup"):
            await run_in_threadpool(offline.look_up_titles, V, c)
        files = await run_in_threadpool(offline.video_files, folder)
        if not files:
            return go(_back_to_course(c.id), err="That folder has no video files.")
        targets = offline.targets_for(V, c)
        if not targets:
            return go(_back_to_course(c.id), err="inPace needs the playlist's list of videos first. Connect to the internet and try again.")
        rows = await run_in_threadpool(offline.match, targets, files)
        for r, tg in zip(rows, targets):
            r["label"], r["lessons"] = tg["label"], tg.get("lessons") or []
            cur = offline.local_file(V, c.id, tg["key"])
            r["current"] = str(cur) if cur and not r["file"] else ""  # keep a file you linked before
        return page("offline_match.html", request, course=c, folder=str(folder), rows=rows,
                    files=[(str(f), str(f.relative_to(folder))) for f in files], back=_back_to_course(c.id),
                    sure=sum(r["sure"] == "yes" for r in rows))

    async def offline_save(request: Request):
        """Step 2: save the pairs the person checked."""
        c = _offline_course(request)
        if not c:
            return go("/courses", err="That course isn't installed.")
        form = await request.form()
        folder = Path(str(form.get("folder", ""))).expanduser()
        known = {t["key"] for t in offline.targets_for(V, c)}
        saved = 0
        for key, value in form.multi_items():
            if not key.startswith("file:") or key[5:] not in known:
                continue
            if value == "keep":
                continue
            path = Path(str(value)) if value else None
            if path:
                try:
                    path.resolve().relative_to(folder.resolve())  # only files from the folder that was searched
                except (ValueError, OSError):
                    continue
                if not path.is_file():
                    continue
            offline.set_local_file(V, c.id, key[5:], path)
            saved += bool(path)
        return go(_back_to_course(c.id), ok=gettext("{n} videos now play from this computer.").format(n=saved))

    # ---- a course's book, which each learner gets themselves ------------------------------------------------
    def _book_state(c: Course) -> dict | None:
        name = c.extra.get("book")
        if not name:
            return None
        info = c.extra.get("book_info") or {}
        found = V.find_media(c.id, name)
        return {"name": name, "info": info, "path": str(found) if found else "", "mine": bool(V.book_file(c.id)),
                "warning": V._meta(f"bookwarn:{c.id}", "") or ""}

    async def course_go(request: Request):
        """A course's own page (its journey), from anywhere that only knows the course id."""
        jid = V.journey_for_course(request.path_params["cid"])
        return RedirectResponse(f"/learn/{jid}" if jid else "/courses", status_code=303)

    async def course_book(request: Request):
        """Show inPace where your copy of the course's book is: a PDF, a folder to look in, or the usual places."""
        cid = request.path_params["cid"]
        c = V.get_course(cid)
        if not c or not c.extra.get("book"):
            return go("/courses", err="That course isn't installed.")
        form = await request.form()
        back = _back_to_course(cid).replace("#offline", "#book")
        info, name = c.extra.get("book_info") or {}, c.extra["book"]
        from starlette.concurrency import run_in_threadpool
        if form.get("search"):
            found = await run_in_threadpool(books.search, info, name)
            if not found:
                return go(back, err="inPace didn't find the book in Downloads, Documents or Desktop. Choose its folder or the file.")
        else:
            raw = str(form.get("path", "")).strip().strip('"')
            p = Path(raw).expanduser() if raw else None
            if not p or not p.exists():
                return go(back, err="That file or folder wasn't found. Copy its full path and paste it here.")
            if p.is_dir():
                found = await run_in_threadpool(books.find_in, p, info, name)
                if not found:
                    return go(back, err="There's no matching PDF in that folder. Choose the PDF file itself.")
            elif p.suffix.lower() != ".pdf":
                return go(back, err="Choose a PDF file.")
            else:
                found = p
        warning = await run_in_threadpool(books.check, found, info)
        if warning == "That file couldn't be read as a PDF.":
            return go(back, err=warning)
        V.set_book_file(cid, found)
        pages, _ = await run_in_threadpool(books.pdf_facts, found)
        V._set_meta(f"bookwarn:{cid}", gettext(warning).format(got=pages, want=info.get("pages", "?")) if warning else "")
        return go(back, ok=gettext("Found your book: {path}").format(path=found))

    async def offline_folder(request: Request):
        """Where this course saves its videos, and the name of its folder."""
        c = _offline_course(request)
        if not c:
            return go("/courses", err="That course isn't installed.")
        form = await request.form()
        base = str(form.get("base", "")).strip().strip('"')
        if base and not Path(base).expanduser().is_dir():
            return go(_back_to_course(c.id), err="That folder wasn't found. Copy its full path and paste it here.")
        V._set_meta(f"ytdlp_base:{c.id}", str(Path(base).expanduser()) if base else "")
        name = str(form.get("name", "")).strip()
        V._set_meta(f"ytdlp_dirname:{c.id}", offline.safe_name(name) if name and offline.safe_name(name) != offline.safe_name(c.title) else "")
        return go(_back_to_course(c.id), ok=gettext("New downloads go to {folder}").format(folder=offline.download_folder(V, c)))

    async def offline_forget(request: Request):
        c = _offline_course(request)
        if not c:
            return go("/courses", err="That course isn't installed.")
        form = await request.form()
        if any(j.get("state") == "running" for cid, j in offline.JOBS.items() if cid == c.id):
            return go(_back_to_course(c.id), err="Stop the downloads first.")
        gone = offline.forget(V, c, delete_downloads=form.get("delete") == "1")
        msg = gettext("Deleted {n} downloaded videos. Lessons play from YouTube again.").format(n=gone) if gone \
            else "Lessons play from YouTube again. Your files weren't touched."
        return go(_back_to_course(c.id), ok=msg)

    async def video_settings(request: Request):
        form = await request.form()
        if form.get("updates") in ("auto", "manual"):
            V._set_meta("ytdlp_updates", str(form.get("updates")))
        if str(form.get("quality", "")) in offline.QUALITIES:
            V._set_meta("ytdlp_quality", str(form.get("quality")))
        folder = str(form.get("folder", ""))
        if folder == "custom":
            path = str(form.get("folder_path", "")).strip().strip('"')
            if not path or not Path(path).expanduser().is_dir():
                return go("/settings#videos", err="That folder wasn't found. Copy its full path and paste it here.")
            V._set_meta("ytdlp_folder_path", str(Path(path).expanduser()))
        if folder in offline.FOLDERS:
            V._set_meta("ytdlp_folder", folder)
        return go("/settings#videos", ok="Saved.")

    async def video_tool_update(request: Request):
        from starlette.concurrency import run_in_threadpool
        form = await request.form()
        back = "/downloads" if form.get("back") == "downloads" else "/settings#videos"
        token = _progress_token(form)
        try:
            changed, ver = await run_in_threadpool(progress.within, token, {"title": "yt-dlp", "note": "download"},
                                                   offline.update_tool, V.home)
        except offline.ToolProblem as e:
            return go(back, err=str(e))
        finally:
            progress.report(token, state="done")
        V._set_meta("ytdlp_checked", str(_time.time()))
        if changed:
            return go(back, ok=gettext("yt-dlp {v} is ready.").format(v=ver))
        return go(back, ok=gettext("You already have the newest yt-dlp ({v}).").format(v=ver))

    async def pdf_reader(request: Request):
        """inPace's own PDF reader (pdf.js, bundled), so PDFs open in every app window, offline."""
        src = request.query_params.get("src", "")
        if not src.startswith(("/m/", "/evidence/", "/files/")):
            return Response("Not found", status_code=404)
        key = request.query_params.get("key", "")[:600]
        try:
            start = int(float(V._meta(f"pos:{key}", "0") or 0)) if key else 0
        except ValueError:
            start = 0
        CURRENT["lang"] = V._meta("lang", "en") or "en"

        def num(name: str) -> int:
            v = request.query_params.get(name, "")
            return int(v) if v.isdigit() and 0 < int(v) < 100000 else 0
        first, last = num("from"), num("to")
        if last and first > last:
            first, last = last, first
        return page("pdf_viewer.html", request, src=src, key=key, start=max(start, 1), first=first or 1, last=last,
                    file_name=request.query_params.get("name", "PDF")[:200], standalone=request.query_params.get("full") == "1")

    async def media_position(request: Request):
        """The video player reports where you are every few seconds, so it can continue from there next time."""
        form = await request.form()
        key = str(form.get("key", ""))[:600]
        try:
            t = max(0.0, float(form.get("t") or 0))
            d = float(form.get("d") or 0)
        except ValueError:
            return Response(status_code=400)
        if form.get("speed"):
            try:
                V._set_meta("video_speed", str(min(3.0, max(0.25, float(form.get("speed"))))))
            except ValueError:
                pass
        if key and "|" in key:
            # Near the end counts as finished: next time it starts from the beginning.
            done = d > 0 and t > d - max(10.0, d * 0.03)
            V._set_meta(f"pos:{key}", "0" if done else f"{t:.1f}")
        return Response(status_code=204)

    SHARE_FILE_LIMIT = 25 * 1024 * 1024

    def _shareable_files(files: dict) -> tuple[dict, list]:
        """What may travel inside a shared course file: small files only (PDFs, slides, pictures, code).
        Videos, audio and anything over 25 MB stay on this computer; the other person gets them their own way
        (YouTube, the course's download links, or their own folder)."""
        keep, left = {}, []
        for rel, p in files.items():
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if _media_kind(p.name) in ("video", "audio") or size > SHARE_FILE_LIMIT:
                left.append(rel)
            else:
                keep[rel] = p
        return keep, left

    def _course_files(c: Course, include_book: bool = False) -> dict:
        """Every file of the course that's on this computer, by its path inside the course.
        A book course's book is left out unless asked for: people share the course, and each uses their own copy."""
        out = {}
        book = c.extra.get("book")
        for m in c.modules:
            for les in m["lessons"]:
                for ref in media_mod.media_refs(les):
                    if book and ref == book and not include_book:
                        continue
                    p = V.find_media(c.id, ref)
                    if p and p.is_dir():
                        for f in p.rglob("*"):
                            if f.is_file() and not any(x in media_mod.SKIP_DIRS or x.startswith(".")
                                                       for x in f.relative_to(p).parts):
                                out[(ref.rstrip("/") + "/" + f.relative_to(p).as_posix()).lstrip("/").replace(":", "")] = f
                    elif p:
                        out[ref.lstrip("/").replace(":", "")] = p
        img = c.extra.get("image")
        cov = V.find_media(c.id, img) if img else None
        if cov and cov.is_file():
            out[img] = cov
        return out

    async def media_file(request: Request):
        """A course's video, audio, page or picture, straight from where it lives on this computer."""
        p = V.find_media(request.path_params["cid"], request.path_params["path"])
        if not p or p.is_dir():
            return Response("Not found", status_code=404)
        headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"}
        if p.suffix.lower() in HTML_EXT + (".svg",):
            # Pages run sealed off: their own scripts work, but they can't reach inPace, your data, or the internet.
            headers["Content-Security-Policy"] = (
                "sandbox allow-scripts allow-popups; default-src 'self' http://127.0.0.1:* 'unsafe-inline' "
                "'unsafe-eval' data: blob:; connect-src 'none'; form-action 'none'")
        if request.query_params.get("view") == "1" and p.stat().st_size < 5_000_000:
            # "Open it" for a code file: show it as plain text instead of running or downloading it.
            return Response(p.read_bytes(), media_type="text/plain; charset=utf-8", headers=headers)
        return FileResponse(p, headers=headers)

    async def course_from_folder_route(request: Request):
        form = await request.form()
        folder = str(form.get("folder", "")).strip().strip('"')
        if not folder:
            return go("/courses", err="Choose a folder first.")
        try:
            c = course_from_folder(Path(folder).expanduser(), str(form.get("title", "")))
        except CourseError as e:
            return go("/courses", err=e.problems[0])
        base, n = c.id, 1
        while V.get_course(c.id):
            n += 1
            c.id = f"{base}-{n}"
        V.set_media_root(c.id, str(Path(folder).expanduser()))
        V.install_course(c)
        return go("/courses", ok=f"Added “{c.title}” from your folder. The files stay where they are.")

    async def set_media_folder(request: Request):
        cid = request.path_params["cid"]
        c = V.get_course(cid)
        form = await request.form()
        back = request.headers.get("referer") or "/courses"
        if not back.startswith(("http://127.0.0.1", "http://localhost", "/")):
            back = "/courses"
        if not c:
            return go("/courses", err="That course isn't installed.")
        folder = str(form.get("folder", "")).strip().strip('"')
        if folder.lower().endswith(".zip") and Path(folder).expanduser().is_file():
            from . import coursefiles  # a zip: unzip it into inPace's folder, then use that
            from starlette.concurrency import run_in_threadpool
            try:
                folder = str(await run_in_threadpool(coursefiles.unzip, Path(folder).expanduser(), V.home / "course-files" / cid))
            except (ValueError, OSError, zipfile.BadZipFile):
                return RedirectResponse(_with_msg(back, err="That zip couldn't be opened. Download it again, or unzip it yourself and choose the folder."), 303)
        if not folder or not Path(folder).expanduser().is_dir():
            return RedirectResponse(_with_msg(back, err="That folder wasn't found. Copy its full path and paste it here."), 303)
        V.set_media_root(cid, folder)
        left = V.missing_media(c)
        if left:
            return RedirectResponse(_with_msg(back, err=f"Found the folder, but {len(left)} file(s) are still missing."), 303)
        return RedirectResponse(_with_msg(back, ok="Found all the course files."), 303)

    async def find_course_files(request: Request):
        """"Find them for me": look in Downloads, Documents and Desktop for the course's missing files, in a folder
        (even a few folders down) or in a .zip (unzipped into inPace's folder). The folder found is remembered."""
        from . import coursefiles
        from starlette.concurrency import run_in_threadpool
        cid = request.path_params["cid"]
        c = V.get_course(cid)
        back = request.headers.get("referer") or "/courses"
        if not back.startswith(("http://127.0.0.1", "http://localhost", "/")):
            back = "/courses"
        if not c:
            return go("/courses", err="That course isn't installed.")
        missing = V.missing_media(c)
        if not missing:
            return RedirectResponse(_with_msg(back, ok="Found all the course files."), 303)
        names = {Path(m).name for m in missing}
        found = await run_in_threadpool(coursefiles.find_folder, names)
        if found:
            V.set_media_root(cid, str(found))
            missing = V.missing_media(c)
        if missing:
            z = await run_in_threadpool(coursefiles.find_zip, {Path(m).name for m in missing})
            if z:
                try:
                    out = await run_in_threadpool(coursefiles.unzip, z, V.home / "course-files" / cid)
                    V.set_media_root(cid, str(out))
                    missing = V.missing_media(c)
                except (ValueError, OSError, zipfile.BadZipFile):
                    pass
        if not missing:
            return RedirectResponse(_with_msg(back, ok="Found all the course files."), 303)
        if found or V.media_root(cid):
            return RedirectResponse(_with_msg(back, err=f"Found some of the files, but {len(missing)} are still missing. If the download hasn't finished, wait and try again."), 303)
        return RedirectResponse(_with_msg(back, err="Didn't find them in Downloads, Documents or Desktop. If you saved them somewhere else, choose that folder or zip below."), 303)

    def _with_msg(url: str, ok: str = "", err: str = "") -> str:
        from urllib.parse import urlsplit
        u = urlsplit(url)
        path = u.path or "/"
        if u.query:
            keep = "&".join(x for x in u.query.split("&") if not x.startswith(("ok=", "err=", "yay=")))
            path += ("?" + keep) if keep else ""
        return go(path, ok=ok or None, err=err or None).headers["location"]

    async def pick_folder_route(request: Request):
        title = say("Choose the course folder")
        import anyio
        folder = await anyio.to_thread.run_sync(lambda: integrations.pick_folder(title))
        return JSONResponse({"folder": folder})

    # ---- Add a course: the easy way --------------------------------------------------------------------
    FIXED_TITLES = ("General", "Other materials", "Not sorted yet", "Videos", "Audio", "Slides and PDFs",
                    "Documents and sheets", "Web pages", "Notes", "Pictures", "Code", "Other files")

    def _book_words(text: str) -> str:
        """Names inPace makes up for parts of a book, in the app's language."""
        CURRENT["lang"] = V._meta("lang", "en") or "en"
        if text in ("Front matter", "Introduction"):
            return say(text)
        m = re.fullmatch(r"Pages (\d+)–(\d+)", text)
        return t("Pages {a} to {b}", a=m.group(1), b=m.group(2)) if m else text

    def _drafts() -> Path:
        d = V.home / "drafts"
        d.mkdir(exist_ok=True)
        return d

    def _book(form_or_query, folder: Path | None) -> str:
        """The book's file name in that folder (a PDF), or ""."""
        name = str(form_or_query.get("book", "")).strip()
        if not name or not folder or "/" in name or "\\" in name or name.startswith(".") or not name.lower().endswith(".pdf"):
            return ""
        return name if (folder / name).is_file() else ""

    def _source(form_or_query) -> tuple[Path | None, str, str]:
        """(folder, folder text, draft id). A draft is files you picked, already copied into inPace."""
        draft = str(form_or_query.get("draft", "")).strip()
        if draft:
            if not re.fullmatch(r"[0-9a-f]{16}", draft) or not (_drafts() / draft).is_dir():
                return None, "", ""
            return _drafts() / draft, "", draft
        text = str(form_or_query.get("folder", "")).strip().strip('"')
        return (Path(text).expanduser() if text else None), text, ""

    async def add_hub(request: Request):
        import shutil
        import time
        for d in _drafts().iterdir():  # files picked but never made into a course
            if d.is_dir() and time.time() - d.stat().st_mtime > 2 * 86400:
                shutil.rmtree(d, ignore_errors=True)
        return page("add.html", request, ai=integrations.ai_settings(V))

    def _organizer(request: Request, folder: Path, folder_text: str, draft: str, plan: dict, book: str = "",
                   **extra) -> HTMLResponse:
        import shutil
        if book:
            full = organize.book_plan(folder / book, plan["title"])
            files = set(full["names"])
            info = organize.book_info(folder / book, full)
            for ref in info:
                info[ref]["name"] = _book_words(info[ref]["name"])
            for sec in plan["sections"]:
                sec["title"] = _book_words(sec["title"])
            names = plan.get("names") or {}
            for ref, name in list(names.items()):
                names[ref] = _book_words(name)
                if ref in info:
                    info[ref] = {**info[ref], "name": names[ref]}
            extra.pop("allowed", None)
            plan.setdefault("cant_show", [])
        else:
            files = organize.all_files(folder, plan["title"]) if "allowed" not in extra else extra.pop("allowed")
            info = organize.file_info(folder, sorted(files))
        used = {f for s in plan["sections"] for f in s["files"]}
        try:
            free = shutil.disk_usage(V.home).free
        except OSError:
            free = 0
        CURRENT["lang"] = V._meta("lang", "en") or "en"
        for sec in plan["sections"]:
            if sec["title"] in FIXED_TITLES:
                sec["title"] = say(sec["title"])
        files_list = sorted(files, key=lambda f: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", f)])
        cant = plan.get("cant_show")
        if cant is None and not book:
            try:
                cant = organize.guess_plan(folder)["cant_show"]
            except CourseError:
                cant = []
        return page("add_organize.html", request, plan=plan, info=info, cant_show=cant, book=book, left_out=[f for f in files_list if f not in used],
                    folder=folder_text, draft=draft, free=free, nice_size=organize.nice_size,
                    ai=integrations.ai_settings(V), prompt=organize.ai_prompt(plan["title"], files_list, extra.get("notes", "")),
                    **extra)

    async def add_organize(request: Request):
        if request.method == "GET":
            folder, text, draft = _source(request.query_params)
            title = str(request.query_params.get("title", ""))
            if not folder:
                return go("/add/folder", err="Choose a folder first.")
            book = _book(request.query_params, folder)
            if book:
                try:
                    plan = organize.book_plan(folder / book, title)
                except CourseError as e:
                    return go("/add/book", err=e.problems[0])
                return _organizer(request, folder, text, draft, plan, book=book, how=plan["how"])
            try:
                plan = organize.guess_plan(folder, title)
            except CourseError as e:
                return go("/add/folder", err=e.problems[0])
            if draft and not plan["sections"]:
                return go("/add/files", err="None of those files can be shown in inPace.")
            how = "folders" if plan["organized"] else ("numbers" if any(
                s["title"].split(" ")[0] in ("Week", "Lecture", "Chapter", "Unit", "Module", "Part", "Session", "Lesson",
                                             "Topic", "Day", "Section", "Lab", "Tutorial", "Class") or s["title"].startswith("ال")
                for s in plan["sections"]) else ("kinds" if len(plan["sections"]) > 1 else "one"))
            return _organizer(request, folder, text, draft, plan, how=how)
        form = await request.form()
        folder, text, draft = _source(form)
        if not folder or not folder.is_dir():
            return go("/add/folder", err="That folder wasn't found. Copy its full path and paste it here.")
        book = _book(form, folder)
        try:
            if book:
                book_full = organize.book_plan(folder / book)
                allowed = set(book_full["names"])
            else:
                allowed = organize.all_files(folder)
        except CourseError as e:
            return go("/add/book" if book else "/add/folder", err=e.problems[0])
        try:
            raw = json.loads(str(form.get("plan") or "{}"))
        except ValueError:
            raw = {}
        plan = organize.clean_plan(folder, raw if isinstance(raw, dict) else {}, allowed)
        action = str(form.get("action", "create"))
        notes = str(form.get("notes", ""))
        if action in ("ai_auto", "ai_paste"):
            reply = str(form.get("reply", ""))
            if action == "ai_auto":
                from starlette.concurrency import run_in_threadpool
                files_list = sorted(allowed)
                try:
                    reply = await run_in_threadpool(integrations.ask_ai, V, organize.ai_prompt(plan["title"], files_list, notes))
                except RuntimeError as e:
                    return _organizer(request, folder, text, draft, plan, allowed=allowed, notes=notes, ai_error=str(e), open_ai=True)
            try:
                plan = organize.merge_ai(organize.parse_ai(reply), folder, allowed, plan["title"])
            except CourseError as e:
                return _organizer(request, folder, text, draft, plan, allowed=allowed, notes=notes, reply=reply,
                                  ai_error=e.problems[0], open_ai=True)
            return _organizer(request, folder, text, draft, plan, allowed=allowed, notes=notes, how="ai")
        try:
            if book:
                info = organize.book_info(folder / book, book_full)
                for ref in info:
                    info[ref]["name"] = _book_words(info[ref]["name"])
                c = organize.course_from_book(folder, book, plan, info)
            else:
                c = organize.course_from_plan(folder, plan)
        except CourseError as e:
            return _organizer(request, folder, text, draft, plan, book=book, allowed=allowed, problem=e.problems[0])
        base, n = c.id, 1
        while V.get_course(c.id):
            n += 1
            c.id = f"{base}-{n}"
        import shutil
        if draft:  # picked files: they already live in inPace, move them to the course's own folder
            target = V.media_dir(c.id)
            shutil.rmtree(target, ignore_errors=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(folder), str(target))
            V.install_course(c)
            return go(f"/courses?show={c.id}", ok=f"Added “{c.title}”.\nIts files are saved in inPace.")
        V.set_media_root(c.id, str(folder))
        V.install_course(c)
        if form.get("storage") == "copy":
            need = organize.plan_size(folder, plan)
            try:
                free = shutil.disk_usage(V.home).free
            except OSError:
                free = need + 1
            if need > free:
                return go(f"/courses?show={c.id}", err="There isn't enough free space to copy the files, so they stay where they are.")
            cid = c.id
            organize.start_copy(cid, folder, plan, V.media_dir(cid), done=lambda: V.set_media_root(cid, ""))
            return go(f"/add/copying/{cid}")
        return go(f"/courses?show={c.id}", ok=f"Added “{c.title}”.\nThe files stay where they are.")

    async def add_folder(request: Request):
        return page("add_folder.html", request)

    async def add_files(request: Request):
        if request.method == "GET":
            return page("add_files.html", request)
        import secrets
        form = await request.form()
        ups = [u for u in form.getlist("files") if getattr(u, "filename", "")]
        if not ups:
            return go("/add/files", err="Choose some files first.")
        draft = secrets.token_hex(8)
        root = _drafts() / draft
        for up in ups:
            parts = [x for x in re.split(r"[\\/]+", up.filename) if x not in ("", ".", "..")]
            if not parts:
                continue
            dst = root.joinpath(*[re.sub(r'[<>:"|?*\x00-\x1f]', "_", x) for x in parts])
            dst.parent.mkdir(parents=True, exist_ok=True)
            with open(dst, "wb") as out:
                while chunk := await up.read(4 * 1024 * 1024):
                    out.write(chunk)
        from urllib.parse import quote as q
        return RedirectResponse(f"/add/organize?draft={draft}&title={q(str(form.get('title', '')))}", 303)

    async def add_book(request: Request):
        """A book (PDF): pick the file (inPace keeps a copy) or give the path of one to leave where it is."""
        if request.method == "GET":
            return page("add_book.html", request)
        import secrets
        form = await request.form()
        title = str(form.get("title", ""))
        from urllib.parse import quote as q
        path = str(form.get("path", "")).strip().strip('"')
        if path:
            p = Path(path).expanduser()
            if not p.is_file() or p.suffix.lower() != ".pdf":
                return go("/add/book", err="That PDF wasn't found. Copy its full path and paste it here.")
            return RedirectResponse(f"/add/organize?folder={q(str(p.parent))}&book={q(p.name)}&title={q(title)}", 303)
        up = form.get("book")
        if not up or not getattr(up, "filename", "") or not up.filename.lower().endswith(".pdf"):
            return go("/add/book", err="Choose a PDF first.")
        draft = secrets.token_hex(8)
        root = _drafts() / draft
        root.mkdir(parents=True)
        name = re.sub(r'[<>:"|?*\x00-\x1f/\\]', "_", up.filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]) or "book.pdf"
        with open(root / name, "wb") as out:
            while chunk := await up.read(4 * 1024 * 1024):
                out.write(chunk)
        return RedirectResponse(f"/add/organize?draft={draft}&book={q(name)}&title={q(title)}", 303)

    async def add_copying(request: Request):
        cid = request.path_params["cid"]
        job = organize.JOBS.get(cid)
        c = V.get_course(cid)
        if not c:
            return go("/courses", err="That course isn't installed.")
        if not job or job["state"] == "done":
            return go(f"/courses?show={cid}", ok=f"Added “{c.title}”.\nIts files are copied into inPace.")
        return page("add_copying.html", request, c=c, job=job, nice_size=organize.nice_size)

    # ---- Reminders and alarms ----------------------------------------------------------------------------
    def _scheduler_status() -> str:
        if os.environ.get("INPACE_MOBILE") == "android":
            return "android"
        st = V._meta("scheduler_status", "") or ""
        return st.split(":")[0] if st else ""

    async def reminders_page(request: Request):
        if request.method == "POST":
            form = await request.form()
            action = str(form.get("action", ""))
            if action == "add":
                days = [int(d) for d in form.getlist("days") if str(d).isdigit() and int(d) in range(7)]
                every, start = 1, None
                if form.get("repeat") == "every":  # "Other": every few days, from a day you pick
                    try:
                        every = int(form.get("every") or 0)
                    except ValueError:
                        every = 0
                    if not 2 <= every <= reminders.MAX_EVERY:
                        return go("/reminders", err="Choose how many days apart, from 2 to 60.")
                    start = reminders._date(form.get("start")) or date.today()
                    days = list(range(7))
                if not days:
                    return go("/reminders", err="Choose at least one day.")
                r = reminders.add(V, str(form.get("time", "")), days,
                                  "alarm" if form.get("kind") == "alarm" else "notify", str(form.get("label", "")),
                                  every=every, start=start)
                if not r:
                    return go("/reminders", err="Choose a time for the reminder.")
                msg = "Reminder added."
            elif action in ("toggle", "delete"):
                reminders.change(V, str(form.get("id", "")), action)
                msg = "Reminder removed." if action == "delete" else "Saved."
            elif action == "auto":
                reminders.set_auto(V, {k: form.get(k) == "1" for k in reminders.AUTO_KINDS}, int(form.get("miss_days") or 7))
                msg = "Saved."
            else:
                return go("/reminders")
            from starlette.concurrency import run_in_threadpool
            status = await run_in_threadpool(notifier.sync, V, True)
            if status.startswith("error"):
                return go("/reminders", ok=msg, err="Your computer's scheduler said no, so reminders only show while inPace is open.")
            return go("/reminders", ok=msg)
        d = reminders.load(V)
        return page("reminders.html", request, r=d, status=_scheduler_status(), detail=V._meta("scheduler_status", "") or "",
                    today=date.today().isoformat(),
                    test_msg=reminders.reminder_message(V, {"label": say("Test: this is how a reminder looks")}))

    async def reminders_plan(request: Request):
        """For the Android app: everything to schedule (it asks again whenever you use inPace)."""
        return JSONResponse(reminders.plan(V))

    async def reminders_test(request: Request):
        form = await request.form()
        kind = "alarm" if form.get("kind") == "alarm" else "notify"
        msg = reminders.reminder_message(V, {"label": say("Test: this is how a reminder looks")})
        labels = {"stop": say("Stop"), "snooze": say("Snooze 10 min"), "open": say("Start studying")}
        if kind == "alarm":
            threading.Thread(target=notifier.alarm, args=(msg["title"], msg["body"], msg["url"], labels, V.home, msg["picture"]),
                             daemon=True).start()
            return go("/reminders", ok="The alarm is ringing. Stop it or snooze it.")
        from starlette.concurrency import run_in_threadpool
        ok = await run_in_threadpool(notifier.notify, msg["title"], msg["body"], msg["url"], V.home, msg["picture"])
        return go("/reminders", ok="Sent. Look for it in the corner of your screen.") if ok else \
            go("/reminders", err="This computer didn't show the notification. Check that notifications are allowed for inPace.")

    async def remove_course(request: Request):
        """Delete a course. A started course needs a tick in the box first, because its progress goes too."""
        cid = request.path_params["cid"]
        c = V.get_course(cid)
        if not c:
            return go("/courses", err="That course isn't installed.")
        jid = V.journey_for_course(cid)
        if request.method == "GET":
            info = None
            if jid:
                prog = V.progress(jid)
                info = {"percent": prog["percent"], "milestones": len(V.milestones(jid))}
            return page("delete_course.html", request, c=c, info=info)
        form = await request.form()
        if jid and form.get("sure") != "1":
            return go(f"/courses/{cid}/remove", err="Tick the box to confirm.")
        import shutil
        shutil.rmtree(V.home / "course_history" / cid, ignore_errors=True)
        if jid:
            V.archive_course(cid)
        else:
            V.delete_course(cid)
            folders.forget(V, cid)
        return go("/courses", ok=f"Deleted “{c.title}”.")

    # ---- updating a course to a newer version ---------------------------------
    def _pending(cid: str) -> Path:
        return V.home / "pending" / cid

    def _hold_update(new: Course, media_zip=None):
        """A newer copy of a course you already have arrived. Keep it aside and ask what to do."""
        import shutil
        from .course import save_course_folder
        pend = _pending(new.id)
        shutil.rmtree(pend, ignore_errors=True)
        save_course_folder(new, pend / "course")
        if media_zip is not None:
            zf, inside = media_zip
            for info, rel in inside:
                target = (pend / "files" / rel)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out, 1024 * 1024)
        return go(f"/courses/{new.id}/update")

    def _outline_lines(c: Course) -> list:
        out = []
        for m in c.modules:
            out.append(("module", m["title"], ""))
            out += [("lesson", les["title"], m["title"]) for les in m["lessons"]]
        return out

    async def course_update(request: Request):
        cid = request.path_params["cid"]
        cur = V.get_course(cid)
        pend = _pending(cid)
        if not cur or not (pend / "course" / "course.yaml").exists():
            return go("/courses", err="There's no update waiting for this course.")
        new = load_course(files_from_folder(pend / "course"))
        if request.method == "GET":
            a, b = _outline_lines(cur), _outline_lines(new)
            added = [x for x in b if x not in a]
            removed = [x for x in a if x not in b]
            jid = V.journey_for_course(cid)
            return page("update_course.html", request, cur=cur, new=new, added=added[:40], removed=removed[:40],
                        same=(cur.hash == new.hash), started=bool(jid))
        import shutil
        form = await request.form()
        choice = form.get("choice")
        if choice == "cancel":
            shutil.rmtree(pend, ignore_errors=True)
            return go("/courses", ok="Kept your course as it was.")
        if choice == "separate":
            base, n = new.id, 1
            while V.get_course(new.id):
                n += 1
                new.id = f"{base}-{n}"
        else:
            new.extra.update({k: v for k, v in cur.extra.items() if k not in new.extra})
            # The version before is kept, so Undo in the editor can bring it back.
            editor.save(V, new)
        if choice == "separate":
            V.install_course(new)
        files = pend / "files"
        if files.exists():
            dest = V.media_dir(new.id)
            dest.mkdir(parents=True, exist_ok=True)
            for f in files.rglob("*"):
                if f.is_file():
                    target = dest / f.relative_to(files)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(f), str(target))
        shutil.rmtree(pend, ignore_errors=True)
        if choice == "separate":
            return go("/courses", ok=f"Added “{new.title}” as a separate course.")
        return go("/courses", ok=f"Updated “{new.title}”. Your progress is kept.")

    async def refresh_from_folder(request: Request):
        """Look in the course's folder again: new videos become new lessons, everything you did stays."""
        cid = request.path_params["cid"]
        cur = V.get_course(cid)
        root = V.media_root(cid)
        if not cur or not root:
            return go("/courses", err="This course isn't linked to a folder.")
        try:
            fresh = course_from_folder(root, cur.title)
        except CourseError as e:
            return go("/courses", err=e.problems[0])
        merged, added = _merge_folder(cur, fresh)
        if not added:
            return go(_back(request), ok="Nothing new in the folder. Your course is up to date.")
        editor.bump(merged)
        editor.save(V, merged)
        return go(_back(request), ok=f"Added {added} new lesson(s) from the folder.")

    def _merge_folder(cur: Course, fresh: Course):
        """Keep every existing module and lesson (with your edits, tasks and ids); add what's new."""
        import copy
        merged = copy.deepcopy(cur)
        have = {les.get("media") for m in merged.modules for les in m["lessons"] if les.get("media")}
        ids = editor.all_ids(merged)
        added = 0
        for fm in fresh.modules:
            new_lessons = [les for les in fm["lessons"] if les.get("media") and les["media"] not in have]
            if not new_lessons:
                continue
            target = next((m for m in merged.modules if m["title"] == fm["title"]), None)
            if target is None:
                mid = editor._unique("m", ids)
                ids.add(mid)
                target = {"id": mid, "title": fm["title"], "lessons": [], "requires": []}
                merged.modules.append(target)
            for les in new_lessons:
                lid = editor._unique(f"{target['id']}-l", ids)
                ids.add(lid)
                target["lessons"].append({**les, "id": lid})
                added += 1
        merged.extra["media_index"] = {**cur.extra.get("media_index", {}), **fresh.extra.get("media_index", {})}
        return merged, added

    # ---- AI course maker -----------------------------------------------------
    def _titled_videos(text: str) -> str:
        out = []
        for line in text.splitlines()[:200]:
            line = line.strip()
            if not line:
                continue
            if "|" not in line and line.startswith("http"):
                title = editor.youtube_title(line)
                line = f"{title} | {line}" if title else line
            out.append(line)
        return "\n".join(out)

    async def _ai_sources(form) -> dict:
        """Your own book or files for an AI course: uploaded ones are kept in a draft folder until the course is saved,
        a folder or PDF on this device stays where it is. Returns {"draft", "path", "folder", "names"}."""
        import secrets
        draft = str(form.get("src_draft", "")).strip()
        path = str(form.get("src_path", "")).strip().strip('"')
        ups = [u for u in form.getlist("src_files") if getattr(u, "filename", "")]
        if ups:
            draft = secrets.token_hex(8)
            root = _drafts() / draft
            root.mkdir(parents=True)
            for up in ups[:200]:
                name = re.sub(r'[<>:"|?*\x00-\x1f/\\]', "_", up.filename.replace("\\", "/").rsplit("/", 1)[-1]).strip(". ")
                if not name:
                    continue
                with open(root / name, "wb") as out:
                    while chunk := await up.read(4 * 1024 * 1024):
                        out.write(chunk)
            path = ""
        if draft and re.fullmatch(r"[0-9a-f]{16}", draft) and (_drafts() / draft).is_dir():
            folder = _drafts() / draft
            return {"draft": draft, "path": "", "folder": folder,
                    "names": sorted(p.name for p in folder.iterdir() if p.is_file() and _media_kind(p.name))}
        if path:
            p = Path(path).expanduser()
            if p.is_file() and _media_kind(p.name):
                return {"draft": "", "path": str(p), "folder": p.parent, "names": [p.name]}
            if p.is_dir():
                try:
                    names = sorted(organize.all_files(p))
                except CourseError:
                    names = []
                return {"draft": "", "path": str(p), "folder": p, "names": names[:200]}
        return {"draft": "", "path": "", "folder": None, "names": []}

    async def ai_page(request: Request):
        ctx: dict = {"step": 1, "form": {}}
        if request.method == "POST":
            form = await request.form()
            action = form.get("action")
            ctx["form"] = {k: v for k, v in form.items() if isinstance(v, str)}
            src = await _ai_sources(form)
            ctx["src"] = src
            if action == "auto":
                from starlette.concurrency import run_in_threadpool
                prompt = str(form.get("prompt", ""))
                try:
                    reply = await run_in_threadpool(integrations.ask_ai, V, prompt)
                except RuntimeError as e:
                    ctx.update(step=2, prompt=prompt, ai_error=str(e))
                    return page("ai.html", request, ai=integrations.ai_settings(V), providers=integrations.PROVIDERS, **ctx)
                action, form = "check", {"reply": reply}
                ctx["form"] = {}
            if action == "prompt":
                extra = {k: str(form.get(k, "")) for k in ("book_title", "book_author", "chapters", "material", "exam",
                                                           "playlist", "videos", "course_name", "platform",
                                                           "course_outline", "project")}
                if form.get("source") == "playlist" and extra["videos"].strip() and form.get("fetch_titles"):
                    # Fill in missing video titles from YouTube (only because you ticked the box: this goes online).
                    from starlette.concurrency import run_in_threadpool
                    extra["videos"] = await run_in_threadpool(_titled_videos, extra["videos"])
                described = organize.describe_sources(src["folder"], src["names"]) if src["folder"] else []
                ctx["prompt"] = ai.build_prompt(str(form.get("topic", "")), str(form.get("level", "beginner")),
                                                int(form.get("weeks") or 4), int(form.get("hours") or 3),
                                                str(form.get("language", "English")), str(form.get("notes", "")),
                                                source=str(form.get("source", "topic")), sources=described, **extra)
                ctx["src_books"] = [d for d in described if d.get("toc") is not None]
                ctx["step"] = 2
            elif action in ("check", "save"):
                text = strip_fences(str(form.get("reply", "")))
                ctx["step"] = 3
                ctx["reply"] = form.get("reply", "")
                try:
                    course = load_course({"course.yaml": text})
                except CourseError as e:
                    ctx["problems"] = e.problems
                else:
                    if action == "save":
                        if V.get_course(course.id):
                            course.id = f"{course.id}-{now_utc()[:10]}"
                        books = [n for n in src["names"] if n.lower().endswith(".pdf") and any(
                            str(les.get("media", "")).startswith(n + "#") for m in course.modules for les in m["lessons"])]
                        if books:
                            course.extra["book"] = books[0]  # shared courses never carry the book itself
                        V.install_course(course)
                        if src["draft"]:  # your uploaded files become the course's own files
                            import shutil
                            target = V.media_dir(course.id)
                            target.mkdir(parents=True, exist_ok=True)
                            for f in src["folder"].iterdir():
                                shutil.move(str(f), str(target / f.name))
                            shutil.rmtree(src["folder"], ignore_errors=True)
                        elif src["path"]:
                            V.set_media_root(course.id, str(src["folder"]))
                        return go("/courses", ok=f"Saved “{course.title}”. It's ready to start.")
                    ctx["preview"] = course
        return page("ai.html", request, ai=integrations.ai_settings(V), providers=integrations.PROVIDERS, **ctx)

    # ---- learning ----------------------------------------------------------------
    async def course_overview(request: Request):
        j = journey_or_404(request.path_params["jid"])
        if not j:
            return go("/", err="That course wasn't found.")
        course = V.get_course(j["course_id"])
        book = _book_state(course) if course else None
        missing = V.missing_media(course) if course else []
        if book:  # the book has its own box; the general "where are the files" box is for the rest
            missing = [m for m in missing if m != book["name"]]
        on_rm = roadmaps.on_roadmaps(V.home, course.id) if course else []
        return page("course.html", request, j=j, prog=V.progress(j["id"]), book=book, on_rm=on_rm,
                    parts=lesson_parts(V.get_course(j["course_id"])) if V.get_course(j["course_id"]) else {},
                    note_count=len(V.notes(j["course_id"])),
                    missing=missing,
                    media_root=V.media_root(j["course_id"]) if course else None,
                    offline=offline.status(V, course) if course and offline.course_videos(course) else None,
                    qualities=offline.QUALITIES, has_ffmpeg=bool(shutil.which("ffmpeg")),
                    quality=(V._meta(f"ytdlp_quality:{course.id}", "") or V._meta("ytdlp_quality", "720") or "720") if course else "720")

    def _module_state(prog: dict, module_id: str) -> dict | None:
        return next((m for m in prog["modules"] if m["id"] == module_id), None)

    def _module_done(jid: str, mid: str) -> bool:
        m = _module_state(V.progress(jid), mid)
        return bool(m and m["status"] == "done")

    async def lesson(request: Request):
        j = journey_or_404(request.path_params["jid"])
        if not j:
            return go("/", err="That course wasn't found.")
        course = V.get_course(j["course_id"])
        found = course.find_lesson(request.path_params["lid"])
        if not found:
            return go(f"/learn/{j['id']}", err="That lesson wasn't found.")
        module, les = found
        prog = V.progress(j["id"])
        mstate = _module_state(prog, module["id"])
        if mstate["status"] == "locked":
            return go(f"/learn/{j['id']}", err="Finish the module before this one first.")
        mini = request.query_params.get("mini") == "1"  # the pop-out window: just this lesson's video and the timer
        if not mini:
            V.add_event(j["id"], "lesson_opened", {"lesson": les["id"]})
        idx = [x["id"] for x in module["lessons"]].index(les["id"])
        lstate = mstate["lessons"][idx]
        nxt = module["lessons"][idx + 1]["id"] if idx + 1 < len(module["lessons"]) else None
        prv = module["lessons"][idx - 1]["id"] if idx > 0 else None
        return page("mini.html" if mini else "lesson.html", request, j=j, course=course, module=module, mstate=mstate, lesson=les,
                    lstate=lstate, html=media_mod.lesson_html(course.id, les, md.render(_drop_title(les["content"], les["title"])),
                                                       _course_files_view(course.id), gettext),
                    next_id=nxt, prev_id=prv, notes=V.notes(course.id, les["id"]),
                    has_answers=course.has_answers, prog=prog,
                    codenote=_codenote_state() if codenote.has_code(les.get("content") or "") else None)

    # ---- Progress for long buttons (v1.31.2, progress.py) ---------------------------------------------------------
    def _progress_token(form) -> str:
        t = str(form.get("progress", "") or "")
        return t if re.fullmatch(r"[A-Za-z0-9]{6,40}", t) else ""

    async def progress_json(request: Request):
        return JSONResponse(progress.get(str(request.query_params.get("t", ""))), headers={"Cache-Control": "no-store"})

    # ---- Works with CodeNote (v1.31): "Practice in CodeNote" ------------------------------------------------------
    def _codenote_state() -> dict:
        """Whether to show the button now. On Android the app shell checks, so the button starts hidden and the
        page's script shows it when the shell says CodeNote is there (spec §8)."""
        android = updater.install_kind() == "android"
        return {"on": (not android) and codenote.available_now(), "shell": "android" if android else
                ("window" if codenote.SHELL["kind"] == "window" else "")}

    async def codenote_status(request: Request):
        from starlette.concurrency import run_in_threadpool
        if updater.install_kind() == "android":
            return JSONResponse({"available": None, "shell": "android"})
        fresh = request.query_params.get("fresh") == "1"
        on = await run_in_threadpool(codenote.available, fresh)
        return JSONResponse({"available": on, "shell": codenote.SHELL["kind"]}, headers={"Cache-Control": "no-store"})

    def _codenote_payload(form) -> dict | None:
        c = V.get_course(str(form.get("course", "")))
        if not c:
            return None
        task = None
        if form.get("task"):
            found = c.find_requirement(str(form.get("task")))
            if not found or found[1]["type"] != "practical":
                return None
            module, task = found
            les = codenote.task_lesson(module)
        else:
            found = c.find_lesson(str(form.get("lesson", "")))
            if not found:
                return None
            module, les = found
        return codenote.payload(c, module, les, task) if les else None

    async def codenote_open(request: Request):
        """Practice in CodeNote: make the link (spec §1-2). On a computer inPace opens it here; on Android the
        app shell does. A lesson too long for a link comes as a .md file instead (spec §3)."""
        form = await request.form()
        data = _codenote_payload(form)
        if not data:
            return JSONResponse({"ok": False, "message": gettext("That lesson wasn't found.")}, status_code=404)
        link = codenote.link(data)
        if len(link) > codenote.LINK_LIMIT:
            q = urlencode({k: str(form.get(k, "")) for k in ("course", "lesson", "task") if form.get(k)})
            return JSONResponse({"ok": True, "file": f"/codenote/lesson.md?{q}",
                                 "message": gettext("This lesson is long, so it comes as a file: open it in CodeNote.")})
        web = codenote.web_link(data)
        if updater.install_kind() == "android":
            return JSONResponse({"ok": True, "link": link, "web": web})
        from starlette.concurrency import run_in_threadpool
        how = await run_in_threadpool(codenote.open_on_computer, link, web)
        return JSONResponse({"ok": bool(how), "opened": how,
                             "message": "" if how else gettext("inPace couldn't open CodeNote.")})

    async def codenote_file(request: Request):
        data = _codenote_payload(request.query_params)
        if not data:
            return Response("Not found", status_code=404)
        name = re.sub(r"[^\w .()-]+", "", data["title"], flags=re.UNICODE).strip()[:80] or "lesson"
        return download(codenote.lesson_file(data).encode("utf-8"), f"{name}.md", "text/markdown; charset=utf-8")

    async def module_page(request: Request):
        j = journey_or_404(request.path_params["jid"])
        if not j:
            return go("/", err="That course wasn't found.")
        course = V.get_course(j["course_id"])
        module = next((m for m in course.modules if m["id"] == request.path_params["mid"]), None)
        if not module:
            return go(f"/learn/{j['id']}", err="That module wasn't found.")
        prog = V.progress(j["id"])
        mstate = _module_state(prog, module["id"])
        if mstate["status"] == "locked":
            return go(f"/learn/{j['id']}", err="Finish the module before this one first.")
        exams = [x for x in checks.my_exams(V, j["id"]) if course.find_requirement(x["exam"]["req"]) and
                 course.find_requirement(x["exam"]["req"])[0]["id"] == module["id"]]
        # Where to go once this module is done: the first lesson left in the next module.
        after, idx = None, [m["id"] for m in prog["modules"]].index(module["id"])
        for m in prog["modules"][idx + 1:]:
            if m["status"] == "locked":
                break
            left = lesson_ahead(m["lessons"])
            if left or m["status"] != "done":
                after = {"title": m["title"],
                         "url": f"/learn/{j['id']}/lesson/{left['id']}" if left else f"/learn/{j['id']}/module/{m['id']}"}
                break
        return page("module.html", request, j=j, course=course, module=module, mstate=mstate,
                    has_answers=course.has_answers, exams=exams, after=after, finished=prog["finished"],
                    codenote=_codenote_state() if codenote.task_lesson(module) else None)

    async def take_exam(request: Request):
        j = journey_or_404(request.path_params["jid"])
        exam = checks.get_my_exam(V, request.path_params["eid"]) if j else None
        if not exam or exam["journey"] != j["id"]:
            return go("/", err="That exam wasn't found.")
        course = V.get_course(j["course_id"])
        found = course.find_requirement(exam["req"])
        module = found[0] if found else {"id": "", "title": exam["task"], "lessons": []}
        checker_name = display_name(V.person(exam["checker"]["id"]))
        if any(e["type"] == "exam_taken" and e["data"]["exam"] == exam["id"] for e in V.events(j["id"])):
            return go(f"/learn/{j['id']}/module/{module['id']}", err="You already took this exam.")
        if request.method == "POST":
            form = await request.form()
            answers = {q["id"]: str(form.get(q["id"], "")) for q in exam["questions"]}
            V.add_event(j["id"], "exam_taken", {"exam": exam["id"], "req": exam["req"], "task": exam["task"],
                                                "checker": exam["checker"]["id"], "answers": answers})
            return go(f"/learn/{j['id']}/exam/{exam['id']}/done", yay="exam")
        return page("quiz.html", request, j=j, module=module, req={"pass": exam["pass"]}, exam=exam["questions"],
                    seed="", verified=True, checker_name=checker_name, dispose=f"/learn/{j['id']}/module/{module['id']}")

    async def exam_done(request: Request):
        j = journey_or_404(request.path_params["jid"])
        exam = checks.get_my_exam(V, request.path_params["eid"]) if j else None
        if not exam or exam["journey"] != j["id"]:
            return go("/", err="That exam wasn't found.")
        found = V.get_course(j["course_id"]).find_requirement(exam["req"])
        module = found[0] if found else {"id": "", "title": exam["task"], "lessons": []}
        checker_name = display_name(V.person(exam["checker"]["id"]))
        back = f"/learn/{j['id']}/module/{module['id']}" if module["id"] else f"/learn/{j['id']}"
        return page("quiz_result.html", request, j=j, module=module, verified=True, checker_name=checker_name, dispose=back)

    async def journey_action(request: Request):
        jid, action = request.path_params["jid"], request.path_params["action"]
        if not journey_or_404(jid):
            return go("/", err="That course wasn't found.")
        form = await request.form()
        back = str(form.get("back") or "/")
        if not back.startswith("/"):
            back = "/"
        evs = V.events(jid)
        if action == "commit":
            n = max(1, min(int(form.get("per_week") or 2), 14))
            V.add_event(jid, "commitment_set", {"per_week": n})
            return go(back, ok=f"Your goal: {n} milestone{'s' if n > 1 else ''} a week. Your checker will see it.", yay="goal")
        if action == "pause" and not pace.is_paused(evs):
            V.add_event(jid, "pause_started", {"reason": str(form.get("reason", "")).strip()[:200]})
            return go(back, ok="You're on a break. Weeks on a break don't count as missed.")
        if action == "resume" and pace.is_paused(evs):
            V.add_event(jid, "pause_ended", {})
            return go(back, yay="back")
        if action == "reflect":
            data = {k: str(form.get(k, "")).strip()[:2000] for k in ("learned", "hard", "next")}
            if not any(data.values()):
                return go(back, err="Write at least one answer.")
            V.add_event(jid, "reflection_saved", data)
            return go(back, ok="Reflection saved.")
        return go(back)

    async def practice(request: Request):
        j = journey_or_404(request.path_params["jid"])
        if not j:
            return go("/", err="That course wasn't found.")
        course = V.get_course(j["course_id"])
        if request.method == "GET":
            due = pace.due_cards(V, course.id)[:10]
            if not due:
                return go("/", ok="Nothing to review today. Come back tomorrow.")
            seed = new_seed()
            exam = build_exam(course, due, seed)
            return page("quiz.html", request, j=j, course=course, module={"id": "", "title": "Review"},
                        req={"pass": 0}, exam=exam, seed=seed, review=True, qids=",".join(due), dispose="/")
        form = await request.form()
        seed, qids = str(form.get("seed", "")), [q for q in str(form.get("qids", "")).split(",") if q in course.questions]
        exam = build_exam(course, qids, seed)
        answers = {it["id"]: str(form.get(it["id"], "")) for it in exam}
        result = grade(course, exam, answers)
        pace.update_cards(V, course.id, {it["id"]: d["ok"] for it, d in zip(exam, result["details"])})
        V.add_event(j["id"], "review_done", {"count": result["total"], "right": result["score"],
                                             "seed": seed, "qids": qids, "answers": answers})
        return go(f"/learn/{j['id']}/practice/result")

    async def practice_result(request: Request):
        j = journey_or_404(request.path_params["jid"])
        if not j:
            return go("/", err="That course wasn't found.")
        course = V.get_course(j["course_id"])
        last = next((e for e in reversed(V.events(j["id"])) if e["type"] == "review_done" and e["data"].get("seed")), None)
        if not last:
            return RedirectResponse("/", status_code=303)
        qids = [q for q in last["data"].get("qids", []) if q in course.questions]
        result = grade(course, build_exam(course, qids, last["data"]["seed"]), last["data"].get("answers", {}))
        return page("quiz_result.html", request, j=j, module={"id": "", "title": "Review", "lessons": []},
                    req={"pass": 0, "id": ""}, result=result, passed=True, review=True, dispose="/")

    async def lesson_done(request: Request):
        jid, lid = request.path_params["jid"], request.path_params["lid"]
        j = journey_or_404(jid)
        course = V.get_course(j["course_id"]) if j else None
        found = course.find_lesson(lid) if course else None
        if not found:
            return go("/", err="That lesson wasn't found.")
        was_done = _module_done(jid, found[0]["id"])
        if not any(e["type"] == "lesson_done" and e["data"]["lesson"] == lid for e in V.events(jid)):
            V.add_event(jid, "lesson_done", {"lesson": lid, "title": found[1]["title"]})
        if not was_done and _module_done(jid, found[0]["id"]):
            return go(f"/learn/{jid}/module/{found[0]['id']}", yay="module")
        form = await request.form()
        target = form.get("next")
        if target:
            return go(f"/learn/{jid}/lesson/{target}", yay="lesson")
        return go(f"/learn/{jid}/module/{found[0]['id']}", ok="All lessons read. Now the tasks.")

    # ---- notes on lessons (v1.25): private, kept in vault.db ------------------
    def _safe_back(value, fallback: str) -> str:
        back = str(value or "")
        return back if back.startswith("/") and not back.startswith("//") else fallback

    def _note_html(n: dict, back: str, jump: bool = True) -> str:
        CURRENT["lang"] = V._meta("lang", "en") or "en"
        return env.get_template("_note.html").render(n=n, back=back, jump=jump)

    async def add_note(request: Request):
        jid, lid = request.path_params["jid"], request.path_params["lid"]
        j = journey_or_404(jid)
        course = V.get_course(j["course_id"]) if j else None
        if not course or not course.find_lesson(lid):
            return go("/", err="That lesson wasn't found.")
        form = await request.form()
        back = f"/learn/{jid}/lesson/{lid}"
        quick = request.headers.get("x-inpace-fetch") == "1"  # the "Take a note" button on selected text
        try:
            n = V.add_note(course.id, lid, jid, str(form.get("quote", "")), str(form.get("text", "")))
        except ValueError as e:
            return Response(gettext(str(e)), status_code=400) if quick else go(back + "#notes", err=str(e))
        if quick:
            return HTMLResponse(_note_html(n, back))
        return go(f"{back}#note-{n['id']}", ok="Note saved.")

    async def edit_note(request: Request):
        n = V.note(request.path_params["nid"])
        form = await request.form()
        back = _safe_back(form.get("back"), "/")
        if not n:
            return go(back, err="That note wasn't found.")
        if form.get("delete"):
            V.delete_note(n["id"])
            return go(back.split("#")[0] + "#notes", ok="Note deleted.")
        try:
            V.edit_note(n["id"], str(form.get("text", "")))
        except ValueError as e:
            return go(back, err=str(e))
        return go(back.split("#")[0] + f"#note-{n['id']}", ok="Note saved.")

    def _notes_by_lesson(j: dict, course) -> list[dict]:
        """All notes on a course, in the course's own order: module, lesson, then oldest first."""
        mine = V.notes(course.id)
        out = []
        for m in course.modules:
            for les in m["lessons"]:
                here = [n for n in mine if n["lesson"] == les["id"]]
                if here:
                    out.append({"module": m["title"], "lesson": les, "notes": here})
        known = {les["id"] for m in course.modules for les in m["lessons"]}
        lost = [n for n in mine if n["lesson"] not in known]  # the course changed and that lesson is gone
        if lost:
            out.append({"module": "", "lesson": {"id": "", "title": gettext("Lessons no longer in the course")}, "notes": lost})
        return out

    async def notes_page(request: Request):
        j = journey_or_404(request.path_params["jid"])
        if not j:
            return go("/", err="That course wasn't found.")
        course = V.get_course(j["course_id"])
        return page("notes.html", request, j=j, course=course, groups=_notes_by_lesson(j, course))

    async def notes_file(request: Request):
        """Your notes on a course as a Markdown file, to keep or print."""
        j = journey_or_404(request.path_params["jid"])
        if not j:
            return go("/", err="That course wasn't found.")
        course = V.get_course(j["course_id"])
        lines = [f"# {course.title}", "", gettext("My notes, from inPace."), ""]
        last_module = None
        for g in _notes_by_lesson(j, course):
            if g["module"] and g["module"] != last_module:
                lines += [f"## {g['module']}", ""]
                last_module = g["module"]
            lines += [f"### {g['lesson']['title']}", ""]
            for n in g["notes"]:
                if n["quote"]:
                    lines += ["> " + n["quote"], ""]
                if n["text"]:
                    lines += [n["text"], ""]
                lines += [f"*{n['updated_at'][:10]}*", ""]
        name = f"{course.title} - {gettext('notes')}.md"
        return download("\n".join(lines).encode("utf-8"), name, "text/markdown; charset=utf-8")

    async def _req_ctx(request: Request):
        j = journey_or_404(request.path_params["jid"])
        if not j:
            return None, None, None, None
        course = V.get_course(j["course_id"])
        found = course.find_requirement(request.path_params["rid"])
        if not found:
            return j, course, None, None
        return j, course, found[0], found[1]

    async def add_evidence(request: Request):
        j, course, module, req = await _req_ctx(request)
        if not req:
            return go("/", err="That task wasn't found.")
        form = await request.form()
        up = form.get("file")
        back = f"/learn/{j['id']}/module/{module['id']}#task-{req['id']}"
        if not up or not getattr(up, "filename", ""):
            return go(back, err="Choose a file first.")
        data = await up.read()
        if not data:
            return go(back, err="That file is empty.")
        if len(data) > 100 * 1024 * 1024:
            return go(back, err="That file is over 100 MB. Try a smaller file or a screenshot.")
        was_done = _module_done(j["id"], module["id"])
        V.save_evidence(j["id"], req["id"], up.filename, data, task=req["prompt"])
        if not was_done and _module_done(j["id"], module["id"]):
            return go(back, yay="module")
        return go(back, ok=f"Saved “{up.filename}” as your work.")

    async def add_git(request: Request):
        j, course, module, req = await _req_ctx(request)
        if not req:
            return go("/", err="That task wasn't found.")
        form = await request.form()
        back = f"/learn/{j['id']}/module/{module['id']}#task-{req['id']}"
        try:
            name, data = integrations.git_summary(str(form.get("folder", "")))
        except RuntimeError as e:
            return go(back, err=str(e))
        V.save_evidence(j["id"], req["id"], name, data, task=req["prompt"])
        return go(back, ok="Saved your Git project's history as proof.")

    async def save_writeup(request: Request):
        j, course, module, req = await _req_ctx(request)
        if not req:
            return go("/", err="That task wasn't found.")
        form = await request.form()
        text = str(form.get("text", "")).strip()
        words = len(text.split())
        back = f"/learn/{j['id']}/module/{module['id']}#task-{req['id']}"
        if not text:
            return go(back, err="Write something first.")
        was_done = _module_done(j["id"], module["id"])
        V.add_event(j["id"], "writeup_saved", {"req": req["id"], "task": req["prompt"], "text": text, "words": words})
        if not was_done and _module_done(j["id"], module["id"]):
            return go(back, yay="module")
        need = req.get("min_words", 40)
        if words < need:
            return go(back, ok=f"Saved. You have {words} words; this needs at least {need} to count.")
        return go(back, ok="Saved your explanation.")

    async def quiz(request: Request):
        j, course, module, req = await _req_ctx(request)
        if not req or req["type"] != "quiz":
            return go("/", err="That quiz wasn't found.")
        if request.method == "GET":
            seed = new_seed()
            try:
                exam = build_exam(course, req["questions"], seed)
            except NoAnswers:
                return go(f"/learn/{j['id']}/module/{module['id']}",
                          err="This course came without answers, so practice quizzes aren't available. "
                              "Ask whoever shared it for the version with answers.")
            return page("quiz.html", request, j=j, course=course, module=module, req=req, exam=exam, seed=seed,
                        dispose=f"/learn/{j['id']}/module/{module['id']}")
        form = await request.form()
        seed = str(form.get("seed", ""))
        exam = build_exam(course, req["questions"], seed)
        picked = {item["id"]: str(form.get(item["id"], "")) for item in exam}
        result = grade(course, exam, picked)
        passed = result["percent"] >= req.get("pass", 70)
        pace.update_cards(V, course.id, {d_id: d["ok"] for d_id, d in zip([it["id"] for it in exam], result["details"])})
        V.add_event(j["id"], "quiz_taken", {"req": req["id"], "task": module["title"], "mode": "practice",
                                            "seed": seed, "answers": picked,
                                            "score": result["score"], "total": result["total"],
                                            "percent": result["percent"], "passed": passed})
        done_now = _module_done(j["id"], module["id"])
        # Show the result on its own page (post, then redirect), so Back or reload never sends the answers again.
        return go(f"/learn/{j['id']}/task/{req['id']}/quiz/result",
                  yay=("module" if done_now else "quiz") if passed else None)

    async def quiz_result(request: Request):
        """Your last practice try of this quiz, worked out again from what was saved."""
        j, course, module, req = await _req_ctx(request)
        if not req or req["type"] != "quiz":
            return go("/", err="That quiz wasn't found.")
        back = f"/learn/{j['id']}/module/{module['id']}"
        last = next((e for e in reversed(V.events(j["id"])) if e["type"] == "quiz_taken"
                     and e["data"].get("req") == req["id"] and e["data"].get("seed")), None)
        if not last:
            return RedirectResponse(back, status_code=303)
        exam = build_exam(course, req["questions"], last["data"]["seed"])
        result = grade(course, exam, last["data"].get("answers", {}))
        passed = result["percent"] >= req.get("pass", 70)
        return page("quiz_result.html", request, j=j, module=module, req=req, result=result, passed=passed,
                    dispose=back)

    # ---- milestones -----------------------------------------------------------
    async def milestones(request: Request):
        cards = [journey_card(j) for j in V.journeys()]
        for c in cards:
            c["send"] = None
            if c["milestones"]:
                jid = c["journey"]["id"]
                since = exchange.checkers_have(V, jid)
                sh = exchange.share_links(say("My progress on inPace 🐢 Tap the link to check it:"),
                                          exchange.make_progress_file(V, jid, since), say("My progress on inPace"))
                if sh["fits"]:
                    c["send"] = sh
        return page("milestones.html", request, cards=cards, checkers=V.my_checkers())

    async def save_milestone(request: Request):
        jid = request.path_params["jid"]
        if not journey_or_404(jid):
            return go("/milestones", err="That course wasn't found.")
        if not has_new(jid):
            return go("/milestones", err="Nothing new to save yet. Finish a lesson or task first.")
        m = V.create_milestone(jid)
        return go("/milestones", yay="milestone")

    async def export_progress(request: Request):
        jid = request.path_params["jid"]
        j = journey_or_404(jid)
        if not j:
            return go("/milestones", err="That course wasn't found.")
        if not V.milestones(jid):
            return go("/milestones", err="Save a milestone first.")
        data = exchange.make_progress_file(V, jid)
        title = data["journey"]["course"]["title"]
        return download(exchange.dump(data), f"{V.me['name']} - {title} - {now_utc()[:10]}.inpace", "application/json")

    async def file_pack(request: Request):
        jid = request.path_params["jid"]
        try:
            data = checks.make_file_pack(V, jid)
        except exchange.FileProblem as e:
            return go("/milestones", err=str(e))
        V._set_meta(f"pack:{jid}", now_utc())
        return download(data, f"{V.me['name']} - requested files - {now_utc()[:10]}.zip", "application/zip")

    async def learning_record(request: Request):
        jid = request.path_params["jid"]
        if not journey_or_404(jid) or not V.milestones(jid):
            return go("/milestones", err="Save a milestone first.")
        j = V.journey(jid)
        title = V.get_course(j["course_id"]).title
        CURRENT["lang"] = V._meta("lang", "en") or "en"
        return download(record.build_record(V, jid, gettext, CURRENT["lang"], MONTHS[CURRENT["lang"]]).encode("utf-8"), f"{V.me['name']} - {title} - learning record.html",
                        "text/html")

    # ---- races ------------------------------------------------------------------
    async def races_page(request: Request):
        rows = []
        for r in races.my_races(V):
            b = races.board(V, r["id"])
            rows.append({"r": r, "b": b})
        return page("races.html", request, rows=rows, kinds=races.KINDS, journeys=[
            {**j, "title": (V.get_course(j["course_id"]).title if V.get_course(j["course_id"]) else j["course_id"])}
            for j in V.journeys()])

    async def race_new(request: Request):
        form = await request.form()
        try:
            race = races.create_race(V, str(form.get("name", "")), str(form.get("kind", "")), int(form.get("days") or 14))
            races.join_race(V, race, str(form.get("journey", "")), str(form.get("folder", "")))
        except (ValueError, exchange.FileProblem) as e:
            return go("/races", err=str(e))
        return go(f"/races/{race['id']}", ok="Race created. Send the invite to your friends.")

    async def race_join(request: Request):
        form = await request.form()
        import json as _json
        try:
            race = _json.loads(str(form.get("race", "")))
            races.join_race(V, race, str(form.get("journey", "")), str(form.get("folder", "")))
        except (ValueError, exchange.FileProblem) as e:
            return go("/races", err=str(e))
        return go(f"/races/{race['id']}", ok=f"You joined “{race['name']}”.")

    async def race_page(request: Request):
        rid = request.path_params["rid"]
        r = races.get_race(V, rid)
        if not r:
            return go("/races", err="That race wasn't found.")
        sync_msg = None
        if r["folder"]:
            try:
                n = races.sync_folder(V, rid)
                sync_msg = f"Shared folder synced · {n} other racer{'s' if n != 1 else ''}"
            except exchange.FileProblem as e:
                sync_msg = str(e)
        b = races.board(V, rid)
        invite = exchange.share_links(say("Join my race on inPace 🐢 Tap the link:"),
                                      races.get_race(V, rid)["race"], say("Join my race on inPace"))
        try:
            update = exchange.share_links(say("My inPace race update. Tap the link:"),
                                          races.make_update(V, rid), say("My inPace race update"))
        except Exception:
            update = None
        return page("race.html", request, b=b, rid=rid, sync_msg=sync_msg, cheers=races.CHEERS,
                    invite=invite, update=update)

    async def race_action(request: Request):
        rid, action = request.path_params["rid"], request.path_params["action"]
        r = races.get_race(V, rid)
        if not r:
            return go("/races", err="That race wasn't found.")
        if action == "invite":
            return download(exchange.dump(r["race"]), f"Race invite - {r['race']['name']}.inpace", "application/json")
        if action == "update":
            return download(exchange.dump(races.make_update(V, rid)),
                            f"Race update - {V.me['name']} - {now_utc()[:10]}.inpace", "application/json")
        form = await request.form()
        if action == "cheer":
            races.send_cheer(V, rid, str(form.get("to", "")), str(form.get("text", "")))
            return go(f"/races/{rid}", ok="Cheer added. It goes out with your next update.")
        if action == "folder":
            V.db.execute("UPDATE races SET folder=? WHERE id=?", (str(form.get("folder", "")).strip(), rid))
            V.db.commit()
            return go(f"/races/{rid}", ok="Saved.")
        if action == "leave":
            races.leave_race(V, rid)
            return go("/races", ok="You left the race.")
        return go(f"/races/{rid}")

    # ---- course editor ---------------------------------------------------------
    async def edit_new(request: Request):
        if request.method == "POST":
            f = await request.form()
            try:
                links = str(f.get("links", "")) if f.get("start") == "links" else ""
                if f.get("start") == "links" and not links.strip():
                    raise CourseError(["Paste at least one link or file path."])
                from starlette.concurrency import run_in_threadpool
                c = await run_in_threadpool(
                    editor.new_course, V, str(f.get("title", "")), str(f.get("description", "")),
                    str(f.get("module_title", "")), str(f.get("lesson_title", "")), str(f.get("content", "")),
                    links, str(f.get("language", "en")), bool(f.get("fetch_titles")))
            except CourseError as e:
                return page("edit_new.html", request, problems=e.problems, form=dict(f))
            return go(f"/edit/{c.id}", ok="Course created. Add more lessons, tasks and questions.")
        return page("edit_new.html", request, form={})

    async def edit_course(request: Request):
        cid = request.path_params["cid"]
        c = V.get_course(cid)
        if not c:
            return go("/courses", err="That course isn't installed.")
        if request.method == "POST":
            f = await request.form()
            data = {k: str(v) for k, v in f.items()}
            data["questions"] = [str(x) for x in f.getlist("questions")]
            try:
                if data.get("action") == "undo":
                    editor.undo(V, cid)
                    return go(f"/edit/{cid}", ok="Undone. The course is back to how it was before your last change.")
                if data.get("action") in ("add_links", "add_lesson") and data.get("fetch_titles"):
                    from starlette.concurrency import run_in_threadpool
                    await run_in_threadpool(editor.edit, V, cid, data["action"], data)
                else:
                    editor.edit(V, cid, data.get("action", ""), data)
            except CourseError as e:
                return page("edit_course.html", request, c=c, problems=e.problems, started=bool(V.journey_for_course(cid)),
                            can_undo=editor.can_undo(V, cid), journey=V.journey_for_course(cid))
            anchor = f"#{data['module']}" if data.get("module") else ""
            return go(f"/edit/{cid}{anchor}", ok="Saved.")
        return page("edit_course.html", request, c=c, started=bool(V.journey_for_course(cid)),
                    can_undo=editor.can_undo(V, cid), journey=V.journey_for_course(cid))

    async def edit_yaml(request: Request):
        cid = request.path_params["cid"]
        c = V.get_course(cid)
        if not c:
            return go("/courses", err="That course isn't installed.")
        if request.method == "POST":
            text = str((await request.form()).get("yaml", ""))
            try:
                editor.save_yaml(V, cid, text)
            except CourseError as e:
                return page("edit_yaml.html", request, c=c, text=text, problems=e.problems)
            return go(f"/edit/{cid}", ok="Saved.")
        return page("edit_yaml.html", request, c=c, text=editor.course_to_yaml(c))

    async def lesson_preview(request: Request):
        """What the lesson will look like, for the Preview tab in the lesson editor."""
        cid = request.path_params["cid"]
        f = await request.form()
        les = {"title": str(f.get("title", "")), "content": str(f.get("content", "")), "media": str(f.get("media", "")).strip()}
        body = md.render(_drop_title(les["content"], les["title"]))
        return HTMLResponse(media_mod.lesson_html(cid, les, body, _course_files_view(cid), gettext))

    async def edit_lesson_media(request: Request):
        cid, lid = request.path_params["cid"], request.path_params["lid"]
        c = V.get_course(cid)
        if not c or not c.find_lesson(lid):
            return go(f"/edit/{cid}", err="That lesson wasn't found.")
        form = await request.form()
        back = f"/edit/{cid}/lesson/{lid}"
        label = str(form.get("label", "")).strip()
        ref = (str(form.get("ref", "")).strip() or str(form.get("ref_path", "")).strip()).strip('"')
        up = form.get("file")
        if up is not None and getattr(up, "filename", ""):
            # A small file added here is kept with the course, so it travels when you share it with files.
            name = re.sub(r"[^\w .()-]+", "", Path(up.filename).name, flags=re.UNICODE).strip() or "file"
            dest = V.media_dir(cid) / "media"
            dest.mkdir(parents=True, exist_ok=True)
            import shutil
            with open(dest / name, "wb") as out:
                shutil.copyfileobj(up.file, out, 1024 * 1024)
            ref = f"media/{name}"
        if not ref:
            return go(back, err="Add a file, a link or a path first.")
        from .course import is_url, local_ref, media_kind
        if not is_url(ref) and not (local_ref(ref) and media_kind(ref)):
            return go(back, err="That isn't a video, audio, web page, PDF or picture inPace can show.")
        try:
            editor.edit(V, cid, "add_media", {"lesson": lid, "ref": ref, "label": label})
        except CourseError as e:
            return go(back, err=e.problems[0])
        return go(back, ok="Added to the lesson.")

    async def edit_course_image(request: Request):
        """Add, change or remove the course's cover picture. It's saved with the course's own files."""
        cid = request.path_params["cid"]
        c = V.get_course(cid)
        if not c:
            return go("/courses", err="That course isn't installed.")
        form = await request.form()
        folder = V.media_dir(cid)
        if form.get("remove"):
            old = c.extra.pop("image", None)
            if old and old.startswith("cover.") and (folder / old).exists():
                (folder / old).unlink()
            editor.save(V, c)
            return go(f"/edit/{cid}", ok="Removed the picture.")
        up = form.get("image")
        if not up or not getattr(up, "filename", ""):
            return go(f"/edit/{cid}", err="Choose a picture first.")
        ext = Path(up.filename).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            return go(f"/edit/{cid}", err="Choose a JPG, PNG, WebP or GIF picture.")
        data = await up.read()
        if len(data) > 8 * 1024 * 1024:
            return go(f"/edit/{cid}", err="That picture is too big. Choose one under 8 MB.")
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("cover.*"):
            old.unlink()
        (folder / f"cover{ext}").write_bytes(data)
        c.extra["image"] = f"cover{ext}"
        editor.save(V, c)
        return go(f"/edit/{cid}", ok="Saved the picture.")

    async def edit_lesson(request: Request):
        cid, lid = request.path_params["cid"], request.path_params["lid"]
        c = V.get_course(cid)
        found = c.find_lesson(lid) if c else None
        if not found:
            return go(f"/edit/{cid}", err="That lesson wasn't found.")
        return page("edit_lesson.html", request, c=c, module=found[0], lesson=found[1])

    # ---- people ---------------------------------------------------------------
    async def people(request: Request):
        rows = []
        for p in V.people():
            rows.append({**p, "waiting": V.waiting_count(p["id"]) if p["i_check"] else 0,
                         "journeys": V.received(p["id"]) if p["i_check"] else []})
        by_course: dict[str, list] = {}
        for p in rows:
            for r in p["journeys"]:
                by_course.setdefault(r["course"], []).append({"person": p, "rec": r,
                                                              "percent": (r["data"]["milestones"][-1]["body"]["summary"]["percent"]
                                                                          if r["data"]["milestones"] else 0)})
        share = exchange.share_links(say("Add me on inPace 🐢 Tap the link:"), exchange.make_contact_card(V),
                                     say("Add me on inPace"))
        added = V.person(str(request.query_params.get("added", "")))
        return page("people.html", request, people=rows, by_course=by_course, share=share, added=added)

    async def my_card(request: Request):
        return download(exchange.dump(exchange.make_contact_card(V)), f"{V.me['name']} - contact card.inpace",
                        "application/json")

    def _their_island(d: dict) -> str:
        """Someone's island from their card or file, cleaned so only things we can draw get in."""
        snap = garden.clean_snapshot(d.get("island")) if isinstance(d, dict) else None
        return json.dumps(snap, sort_keys=True, ensure_ascii=False) if snap else ""

    def _their_turtle(d: dict) -> str:
        """Someone's turtle from their card or file, cleaned so only real turtle parts get in."""
        return json.dumps(mascot_mod.clean_avatar(d["avatar"]), sort_keys=True) if isinstance(d.get("avatar"), dict) else ""

    async def add_person(request: Request):
        form = await request.form()
        import json as _json
        try:
            card = _json.loads(str(form.get("card", "")))
            exchange.check_contact_card(card)
        except (ValueError, exchange.FileProblem):
            return go("/people", err="That contact card couldn't be read. Ask for a new one.")
        if card["id"] == V.identity.id:
            return go("/people", err="That's your own contact card.")
        rel = form.get("relationship")
        checks_me = rel in ("checks_me", "buddies")
        i_check = rel in ("i_check", "buddies")
        if not (checks_me or i_check):
            return go("/people", err="Choose how you're connected.")
        V.add_person(card["id"], card["name"], card["color"], checks_me, i_check, _their_turtle(card), _their_island(card))
        nick = str(form.get("nickname", "")).strip()
        if nick:
            p = V.person(card["id"])
            V.set_roles(card["id"], bool(p["checks_me"]), bool(p["i_check"]), nick)
        nxt = str(form.get("then", ""))
        if nxt.startswith("/review/") or nxt == "/open":
            return go(nxt, ok=f"Added {card['name']}.")
        return go(f"/people?added={card['id']}", ok=f"Added {card['name']}.")

    async def edit_person(request: Request):
        pid = request.path_params["pid"]
        form = await request.form()
        if form.get("remove"):
            V.remove_person(pid)
            return go("/people", ok="Removed.")
        V.set_roles(pid, bool(form.get("checks_me")), bool(form.get("i_check")), str(form.get("nickname", "")))
        return go("/people", ok="Saved.")

    # ---- one place to open any file ------------------------------------------
    def _unpack_media(c, zf, inside) -> None:
        """Copy a course file's videos and other files into the course's media folder (never outside it)."""
        import shutil
        if not inside:
            return
        dest = V.media_dir(c.id).resolve()
        for info, rel in inside:
            target = (dest / rel).resolve()
            try:
                target.relative_to(dest)
            except ValueError:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, 1024 * 1024)

    def _install_pack(request: Request, fileobj, fname: str, then: str | None = None):
        import shutil
        import zipfile
        try:
            zf = zipfile.ZipFile(fileobj)
            c = load_course(files_from_zip(fileobj))
        except zipfile.BadZipFile:
            return go("/open", err="This doesn't look like a course file.")
        except CourseError as e:
            return page("open.html", request, problems=e.problems, filename=fname)
        inside = media_in_zip(zf)
        existing = V.get_course(c.id)
        if existing and existing.hash != c.hash:
            return _hold_update(c, (zf, inside) if inside else None)
        c = V.install_course(c)
        _unpack_media(c, zf, inside)
        lines = [f"Added the course “{c.title}”."]
        if c.questions and not c.has_answers:
            lines.append("It came without answers, so practice quizzes are off.")
        if not inside and V.missing_media(c):
            lines.append("Its videos and other files aren't inside. Choose their folder on the course page.")
        return go(then or "/courses", ok="\n".join(lines))

    async def open_link(request: Request):
        """inPace was opened from a link (inpace://open/...). Hand the data to Open, like a pasted code."""
        body = exchange.link_body("inpace:" + str(request.query_params.get("d", "")))
        if not body:
            return go("/", err="That link is cut off or damaged. Copy the whole message again.")
        if not V.is_set_up:
            V._set_meta("pending_link", body)  # opened before setup: come back to it right after
            return go("/setup")
        V._set_meta("pending_link", "")
        return page("link.html", request, code="inpace:" + body)

    def _open_lesson_link(cid: str, lid: str):
        """A lesson link: the lesson if its course is here (and started), else the course in the library, else a
        plain message."""
        c = V.get_course(cid)
        if c:
            jid = V.journey_for_course(cid)
            if not c.find_lesson(lid):
                return go(f"/learn/{jid}" if jid else "/courses",
                          err=gettext("That lesson isn't in “{title}” anymore.").format(title=c.title))
            if jid:
                return go(f"/learn/{jid}/lesson/{quote(lid)}")
            return go("/courses", err=gettext("Start “{title}” first: the lesson is in that course.").format(title=c.title))
        if library.find(library.cached_index(V.home), cid):
            return go(f"/library/{quote(cid)}", err="That course isn't on this device yet. You can add it from the library.")
        return go("/courses", err="That lesson's course isn't on this device. Ask for the course file, then open the link again.")

    async def open_file(request: Request):
        if request.method == "GET":
            return page("open.html", request)
        form = await request.form()
        back = "/people" if form.get("from") == "people" else "/open"
        if form.get("code") is not None:
            try:
                raw = exchange.dump(exchange.from_code(str(form.get("code"))))
                fname = "code.inpace"
            except exchange.FileProblem as e:
                return go(back, err=str(e))
        else:
            up = form.get("file")
            if not up or not getattr(up, "filename", ""):
                return go("/open", err="Choose a file first.")
            fname = up.filename
            up.file.seek(0, 2)
            size = up.file.tell()
            up.file.seek(0)
            if size > 40 * 1024 * 1024 and up.file.read(2) == b"PK":
                up.file.seek(0)  # a big course pack that carries its own videos: read it from disk, not memory
                return _install_pack(request, up.file, fname)
            up.file.seek(0)
            raw = await up.read()
        if raw[:2] == b"PK" and checks.is_file_pack(raw):
            try:
                res = checks.import_file_pack(V, raw)
            except (exchange.FileProblem, KeyError, ValueError) as e:
                return go("/open", err=str(e) if isinstance(e, exchange.FileProblem) else "This file pack is damaged.")
            return go(f"/review/{res['learner']}/{res['journey']}", ok=f"Got {res['count']} file(s) from {res['name']}.")
        if raw[:2] == b"PK":  # a course pack (zip)
            import io as _io
            return _install_pack(request, _io.BytesIO(raw), fname)
        if fname.lower().endswith((".yaml", ".yml")) or not raw.lstrip()[:1] == b"{":
            # A single-file course (the all-in-one format, e.g. saved from an AI chat).
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                return go("/open", err="This file isn't text inPace can read.")
            if re.search(r"(?m)^steps:", text) and not re.search(r"(?m)^modules:", text):  # a roadmap (v1.24)
                try:
                    rm = roadmaps.parse(strip_fences(text), "link")
                except roadmaps.RoadmapError as e:
                    return page("open.html", request, problems=e.problems, filename=fname)
                return _show_roadmap(request, rm, "shared", await _library_now(),
                                     shared_json=json.dumps(roadmaps.share_data(rm, False), ensure_ascii=False))
            try:
                course = load_course({"course.yaml": strip_fences(text)})
            except CourseError as e:
                hint = []
                if any("is missing" in p and "lessons/" in p for p in e.problems):
                    hint = ["This course keeps its lessons in separate files. Put course.yaml and the lessons "
                            "folder together in a zip file, then open the zip."]
                return page("open.html", request, problems=hint + e.problems, filename=fname)
            existing = V.get_course(course.id)
            if existing and existing.hash != course.hash:
                return _hold_update(course)
            c = V.install_course(course)
            extra = "" if c.has_answers else " It has no answers, so practice quizzes are off."
            return go("/courses", ok=f"Added the course “{c.title}”.{extra}")
        try:
            data = exchange.read_inpace_file(raw)
        except exchange.FileProblem as e:
            return go("/open", err=str(e))
        kind = data["inpace"]
        try:
            if kind == "contact":
                exchange.check_contact_card(data)
                if data["id"] == V.identity.id:
                    return go("/open", err="That's your own contact card. Send it to the other person instead.")
                import json as _json
                return page("add_person.html", request, card=data, card_json=_json.dumps(data),
                            existing=V.person(data["id"]), then="/people")
            if kind == "progress":
                data = exchange.complete_progress(V, data)
                learner = data["learner"]["id"]
                if learner == V.identity.id:
                    return go("/open", err="That's your own progress file. Send it to your checker.")
                p = V.person(learner)
                if not p or not p["i_check"]:
                    import json as _json
                    card = {"id": learner, "name": data["learner"]["name"], "color": data["learner"]["color"]}
                    V.store_received(data)
                    return page("add_person.html", request, card=card, card_json=None, from_progress=True,
                                progress_json=_json.dumps(data), existing=p,
                                then=f"/review/{learner}/{data['journey']['id']}")
                V.store_received(data)
                V.update_person_extras(learner, _their_turtle(data["learner"]), _their_island(data))
                return go(f"/review/{learner}/{data['journey']['id']}")
            if kind == "lesson":  # SPEC §14: open one lesson (CodeNote's "Back to inPace")
                return _open_lesson_link(str(data.get("course", "")), str(data.get("lesson", "")))
            if kind == "library-course":
                return go("/library?show=" + quote(str(data.get("id", ""))))
            if kind == "library-roadmap":
                return go("/roadmaps/" + quote(str(data.get("id", ""))))
            if kind == "roadmap":
                try:
                    rm = roadmaps.parse(data, "link")
                except roadmaps.RoadmapError:
                    return go("/open", err="That roadmap link is damaged. Ask for it again.")
                index = await _library_now()
                have = roadmaps.get(V.home, rm["id"])
                if have and roadmaps.fingerprint(have) == roadmaps.fingerprint(rm):
                    return go(f"/roadmaps/{rm['id']}")
                return _show_roadmap(request, rm, "shared", index, shared_json=json.dumps(data, ensure_ascii=False))
            if kind == "race":
                races.check_race(data)
                if races.get_race(V, data["id"]):
                    return go(f"/races/{data['id']}")
                import json as _json
                js = [{**j, "title": V.get_course(j["course_id"]).title} for j in V.journeys() if V.get_course(j["course_id"])]
                return page("join_race.html", request, race=data, race_json=_json.dumps(data), journeys=js,
                            kinds=races.KINDS)
            if kind == "race_update":
                name = races.import_update(V, data)
                return go(f"/races/{data['race']}", ok=f"Got {name}'s race update.")
            if kind == "exam":
                res = checks.import_exam(V, data)
                return go(f"/learn/{data['journey']}/exam/{data['id']}",
                          ok=f"{res['name']} sent you a verified exam for “{res['task']}”.")
            if kind == "approval":
                res = exchange.import_approval_file(V, data)
                V.update_person_extras(data["checker"]["id"], _their_turtle(data["checker"]), _their_island(data))
                first = {"approved": "{a} approved {b} milestone(s).", "question": "{a} has a question about {b} milestone(s).",
                         "flag": "{a} flagged {b} milestone(s)."}[res["decision"]]
                lines = [first.format(a=res["name"], b=res["count"])]
                if res["note"]:
                    lines.append(f"Note: “{res['note']}”")
                if res.get("results"):
                    lines.append("Your exam score is in.")
                if res.get("requests"):
                    lines.append(f"They asked to see {res['requests']} file(s).")
                return go("/milestones", ok="\n".join(lines),
                          yay="approved" if res["decision"] == "approved" else None)
        except exchange.FileProblem as e:
            return go("/open", err=str(e))
        except (KeyError, TypeError, ValueError):
            return go("/open", err="This file is damaged or from a newer version of inPace.")
        return go("/open", err="inPace doesn't know this kind of file yet.")

    async def add_person_from_progress(request: Request):
        """Checker adds an unknown learner straight from their progress file."""
        form = await request.form()
        import json as _json
        try:
            data = _json.loads(str(form.get("progress", "")))
            learner = data["learner"]
        except (ValueError, KeyError):
            return go("/open", err="Something went wrong. Open the file again.")
        V.add_person(learner["id"], learner["name"], learner["color"], False, True, _their_turtle(learner), _their_island(data))
        nick = str(form.get("nickname", "")).strip()
        if nick:
            V.set_roles(learner["id"], False, True, nick)
        return go(f"/review/{learner['id']}/{data['journey']['id']}", ok=f"Added {learner['name']}.")

    # ---- reviewing someone ------------------------------------------------------
    async def review(request: Request):
        lid, jid = request.path_params["learner"], request.path_params["journey"]
        rec = V.received_one(lid, jid)
        person = V.person(lid)
        if not rec or not person:
            return go("/people", err="Open their progress file first.")
        if request.method == "POST":
            form = await request.form()
            decision = str(form.get("decision"))
            if decision not in ("approved", "question", "flag"):
                return go(f"/review/{lid}/{jid}", err="Choose approve, question or flag.")
            report = exchange.review_progress(V, rec["data"])
            if decision == "approved" and not report["history_ok"]:
                return go(f"/review/{lid}/{jid}", err="You can't approve while there's a problem with the history.")
            seqs = [m["body"]["seq"] for m in report["new"]] or [m["body"]["seq"] for m in report["milestones"][-1:]]
            note = str(form.get("note", ""))
            # Grade any verified exams in the new milestones, and add file requests.
            results = []
            for m in report["new"]:
                for e in m["body"]["events"]:
                    if e["type"] == "exam_taken":
                        g = checks.grade_exam_event(V, e["data"])
                        if g:
                            results.append({k: g[k] for k in ("exam", "score", "total", "percent", "passed")})
            known = checks.evidence_in(rec["data"])
            requests = []
            for item in form.getlist("request"):
                sha, _, name = str(item).partition("|")
                if sha in known:
                    requests.append({"sha256": sha, "name": known[sha]["name"]})
            extras = checks.sign_extras(V, lid, jid, results, requests) if (results or requests) else None
            approval = exchange.make_approval_file(V, rec["data"], decision, note, seqs, extras)
            out = V.home / "outbox"
            out.mkdir(exist_ok=True)
            fname = f"For {display_name(person)} - {decision} - {now_utc()[:10]}.inpace"
            fname = re.sub(r"[^\w .,()-]+", "", fname)
            (out / fname).write_bytes(exchange.dump(approval))
            return go(f"/review/{lid}/{jid}?file={quote(fname)}", ok="Done! Now send the reply file back.")
        report = exchange.review_progress(V, rec["data"])
        course = V.get_course(rec["data"]["journey"]["course"]["id"])
        # Resolve lesson and task names from our own copy of the course, if we have it.
        names = {}
        if course:
            for m in course.modules:
                for les in m["lessons"]:
                    names[les["id"]] = les["title"]
                for r in m["requires"]:
                    names[r["id"]] = r["prompt"]
        graded = {}
        for m in report["milestones"]:
            for e in m["body"]["events"]:
                if e["type"] == "exam_taken":
                    g = checks.grade_exam_event(V, e["data"])
                    if g:
                        graded[e["data"]["exam"]] = g
        quizzes = []
        if course:
            for m in course.modules:
                for r in m["requires"]:
                    if r["type"] == "quiz":
                        quizzes.append({"id": r["id"], "module": m["title"]})
        diffs = checks.outline_differences(course, rec["data"].get("outline"),
                                           rec["data"]["journey"]["course"]["hash"]) if course else []
        all_events = [e for m in report["milestones"] for e in m["body"]["events"]]
        weekly = pace.weeks(all_events, [m["body"]["created_at"] for m in report["milestones"]])
        reply_file = request.query_params.get("file")
        reply_share = None
        if reply_file and (V.home / "outbox" / Path(reply_file).name).exists():
            try:
                sh = exchange.share_links(say("My reply on inPace 🐢 Tap the link to open it:"),
                                          exchange.read_inpace_file((V.home / "outbox" / Path(reply_file).name).read_bytes()),
                                          say("My reply on inPace"))
                reply_share = sh if sh["fits"] else None
            except exchange.FileProblem:
                pass
        return page("review.html", request, person=person, rec=rec, report=report, names=names, weekly=weekly,
                    reply_file=reply_file, reply_share=reply_share, receipts=V.receipts(lid, jid),
                    graded=graded, have_files=checks.has_received_files(V), course=course, quizzes=quizzes,
                    sent=checks.sent_exams(V, lid, jid), course_diffs=diffs,
                    similar=checks.similar_writeups(V, rec["data"]), all_files=checks.evidence_in(rec["data"]))

    async def make_exam_page(request: Request):
        lid, jid, rid = request.path_params["learner"], request.path_params["journey"], request.path_params["rid"]
        rec, person = V.received_one(lid, jid), V.person(lid)
        if not rec or not person:
            return go("/people", err="Open their progress file first.")
        course = V.get_course(rec["data"]["journey"]["course"]["id"])
        found = course.find_requirement(rid) if course else None
        if not found or found[1]["type"] != "quiz":
            return go(f"/review/{lid}/{jid}", err="That quiz wasn't found in your copy of the course.")
        module, req = found
        ctx = dict(person=person, journey=jid, module=module, req=req,
                   has_earlier=bool(checks.earlier_quiz_questions(course, rid)))
        if request.method == "POST":
            form = await request.form()
            if form.get("action") == "add_question":
                try:
                    checks.add_private_question(V, course.id, str(form.get("text", "")), str(form.get("right", "")),
                                                str(form.get("wrong", "")).splitlines())
                except ValueError as e:
                    return go(f"/review/{lid}/{jid}/exam/{rid}", err=str(e))
                return go(f"/review/{lid}/{jid}/exam/{rid}", ok="Question saved. It's ticked for this exam.")
            try:
                exam = checks.make_exam(V, rec["data"], course, rid, [str(x) for x in form.getlist("private")],
                                        bool(form.get("surprise")))
            except exchange.FileProblem as e:
                return go(f"/review/{lid}/{jid}", err=str(e))
            out = V.home / "outbox"
            out.mkdir(exist_ok=True)
            fname = re.sub(r"[^\w .,()-]+", "", f"Exam for {display_name(person)} - {module['title']} - {now_utc()[:10]}.inpace")
            (out / fname).write_bytes(exchange.dump(exam))
            return page("make_exam.html", request, exam_file=fname, **ctx)
        return page("make_exam.html", request, private=checks.private_questions(V, course.id), **ctx)

    async def my_evidence(request: Request):
        """Play back your own saved work (a voice note or video) right on the task page."""
        sha = request.path_params["sha"]
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            return Response("Not found", status_code=404)
        p = V.home / "evidence" / sha[:2] / sha
        if not p.exists():
            return Response("Not found", status_code=404)
        name = Path(request.query_params.get("name") or "file").name
        if request.query_params.get("view") == "1" and name.lower().endswith((".html", ".htm")):
            return _sealed_html(p.read_bytes())
        import mimetypes
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if not mime.startswith(("audio/", "video/", "image/")):
            return download(p.read_bytes(), name)
        return FileResponse(p, media_type=mime, headers={"X-Content-Type-Options": "nosniff"})

    def _sealed_html(data: bytes) -> Response:
        """An HTML work file (a CodeNote report, say) to look at inside inPace: shown in a frame with sandbox="" on
        the page, and sealed here too, so no script runs and it can't reach anything."""
        return Response(data, media_type="text/html; charset=utf-8", headers={
            "Content-Security-Policy": "sandbox; default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; "
                                       "font-src data:; media-src data: blob:",
            "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})

    async def received_file(request: Request):
        got = checks.received_file(V, request.path_params["sha"])
        if not got:
            return go("/people", err="That file isn't here.")
        if request.query_params.get("view") == "1" and got[1].lower().endswith((".html", ".htm")):
            return _sealed_html(got[0])
        if request.query_params.get("play") == "1":
            import mimetypes
            mime = mimetypes.guess_type(got[1])[0] or ""
            if mime.startswith(("audio/", "video/")):
                return Response(got[0], media_type=mime, headers={"X-Content-Type-Options": "nosniff"})
        return download(got[0], got[1])

    async def outbox(request: Request):
        name = Path(request.path_params["name"]).name
        p = V.home / "outbox" / name
        if not p.exists():
            return go("/people", err="That file is gone. Review again to make a new one.")
        return download(p.read_bytes(), name, "application/json")

    async def backup(request: Request):
        form = await request.form()
        try:
            data = pace.make_backup(V, str(form.get("password", "")))
        except ValueError as e:
            return go("/settings", err=str(e))
        return download(data, f"inPace backup - {V.me['name']} - {now_utc()[:10]}.inpace-backup")

    async def restore(request: Request):
        form = await request.form()
        up = form.get("file")
        if not up or not getattr(up, "filename", ""):
            return go("/settings", err="Choose your backup file first.")
        raw = await up.read()
        try:
            pace.open_backup(raw, str(form.get("password", "")))
        except ValueError as e:
            return go("/settings", err=str(e))
        except Exception:
            return go("/settings", err="This backup couldn't be read.")
        pace.restore_backup(V, raw, str(form.get("password", "")))
        # Reopen the restored data right away (closing inPace instead looked like a crash).
        V.__init__(V.home)
        return go("/", ok="Backup restored.")

    async def youtube_setting(request: Request):
        form = await request.form()
        V._set_meta("yt_ad_guard", "on" if form.get("guard") else "off")
        V._set_meta("yt_ad_block", "on" if form.get("block") else "off")
        return go("/settings#youtube", ok="Saved.")

    async def yt_stream(request: Request):
        """The ad blocker: yt-dlp finds the video's plain file, so inPace's own player plays it with no ads.
        Empty answer: play it in YouTube's player instead (with the ad guard)."""
        from starlette.concurrency import run_in_threadpool
        from . import ytrules as _yr
        asked = request.query_params.get("q", "")  # the quality menu of a YouTube lesson asked for this size
        if asked not in ("360", "480", "720", "1080"):
            asked = ""
        if not asked and not _yr.current()["ad_block"]:
            return JSONResponse({"why": gettext("It's turned off in Settings.")})
        q = asked or V._meta("ytdlp_quality", "720") or "720"
        found = await run_in_threadpool(offline.stream, V.home, request.path_params["vid"], None,
                                        request.query_params.get("hls") == "1", "720" if q == "best" else q, bool(asked))
        if found.get("why"):
            found["why"] = _tr_why(found["why"])
        return JSONResponse(found, headers={"Cache-Control": "no-store"})

    async def yt_subs(request: Request):
        """A YouTube lesson's subtitle languages (for the CC button), or one track's text."""
        from starlette.concurrency import run_in_threadpool
        vid, lang = request.path_params["vid"], request.path_params.get("lang", "")
        ui = V._meta("lang", "en") or "en"
        if not lang:
            found = await run_in_threadpool(offline.subtitles, V.home, vid, ui)
            tracks = [{"lang": x["lang"], "label": (x["name"] + " · " + say("made by YouTube")) if x["auto"] else x["name"],
                       "from": x.get("from", "")} for x in found.get("tracks", [])]
            return JSONResponse({"tracks": tracks, "why": _tr_why(found["why"]) if found.get("why") else ""},
                                headers={"Cache-Control": "no-store"})
        try:
            text = await run_in_threadpool(offline.subtitle_text, V.home, vid, lang, ui)
        except Exception:
            text = ""
        if not text.startswith("WEBVTT"):
            return Response(status_code=404)
        return Response(text, media_type="text/vtt", headers={"Cache-Control": "max-age=3600"})

    async def delete_everything(request: Request):
        """Settings → Delete all my data: empties inPace's folder (courses, progress, notes, people, keys,
        backups inside it) and starts fresh, like the first day. Asks you to type a word first."""
        import shutil as _sh
        form = await request.form()
        word = str(form.get("confirm", "")).strip()
        if word.casefold() not in {"delete", gettext("DELETE").casefold()}:
            return go("/settings#delete", err="Nothing was deleted. Type the word exactly to confirm.")
        folders = []
        if form.get("videos"):
            folders = [offline.system_folder("downloads") / "inPace", offline.system_folder("videos") / "inPace"]
        try:
            V.db.close()
        except Exception:
            pass
        left = []
        for item in list(V.home.iterdir()):
            try:
                _sh.rmtree(item) if item.is_dir() and not item.is_symlink() else item.unlink()
            except OSError:
                left.append(item.name)
        for f in folders:
            _sh.rmtree(f, ignore_errors=True)
        V.__init__(V.home)  # an empty inPace: the welcome page comes next
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                notifier.sync(V, True)  # no courses left, so no reminders on this computer either
            except Exception:
                pass
        if left:
            return go("/", err=say("Almost everything was deleted. A few files were in use: %s", [", ".join(left[:5])]))
        return go("/", ok="All your inPace data was deleted.")

    async def ai_settings(request: Request):
        form = await request.form()
        integrations.save_ai_settings(V, str(form.get("provider", "")), str(form.get("model", "")),
                                      str(form.get("base_url", "")), str(form.get("key", "")))
        return go("/settings#ai", ok="AI settings saved.")

    async def settings(request: Request):
        if request.method == "POST":
            form = await request.form()
            V.rename(str(form.get("name", "")).strip() or V.me["name"], V.me["color"])
            V._set_meta("lang", langs.pick(str(form.get("lang", "")), CURRENT["lang"]))
            return go("/settings", ok="Saved.")
        av = mascot_mod.clean_avatar(V.me.get("avatar") or {})
        videos = {"version": offline.version(V.home), "updates": V._meta("ytdlp_updates", "auto") or "auto",
                  "quality": V._meta("ytdlp_quality", "720") or "720", "ffmpeg": bool(shutil.which("ffmpeg")),
                  "qualities": offline.QUALITIES, "folder": V._meta("ytdlp_folder", "downloads") or "downloads",
                  "folder_path": V._meta("ytdlp_folder_path", "") or "",
                  "downloads": str(offline.system_folder("downloads") / "inPace"),
                  "videos_dir": str(offline.system_folder("videos") / "inPace"), "android": offline.on_android()}
        try:
            startup = json.loads(V._meta("startup_last", "") or "null")
        except ValueError:
            startup = None
        return page("settings.html", request, colors=COLORS, yt_guard=(V._meta("yt_ad_guard", "on") or "on") == "on", yt_block=(V._meta("yt_ad_block", "on") or "on") == "on", home=str(V.home), ai=integrations.ai_settings(V), videos=videos,
                    maker=_maker(av), av=av, has_turtle=bool(V.me.get("avatar")),
                    providers=integrations.PROVIDERS, models=integrations.DEFAULT_MODELS, startup=startup)

    # ---- Tempo's island (reward mode) -------------------------------------------------------------
    def _island_labels() -> dict:
        CURRENT["lang"] = V._meta("lang", "en") or "en"
        out = {"island": say("Tempo carries your island"), "wilting": say("wilting"),
               "dead": say("Taken by the fog"), "visitor": say("A visitor came, because you studied today"),
               "trophy": say("A trophy for a finished course")}
        out.update({k: say(n) for k, n in garden.FRIEND_NAMES.items()})
        out.update({"plant_" + k: say(n) for k, n in garden.PLANT_NAMES.items()})
        out.update({"deco_" + k: say(n) for k, n in garden.SHOP_NAMES.items()})
        out.update({"phase_" + k: say(n) for k, n in (("night", "Night on the island"), ("dawn", "Dawn on the island"),
                    ("morning", "Morning on the island"), ("day", "Daytime on the island"),
                    ("sunset", "Sunset on the island"), ("dusk", "Dusk on the island"))})
        return out

    def _island_others() -> list[dict]:
        """Friends' turtles on your sea chart: learners you check (by their progress) and your checkers (at the lighthouse).
        People who made a turtle sail in their own colours."""
        def palette(p):
            if p.get("avatar"):
                av = mascot_mod.clean_avatar(p["avatar"])
                return tuple(mascot_mod.SHELLS[av["shell"]]) + tuple(mascot_mod.SCARVES[av["scarf"]])
            return garden.PALETTES[1 + sum(map(ord, p["id"])) % (len(garden.PALETTES) - 1)]
        out = []
        for p in V.people():
            if p["i_check"]:
                best = 0
                for r in V.received(p["id"]):
                    for m in r["data"].get("milestones", []):
                        best = max(best, (m.get("body", {}).get("summary", {}) or {}).get("percent", 0) or 0)
                out.append({"name": display_name(p), "pos": best / 100, "palette": palette(p)})
            elif p["checks_me"]:
                out.append({"name": display_name(p), "pos": 0.4, "palette": palette(p)})
        return out[:8]

    def _trip_live() -> dict | None:
        """The running focus trip, or the floating timer, for the phone's countdown notification (None when
        there's nothing to show)."""
        trip = garden.active(V) if garden.is_on(V) else None
        if not trip or trip["state"] not in ("running", "paused"):
            d = focus.live(V)
            if not d.get("on") or d.get("kind") != "timer":
                return None
            CURRENT["lang"] = V._meta("lang", "en") or "en"
            return {"id": d["id"], "state": d["state"], "mode": "anywhere", "goal": round(d["goal"] / 60), "url": "/",
                    "ends_ms": int((_time.time() + d["left"]) * 1000) if d["state"] == "running" else None,
                    "channel": say("Focus timer"), "title": say("Focus timer"),
                    "body": d.get("label") or say("Keep going. Tap to open inPace."),
                    "paused_title": say("Timer paused"), "paused_body": say("Tap to open inPace and go on."),
                    "done_title": say("Time's up!"), "done_body": t("{n} minutes of focus. Take a short break.", n=round(d["goal"] / 60)),
                    **_timer_buttons()}
        CURRENT["lang"] = V._meta("lang", "en") or "en"
        plant = say(garden.PLANT_NAMES.get(trip["kind"], ""))
        left = max(0, trip["goal"] * 60 - garden.elapsed(trip))
        return {"id": trip["id"], "state": trip["state"], "mode": trip["mode"], "goal": trip["goal"],
                "ends_ms": int((_time.time() + left) * 1000) if trip["state"] == "running" else None,
                "channel": say("Focus trip"),
                "title": t("Focus trip: {plant}", plant=plant),
                "body": say("Tempo is swimming. Your plant grows while you study."),
                "paused_title": t("Your {plant} sprout is waiting", plant=plant),
                "paused_body": say("Phone down: the clock only counts while the trip screen is open. Come back to keep growing."),
                "done_title": t("Your {plant} is ready!", plant=plant),
                "done_body": say("Tempo finished the trip. Come and see it join the island."),
                **_timer_buttons()}

    def _timer_buttons() -> dict:
        """The words on the notification's buttons (the phone app makes Pause, Go on and Stop from them)."""
        return {"actions": True, "l_pause": say("Pause"), "l_resume": say("Go on"), "l_stop": say("Stop")}

    _trip_timer: dict = {"key": None, "timer": None}

    def _arm_trip_timer() -> None:
        """On a computer: while inPace is open (even minimized), say "your plant is ready" the minute the trip ends.
        (When inPace is closed, the hourly reminder check says it instead. Phones schedule it themselves.)"""
        if os.environ.get("INPACE_MOBILE"):
            return
        if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("INPACE_TEST_TRIP_TIMER"):
            return  # no real notifications while the tests run
        try:
            trip = garden.active(V) if garden.is_on(V) else None
            key, left = None, 0.0
            if trip and trip["state"] == "running" and reminders.load(V)["auto"]["island"]:
                left = trip["goal"] * 60 - garden.elapsed(trip)
                key = f'{trip["id"]}:{trip["run_from"]}:{trip["banked"]}'
            if key == _trip_timer["key"]:
                return
            if _trip_timer["timer"]:
                _trip_timer["timer"].cancel()
            _trip_timer.update(key=key, timer=None)
            if key:
                timer = threading.Timer(max(1.0, left + 1), _trip_ring)
                timer.daemon = True
                timer.start()
                _trip_timer["timer"] = timer
        except Exception:
            pass

    def _trip_ring() -> None:
        try:
            reminders.use_language(V)
            item = reminders.trip_done_now(V)
            if item and notifier.notify(item["title"], item["body"], item["url"], V.home, picture=item.get("picture", "")):
                reminders.mark_sent(V, item)
        except Exception:
            pass
        _trip_timer.update(key=None, timer=None)

    def _goal_met() -> bool:
        for j in V.journeys():
            card = journey_card(j)
            pc = card.get("pace") or {}
            tw, com = pc.get("this_week"), pc.get("commitment")
            if com and tw and tw.get("count", 0) >= com.get("per_week", 99):
                return True
        return False

    async def island(request: Request):
        garden.setup(V)
        on = garden.is_on(V)
        lang = V._meta("lang", "en") or "en"
        just = garden.check(V) if on else None
        st = garden.stats(V)
        coll = garden.collection(V, st)
        have = garden.unlocked(V, st)
        trip = garden.active(V)
        journeys = [{"id": j["id"], "title": (V.get_course(j["course_id"]).title if V.get_course(j["course_id"]) else j["course_id"])}
                    for j in V.journeys()]
        ctx = dict(on=on, st=st, coll=coll, have=have, trip=trip, just=just, lengths=garden.LENGTHS, journeys=journeys,
                   plant_svg=garden.plant_svg, friend_svg=garden.friend_svg,
                   elapsed=int(garden.elapsed(trip)) if trip else 0,
                   last_kind=(garden.last_grown(V) or {}).get("kind", "sunflower"))
        world_setting = V._meta("island_world", "") or ""
        if not on:
            intro = garden.story.chapter("c1", garden.story.world_for(world_setting, lang), lang)
            return page("island.html", request, intro=intro, **ctx)
        rot = garden.decay(V)
        wx = garden.weather(V, goal_met=_goal_met())
        others = _island_others()
        tale = garden.story_state(V, st, wx, lang, people=len(others))
        shown = garden.island(V, lang)
        ring = 1 + shown["living"] // 10
        labels = _island_labels()
        labels["villain"] = garden.story.villain_name(tale["world"], lang)
        look = garden.looks(V, "")
        sky = garden.sky_at()
        picture = garden.island_svg(shown["plants"], have["friends"], ring, st["blooming"], labels=labels,
                                    palette=shown["palette"], fog=wx["fog"], fair=wx["fair"],
                                    look=look, title=shown["title"], villain=wx["threat"],
                                    season_now=garden.season(datetime.now().month),
                                    visitor=garden.visitor_today(V), fled=wx["fled"], trophies=st["courses"])
        ctx["wallet"] = garden.wallet(V, st)
        ctx["shop"] = _shop(ctx["wallet"], look)
        ctx["look"] = look
        ctx["rot"] = rot
        ctx["sky"] = sky
        ctx["phase_label"] = labels.get("phase_" + sky["phase"], "")
        ctx["taunt"] = garden.story.taunt(wx["threat"], tale["world"], lang, wx["wilt_in"] or 0)
        ctx["villain_svg"] = Markup(f'<svg viewBox="0 0 160 140" width="96" height="84" aria-hidden="true">{garden.art.villain(wx["threat"])}</svg>') if wx["threat"] else ""
        ctx["death_in"] = max(0, int((rot["next_death"] - _time.time()) // 86400)) if rot.get("next_death") else None
        ctx["rewards"] = garden.course_rewards(V)
        ctx["sharing"] = garden.share_on(V)
        ctx["friend_islands"] = _friend_islands()
        story_pos = len([c for c in tale["chapters"] if not c["interlude"]]) / len(garden.story.CHAPTERS)
        chart = garden.sea_chart([shown], others, story_pos, labels={"chart": say("The way to the Far Shore")})
        friend_lines = {k: say(n) + ": " + say(story) for k, n, _, story in garden.FRIENDS if k in have["friends"]}
        return page("island.html", request, wx=wx, tale=tale, shown=shown, ring=ring, picture=picture,
                    chart=chart, world_setting=world_setting, others=others, friend_lines=friend_lines, **ctx)

    async def island_world(request: Request):
        form = await request.form()
        w = str(form.get("world", ""))
        V._set_meta("island_world", w if w in garden.story.WORLDS else "")
        return go("/island#logbook")

    async def island_name(request: Request):
        form = await request.form()
        garden.set_title(V, "", str(form.get("title", "")))
        return go("/island")

    def _shop(wallet: dict, look: dict) -> list[dict]:
        """The shop, grouped, with what you own and what this island uses."""
        groups = [("theme", say("Island ground"), garden.THEMES), ("sky", say("Sky"), garden.SKIES),
                  ("water", say("Sea"), garden.WATERS), ("decor", say("Things to put on the island"), garden.DECOR),
                  ("accessory", say("For your own turtle"), mascot_mod.PAID_ACCESSORIES)]
        out = []
        for kind, title, items in groups:
            rows = []
            for key, price in items.items():
                owned = f"{kind}:{key}" in wallet["owned"]
                using = (key in look["decor"]) if kind == "decor" else (look.get(kind) == key)
                rows.append({"key": key, "name": say(garden.SHOP_NAMES.get(key, key)), "price": price, "owned": owned,
                             "using": using, "afford": wallet["balance"] >= price, "preview": Markup(_shop_preview(kind, key))})
            out.append({"kind": kind, "title": title, "rows": rows})
        return out

    def _shop_preview(kind: str, key: str) -> str:
        if kind == "theme":
            g, e, h = garden.THEME_COLORS[key]
            return (f'<svg viewBox="0 0 60 40" width="60" height="40"><path d="M4 36 C4 14 18 6 30 6 C42 6 56 14 56 36 Z" fill="{g}" stroke="#111" stroke-width="2"/>'
                    f'<path d="M14 26 q16 8 32 0" fill="none" stroke="{e}" stroke-width="3"/><path d="M16 18 q6 -6 12 -7" stroke="{h}" stroke-width="3" fill="none" stroke-linecap="round"/></svg>')
        if kind == "water":
            a, b = garden.WATER_COLORS[key]
            return (f'<svg viewBox="0 0 60 40" width="60" height="40"><rect width="60" height="40" rx="8" fill="{a}"/>'
                    f'<path d="M0 24 q7.5 -6 15 0 t15 0 t15 0 t15 0 V40 H0 Z" fill="{b}" stroke="#111" stroke-width="1.6"/></svg>')
        if kind == "sky":
            top, low = {"auto": ("#7EC4F0", "#FFD08A"), "balloons": ("#7EC4F0", "#E4F4FB"),
                        "starry": ("#0F1A33", "#4A3F7A"), "aurora": ("#0E1F3A", "#1B4D5C")}[key]
            extra = {"balloons": '<circle cx="22" cy="16" r="7" fill="#E6007E" stroke="#111" stroke-width="1.5"/><circle cx="42" cy="22" r="5" fill="#3D8FD1" stroke="#111" stroke-width="1.5"/>',
                     "starry": "".join(f'<circle cx="{x}" cy="{y}" r="1.4" fill="#fff"/>' for x, y in ((10, 8), (24, 18), (40, 6), (50, 20), (16, 28), (34, 30))),
                     "aurora": '<path d="M0 16 Q20 4 34 14 T60 10 V22 Q40 18 30 26 T0 26 Z" fill="#5CF2B8" opacity=".6"/>',
                     "auto": '<circle cx="44" cy="14" r="7" fill="#FFD43B" stroke="#111" stroke-width="1.5"/><path d="M10 12 a6 6 0 1 0 5 9 a5 5 0 1 1 -5 -9z" fill="#FFF3B0" stroke="#111" stroke-width="1.2"/>'}[key]
            return (f'<svg viewBox="0 0 60 40" width="60" height="40"><defs><linearGradient id="sp-{key}" x1="0" y1="0" x2="0" y2="1">'
                    f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{low}"/></linearGradient></defs>'
                    f'<rect width="60" height="40" rx="8" fill="url(#sp-{key})"/>{extra}</svg>')
        if kind == "decor":
            return f'<svg viewBox="-50 -110 100 116" width="46" height="54">{garden.art.deco(key, "")}</svg>'
        if kind == "accessory":
            return str(mascot_mod.buddy_head({"acc": key}, 54))
        return ""

    async def island_buy(request: Request):
        form = await request.form()
        kind, key, jid = str(form.get("kind", "")), str(form.get("key", "")), ""
        back = "/island#shop"
        problem = garden.buy(V, kind, key, garden.stats(V))
        if problem:
            return go(back, err=problem)
        if kind != "accessory":
            garden.set_look(V, jid, kind, key)
            return go(back, ok="Bought, and it's on your island now.")
        return go(back, ok="Bought. Put it on your turtle in Settings.")

    async def island_look(request: Request):
        form = await request.form()
        garden.set_look(V, "", str(form.get("kind", "")), str(form.get("key", "")))
        return go("/island#shop")

    async def island_clear(request: Request):
        form = await request.form()
        garden.clear_dead(V)
        return go("/island", ok="Cleared. There's room to grow again.")

    def _person_palette(p: dict):
        if p.get("avatar"):
            av = mascot_mod.clean_avatar(p["avatar"])
            return tuple(mascot_mod.SHELLS[av["shell"]]) + tuple(mascot_mod.SCARVES[av["scarf"]])
        return garden.PALETTES[0]

    def _their_island_svg(p: dict, snap: dict) -> str:
        """A friend's island, carried by their own turtle, under your sky."""
        labels = _island_labels()
        return garden.island_svg(snap["plants"], set(snap["friends"]), snap["ring"], labels=labels,
                                 palette=_person_palette(p), look=snap["look"], title=snap["title"],
                                 season_now=garden.season(datetime.now().month), trophies=snap["trophies"])

    def _friend_islands() -> list[dict]:
        out = []
        for p in V.people():
            try:
                snap = garden.clean_snapshot(json.loads(p.get("island") or "null"))
            except ValueError:
                snap = None
            if not snap:
                continue
            out.append({"id": p["id"], "person": p, "name": display_name(p),
                        "title": snap["title"] or t("{name}'s island", name=display_name(p)),
                        "plants": snap["stats"]["plants"], "picture": Markup(_their_island_svg(p, snap))})
        return out[:12]

    async def person_island(request: Request):
        p = V.person(request.path_params["pid"])
        try:
            snap = garden.clean_snapshot(json.loads((p or {}).get("island") or "null"))
        except ValueError:
            snap = None
        if not p or not snap:
            return go("/people", err="This person hasn't shared an island with you yet.")
        when = datetime.fromtimestamp(snap["at"]).strftime("%Y-%m-%d") if snap["at"] else ""
        return page("person_island.html", request, person=p, who=display_name(p), snap=snap, when=when,
                    title=snap["title"] or t("{name}'s island", name=display_name(p)),
                    picture=Markup(_their_island_svg(p, snap)),
                    friends=[{"key": k, "name": say(garden.FRIEND_NAMES[k])} for k in snap["friends"]],
                    friend_svg=garden.friend_svg)

    def _share_island_svg() -> str:
        """A square picture of your island to share anywhere: its name, the island, and a few numbers."""
        lang = V._meta("lang", "en") or "en"
        st = garden.stats(V)
        wx = garden.weather(V)
        isle = garden.island(V, lang)
        have = garden.unlocked(V, st)
        art_svg = garden.island_svg(isle["plants"], have["friends"], 1 + isle["living"] // 10, st["blooming"],
                                    labels=_island_labels(), fair=wx["fair"], look=garden.looks(V, ""),
                                    title=isle["title"], season_now=garden.season(datetime.now().month),
                                    trophies=st["courses"])
        art_svg = art_svg.replace('<svg class="island-art', '<svg x="40" y="190" width="1000" height="588" class="island-art', 1)
        esc = lambda x: str(Markup.escape(x))
        facts = " · ".join([t("{n} plants", n=st["plants"]), t("{n} friends", n=len(have["friends"])),
                            t("{n} h of focus", n=st["hours"]), t("{n} days in a row", n=st["streak"])])
        font = 'font-family="system-ui, -apple-system, Segoe UI, sans-serif"'
        me = V.me
        head = str(mascot_mod.buddy_head(me.get("avatar") or {}, 90)) if me.get("avatar") else ""
        head = head.replace('<svg class="buddy-head"', '<svg x="40" y="40" class="buddy-head"', 1)
        return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1080" width="1080" height="1080">'
                '<rect width="1080" height="1080" fill="#F7F3EA"/>'
                f'<rect x="40" y="190" width="1000" height="588" fill="none" stroke="#111" stroke-width="6"/>'
                f'{head}<text x="{150 if head else 40}" y="105" {font} font-size="64" font-weight="800" fill="#111">{esc(isle["title"])}</text>'
                f'<text x="{150 if head else 40}" y="150" {font} font-size="32" fill="#5E5A52">{esc(t("{name} is growing it, one focus trip at a time.", name=me["name"]))}</text>'
                f'{art_svg}'
                f'<text x="540" y="870" text-anchor="middle" {font} font-size="40" font-weight="700" fill="#111">{esc(facts)}</text>'
                f'<text x="540" y="1010" text-anchor="middle" {font} font-size="34" fill="#5E5A52">{esc(say("Slow and steady. Learning with inPace."))}</text>'
                '</svg>')

    async def island_share_svg(request: Request):
        name = garden.island(V, V._meta("lang", "en") or "en")["title"]
        return download(_share_island_svg().encode(), f"{name}.svg", "image/svg+xml")

    async def island_share_png(request: Request):
        form = await request.form()
        raw = _png_from_form(form)
        if raw is None:
            return go("/island", err="The picture couldn't be made. Try the SVG instead.")
        name = garden.island(V, V._meta("lang", "en") or "en")["title"]
        return download(raw, f"{name}.png", "image/png")

    async def island_sharing(request: Request):
        form = await request.form()
        V._set_meta("island_share", "1" if form.get("on") == "1" else "0")
        if form.get("on") == "1":
            return go("/island", ok="People you add will see your island. Send them your contact card again to show it now.")
        return go("/island", ok="Your island is private now. New cards and files won't carry it.")

    async def island_gentle(request: Request):
        form = await request.form()
        V._set_meta("island_gentle", "1" if form.get("on") == "1" else "")
        if form.get("on") == "1":
            return go("/island", ok="Gentle sea is on. The fog still comes, but it never takes your plants.")
        return go("/island", ok="The fog is real again. Stay away too long and your plants wilt.")

    async def island_mode(request: Request):
        form = await request.form()
        garden.set_on(V, form.get("on") == "1")
        if form.get("on") == "1":
            import time as _t
            V._set_meta("garden_since", str(_t.time()))
        if form.get("on") == "1":
            return go("/island", ok="Tempo's island is on. Start a focus trip to grow your first plant.")
        return go("/island", ok="Reward mode is off. Your island is kept, ready for when you come back.")

    async def island_start(request: Request):
        if not garden.is_on(V):
            return go("/island")
        form = await request.form()
        try:
            minutes = int(form.get("minutes") or 25)
        except ValueError:
            minutes = 25
        garden.start(V, str(form.get("kind", "")), minutes, str(form.get("mode", "anywhere")), str(form.get("journey", "")))
        return go("/island/trip")

    async def island_trip(request: Request):
        if not garden.is_on(V):
            return go("/island")
        just = garden.check(V)
        trip = garden.active(V)
        if not trip and not just:
            return RedirectResponse("/island", status_code=303)
        shown = trip or just
        title = ""
        if shown.get("journey"):
            j = V.journey(shown["journey"])
            c = V.get_course(j["course_id"]) if j else None
            title = c.title if c else ""
        return page("island_trip.html", request, trip=trip, just=just, kind=shown["kind"], goal=shown["goal"],
                    elapsed=int(garden.elapsed(trip)) if trip else shown["goal"] * 60, studying=title,
                    trip_svg=garden.trip_svg(shown["kind"], 1.0 if just else garden.elapsed(trip) / (trip["goal"] * 60),
                                             "cheer" if just else "read", label=say("Tempo swims while your plant grows"),
                                             stages=not just, sky=garden.sky_at()),
                    plant_name=say(garden.PLANT_NAMES.get(shown["kind"], "")),
                    plant_svg=garden.plant_svg, dispose="/island" if just else None)

    async def island_rest(request: Request):
        garden.rest(V)
        return go("/island", ok="Resting. Your sprout keeps its minutes and waits for your next trip.")

    async def island_letgo(request: Request):
        garden.let_go(V)
        return go("/island")

    async def island_pause(request: Request):
        trip = garden.active(V)
        if trip and trip["mode"] == "phone":
            garden.rest(V, state="paused")
        _arm_trip_timer()
        return Response(status_code=204)

    async def island_resume(request: Request):
        # Coming back to the trip screen restarts a "phone down" trip that paused because you left it. A trip you
        # paused yourself (the timer's Pause button) stays paused until you press Go on.
        t0 = garden.active(V)
        if t0 and t0["mode"] == "phone":
            garden.resume(V)
        just = garden.check(V)
        trip = garden.active(V)
        _arm_trip_timer()
        return JSONResponse({"grown": bool(just), "elapsed": int(garden.elapsed(trip)) if trip else 0,
                             "state": trip["state"] if trip else "grown"})

    async def island_live(request: Request):
        """What the phone's notification should show about the focus trip right now."""
        return JSONResponse({"trip": _trip_live()}, headers={"Cache-Control": "no-store"})

    async def island_done(request: Request):
        just = garden.check(V)
        trip = garden.active(V)
        return JSONResponse({"grown": bool(just) or not trip, "elapsed": int(garden.elapsed(trip)) if trip else 0})

    async def startup_time(request: Request):
        """The phone app reports how long it took to start (Python ready, first page shown), for Settings."""
        form = await request.form()
        out = {}
        for k in ("python", "page"):
            try:
                ms = int(str(form.get(k, "")))
                if 0 <= ms < 600_000:
                    out[k] = ms
            except ValueError:
                pass
        if out:
            out["at"] = now_utc()
            V._set_meta("startup_last", json.dumps(out))
        return JSONResponse({"ok": bool(out)})

    async def ping(request: Request):
        """Lets a newly started inPace find and replace an older one using the same data folder."""
        from . import __version__
        return JSONResponse({"app": "inpace", "version": __version__, "home": str(V.home.resolve())})

    _news_lock = threading.Lock()

    def _look_for_news() -> None:
        """Twice a day, look on GitHub for a new version, in the background (never slows a page)."""
        if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("INPACE_TEST_NEWS"):
            return
        if _time.time() - int(V._meta("update_news_checked", "0") or 0) < updater.NEWS_EVERY:
            return
        if not _news_lock.acquire(blocking=False):
            return

        def run():
            try:
                updater.check_news(V)
            finally:
                _news_lock.release()
        threading.Thread(target=run, daemon=True).start()

    # ---- new courses in the library: a badge on "Course library" and one notification -------------------
    _courses_lock = threading.Lock()

    def _note_library(index: dict, tell: bool = False) -> list[str]:
        """Remember which library courses we've seen. Courses that appear later are "new" (library_new) until you
        open the library page. The very first look only remembers, so nothing old is called new."""
        ids = [str(e.get("id")) for e in index.get("courses", []) if e.get("id")]
        if not ids or index.get("offline"):
            return []
        raw = V._meta("library_known", "")
        if not raw:
            V._set_meta("library_known", json.dumps(ids))
            return []
        try:
            known = set(json.loads(raw))
            pending = list(json.loads(V._meta("library_new", "[]") or "[]"))
        except ValueError:
            known, pending = set(ids), []
        fresh = [i for i in ids if i not in known]
        if not fresh:
            return []
        V._set_meta("library_known", json.dumps(sorted(known | set(fresh))))
        V._set_meta("library_new", json.dumps(pending + [i for i in fresh if i not in pending]))
        if tell and not os.environ.get("PYTEST_CURRENT_TEST"):
            titles = [str(e.get("title", "")) for e in index.get("courses", []) if str(e.get("id")) in fresh]
            CURRENT["lang"] = V._meta("lang", "en") or "en"
            title = say("New courses in the library") if len(fresh) > 1 else say("A new course in the library")
            body = ", ".join(titles[:3]) + (" …" if len(titles) > 3 else "")
            try:
                notifier.notify(title, body, "/library", V.home, picture="tempo_cheer")
            except Exception:
                pass
        return fresh

    def _library_new() -> set[str]:
        try:
            return set(json.loads(V._meta("library_new", "[]") or "[]"))
        except ValueError:
            return set()

    def _look_for_courses() -> None:
        """Twice a day, look at the library in the background for courses that weren't there before."""
        if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("INPACE_TEST_NEWS"):
            return
        if _time.time() - int(V._meta("library_checked", "0") or 0) < updater.NEWS_EVERY:
            return
        if not _courses_lock.acquire(blocking=False):
            return

        def run():
            try:
                V._set_meta("library_checked", str(int(_time.time())))
                _note_library(library.load_index(V.home, True), tell=True)
            except Exception:
                pass  # offline or the library is busy: try again next time
            finally:
                _courses_lock.release()
        threading.Thread(target=run, daemon=True).start()

    def _yt_rules_later() -> None:
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            from . import ytrules
            ytrules.refresh_later()

    def _update_news() -> dict | None:
        """A new version is out: what the pop-up says and offers, or None when there's nothing to say. Copies that
        update themselves (Settings: automatic updates) don't need it: their own bar says when it's installed."""
        _look_for_news()
        rel = updater.news(V)
        if not rel:
            return None
        kind = updater.install_kind()
        if kind not in ("source", "android") and (V._meta("updates", "") or "") == "auto":
            return None
        try:
            later = json.loads(V._meta("update_news_later", "{}") or "{}")
        except ValueError:
            later = {}
        if later.get("version") == rel["version"] and _time.time() - float(later.get("at") or 0) < 3 * 86400:
            return None
        notes = re.split(r"(?m)^#{1,3} ", rel.get("notes") or "")[0].strip() or (rel.get("notes") or "")
        notes = notes[:1800]
        apk = (rel.get("assets") or {}).get(updater.ANDROID_APK) or rel.get("page") or ""
        return {"version": rel["version"], "current": updater.__version__, "kind": kind, "page": rel.get("page", ""),
                "apk": apk, "notes_html": Markup(md.render(notes)) if notes else ""}

    async def update_later(request: Request):
        """"Later" on the new-version pop-up: ask again in three days (or when a newer one comes out)."""
        rel = updater.news(V)
        if rel:
            V._set_meta("update_news_later", json.dumps({"version": rel["version"], "at": _time.time()}))
        if request.headers.get("x-inpace-fetch"):
            return Response(status_code=204)
        return go(_back(request))

    def _update_info() -> dict:
        kind = updater.install_kind()
        try:
            status = json.loads(V._meta("update_status", "{}") or "{}")
        except ValueError:
            status = {}
        if status.get("version") and not updater.newer(status["version"]):
            status = {}  # already running that version
        return {"kind": kind, "setting": V._meta("updates", "") or "", "status": status,
                "version": updater.__version__}

    async def update_setting(request: Request):
        form = await request.form()
        choice = "auto" if form.get("choice") == "auto" else "off"
        V._set_meta("updates", choice)
        if choice == "auto" and updater.install_kind() not in ("source", "android"):
            import threading
            threading.Thread(target=updater.run, args=(V,), kwargs={"force": True}, daemon=True).start()
            return go(_back(request), ok="Automatic updates are on. inPace checks once a day.")
        return go(_back(request), ok="Automatic updates are off. You can turn them on in Settings.")

    def _back(request: Request) -> str:
        from urllib.parse import urlsplit
        ref = urlsplit(request.headers.get("referer") or "/")
        return ref.path if ref.path.startswith("/") else "/"

    async def update_check(request: Request):
        import anyio
        token = _progress_token(await request.form())
        status = await anyio.to_thread.run_sync(lambda: progress.within(token, {"title": "inPace", "note": "check"},
                                                                         updater.run, V, force=True))
        progress.report(token, state="done")
        msg = {"current": ("ok", "You have the newest version."),
               "installed": ("ok", "The new version is installed. Restart inPace to use it."),
               "ready": ("ok", "The new version is downloaded and ready to install."),
               "none": ("ok", "This copy runs from its code folder. Update it with git pull."),
               }.get(status.get("state"), ("err", "Couldn't check for updates right now. Are you online?"))
        return go("/settings#updates", **{msg[0]: msg[1]})

    async def update_install(request: Request):
        import anyio
        status = json.loads(V._meta("update_status", "{}") or "{}")
        if status.get("state") != "ready" or not status.get("file"):
            return go(_back(request), err="There's no update waiting to be installed.")
        if updater.install_kind() == "windows":
            import threading
            threading.Timer(0.6, updater.run_windows_installer, args=(Path(status["file"]),)).start()
            V._set_meta("update_status", json.dumps({"state": "installed", "version": status.get("version", "")}))
            return HTMLResponse('<!doctype html><meta charset="utf-8"><title>inPace</title>'
                                '<body style="font-family:system-ui;padding:3rem;background:#F7F3EA;color:#111">'
                                f'<h1>{html_escape(say("Updating inPace…"))}</h1>'
                                f'<p>{html_escape(say("It closes, installs the new version, and opens again in a moment."))}</p>')
        token = _progress_token(await request.form())
        progress.report(token, title=f"inPace {status.get('version', '')}", state="installing", note="install")
        try:
            await anyio.to_thread.run_sync(lambda: updater.install("deb", Path(status["file"])))
        except Exception as e:
            progress.report(token, state="failed")
            return go(_back(request), err=str(e))
        progress.report(token, state="done")
        V._set_meta("update_status", json.dumps({"state": "installed", "version": status.get("version", "")}))
        return _restarting()

    async def update_restart(request: Request):
        return _restarting()

    def _restarting():
        import threading
        threading.Timer(0.6, updater.restart).start()
        return HTMLResponse('<!doctype html><meta charset="utf-8"><title>inPace</title>'
                            '<body style="font-family:system-ui;padding:3rem;background:#F7F3EA;color:#111">'
                            '<h1>Restarting inPace…</h1><p>The new version opens in a moment.</p></body>')

    async def set_look(request: Request):
        """Settings → Light or dark: like the device, light, or dark; and dark as dark brown or AMOLED black."""
        form = await request.form()
        theme = str(form.get("theme", ""))
        V._set_meta("theme", theme if theme in ("light", "dark") else "")
        V._set_meta("dark_style", "black" if form.get("dark_style") == "black" else "")
        return go("/settings#look", ok="Saved.")

    async def set_theme(request: Request):
        form = await request.form()
        theme = str(form.get("theme", ""))
        if V.is_set_up:
            V._set_meta("theme", theme if theme in ("light", "dark") else "")
        return Response(status_code=204)

    async def quit_app(request: Request):
        import os
        import threading
        from .window import close_children
        threading.Timer(0.6, lambda: (close_children(), os._exit(0))).start()
        return HTMLResponse('<!doctype html><meta charset="utf-8"><title>inPace stopped</title>'
                            '<body style="font-family:system-ui;padding:3rem;background:#F7F7F4;color:#15191F">'
                            '<h1>inPace has stopped</h1><p>You can close this tab. Open inPace again any time.</p></body>')

    def needs_setup(handler):
        async def wrapped(request: Request):
            if not V.is_set_up:
                return go("/setup")
            return await handler(request)
        return wrapped

    routes = [
        Route("/setup", setup, methods=["GET", "POST"]),
        Route("/", needs_setup(home)),
        Route("/courses", needs_setup(courses)),
        Route("/add", needs_setup(add_hub)),
        Route("/reminders", needs_setup(reminders_page), methods=["GET", "POST"]),
        Route("/reminders/plan.json", needs_setup(reminders_plan)),
        Route("/reminders/test", needs_setup(reminders_test), methods=["POST"]),
        Route("/add/folder", needs_setup(add_folder)),
        Route("/add/links", needs_setup(add_links), methods=["GET", "POST"]),
        Route("/build", needs_setup(build_page)),
        Route("/build/save", needs_setup(build_save), methods=["POST"]),
        Route("/build/upload", needs_setup(build_upload), methods=["POST"]),
        Route("/build/links", needs_setup(build_links), methods=["POST"]),
        Route("/build/{cid}", needs_setup(build_page)),
        Route("/folders/new", needs_setup(folder_new), methods=["POST"]),
        Route("/folders/{fid}/rename", needs_setup(folder_rename), methods=["POST"]),
        Route("/folders/{fid}/delete", needs_setup(folder_delete), methods=["POST"]),
        Route("/courses/{cid}/folder", needs_setup(course_folder), methods=["POST"]),
        Route("/add/files", needs_setup(add_files), methods=["GET", "POST"]),
        Route("/add/book", needs_setup(add_book), methods=["GET", "POST"]),
        Route("/add/organize", needs_setup(add_organize), methods=["GET", "POST"]),
        Route("/add/copying/{cid}", needs_setup(add_copying)),
        Route("/courses/sample/{cid}", needs_setup(add_sample), methods=["POST"]),
        Route("/courses/from-folder", needs_setup(course_from_folder_route), methods=["POST"]),
        Route("/courses/{cid}/media-folder", needs_setup(set_media_folder), methods=["POST"]),
        Route("/courses/{cid}/find-files", needs_setup(find_course_files), methods=["POST"]),
        Route("/pick-folder", needs_setup(pick_folder_route), methods=["POST"]),
        Route("/m/{cid}/{path:path}", needs_setup(media_file)),
        Route("/sample-file/{cid}/{path:path}", needs_setup(sample_file)),
        Route("/roadmaps", needs_setup(roadmaps_page)),
        Route("/roadmaps/new", needs_setup(roadmap_new), methods=["GET", "POST"]),
        Route("/roadmaps/shared", needs_setup(roadmap_follow_shared), methods=["POST"]),
        Route("/roadmaps/{rid}", needs_setup(roadmap_page)),
        Route("/roadmaps/{rid}/follow", needs_setup(roadmap_follow), methods=["POST"]),
        Route("/roadmaps/{rid}/edit", needs_setup(roadmap_edit), methods=["GET", "POST"]),
        Route("/roadmaps/{rid}/remove", needs_setup(roadmap_remove), methods=["POST"]),
        Route("/roadmaps/{rid}/share", needs_setup(roadmap_share)),
        Route("/roadmaps/{rid}/file", needs_setup(roadmap_file)),
        Route("/roadmaps/{rid}/add/{cid}", needs_setup(roadmap_add_course), methods=["POST"]),
        Route("/roadmaps/{rid}/add-all", needs_setup(roadmap_add_all), methods=["POST"]),
        Route("/roadmaps/{rid}/drop-missing", needs_setup(roadmap_drop_missing), methods=["POST"]),
        Route("/roadmaps/{rid}/start/{cid}", needs_setup(roadmap_start), methods=["POST"]),
        Route("/island/voyages", needs_setup(island_voyages)),
        Route("/library", needs_setup(library_page)),
        Route("/library/{cid}/add", needs_setup(library_add), methods=["POST"]),
        Route("/library/{cid}", needs_setup(library_course)),
        Route("/courses/{cid}/publish", needs_setup(publish_course)),
        Route("/feedback", needs_setup(feedback_page)),
        Route("/share", needs_setup(share_pick)),
        Route("/courses/{cid}/share", needs_setup(share_course)),
        Route("/courses/{cid}/publish/file", needs_setup(publish_file)),
        Route("/media-pos", needs_setup(media_position), methods=["POST"]),
        Route("/yt/{cid}/{vid}", needs_setup(yt_file)),
        Route("/yt-stream/{vid}", needs_setup(yt_stream)),
        Route("/yt-subs/{vid}.json", needs_setup(yt_subs)),
        Route("/yt-subs/{vid}/{lang}.vtt", needs_setup(yt_subs)),
        Route("/courses/{cid}/subs", needs_setup(subtitle_file)),
        Route("/courses/{cid}/subs/add", needs_setup(subtitle_add), methods=["POST"]),
        Route("/courses/{cid}/open-media", needs_setup(open_media), methods=["POST"]),
        Route("/courses/{cid}/offline/download", needs_setup(offline_download), methods=["POST"]),
        Route("/courses/{cid}/offline/stop", needs_setup(offline_stop), methods=["POST"]),
        Route("/downloads", needs_setup(downloads_page)),
        Route("/codenote.json", needs_setup(codenote_status)),
        Route("/progress.json", needs_setup(progress_json)),
        Route("/codenote/open", needs_setup(codenote_open), methods=["POST"]),
        Route("/codenote/lesson.md", needs_setup(codenote_file)),
        Route("/downloads.json", needs_setup(downloads_json)),
        Route("/downloads/settings", needs_setup(downloads_settings), methods=["POST"]),
        Route("/downloads/delete/{cid}", needs_setup(downloads_delete), methods=["POST"]),
        Route("/downloads/delete-file/{cid}", needs_setup(downloads_delete_file), methods=["POST"]),
        Route("/downloads/open/{cid}", needs_setup(downloads_open), methods=["POST"]),
        Route("/downloads/{action}", needs_setup(downloads_action), methods=["POST"]),
        Route("/courses/{cid}/offline/video", needs_setup(offline_video), methods=["POST"]),
        Route("/courses/{cid}/offline/status", needs_setup(offline_status)),
        Route("/courses/{cid}/offline/match", needs_setup(offline_match), methods=["POST"]),
        Route("/courses/{cid}/offline/save", needs_setup(offline_save), methods=["POST"]),
        Route("/courses/{cid}/offline/forget", needs_setup(offline_forget), methods=["POST"]),
        Route("/courses/{cid}/offline/folder", needs_setup(offline_folder), methods=["POST"]),
        Route("/courses/{cid}/book", needs_setup(course_book), methods=["POST"]),
        Route("/courses/{cid}/go", needs_setup(course_go)),
        Route("/settings/videos", needs_setup(video_settings), methods=["POST"]),
        Route("/settings/videos/update", needs_setup(video_tool_update), methods=["POST"]),
        Route("/pdf", needs_setup(pdf_reader)),
        Route("/nav.json", needs_setup(nav_index)),
        Route("/settings/colors", needs_setup(set_accent), methods=["POST"]),
        Route("/evidence/{sha}", needs_setup(my_evidence)),
        Route("/courses/{cid}/start", needs_setup(start_course), methods=["POST"]),
        Route("/courses/{cid}/export", needs_setup(export_course)),
        Route("/courses/{cid}/remove", needs_setup(remove_course), methods=["GET", "POST"]),
        Route("/courses/{cid}/update", needs_setup(course_update), methods=["GET", "POST"]),
        Route("/courses/{cid}/refresh", needs_setup(refresh_from_folder), methods=["POST"]),
        Route("/ai", needs_setup(ai_page), methods=["GET", "POST"]),
        Route("/learn/{jid}", needs_setup(course_overview)),
        Route("/learn/{jid}/lesson/{lid}", needs_setup(lesson)),
        Route("/learn/{jid}/module/{mid}", needs_setup(module_page)),
        Route("/learn/{jid}/exam/{eid}", needs_setup(take_exam), methods=["GET", "POST"]),
        Route("/learn/{jid}/exam/{eid}/done", needs_setup(exam_done)),
        Route("/learn/{jid}/do/{action}", needs_setup(journey_action), methods=["POST"]),
        Route("/learn/{jid}/practice", needs_setup(practice), methods=["GET", "POST"]),
        Route("/learn/{jid}/practice/result", needs_setup(practice_result)),
        Route("/learn/{jid}/lesson/{lid}/done", needs_setup(lesson_done), methods=["POST"]),
        Route("/learn/{jid}/lesson/{lid}/notes", needs_setup(add_note), methods=["POST"]),
        Route("/learn/{jid}/notes", needs_setup(notes_page)),
        Route("/learn/{jid}/notes.md", needs_setup(notes_file)),
        Route("/notes/{nid}", needs_setup(edit_note), methods=["POST"]),
        Route("/learn/{jid}/task/{rid}/evidence", needs_setup(add_evidence), methods=["POST"]),
        Route("/learn/{jid}/task/{rid}/git", needs_setup(add_git), methods=["POST"]),
        Route("/learn/{jid}/task/{rid}/writeup", needs_setup(save_writeup), methods=["POST"]),
        Route("/learn/{jid}/task/{rid}/quiz", needs_setup(quiz), methods=["GET", "POST"]),
        Route("/learn/{jid}/task/{rid}/quiz/result", needs_setup(quiz_result)),
        Route("/milestones", needs_setup(milestones)),
        Route("/milestones/{jid}/save", needs_setup(save_milestone), methods=["POST"]),
        Route("/milestones/{jid}/export", needs_setup(export_progress)),
        Route("/milestones/{jid}/files", needs_setup(file_pack)),
        Route("/milestones/{jid}/record", needs_setup(learning_record)),
        Route("/races", needs_setup(races_page)),
        Route("/races/new", needs_setup(race_new), methods=["POST"]),
        Route("/races/join", needs_setup(race_join), methods=["POST"]),
        Route("/races/{rid}", needs_setup(race_page)),
        Route("/races/{rid}/{action}", needs_setup(race_action), methods=["GET", "POST"]),
        Route("/edit/new", needs_setup(edit_new), methods=["GET", "POST"]),
        Route("/edit/{cid}", needs_setup(edit_course), methods=["GET", "POST"]),
        Route("/edit/{cid}/lesson/{lid}", needs_setup(edit_lesson)),
        Route("/edit/{cid}/lesson/{lid}/media", needs_setup(edit_lesson_media), methods=["POST"]),
        Route("/edit/{cid}/image", needs_setup(edit_course_image), methods=["POST"]),
        Route("/edit/{cid}/yaml", needs_setup(edit_yaml), methods=["GET", "POST"]),
        Route("/edit/{cid}/preview", needs_setup(lesson_preview), methods=["POST"]),
        Route("/people", needs_setup(people)),
        Route("/people/card", needs_setup(my_card)),
        Route("/people/add", needs_setup(add_person), methods=["POST"]),
        Route("/link", open_link),
        Route("/people/add-learner", needs_setup(add_person_from_progress), methods=["POST"]),
        Route("/people/{pid}", needs_setup(edit_person), methods=["POST"]),
        Route("/open", needs_setup(open_file), methods=["GET", "POST"]),
        Route("/review/{learner}/{journey}", needs_setup(review), methods=["GET", "POST"]),
        Route("/review/{learner}/{journey}/exam/{rid}", needs_setup(make_exam_page), methods=["GET", "POST"]),
        Route("/files/{sha}", needs_setup(received_file)),
        Route("/outbox/{name}", needs_setup(outbox)),
        Route("/settings", needs_setup(settings), methods=["GET", "POST"]),
        Route("/quit", quit_app, methods=["POST"]),
        Route("/theme", set_theme, methods=["POST"]),
        Route("/settings/look", needs_setup(set_look), methods=["POST"]),
        Route("/island", needs_setup(island)),
        Route("/island/mode", needs_setup(island_mode), methods=["POST"]),
        Route("/island/world", needs_setup(island_world), methods=["POST"]),
        Route("/island/name", needs_setup(island_name), methods=["POST"]),
        Route("/island/buy", needs_setup(island_buy), methods=["POST"]),
        Route("/settings/turtle", needs_setup(settings_turtle), methods=["POST"]),
        Route("/me/turtle.svg", needs_setup(my_turtle_svg)),
        Route("/me/turtle.png", needs_setup(my_turtle_png), methods=["POST"]),
        Route("/island/look", needs_setup(island_look), methods=["POST"]),
        Route("/island/clear", needs_setup(island_clear), methods=["POST"]),
        Route("/island/gentle", needs_setup(island_gentle), methods=["POST"]),
        Route("/island/sharing", needs_setup(island_sharing), methods=["POST"]),
        Route("/island/share.svg", needs_setup(island_share_svg)),
        Route("/island/share.png", needs_setup(island_share_png), methods=["POST"]),
        Route("/people/{pid}/island", needs_setup(person_island)),
        Route("/island/start", needs_setup(island_start), methods=["POST"]),
        Route("/island/trip", needs_setup(island_trip)),
        Route("/island/rest", needs_setup(island_rest), methods=["POST"]),
        Route("/island/let-go", needs_setup(island_letgo), methods=["POST"]),
        Route("/island/pause", needs_setup(island_pause), methods=["POST"]),
        Route("/island/resume", needs_setup(island_resume), methods=["POST"]),
        Route("/island/done", needs_setup(island_done), methods=["POST"]),
        Route("/island/live.json", needs_setup(island_live)),
        Route("/timer.json", needs_setup(timer_json)),
        Route("/window/popout", needs_setup(window_popout), methods=["POST"]),
        Route("/window/popout/close", needs_setup(window_popout_close), methods=["POST"]),
        Route("/timer/{what}", needs_setup(timer_action), methods=["POST"]),
        Route("/settings/timer", needs_setup(timer_settings), methods=["POST"]),
        Route("/tour/done", needs_setup(tour_done), methods=["POST"]),
        Route("/tour/again", needs_setup(tour_again), methods=["POST"]),
        Route("/ping", ping),
        Route("/startup-time", startup_time, methods=["POST"]),
        Route("/updates/setting", needs_setup(update_setting), methods=["POST"]),
        Route("/updates/check", needs_setup(update_check), methods=["POST"]),
        Route("/updates/later", needs_setup(update_later), methods=["POST"]),
        Route("/updates/install", needs_setup(update_install), methods=["POST"]),
        Route("/updates/restart", needs_setup(update_restart), methods=["POST"]),
        Route("/settings/ai", needs_setup(ai_settings), methods=["POST"]),
        Route("/settings/backup", needs_setup(backup), methods=["POST"]),
        Route("/settings/restore", needs_setup(restore), methods=["POST"]),
        Route("/settings/delete-everything", needs_setup(delete_everything), methods=["POST"]),
        Route("/settings/youtube", needs_setup(youtube_setting), methods=["POST"]),
        Mount("/static", StaticFiles(directory=HERE / "static"), name="static"),
    ]
    from starlette.middleware import Middleware

    class LangMiddleware:
        """Set the language before any route runs. Some pages build text (like the tour) before they
        render, so without this the first page after the app starts could come out in English."""

        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http" and not scope.get("path", "").startswith("/static/"):
                try:
                    if V.is_set_up:
                        CURRENT["lang"] = V._meta("lang", "en") or "en"
                except Exception:
                    pass
            return await self.app(scope, receive, send)

    async def page_not_found(request: Request, exc):
        """A link to a page that doesn't exist: in the app window, go home instead of a dead black page you can't
        leave (the window has no browser Back button)."""
        if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
            return RedirectResponse("/", status_code=303)
        return Response("Not found", status_code=404)

    return Starlette(routes=routes, middleware=[Middleware(NavMiddleware), Middleware(LangMiddleware)],
                     exception_handlers={404: page_not_found})
