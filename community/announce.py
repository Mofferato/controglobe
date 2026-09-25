#!/usr/bin/env python3
"""Announce Controglobe's new YouTube uploads in the Discord's #announcements.

  python announce.py --state FILE          post every upload not announced yet (the GitHub Action runs this)
  python announce.py --message "text"      post one message of your own: a premiere, a new article
  python announce.py --dry-run ...         say what would be posted, post nothing

It reads the channel's public upload feed (no YouTube key) and posts through a Discord webhook,
so no bot has to stay in the server. Settings come from the environment, which the GitHub Action
fills from the repository's secrets and variables:

  DISCORD_ANNOUNCE_WEBHOOK   the #announcements webhook address (a secret: never commit it)
  YOUTUBE_CHANNEL_ID         the channel's ID: UC and 22 more characters
  DISCORD_PING_ROLE          optional: the Video Pings role's ID, pinged with each new video

The state file lists the uploads already announced. A first run without one only records what is
on the channel, so switching this on never floods #announcements with old videos. README.md in
this folder, "Announcing new videos by itself", has the setup.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

UA = "DiscordBot (https://github.com/Mofferato/controglobe, 1.0)"
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
WEBHOOK = re.compile(r"https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api/(?:v\d+/)?webhooks/\d+/[\w-]+")
CHANNEL = re.compile(r"UC[\w-]{22}")
ROLE = re.compile(r"\d{15,21}")
KEEP = 500                      # announced IDs remembered; the feed only ever shows the latest 15


class Stop(Exception):
    """A problem to report. `fatal` ones need a person (a wrong setting); the rest pass with time."""

    def __init__(self, msg: str, fatal: bool):
        super().__init__(msg)
        self.fatal = fatal


def fetch(url: str, data: bytes | None = None, tries: int = 4) -> bytes:
    headers = {"User-Agent": UA}
    if data is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(tries):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf8", "replace")
            if e.code == 429:
                try:
                    wait = float(json.loads(body).get("retry_after", 2))
                except ValueError:
                    wait = 2.0
                time.sleep(wait + 0.25)
                continue
            if e.code >= 500 and attempt < tries - 1:
                time.sleep(2 ** attempt)
                continue
            raise Stop(f"HTTP {e.code} from {url.split('?')[0]}: {body[:200]}", fatal=e.code < 500) from None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < tries - 1:
                time.sleep(2 ** attempt)
                continue
            raise Stop(f"could not reach {url.split('?')[0]}: {e}", fatal=False) from None
    raise Stop(f"{url.split('?')[0]} kept asking to wait", fatal=False)


def uploads(channel_id: str) -> list[dict]:
    """The channel's latest uploads, oldest first."""
    root = ET.fromstring(fetch(FEED.format(channel_id)))
    out = []
    for entry in root.findall("a:entry", NS):
        vid = entry.findtext("yt:videoId", default="", namespaces=NS)
        link = entry.find("a:link", NS)
        out.append({"id": vid, "title": (entry.findtext("a:title", default="", namespaces=NS)).strip(),
                     "url": link.get("href") if link is not None else f"https://www.youtube.com/watch?v={vid}",
                     "published": entry.findtext("a:published", default="", namespaces=NS)})
    return sorted((v for v in out if v["id"]), key=lambda v: v["published"])


def post(webhook: str, content: str, role: str | None, dry: bool) -> None:
    mention = f"<@&{role}> " if role else ""
    body = {"content": mention + content, "allowed_mentions": {"parse": [], "roles": [role] if role else []}}
    if len(body["content"]) > 2000:
        raise Stop(f"the message is {len(body['content'])} characters; Discord allows 2000", fatal=True)
    if dry:
        print(f"  would post: {body['content']!r}")
        return
    fetch(webhook + "?wait=true", json.dumps(body).encode())
    print(f"  posted: {content.splitlines()[0][:90]}")


def video_message(v: dict) -> str:
    title = re.sub(r"([*_~`|\\>])", r"\\\1", v["title"])      # a title is text, not Discord formatting
    return f"🎬 **{title}**\nNew on the channel: {v['url']}"


def check(state_path: pathlib.Path, channel_id: str, webhook: str, role: str | None, dry: bool) -> None:
    seen = None
    if state_path.exists():
        seen = json.loads(state_path.read_text(encoding="utf8")).get("announced", [])
    vids = uploads(channel_id)
    if seen is None:
        print(f"First run: recorded the {len(vids)} uploads on the channel; the next new one is announced.")
        seen = [v["id"] for v in vids]
    else:
        new = [v for v in vids if v["id"] not in seen]
        print(f"{len(vids)} uploads in the feed, {len(new)} new.")
        for v in new:
            post(webhook, video_message(v), role, dry)
            seen.append(v["id"])                 # recorded one by one, so a failure never repeats a post
            if not dry:
                save(state_path, seen)
    if not dry:
        save(state_path, seen)


def save(path: pathlib.Path, seen: list[str]) -> None:
    path.write_text(json.dumps({"announced": seen[-KEEP:]}, indent=0) + "\n", encoding="utf8")


def settings(need_channel: bool) -> tuple[str, str | None, str | None]:
    webhook = (os.environ.get("DISCORD_ANNOUNCE_WEBHOOK") or "").strip()
    channel = (os.environ.get("YOUTUBE_CHANNEL_ID") or "").strip()
    role = (os.environ.get("DISCORD_PING_ROLE") or "").strip() or None
    missing = [n for n, v in (("DISCORD_ANNOUNCE_WEBHOOK", webhook),
                              ("YOUTUBE_CHANNEL_ID", channel if need_channel else "x")) if not v]
    if missing:
        raise Stop(f"not set up yet: {', '.join(missing)} missing (community/README.md, "
                   f"'Announcing new videos by itself')", fatal=False)
    if not WEBHOOK.fullmatch(webhook):
        raise Stop("DISCORD_ANNOUNCE_WEBHOOK is not a Discord webhook address "
                   "(https://discord.com/api/webhooks/<number>/<token>)", fatal=True)
    if need_channel and not CHANNEL.fullmatch(channel):
        raise Stop(f"YOUTUBE_CHANNEL_ID should be UC and 22 more characters, not {len(channel)} characters "
                   f"(YouTube: Settings > Advanced settings > Channel ID)", fatal=True)
    if role and not ROLE.fullmatch(role):
        raise Stop("DISCORD_PING_ROLE should be the role's ID, a long number", fatal=True)
    return webhook, channel or None, role


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", default=".announced.json", help="the list of uploads already announced")
    ap.add_argument("--message", help="post this instead of checking YouTube (\\n makes a new line)")
    ap.add_argument("--ping", action="store_true", help="with --message: ping the Video Pings role too")
    ap.add_argument("--dry-run", action="store_true", help="post nothing, say what would be posted")
    args = ap.parse_args(argv)
    gh = bool(os.environ.get("GITHUB_ACTIONS"))
    try:
        if args.message is not None:
            text = args.message.replace("\\n", "\n").strip()
            if not text:
                raise Stop("the message is empty", fatal=True)
            webhook, _, role = settings(need_channel=False)
            post(webhook, text, role if args.ping else None, args.dry_run)
        else:
            webhook, channel, role = settings(need_channel=True)
            check(pathlib.Path(args.state), channel, webhook, role, args.dry_run)
    except Stop as e:
        # In the Action a passing problem is a warning, so a YouTube hiccup does not email anyone;
        # a wrong setting fails the run, so it gets noticed.
        print(f"{'::error::' if gh and e.fatal else '::warning::' if gh else ''}{e}")
        return 1 if e.fatal else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
