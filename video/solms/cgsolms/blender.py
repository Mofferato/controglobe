"""The 3D globe: the cold open's dive from space onto Texas and the end card's pull-out, rendered
by Blender on the GPU (EEVEE), in the background, from a script this module writes.

    python solms.py blender 1

1. The Earth's colour: the whole globe drawn the way the phase's plate is (Natural Earth II's land
   cover in the skin's painted palette, ETOPO 2022 shaded by QGIS, the sea tinted by its depth),
   with the Kingdom of Solms-America's ground glowing teal; and a height map for the relief.
2. Blender (blender -b -P) builds the scene: the Earth with the relief as bump, a cloud shell, an
   atmosphere that glows at the limb, a sun rising over the Gulf, stars; and flies the camera.
3. FFmpeg encodes the frames into the composition's assets/clips/.
"""

from __future__ import annotations

import json
import os
import subprocess
import textwrap

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import frame as F

Image.MAX_IMAGE_PIXELS = None
BLENDER = r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"
GW, GH = 8192, 4096


def _qgis_shade(out):
    """ETOPO 2022 resampled to the globe's grid and shaded, in the open QGIS (headless otherwise)."""
    from cgvideo.terrain import _qgis
    dem = out / "globe_dem.tif"
    shade = out / "globe_shade.tif"
    if not dem.exists():
        _qgis("gdal:warpreproject", {"INPUT": str(F.VIDEO / "cache" / "etopo" / "ETOPO_2022_v1_60s_N90W180_surface.tif"),
                                     "SOURCE_CRS": "EPSG:4326", "TARGET_CRS": "EPSG:4326", "RESAMPLING": 5, "DATA_TYPE": 6,
                                     "EXTRA": f"-te -180 -90 180 90 -ts {GW} {GH}", "OUTPUT": str(dem)}, "globe")
    if not shade.exists():
        _qgis("gdal:hillshade", {"INPUT": str(dem), "BAND": 1, "Z_FACTOR": 3.0, "SCALE": 111120.0, "AZIMUTH": 315.0,
                                 "ALTITUDE": 40.0, "COMPUTE_EDGES": True, "ZEVENBERGEN": False, "COMBINED": False,
                                 "MULTIDIRECTIONAL": True, "OUTPUT": str(shade)}, "globe")
    return dem, shade


def globe_texture(n: int, log=print):
    out = F.BUILD / "globe"
    out.mkdir(parents=True, exist_ok=True)
    tex, bump = out / "earth_marble.jpg", out / "earth_height.png"
    if tex.exists() and bump.exists():
        return tex, bump
    from . import ground as gr
    dem, shade = _qgis_shade(out)
    elev = np.asarray(Image.open(dem), np.float32)
    sh = np.asarray(Image.open(shade), np.float32)
    cover = np.asarray(Image.open(F.VIDEO / "cache" / "naturalearth" / "NE2LC" / "NE2_HR_LC.tif").convert("RGB")
                       .resize((GW, GH), Image.LANCZOS), np.float32)
    S = gr.SKINS["marble"]
    # the land: the plate's palette by hue, lit by the relief; the sea by depth
    import geopandas as gpd
    import shapely
    ne = F.VIDEO / "cache" / "naturalearth"
    land = gpd.read_file(f"/vsizip/{(ne / 'ne_10m_land.zip').as_posix()}")
    tf = lambda g: shapely.transform(g, lambda c: np.column_stack(((c[:, 0] + 180) / 360 * GW, (90 - c[:, 1]) / 180 * GH)))
    lm = gr._mask([tf(g) for g in land.geometry], GW, GH, k=1)
    grey = cover.mean(-1, keepdims=True)
    own = (grey + (cover - grey) * S["saturation"]) * np.array(S["warm"], np.float32)
    hue = gr._hue(cover)
    bst = np.array([h for h, _ in S["biomes"]], np.float32)
    bcol = np.array([gr._hex(c) for _, c in S["biomes"]])
    painted = np.stack([np.interp(hue, bst, bcol[:, i]) for i in range(3)], -1) * (0.9 + 0.35 * (grey / 255.0 - 0.85))
    rgb = painted * (1 - S["keep"]) + own * S["keep"]
    # polar ice stays white
    ice = ((grey[..., 0] > 225) & (np.abs(np.linspace(90, -90, GH))[:, None] > 58))[..., None]
    rgb = np.where(ice, np.array([236, 240, 242], np.float32), rgb)
    flat = float(np.median(sh[lm > 0.5]))
    lit = np.clip((sh - flat) / max(255 - flat, 1), 0, 1)[..., None]
    dark = np.clip((flat - sh) / max(flat, 1), 0, 1)[..., None]
    rgb = rgb * (1 - 0.6 * dark) + (255 - rgb) * 0.2 * lit
    stops = np.array([d for d, _ in S["sea"]], np.float32)
    cols = np.array([gr._hex(c) for _, c in S["sea"]])
    sea = np.stack([np.interp(np.clip(-elev, 0, None), stops, cols[:, i]) for i in range(3)], -1)
    a = lm[..., None]
    rgb = rgb * a + sea * (1 - a)
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    # Solms-America's ground, glowing teal
    try:
        import sys
        sys.path.insert(0, str(F.VIDEO))
        from cgvideo import frontiers as fr
        land_ll = shapely.make_valid(shapely.union_all(list(land.cx[-130:-60, 10:60].geometry)))
        held, _, rows, _ = fr.held_nations("north-america", land_ll, F.VIDEO / "data" / "atlas")
        g = tf(held["solms"])
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        for p in shapely.get_parts(g):
            ring = list(p.exterior.coords)
            d.polygon(ring, fill=(42, 157, 143, 90))
            d.line(ring + [ring[0]], fill=(150, 255, 235, 255), width=5)
        glow = ov.filter(ImageFilter.GaussianBlur(6))
        img = Image.alpha_composite(Image.alpha_composite(img.convert("RGBA"), glow), ov).convert("RGB")
    except Exception as e:                       # the atlas has not been traced on this machine
        log(f"  globe: Solms-America not drawn ({e})")
    img.save(tex, quality=92)
    h = np.clip((elev + 11000) / 20000 * 65535, 0, 65535).astype(np.uint16)
    Image.fromarray(h).save(bump)
    log(f"  globe texture {GW}x{GH} and height map")
    return tex, bump


BPY = r'''
import bpy, math, sys, json
from mathutils import Vector
args = json.loads(sys.argv[sys.argv.index("--") + 1])
scn = bpy.context.scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
try:
    scn.render.engine = "BLENDER_EEVEE_NEXT"
except Exception:
    scn.render.engine = "BLENDER_EEVEE"
scn.render.resolution_x, scn.render.resolution_y = args["w"], args["h"]
scn.render.fps = args["fps"]
scn.frame_start, scn.frame_end = 1, args["frames"]
scn.render.image_settings.file_format = "PNG"
scn.render.filepath = args["out"] + "/f_"
try:
    scn.eevee.taa_render_samples = 32
except Exception:
    pass
scn.view_settings.view_transform = "Standard"
scn.view_settings.look = "None"
scn.view_settings.exposure = 0.15

def mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    return m, m.node_tree.nodes, m.node_tree.links

R = 1.0
# the Earth
bpy.ops.mesh.primitive_uv_sphere_add(segments=256, ring_count=128, radius=R)
earth = bpy.context.object
bpy.ops.object.shade_smooth()
m, N, L = mat("earth")
for n in list(N):
    N.remove(n)
out = N.new("ShaderNodeOutputMaterial")
bsdf = N.new("ShaderNodeBsdfPrincipled")
tex = N.new("ShaderNodeTexImage"); tex.image = bpy.data.images.load(args["tex"]); tex.interpolation = "Cubic"
hgt = N.new("ShaderNodeTexImage"); hgt.image = bpy.data.images.load(args["bump"]); hgt.image.colorspace_settings.name = "Non-Color"
bump = N.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.35; bump.inputs["Distance"].default_value = 0.02
coord = N.new("ShaderNodeTexCoord")
sep = N.new("ShaderNodeSeparateXYZ"); L.new(coord.outputs["Object"], sep.inputs["Vector"])
lon = N.new("ShaderNodeMath"); lon.operation = "ARCTAN2"; L.new(sep.outputs["Y"], lon.inputs[0]); L.new(sep.outputs["X"], lon.inputs[1])
lat = N.new("ShaderNodeMath"); lat.operation = "ARCSINE"; lat.use_clamp = False; L.new(sep.outputs["Z"], lat.inputs[0])
u = N.new("ShaderNodeMath"); u.operation = "MULTIPLY_ADD"; u.inputs[1].default_value = 1 / (2 * math.pi); u.inputs[2].default_value = 0.5
L.new(lon.outputs["Value"], u.inputs[0])
v = N.new("ShaderNodeMath"); v.operation = "MULTIPLY_ADD"; v.inputs[1].default_value = 1 / math.pi; v.inputs[2].default_value = 0.5
L.new(lat.outputs["Value"], v.inputs[0])
uv = N.new("ShaderNodeCombineXYZ"); L.new(u.outputs["Value"], uv.inputs["X"]); L.new(v.outputs["Value"], uv.inputs["Y"])
L.new(uv.outputs["Vector"], tex.inputs["Vector"]); L.new(uv.outputs["Vector"], hgt.inputs["Vector"])
L.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
L.new(hgt.outputs["Color"], bump.inputs["Height"]); L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
bsdf.inputs["Roughness"].default_value = 0.78
try:
    bsdf.inputs["Specular IOR Level"].default_value = 0.25
except Exception:
    pass
L.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
earth.data.materials.append(m)

# clouds: a thin shell of noise
bpy.ops.mesh.primitive_uv_sphere_add(segments=128, ring_count=64, radius=R * 1.006)
cl = bpy.context.object; bpy.ops.object.shade_smooth()
m, N, L = mat("clouds")
for n in list(N):
    N.remove(n)
out = N.new("ShaderNodeOutputMaterial"); mix = N.new("ShaderNodeMixShader"); tr = N.new("ShaderNodeBsdfTransparent")
dif = N.new("ShaderNodeBsdfDiffuse"); dif.inputs["Color"].default_value = (1, 1, 1, 1)
noise = N.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value = 6.0; noise.inputs["Detail"].default_value = 12.0
noise.inputs["Roughness"].default_value = 0.62
ramp = N.new("ShaderNodeValToRGB"); ramp.color_ramp.elements[0].position = 0.56; ramp.color_ramp.elements[1].position = 0.74
L.new(noise.outputs["Fac"], ramp.inputs["Fac"]); L.new(ramp.outputs["Color"], mix.inputs["Fac"])
L.new(tr.outputs["BSDF"], mix.inputs[1]); L.new(dif.outputs["BSDF"], mix.inputs[2]); L.new(mix.outputs["Shader"], out.inputs["Surface"])
for k, v in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
    try:
        setattr(m, k, v)
    except Exception:
        pass
cl.data.materials.append(m)

# the atmosphere: a shell that glows toward the limb
bpy.ops.mesh.primitive_uv_sphere_add(segments=128, ring_count=64, radius=R * 1.022)
at = bpy.context.object; bpy.ops.object.shade_smooth()
m, N, L = mat("atmosphere")
for n in list(N):
    N.remove(n)
out = N.new("ShaderNodeOutputMaterial"); add = N.new("ShaderNodeAddShader"); tr = N.new("ShaderNodeBsdfTransparent")
em = N.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (0.22, 0.52, 1.0, 1)
lw = N.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.3
pw = N.new("ShaderNodeMath"); pw.operation = "POWER"; pw.inputs[1].default_value = 3.2
L.new(lw.outputs["Facing"], pw.inputs[0]); L.new(pw.outputs["Value"], em.inputs["Strength"])
L.new(tr.outputs["BSDF"], add.inputs[0]); L.new(em.outputs["Emission"], add.inputs[1]); L.new(add.outputs["Shader"], out.inputs["Surface"])
for k, v in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
    try:
        setattr(m, k, v)
    except Exception:
        pass
at.data.materials.append(m)

# the world: black space and stars
w = bpy.data.worlds.new("space"); scn.world = w; w.use_nodes = True
N, L = w.node_tree.nodes, w.node_tree.links
for n in list(N):
    N.remove(n)
wo = N.new("ShaderNodeOutputWorld"); bg = N.new("ShaderNodeBackground")
vn = N.new("ShaderNodeTexVoronoi"); vn.inputs["Scale"].default_value = 420.0
rp = N.new("ShaderNodeValToRGB"); rp.color_ramp.elements[0].position = 0.0; rp.color_ramp.elements[0].color = (1, 1, 1, 1)
rp.color_ramp.elements[1].position = 0.035; rp.color_ramp.elements[1].color = (0, 0, 0, 1)
L.new(vn.outputs["Distance"], rp.inputs["Fac"]); L.new(rp.outputs["Color"], bg.inputs["Color"])
bg.inputs["Strength"].default_value = 0.9
L.new(bg.outputs["Background"], wo.inputs["Surface"])

# the sun, rising over the Gulf
bpy.ops.object.light_add(type="SUN")
sun = bpy.context.object; sun.data.energy = 5.0; sun.data.angle = 0.02
def ll2v(lon, lat, r=1.0):
    lo, la = math.radians(lon), math.radians(lat)
    return Vector((r * math.cos(la) * math.cos(lo), r * math.cos(la) * math.sin(lo), r * math.sin(la)))
sd = ll2v(args["sun"][0], args["sun"][1])
sun.rotation_euler = (-sd).to_track_quat("-Z", "Y").to_euler()


# the camera's flight: keys of lon, lat, distance (in Earth radii from the centre), roll toward north
bpy.ops.object.camera_add()
cam = bpy.context.object; scn.camera = cam
cam.data.lens = args["lens"]; cam.data.clip_start = 0.001; cam.data.clip_end = 100
keys = args["keys"]
def ease(t):
    return t * t * (3 - 2 * t)
for f in range(1, args["frames"] + 1):
    t = (f - 1) / max(1, args["frames"] - 1) * keys[-1][0]
    i = max(j for j in range(len(keys)) if keys[j][0] <= t) if t < keys[-1][0] else len(keys) - 2
    a, b = keys[i], keys[min(i + 1, len(keys) - 1)]
    u = 0 if b[0] == a[0] else ease((t - a[0]) / (b[0] - a[0]))
    lon = a[1] + (b[1] - a[1]) * u; lat = a[2] + (b[2] - a[2]) * u
    dist = math.exp(math.log(a[3]) + (math.log(b[3]) - math.log(a[3])) * u)
    tilt = a[4] + (b[4] - a[4]) * u
    target = ll2v(lon, lat, R)
    up = Vector((0, 0, 1))
    north = (up - target.normalized() * up.dot(target.normalized())).normalized()
    pos = target.normalized() * dist - north * math.tan(math.radians(tilt)) * (dist - R)
    cam.location = pos
    q = (target - pos).to_track_quat("-Z", "Y")
    cam.rotation_euler = q.to_euler()
    # keep north up: align the camera's up with the meridian
    cam.keyframe_insert("location", frame=f); cam.keyframe_insert("rotation_euler", frame=f)
    cl.rotation_euler[2] = f * 0.00025
    cl.keyframe_insert("rotation_euler", frame=f)
if args.get("save"):
    bpy.ops.wm.save_as_mainfile(filepath=args["save"])
else:
    bpy.ops.render.render(animation=True)
'''


def render_clip(name, tex, bump, keys, seconds, sun, fps=30, w=1920, h=1080, lens=50, log=print):
    out = F.BUILD / "globe" / name
    out.mkdir(parents=True, exist_ok=True)
    frames = int(round(seconds * fps))
    done = sorted(out.glob("f_*.png"))
    if len(done) < frames:
        script = F.BUILD / "globe" / "cg_globe.py"
        script.write_text(BPY, encoding="utf8")
        args = {"w": w, "h": h, "fps": fps, "frames": frames, "out": str(out).replace("\\", "/"), "tex": str(tex),
                "bump": str(bump), "keys": keys, "sun": sun, "lens": lens}
        log(f"  Blender: {name}, {frames} frames at {w}x{h}")
        p = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", str(script), "--", json.dumps(args)],
                           capture_output=True, text=True)
        tail = "\n".join((p.stdout + p.stderr).splitlines()[-12:])
        if p.returncode != 0 or len(sorted(out.glob("f_*.png"))) < frames:
            raise RuntimeError(f"Blender failed for {name}:\n{tail}")
    from .render import FFMPEG_DIRS
    ff = os.path.join(FFMPEG_DIRS[0], "ffmpeg.exe")
    dst = F.build_dir(1) / "hf" / "assets" / "clips" / f"{name}.mp4"
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(out / "f_%04d.png"), "-c:v", "libx264",
                    "-preset", "slow", "-crf", "15", "-pix_fmt", "yuv420p", str(dst)], check=True)
    log(f"  {dst}")
    return dst


def save_scene(tex, bump, log=print):
    """The dive as a .blend file, to open in Blender and adjust by hand (build/solms/globe/globe_scene.blend)."""
    out = F.BUILD / "globe" / "globe_scene.blend"
    script = F.BUILD / "globe" / "cg_globe.py"
    script.write_text(BPY, encoding="utf8")
    args = {"w": 1920, "h": 1080, "fps": 30, "frames": 405, "out": str(F.BUILD / "globe" / "globe_open").replace("\\", "/"),
            "tex": str(tex), "bump": str(bump), "lens": 50, "sun": [-20, 14], "save": str(out),
            "keys": [[0, -58, 16, 7.2, 0], [6, -82, 25, 4.0, 0], [11, -100, 30.5, 2.15, 0], [13.5, -102, 31.0, 1.74, 0]]}
    subprocess.run([BLENDER, "-b", "--factory-startup", "-P", str(script), "--", json.dumps(args)], capture_output=True, text=True)
    log(f"  {out}" if out.exists() else "  the .blend was not saved")
    return out


def build(n: int, log=print):
    tex, bump = globe_texture(n, log)
    # the dive: the Americas from space at dawn, turning to the kingdom's ground and dropping onto it
    render_clip("globe_open", tex, bump, keys=[[0, -58, 16, 7.2, 0], [6, -82, 25, 4.0, 0], [11, -100, 30.5, 2.15, 0],
                                              [13.5, -102, 31.0, 1.74, 0]], seconds=13.5, sun=[-20, 14], log=log)
    # the pull-out under the end card
    render_clip("globe_out", tex, bump, keys=[[0, -101.5, 30.5, 1.74, 0], [4, -96, 28, 3.2, 0], [8.5, -84, 22, 6.6, 0]],
                seconds=8.5, sun=[-30, 14], log=log)
    save_scene(tex, bump, log)
