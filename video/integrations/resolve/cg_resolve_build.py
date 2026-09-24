"""Build the DaVinci Resolve project from the pipeline's output.

What it does
  - creates (or opens) the project at the video's resolution and frame rate
  - imports output/sequence/frame_%06d.png as ONE clip and makes a timeline from it
  - optionally adds music and a narration track (CG_MUSIC, CG_NARRATION)
  - drops a marker on every era start and every event, coloured by weight (from timeline.json)
  - optionally queues and starts an H.264 render (CG_RENDER=1)

Run it
  Resolve Studio: Preferences > System > General > External scripting using: Local, keep
    Resolve open, then from a terminal:  python integrations/resolve/cg_resolve_build.py
  Resolve (free): external scripting is Studio-only. Copy this file into
    %APPDATA%\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Utility\\  (Windows)
    and run it from Workspace > Scripts > cg_resolve_build. Set CG_VIDEO_DIR first, because
    the copy no longer sits inside the video folder.

Captions: import output/captions.srt with File > Import > Subtitle (or ask Claude to do it
through the DaVinci Resolve MCP server).
"""

import json
import os
import pathlib
import sys


def video_dir() -> pathlib.Path:
    env = os.environ.get("CG_VIDEO_DIR")
    if env:
        return pathlib.Path(env)
    here = globals().get("__file__")
    if here:
        return pathlib.Path(here).resolve().parents[2]
    raise SystemExit("set CG_VIDEO_DIR to the controglobe/video folder")


def get_resolve():
    if globals().get("resolve"):
        return globals()["resolve"]
    bmd_mod = globals().get("bmd")
    if bmd_mod is not None:  # Resolve's own interpreter (Workspace > Scripts)
        return bmd_mod.scriptapp("Resolve")
    try:
        import DaVinciResolveScript as dvr
    except ImportError:
        for p in (r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules",
                  "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
                  "/opt/resolve/Developer/Scripting/Modules"):
            if os.path.isdir(p):
                sys.path.append(p)
        import DaVinciResolveScript as dvr
    app = dvr.scriptapp("Resolve")
    if app is None:
        raise SystemExit("could not reach Resolve: is it running, and is external scripting set to Local?")
    return app


def main():
    v = video_dir()
    doc = json.loads((v / "output" / "timeline.json").read_text(encoding="utf8"))
    meta, slots = doc["meta"], doc["slots"]
    seq = v / "output" / "sequence"
    if not (seq / "frame_000001.png").exists():
        raise SystemExit("no output/sequence: run `python build.py sequence` first")

    resolve = get_resolve()
    pm = resolve.GetProjectManager()
    name = os.environ.get("CG_PROJECT", "Controglobe - Arabia in place of the US")
    project = pm.LoadProject(name) or pm.CreateProject(name)
    if project is None:
        raise SystemExit(f"could not open or create project '{name}'")
    project.SetSetting("timelineResolutionWidth", str(meta["width"]))
    project.SetSetting("timelineResolutionHeight", str(meta["height"]))
    project.SetSetting("timelineFrameRate", str(meta["fps"]))
    project.SetSetting("timelinePlaybackFrameRate", str(meta["fps"]))

    mp = project.GetMediaPool()
    folder = mp.AddSubFolder(mp.GetRootFolder(), "Controglobe") or mp.GetRootFolder()
    mp.SetCurrentFolder(folder)
    items = mp.ImportMedia([{"FilePath": str(seq / "frame_%06d.png"), "StartIndex": 1,
                             "EndIndex": int(meta["total_frames"])}])
    if not items:
        raise SystemExit("Resolve did not import the image sequence")
    timeline = mp.CreateTimelineFromClips(os.environ.get("CG_TIMELINE", "Controglobe v1"), items)
    project.SetCurrentTimeline(timeline)

    audio_track = 1
    for env in ("CG_MUSIC", "CG_NARRATION"):
        path = os.environ.get(env)
        if not path:
            continue
        clip = mp.ImportMedia([path])
        if not clip:
            print(f"could not import {path}")
            continue
        if audio_track > timeline.GetTrackCount("audio"):
            timeline.AddTrack("audio", "stereo")
        ok = mp.AppendToTimeline([{"mediaPoolItem": clip[0], "mediaType": 2, "trackIndex": audio_track,
                                   "recordFrame": timeline.GetStartFrame()}])
        print(f"{env}: {'placed on A' + str(audio_track) if ok else 'append failed; drag it in by hand'}")
        audio_track += 1

    colors = {3: "Red", 2: "Yellow", 1: "Green"}
    n = 0
    for s in slots:
        if s["era_start"]:
            n += bool(timeline.AddMarker(s["start_frame"], "Blue", s["era_name"], s["label"], max(1, s["frames"]), ""))
        for e in s["events"]:
            n += bool(timeline.AddMarker(s["start_frame"], colors.get(e["importance"], "Green"),
                                         f"{s['label']}: {e['date']}", e["text"], max(1, s["frames"]), ""))
    print(f"timeline '{timeline.GetName()}': {meta['total_frames']} frames, {n} markers")

    if os.environ.get("CG_RENDER"):
        out = v / "output" / "render"
        out.mkdir(parents=True, exist_ok=True)
        project.SetCurrentRenderFormatAndCodec("mp4", "H264")
        project.SetRenderSettings({"SelectAllFrames": True, "TargetDir": str(out),
                                   "CustomName": os.environ.get("CG_RENDER_NAME", "controglobe_arabia")})
        job = project.AddRenderJob()
        project.StartRendering(job)
        print(f"rendering to {out}")


main()
