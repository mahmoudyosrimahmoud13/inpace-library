"""Posts to the inPace Telegram channel, next to Discord: new and updated courses and roadmaps, the whole library,
and announcements with pictures. The app repo posts new releases the same way.

Needs two GitHub secrets: TELEGRAM_BOT_TOKEN (from @BotFather) and TELEGRAM_CHAT (the channel, like @inpace_app).
The bot must be an admin of the channel. Without the secrets, nothing is posted.
"""
from __future__ import annotations

import html
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def config() -> tuple[str, str] | None:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT", "").strip()
    return (token, chat) if token and chat else None


def _call(token: str, method: str, fields: dict, files: list[tuple[str, Path]] | None = None) -> dict:
    url = f"{os.environ.get('TELEGRAM_API', 'https://api.telegram.org')}/bot{token}/{method}"
    if files:
        b = uuid.uuid4().hex
        parts = []
        for k, v in fields.items():
            parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'.encode() + str(v).encode() + b"\r\n")
        for name, f in files:
            parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{name}"; filename="{f.name}"\r\n'
                         f'Content-Type: image/jpeg\r\n\r\n'.encode() + f.read_bytes() + b"\r\n")
        body, ctype = b"".join(parts) + f"--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"
    else:
        body, ctype = json.dumps(fields).encode(), "application/json"
    for attempt in range(6):
        req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:  # 429: Telegram says how long to wait
            try:
                wait = json.loads(e.read() or b"{}").get("parameters", {}).get("retry_after")
            except ValueError:
                wait = None
            if e.code != 429 or not wait or attempt == 5:
                raise
            time.sleep(min(float(wait), 60) + 0.5)
    return {}


def cut(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def from_discord(msg: dict) -> str:
    """A Discord post (content and its first embed) as Telegram HTML text."""
    e = html.escape
    out = []
    if msg.get("content"):
        out.append(e(msg["content"]).replace("## ", "").replace("**", ""))
    for em in msg.get("embeds") or []:
        title = e(em.get("title") or "")
        out.append(f'<b><a href="{e(em["url"])}">{title}</a></b>' if em.get("url") else f"<b>{title}</b>")
        if em.get("description"):
            out.append(e(em["description"]))
    return "\n\n".join(x for x in out if x)


def send(text: str, picture: Path | None = None, pictures: list[Path] | None = None) -> None:
    """One post: text alone, text under one picture, or an album of pictures with the text under the first."""
    cfg = config()
    if not cfg:
        return
    token, chat = cfg
    pics = pictures or ([picture] if picture else [])
    if not pics:
        _call(token, "sendMessage", {"chat_id": chat, "text": cut(text, 4000), "parse_mode": "HTML",
                                     "link_preview_options": {"is_disabled": True}})
    elif len(pics) == 1 and len(text) <= 1024:
        _call(token, "sendPhoto", {"chat_id": chat, "caption": text, "parse_mode": "HTML"}, [("photo", pics[0])])
    else:
        media = [{"type": "photo", "media": f"attach://p{i}"} for i in range(len(pics))]
        if len(text) <= 1024:
            media[0].update({"caption": text, "parse_mode": "HTML"})
        _call(token, "sendMediaGroup", {"chat_id": chat, "media": json.dumps(media)},
              [(f"p{i}", p) for i, p in enumerate(pics)])
        if len(text) > 1024:
            _call(token, "sendMessage", {"chat_id": chat, "text": cut(text, 4000), "parse_mode": "HTML"})
    time.sleep(3.1)  # Telegram allows about 20 posts a minute in one channel


def check() -> int:
    """python scripts/telegram_post.py: checks the token and the channel, and posts a short hello."""
    cfg = config()
    if not cfg:
        print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT first.")
        return 1
    token, chat = cfg
    me = _call(token, "getMe", {})["result"]["username"]
    print("Bot:", "@" + me)
    send("🐢 inPace is connected to this channel. · inPace متصل بهذه القناة.")
    print("Posted a hello in", chat)
    return 0


if __name__ == "__main__":
    raise SystemExit(check())
