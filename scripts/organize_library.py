"""Give every course a section and tidy its tags, so the library is easy to browse.

    python scripts/organize_library.py          # change the library.yaml files
    python scripts/organize_library.py --check  # only show what would change

For each courses/<id>/library.yaml it:
- sets `section:` (one of sections.yaml) unless the file already has a valid one,
- makes tags lower case, merges duplicates and spelling variants, drops noise,
- adds exactly one level tag: beginner, intermediate or advanced,
- keeps at most 8 tags, topic tags first.
Safe to run again: a tidy library comes out the same."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
COURSES = ROOT / "courses"
SECTIONS = [s["id"] for s in yaml.safe_load((ROOT / "sections.yaml").read_text(encoding="utf-8"))]

# Course id patterns -> section (first match wins). New courses not listed fall back to their tags.
BY_ID = [
    (r"^(os-fundamentals|linux-|bash-|networking-|docker-|kubernetes|git-|github-|aws-|cloud-|devops|terraform|ansible|ssh-|observability)", "linux-cloud-devops"),
    (r"^(inpace-inside|.*-for-inpace)$", "build-inpace"),
    (r"^(postgres|sql|data-|excel|power-bi|pandas)", "data-databases"),
    (r"^(dl-|mls-|ml-|deep-learning|llm|nlp)", "ai-ml"),
    (r"^(mml-|math|maths|statistics|calculus|linear-algebra)", "maths"),
    (r"^(ai-engineer-hired|interview|career)", "careers"),
    (r"^(cma|fmaa|accounting|finance)", "business-finance"),
    (r"^(english|german|spanish|french|arabic-language)", "languages"),
    (r"^(python|javascript|csharp|java|fastapi|flutter|html|css|react|system-design|web)", "programming-web"),
]
BY_TAG = [
    ({"linux", "devops", "docker", "kubernetes", "git", "github", "aws", "cloud", "networking", "bash", "security"}, "linux-cloud-devops"),
    ({"sql", "postgresql", "databases", "data analysis", "data engineering", "excel", "power bi"}, "data-databases"),
    ({"machine learning", "deep learning", "ai", "nlp", "llm"}, "ai-ml"),
    ({"math", "statistics", "calculus", "linear algebra"}, "maths"),
    ({"career", "interview"}, "careers"),
    ({"accounting", "finance", "business", "marketing"}, "business-finance"),
    ({"english", "german", "spanish", "french", "language", "grammar"}, "languages"),
    ({"python", "javascript", "web", "programming", "backend", "frontend", "mobile", "flutter"}, "programming-web"),
]

LEVEL_BY_ID = [  # checked in order
    (r"^(linux-sysadmin|linux-network-security|bash-|docker-|github-|dl-|mls-|mml-|ai-engineer|fastapi|jinja|javascript-for|inpace-inside|fmaa|os-fundamentals)", "intermediate"),
    (r"(advanced|internals|interview|tdd|data-engineering)", "advanced"),
]
LEVELS = ("beginner", "intermediate", "advanced")
SYNONYMS = {
    "beginners": "beginner", "basics": "beginner", "elementary": "beginner", "a1": "beginner", "a2": "beginner",
    "b1": "intermediate", "b2": "intermediate", "c1": "advanced",
    "cmd": "cma", "postgres": "postgresql", "maths": "math", "mathematics": "math", "ml": "machine learning",
    "dl": "deep learning", "k8s": "kubernetes", "js": "javascript", "c#": "csharp", ".net": "dotnet",
    "tcp ip": "tcp/ip", "ci cd": "ci/cd", "cicd": "ci/cd", "data analytics": "data analysis",
    "shell scripting": "bash", "shell": "bash", "command line": "command line", "operating systems": "operating systems",
    "sys admin": "sysadmin", "system administration": "sysadmin", "exam": "exam prep",
}
DROP = {"devops track", "project", "new", "free", "course", "tutorial", "andrew ng", "3blue1brown", "mml book",
        "harvard", "cs50", "fmaa", "prc"}
KEEP_CASE = {"fmaa": "FMAA"}
EXTRA = {  # courses that had no or too few tags
    "fastapi": ["fastapi", "python", "backend", "api"],
    "flutter-tdd-and-clean-architecture": ["flutter", "dart", "testing", "clean architecture", "mobile"],
    "python-basics": ["python", "programming"], "python-basics-ar": ["python", "programming", "arabic"],
    "cma-part-1-for-complete-beginners-12-weeks-through-sections-": ["cma", "accounting", "management accounting", "exam prep"],
    "excel-tutorial-for-data-analysts": ["excel", "data analysis", "spreadsheets"],
    "fmaa-prc": ["fmaa exam"], "fmaa-prc-ar": ["fmaa exam"],
}


def clean_tag(t) -> str:
    t = re.sub(r"[\s_\-]+", " ", str(t).strip().lower())
    return SYNONYMS.get(t, t)


def pick_section(cid: str, tags: list[str]) -> str:
    for pat, sec in BY_ID:
        if re.search(pat, cid):
            return sec
    for words, sec in BY_TAG:
        if words & set(tags):
            return sec
    return "other"


def pick_level(cid: str, tags: list[str], title: str) -> str:
    found = [t for t in tags if t in LEVELS]
    for pat, lvl in LEVEL_BY_ID:
        if re.search(pat, cid):
            return lvl
    if found:
        return found[0]
    words = title.lower()
    if re.search(r"advanced|deep dive|internals|master", words):
        return "advanced"
    if re.search(r"beginner|from zero|basics|introduction|intro|fundamentals|first", words):
        return "beginner"
    return "intermediate"


def tidy(cid: str, meta: dict, title: str, twin_level: str | None = None) -> dict:
    tags = []
    for t in list(meta.get("tags") or []) + EXTRA.get(cid, []):
        t = clean_tag(t)
        if t and t not in DROP and t not in tags:
            tags.append(t)
    level = twin_level or pick_level(cid, tags, title)   # an Arabic copy takes its English twin's level
    topic = [t for t in tags if t not in LEVELS]
    if cid.endswith("-ar") and "arabic" in topic:
        topic.remove("arabic")
        topic.append("arabic")                          # keep it, but last
    section = meta.get("section") if meta.get("section") in SECTIONS else pick_section(cid, topic)
    out = dict(meta)
    out["section"] = section
    out["tags"] = topic[:7] + [level]
    return out


def main(argv: list[str]) -> int:
    check = "--check" in argv
    changed = 0
    counts: dict[str, int] = {}
    folders = sorted(p for p in COURSES.iterdir() if p.is_dir())
    folders.sort(key=lambda p: p.name.endswith("-ar"))      # English twins first, so Arabic copies can follow them
    levels: dict[str, str] = {}
    for folder in folders:
        lib = folder / "library.yaml"
        meta = yaml.safe_load(lib.read_text(encoding="utf-8")) if lib.exists() else {}
        course = yaml.safe_load((folder / "course.yaml").read_text(encoding="utf-8")) or {}
        twin = levels.get(folder.name[:-3]) if folder.name.endswith("-ar") else None
        new = tidy(folder.name, meta or {}, str(course.get("title", "")), twin)
        levels[folder.name] = new["tags"][-1]
        counts[new["section"]] = counts.get(new["section"], 0) + 1
        if new != meta:
            changed += 1
            print(f"{'WOULD ' if check else ''}UPDATE {folder.name}: [{new['section']}] {', '.join(new['tags'])}")
            if not check:
                lib.write_text(yaml.safe_dump(new, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")
    print(f"\n{changed} course(s) {'would change' if check else 'changed'}. Courses per section:")
    for s in SECTIONS:
        if counts.get(s):
            print(f"  {s}: {counts[s]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
