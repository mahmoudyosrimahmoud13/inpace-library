"""Tools the library's GitHub Actions run. Needs the inpace package (installed from its repository).

  python scripts/library_tools.py submit EVENT.json   read a submission issue, check the course (or roadmap), add it
  python scripts/library_tools.py check               check every course in courses/ and roadmap in roadmaps/
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
ROADMAPS = ROOT / "roadmaps"  # roadmaps (inPace 1.24+): a path through several courses of the library, as YAML
ROADMAP_VERSION = "1.24"
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
    if any(l.get("name") == "roadmap-submission" for l in issue.get("labels") or []):
        return submit_roadmap(event)
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
    return {"ok": True, "kind": "course", "id": course.id, "title": course.title, "version": course.version,
            "update": bool(owner), "author": author["name"], "downloads": course.extra.get("downloads", []),
            "path": f"courses/{course.id}"}


# ---------------------------------------------------------------------------
# Roadmaps (inPace 1.24): a path through several courses that are in the library
# ---------------------------------------------------------------------------

class RoadmapProblem(Exception):
    pass


def parse_roadmap(text: str) -> dict:
    """Read a roadmap the same way the app does (inpace.roadmaps), or with a small fallback for older installs."""
    try:
        from inpace.roadmaps import RoadmapError, parse
    except ImportError:  # the inpace package from before 1.24: the basic checks only
        data = yaml.safe_load(text)
        if not isinstance(data, dict) or not data.get("title") or not isinstance(data.get("steps"), list) or not data["steps"]:
            raise RoadmapProblem("A roadmap needs a title and at least one course under steps.")
        steps = [s if isinstance(s, dict) else {"course": str(s)} for s in data["steps"]]
        return {**data, "author": str(data.get("author") or ""), "tags": data.get("tags") or [], "steps": steps,
                "language": data.get("language") or "en", "description": data.get("description") or ""}
    try:
        return parse(text, "library")
    except RoadmapError as e:
        raise RoadmapProblem(" ".join(e.problems))


def roadmap_meta(path: Path) -> dict:
    """Fields the app doesn't need but the library does (official, submitted_by), straight from the YAML."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {k: data[k] for k in ("official", "order", "submitted_by", "issue", "updated") if k in data}


def load_roadmaps() -> list[tuple[Path, dict]]:
    """Every roadmap, the library team's picks first (order: in the YAML), then the newest."""
    if not ROADMAPS.is_dir():
        return []
    found = [(f, parse_roadmap(f.read_text(encoding="utf-8"))) for f in ROADMAPS.glob("*.yaml")]
    def key(item):
        meta = roadmap_meta(item[0])
        return (int(meta.get("order") or 999), "" if meta.get("order") else str(-int(str(meta.get("updated") or "0").replace("-", "") or 0)), item[1]["title"])
    return sorted(found, key=key)


def roadmap_problems(path: Path | None, rm: dict, course_ids: set[str]) -> list[str]:
    problems = []
    if path is not None and rm["id"] != path.stem:
        problems.append(f"the file is named {path.name} but the roadmap id is {rm['id']}")
    missing = [s["course"] for s in rm["steps"] if s["course"] not in course_ids]
    if missing:
        problems.append("these courses aren't in the library: " + ", ".join(missing))
    return problems


def submit_roadmap(event: dict) -> dict:
    """A "Submit a roadmap" issue: the roadmap's YAML pasted in the form. Checks it and writes roadmaps/<id>.yaml."""
    issue = event["issue"]
    fields = form_fields(issue.get("body") or "")
    problems = []
    agree = fields.get("before you submit", "")
    if agree.count("[X]") + agree.count("[x]") < 1:
        problems.append("Please tick the box under **Before you submit**.")
    text = re.sub(r"^```(?:ya?ml)?\s*|```\s*$", "", fields.get("roadmap", "").strip())
    if not text:
        problems.append("I couldn't find the roadmap. In inPace, open the roadmap, press **Share**, then "
                        "**Open the form**: the roadmap is filled in for you.")
    if problems:
        return {"ok": False, "problems": problems, "kind": "roadmap"}
    try:
        rm = parse_roadmap(text)
    except RoadmapProblem as e:
        return {"ok": False, "problems": [str(e)], "kind": "roadmap"}
    except Exception:
        return {"ok": False, "problems": ["The roadmap couldn't be read. Copy it again from inPace (Share → Copy the roadmap)."],
            "kind": "roadmap"}
    course_ids = {p.name for p in COURSES.iterdir() if p.is_dir()}
    found = roadmap_problems(None, rm, course_ids)
    if found:
        return {"ok": False, "problems": [f"A library roadmap can only use courses in the library: {found[0].split(': ', 1)[1]}. "
                                          "Publish those courses first, or take them off the roadmap."], "kind": "roadmap"}
    target = ROADMAPS / f"{rm['id']}.yaml"
    login = issue["user"]["login"]
    update = target.exists()
    if update:
        old = roadmap_meta(target)
        if old.get("official") or old.get("submitted_by") != login:
            return {"ok": False, "problems": [f"A roadmap with the id `{rm['id']}` is already in the library, made by someone else. "
                                              "Give yours another title in inPace and submit again."], "kind": "roadmap"}
        if parse_roadmap(target.read_text(encoding="utf-8"))["steps"] == rm["steps"] and \
                parse_roadmap(target.read_text(encoding="utf-8"))["title"] == rm["title"]:
            return {"ok": False, "problems": ["This is the same as the version already in the library."], "kind": "roadmap"}
    data = {"id": rm["id"], "title": rm["title"], "description": rm.get("description", ""), "language": rm.get("language", "en"),
            "author": rm.get("author") or login, "tags": rm.get("tags", []),
            "steps": [{k: st[k] for k in ("course", "note", "optional") if st.get(k)} for st in rm["steps"]],
            "submitted_by": login, "issue": issue["number"], "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    ROADMAPS.mkdir(exist_ok=True)
    target.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=110), encoding="utf-8")
    return {"ok": True, "kind": "roadmap", "id": rm["id"], "title": rm["title"], "update": update,
            "author": data["author"], "path": f"roadmaps/{rm['id']}.yaml", "courses": len(rm["steps"])}


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
    course_ids = {p.name for p in COURSES.iterdir() if p.is_dir()}
    for f in sorted(ROADMAPS.glob("*.yaml")) if ROADMAPS.is_dir() else []:
        try:
            rm = parse_roadmap(f.read_text(encoding="utf-8"))
            problems = roadmap_problems(f, rm, course_ids)
            if problems:
                raise ValueError("; ".join(problems))
            print(f"OK   roadmaps/{f.name}: {rm['title']} ({len(rm['steps'])} courses)")
        except Exception as e:
            bad += 1
            print(f"FAIL roadmaps/{f.name}: {e}")
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
        entry["outline"] = outline(course)
        entry["sample"] = sample(course)
        if meta.get("credit"):
            entry["credit"] = str(meta["credit"])
        if course.extra.get("book_info"):  # a book each learner gets themselves (never inside the course)
            entry["book"] = course.extra["book_info"]
        entry["link"] = to_link(share_data(entry))
        entries.append(entry)
    by_id = {c["id"]: c for c in entries}
    road = []
    for f, rm in load_roadmaps():
        problems = roadmap_problems(f, rm, set(by_id))
        if problems:
            raise SystemExit(f"roadmaps/{f.name}: " + "; ".join(problems))
        meta = roadmap_meta(f)
        steps = [{k: st[k] for k in ("course", "note", "optional") if st.get(k)} for st in rm["steps"]]
        entry = {"id": rm["id"], "title": rm["title"], "description": rm.get("description", ""),
                 "language": rm.get("language", "en"), "tags": rm.get("tags", []),
                 "author": {"name": rm.get("author") or "inPace", "verified": bool(meta.get("official"))},
                 "steps": steps, "courses": len(steps),
                 "minutes": sum(by_id[st["course"]].get("minutes") or 0 for st in steps),
                 "lessons": sum(by_id[st["course"]].get("lessons") or 0 for st in steps),
                 "updated": meta.get("updated"), "needs": ROADMAP_VERSION}
        entry["hash"] = hashlib.sha256(json.dumps({"title": entry["title"], "description": entry["description"], "steps": steps},
                                                  sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
        entry["link"] = to_link({"inpace": "library-roadmap", "id": entry["id"], "title": entry["title"],
                                 "author": entry["author"]["name"]})
        road.append(entry)
    for c in entries:  # each course knows the roadmaps it's on (for its page)
        c["roadmaps"] = [r["id"] for r in road if any(st["course"] == c["id"] for st in r["steps"])]
    index = {"inpace": "library", "v": 1, "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "courses": entries, "roadmaps": road}
    (out / "library.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    # A tiny summary other pages can read (inPace's website shows the number of courses from it).
    stats = {"courses": len(entries), "lessons": sum(c["lessons"] for c in entries),
             "hours": round(sum(c.get("minutes") or 0 for c in entries) / 60),
             "languages": sorted({c["language"] for c in entries}), "roadmaps": len(road), "updated": index["updated"]}
    (out / "stats.json").write_text(json.dumps(stats), encoding="utf-8")
    (out / "index.html").write_text(page(entries, road), encoding="utf-8")
    (out / "c").mkdir()
    for entry in entries:
        (out / "c" / f"{entry['id']}.html").write_text(course_page(entry, road), encoding="utf-8")
    (out / "r").mkdir()
    for r in road:
        (out / "r" / f"{r['id']}.html").write_text(roadmap_page(r, by_id), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    print(f"Built {len(entries)} courses and {len(road)} roadmaps into {out}")


SITE_MAIN = "https://mahmoudyosrimahmoud13.github.io/inPace/"
FORM = "https://github.com/mahmoudyosrimahmoud13/inpace-library/issues/new?template=submit-course.yml"
FORM_ROADMAP = "https://github.com/mahmoudyosrimahmoud13/inpace-library/issues/new?template=submit-roadmap.yml"
REPORT = "https://github.com/mahmoudyosrimahmoud13/inpace-library/issues/new?template=report.yml"


def t(en: str, ar: str) -> str:
    """Both languages; the page shows the one the visitor picked."""
    return f'<span class="en">{en}</span><span class="ar">{ar}</span>'


def outline(course) -> list[dict]:
    """Modules, lessons and tasks, so people can see what's inside before adding a course (no answers)."""
    mods = []
    for m in course.modules:
        lessons = []
        for les in m["lessons"]:
            kind = ""
            if les.get("media"):
                ref = str(les["media"]).split("#")[0]
                kind = media_kind(ref) or ("video" if "youtu" in ref else "")
            lessons.append({"title": les["title"], "minutes": int(les.get("minutes") or 0), "media": kind})
        tasks = []
        for r in m["requires"]:
            if r["type"] == "quiz":
                tasks.append({"type": "quiz", "questions": len(r.get("questions") or [])})
            else:
                tasks.append({"type": r["type"], "prompt": str(r.get("prompt", ""))[:400]})
        mods.append({"title": m["title"], "lessons": lessons, "tasks": tasks})
    return mods


def sample(course) -> dict | None:
    """One lesson to read before adding: the longer of the first two lessons of the first module."""
    if not course.modules or not course.modules[0]["lessons"]:
        return None
    first = [les for les in course.modules[0]["lessons"][:2] if (les.get("content") or "").strip()]
    if not first:
        return None
    les = max(first, key=lambda x: len(x["content"]))
    text = les["content"]
    if len(text) > 9000:
        text = text[:9000].rsplit("\n\n", 1)[0] + "\n\n…"
    return {"title": les["title"], "text": text}


ICONS = {
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "layers": '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    "doc": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    "video": '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="m16 10 5-3v10l-5-3"/>',
    "check": '<path d="m5 12 4 4 10-10"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    "back": '<path d="M15 6l-6 6 6 6"/>',
    "route": '<circle cx="6" cy="19" r="2.2"/><circle cx="18" cy="5" r="2.2"/><path d="M8.2 19H15a3.5 3.5 0 0 0 0-7H9a3.5 3.5 0 0 1 0-7h6.8"/>',
}


def ic(name: str) -> str:
    return (f'<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def hours(minutes: int) -> str:
    if not minutes:
        return ""
    if minutes < 90:
        return t(f"{minutes} min of lessons", f"{minutes} دقيقة من الدروس")
    h = round(minutes / 60)
    return t(f"about {h} h of lessons", f"حوالي {h} ساعة من الدروس")


def lang_name(code: str) -> str:
    return t("Arabic", "العربية") if code == "ar" else t("English", "الإنجليزية")


def cover_html(c: dict, root: str) -> str:
    e = html.escape
    if c.get("cover"):
        return f'<img class="cover" src="{e(c["cover"])}" alt="" loading="lazy">'
    hue = (len(c["id"]) * 47) % 360
    return f'<span class="cover blank" style="--hue:{hue}" aria-hidden="true">{e(c["title"][:1].upper())}</span>'


STYLE = """
:root { --ink:#111; --paper:#F7F3EA; --cream:#F2EDE2; --surface:#fff; --sun:#FFD43B; --sky:#CDE8F2; --pink:#E6007E;
  --muted:#4F4A40; --hair:#DDD5C4; color-scheme: light; }
@media (prefers-color-scheme: dark) { :root:not([data-theme=light]) { --ink:#F2EDE2; --paper:#12110E; --cream:#1E1C17; --surface:#1C1A15; --sun:#E2BD4C; --sky:#2A3A40; --muted:#B5AD9C; --hair:#3A362D; color-scheme: dark; } }
:root[data-theme=dark] { --ink:#F2EDE2; --paper:#12110E; --cream:#1E1C17; --surface:#1C1A15; --sun:#E2BD4C; --sky:#2A3A40; --muted:#B5AD9C; --hair:#3A362D; color-scheme: dark; }
* { box-sizing: border-box; }
html[lang=ar] .en, html[lang=en] .ar { display: none !important; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 17px/1.6 "Readex Pro", system-ui, "Segoe UI", Tahoma, sans-serif;
  background-image: repeating-linear-gradient(60deg, rgba(127,127,127,.07) 0 1px, transparent 1px 24px), repeating-linear-gradient(-60deg, rgba(127,127,127,.07) 0 1px, transparent 1px 24px); }
a { color: inherit; }
.i { width: 1.05em; height: 1.05em; flex: none; vertical-align: -0.15em; }
:focus-visible { outline: 3px solid var(--pink); outline-offset: 2px; }
.top { position: sticky; top: 0; z-index: 5; display: flex; align-items: center; gap: 1rem; padding: .7rem 16px; background: var(--cream); border-bottom: 3px solid var(--ink); }
.brand { display: flex; align-items: center; gap: .5rem; text-decoration: none; font-size: 1.35rem; font-weight: 800; }
.brand span { font-weight: 300; }
.top nav { margin-inline-start: auto; display: flex; gap: 1rem; font-weight: 600; }
.top nav a { text-decoration: none; } .top nav a:hover { text-decoration: underline; }
.sq { display: inline-grid; place-items: center; min-width: 40px; height: 40px; padding: 0 .7rem; cursor: pointer; background: var(--surface); color: var(--ink);
  border: 3px solid var(--ink); font: inherit; font-weight: 700; }
.sq svg { width: 20px; height: 20px; } .theme .sun { display: none; }
:root[data-theme=dark] .theme .sun { display: block; } :root[data-theme=dark] .theme .moon { display: none; }
@media (prefers-color-scheme: dark) { :root:not([data-theme=light]) .theme .sun { display: block; } :root:not([data-theme=light]) .theme .moon { display: none; } }
@media (max-width: 720px) { .top nav { display: none; } .theme { margin-inline-start: auto; } }
.wrap { max-width: 1180px; margin: 0 auto; padding-inline: 16px; }
.hero { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 2rem; align-items: end; padding-block: 2.6rem 1.2rem; }
h1 { font-size: clamp(2.1rem, 6vw, 3.6rem); margin: 0 0 .6rem; line-height: 1.05; letter-spacing: -.02em; }
.lead { color: var(--muted); max-width: 40em; margin: 0; font-size: 1.08rem; }
.stats { display: flex; gap: .8rem; margin: 0; }
.stats div { background: var(--sun); color: #111; border: 3px solid var(--ink); box-shadow: 5px 5px 0 var(--ink); padding: .5rem .9rem; min-width: 96px; }
[dir=rtl] .stats div { box-shadow: -5px 5px 0 var(--ink); }
.stats b { display: block; font-size: 1.7rem; line-height: 1.1; }
.stats span { font-size: .85rem; font-weight: 600; }
.tools { display: flex; flex-wrap: wrap; gap: .8rem 1rem; align-items: center; padding-block: .6rem 1.4rem; }
.find { display: flex; align-items: center; gap: .5rem; flex: 1 1 320px; max-width: 460px; border: 3px solid var(--ink); background: var(--surface); padding-inline: .8rem; }
.find input { font: inherit; width: 100%; padding: .65rem 0; border: 0; background: transparent; color: var(--ink); outline: none; }
.find:focus-within { outline: 3px solid var(--pink); outline-offset: 2px; }
.topics { display: flex; flex-wrap: wrap; gap: .45rem; }
.topic { font: inherit; font-size: .88rem; font-weight: 600; cursor: pointer; padding: .3rem .75rem; background: var(--surface); color: var(--ink); border: 2px solid var(--ink); }
.topic[aria-pressed=true] { background: var(--ink); color: var(--paper); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 330px), 1fr)); gap: 1.6rem; padding-block: .4rem 3rem; }
.card { display: flex; flex-direction: column; background: var(--surface); border: 3px solid var(--ink); box-shadow: 6px 6px 0 var(--ink); transition: transform .12s, box-shadow .12s; }
[dir=rtl] .card { box-shadow: -6px 6px 0 var(--ink); }
.card:hover { transform: translate(-2px, -2px); box-shadow: 9px 9px 0 var(--ink); }
[dir=rtl] .card:hover { transform: translate(2px, -2px); box-shadow: -9px 9px 0 var(--ink); }
.card:target { box-shadow: 8px 8px 0 var(--pink); }
.card[hidden] { display: none; }
.cover { display: block; width: 100%; aspect-ratio: 16/10; object-fit: cover; border-bottom: 3px solid var(--ink); background: var(--cream); }
.blank { display: grid; place-items: center; font-size: 4rem; font-weight: 800; color: #111; background: hsl(var(--hue) 75% 75%); }
.card .body { display: flex; flex-direction: column; gap: .55rem; padding: 1rem 1.1rem 1.2rem; flex: 1; }
.card h2 { margin: 0; font-size: 1.2rem; line-height: 1.3; }
.card h2 a { text-decoration: none; } .card h2 a:hover { text-decoration: underline; }
.facts { display: flex; flex-wrap: wrap; gap: .35rem .9rem; margin: 0; padding: 0; list-style: none; color: var(--muted); font-size: .86rem; font-weight: 600; }
.facts li { display: inline-flex; align-items: center; gap: .3rem; }
.desc { margin: 0; color: var(--muted); font-size: .95rem; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.by { margin: 0; font-size: .86rem; color: var(--muted); }
.by .ok { color: #136B45; font-weight: 700; }
.actions { display: flex; flex-wrap: wrap; gap: .6rem; margin-top: auto; padding-top: .5rem; }
.btn { display: inline-flex; align-items: center; gap: .4rem; padding: .5rem .95rem; border: 3px solid var(--ink); text-decoration: none; color: var(--ink);
  font: inherit; font-weight: 700; font-size: .95rem; background: var(--surface); cursor: pointer; }
.btn:hover { background: var(--sun); color: #111; }
.btn.primary { background: var(--ink); color: var(--paper); }
.btn.primary:hover { background: var(--pink); border-color: var(--pink); color: #fff; }
.btn.quiet { border-color: transparent; background: transparent; text-decoration: underline; padding-inline: .3rem; }
.cover-link { display: block; text-decoration: none; }
.prose table + h2, .prose table + h3 { margin-top: 1.6rem; }
.empty { color: var(--muted); }
.share { padding-block: .5rem 4rem; }
.share > div { background: var(--sun); color: #111; border: 3px solid var(--ink); box-shadow: 6px 6px 0 var(--ink); padding: 1.5rem; }
.share h2 { font-size: 1.6rem; margin: 0 0 .6rem; }
.share ol { margin: .5rem 0 1rem; padding-inline-start: 1.3rem; } .share li { margin: .35rem 0; }
.share .btn { background: #fff; color: #111; border-color: #111; }
footer { text-align: center; padding: 2rem 16px; color: var(--muted); font-size: .92rem; }
/* course page */
.crumb { display: inline-flex; align-items: center; gap: .3rem; margin-top: 1.6rem; font-weight: 600; text-decoration: none; }
.crumb:hover { text-decoration: underline; }
[dir=rtl] .crumb .i { transform: scaleX(-1); }
.course-head { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr); gap: 2rem; align-items: start; padding-block: 1.2rem 2rem; }
.course-head .cover { border: 3px solid var(--ink); box-shadow: 8px 8px 0 var(--ink); }
[dir=rtl] .course-head .cover { box-shadow: -8px 8px 0 var(--ink); }
.course-head h1 { font-size: clamp(1.8rem, 4vw, 2.7rem); }
.course-head .desc { -webkit-line-clamp: unset; font-size: 1.02rem; }
.course-head .facts { font-size: .92rem; margin-block: .8rem; }
.tags { display: flex; flex-wrap: wrap; gap: .35rem; margin: .6rem 0; }
.tag { font-size: .8rem; font-weight: 600; border: 2px solid var(--ink); padding: 0 .45rem; }
.section-title { font-size: 1.6rem; margin: 2.2rem 0 1rem; }
.nbs { list-style: none; padding: 0; margin: 0; display: grid; gap: .6rem; }
.nbs .nb { display: flex; flex-wrap: wrap; gap: .6rem 1rem; align-items: center; justify-content: space-between;
  border: 2px solid var(--hair); padding: .8rem 1rem; }
.nbs .actions { display: flex; flex-wrap: wrap; gap: .4rem; margin: 0; }
.modules { list-style: none; margin: 0; padding: 0; counter-reset: mod; display: grid; gap: 1rem; }
.mod { background: var(--surface); border: 3px solid var(--ink); }
.mod summary { display: flex; gap: 1rem; align-items: center; cursor: pointer; padding: .9rem 1.1rem; list-style: none; font-weight: 700; }
.mod summary::-webkit-details-marker { display: none; }
.mod summary::before { counter-increment: mod; content: counter(mod); display: grid; place-items: center; flex: none; width: 2.1rem; height: 2.1rem;
  background: var(--sun); color: #111; border: 2px solid var(--ink); font-weight: 800; }
.mod summary .sum { margin-inline-start: auto; color: var(--muted); font-size: .86rem; font-weight: 600; white-space: nowrap; }
.mod[open] summary { border-bottom: 2px solid var(--hair); }
.mod ul { list-style: none; margin: 0; padding: .4rem 1.1rem .6rem; }
.mod li { display: flex; gap: .6rem; align-items: baseline; padding: .35rem 0; border-bottom: 1px dashed var(--hair); }
.mod li:last-child { border-bottom: 0; }
.mod li .mins { margin-inline-start: auto; color: var(--muted); font-size: .85rem; white-space: nowrap; }
.mod li .kind { font-size: .75rem; font-weight: 700; border: 1.5px solid var(--ink); padding: 0 .35rem; }
.mod .tasks { display: flex; flex-wrap: wrap; gap: .45rem; padding: .2rem 1.1rem 1rem; }
.mod .task { display: inline-flex; gap: .35rem; align-items: center; font-size: .82rem; font-weight: 700; background: var(--sky); color: var(--ink); padding: .2rem .6rem; }
.sample { background: var(--surface); border: 3px solid var(--ink); box-shadow: 6px 6px 0 var(--ink); padding: 1.4rem clamp(1rem, 4vw, 2.6rem); }
[dir=rtl] .sample { box-shadow: -6px 6px 0 var(--ink); }
.sample h2 { font-size: 1.5rem; margin-top: 0; }
.prose { line-height: 1.7; max-width: 46em; margin-inline-end: auto; }
.prose > * { max-width: 100%; }
.prose [dir=rtl] { text-align: right; } .prose [dir=ltr] { text-align: left; }
.prose pre.mermaid { background: var(--surface); color: var(--ink); text-align: center; white-space: pre-wrap; border: 2px solid var(--hair); }
.prose pre.mermaid svg { max-width: 100%; height: auto; }
.prose pre code { color: #E6EDF3; background: none; padding: 0; }
.prose pre .k, .prose pre .kn, .prose pre .kd, .prose pre .kr, .prose pre .kc, .prose pre .ow, .prose pre .kt { color: #FF8FA3; }
.prose pre .s, .prose pre .s1, .prose pre .s2, .prose pre .sa, .prose pre .sb, .prose pre .sd, .prose pre .sh, .prose pre .dl, .prose pre .sx { color: #A5E3B2; }
.prose pre .si, .prose pre .se { color: #F2C97D; }
.prose pre .c, .prose pre .c1, .prose pre .cm, .prose pre .ch, .prose pre .cs, .prose pre .cp { color: #7E8A9B; font-style: italic; }
.prose pre .nf, .prose pre .fm, .prose pre .nc, .prose pre .nn { color: #8CC8FF; }
.prose pre .nb, .prose pre .bp, .prose pre .nd, .prose pre .nt, .prose pre .na { color: #C7A6FF; }
.prose pre .m, .prose pre .mi, .prose pre .mf, .prose pre .mh, .prose pre .il { color: #F7B57A; }
.prose pre .o, .prose pre .p { color: #C9D4E1; }
.prose table { border-collapse: collapse; width: 100%; font-size: .93rem; display: block; overflow-x: auto; }
.prose th, .prose td { border: 1.5px solid var(--hair); padding: .35rem .6rem; text-align: start; }
.prose th { background: var(--cream); }
.prose pre { background: #111; color: #F2EDE2; padding: .9rem 1rem; overflow-x: auto; font-size: .86rem; direction: ltr; }
.prose code { font-family: ui-monospace, Consolas, monospace; font-size: .9em; }
.prose :not(pre) > code { background: var(--cream); padding: .05rem .3rem; }
.prose blockquote { margin: 1rem 0; padding: .4rem 1rem; border-inline-start: 4px solid var(--sun); background: var(--cream); }
.fade { position: relative; max-height: 34rem; overflow: hidden; }
.fade::after { content: ""; position: absolute; inset: auto 0 0 0; height: 7rem; background: linear-gradient(transparent, var(--surface)); }
.fade.open { max-height: none; } .fade.open::after { display: none; }
.credit { color: var(--muted); font-size: .88rem; border-top: 2px solid var(--hair); padding-top: .8rem; margin-top: 2rem; }
.sticky-add { position: sticky; bottom: 0; display: none; }
@media (max-width: 760px) {
  .hero, .course-head { grid-template-columns: 1fr; }
  .stats div { min-width: 0; flex: 1; }
  .sticky-add { display: flex; gap: .6rem; padding: .7rem 16px; background: var(--cream); border-top: 3px solid var(--ink); }
  .sticky-add .btn { flex: 1; justify-content: center; }
}
@media (prefers-reduced-motion: reduce) { .card { transition: none; } .card:hover { transform: none; } }
/* Roadmaps (inPace 1.24) */
.new { display: inline-flex; align-items: center; gap: .3rem; font-size: .78rem; font-weight: 800; background: var(--pink); color: #fff;
  border: 2px solid var(--ink); padding: .05rem .5rem; vertical-align: middle; }
.roadmaps { padding-block: .6rem 1rem; }
.roadmaps-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: .6rem 1rem; }
.roadmaps-head h2 { font-size: 1.8rem; margin: 0; }
.roadmaps-lead { margin: .5rem 0 0; color: var(--muted); max-width: 48em; }
.rgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 330px), 1fr)); gap: 1.4rem; padding-block: 1rem 1.6rem; }
.rcard .top-band { display: flex; align-items: center; justify-content: space-between; padding: .8rem 1.1rem; color: #111; background: var(--sky);
  border-bottom: 3px solid var(--ink); background-image: repeating-linear-gradient(90deg, transparent 0 22px, rgba(255,255,255,.55) 22px 30px); text-decoration: none; }
.rcard .badge { display: grid; place-items: center; width: 46px; height: 46px; background: var(--sun); border: 3px solid var(--ink); }
.rcard .badge .i { width: 26px; height: 26px; }
.rcard .count { font-weight: 800; background: #fff; border: 2px solid var(--ink); padding: .05rem .55rem; }
.rpath { list-style: none; margin: 0; padding: 0; counter-reset: rp; display: grid; gap: .3rem; font-size: .9rem; }
.rpath li { counter-increment: rp; display: flex; gap: .5rem; align-items: baseline; }
.rpath li::before { content: counter(rp); flex: none; display: grid; place-items: center; width: 1.35rem; height: 1.35rem; font-size: .72rem; font-weight: 800;
  border: 2px solid var(--ink); background: var(--cream); }
.rpath li.more { color: var(--muted); } .rpath li.more::before { content: "…"; border-style: dashed; }
.rpath a { text-decoration: none; } .rpath a:hover { text-decoration: underline; }
.needs { font-size: .85rem; color: var(--muted); margin: .2rem 0 0; }
.on-roadmaps { display: flex; flex-wrap: wrap; gap: .4rem .6rem; align-items: center; margin: .8rem 0; padding: .6rem .9rem; background: var(--sky); color: #111;
  border: 2px solid var(--ink); font-size: .92rem; }
.on-roadmaps a { font-weight: 700; color: #111; }
.road { list-style: none; margin: 0 0 2rem; padding: 0; display: grid; gap: 1rem; position: relative; }
.road::before { content: ""; position: absolute; inset-block: 24px; inset-inline-start: 23px; border-inline-start: 3px dashed var(--ink); opacity: .5; }
.road > li { display: grid; grid-template-columns: 50px 1fr; gap: .9rem; align-items: start; }
.road .n { display: grid; place-items: center; width: 50px; height: 50px; font-weight: 800; font-size: 1.05rem; background: var(--sun); color: #111;
  border: 3px solid var(--ink); position: relative; z-index: 1; }
.road li.opt .n { background: var(--surface); color: var(--ink); border-style: dashed; }
.road li.harbour .n { background: var(--sky); font-size: 1.3rem; }
.road .step { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; background: var(--surface); border: 3px solid var(--ink); box-shadow: 5px 5px 0 var(--ink);
  padding: .9rem 1rem; }
[dir=rtl] .road .step { box-shadow: -5px 5px 0 var(--ink); }
.road .step .cover { width: 108px; aspect-ratio: 16 / 10; object-fit: cover; border: 2px solid var(--ink); font-size: 1.6rem; }
.road .step h3 { margin: 0; font-size: 1.1rem; } .road .step h3 a { text-decoration: none; } .road .step h3 a:hover { text-decoration: underline; }
.road .step .grow { flex: 1 1 14rem; display: flex; flex-direction: column; gap: .3rem; }
.road .note { margin: .2rem 0 0; padding: .45rem .7rem; background: var(--cream); border-inline-start: 4px solid var(--sun); font-size: .95rem; }
.road .opt-tag { font-size: .75rem; font-weight: 700; border: 1.5px dashed var(--ink); padding: 0 .4rem; }
@media (max-width: 640px) { .road > li { grid-template-columns: 40px 1fr; gap: .55rem; } .road .n { width: 40px; height: 40px; }
  .road::before { inset-inline-start: 18px; } .road .step .cover { display: none; } }
"""

HEAD_SCRIPT = """<script>
  (function () {
    var lang = null;
    try { lang = localStorage.getItem("inpace-site-lang"); } catch (e) {}
    if (!lang) lang = (navigator.language || "").toLowerCase().indexOf("ar") === 0 ? "ar" : "en";
    document.documentElement.lang = lang; document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    var th = null; try { th = localStorage.getItem("inpace-site-theme"); } catch (e) {}
    if (th === "light" || th === "dark") document.documentElement.setAttribute("data-theme", th);
  })();
</script>"""

COMMON_SCRIPT = """<script>
var html = document.documentElement;
function labels() { var ar = html.lang === "ar";
  [].forEach.call(document.querySelectorAll("[data-ph-en]"), function (el) { el.placeholder = ar ? el.dataset.phAr : el.dataset.phEn; el.setAttribute("aria-label", el.placeholder); }); }
labels();
document.getElementById("lang").addEventListener("click", function () {
  var next = html.lang === "ar" ? "en" : "ar"; html.lang = next; html.dir = next === "ar" ? "rtl" : "ltr";
  try { localStorage.setItem("inpace-site-lang", next); } catch (e) {}
  labels();
});
document.getElementById("theme").addEventListener("click", function () {
  var now = html.getAttribute("data-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  var next = now === "dark" ? "light" : "dark"; html.setAttribute("data-theme", next);
  try { localStorage.setItem("inpace-site-theme", next); } catch (e) {}
});
[].forEach.call(document.querySelectorAll("[data-copy]"), function (b) {
  b.addEventListener("click", function () {
    var old = b.innerHTML;
    navigator.clipboard.writeText(b.dataset.copy).then(function () {
      b.textContent = html.lang === "ar" ? "تم النسخ!" : "Copied!"; setTimeout(function () { b.innerHTML = old; }, 1600); });
  });
});
</script>"""


def shell(title: str, description: str, body: str, root: str, script: str = "") -> str:
    e = html.escape
    return f"""<!doctype html>
<html lang="en" dir="ltr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="icon" href="{SITE_MAIN}assets/icon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Readex+Pro:wght@300;400;600;700;800&display=swap" rel="stylesheet">
{HEAD_SCRIPT}
<style>{STYLE}</style></head><body>
<div class="top">
  <a class="brand" href="{SITE_MAIN}"><img src="{SITE_MAIN}assets/icon.svg" width="30" height="30" alt=""><b><span>in</span>Pace</b></a>
  <nav><a href="{root}index.html">{t("Library", "المكتبة")}</a><a href="{root}index.html#roadmaps">{t("Roadmaps", "مسارات التعلّم")}</a><a href="{SITE_MAIN}guide.html">{t("Guide", "الدليل")}</a>
    <a href="{root}index.html#share">{t("Share your course", "شارك دورتك")}</a><a href="{SITE_MAIN}#download">{t("Download inPace", "حمّل inPace")}</a></nav>
  <button class="sq theme" type="button" id="theme" aria-label="Light or dark mode" title="Light or dark mode"><svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/></svg><svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/></svg></button>
  <button class="sq" type="button" id="lang">{t("عربي", "English")}</button>
</div>
{body}
<footer>{t("Something wrong with a course?", "مشكلة في دورة؟")} <a href="{REPORT}">{t("Report it", "أبلغ عنها")}</a> ·
  <a href="https://github.com/mahmoudyosrimahmoud13/inpace-library">GitHub</a></footer>
{COMMON_SCRIPT}{script}
</body></html>
"""


def facts(c: dict) -> str:
    items = []
    if c.get("minutes"):
        items.append(f'<li>{ic("clock")}{hours(c["minutes"])}</li>')
    items.append(f'<li>{ic("layers")}{c["modules"]} {t("modules", "وحدات")} · {c["lessons"]} {t("lessons", "دروس")}</li>')
    items.append(f'<li>{ic("globe")}{lang_name(c["language"])}</li>')
    return '<ul class="facts">' + "".join(items) + "</ul>"


def byline(c: dict) -> str:
    e = html.escape
    tick = f' <span class="ok">{ic("check")}{t("checked", "موثّق")}</span>' if c["author"]["verified"] else ""
    return f'<p class="by">{t("by", "من إعداد")} <bdi>{e(c["author"]["name"])}</bdi>{tick}</p>'


def new_badge() -> str:
    return f'<span class="new">{t("New in inPace " + ROADMAP_VERSION, "جديد في inPace " + ROADMAP_VERSION)}</span>'


def needs_note() -> str:
    return (f'<p class="needs">{t(f"Following a roadmap needs inPace {ROADMAP_VERSION} or newer. With an older version you can still add each course on its own.", f"متابعة مسار التعلّم تحتاج inPace {ROADMAP_VERSION} أو أحدث. ومع إصدار أقدم يمكنك إضافة كل دورة وحدها.")} '
            f'<a href="{SITE_MAIN}#download">{t("Get the newest inPace", "حمّل أحدث inPace")}</a></p>')


def roadmap_card(r: dict, by_id: dict, root: str = "") -> str:
    e = html.escape
    items = []
    for st in r["steps"][:4]:
        c = by_id.get(st["course"], {})
        items.append(f'<li dir="auto"><a href="{root}c/{e(st["course"])}.html">{e(c.get("title", st["course"]))}</a></li>')
    extra = len(r["steps"]) - 4
    if extra > 0:
        items.append(f'<li class="more">{t(f"and {extra} more", f"و{extra} أخرى")}</li>')
    words = " ".join([r["id"], r["title"], r.get("description", ""), r["author"]["name"]] + list(r.get("tags") or [])).lower()
    hrs = hours(r.get("minutes") or 0)
    return f"""<article class="card rcard" id="r-{e(r["id"])}" data-q="{e(words)}" data-tags="{e('|'.join(str(x).lower() for x in r.get("tags") or []))}">
  <a class="top-band" href="{root}r/{e(r["id"])}.html" tabindex="-1" aria-hidden="true"><span class="badge">{ic("route")}</span>
    <span class="count">{len(r["steps"])} {t("courses", "دورات")}</span></a>
  <div class="body">
    <h2 dir="auto"><a href="{root}r/{e(r["id"])}.html">{e(r["title"])}</a></h2>
    <ul class="facts">{f'<li>{ic("clock")}{hrs}</li>' if hrs else ''}<li>{ic("globe")}{lang_name(r["language"])}</li></ul>
    <p class="desc" dir="auto">{e(r.get("description", ""))}</p>
    <ol class="rpath">{"".join(items)}</ol>
    <p class="by">{t("by", "من إعداد")} <bdi>{e(r["author"]["name"])}</bdi>{f' <span class="ok">{ic("check")}{t("checked", "موثّق")}</span>' if r["author"]["verified"] else ""}</p>
    <div class="actions"><a class="btn primary" href="{e(r["link"])}">{t("Follow in inPace", "تابِعه في inPace")}</a>
      <a class="btn" href="{root}r/{e(r["id"])}.html">{t("See the path", "شاهد المسار")}</a></div>
  </div>
</article>"""


def page(entries: list[dict], road: list[dict] | None = None) -> str:
    road = road or []
    by_id = {c["id"]: c for c in entries}
    e = html.escape
    counts: dict[str, int] = {}
    for c in entries:
        for tag in {str(x).lower() for x in c["tags"]}:
            counts[tag] = counts.get(tag, 0) + 1
    topics = [k for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if n > 1][:10]
    cards = []
    for c in entries:
        words = " ".join([c["id"], c["title"], c["description"], c["author"]["name"]] + c["tags"]).lower()
        dl = ""
        if c["downloads"]:
            d = c["downloads"][0]
            size = " · " + e(d["size"]) if d.get("size") else ""
            dl = f'<p class="by">{ic("video")} {t("Videos download separately", "الفيديوهات تُحمّل منفصلة")}{size}</p>'
        cards.append(f"""<article class="card" id="{e(c["id"])}" data-q="{e(words)}" data-tags="{e('|'.join(x.lower() for x in c['tags']))}">
  <a class="cover-link" href="c/{e(c["id"])}.html" tabindex="-1" aria-hidden="true">{cover_html(c, "")}</a>
  <div class="body">
    <h2 dir="auto"><a href="c/{e(c["id"])}.html">{e(c["title"])}</a></h2>
    {facts(c)}
    <p class="desc" dir="auto">{e(c["description"])}</p>
    {byline(c)}{dl}
    <div class="actions"><a class="btn primary" href="{e(c["link"])}">{t("Add to inPace", "أضف إلى inPace")}</a>
      <a class="btn" href="c/{e(c["id"])}.html">{t("See what's inside", "شاهد المحتوى")}</a></div>
  </div>
</article>""")
    total_h = round(sum(c.get("minutes") or 0 for c in entries) / 60)
    roadmaps_section = ""
    if road:
        roadmaps_section = f"""<section class="roadmaps" id="roadmaps">
  <div class="roadmaps-head"><h2>{t("Roadmaps", "مسارات التعلّم")}</h2>{new_badge()}</div>
    <p class="roadmaps-lead">{t("A roadmap is a path through several courses of the library, in the order that makes sense, toward one goal. Follow one in inPace: it keeps your place, shows the next course, and Tempo sails it with you on his island.", "مسار التعلّم طريق يمرّ بعدة دورات من المكتبة بالترتيب المناسب نحو هدف واحد. تابِعه في inPace: يحفظ مكانك، ويريك الدورة التالية، ويُبحر به تمبو معك على جزيرته.")}</p>
  <div class="rgrid">{"".join(roadmap_card(r, by_id) for r in road)}</div>
  {needs_note()}
</section>
<h2 class="section-title" id="courses">{t("Courses", "الدورات")}</h2>"""
    chips = (f'<button class="topic" type="button" data-topic="" aria-pressed="true">{t("All", "الكل")}</button>' +
             "".join(f'<button class="topic" type="button" data-topic="{e(x)}" aria-pressed="false">{e(x)}</button>' for x in topics))
    body = f"""<div class="wrap">
<header class="hero">
  <div>
    <h1>{t("The inPace course library", "مكتبة دورات inPace")}</h1>
    <p class="lead">{t("Free courses made and shared by people who learn with inPace. Look inside any course first, then press <b>Add to inPace</b> and it opens in the app, ready to start. Your progress stays on your device.",
        "دورات مجانية صنعها وشاركها متعلمون يستخدمون inPace. اطّلع على محتوى أي دورة أولًا، ثم اضغط <b>أضف إلى inPace</b> فتفتح في التطبيق جاهزة للبدء. ويبقى تقدّمك على جهازك.")}</p>
  </div>
  <div class="stats"><div><b>{len(entries)}</b><span>{t("courses", "دورة")}</span></div>{f'<div><b>{len(road)}</b><span>{t("roadmaps", "مسار")}</span></div>' if road else ''}<div><b>{total_h}</b><span>{t("hours of lessons", "ساعة دروس")}</span></div><div><b>0</b><span>{t("cost", "تكلفة")}</span></div></div>
</header>
{roadmaps_section}
<div class="tools">
  <label class="find">{ic("search")}<input type="search" id="q" dir="auto" data-ph-en="Search courses" data-ph-ar="ابحث في الدورات"></label>
  <div class="topics" role="group" aria-label="Topics">{chips}</div>
</div>
<main class="grid" id="list">
{"".join(cards) or '<p class="empty">' + t("No courses yet.", "لا توجد دورات بعد.") + '</p>'}
</main>
<p class="empty" id="none" hidden>{t("No course matches that. Try another word or topic.", "لا توجد دورة تطابق ذلك. جرّب كلمة أو موضوعًا آخر.")}</p>
</div>
<section class="share wrap" id="share"><div>
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
  <h2>{t("Share a roadmap", "شارك مسار تعلّم")} {new_badge()}</h2>
  <p>{t("In inPace, open <b>Roadmaps → Make a roadmap</b>. Type a goal and inPace suggests the courses, in order. Add a note to each one, save, then press <b>Share → Open the form</b>: your roadmap is filled in for you. Roadmaps can only use courses that are in the library.", "في inPace افتح <b>مسارات التعلّم ← اصنع مسارًا</b>. اكتب هدفًا فيقترح inPace الدورات بالترتيب. أضف ملاحظة لكل دورة واحفظ، ثم اضغط <b>شارك ← افتح النموذج</b>: يُملأ المسار لك. ولا يستخدم المسار إلا دورات موجودة في المكتبة.")}</p>
  <p><a class="btn" href="{FORM_ROADMAP}">{t("Open the roadmap form", "افتح نموذج المسار")}</a></p>
</div></section>"""
    script = """<script>
var q = document.getElementById("q"), cards = [].slice.call(document.querySelectorAll("#list .card")), topic = "";
function run() {
  var w = q.value.toLowerCase().split(/\\s+/).filter(Boolean), shown = 0;
  cards.forEach(function (c) {
    var ok = w.every(function (x) { return c.dataset.q.indexOf(x) >= 0; }) && (!topic || c.dataset.tags.split("|").indexOf(topic) >= 0);
    c.hidden = !ok; shown += ok; });
  document.getElementById("none").hidden = shown > 0;
}
q.addEventListener("input", run);
[].forEach.call(document.querySelectorAll(".topic"), function (b) {
  b.addEventListener("click", function () {
    topic = b.dataset.topic;
    [].forEach.call(document.querySelectorAll(".topic"), function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
    run();
  });
});
if (location.hash) { var el = document.getElementById(decodeURIComponent(location.hash.slice(1))); if (el) el.scrollIntoView(); }
</script>"""
    return shell("inPace course library", "Free courses made and shared by inPace learners. Look inside, then add one to inPace with a click.",
                 body, "", script)


def outline_html(c: dict) -> str:
    e = html.escape
    names = {"practical": t("Practical task", "مهمة عملية"), "explain": t("Explain in your words", "اشرح بكلماتك")}
    out = []
    for i, m in enumerate(c.get("outline") or []):
        mins = sum(les["minutes"] for les in m["lessons"])
        rows = []
        for les in m["lessons"]:
            kind = {"pdf": t("slides", "شرائح"), "video": t("video", "فيديو"), "audio": t("audio", "صوت"),
                    "youtube": t("YouTube", "يوتيوب"), "link": t("link", "رابط")}.get(les["media"], "")
            rows.append(f'<li><span dir="auto">{e(les["title"])}</span>{f"<span class=kind>{kind}</span>" if kind else ""}'
                        f'<span class="mins">{les["minutes"] or ""}{t(" min", " د") if les["minutes"] else ""}</span></li>')
        tasks = []
        for tk in m["tasks"]:
            if tk["type"] == "quiz":
                tasks.append(f'<span class="task">{ic("check")}{t("Quiz", "اختبار")} · {tk["questions"]} {t("questions", "أسئلة")}</span>')
            else:
                tasks.append(f'<span class="task" title="{e(tk.get("prompt", ""))}">{ic("doc")}{names.get(tk["type"], e(tk["type"]))}</span>')
        out.append(f"""<li><details class="mod"{" open" if i == 0 else ""}><summary><span dir="auto">{e(m["title"])}</span>
  <span class="sum">{len(m["lessons"])} {t("lessons", "دروس")}{f" · {mins}" + t(" min", " د") if mins else ""}</span></summary>
  <ul>{"".join(rows)}</ul>{f'<div class="tasks">{"".join(tasks)}</div>' if tasks else ""}</details></li>""")
    return '<ol class="modules">' + "".join(out) + "</ol>" if out else ""


REPO_BLOB = "https://github.com/mahmoudyosrimahmoud13/inpace-library/blob/main/courses"
REPO_RAW = "https://raw.githubusercontent.com/mahmoudyosrimahmoud13/inpace-library/main/courses"


def notebooks_html(c: dict) -> str:
    """Notebooks that come with a course: open in Colab, download, or read the PDF version (if there is one)."""
    folder = ROOT / "courses" / c["id"] / "files"
    nbs = sorted(folder.glob("*.ipynb")) if folder.is_dir() else []
    if not nbs:
        return ""
    e = html.escape
    rows = []
    for nb in nbs:
        name = nb.stem
        try:
            first = json.loads(nb.read_text(encoding="utf-8"))["cells"][0]["source"]
            title = "".join(first).splitlines()[0].lstrip("# ").strip() or name
        except Exception:
            title = name
        colab = f"https://colab.research.google.com/github/mahmoudyosrimahmoud13/inpace-library/blob/main/courses/{c['id']}/files/{nb.name}"
        links = [f'<a class="btn" href="{e(colab)}" target="_blank" rel="noopener">{t("Open in Colab", "افتح في Colab")}</a>',
                 f'<a class="btn quiet" href="{e(REPO_RAW)}/{e(c["id"])}/files/{e(nb.name)}" download>{t("Download notebook", "حمّل الدفتر")}</a>']
        if (folder / f"{name}.pdf").is_file():
            links.append(f'<a class="btn quiet" href="{e(REPO_BLOB)}/{e(c["id"])}/files/{e(name)}.pdf" target="_blank" rel="noopener">{t("PDF version", "نسخة PDF")}</a>')
        rows.append(f'<li class="nb"><span dir="auto"><b>{e(title)}</b><br><code>{e(nb.name)}</code></span><span class="actions">{"".join(links)}</span></li>')
    return (f'<h2 class="section-title">{t("Notebooks and downloads", "الدفاتر والتنزيلات")}</h2>'
            f'<p class="by">{t("They also come inside the course. Colab runs them free in your browser.", "وهي موجودة داخل الدورة أيضًا. يشغّلها Colab مجانًا في متصفحك.")}</p>'
            f'<ul class="nbs">{"".join(rows)}</ul>')


def course_page(c: dict, road: list[dict] | None = None) -> str:
    e = html.escape
    mine = [r for r in road or [] if r["id"] in (c.get("roadmaps") or [])]
    on_rm = ""
    if mine:
        links = ", ".join(f'<a href="../r/{e(r["id"])}.html" dir="auto">{e(r["title"])}</a>' for r in mine)
        on_rm = f'<p class="on-roadmaps">{ic("route")}<span>{t("On these roadmaps:", "ضمن هذه المسارات:")} {links}</span></p>'
    try:  # the app's own renderer: code colours, each paragraph's direction, and diagrams, like in inPace
        from inpace.app import md
    except Exception:
        from markdown_it import MarkdownIt
        md = MarkdownIt("commonmark", {"html": False}).enable("table")
    tags = "".join(f'<span class="tag">{e(x)}</span>' for x in c["tags"][:8])
    sample_html = ""
    if c.get("sample"):
        text = re.sub(r"^#\s+.*\n+", "", c["sample"]["text"])
        sample_html = f"""<h2 class="section-title">{t("Read a lesson first", "اقرأ درسًا أولًا")}</h2>
<article class="sample"><h2 dir="auto">{e(c["sample"]["title"])}</h2>
  <div class="prose fade" id="sample" dir="{'rtl' if c['language'] == 'ar' else 'auto'}">{md.render(text)}</div>
  <p><button class="btn" type="button" id="more">{t("Show the whole lesson", "اعرض الدرس كاملًا")}</button></p></article>"""
    dl = ""
    if c["downloads"]:
        d = c["downloads"][0]
        dl = f'<p class="by">{ic("video")} {t("Videos download separately", "الفيديوهات تُحمّل منفصلة")}{" · " + e(d["size"]) if d.get("size") else ""}</p>'
    credit = f'<p>{e(c["credit"])}</p>' if c.get("credit") else ""
    if c.get("book"):
        b = c["book"]
        link = f' <a href="{e(b["url"])}">{e(b["url"].split("//", 1)[-1])}</a>' if b.get("url") else ""
        dl += (f'<p class="by">{ic("doc")} {t("Uses a book you download yourself, free:", "تستخدم كتابًا تحمّله بنفسك مجانًا:")} '
               f'<b dir="auto">{e(b.get("title", ""))}</b>.{link} '
               f'{t("inPace 1.20 or newer finds it on your device.", "يجده inPace 1.20 أو أحدث على جهازك.")}</p>')
    actions = f"""<a class="btn primary" href="{e(c["link"])}">{t("Add to inPace", "أضف إلى inPace")}</a>
      <button class="btn" type="button" data-copy="{e(c["link"])}">{t("Copy link", "انسخ الرابط")}</button>
      <a class="btn quiet" href="{e(c["pack"])}" download>{t("Download file", "حمّل الملف")}</a>"""
    body = f"""<div class="wrap">
<a class="crumb" href="../index.html#{e(c["id"])}">{ic("back")}{t("All courses", "كل الدورات")}</a>
<header class="course-head">
  {cover_html(c, "../")}
  <div>
    <h1 dir="auto">{e(c["title"])}</h1>
    {facts(c)}
    <p class="desc" dir="auto">{e(c["description"])}</p>
    {byline(c)}{dl}
    <div class="tags">{tags}</div>
    <div class="actions">{actions}</div>
  </div>
</header>
{on_rm}
<h2 class="section-title">{t("What's inside", "محتوى الدورة")}</h2>
<p class="by">{t("Each module ends with tasks. The next module opens when they're done.", "تنتهي كل وحدة بمهام، وتُفتح الوحدة التالية عند إنجازها.")}</p>
{outline_html(c) or '<p class="empty">' + t("Add the course to see its lessons.", "أضف الدورة لترى دروسها.") + '</p>'}
{notebooks_html(c)}
{sample_html}
<div class="credit"><p>{t("License", "الرخصة")}: <bdi>{e(c.get("license") or "")}</bdi> · {t("Updated", "آخر تحديث")} <bdi>{e(str(c.get("updated") or ""))}</bdi></p>{credit}</div>
</div>
<div class="sticky-add"><a class="btn primary" href="{e(c["link"])}">{t("Add to inPace", "أضف إلى inPace")}</a></div>"""
    mermaid = ""
    if 'class="mermaid"' in sample_html:
        mermaid = """<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<script>
(function () {
  var html = document.documentElement;
  var dark = html.getAttribute("data-theme") === "dark" || (!html.getAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches);
  if (window.mermaid) { mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: dark ? "dark" : "default" });
    mermaid.run({ querySelector: "pre.mermaid" }).catch(function () {}); }
})();
</script>"""
    script = mermaid + """<script>
var more = document.getElementById("more"), s = document.getElementById("sample");
if (more && s) {
  if (s.scrollHeight <= s.clientHeight + 10) { s.classList.add("open"); more.parentNode.hidden = true; }
  more.addEventListener("click", function () { s.classList.add("open"); more.parentNode.hidden = true; });
}
</script>"""
    return shell(f"{c['title']} · inPace course library", c["description"][:300], body, "../", script)


def roadmap_page(r: dict, by_id: dict) -> str:
    e = html.escape
    steps = []
    for i, st in enumerate(r["steps"], 1):
        c = by_id[st["course"]]
        note = f'<p class="note" dir="auto">{e(st["note"])}</p>' if st.get("note") else ""
        opt = f' <span class="opt-tag">{t("optional", "اختيارية")}</span>' if st.get("optional") else ""
        steps.append(f"""<li class="{'opt' if st.get('optional') else ''}"><span class="n">{i:02d}</span>
  <div class="step">{cover_html(c, "../")}
    <div class="grow"><h3 dir="auto"><a href="../c/{e(c["id"])}.html">{e(c["title"])}</a>{opt}</h3>
      {facts(c)}{note}</div>
    <div class="actions"><a class="btn" href="{e(c["link"])}">{t("Add to inPace", "أضف إلى inPace")}</a></div></div></li>""")
    steps.append(f"""<li class="harbour"><span class="n" aria-hidden="true">⚓</span><div class="step"><div class="grow"><h3>{t("The harbour", "الميناء")}</h3>
  <p class="by">{t("Finish every course that isn't optional. In inPace, Tempo reaches the harbour and opens a chest of shells on his island.", "أنهِ كل دورة غير اختيارية. في inPace يصل تمبو إلى الميناء ويفتح صندوق أصداف على جزيرته.")}</p></div></div></li>""")
    hrs = hours(r.get("minutes") or 0)
    tags = "".join(f'<span class="tag">{e(x)}</span>' for x in (r.get("tags") or [])[:8])
    body = f"""<div class="wrap">
<a class="crumb" href="../index.html#roadmaps">{ic("back")}{t("All roadmaps", "كل المسارات")}</a>
<header class="course-head" style="grid-template-columns: 1fr">
  <div>
    <p>{new_badge()}</p>
    <h1 dir="auto">{e(r["title"])}</h1>
    <ul class="facts"><li>{ic("layers")}{len(r["steps"])} {t("courses", "دورات")} · {r.get("lessons") or 0} {t("lessons", "دروس")}</li>{f'<li>{ic("clock")}{hrs}</li>' if hrs else ''}<li>{ic("globe")}{lang_name(r["language"])}</li></ul>
    <p class="desc" dir="auto">{e(r.get("description", ""))}</p>
    <p class="by">{t("by", "من إعداد")} <bdi>{e(r["author"]["name"])}</bdi>{f' <span class="ok">{ic("check")}{t("checked", "موثّق")}</span>' if r["author"]["verified"] else ""}</p>
    <div class="tags">{tags}</div>
    <div class="actions"><a class="btn primary" href="{e(r["link"])}">{t("Follow in inPace", "تابِعه في inPace")}</a>
      <button class="btn" type="button" data-copy="{e(r["link"])}">{t("Copy link", "انسخ الرابط")}</button></div>
    {needs_note()}
  </div>
</header>
<h2 class="section-title">{t("The path", "المسار")}</h2>
<ol class="road">{"".join(steps)}</ol>
</div>
<div class="sticky-add"><a class="btn primary" href="{e(r["link"])}">{t("Follow in inPace", "تابِعه في inPace")}</a></div>"""
    return shell(f"{r['title']} · inPace roadmaps", r.get("description", "")[:300] or r["title"], body, "../")


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
