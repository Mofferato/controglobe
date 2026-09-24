# Phase prompts

Short prompts for each step, to use after the master prompt (`MASTER_PROMPT.md`) has set the
scene. Each one names its inputs, its outputs and when it is done, so a session can pick up
any phase cold. Replace anything in angle brackets.

## 0. Session start (every time)

> Read `video/CLAUDE.md`. Run `python build.py check` and tell me the state in five lines:
> errors, warnings, how many control rows are still inferred, and which phase we are in.

## 1. Canon digest

> Extract the text of every encyclopedia page (English, and `ar/GLOSSARY.md` for spellings).
> Build `docs/canon_digest.md`: a table of every dated statement about who held, founded,
> bought, ceded, annexed, admitted or lost a place, with page and section. Then a list of
> contradictions between pages, and a list of silences the video must fill (eras or regions
> with no holder). Do not edit data yet.

Done when: the digest exists and every row cites a page.

## 2. Regions

> Compare the digest with `data/regions.csv`. List every change the regions cannot express
> (a colony smaller than its region, a frontier on a river that runs through a region). Propose
> splits and new seeds with coordinates and why, apply them, rebuild the mesh, run check, and
> preview <years that show the split regions>. Show me the previews.

Done when: every territorial fact in the digest can be expressed with whole regions.

## 3. Control data, one era at a time

> Era <e5, The age of the crowns, 1497-1762>. Using the digest, rewrite this era's block in
> `data/control.csv`. Canon rows get `canon` and the page; gaps get `inferred` and a one-line
> reason. Add a `checks.csv` row for every canon fact of the form "year, place, holder".
> Run check until it passes, then preview the era's first year, last year and every year a
> border moves, look at each image, and fix what looks wrong. Report the inferred rows.

Done when: check passes, previews reviewed, inferred rows listed.

## 4. Precise frontiers

> The frontier between <Najd> and <Sharqiyah> should follow <the Dahna sands / the Tuwayq
> escarpment>. Add or refine the line in `data/custom_lines.geojson` with coordinates you can
> justify (or draw it in QGIS through the MCP server: load `integrations/qgis/cg_qgis.py`, run
> `cg_load()`, edit "custom_lines (edit me)", save). Rebuild the mesh, check, and show me
> before and after previews of <1850>.

For a frontier placed to the kilometre, draw a polygon in `overrides.geojson` with the
`region_id` that must own the cells inside it.

## 5. Events and places

> From the digest, make sure every dated event is in `data/events.csv` with importance 1-3
> (3 = the viewer must read it: independence, purchases, secession, abolition). Keep captions
> under 90 characters in the timeline article's voice. Add capitals, forts, battles and the
> federal district to `data/places.csv` with the years they should show.

## 6. Pacing

> Set `pacing.target_minutes` to <15>. Run timeline. Show me the chapter list, total length,
> and for each era the seconds per year and the narration budget. Flag any era where a year
> lasts under 3 frames outside antiquity, or any caption that is on screen for less than
> 3 seconds.

## 7. Visual QA pass

> Run `python build.py sheet`, open `output/qa/contact_sheet.png`, then preview any frame that
> looks wrong at full size. Check label collisions, slivers, near-identical neighbour colours,
> labels in the sea, and the inset. Fix the causes (colours in polities.csv, label thresholds
> in config, region splits) rather than the symptoms, and show before and after.

## 8. Narration (optional)

> Write the voice-over as `docs/narration.md`, one section per era with its start timecode
> from `output/youtube_chapters.txt`, within the word budget in
> `output/narration_budget.csv`. Encyclopedia register, present tense, no jokes; name the
> American counterpart at most once per era, and only where the rhyme helps.

## 9. Full render and edit

> Render every year at full resolution with <N> workers (tell me the estimate first), then
> `sequence` and `animatic`. If GIMP finishing is on, give me the exact PowerShell command for
> `integrations/gimp/cg_gimp_finish.py` and build the sequence from `output/frames_gimp`.
> Then build the Resolve project: run `integrations/resolve/cg_resolve_build.py` (or through
> the Resolve MCP server), with music from <path>, and list the manual polish still to do.

## 10. Publishing kit

> Write `docs/publish.md`: five title options (under 70 characters), the description (premise
> in two sentences, what transposition means, chapters from `output/youtube_chapters.txt`,
> sources: the encyclopedia and Natural Earth), 15 tags, a pinned comment, and a thumbnail
> brief (which year's map, what text, what colours) for GIMP.
