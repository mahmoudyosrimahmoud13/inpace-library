"""Posts an announcement with pictures (promo/launch.yaml) to the Discord #announcements channel.

Run it from GitHub: Actions > Discord announcement > Run workflow. It needs the secret DISCORD_WEBHOOKS.
    python scripts/discord_promo.py promo/launch.yaml            post it
    python scripts/discord_promo.py promo/launch.yaml --dry-run  only show what would be posted
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import uuid
from pathlib import Path

import yaml


def form(payload: dict, files: list[Path]) -> tuple[bytes, str]:
    """A multipart body: the message as payload_json, and each picture as files[n]."""
    b = uuid.uuid4().hex
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="payload_json"\r\nContent-Type: application/json\r\n\r\n'.encode()
             + json.dumps(payload, ensure_ascii=False).encode() + b"\r\n"]
    for i, f in enumerate(files):
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="files[{i}]"; filename="{f.name}"\r\n'
                     f'Content-Type: image/jpeg\r\n\r\n'.encode() + f.read_bytes() + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={b}"


def main(argv: list[str]) -> int:
    src = Path(argv[0] if argv else "promo/launch.yaml")
    dry = "--dry-run" in argv
    posts = yaml.safe_load(src.read_text(encoding="utf-8"))["posts"]
    try:
        hook = json.loads(os.environ.get("DISCORD_WEBHOOKS") or "{}").get("announcements")
    except ValueError:
        hook = None
    for p in posts:
        files = [src.parent / f for f in p.get("files", [])]
        missing = [f.name for f in files if not f.is_file()]
        if missing:
            print("Missing pictures:", ", ".join(missing)); return 1
        text = p["text"].strip()
        if len(text) > 2000:
            print("A post is longer than Discord allows (2000 characters):", len(text)); return 1
        if dry or not hook:
            print(("DRY RUN" if dry else "No DISCORD_WEBHOOKS secret") + f": would post {len(text)} characters and {len(files)} pictures")
            continue
        body, ctype = form({"username": "inPace", "content": text, "allowed_mentions": {"parse": []}}, files)
        req = urllib.request.Request(hook + "?wait=true", data=body, method="POST",
                                     headers={"Content-Type": ctype, "User-Agent": "inPace-library"})
        urllib.request.urlopen(req, timeout=60).read()
        print(f"Posted ({len(files)} pictures).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
