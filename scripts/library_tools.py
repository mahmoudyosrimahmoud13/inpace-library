"""Tools the library's GitHub Actions run. Needs the inpace package (installed from its repository).

  python scripts/library_tools.py submit EVENT.json   read a submission issue, check the course, add it to courses/
  python scripts/library_tools.py check               check every course in courses/
  python scripts/library_tools.py build _site         build library.json, the course files and the web page
"""
from __future__ import annotations

import hashlib
import html
import io
import json
import os
import re
import shutil
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml
from inpace.course import course_to_files, files_from_folder, load_course, media_kind, safe_media_path
from inpace.exchange import to_link
from inpace.library import AUTHOR_FILE, MAX_COURSE_BYTES, SITE, LibraryProblem, check_author, read_submission, share_data

ROOT = Path(__file__).resolve().parent.parent
COURSES = ROOT / "courses"
LICENSES = ("CC-BY-4.0", "CC-BY-SA-4.0", "CC0-1.0")
ATTACHMENT = re.compile(r"https://github\.com/(?:user-attachments/files|[\w.-]+/[\w.-]+/files)/[^\s)\]>\"']+")


# ---------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------

def form_fields(body: str) -> dict:
    """GitHub issue forms arrive as '### Label' followed by the answer."""
    out, label = {}, None
    for line in (body or "").splitlines():
        m = re.match(r"^###\s+(.*)$", line)
        if m:
            label = m.group(1).strip().lower()
            out[label] = ""
        elif label:
            out[label] += line + "\n"
    return {k: v.strip() for k, v in out.items() if v.strip() != "_No response_"}


def download(url: str) -> bytes:
    headers = {"User-Agent": "inpace-library-bot"}
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
        data = r.read(MAX_COURSE_BYTES + 1)
    if len(data) > MAX_COURSE_BYTES:
        raise LibraryProblem("The course file is over 20 MB. Put big videos somewhere people can download them and "
                             "add the link in inPace (Edit → Course details).")
    return data


def existing_author(cid: str) -> str | None:
    f = COURSES / cid / AUTHOR_FILE
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8")).get("author")
    return "official" if (COURSES / cid).exists() else None


def submit(event_path: str) -> dict:
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    issue = event["issue"]
    fields = form_fields(issue.get("body") or "")
    problems: list[str] = []
    agree = fields.get("before you submit", "")
    if agree.count("[X]") + agree.count("[x]") < 2:
        problems.append("Please tick both boxes under **Before you submit**.")
    lic = next((x for x in LICENSES if fields.get("license", "").startswith(x)), None)
    if not lic:
        problems.append("Please choose a license.")
    urls = [u for u in ATTACHMENT.findall(fields.get("course file", "")) if u.lower().endswith(".zip")]
    if not urls:
        problems.append("I couldn't find the course file. Drag the .zip from inPace into the **Course file** box "
                        "(edit this issue to add it, and I'll check again).")
    if problems:
        return {"ok": False, "problems": problems}
    try:
        data = download(urls[-1])
        course, author = read_submission(data)
    except LibraryProblem as e:
        return {"ok": False, "problems": [str(e)]}
    except Exception as e:  # network trouble, broken zip...
        return {"ok": False, "problems": [f"I couldn't open the course file ({type(e).__name__}). Try attaching it again."]}

    owner = existing_author(course.id)
    if owner == "official":
        return {"ok": False, "problems": [f"The id `{course.id}` is used by a course the library team looks after. "
                                          "Change your course's id in inPace (Edit as one file) and publish again."]}
    if owner and owner != author["author"]:
        return {"ok": False, "problems": [f"A course with the id `{course.id}` was published by someone else. "
                                          "Only its author can update it. Change your course's id and publish again."]}
    if owner:
        old = load_course(files_from_folder(COURSES / course.id))
        if old.hash == course.hash:
            return {"ok": False, "problems": ["This is the same as the version already in the library. Change the course "
                                              "in inPace first, then publish again."]}

    target = COURSES / course.id
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    for name, text in course_to_files(course, True).items():
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        (target / name).write_text(text, encoding="utf-8")
    zf = zipfile.ZipFile(io.BytesIO(data))
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        if "/files/" in "/" + name and not info.is_dir():
            rel = safe_media_path(name.split("files/", 1)[1])
            if rel:
                out = target / "files" / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(zf.read(info))
    (target / AUTHOR_FILE).write_text(json.dumps(author, ensure_ascii=False, indent=1), encoding="utf-8")
    tags = [t.strip().lower() for t in fields.get("tags", "").split(",") if t.strip()][:8]
    meta = {"license": lic, "tags": tags, "submitted_by": issue["user"]["login"], "issue": issue["number"],
            "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    (target / "library.yaml").write_text(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return {"ok": True, "id": course.id, "title": course.title, "version": course.version, "update": bool(owner),
            "author": author["name"], "downloads": course.extra.get("downloads", [])}


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def load(folder: Path):
    course = load_course(files_from_folder(folder))
    meta = yaml.safe_load((folder / "library.yaml").read_text(encoding="utf-8")) if (folder / "library.yaml").exists() else {}
    author = None
    if (folder / AUTHOR_FILE).exists():
        author = json.loads((folder / AUTHOR_FILE).read_text(encoding="utf-8"))
    return course, meta or {}, author


def check() -> int:
    bad = 0
    for folder in sorted(p for p in COURSES.iterdir() if p.is_dir()):
        try:
            course, meta, author = load(folder)
            problems = []
            if course.id != folder.name:
                problems.append(f"the folder is named {folder.name} but the course id is {course.id}")
            if meta.get("license") not in LICENSES:
                problems.append("library.yaml needs a license: " + ", ".join(LICENSES))
            if author:
                p = check_author(author, course)
                if p:
                    problems.append(p)
            elif not meta.get("official"):
                problems.append("not signed by its author (only courses marked official: true may be unsigned)")
            size = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())
            if size > MAX_COURSE_BYTES:
                problems.append("bigger than 20 MB")
            if problems:
                raise ValueError("; ".join(problems))
            print(f"OK   {folder.name}: {course.title} (v{course.version}, {len(course.modules)} modules)")
        except Exception as e:
            bad += 1
            print(f"FAIL {folder.name}: {e}")
    return 1 if bad else 0


# ---------------------------------------------------------------------------
# The published site: library.json, course files, covers and a web page
# ---------------------------------------------------------------------------

def pack(folder: Path) -> bytes:
    """The same bytes every time for the same course, so the checksum only changes when the course does."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(p for p in folder.rglob("*") if p.is_file() and p.name != "library.yaml"):
            info = zipfile.ZipInfo(f.relative_to(folder).as_posix(), date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, f.read_bytes())
    return buf.getvalue()


def build(out: Path) -> None:
    shutil.rmtree(out, ignore_errors=True)
    (out / "packs").mkdir(parents=True)
    (out / "covers").mkdir()
    entries = []
    for folder in sorted(p for p in COURSES.iterdir() if p.is_dir()):
        course, meta, author = load(folder)
        data = pack(folder)
        (out / "packs" / f"{course.id}.zip").write_bytes(data)
        cover = None
        img = course.extra.get("image")
        if img and (folder / "files" / img).is_file() and media_kind(img) == "image":
            name = f"{course.id}{Path(img).suffix.lower()}"
            shutil.copyfile(folder / "files" / img, out / "covers" / name)
            cover = SITE + "covers/" + name
        verified = bool(author and not check_author(author, course))
        entry = {
            "id": course.id, "title": course.title, "description": course.description, "language": course.language,
            "version": course.version, "hash": course.hash, "modules": len(course.modules),
            "lessons": course.lesson_count,
            "minutes": sum(int(les.get("minutes") or 0) for m in course.modules for les in m["lessons"]),
            "tags": meta.get("tags", []), "license": meta.get("license"),
            "author": {"name": author["name"] if author else meta.get("author", "inPace"),
                       "id": author["author"] if author else None, "verified": verified or bool(meta.get("official"))},
            "downloads": course.extra.get("downloads", []),
            "cover": cover, "pack": SITE + f"packs/{course.id}.zip",
            "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "updated": meta.get("updated"),
        }
        entry["link"] = to_link(share_data(entry))
        entries.append(entry)
    index = {"inpace": "library", "v": 1, "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "courses": entries}
    (out / "library.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "index.html").write_text(page(entries), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    print(f"Built {len(entries)} courses into {out}")


SITE_MAIN = "https://mahmoudyosrimahmoud13.github.io/inPace/"
FORM = "https://github.com/mahmoudyosrimahmoud13/inpace-library/issues/new?template=submit-course.yml"
REPORT = "https://github.com/mahmoudyosrimahmoud13/inpace-library/issues/new?template=report.yml"


def t(en: str, ar: str) -> str:
    """Both languages; the page shows the one the visitor picked."""
    return f'<span class="en">{en}</span><span class="ar">{ar}</span>'


def page(entries: list[dict]) -> str:
    e = html.escape
    cards = []
    for c in entries:
        cover = (f'<img src="{e(c["cover"])}" alt="" loading="lazy">' if c["cover"]
                 else f'<span class="blank">{e(c["title"][:1].upper())}</span>')
        tags = "".join(f"<span class=chip>{e(x)}</span>" for x in c["tags"][:5])
        dl = ""
        if c["downloads"]:
            d = c["downloads"][0]
            size = " · " + e(d["size"]) if d.get("size") else ""
            dl = f'<p class="dl">🎬 {t("Videos download separately", "الفيديوهات تُحمّل منفصلة")}{size}</p>'
        words = " ".join([c["id"], c["title"], c["description"], c["author"]["name"]] + c["tags"]).lower()
        lang = t("Arabic", "العربية") if c["language"] == "ar" else t("English", "الإنجليزية")
        tick = " ✓" if c["author"]["verified"] else ""
        cards.append(f"""<article class="card" id="{e(c["id"])}" data-q="{e(words)}">
  {cover}
  <div class="body">
    <h2 dir="auto">{e(c["title"])}</h2>
    <p dir="auto">{e(c["description"])}</p>
    <p class="meta">{c["modules"]} {t("modules", "وحدة")} · {c["lessons"]} {t("lessons", "درس")} · {lang}
      · {t("by", "من إعداد")} <bdi>{e(c["author"]["name"])}</bdi>{tick} · <bdi>{e(c["license"] or "")}</bdi></p>
    {dl}<p>{tags}</p>
    <p class="actions"><a class="btn primary" href="{e(c["link"])}">{t("Add to inPace", "أضف إلى inPace")}</a>
      <button class="btn" type="button" data-copy="{e(c["link"])}">{t("Copy link", "انسخ الرابط")}</button>
      <a class="btn quiet" href="{e(c["pack"])}" download>{t("Download file", "حمّل الملف")}</a></p>
  </div>
</article>""")
    return f"""<!doctype html>
<html lang="en" dir="ltr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>inPace course library</title>
<meta name="description" content="Free courses made and shared by inPace learners. Add one to inPace with a click.">
<link rel="icon" href="{SITE_MAIN}assets/icon.svg" type="image/svg+xml">
<script>
  (function () {{
    var lang = null;
    try {{ lang = localStorage.getItem("inpace-site-lang"); }} catch (e) {{}}
    if (!lang) lang = (navigator.language || "").toLowerCase().indexOf("ar") === 0 ? "ar" : "en";
    document.documentElement.lang = lang; document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }})();
</script>
<style>
:root {{ --ink:#111; --paper:#F7F3EA; --cream:#F2EDE2; --surface:#fff; --sun:#FFD43B; --muted:#4F4A40; color-scheme: light; }}
@media (prefers-color-scheme: dark) {{ :root {{ --ink:#F2EDE2; --paper:#12110E; --cream:#1E1C17; --surface:#1C1A15; --sun:#E2BD4C; --muted:#B5AD9C; color-scheme: dark; }} }}
* {{ box-sizing: border-box; }}
html[lang=ar] .en, html[lang=en] .ar {{ display: none !important; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font:17px/1.6 system-ui, "Segoe UI", Tahoma, sans-serif; }}
a {{ color: inherit; }}
.top {{ position: sticky; top: 0; z-index: 5; display: flex; align-items: center; gap: 1rem; padding: .7rem 16px; background: var(--cream); border-bottom: 3px solid var(--ink); }}
.brand {{ display: flex; align-items: center; gap: .5rem; text-decoration: none; font-size: 1.35rem; font-weight: 800; }}
.brand span {{ font-weight: 300; }}
.top nav {{ margin-inline-start: auto; display: flex; gap: 1rem; font-weight: 600; }}
.top nav a {{ text-decoration: none; }}
.lang {{ font: inherit; font-weight: 700; cursor: pointer; background: var(--surface); color: var(--ink); border: 3px solid var(--ink); padding: .25rem .8rem; }}
@media (max-width: 640px) {{ .top nav {{ display: none; }} .lang {{ margin-inline-start: auto; }} }}
header, main, .share {{ max-width: 1000px; margin: 0 auto; padding-inline: 16px; }}
header {{ padding-block: 2.5rem 1rem; }}
h1 {{ font-size: clamp(2rem, 6vw, 3.2rem); margin: 0 0 .5rem; line-height: 1.15; }}
header p {{ color: var(--muted); max-width: 42em; margin: 0 0 1.2rem; }}
input {{ font: inherit; width: 100%; max-width: 480px; padding: .7rem .9rem; border: 3px solid var(--ink); background: var(--surface); color: var(--ink); }}
main {{ padding-block: 1rem 3rem; display: grid; gap: 1.2rem; }}
.card {{ display: grid; grid-template-columns: 200px minmax(0,1fr); gap: 1.2rem; background: var(--surface); border: 3px solid var(--ink); box-shadow: 6px 6px 0 var(--ink); padding: 1.2rem; }}
[dir=rtl] .card {{ box-shadow: -6px 6px 0 var(--ink); }}
.card:target {{ box-shadow: 6px 6px 0 var(--sun); }}
.card img, .blank {{ width: 100%; aspect-ratio: 16/10; object-fit: cover; border: 2px solid var(--ink); }}
.blank {{ display: grid; place-items: center; font-size: 3rem; font-weight: 800; background: var(--sun); color: #111; }}
h2 {{ margin: 0 0 .3rem; font-size: 1.35rem; }} .card p {{ margin: .3rem 0; }}
.meta {{ color: var(--muted); font-size: .92rem; }} .dl {{ font-size: .92rem; font-weight: 600; }}
.chip {{ display: inline-block; border: 2px solid var(--ink); padding: 0 .45rem; margin: 0 0 .3rem .3rem; font-size: .82rem; }}
.btn {{ display: inline-block; padding: .5rem .9rem; border: 3px solid var(--ink); text-decoration: none; color: var(--ink); font: inherit; font-weight: 700;
  margin: .3rem 0 0 .4rem; background: var(--surface); cursor: pointer; }}
.btn.primary {{ background: var(--ink); color: var(--paper); }}
.btn.quiet {{ border-color: transparent; text-decoration: underline; }}
.empty {{ color: var(--muted); }}
.share {{ padding-block: 1rem 4rem; }}
.share > div {{ background: var(--sun); color: #111; border: 3px solid var(--ink); padding: 1.5rem; }}
.share h2 {{ font-size: 1.6rem; margin-bottom: .6rem; }}
.share ol {{ margin: .5rem 0 1rem; padding-inline-start: 1.3rem; }} .share li {{ margin: .35rem 0; }}
.share .btn {{ margin-inline: 0 .5rem; }}
footer {{ text-align: center; padding: 2rem 16px; color: var(--muted); font-size: .92rem; }}
@media (max-width: 640px) {{ .card {{ grid-template-columns: 1fr; }} }}
</style></head><body>
<div class="top">
  <a class="brand" href="{SITE_MAIN}"><img src="{SITE_MAIN}assets/icon.svg" width="30" height="30" alt=""><b><span>in</span>Pace</b></a>
  <nav><a href="{SITE_MAIN}">{t("Home", "الرئيسية")}</a><a href="{SITE_MAIN}guide.html">{t("Guide", "الدليل")}</a>
    <a href="#share">{t("Share your course", "شارك دورتك")}</a><a href="{SITE_MAIN}#download">{t("Download inPace", "حمّل inPace")}</a></nav>
  <button class="lang" type="button" id="lang">{t("عربي", "English")}</button>
</div>
<header>
  <h1>{t("The inPace course library", "مكتبة دورات inPace")}</h1>
  <p>{t("Free courses made and shared by people who learn with inPace. Press <b>Add to inPace</b>, and the course opens in the app, ready to start. Your progress stays on your computer.",
        "دورات مجانية صنعها وشاركها متعلمون يستخدمون inPace. اضغط <b>أضف إلى inPace</b> فتفتح الدورة في التطبيق جاهزة للبدء. ويبقى تقدّمك على جهازك.")}</p>
  <input type="search" id="q" placeholder="Search courses" aria-label="Search courses" dir="auto">
</header>
<main id="list">
{"".join(cards) or '<p class="empty">' + t("No courses yet.", "لا توجد دورات بعد.") + '</p>'}
<p class="empty" id="none" hidden>{t("No course matches that.", "لا توجد دورة تطابق ذلك.")}</p>
</main>
<section class="share" id="share"><div>
  <h2>{t("Share your own course", "شارك دورتك")}</h2>
  <ol>
    <li>{t("Make your course in inPace: by hand, with AI, or from a folder of videos.", "اصنع دورتك في inPace: بنفسك، أو بالذكاء الاصطناعي، أو من مجلد فيديوهات.")}</li>
    <li>{t("In <b>My courses</b>, open <b>More</b> on the course and choose <b>Publish to the library</b>.", "في <b>دوراتي</b>، افتح <b>المزيد</b> على الدورة واختر <b>انشر في المكتبة</b>.")}</li>
    <li>{t("Download the course file, open the form, drop the file in and submit. A bot checks it in a few minutes.", "حمّل ملف الدورة، وافتح النموذج، واسحب الملف إليه وأرسله. يفحصه روبوت خلال دقائق.")}</li>
  </ol>
  <p>{t("Big videos? Upload them to Google Drive, MEGA or archive.org and add the download link in the course details. Only share what you made yourself.",
        "فيديوهات كبيرة؟ ارفعها إلى Google Drive أو MEGA أو archive.org وأضف رابط التحميل في تفاصيل الدورة. شارك فقط ما صنعته بنفسك.")}</p>
  <p><a class="btn" href="{SITE_MAIN}#download">{t("Get inPace", "احصل على inPace")}</a>
     <a class="btn" href="{FORM}">{t("Open the submission form", "افتح نموذج الإرسال")}</a></p>
</div></section>
<footer>{t("Something wrong with a course?", "مشكلة في دورة؟")} <a href="{REPORT}">{t("Report it", "أبلغ عنها")}</a> ·
  <a href="https://github.com/mahmoudyosrimahmoud13/inpace-library">GitHub</a></footer>
<script>
var html = document.documentElement, q = document.getElementById("q"), cards = [].slice.call(document.querySelectorAll(".card"));
function labels() {{ var ar = html.lang === "ar"; q.placeholder = ar ? "ابحث في الدورات" : "Search courses"; q.setAttribute("aria-label", q.placeholder); }}
labels();
document.getElementById("lang").addEventListener("click", function () {{
  var next = html.lang === "ar" ? "en" : "ar"; html.lang = next; html.dir = next === "ar" ? "rtl" : "ltr";
  try {{ localStorage.setItem("inpace-site-lang", next); }} catch (e) {{}}
  labels();
}});
q.addEventListener("input", function () {{
  var w = q.value.toLowerCase().split(/\\s+/).filter(Boolean), shown = 0;
  cards.forEach(function (c) {{ var ok = w.every(function (x) {{ return c.dataset.q.indexOf(x) >= 0; }}); c.hidden = !ok; shown += ok; }});
  document.getElementById("none").hidden = shown > 0;
}});
[].forEach.call(document.querySelectorAll("[data-copy]"), function (b) {{
  b.addEventListener("click", function () {{
    var old = b.innerHTML;
    navigator.clipboard.writeText(b.dataset.copy).then(function () {{
      b.textContent = html.lang === "ar" ? "تم النسخ!" : "Copied!"; setTimeout(function () {{ b.innerHTML = old; }}, 1600); }});
  }});
}});
if (location.hash) {{ var el = document.getElementById(decodeURIComponent(location.hash.slice(1))); if (el) el.scrollIntoView(); }}
</script>
</body></html>
"""


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "submit":
        result = submit(sys.argv[2])
        Path(os.environ.get("RESULT_FILE", "result.json")).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=1))
    elif cmd == "check":
        sys.exit(check())
    elif cmd == "build":
        build(Path(sys.argv[2] if len(sys.argv) > 2 else "_site"))
    else:
        print(__doc__)
        sys.exit(2)
