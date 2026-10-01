# Alternate History of Texas (in place of Saudi Arabia)

**The Kingdom of Solms-America, in eight phases.** The Controglobe series' special rendition for
North America: each phase is a war-map video of its own, 12 to 16 minutes, in the look of the
strategy game that owns its era, with the wars simulated on a 2.5D map with true relief, the
armies' numbers on the map, countryballs with dialogue, the visual identity of the land, every name
in four languages and scripts, an uplifting score, and the Discord.

- **The plan:** [`prompts/PHASES.md`](prompts/PHASES.md), the eight phases expanded, the grammar
  every phase shares, and the production steps with ready prompts.
- **The master prompt:** [`prompts/MASTER_PROMPT.md`](prompts/MASTER_PROMPT.md), to paste into a
  new session.
- **Phase I** (500 BCE - 603, *Marble & Bronze*): [`phase1/`](phase1/): `canon.md` (what the pages
  say and what this phase proposes, for your ruling), `script.yaml` (the cut scene by scene, the
  wars), `cast.yaml` (the countryballs), `polities.yaml` (the map, on provinces cut by GRASS).

## How a phase is made

```
python solms.py ground 1      # QGIS: relief, land cover, provinces, basins; GIMP: the plate's grade
python solms.py cast 1        # countryballs, banners, the syllabary, city vignettes, a cast sheet
python solms.py compose 1     # the HyperFrames composition, build/solms/phase1/hf/index.html
python solms.py stills 1 205 440    # stills at chosen seconds (Chrome, the GPU): look at them
python solms.py blender 1     # the 3D globe dive and pull-out (Blender, EEVEE, the GPU), and globe_scene.blend to open
python solms.py score 1       # the uplifting score and the effects (about -15 LUFS)
python solms.py render 1 --from 190 --to 230   # a slice, to check; without --from/--to, the whole phase
python solms.py render 1      # the phase (HyperFrames, Chrome on the GPU), about 2.5 times real time
python solms.py resolve 1     # the Resolve build, in Workspace > Scripts > cg_solms_phase1
python solms.py thumbnail 1   # the thumbnail, finished in GIMP
python solms.py publish 1     # titles, description with chapters, tags, pinned comment
```

Everything generated goes to `build/solms/` (never committed); the third-party libraries and fonts
(three.js, GSAP, Cinzel, Cormorant Garamond, Amiri) are fetched into `cache/solms/` by `compose`.

## The machinery (`cgsolms/`)

| Module | Job |
|---|---|
| `frame.py` | The phase's frame (Lambert equal-area on the southern plains), its grids, the river outlets |
| `qgis_ground.py` | Runs in the open QGIS: ETOPO 2022 at 15 arc-seconds mosaicked and projected, shaded; Natural Earth II's land cover projected; GRASS `r.watershed` half-basins (the provinces) and `r.water.outlet` basins |
| `ground.py` | The colour plate in the skin's palette (land cover by hue, relief, sea by depth, natural lakes and rivers only), graded in the open GIMP; the terrain heights |
| `areas.py` | Areas from whole provinces by basin, window and height, so every frontier is a crest or a river |
| `balls.py`, `cast.py` | Countryballs in seven moods with accessories; banners; the cast sheet |
| `glyphs.py` | The Turquoise syllabary (the setting's own script) |
| `vignettes.py` | Illustrated cards of each people's architecture and life |
| `compose.py` | Script, cast and map to the engine's data; the composition page |
| `engine/engine.js` | Every frame as a pure function of time: three.js terrain with the plate draped, map states crossfaded, names, places, the Road, armies, arrows, battles, sieges, numbers, the cast, cards, the date, the infobox |
| `engine/skin_marble.css` | Phase I's look: marble and bronze, Cinzel, shield-shaped army plaques |
| `blender.py` | The globe texture (QGIS shading) and the Blender script for the 3D shots |
| `score.py` | The score and effects, on the composition's own cues |
| `render.py` | Stills (Playwright) and renders (HyperFrames), whole or a slice |
| `resolve.py`, `thumbnail.py`, `publish.py` | The edit, the thumbnail, the upload kit |

## Notes

- The applications are driven where they can be seen: QGIS and GIMP through their MCP plug-ins'
  sockets (start both servers first); Blender headless from its own command line, which also saves
  the dive as `build/solms/globe/globe_scene.blend` (Earth, clouds, atmosphere, sun and the camera's
  keyed flight) to open and adjust by hand. The Blender MCP add-on and server default to port 9876,
  which the QGIS plug-in holds: give one of them another port to have both live. DaVinci Resolve
  through a Lua menu script, the only scripting the free edition allows from 21.1 on.
- HyperFrames needs FFmpeg and FFprobe; `render.py` puts `C:\Users\PC\tools\ffmpeg-master-latest-win64-gpl\bin`
  on the path (`FFMPEG_DIRS`). Change it if FFmpeg lives elsewhere.
- Nothing from any game, film or other video is reused: the skins are our own drawing of the
  conventions a strategy-game player reads at a glance. The reference studied for the war-map
  grammar (keyframes, chapters, pacing) stays in `reference/`, which is never committed.
