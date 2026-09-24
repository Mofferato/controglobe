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
    # election years hold long enough to read the result in the infobox
    elections = {int(e["year"]) for e in (getattr(data, "elections", None) or [])}
    election_hold = float(pace.get("election_seconds", 0))

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
        if y in elections:
            d = max(d, 0.0) + election_hold
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
    what = write_resolve_lua(cfg, slots, meta)
    installed = install_resolve_script(cfg)
    print(f"  Resolve build script: {what}" + (f"; installed as {installed}" if installed else ""))
    print(f"  {len(slots)} years, {meta['total_frames']} frames, {timecode(meta['total_frames'], fps)} at {fps} fps"
          + (f" (base pace scaled x{meta['scale']:.2f})" if meta["scale"] != 1 else ""))
    return slots, meta


def _lua_str(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def motion_cut(cfg: dict):
    """The finished motion cut, if `build.py motion` has rendered one (ProRes preferred)."""
    out = paths(cfg).output / "motion"
    for name in ("controglobe_motion.mov", "controglobe_motion.mp4"):
        if (out / name).exists():
            return out / name
    return None


def resolve_scripts_dir():
    """Resolve's per-user Scripts > Utility folder, if Resolve is installed on this machine."""
    import os
    import pathlib
    import sys
    if sys.platform == "win32":
        base = pathlib.Path(os.environ.get("APPDATA", "")) / "Blackmagic Design" / "DaVinci Resolve" / "Support"
    elif sys.platform == "darwin":
        base = pathlib.Path.home() / "Library" / "Application Support" / "Blackmagic Design" / "DaVinci Resolve"
    else:
        base = pathlib.Path.home() / ".local" / "share" / "DaVinciResolve"
    return base / "Fusion" / "Scripts" / "Utility" if base.exists() else None


def install_resolve_script(cfg: dict):
    """Copy output/resolve_build.lua into Resolve's Scripts menu as cg_resolve_build."""
    import shutil
    target = resolve_scripts_dir()
    src = paths(cfg).output / "resolve_build.lua"
    if target is None or not src.exists():
        return None
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, target / "cg_resolve_build.lua")
    return target / "cg_resolve_build.lua"


def write_resolve_lua(cfg: dict, slots: list[Slot], meta: dict, media: str = "auto") -> str:
    """output/resolve_build.lua: the Resolve build as a Lua script, with the data baked in.

    media: "motion" builds from the finished motion cut (output/motion/controglobe_motion.*),
    with the markers moved past its opening and a marker on the opening and the finale;
    "sequence" builds from the image sequence of yearly stills; "auto" takes the motion cut
    when one has been rendered. Returns the media it used.

    What the free edition allows (measured on DaVinci Resolve 21.1.0.14, free):
      - Python scripts do not run at all; Lua scripts from Workspace > Scripts do.
      - The Lua sandbox has no `io` library, so no log file; the report goes to the Console.
      - `Resolve()` returns nil, but the `resolve` object handed to menu scripts works and
        drives the project fully (import, timeline, markers).
      - Fusion's UIManager (script windows) is Studio-only: touching it pops Resolve's
        "limitation" upgrade prompt. The report window is therefore shown on Studio only.
      - An image sequence imports at 24 fps whatever the timeline rate, so the clip's own
        frame rate is set before the timeline is made; the timeline length is then checked.
    If a Resolve refuses project scripting outright, the report carries the manual import.
    Copy this file to
    %APPDATA%\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Utility\\
    and run it from Workspace > Scripts with a project open.
    """
    P = paths(cfg)
    fps = int(meta["fps"])
    log = (P.output / "resolve_build.log").resolve().as_posix()
    movie = motion_cut(cfg) if media in ("auto", "motion") else None
    if media == "motion" and movie is None:
        raise SystemExit("no motion cut yet: run `python build.py motion` first")
    if media == "auto" and movie is None:
        # The finished video is the motion cut. Until one is rendered, the menu script says so
        # instead of quietly building the stills cut, which is only for editing by hand.
        pending = [
            "-- Generated by `python build.py timeline`: no motion cut has been rendered yet.",
            'print("Controglobe: the finished video (the motion cut) is not rendered yet, '
            'so there is nothing to build. Nothing was changed.")',
            'print("Run: python build.py motion   (when it finishes it puts the real script in this menu)")',
            'print("For the stills cut instead: python build.py resolve --media sequence")',
        ]
        (P.output / "resolve_build.lua").write_text("\n".join(pending) + "\n", encoding="utf8")
        return "nothing yet: the motion cut is not rendered (the menu script says so)"
    marks = _markers(slots)
    if movie is not None:
        from .finale import Finale
        from .motion import intro_seconds, mcfg
        m = mcfg(cfg)
        intro = int(round(intro_seconds(m) * fps))
        main = slots[-1].start_frame + slots[-1].frames
        finale = Finale.length(cfg, fps)
        total = intro + main + finale
        marks = ([(0, "Purple", "Opening", "The premise card and the globe", intro)]
                 + [(f + intro, c, n, note, d) for f, c, n, note, d in marks]
                 + [(intro + main, "Purple", "Finale: Arabia in 2025",
                     "Population, religion, ancestry, largest cities, end card", finale)])
        path = movie.resolve().as_posix()
        edl_path = P.output / "markers_motion.edl"
        what, base_name = f"the motion cut {movie.name}", "Controglobe motion v"
        import_lines = [f"  local items = mp:ImportMedia({{{_lua_str(path)}}})"]
        step2 = [f"2. Media page: drag {path} into the Media Pool."]
    else:
        seq_dir = P.sequence.resolve().as_posix()
        seq = (P.sequence / "frame_%06d.png").resolve().as_posix()
        total = int(meta["total_frames"])
        edl_path = P.output / "markers.edl"
        what, base_name = "the yearly stills (output/sequence)", "Controglobe v"
        import_lines = [
            f"  local items = mp:ImportMedia({{{{FilePath = {_lua_str(seq)}, StartIndex = 1, EndIndex = {total}}}}})",
            "  if not items or #items == 0 then",
            '    say("Frame-pattern import returned nothing; importing the folder instead.")',
            "    local ms = r:GetMediaStorage()",
            f"    items = ms and ms:AddItemListToMediaPool({{{_lua_str(seq_dir)}}})",
            "  end",
        ]
        step2 = [f"2. Media page: drag the folder {seq_dir} into the Media Pool. It arrives as one clip."]
    edl = edl_path.resolve().as_posix()
    manual = "\n".join([
        "Manual import (no scripting needed, about a minute):",
        f"1. Make a new project. File > Project Settings > Master Settings: timeline frame rate {fps}.",
        "   Set it BEFORE importing anything: Resolve locks it once a timeline exists.",
        *step2,
        f"3. Right-click the clip > Clip Attributes > Video > Video Frame Rate: {fps}.",
        "4. Right-click the clip > Create New Timeline Using Selected Clips.",
        "5. Right-click the new timeline in the Media Pool > Timelines > Import >",
        f"   Timeline Markers from EDL, and pick {edl}",
    ])
    lines = [
        "-- Generated by `python build.py timeline`. Do not edit: re-run the pipeline instead.",
        "-- Builds the Controglobe timeline in DaVinci Resolve. Run it from Workspace > Scripts",
        "-- with a project open. It reports in Workspace > Console (and, on Studio, in a window).",
        "-- The free edition's Lua has no io library and no script windows: see the notes in",
        "-- cgvideo/timeline.py (write_resolve_lua) for what that edition allows.",
        f"local MANUAL = [==[{manual}]==]",
        "local STUDIO = false",
        "local report = {}",
        "local function say(msg)",
        "  msg = tostring(msg)",
        "  print(msg)",
        "  report[#report + 1] = msg",
        "end",
        "",
        "local function show(text)",
        "  local ok = pcall(function()",
        "    local ui = fu.UIManager",
        "    local disp = bmd.UIDispatcher(ui)",
        '    local win = disp:AddWindow({ID = "CGReport", WindowTitle = "Controglobe: Resolve build",',
        "                                Geometry = {200, 200, 760, 420}},",
        '      ui:VGroup({ui:TextEdit({ID = "Report", PlainText = text, ReadOnly = true}),',
        '                 ui:Button({ID = "OK", Text = "OK", Weight = 0})}))',
        "    win.On.OK.Clicked = function(ev) disp:ExitLoop() end",
        "    win.On.CGReport.Close = function(ev) disp:ExitLoop() end",
        "    win:Show()",
        "    disp:RunLoop()",
        "    win:Hide()",
        "  end)",
        '  if not ok then print("(No report window; the report is above in this Console.)") end',
        "end",
        "",
        "local function try(f, ...)",
        "  local ok, v = pcall(f, ...)",
        "  if ok then return v end",
        "end",
        "",
        "local function main()",
        '  say("Scripting check: resolve=" .. type(resolve) .. ", Resolve=" .. type(Resolve) .. ", bmd="',
        '      .. type(bmd) .. ", fu=" .. type(fu) .. ", io=" .. type(io))',
        "  -- A menu script is handed a live `resolve`; else ask for one. On free 21.1 Resolve()",
        "  -- returns nil while the handed-in `resolve` works, so the global comes first.",
        "  local r = resolve",
        '  if not r and bmd and bmd.scriptapp then r = try(bmd.scriptapp, "Resolve") end',
        "  if not r and Resolve then r = try(Resolve) end",
        "  if not r and app then r = try(function() return app:GetResolve() end) end",
        "  if not r then",
        '    say("RESULT: this DaVinci Resolve does not let scripts control projects. Nothing was changed.")',
        '    say("")',
        "    say(MANUAL)",
        "    return",
        "  end",
        '  local product = tostring(try(function() return r:GetProductName() end) or "DaVinci Resolve")',
        '  local version = tostring(try(function() return r:GetVersionString() end) or "?")',
        '  STUDIO = product:find("Studio") ~= nil',
        '  say(product .. " " .. version)',
        "  local pm = r:GetProjectManager()",
        "  local project = pm and pm:GetCurrentProject()",
        '  if not project then say("RESULT: no project is open. Open or create one, then run this again.") return end',
        '  say("Project: " .. tostring(project:GetName()))',
        f'  say("Building from {what}.")',
        '  local rate = tonumber(project:GetSetting("timelineFrameRate"))',
        f"  if rate ~= {fps} then",
        f'    if project:SetSetting("timelineFrameRate", "{fps}") then',
        f'      project:SetSetting("timelinePlaybackFrameRate", "{fps}")',
        f'      say("Timeline frame rate set to {fps}.")',
        "    else",
        f'      say("WARNING: this project runs at " .. tostring(rate) .. " fps and Resolve will not change it "',
        f'          .. "now. Use a new project set to {fps} fps, or the video will play at the wrong speed.")',
        "    end",
        "  end",
        "  local mp = project:GetMediaPool()",
        *import_lines,
        "  if not items or #items == 0 then",
        '    say("RESULT: the media did not import. Render it first (python build.py motion, or sequence).")',
        "    return",
        "  end",
        '  say("Imported " .. #items .. " clip(s).")',
        "  -- An image sequence comes in at 24 fps whatever the timeline runs at, so the clip's own",
        "  -- rate is set before it goes on a timeline (Resolve locks it after); a movie keeps its own.",
        "  for i, item in ipairs(items) do",
        '    local before = try(function() return item:GetClipProperty("FPS") end)',
        f"    if tonumber(before) ~= {fps} then",
        f'      local changed = try(function() return item:SetClipProperty("FPS", "{fps}") end)',
        '      local after = try(function() return item:GetClipProperty("FPS") end)',
        '      say("Clip frame rate: " .. tostring(before) .. " -> " .. tostring(after)',
        '          .. (changed and "" or " (Resolve refused the change)"))',
        "    else",
        '      say("Clip frame rate: " .. tostring(before))',
        "    end",
        "  end",
        "  -- A fresh name each run, so a second run never collides with the first.",
        "  local taken = {}",
        "  for i = 1, (project:GetTimelineCount() or 0) do",
        "    local t = project:GetTimelineByIndex(i)",
        "    if t then taken[t:GetName()] = true end",
        "  end",
        f'  local name, v = "{base_name}1", 1',
        f'  while taken[name] do v = v + 1 name = "{base_name}" .. v end',
        "  local tl = mp:CreateTimelineFromClips(name, items)",
        '  if not tl then say("RESULT: Resolve would not make the timeline.") return end',
        "  project:SetCurrentTimeline(tl)",
        "  local frames = tl:GetEndFrame() - tl:GetStartFrame()",
        '  say("Timeline: " .. tl:GetName() .. ", " .. frames .. " frames.")',
        f"  if frames ~= {total} then",
        f'    say("WARNING: expected {total} frames. The clip is not at {fps} fps, so the video plays at the "',
        f'        .. "wrong speed and the markers drift. Right-click the clip > Clip Attributes > Video > "',
        f'        .. "Video Frame Rate: {fps}, then make the timeline again.")',
        "  end",
        "  local marks = {",
    ]
    for f, c, name, note, dur in marks:
        lines.append(f"    {{{f}, {_lua_str(c)}, {_lua_str(name)}, {_lua_str(note)}, {dur}}},")
    lines += [
        "  }",
        "  local n = 0",
        "  for _, m in ipairs(marks) do",
        '    if tl:AddMarker(m[1], m[2], m[3], m[4], m[5], "") then n = n + 1 end',
        "  end",
        f'  say("Markers: " .. n .. " of {len(marks)}.")',
        '  say("RESULT: done.")',
        "end",
        "",
        "local ok, err = pcall(main)",
        "if not ok then",
        '  say("ERROR: " .. tostring(err))',
        '  say("")',
        "  say(MANUAL)",
        "end",
        f"local LOG = {_lua_str(log)}",
        "if io and io.open then",
        '  local fh = io.open(LOG, "w")',
        '  if fh then fh:write(table.concat(report, "\\n"), "\\n") fh:close() end',
        "end",
        "-- Script windows are a Studio feature; on the free edition they pop an upgrade prompt.",
        'if STUDIO then show(table.concat(report, "\\n")) end',
    ]
    (P.output / "resolve_build.lua").write_text("\n".join(lines) + "\n", encoding="utf8")
    write_marker_edl(cfg, marks, meta, edl_path)
    return what


def _markers(slots: list[Slot]) -> list[tuple]:
    """One marker per year that has an era start or events: Resolve keeps one per frame.

    Colour is the weightiest thing on that frame: Red (importance 3), Yellow (2), Blue (an era
    starts), Green (1).
    """
    colors = {3: "Red", 2: "Yellow", 1: "Green"}
    rank = {"Red": 0, "Yellow": 1, "Blue": 2, "Green": 3}
    marks = []
    for s in slots:
        names, notes, cols = [], [], []
        if s.era_start:
            names.append(s.era_name)
            notes.append(f"Era: {s.era_name} from {s.label}")
            cols.append("Blue")
        for e in s.events:
            names.append(f"{s.label}: {e['date']}" if not names else e["date"])
            notes.append(e["text"])
            cols.append(colors.get(e["importance"], "Green"))
        if names:
            color = min(cols, key=rank.get)
            marks.append((s.start_frame, color, " / ".join(names), " | ".join(notes), max(1, s.frames)))
    return marks


def write_marker_edl(cfg: dict, marks: list[tuple], meta: dict, dest=None) -> None:
    """output/markers.edl: the same markers for Resolve's own importer, no scripting needed.

    In Resolve: Media Pool, right-click the timeline > Timelines > Import > Timeline Markers
    from EDL. Assumes the timeline starts at 01:00:00:00, Resolve's default.
    """
    fps = int(meta["fps"])

    def tc(frame: int) -> str:
        frame += 3600 * fps  # 01:00:00:00
        h, rem = divmod(frame, 3600 * fps)
        m, rem = divmod(rem, 60 * fps)
        s, f = divmod(rem, fps)
        return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"

    out = ["TITLE: Controglobe markers", "FCM: NON-DROP FRAME", ""]
    for n, (f, color, name, note, dur) in enumerate(marks, 1):
        text = f"{name} - {note}".replace("|", "/")
        out.append(f"{n:03d}  001      V     C        {tc(f)} {tc(f + 1)} {tc(f)} {tc(f + 1)}  ")
        out.append(f" |C:ResolveColor{color} |M:{text} |D:{dur}")
        out.append("")
    (dest or paths(cfg).output / "markers.edl").write_text("\n".join(out), encoding="utf8")


def load(cfg: dict) -> tuple[list[dict], dict]:
    p = paths(cfg).output / "timeline.json"
    if not p.exists():
        raise SystemExit("no output/timeline.json: run `python build.py timeline` first")
    doc = json.loads(p.read_text(encoding="utf8"))
    return doc["slots"], doc["meta"]
