"""Study a reference video's pacing and layout, on your own machine, for your own notes.

Downloads a video you are allowed to watch (yt-dlp), finds its cuts with ffmpeg's scene
detector, and writes into reference/<id>/ (git-ignored, never published):
  keyframes/      one small frame per cut
  cuts.csv        the time of every cut and the gap before it: the reference's rhythm
  sheet.png       a contact sheet of the keyframes
  report.md       cut count, average shot length, longest holds

Use it to learn rhythm and layout conventions (where the year sits, how long an era card
holds, how often the camera moves); then build our own look. Do not reuse anyone's frames,
art, flags, portraits or music in the Controglobe video.

  pip install yt-dlp
  python integrations/reference/study_reference.py https://www.youtube.com/watch?v=<id> [--threshold 0.3]
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2]))

from cgvideo.sequence import find_ffmpeg  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--threshold", type=float, default=0.3, help="scene-change sensitivity, 0-1")
    args = ap.parse_args()
    vid = re.sub(r"\W", "", args.url.split("v=")[-1])[:20] or "ref"
    out = HERE.parents[2] / "reference" / vid
    (out / "keyframes").mkdir(parents=True, exist_ok=True)
    src = out / "source.mp4"
    if not src.exists():
        subprocess.run([sys.executable, "-m", "yt_dlp", "-f", "bv*[height<=720][ext=mp4]/b[height<=720]",
                        "-o", str(src), args.url], check=True)
    ff = find_ffmpeg()
    proc = subprocess.run([ff, "-i", str(src), "-vf", f"select='gt(scene,{args.threshold})',showinfo,scale=320:-2",
                           "-vsync", "vfr", str(out / "keyframes" / "cut_%04d.jpg")],
                          capture_output=True, text=True)
    times = [float(t) for t in re.findall(r"pts_time:([\d.]+)", proc.stderr)]
    with open(out / "cuts.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["cut", "seconds", "gap"])
        prev = 0.0
        for n, t in enumerate(times, 1):
            w.writerow([n, round(t, 2), round(t - prev, 2)])
            prev = t
    gaps = [b - a for a, b in zip([0.0] + times, times)]
    from PIL import Image
    frames = sorted((out / "keyframes").glob("*.jpg"))[:120]
    if frames:
        im0 = Image.open(frames[0])
        cols = 10
        sheet = Image.new("RGB", (cols * im0.width, -(-len(frames) // cols) * im0.height))
        for k, f in enumerate(frames):
            sheet.paste(Image.open(f), ((k % cols) * im0.width, (k // cols) * im0.height))
        sheet.save(out / "sheet.png")
    longest = sorted(zip(gaps, times), reverse=True)[:10]
    (out / "report.md").write_text(
        f"# Reference study: {args.url}\n\n{len(times)} cuts; average shot {sum(gaps) / max(1, len(gaps)):.2f} s\n\n"
        "Longest holds (seconds, ending at):\n\n" + "".join(f"- {g:.1f} s at {t:.1f} s\n" for g, t in longest),
        encoding="utf8")
    print(f"{len(times)} cuts -> {out}")


if __name__ == "__main__":
    main()
