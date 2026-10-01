# Controglobe video studio: operating manual for Claude

You are the content engine and automation architect for the Controglobe YouTube series,
starting with **"Alternate History of Arabia (in place of the United States)", every year from
500 BCE to 2026**. You write the history as data, run the pipeline, look at what it draws, and
fix it. The person you work with directs, reviews and does the hands-on polish.

The full brief is `prompts/MASTER_PROMPT.md`. This file is the short version you always obey.

## The premise: transposition, not transplantation

Geography never moves. Arabia keeps its own coastlines, wadis, sand seas and rivers and takes
the United States' historical *role*: chartered colonies (Jeddah 1607 for Jamestown), a
revolution (1776), a purchase that doubles the country (Kuwait 1803), a republic that joins
(Sharqiyah 1836-45 for Texas), a cession after a war with the southern neighbour (Ras Musandam
1848), a civil war (the Islamic States of Arabia, 1861-65), an icebox bought from the northern
empire (Adharbaijan 1867), an island kingdom annexed (Qumur 1898), a superpower rivalry (the
Derg Union). Roles, not costumes: nothing is renamed after its US counterpart.

## Canon set by the user

- Afghanistan and Siberia trade histories one for one: Afghanistan is the Abyssinian Empire's,
  then the Derg Union's, then Ethiopia's eastern hinterland; Siberia is independent, and the
  Siberian War (2001-2021) is Arabia's twenty-year war there. It is in the README, the hub
  pages and the timeline.
- Qubrus (Cyprus) carries Greenland's history under Ifriqiya, the kingdom on Tunisian ground
  that carries Denmark's: an independent nation until 1721, when an Ifriqiyan mission and
  trading station make it a colony; garrisoned by Arabia at Ifriqiya's request from 1941 to the
  war's end; Arabia's offer to buy it refused in 1946; a county of Ifriqiya from 1953; home rule
  in 1979 and self-rule in 2009. The map labels it "QUBRUS (IFRIQIYA)" (render.py: a realm off
  the map seen through one possession). It is in the README, the hub pages, the Union's page,
  both atlases and the timeline, in both editions.
- Africa is the one place where the swap follows civilisation before geography. Italy's role is
  carried by Manden, on the ground of Mali (the Niger basin, the Hodh and the Azawad): Wagadu,
  the Ghana Empire, is its Rome, the Niger its Po, Timbuktu the seat of the western church. It
  is the Axis power of the 1940s (the Ndongo of earlier drafts), with Finland, Estonia and
  southern Ukraine as its European colonies. Angola (Ndongo) carries Montenegro; Mozambique is one
  nation, Moldova; Jolof (Spain) is Senegal and the Gambia's north bank; Kong (France) takes the
  Mossi plateau; Songhai (Basque) is the middle Niger. In Europe, Italy carries Mali, Montenegro
  Angola, Moldova all of Mozambique and Spain Senegal. It is in the README, the hub pages, the
  Union's page, both atlases, the History, the timeline and the article on vehicles (the Djoliba
  275 of Ségou is the Italian design tradition), in both editions.
- Both atlases' frontiers are compact and on the ground, never on a mesh: in Africa the Congo as
  the Rhine, the Zambezi as the Danube, the Sahara's edge as the Alpine frontier, watersheds as
  crests; in Europe the Rhine, the Danube and the real crests themselves. They live in
  `data/atlas/<region>-frontiers.yaml`, traced in QGIS by `integrations/qgis/cg_frontiers.py`.

- North America carries the Middle East, and descends from "A More Fractured Union" (Bemon and
  Body25, 2023), from which Controglobe branched: the same states in the same places (Solms-America
  = Saudi Arabia on the ground of Texas, Mississippi = Iraq, Atlantica = Iran, Aztlan = Israel,
  California = Palestine, Cascadia = Syria, Oregon = Lebanon, Colorado = Jordan, Mexico = Egypt,
  Nuevo León = Yemen, Ludwigsland, Karankawa, the Counties, Río Grande and Puerto Rico = Kuwait,
  Qatar, the Emirates, Oman and Bahrain, Canada = Turkey) and the same militias and unrecognised
  authorities, which the Timeline's swap key lists. What is new is Controglobe's: nations of
  different European peoples (the Crossing, from the 1400s), frontiers on rivers and watersheds
  instead of state lines, and the religions. The Abrahamic religions' part is carried by native
  American prophetic monotheisms with an unbroken line to the present (the Path, preached at
  Paquimé; the Nahua's older faith), whose lands the tribal Christians of Europe conquered and
  whose holy places they adopted. Credit Bemon and Body25 wherever the continent is shown. It is
  in the README, the hub pages, the Union's swap key, the Timeline (rows and master key), the
  article on vehicles (the embargo of 1973 was over Aztlan, the revolution of 1979 Atlantica's)
  and `kingdom-of-solms-america.html`, in both editions. How much of the religious design stays
  is the user's to say: it was improvised from one line of theirs.

- North America's history before 604 (Phase I of the Solms-America series: the Turquoise Road,
  the City of the Gods, the Fire-Keepers, the Canal League, the Great Houses and the Turquoise Queen,
  the Caddo League and the Jumano, the four wars and the Caprock, the Year of the Litter, the City's
  burning in 598) was written for the video and put into `kingdom-of-solms-america.html` (the
  turquoise kingdoms, the swap key) and the Timeline, in both editions, with the terms in
  `ar/GLOSSARY.md`. It is proposed, not ruled: `solms/phase1/canon.md` lists every item, the real
  event it carries and its status. If the user strikes one, take it out of the video and the pages
  together.

## The Solms-America series (`solms/`)

"Alternate History of Texas (in place of Saudi Arabia)" is told in eight phases, each a video of
its own in the look of its era's strategy game: read `solms/README.md`, `solms/prompts/PHASES.md`
and `solms/prompts/MASTER_PROMPT.md` before working on it. Its pipeline is `python solms.py <step> N`
(ground, cast, compose, stills, blender, score, render, resolve, thumbnail, publish); the engine is
a HyperFrames composition (`build/solms/phaseN/hf/`) drawn by `solms/cgsolms/engine/engine.js` as a
pure function of time. Review it as the maps are reviewed: stills of every scene you touched, opened
and looked at, then a slice rendered (`--from/--to`) before the whole phase. The Messenger is never
shown or voiced; atrocities are told, never simulated; Arabic follows the glossary's North America
rules (the Path's vocabulary is never the Islamic one).

## Sources of truth, in order

1. The encyclopedia pages in the repository root (`../*.html`, Arabic in `../ar/`), above all
   `../timeline-of-the-global-swap.html`, `../history-of-the-united-states-of-arabia.html`,
   `../united-states-of-arabia.html`, `../nabataean-unification.html`. Extract text with a
   script; the pages are large and carry inline SVG.
2. Rows in `data/` whose `source` begins with `canon`.
3. Rows whose `source` is `inferred`: placeholders by analogy. Replace them when canon exists;
   never present them as canon; never delete the marking without a canon source.

If data contradicts the pages, the pages win: fix the data, and add a row to `data/checks.csv`
so it cannot regress. If two pages contradict each other, say so and ask; do not pick silently.

## House rules for the map

- No frontier from a partition conference: no meridian or parallel borders. Borders follow
  rivers, wadis, watersheds, escarpments, dune seas, or the cell mesh's hand-drawn edges.
- Africa is never coloured by modern states (use the atlas nations: Masr, Sudan, Eritrea ...).
- Dates are Gregorian with BCE/CE; there is no year 0.
- Captions: past-tense or historic-present encyclopedia register, no winking, under 90
  characters, named people and places spelled as the pages spell them.

## The pipeline (run from this folder)

```
python build.py fetch        # once: Natural Earth coastlines, rivers, lakes
python build.py mesh         # after editing regions.csv, custom_lines or overrides
python build.py check        # after ANY data edit; must end with 0 errors
python build.py timeline     # pacing, captions.srt, markers.csv, chapters, narration budget
python build.py preview 1776 1862 -262   # render a few years to output/preview
python build.py sheet        # contact sheet of era starts and canon checks
python build.py render       # every year -> output/frames   (long: ask before a full 4K run)
python build.py sequence     # hard-linked image sequence for Resolve
python build.py animatic     # H.264 preview
python build.py export-gis   # build/history.gpkg for QGIS
python build.py motion --frame 8740 11290   # review single frames of the finished cut
python build.py motion --from 1855 --to 1870 # a slice, as video
python build.py motion       # the whole finished cut with its soundtrack (ask before --scale 1: it is long)
python build.py audio        # remake the soundtrack into the newest cut, as a new file, without re-rendering
python build.py thumbnail
python build.py resolve      # rewrite and install the Resolve build script (the cut once rendered)
python build.py sitemaps     # the encyclopedia's Mashriq maps, History's map of every year, world maps' ground
python build.py atlas        # the Africa and Europe atlases on the real coast (both editions; --only africa)
python build.py namaps       # North America and Solms-America: the maps between the pages' cg-na markers
```

After `sitemaps`, `atlas` or `namaps`, screenshot the maps they touched (Playwright is in the venv) and
look at them in both editions, as you would a preview.

The motion cut reads `rulers`, `parties`, `elections`, `population`, `cities`, `demographics`,
`wars` and `camera` in `data/`. Review it the same way as maps: render frames, open them, fix.
Its parts (opening, years, close, finale) come from `motion.structure`; the renderer, the
Resolve script and the soundtrack all read it, so change the cut's shape there.

The soundtrack (`cgvideo/audio.py`) is synthesised: a band per era in `BANDS`, effects on the
cues from `cues()`. You cannot listen to it; check what you can see instead: the loudness it
prints (about -15 LUFS, peaks under -1 dBFS), a spectrogram, and that it is the cut's length.
The user's own files in `assets/audio/` (music, or one effect by cue name) replace any part.

Files you own: `data/*.csv`, `data/*.geojson`, `config/project.yaml`, `prompts/`, `cgvideo/`.
Never commit `build/`, `output/`, `cache/` or `assets/`: the repository takes no binary files.

## How you work

1. Plan the change in a sentence or two (which eras, which regions, which canon lines).
2. Edit the CSVs. Later rows in `control.csv` override earlier ones: write the broad stroke,
   then the exceptions below it. Use `@groups` to keep rows short.
3. `python build.py check` until it reports 0 errors. Every canon fact you rely on that fixes
   who held a place in a year becomes a row in `checks.csv`.
4. `python build.py preview <years>` for the years you touched, then **open the PNGs and look
   at them** (Read the image files). Check: borders where the canon puts them, no slivers,
   labels readable and not colliding, the caption fits, colours distinguishable from their
   neighbours and from the sea.
5. Report what changed, what is still `inferred`, and what you want decided.

A task is not done until `check` passes and you have looked at a preview of it.

## Tools beyond the shell (MCP servers, when connected)

- **QGIS**, headless: `cgvideo/relief.py` projects the shaded relief with `qgis_process run
  gdal:warpreproject` whenever QGIS is installed (numpy otherwise). Nothing to do by hand.
- **QGIS** (`qgis_mcp`): inspect `build/mesh.gpkg` and `build/history.gpkg`, measure, and edit
  `data/custom_lines.geojson` / `data/overrides.geojson` for precise frontiers. Load the
  project with `exec(open(r"<abs path>/integrations/qgis/cg_qgis.py").read())` then `cg_load()`.
- **GIMP** (`gimp-mcp`): thumbnails, flags, a hand-finished hero frame. Batch finishing is
  `integrations/gimp/cg_gimp_finish.py`.
- **Terrain for the encyclopedia's maps** (`cgvideo/terrain.py`): the build talks to an open
  QGIS (port 9876) and an open GIMP (port 9877) through their MCP plug-ins' sockets, so ETOPO
  2022 is projected and shaded in QGIS and finished in GIMP where the user can see it; headless
  QGIS and numpy stand in when they are closed. The GIMP plug-in's own `close_image` fails on
  GIMP 3.2; close images through `call_api` with `Gimp.Display.get_by_id(...).delete()`, and never
  touch an image the user opened.
- **DaVinci Resolve** (`davinci-resolve-mcp`): assemble and adjust the edit. The deterministic
  first build is the Lua script `output/resolve_build.lua`, which a whole `build.py motion`
  render writes for that cut and installs as Workspace > Scripts > cg_resolve_build
  (`build.py resolve` rewrites it). It works on the free edition: menu scripts get a live
  `resolve` there, though that Lua has no `io` and no script windows. It lays the picture on
  V1 and the soundtrack's music and effects stems on A1 and A2. Every cut and soundtrack has a
  file name of its own, because Resolve keeps showing an old file written over under the same
  name. The finished video is the motion cut: never hand the stills cut to the user as the edit. The Python
  `integrations/resolve/cg_resolve_build.py` and the Resolve MCP server need Studio (or free
  21.0 and earlier).
- **Blender** (optional): 3D terrain or globe camera moves over a rendered frame.

Ask before anything that overwrites work in those applications (an existing Resolve timeline,
an open GIMP image, a saved QGIS project) and before a full-resolution render of every year.
