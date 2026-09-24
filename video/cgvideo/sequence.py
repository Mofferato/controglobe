"""Turn one still per year into something an editor can use.

sequence  a numbered image sequence at the project frame rate, made of hard links to the
          yearly stills (no extra disk space), which Resolve imports as a single clip
animatic  an H.264 preview straight from the stills with ffmpeg, optionally with music
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

from .config import paths
from .render import frame_name


def expand(cfg: dict, slots: list[dict], frames_dir: str | None = None) -> pathlib.Path:
    P = paths(cfg)
    stills = pathlib.Path(frames_dir) if frames_dir else P.frames
    out = P.sequence
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    n = 0
    linked = True
    for s in slots:
        src = stills / frame_name(s)
        if not src.exists():
            raise SystemExit(f"missing {src.name}: run `python build.py render` first")
        for _ in range(s["frames"]):
            n += 1
            dst = out / f"frame_{n:06d}.png"
            if linked:
                try:
                    os.link(src, dst)
                    continue
                except OSError:
                    linked = False
            shutil.copyfile(src, dst)
    print(f"  {n} frames in {out} ({'hard links' if linked else 'copies'})")
    return out


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # pip install imageio-ffmpeg ships a static ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise SystemExit("ffmpeg not found: `pip install imageio-ffmpeg`, or on Windows "
                         "`winget install Gyan.FFmpeg`, then retry") from None


def animatic(cfg: dict, slots: list[dict], audio: str | None = None, frames_dir: str | None = None) -> pathlib.Path:
    ffmpeg = find_ffmpeg()
    P = paths(cfg)
    stills = pathlib.Path(frames_dir) if frames_dir else P.frames
    fps = int(cfg["frame"]["fps"])
    listing = P.output / "animatic_concat.txt"
    with open(listing, "w", encoding="utf8") as fh:
        for s in slots:
            src = (stills / frame_name(s)).resolve().as_posix()
            fh.write(f"file '{src}'\nduration {s['frames'] / fps:.6f}\n")
        fh.write(f"file '{(stills / frame_name(slots[-1])).resolve().as_posix()}'\n")
    dest = P.output / "animatic.mp4"
    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listing)]
    if audio:
        cmd += ["-i", audio]
    cmd += ["-vf", f"fps={fps},format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "18"]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd.append(str(dest))
    print("  " + " ".join(cmd))
    subprocess.run(cmd, check=True)
    return dest
