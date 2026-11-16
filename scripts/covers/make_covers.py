"""Draw course covers from covers.yaml.

    python scripts/covers/make_covers.py                 # every course in covers.yaml
    python scripts/covers/make_covers.py fmaa-prc        # just these
    python scripts/covers/make_covers.py --sheet         # also save scripts/covers/.sheet.jpg to compare them

Writes courses/<id>/files/cover.jpg (1280x800) and sets `image: cover.jpg` in course.yaml.
Needs: pip install pyyaml playwright && playwright install chromium
"""
from __future__ import annotations
import sys
from pathlib import Path
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FONTS = (HERE / "fonts").as_uri()

def face(fam, file, w):
    return f"@font-face{{font-family:'{fam}';src:url({FONTS}/{file});font-weight:{w}}}"

CSS = "".join(
    [face("Brico", f"bricolage-grotesque-latin-{w}-normal.woff2", w) for w in (500, 700, 800)]
    + [face("JBM", f"jetbrains-mono-latin-{w}-normal.woff2", w) for w in (500, 700)]
    + [face("Plex", f"ibm-plex-sans-arabic-{s}-{w}-normal.woff2", w) for s in ("arabic", "latin") for w in (400, 700)]
) + """
*{margin:0;box-sizing:border-box}
body{width:1280px;height:800px;overflow:hidden;position:relative;background:var(--bg);color:var(--ink);font-family:Brico,Plex,sans-serif}
.glow{position:absolute;width:900px;height:900px;border-radius:50%;background:var(--glow);right:-260px;top:-160px;opacity:.55}
.dots{position:absolute;inset:0;background-image:radial-gradient(var(--dot) 1.6px,transparent 1.6px);background-size:28px 28px;opacity:.35}
.art{position:absolute;right:70px;top:120px}
.l{position:absolute;left:84px;top:86px;width:600px}
.chip{display:inline-block;background:var(--accent);color:var(--chipink);font-weight:700;font-size:24px;padding:9px 20px;border-radius:999px}
h1{font-weight:800;font-size:104px;line-height:.95;letter-spacing:-3px;margin-top:34px}
p{font-weight:500;font-size:29px;line-height:1.38;margin-top:30px;opacity:.88;width:560px}
.foot{position:absolute;left:84px;bottom:66px;display:flex;gap:14px;align-items:center;font-weight:700;font-size:24px}
.foot span{border:2.5px solid var(--ink);border-radius:999px;padding:8px 18px}
.brand{position:absolute;right:84px;bottom:74px;font-weight:700;font-size:24px;opacity:.85}
.rtl .l{left:auto;right:84px}.rtl .art{right:auto;left:70px}.rtl .foot{left:auto;right:84px}
.rtl .brand{right:auto;left:84px}.rtl .glow{right:auto;left:-260px}
.rtl h1{letter-spacing:0;line-height:1.2;font-size:92px}.rtl p{font-size:28px}
"""

def page(c: dict, theme: dict) -> str:
    rtl = bool(c.get("rtl"))
    d = "rtl" if rtl else "ltr"
    vars_ = ";".join(f"--{k}:{v}" for k, v in theme.items())
    art = (HERE / "art" / c["art"]).read_text(encoding="utf-8") if c.get("art") else ""
    tags = "".join(f"<span>{t}</span>" for t in c.get("tags", []))
    brand = c.get("brand") or ("مكتبة inPace" if rtl else "inPace library")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS}:root{{{vars_}}}</style></head>
<body class="{d}"><div class="glow"></div><div class="dots"></div><div class="art">{art}</div>
<div class="l" dir="{d}"><span class="chip">{c['chip']}</span><h1>{c['title']}</h1><p>{c['sub']}</p></div>
<div class="foot" dir="{d}">{tags}</div><div class="brand">{brand}</div></body></html>"""

def set_image(course_yaml: Path) -> None:
    text = course_yaml.read_text(encoding="utf-8")
    if "\nimage:" in text:
        return
    lines = text.splitlines(keepends=True)
    out, done = [], False
    for line in lines:
        if not done and line.startswith("modules:"):
            out.append("image: cover.jpg\n"); done = True
        out.append(line)
    course_yaml.write_text("".join(out), encoding="utf-8")

def main(argv: list[str]) -> None:
    from playwright.sync_api import sync_playwright
    cfg = yaml.safe_load((HERE / "covers.yaml").read_text(encoding="utf-8"))
    sheet = "--sheet" in argv
    ids = [a for a in argv if not a.startswith("--")] or list(cfg["courses"])
    made = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        tab = browser.new_page(viewport={"width": 1280, "height": 800})
        for cid in ids:
            c = cfg["courses"][cid]
            folder = ROOT / "courses" / cid
            if not folder.is_dir():
                print(f"SKIP {cid}: no courses/{cid}"); continue
            html_file = HERE / ".preview.html"
            html_file.write_text(page(c, cfg["themes"][c["theme"]]), encoding="utf-8")
            tab.goto(html_file.as_uri())
            tab.evaluate("document.fonts.ready")
            tab.wait_for_timeout(200)
            (folder / "files").mkdir(exist_ok=True)
            out = folder / "files" / "cover.jpg"
            tab.screenshot(path=str(out), type="jpeg", quality=90)
            set_image(folder / "course.yaml")
            made.append(out); print(f"OK   {cid}")
        browser.close()
    (HERE / ".preview.html").unlink(missing_ok=True)
    if sheet and made:
        from PIL import Image
        cols, w, h = 4, 400, 250
        rows = (len(made) + cols - 1) // cols
        s = Image.new("RGB", (cols * w, rows * h), "white")
        for i, f in enumerate(made):
            s.paste(Image.open(f).convert("RGB").resize((w, h)), ((i % cols) * w, (i // cols) * h))
        s.save(HERE / ".sheet.jpg", quality=85); print("sheet: scripts/covers/.sheet.jpg")

if __name__ == "__main__":
    main(sys.argv[1:])
