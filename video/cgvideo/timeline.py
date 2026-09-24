"""Pacing: how many frames each year gets, which captions show, and the edit metadata.

Every year is one still; the still is held for `frames` frames. A year's screen time is its
era's base pace plus dwell for its events (and for an era's first year, a title card), so
2,500 years of antiquity fly past while 1861 stops long enough to read.

Writes to output/:
  timeline.json          the frame plan the renderer, the sequencer and Resolve all read
  captions.srt           one subtitle per event (import into Resolve or upload to YouTube)
  markers.csv            frame-accurate markers: era starts and events, colour by weight
  youtube_chapters.txt   paste into the video description
  narration_budget.csv   seconds and a word ceiling per era for a voice-over script
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field

from . import years as Y
from .config import paths
from .data import Data


@dataclass
class Slot:
    index: int
    year: int
    label: str
    era_id: str
    era_name: str
    era_start: bool
    start_frame: int
    frames: int
    events: list = field(default_factory=list)     # events dated this year
    captions: list = field(default_factory=list)   # everything on screen this year


def _events_by_year(data: Data) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for e in data.events:
        out.setdefault(Y.parse(e["year"]), []).append(e)
    for evs in out.values():
        evs.sort(key=lambda e: -int(e.get("importance") or 1))
    return out


def build(cfg: dict, data: Data) -> tuple[list[Slot], dict]:
    fps = int(cfg["frame"]["fps"])
    pace = cfg["pacing"]
    dwell_table = {int(k): float(v) for k, v in pace["dwell_by_importance"].items()}
    by_year = _events_by_year(data)

    base, dwell, eras = [], [], []
    prev_era = None
    for y in data.year_list:
        era = data.era_of(y)
        if era is None:
            raise SystemExit(f"year {Y.label(y)} is in no era: fix eras.csv")
        eras.append(era)
        base.append(float(era["seconds_per_year"]))
        d = 0.0
        evs = by_year.get(y, [])
        if evs:
            weights = sorted((dwell_table.get(int(e.get("importance") or 1), 0.5) for e in evs), reverse=True)
            d = weights[0] + 0.5 * sum(weights[1:])
        if era["era_id"] != prev_era:
            d += float(pace.get("era_title_seconds", 0))
        dwell.append(d)
        prev_era = era["era_id"]

    scale = 1.0
    target = pace.get("target_minutes")
    if target:
        want = float(target) * 60 - sum(dwell)
        if want <= 0:
            print(f"  warning: event dwell alone exceeds {target} min; pacing left unscaled")
        else:
            scale = want / sum(base)

    min_frames = int(pace.get("min_frames_per_year", 1))
    slots: list[Slot] = []
    clock = 0.0
    frame = 0
    prev_era = None
    for i, y in enumerate(data.year_list):
        clock += base[i] * scale + dwell[i]
        end = max(frame + min_frames, round(clock * fps))
        era = eras[i]
        slots.append(Slot(
            index=i, year=y, label=Y.label(y), era_id=era["era_id"], era_name=era["name"],
            era_start=era["era_id"] != prev_era, start_frame=frame, frames=end - frame,
            events=[{"date": e["date"], "text": e["text"], "importance": int(e.get("importance") or 1)}
                    for e in by_year.get(y, [])]))
        frame = end
        prev_era = era["era_id"]

    # a caption stays up for caption_seconds of screen time, across the years that follow
    hold = float(pace.get("caption_seconds", 4.0)) * fps
    live: list[tuple[int, dict]] = []
    for s in slots:
        live = [(until, e) for until, e in live if until > s.start_frame]
        for e in s.events:
            live.append((s.start_frame + max(hold, s.frames), e))
        s.captions = [e for _, e in sorted(live, key=lambda t: -t[0])][:3]

    meta = {"fps": fps, "total_frames": frame, "seconds": frame / fps, "scale": scale,
            "width": cfg["frame"]["width"], "height": cfg["frame"]["height"], "title": cfg.get("title", "")}
    return slots, meta


def timecode(frame: int, fps: int, srt: bool = False) -> str:
    total = frame / fps
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if srt:
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s % 1) * 1000)) % 1000:03d}"
    return f"{int(h)}:{int(m):02d}:{int(s):02d}" if h else f"{int(m)}:{int(s):02d}"


def write(cfg: dict, data: Data) -> tuple[list[Slot], dict]:
    slots, meta = build(cfg, data)
    out = paths(cfg).output
    out.mkdir(parents=True, exist_ok=True)
    fps = meta["fps"]
    with open(out / "timeline.json", "w", encoding="utf8") as fh:
        json.dump({"meta": meta, "slots": [asdict(s) for s in slots]}, fh, ensure_ascii=False, indent=1)

    hold = float(cfg["pacing"].get("caption_seconds", 4.0)) * fps
    n = 0
    with open(out / "captions.srt", "w", encoding="utf8") as fh:
        for s in slots:
            for e in s.events:
                n += 1
                a = s.start_frame
                b = a + int(max(hold, s.frames))
                fh.write(f"{n}\n{timecode(a, fps, True)} --> {timecode(b, fps, True)}\n{e['date']}: {e['text']}\n\n")

    with open(out / "markers.csv", "w", newline="", encoding="utf8") as fh:
        w = csv.writer(fh)
        w.writerow(["frame", "timecode", "color", "name", "note", "duration"])
        for s in slots:
            if s.era_start:
                w.writerow([s.start_frame, timecode(s.start_frame, fps), "Blue", s.era_name, s.label, s.frames])
            for e in s.events:
                color = {3: "Red", 2: "Yellow", 1: "Green"}.get(e["importance"], "Green")
                w.writerow([s.start_frame, timecode(s.start_frame, fps), color, s.label, e["text"], s.frames])

    with open(out / "youtube_chapters.txt", "w", encoding="utf8") as fh:
        for s in slots:
            if s.era_start:
                fh.write(f"{timecode(s.start_frame, fps)} {s.era_name} ({s.label})\n")

    wpm = 150
    with open(out / "narration_budget.csv", "w", newline="", encoding="utf8") as fh:
        w = csv.writer(fh)
        w.writerow(["era_id", "era", "starts_at", "seconds", "max_words_at_150wpm", "events"])
        for era in data.eras:
            ss = [s for s in slots if s.era_id == era["era_id"]]
            if not ss:
                continue
            secs = sum(s.frames for s in ss) / fps
            w.writerow([era["era_id"], era["name"], timecode(ss[0].start_frame, fps), round(secs, 1),
                        int(secs / 60 * wpm), sum(len(s.events) for s in ss)])
    write_resolve_lua(cfg, slots, meta)
    print(f"  {len(slots)} years, {meta['total_frames']} frames, {timecode(meta['total_frames'], fps)} at {fps} fps"
          + (f" (base pace scaled x{meta['scale']:.2f})" if meta["scale"] != 1 else ""))
    return slots, meta


def _lua_str(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def write_resolve_lua(cfg: dict, slots: list[Slot], meta: dict) -> None:
    """output/resolve_build.lua: the Resolve build as a Lua script, with the data baked in.

    DaVinci Resolve 21.1 and later run Python scripts only in Studio; Lua still runs in the
    free edition. Copy this file to
    %APPDATA%\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Utility\\
    and run it from Workspace > Scripts with a project open.
    """
    P = paths(cfg)
    seq = (P.sequence / "frame_%06d.png").resolve().as_posix()
    colors = {3: "Red", 2: "Yellow", 1: "Green"}
    marks = []
    for s in slots:
        if s.era_start:
            marks.append((s.start_frame, "Blue", s.era_name, s.label, max(1, s.frames)))
        for e in s.events:
            marks.append((s.start_frame, colors.get(e["importance"], "Green"),
                          f"{s.label}: {e['date']}", e["text"], max(1, s.frames)))
    lines = [
        "-- Generated by `python build.py timeline`. Do not edit: re-run the pipeline instead.",
        "-- Builds the Controglobe timeline in DaVinci Resolve (works in the free edition).",
        "local resolve = Resolve()",
        "local project = resolve:GetProjectManager():GetCurrentProject()",
        'if not project then print("Open or create a project first.") return end',
        f'project:SetSetting("timelineResolutionWidth", "{meta["width"]}")',
        f'project:SetSetting("timelineResolutionHeight", "{meta["height"]}")',
        f'project:SetSetting("timelineFrameRate", "{meta["fps"]}")',
        "local mp = project:GetMediaPool()",
        f"local items = mp:ImportMedia({{{{FilePath = {_lua_str(seq)}, StartIndex = 1, "
        f"EndIndex = {meta['total_frames']}}}}})",
        'if not items or #items == 0 then print("Import failed: run `python build.py sequence` first.") return end',
        'local tl = mp:CreateTimelineFromClips("Controglobe v1", items)',
        "project:SetCurrentTimeline(tl)",
        "local marks = {",
    ]
    for f, c, name, note, dur in marks:
        lines.append(f"  {{{f}, {_lua_str(c)}, {_lua_str(name)}, {_lua_str(note)}, {dur}}},")
    lines += [
        "}",
        "local n = 0",
        "for _, m in ipairs(marks) do",
        '  if tl:AddMarker(m[1], m[2], m[3], m[4], m[5], "") then n = n + 1 end',
        "end",
        f'print("Controglobe v1: {meta["total_frames"]} frames, " .. n .. " markers")',
    ]
    (P.output / "resolve_build.lua").write_text("\n".join(lines) + "\n", encoding="utf8")


def load(cfg: dict) -> tuple[list[dict], dict]:
    p = paths(cfg).output / "timeline.json"
    if not p.exists():
        raise SystemExit("no output/timeline.json: run `python build.py timeline` first")
    doc = json.loads(p.read_text(encoding="utf8"))
    return doc["slots"], doc["meta"]
