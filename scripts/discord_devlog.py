"""Posts every push to the library's main branch to the Discord #dev-log channel (like the app's dev log).

GitHub runs this (.github/workflows/discord.yml). Needs the secret DISCORD_WEBHOOKS; without it, it does nothing.
New and updated courses get their own posts in #new-courses (library_tools.py announce), so this is only the log.
"""
from __future__ import annotations

import json
import os
import urllib.request


def cut(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def message(event: dict) -> dict | None:
    commits = [c for c in event.get("commits", []) if c.get("distinct", True)]
    if not commits:
        return None
    lines = [f"• [{cut((c.get('message') or '').splitlines()[0], 180)}]({c.get('url')})" for c in commits[-10:]]
    more = f"\n…and {len(commits) - 10} more" if len(commits) > 10 else ""
    who = (event.get("head_commit") or {}).get("author", {}).get("name") or event.get("pusher", {}).get("name", "")
    return {"username": "inPace dev log", "embeds": [{
        "title": f"{len(commits)} new change{'s' if len(commits) != 1 else ''} in the course library · {len(commits)} تغيير في المكتبة",
        "url": event.get("compare"), "description": "\n".join(lines) + more
        + "\n\nThe library website updates in a few minutes. موقع المكتبة يتحدّث خلال دقائق.\nhttps://mahmoudyosrimahmoud13.github.io/inpace-library/",
        "color": 0x1F9D6A, "footer": {"text": who}}], "allowed_mentions": {"parse": []}}


def main() -> None:
    try:
        hook = json.loads(os.environ.get("DISCORD_WEBHOOKS") or "{}").get("devlog")
    except ValueError:
        hook = None
    if not os.environ.get("GITHUB_EVENT_PATH"):
        print("Nothing to post.")
        return
    msg = message(json.load(open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8")))
    if not msg:
        print("Nothing to post.")
        return
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import telegram_post as tg
    if tg.topic("devlog"):  # the same dev log in the Telegram group's dev log topic
        tg.send(tg.from_discord(msg), where="devlog")
        print("Posted to Telegram (dev log).")
    if not hook:
        print("No DISCORD_WEBHOOKS secret: not posted to Discord.")
        return
    req = urllib.request.Request(hook + "?wait=true", data=json.dumps(msg).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "inPace-library"})
    urllib.request.urlopen(req, timeout=30).read()
    print("Posted to #dev-log.")


if __name__ == "__main__":
    main()
