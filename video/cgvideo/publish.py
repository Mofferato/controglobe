"""The YouTube upload kit: everything typed into YouTube Studio, written from the cut itself.

`python build.py timeline` (and every motion render) writes output/youtube/:
  title.txt           title options, each under YouTube's 100 characters
  description.txt     the description, with the chapters of the current cut and the credits
  tags.txt            comma-separated tags, under YouTube's 500 characters
  pinned_comment.txt  a first comment to pin under the video
  checklist.txt       the upload steps, with the paths of the thumbnail and the subtitles
Edit them freely before pasting: they are regenerated only by the pipeline, never read back.
The links and hashtags come from `publish:` in config/project.yaml. PUBLISHING.md has the
whole upload walk-through and the community post.
"""

from __future__ import annotations

from .config import paths

TITLES = [
    "Alternate History of Arabia (in place of the United States) | Every Year, 500 BCE – 2026",
    "What if the United States had formed in Arabia? | Every Year, 500 BCE – 2026",
    "Alternate History of Arabia (in place of the USA) – Every Year",
]

TAGS = ["alternate history", "alternate history of arabia", "every year", "mapping", "map animation",
        "alternate history map", "controglobe", "global swap", "arabia", "united states", "what if",
        "history", "geography", "worldbuilding", "timelapse map", "qgis"]


def write(cfg, slots, S, fps) -> None:
    """slots: the timeline's Slot objects; S: motion.structure of the cut."""
    from .motion import mcfg
    from .timeline import chapters, timecode
    pub = cfg.get("publish") or {}
    site = pub.get("site", "https://mofferato.github.io/controglobe/")
    repo = pub.get("repo", "https://github.com/Mofferato/controglobe")
    community = pub.get("community")
    tags = " ".join(pub.get("hashtags") or ["#AlternateHistory", "#Mapping", "#Controglobe"])
    out = paths(cfg).output / "youtube"
    out.mkdir(parents=True, exist_ok=True)
    first, last = slots[0].label, slots[-1].label
    end_card = int(round(float(mcfg(cfg)["end_card_seconds"])))
    chap ="\n".join(f"{timecode(f, fps)} {title}" for f, title in chapters(slots, S, fps))
    join = (f"Come and say hi, or join the team: {community}\n" if community else
            f"Come and say hi, or join the team: open an issue at {repo}/issues\n")
    (out / "title.txt").write_text("\n".join(t for t in TITLES if len(t) <= 100) + "\n", encoding="utf8")
    (out / "tags.txt").write_text(", ".join(TAGS) + "\n", encoding="utf8")
    description = f"""What if the history of the United States had happened in Arabia? In Controglobe's Global Swap one change is applied consistently: from {first} the Global North and the Global South trade their histories. The land stays exactly where it is; only history moves. This is that Arabia every year, {first} to {last}: princely colonies of the Hindustani Empire, a revolution, a civil war, two world wars, a cold war with the Derg Union, and a union of 24 states today.

Geography is fixed. Who industrialises, who colonises, who is colonised and who writes the textbooks is not.

Chapters
{chap}

How it was made
An AI-assisted mapping video. The history, the canon and every creative decision are human; the maps, the animation, the music and the edit come from an open-source pipeline built with Claude as a coding assistant, with QGIS, Python and DaVinci Resolve. Every border is drawn on real coastlines (Natural Earth), year by year, from the encyclopedia's canon.

Read the encyclopedia: {site}
Code, data and canon (open source, CC BY-SA 4.0): {repo}

Controglobe is a friends-first project. If you like maps, alternate history, writing, art, music or code, you are welcome to help build this world.
{join}
Credits
Inspired by WTF CD Foxy's alternate-history "every year" videos.
Map data: Natural Earth (public domain). Music and sound effects: made in code for this video, no samples.

{tags}
"""
    (out / "description.txt").write_text(description, encoding="utf8")
    pinned = f"""The encyclopedia behind this video: {site}
Everything is open source, and the project is friends-first: if you want to help (maps, writing, art, music, code) or just talk alternate history, reply here or open an issue at {repo}
Which era should get its own video next?
"""
    (out / "pinned_comment.txt").write_text(pinned, encoding="utf8")
    o = paths(cfg).output
    checklist = f"""YouTube upload checklist (PUBLISHING.md has the details)

1. Upload: YouTube Studio > Create > Upload videos > the newest output/motion/controglobe_motion_<date-time>.mp4
2. Title: pick one from title.txt (under 100 characters)
3. Description: paste description.txt (the chapters are in it; the first must stay at 0:00)
4. Thumbnail: {(o / 'thumbnail_1280x720.png').as_posix()} (under 2 MB)
5. Playlist: add it to one (e.g. "Controglobe: every year")
6. Audience: "No, it's not made for kids"
7. Show more > Altered content: follow YouTube's current wording (a stylised alternate-history map is not a realistic depiction of a real event); the description says how it was made either way
8. Show more > Tags: paste tags.txt; Language English; Caption certification: none; Category Education (or Entertainment)
9. Next > Video elements > Add subtitles > Upload file > With timing > {(o / 'captions.srt').as_posix()}
10. Video elements > End screen: the last {end_card} seconds are the end card; put a video or playlist on the left of the logo and Subscribe on the right
11. Video elements > Cards: a playlist or channel card at an era change you like (external links need the YouTube Partner Programme)
12. Checks: wait for the copyright check (the music is original: nothing to claim)
13. Visibility: Public now, Schedule, or a Premiere (a live countdown with chat: good for a first video)
14. After publishing: pin pinned_comment.txt, answer the first comments, then share it (PUBLISHING.md: the community post)
"""
    (out / "checklist.txt").write_text(checklist, encoding="utf8")
