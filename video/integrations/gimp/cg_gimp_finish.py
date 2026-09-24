"""GIMP 3 batch finishing for the yearly stills: lay a paper or parchment texture over every
frame in Overlay mode, the hand-made look the pipeline's own vignette and grain stop short of.

Run it on the ~2,500 yearly stills (output/frames), not on the expanded sequence; then build
the sequence from the finished folder:  python build.py sequence --frames output/frames_gimp

Windows (PowerShell), GIMP 3.x installed in the default place:
  $env:CG_IN = "C:\\...\\video\\output\\frames"
  $env:CG_OUT = "C:\\...\\video\\output\\frames_gimp"
  $env:CG_TEXTURE = "C:\\...\\video\\assets\\paper.jpg"   # any large paper/parchment scan
  $env:CG_OPACITY = "28"
  & "C:\\Program Files\\GIMP 3\\bin\\gimp-console-3.0.exe" -i --batch-interpreter=python-fu-eval `
      -b "exec(open(r'C:\\...\\video\\integrations\\gimp\\cg_gimp_finish.py').read())" --quit

macOS / Linux: the same with export CG_IN=... and gimp-console-3.0 (or flatpak run org.gimp.GIMP -i ...).

Interactive work (flags, the thumbnail, a hand-painted hero frame) is better done live, or by
Claude through a GIMP MCP server: see the video README.
"""

import glob
import os

import gi

gi.require_version("Gimp", "3.0")
from gi.repository import Gimp, Gio  # noqa: E402


def _load(path):
    return Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(path))


def _save(image, path):
    target = Gio.File.new_for_path(path)
    try:
        Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, target, None)  # GIMP 3.0 and later
    except TypeError:
        Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, image.get_layers(), target)  # 2.99 builds


def finish(src_dir, out_dir, texture=None, opacity=28.0):
    os.makedirs(out_dir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(src_dir, "*.png")))
    for n, path in enumerate(files, 1):
        dest = os.path.join(out_dir, os.path.basename(path))
        if os.path.exists(dest):
            continue
        image = _load(path)
        if texture:
            layer = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, image, Gio.File.new_for_path(texture))
            image.insert_layer(layer, None, 0)
            layer.scale(image.get_width(), image.get_height(), False)
            layer.set_mode(Gimp.LayerMode.OVERLAY)
            layer.set_opacity(float(opacity))
        image.flatten()
        _save(image, dest)
        image.delete()
        if n % 100 == 0 or n == len(files):
            print(f"cg_gimp_finish: {n}/{len(files)}")


finish(os.environ["CG_IN"], os.environ["CG_OUT"], os.environ.get("CG_TEXTURE") or None,
       float(os.environ.get("CG_OPACITY", "28")))
