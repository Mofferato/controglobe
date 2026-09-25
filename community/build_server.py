#!/usr/bin/env python3
"""Build the Controglobe Discord server from discord-server.json.

  python build_server.py --show            print the layout and check it against Discord's limits (no token)
  python build_server.py --dry-run         read the server and print what would change, change nothing
  python build_server.py                   build it: roles, channels, permissions, Community, AutoMod, first posts
  python build_server.py --icon logo.png   also set the server icon (python build.py logo, in video/, draws one)

It talks to Discord as a bot: make one in the Developer Portal, invite it to the server with
Administrator, and give its token in DISCORD_TOKEN (or paste it when asked). Kick the bot when
the build is done. README.md in this folder has every step.

Standard library only. It is safe to run again: it finds what already exists by name (the emoji
in a name do not count, so a plain #rules is adopted as 📜・rules), fixes it in place and never
deletes anything. Anything not in the blueprint is listed and left alone.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
API = "https://discord.com/api/v10"
UA = "DiscordBot (https://github.com/Mofferato/controglobe, 1.0)"
REASON = "Controglobe blueprint (community/build_server.py)"

PERMS = {
    "KICK_MEMBERS": 1 << 1, "BAN_MEMBERS": 1 << 2, "ADD_REACTIONS": 1 << 6, "VIEW_AUDIT_LOG": 1 << 7,
    "VIEW_CHANNEL": 1 << 10, "SEND_MESSAGES": 1 << 11, "MANAGE_MESSAGES": 1 << 13,
    "MUTE_MEMBERS": 1 << 22, "DEAFEN_MEMBERS": 1 << 23, "MOVE_MEMBERS": 1 << 24,
    "MANAGE_NICKNAMES": 1 << 27, "MANAGE_EVENTS": 1 << 33, "MANAGE_THREADS": 1 << 34,
    "CREATE_PUBLIC_THREADS": 1 << 35, "CREATE_PRIVATE_THREADS": 1 << 36,
    "SEND_MESSAGES_IN_THREADS": 1 << 38, "MODERATE_MEMBERS": 1 << 40,
}
P = PERMS
WRITE = P["SEND_MESSAGES"] | P["SEND_MESSAGES_IN_THREADS"] | P["CREATE_PUBLIC_THREADS"] | P["CREATE_PRIVATE_THREADS"]

TEXT, VOICE, CATEGORY, ANNOUNCEMENT, FORUM = 0, 2, 4, 5, 15
TYPES = {"text": TEXT, "voice": VOICE, "announcement": ANNOUNCEMENT, "forum": FORUM}
TRIGGERS = {"spam": 3, "keyword_preset": 4, "mention_spam": 5}
PRESETS = {"profanity": 1, "sexual_content": 2, "slurs": 3}
PLACEHOLDER = re.compile(r"\{(#?[\w-]+)\}")
VS16 = "\N{VARIATION SELECTOR-16}"


class ApiError(Exception):
    def __init__(self, status: int, method: str, path: str, body: str):
        self.status, self.body = status, body
        try:
            data = json.loads(body)
            self.code, msg = data.get("code"), data.get("message", body)
            if data.get("errors"):
                msg += " " + json.dumps(data["errors"], ensure_ascii=False)[:400]
        except ValueError:
            self.code, msg = None, body[:400]
        super().__init__(f"{method} {path}: HTTP {status}: {msg}")


class Discord:
    """The few REST calls the build needs. In a dry run every write is printed and faked."""

    def __init__(self, token: str, dry: bool):
        self.token, self.dry, self._fake = token, dry, 0

    def call(self, method: str, path: str, body=None):
        if method != "GET" and self.dry:
            return self._pretend(method, path, body)
        headers = {"Authorization": f"Bot {self.token}", "User-Agent": UA, "X-Audit-Log-Reason": REASON}
        data = None if method == "GET" else b""              # a PUT with nothing to say still sends a body
        if body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        for _ in range(6):
            req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    raw = r.read()
                    return json.loads(raw) if raw else None
            except urllib.error.HTTPError as e:
                text = e.read().decode("utf8", "replace")
                if e.code == 429:
                    try:
                        wait = float(json.loads(text).get("retry_after", 2))
                    except ValueError:
                        wait = 2.0
                    print(f"    (Discord asks to wait {wait:.1f}s)")
                    time.sleep(wait + 0.25)
                    continue
                raise ApiError(e.code, method, path, text) from None
        raise ApiError(429, method, path, "still rate-limited after six tries")

    def get(self, path):
        return self.call("GET", path)

    def post(self, path, body):
        return self.call("POST", path, body)

    def patch(self, path, body):
        return self.call("PATCH", path, body)

    def _pretend(self, method, path, body):
        self._fake += 1
        fake = {"id": f"new{self._fake}"}
        if isinstance(body, dict):
            fake = {**body, **fake}
            for i, tag in enumerate(fake.get("available_tags") or []):
                tag.setdefault("id", f"tag{self._fake}.{i}")
        return fake


# --- the blueprint -----------------------------------------------------------------------------

def load(path: pathlib.Path) -> dict:
    bp = json.loads(path.read_text(encoding="utf8"))
    for cat in bp["categories"]:
        for ch in cat["channels"]:
            ch.setdefault("type", "text")
            if cat.get("private"):
                ch["private"] = True
    return bp


def channels(bp):
    for cat in bp["categories"]:
        for ch in cat["channels"]:
            yield cat, ch


def norm(name: str) -> str:
    """What a name is once emoji, separators and case are gone: '📜・rules' and 'rules' match."""
    return re.sub(r"[\W_]+", "", name.casefold())


def text(lines, links: dict, ids: dict) -> str:
    """Join a message's lines, fill {site}-style links and {#key} channel mentions, and drop a
    line whose link is not set yet (the YouTube channel, say)."""
    out = []
    for line in [lines] if isinstance(lines, str) else lines:
        missing = False

        def fill(m):
            nonlocal missing
            key = m.group(1)
            if key.startswith("#"):
                if key[1:] in ids:
                    return f"<#{ids[key[1:]]}>"
                missing = True
                return m.group(0)
            if links.get(key):
                return links[key]
            missing = True
            return m.group(0)

        line = PLACEHOLDER.sub(fill, line)
        if not missing:
            out.append(line)
    return "\n".join(out)


def validate(bp: dict) -> list[str]:
    """Discord's limits and the blueprint's own cross-references, checked without a network."""
    errs = []
    keys = [ch["key"] for _, ch in channels(bp)]
    rkeys = [r["key"] for r in bp["roles"]]
    for dup in {k for k in keys if keys.count(k) > 1} | {k for k in rkeys if rkeys.count(k) > 1}:
        errs.append(f"key {dup!r} is used twice")
    fake_ids = {k: "1" * 19 for k in keys}
    links = {k: v or "https://example.com/a-link-of-some-length" for k, v in bp["links"].items()}

    def check_text(where, lines, limit):
        for ref in PLACEHOLDER.findall("\n".join([lines] if isinstance(lines, str) else lines)):
            if ref.startswith("#") and ref[1:] not in fake_ids:
                errs.append(f"{where}: no channel with key {ref[1:]!r}")
            if not ref.startswith("#") and ref not in bp["links"]:
                errs.append(f"{where}: no link called {ref!r}")
        n = len(text(lines, links, fake_ids))
        if n > limit:
            errs.append(f"{where}: {n} characters, Discord allows {limit}")

    s = bp["server"]
    if not 2 <= len(s["name"]) <= 100:
        errs.append("server name must be 2-100 characters")
    if len(s.get("description", "")) > 120:
        errs.append("server description is over 120 characters")
    for k in ("system_channel", "rules_channel", "updates_channel"):
        if s.get(k) and s[k] not in fake_ids:
            errs.append(f"server.{k}: no channel with key {s[k]!r}")
    for r in bp["roles"]:
        for p in r.get("permissions", []):
            if p not in PERMS:
                errs.append(f"role {r['name']}: unknown permission {p}")
    for cat, ch in channels(bp):
        w = f"#{ch['key']}"
        if ch["type"] not in TYPES:
            errs.append(f"{w}: unknown type {ch['type']}")
        if len(ch["name"]) > 100:
            errs.append(f"{w}: name over 100 characters")
        if ch.get("topic"):
            check_text(f"{w} topic", ch["topic"], 4096 if ch["type"] == "forum" else 1024)
        if ch.get("message"):
            check_text(f"{w} message", ch["message"], 2000)
        tags = ch.get("tags", [])
        if len(tags) > 20:
            errs.append(f"{w}: more than 20 tags")
        for t in tags:
            if len(t["name"]) > 20:
                errs.append(f"{w}: tag {t['name']!r} is over 20 characters")
        names = {t["name"] for t in tags}
        for post in ch.get("posts", []):
            if len(post["title"]) > 100:
                errs.append(f"{w}: post title over 100 characters")
            check_text(f"{w} post {post['title']!r}", post["message"], 2000)
            for t in post.get("tags", []):
                if t not in names:
                    errs.append(f"{w}: post {post['title']!r} uses a tag the forum does not have: {t}")
        poll = ch.get("poll")
        if poll:
            if len(poll["question"]) > 300 or not 1 <= len(poll["answers"]) <= 10:
                errs.append(f"{w}: a poll has a question of up to 300 characters and 1-10 answers")
            if not 1 <= poll.get("hours", 24) <= 768:
                errs.append(f"{w}: a poll lasts 1-768 hours")
            for a in poll["answers"]:
                if len(a["text"]) > 55:
                    errs.append(f"{w}: poll answer {a['text']!r} is over 55 characters")
    for rule in bp.get("automod", []):
        if rule["trigger"] not in TRIGGERS:
            errs.append(f"automod {rule['name']}: unknown trigger {rule['trigger']}")
        if len(rule.get("message", "")) > 150:
            errs.append(f"automod {rule['name']}: message over 150 characters")
    ob = bp.get("onboarding", {})
    for k in ob.get("default_channels", []) + ob.get("resources", []) + [t["channel"] for t in ob.get("todo", [])]:
        if k not in fake_ids:
            errs.append(f"onboarding: no channel with key {k!r}")
    writable = [k for k in ob.get("default_channels", [])
                if k in fake_ids and not next(c for _, c in channels(bp) if c["key"] == k).get("readonly")]
    if ob.get("default_channels") and (len(ob["default_channels"]) < 7 or len(writable) < 5):
        errs.append("onboarding: Discord wants at least 7 default channels, 5 of them open to chat")
    for q in ob.get("questions", []):
        for o in q["options"]:
            if len(o["title"]) > 50 or len(o.get("description", "")) > 100:
                errs.append(f"onboarding option {o['title']!r}: title over 50 or description over 100")
            errs += [f"onboarding option {o['title']!r}: no role {r!r}" for r in o["roles"] if r not in rkeys]
            errs += [f"onboarding option {o['title']!r}: no channel {c!r}" for c in o["channels"] if c not in fake_ids]
    return errs


def show(bp: dict) -> None:
    s = bp["server"]
    print(f"{s['name']}: {s['tagline']}\n")
    print("ROLES (top to bottom)")
    for r in bp["roles"]:
        apart = "listed apart" if r.get("hoist") else ""
        print(f"  {r['name']:<14} {r.get('color', 'no colour'):<10} {apart:<13} {r['about']}")
    for cat in bp["categories"]:
        print(f"\n{cat['name'].upper()}" + ("   (Moderators only)" if cat.get("private") else ""))
        for ch in cat["channels"]:
            kind = {"text": "", "voice": "voice", "announcement": "announcements", "forum": "forum"}[ch["type"]]
            flags = ", ".join(x for x in (kind, "read-only" if ch.get("readonly") else "") if x)
            print(f"  {ch['name']:<22} {flags}")
    print("\nLater, when the team asks for it:")
    for item in bp.get("later", []):
        print(f"  {item}")


# --- the build ---------------------------------------------------------------------------------

class Build:
    def __init__(self, api: Discord, bp: dict, gid: str, icon: pathlib.Path | None, community: bool):
        self.api, self.bp, self.gid, self.icon, self.want_community = api, bp, gid, icon, community
        self.links = dict(bp["links"])
        self.role = {}          # key -> role id
        self.chan = {}          # key -> channel id
        self.state = {}         # key -> the channel object as Discord last returned it
        self.new = set()        # keys of channels made in this run
        self.deferred = []      # announcement and forum channels, made once Community is on
        self.used = set()       # ids of existing channels the blueprint has adopted

    def run(self) -> None:
        api, gid = self.api, self.gid
        self.guild = api.get(f"/guilds/{gid}")
        print(f"Server: {self.guild['name']} ({gid})" + ("   DRY RUN: nothing will change" if api.dry else ""))
        self.community = "COMMUNITY" in self.guild.get("features", [])
        self.existing = [c for c in api.get(f"/guilds/{gid}/channels")]
        self.roles()
        self.structure(defer=True)
        self.settings()
        self.structure(defer=False)
        self.sync()
        self.order()
        self.automod()
        self.webhooks()
        self.posts()
        leftovers = [c for c in self.existing if c["id"] not in self.used]
        if leftovers:
            print("\nNot in the blueprint, left alone (delete them by hand if they are Discord's defaults):")
            for c in leftovers:
                kind = {CATEGORY: "category", VOICE: "voice"}.get(c["type"], "text")
                print(f"  {c['name']} ({kind})")
        print("\nDone." if not api.dry else "\nDry run done: run without --dry-run to make these changes.")

    # roles ---------------------------------------------------------------------------------
    def roles(self) -> None:
        api, gid = self.api, self.gid
        have = {norm(r["name"]): r for r in api.get(f"/guilds/{gid}/roles")}
        print("\nRoles")
        for spec in self.bp["roles"]:
            color = int(spec["color"].lstrip("#"), 16) if spec.get("color") else 0
            bits = 0
            for p in spec.get("permissions", []):
                bits |= PERMS[p]
            r = have.get(norm(spec["name"]))
            if r is None:
                r = api.post(f"/guilds/{gid}/roles", {"name": spec["name"], "color": color,
                                                      "hoist": bool(spec.get("hoist")), "mentionable": False,
                                                      "permissions": str(bits)})
                print(f"  + {spec['name']}")
            else:
                change = {}
                if r["name"] != spec["name"]:
                    change["name"] = spec["name"]
                if r.get("color", 0) != color:
                    change["color"] = color
                if bool(r.get("hoist")) != bool(spec.get("hoist")):
                    change["hoist"] = bool(spec.get("hoist"))
                if int(r.get("permissions", 0)) & bits != bits:        # add what is missing, remove nothing
                    change["permissions"] = str(int(r.get("permissions", 0)) | bits)
                if change:
                    api.patch(f"/guilds/{gid}/roles/{r['id']}", change)
                    print(f"  ~ {spec['name']} ({', '.join(change)})")
            self.role[spec["key"]] = r["id"]
        # our roles, top of the blueprint highest; all of them stay below the bot's own role
        n = len(self.bp["roles"])
        try:
            api.patch(f"/guilds/{gid}/roles",
                      [{"id": self.role[s["key"]], "position": n - i} for i, s in enumerate(self.bp["roles"])])
        except ApiError as e:
            print(f"  ! could not put the roles in order ({e.code}): drag them in Server Settings > Roles")

    # channels ------------------------------------------------------------------------------
    def overwrites(self, spec: dict, current: list | None = None) -> list:
        """The blueprint's overwrites, merged into what the channel already has: private shows it
        to Moderators only, read-only lets only Moderators write. Nothing else is removed."""
        everyone, mod = self.gid, self.role["moderator"]
        want = {}

        def add(rid, allow=0, deny=0):
            a, d = want.get(rid, (0, 0))
            want[rid] = (a | allow, d | deny)

        if spec.get("private"):
            add(everyone, deny=P["VIEW_CHANNEL"])
            add(mod, allow=P["VIEW_CHANNEL"])
        if spec.get("readonly"):
            add(everyone, deny=WRITE)
            add(mod, allow=WRITE)
        have = {o["id"]: (int(o["allow"]), int(o["deny"]), o["type"]) for o in current or []}
        for rid, (a, d) in want.items():
            ha, hd, _ = have.get(rid, (0, 0, 0))
            have[rid] = ((ha | a) & ~d, (hd | d) & ~a, 0)
        return [{"id": rid, "type": t, "allow": str(a), "deny": str(d)} for rid, (a, d, t) in have.items()]

    def find(self, name: str, family: set) -> dict | None:
        key = norm(name)
        for c in self.existing:
            if c["id"] not in self.used and c["type"] in family and norm(c["name"]) == key:
                self.used.add(c["id"])
                return c
        return None

    def structure(self, defer: bool) -> None:
        api, gid = self.api, self.gid
        if defer:
            print("\nChannels")
            self.cat = {}
            for cat in self.bp["categories"]:
                c = self.find(cat["name"], {CATEGORY})
                if c is None:
                    c = api.post(f"/guilds/{gid}/channels", {"name": cat["name"], "type": CATEGORY,
                                                            "permission_overwrites": self.overwrites(cat)})
                    print(f"  + {cat['name']}")
                else:
                    change = {}
                    if c["name"] != cat["name"]:
                        change["name"] = cat["name"]
                    ow = self.overwrites(cat, c.get("permission_overwrites"))
                    if canon(ow) != canon(c.get("permission_overwrites") or []):
                        change["permission_overwrites"] = ow
                    if change:
                        api.patch(f"/channels/{c['id']}", change)
                        print(f"  ~ {cat['name']} ({', '.join(change)})")
                self.cat[cat["name"]] = c["id"]
        todo = [(cat, ch) for cat, ch in channels(self.bp)] if defer else self.deferred
        if not defer and todo:
            print("\nAnnouncement and forum channels")
        for cat, ch in todo:
            voice = ch["type"] == "voice"
            if defer:
                c = self.find(ch["name"], {VOICE} if voice else {TEXT, ANNOUNCEMENT, FORUM})
                if c is not None:
                    self.chan[ch["key"]], self.state[ch["key"]] = c["id"], c
                    continue
                if ch["type"] in ("announcement", "forum"):
                    self.deferred.append((cat, ch))
                    continue
            self.chan[ch["key"]] = self.create(cat, ch)["id"]         # create() keeps its state
            self.new.add(ch["key"])

    def create(self, cat: dict, ch: dict) -> dict:
        kind = TYPES[ch["type"]]
        if kind == ANNOUNCEMENT and not self.community:
            kind = TEXT
        body = {"name": ch["name"], "type": kind, "parent_id": self.cat[cat["name"]],
                "permission_overwrites": self.overwrites(ch)}
        if ch.get("topic") and not PLACEHOLDER.search(ch["topic"]):
            body["topic"] = ch["topic"]
        if ch.get("slowmode"):
            body["rate_limit_per_user"] = ch["slowmode"]
        if kind == FORUM:
            body["available_tags"] = [{"name": t["name"], "emoji_name": t.get("emoji"),
                                       "moderated": bool(t.get("moderated"))} for t in ch.get("tags", [])]
            if ch.get("reaction"):
                body["default_reaction_emoji"] = {"emoji_id": None, "emoji_name": ch["reaction"]}
        c = None
        for attempt in emoji_variants(body):
            try:
                c = self.api.post(f"/guilds/{self.gid}/channels", attempt)
                break
            except ApiError as e:
                if e.status != 400:
                    raise
                last = e
        if c is None and kind == FORUM:           # a server without forums: an ordinary channel
            print(f"  ! {ch['name']}: no forum here ({last}); making a text channel")
            body = {k: v for k, v in body.items() if k not in ("available_tags", "default_reaction_emoji")}
            c = self.api.post(f"/guilds/{self.gid}/channels", {**body, "type": TEXT})
        elif c is None:
            raise last
        print(f"  + {ch['name']}" + ("" if c.get("type", kind) == TYPES[ch["type"]] else "  (as a text channel)"))
        self.state[ch["key"]] = c
        return c

    def settings(self) -> None:
        api, s = self.api, self.bp["server"]
        g = self.guild
        change = {}
        if g["name"] != s["name"]:
            change["name"] = s["name"]
        for k in ("verification_level", "default_message_notifications", "explicit_content_filter"):
            if k in s and g.get(k) != s[k] and not (k == "verification_level" and g.get(k, 0) > s[k]):
                change[k] = s[k]
        if s.get("system_channel") and g.get("system_channel_id") != self.chan[s["system_channel"]]:
            change["system_channel_id"] = self.chan[s["system_channel"]]
        if self.icon:
            mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif"}
            data = base64.b64encode(self.icon.read_bytes()).decode()
            change["icon"] = f"data:{mime.get(self.icon.suffix.lower(), 'image/png')};base64,{data}"
        if self.want_community and not self.community:
            change["features"] = list(g.get("features", [])) + ["COMMUNITY"]
            change["verification_level"] = max(g.get("verification_level", 0), s.get("verification_level", 1), 1)
            change["explicit_content_filter"] = 2
        if self.want_community or self.community:
            change["rules_channel_id"] = self.chan[s["rules_channel"]]
            change["public_updates_channel_id"] = self.chan[s["updates_channel"]]
            if s.get("description") and g.get("description") != s["description"]:
                change["description"] = s["description"]
            if g.get("rules_channel_id") == change["rules_channel_id"]:
                del change["rules_channel_id"]
            if g.get("public_updates_channel_id") == change["public_updates_channel_id"]:
                del change["public_updates_channel_id"]
        print("\nServer settings")
        if not change:
            return
        try:
            api.patch(f"/guilds/{self.gid}", change)
            shown = {k: ("<image>" if k == "icon" else v) for k, v in change.items() if k != "features"}
            print(f"  ~ {', '.join(shown)}")
            if "features" in change:
                self.community = True
                print("  + Community is on (announcements, forums, onboarding, the server guide)")
        except ApiError as e:
            if "features" not in change:
                raise
            print(f"  ! could not turn on Community ({e}).\n"
                  f"    Announcements and forums become text channels; turn it on by hand later and run this again.")
            change.pop("features")
            for k in ("rules_channel_id", "public_updates_channel_id", "description"):
                change.pop(k, None)
            if change:
                api.patch(f"/guilds/{self.gid}", change)

    def sync(self) -> None:
        """Bring every channel's name, place, permissions, topic and slowmode to the blueprint."""
        for cat, ch in channels(self.bp):
            c = self.state.get(ch["key"])
            if c is None:
                c = self.api.get(f"/channels/{self.chan[ch['key']]}") if not self.api.dry else {}
            change = {}
            if c.get("name") != ch["name"]:
                change["name"] = ch["name"]
            if c.get("parent_id") != self.cat[cat["name"]]:
                change["parent_id"] = self.cat[cat["name"]]
            ow = self.overwrites(ch, c.get("permission_overwrites"))
            if canon(ow) != canon(c.get("permission_overwrites") or []):
                change["permission_overwrites"] = ow
            if ch.get("topic"):
                topic = text(ch["topic"], self.links, self.chan)
                if (c.get("topic") or "") != topic:
                    change["topic"] = topic
            if ch.get("slowmode") and c.get("rate_limit_per_user") != ch["slowmode"]:
                change["rate_limit_per_user"] = ch["slowmode"]
            if ch["type"] == "announcement" and self.community and c.get("type") == TEXT:
                change["type"] = ANNOUNCEMENT
            if ch["type"] == "forum" and c.get("type") not in (None, FORUM) and ch["key"] not in self.new:
                print(f"  ! {ch['name']} is a text channel; Discord cannot turn it into a forum. "
                      f"Delete it and run this again for a forum.")
            if change:
                self.state[ch["key"]] = self.api.patch(f"/channels/{self.chan[ch['key']]}", change) or c
                if ch["key"] not in self.new or set(change) - {"topic"}:
                    print(f"  ~ {ch['name']} ({', '.join(change)})")

    def order(self) -> None:
        """Categories and channels in blueprint order; anything else keeps its order below them."""
        cats = [self.cat[c["name"]] for c in self.bp["categories"]]
        others = [c["id"] for c in sorted(self.existing, key=lambda c: c.get("position", 0))
                  if c["type"] == CATEGORY and c["id"] not in cats]
        moves = [{"id": cid, "position": i} for i, cid in enumerate(cats + others)]
        for cat in self.bp["categories"]:
            mine = [self.chan[ch["key"]] for ch in cat["channels"]]
            rest = [c["id"] for c in sorted(self.existing, key=lambda c: c.get("position", 0))
                    if c.get("parent_id") == self.cat[cat["name"]] and c["id"] not in mine and c["type"] != CATEGORY]
            moves += [{"id": cid, "position": i} for i, cid in enumerate(mine + rest)]
        try:
            self.api.patch(f"/guilds/{self.gid}/channels", moves)
        except ApiError as e:
            print(f"  ! could not put the channels in order ({e.code}): drag them by hand")

    # moderation, feeds and first posts -----------------------------------------------------
    def automod(self) -> None:
        api, gid = self.api, self.gid
        have = api.get(f"/guilds/{gid}/auto-moderation/rules") or []
        print("\nAutoMod")
        for rule in self.bp.get("automod", []):
            trigger = TRIGGERS[rule["trigger"]]
            if any(r["trigger_type"] == trigger or r["name"] == rule["name"] for r in have):
                continue                         # Discord allows one rule of each of these kinds
            meta = {}
            if trigger == 4:
                meta = {"presets": [PRESETS[p] for p in rule["presets"]]}
            if trigger == 5:
                meta = {"mention_total_limit": rule.get("mention_limit", 5), "mention_raid_protection_enabled": True}
            block = {"type": 1, "metadata": {"custom_message": rule["message"]} if rule.get("message") else {}}
            alert = {"type": 2, "metadata": {"channel_id": self.chan[self.bp["server"]["updates_channel"]]}}
            try:
                api.post(f"/guilds/{gid}/auto-moderation/rules", {
                    "name": rule["name"], "event_type": 1, "trigger_type": trigger, "trigger_metadata": meta,
                    "actions": [block, alert], "enabled": True, "exempt_roles": [self.role["moderator"]]})
                print(f"  + {rule['name']}")
            except ApiError as e:
                print(f"  ! {rule['name']}: {e}")

    def webhooks(self) -> None:
        for _, ch in channels(self.bp):
            if not ch.get("webhook"):
                continue
            cid = self.chan[ch["key"]]
            if self.api.dry:
                print(f"\n  would make the {ch['webhook']} webhook in {ch['name']}")
                continue
            hooks = self.api.get(f"/channels/{cid}/webhooks") or []
            hook = next((h for h in hooks if h.get("name") == ch["webhook"] and h.get("token")), None)
            if hook is None:
                hook = self.api.post(f"/channels/{cid}/webhooks", {"name": ch["webhook"]})
            url = f"https://discord.com/api/webhooks/{hook['id']}/{hook['token']}"
            print(f"\n{ch['webhook']} feed for {ch['name']}. Keep this address private; paste it in GitHub:\n"
                  f"  repository > Settings > Webhooks > Add webhook\n"
                  f"  Payload URL:  {url}/github\n"
                  f"  Content type: application/json\n"
                  f"  Events:       Let me select > Issues, Pull requests, Pushes, Releases")

    def posts(self) -> None:
        api = self.api
        owner = self.guild.get("owner_id")
        print("\nFirst posts")
        if owner and "founder" in self.role:
            try:
                api.call("PUT", f"/guilds/{self.gid}/members/{owner}/roles/{self.role['founder']}")
            except ApiError as e:
                print(f"  ! could not give the owner the Founder role: {e}")
        for _, ch in channels(self.bp):
            key, cid = ch["key"], self.chan[ch["key"]]
            c = self.state.get(key) or {}
            fresh = key in self.new or (not api.dry and c.get("last_message_id") is None
                                        and c.get("type") in (TEXT, ANNOUNCEMENT))
            if not fresh:
                continue
            if ch.get("message"):
                api.post(f"/channels/{cid}/messages", {"content": text(ch["message"], self.links, self.chan),
                                                       "allowed_mentions": {"parse": []}})
                print(f"  + message in {ch['name']}")
            if ch.get("poll"):
                p = ch["poll"]
                answers = [{"poll_media": {"text": a["text"], **({"emoji": {"name": a["emoji"]}} if a.get("emoji") else {})}}
                           for a in p["answers"]]
                body = {"poll": {"question": {"text": p["question"]}, "answers": answers,
                                 "duration": p.get("hours", 24), "allow_multiselect": bool(p.get("multiselect")),
                                 "layout_type": 1}}
                self.post_variants(f"/channels/{cid}/messages", body, f"poll in {ch['name']}")
            if ch.get("posts") and key in self.new:
                forum = c if c.get("available_tags") is not None else (api.get(f"/channels/{cid}") if not api.dry else c)
                tag_id = {t["name"]: t["id"] for t in forum.get("available_tags") or []}
                for post in ch["posts"]:
                    body = {"name": post["title"],
                            "message": {"content": text(post["message"], self.links, self.chan),
                                        "allowed_mentions": {"parse": []}}}
                    if forum.get("type", FORUM) == FORUM:
                        body["applied_tags"] = [tag_id[t] for t in post.get("tags", []) if t in tag_id]
                        self.post_variants(f"/channels/{cid}/threads", body, f"post in {ch['name']}: {post['title']}")
                    else:                        # the forum fell back to a text channel: post it as a message
                        api.post(f"/channels/{cid}/messages", {"content": f"**{post['title']}**\n" + body["message"]["content"],
                                                               "allowed_mentions": {"parse": []}})
                        print(f"  + message in {ch['name']}: {post['title']}")

    def post_variants(self, path, body, label):
        last = None
        for attempt in emoji_variants(body):
            try:
                self.api.post(path, attempt)
                print(f"  + {label}")
                return
            except ApiError as e:
                if e.status != 400:
                    raise
                last = e
        print(f"  ! {label}: {last}")


def emoji_variants(body):
    """The body as written, then with emoji variation selectors stripped, then with no emoji at all:
    Discord is picky about which form of an emoji it accepts in tags and polls."""
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True)
    seen = {raw}
    yield body
    for variant in (json.loads(raw.replace(VS16, "")), strip_emoji(json.loads(raw))):
        key = json.dumps(variant, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            yield variant


def strip_emoji(x):
    if isinstance(x, dict):
        return {k: strip_emoji(v) for k, v in x.items()
                if k not in ("emoji", "emoji_name", "default_reaction_emoji")}
    if isinstance(x, list):
        return [strip_emoji(v) for v in x]
    return x


def canon(overwrites: list) -> set:
    return {(o["id"], int(o.get("type", 0)), int(o["allow"]), int(o["deny"])) for o in overwrites}


def invite_link(app_id: str) -> str:
    """The link that adds the bot to a server with Administrator (permission bit 8)."""
    return f"https://discord.com/oauth2/authorize?client_id={app_id}&scope=bot&permissions=8"


def pick_guild(api: Discord, wanted: str | None) -> str:
    if wanted:
        return wanted
    guilds = api.get("/users/@me/guilds")
    if len(guilds) == 1:
        return guilds[0]["id"]
    if not guilds:
        app = api.get("/oauth2/applications/@me")
        sys.exit("The bot is in no server yet. Open this link, pick Controglobe and press Authorise, then run this again:\n"
                 f"  {invite_link(app['id'])}")
    print("The bot is in several servers; run again with --guild and one of these IDs:")
    for g in guilds:
        print(f"  {g['id']}  {g['name']}")
    sys.exit(2)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--blueprint", default=str(HERE / "discord-server.json"))
    ap.add_argument("--show", action="store_true", help="print the layout and check it; no Discord")
    ap.add_argument("--dry-run", action="store_true", help="read the server and print what would change")
    ap.add_argument("--guild", help="the server ID (only needed if the bot is in more than one)")
    ap.add_argument("--icon", help="a square PNG, JPEG or GIF for the server icon")
    ap.add_argument("--no-community", action="store_true",
                    help="leave Community off (announcement and forum channels become text channels)")
    args = ap.parse_args(argv)

    bp = load(pathlib.Path(args.blueprint))
    errs = validate(bp)
    for e in errs:
        print(f"blueprint: {e}")
    if errs:
        return 1
    if args.show:
        show(bp)
        return 0
    icon = pathlib.Path(args.icon) if args.icon else None
    if icon and not icon.exists():
        sys.exit(f"no such icon file: {icon}")
    token = os.environ.get("DISCORD_TOKEN") or getpass.getpass("Bot token (it is not shown or saved): ")
    token = token.strip().removeprefix("Bot ").strip()
    api = Discord(token, dry=args.dry_run)
    try:
        gid = pick_guild(api, args.guild)
        Build(api, bp, gid, icon, community=not args.no_community).run()
    except ApiError as e:
        print(f"\nDiscord refused: {e}")
        if e.status == 401:
            print("The token is wrong or was reset: copy it again from the Developer Portal (Bot > Reset Token).")
        elif e.code == 50013 or e.status == 403:
            print("The bot lacks a permission: invite it with Administrator (README.md, step 3), and in "
                  "Server Settings > Roles drag its role to the top. Running again is safe.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
