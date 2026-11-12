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


def page(entries: list[dict]) -> str:
    e = html.escape
    cards = []
    for c in entries:
        cover = (f'<img src="{e(c["cover"])}" alt="" loading="lazy">' if c["cover"]
                 else f'<span class="blank">{e(c["title"][:1].upper())}</span>')
        tags = "".join(f"<span class=chip>{e(t)}</span>" for t in c["tags"][:5])
        dl = ""
        if c["downloads"]:
            d = c["downloads"][0]
            dl = f'<p class="dl">Videos download separately{" · " + e(d["size"]) if d.get("size") else ""}</p>'
        words = " ".join([c["id"], c["title"], c["description"], c["author"]["name"]] + c["tags"]).lower()
        cards.append(f'''<article class="card" id="{e(c["id"])}" data-q="{e(words)}" dir="auto">
  {cover}
  <div class="body">
    <h2>{e(c["title"])}</h2>
    <p>{e(c["description"])}</p>
    <p class="meta">{c["modules"]} modules · {c["lessons"]} lessons · {"العربية" if c["language"] == "ar" else "English"}
      · by {e(c["author"]["name"])}{" ✓" if c["author"]["verified"] else ""} · {e(c["license"] or "")}</p>
    {dl}<p>{tags}</p>
    <p class="actions"><a class="btn primary" href="{e(c["link"])}">Add to inPace</a>
      <button class="btn" type="button" data-copy="{e(c["link"])}">Copy link</button>
      <a class="btn" href="{e(c["pack"])}" download>Download</a></p>
  </div>
</article>''')
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>inPace course library</title>
<meta name="description" content="Free courses made and shared by inPace learners.">
<link rel="icon" href="https://mahmoudyosrimahmoud13.github.io/inPace/assets/icon.svg" type="image/svg+xml">
<style>
:root {{ --ink:#111; --paper:#F7F3EA; --surface:#fff; --sun:#FFD43B; --muted:#4F4A40; color-scheme: light; }}
@media (prefers-color-scheme: dark) {{ :root {{ --ink:#F2EDE2; --paper:#12110E; --surface:#1C1A15; --muted:#B5AD9C; color-scheme: dark; }} }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font:17px/1.55 system-ui, sans-serif; }}
header {{ padding: 2.5rem 16px 1rem; max-width: 1000px; margin: 0 auto; }}
h1 {{ font-size: clamp(2rem, 6vw, 3.2rem); margin: 0 0 .4rem; line-height:1.1; }}
header p {{ color: var(--muted); max-width: 40em; }}
input {{ font: inherit; width: 100%; max-width: 480px; padding: .7rem .9rem; border: 3px solid var(--ink); background: var(--surface); color: var(--ink); }}
main {{ max-width: 1000px; margin: 0 auto; padding: 1rem 16px 4rem; display: grid; gap: 1.2rem; }}
.card {{ display: grid; grid-template-columns: 200px minmax(0,1fr); gap: 1.2rem; background: var(--surface); border: 3px solid var(--ink);
  box-shadow: 6px 6px 0 var(--ink); padding: 1.2rem; }}
.card:target {{ box-shadow: 6px 6px 0 var(--sun); }}
.card img, .blank {{ width: 100%; aspect-ratio: 16/10; object-fit: cover; border: 2px solid var(--ink); }}
.blank {{ display: grid; place-items: center; font-size: 3rem; font-weight: 800; background: var(--sun); color: #111; }}
h2 {{ margin: 0 0 .3rem; font-size: 1.35rem; }} .card p {{ margin: .3rem 0; }}
.meta {{ color: var(--muted); font-size: .92rem; }} .dl {{ font-size: .92rem; font-weight: 600; }}
.chip {{ display: inline-block; border: 2px solid var(--ink); padding: 0 .45rem; margin: 0 .3rem .3rem 0; font-size: .82rem; }}
.btn {{ display: inline-block; padding: .5rem .9rem; border: 3px solid var(--ink); text-decoration: none; color: var(--ink);
  font-weight: 700; margin: .3rem .4rem 0 0; background: var(--surface); }}
.btn.primary {{ background: var(--ink); color: var(--paper); }}
button.btn {{ font: inherit; font-weight: 700; cursor: pointer; }}
.empty {{ color: var(--muted); }}
@media (max-width: 640px) {{ .card {{ grid-template-columns: 1fr; }} }}
</style></head><body>
<header>
  <h1>The inPace course library</h1>
  <p>Free courses made and shared by people who learn with <a href="https://mahmoudyosrimahmoud13.github.io/inPace/">inPace</a>.
     Press <b>Add to inPace</b>, or open the Course library inside the app. To share your own course, use
     <b>My courses → More → Publish to the library</b> in inPace.</p>
  <input type="search" id="q" placeholder="Search courses" aria-label="Search courses">
</header>
<main id="list">
{"".join(cards) or '<p class="empty">No courses yet.</p>'}
<p class="empty" id="none" hidden>No course matches that.</p>
</main>
<script>
var q = document.getElementById("q"), cards = [].slice.call(document.querySelectorAll(".card"));
q.addEventListener("input", function () {{
  var w = q.value.toLowerCase().split(/\\s+/).filter(Boolean), shown = 0;
  cards.forEach(function (c) {{ var ok = w.every(function (x) {{ return c.dataset.q.indexOf(x) >= 0; }}); c.hidden = !ok; shown += ok; }});
  document.getElementById("none").hidden = shown > 0;
}});
[].forEach.call(document.querySelectorAll("[data-copy]"), function (b) {{
  b.addEventListener("click", function () {{
    navigator.clipboard.writeText(b.dataset.copy).then(function () {{ b.textContent = "Copied!"; setTimeout(function () {{ b.textContent = "Copy link"; }}, 1600); }});
  }});
}});
if (location.hash) {{ var t = document.getElementById(decodeURIComponent(location.hash.slice(1))); if (t) t.scrollIntoView(); }}
</script>
</body></html>
'''


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
