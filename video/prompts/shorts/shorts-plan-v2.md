# Shorts plan v2 (revised with your analytics and the new asks)

Replaces nothing in [shorts-plan.md](/mnt/project-files/shorts/shorts-plan.md): that file is the code plan. This one adds what was missing from it. Prompt: [shorts-master-prompt.md](/mnt/project-files/shorts/shorts-master-prompt.md).

## Did v1 account for your analytics? Partly.

v1 had the vertical layout, event-first pacing and a CTA card. It did not use your numbers. v2 changes:

| Your data | Change |
|---|---|
| 44% left by 0:30; 34% in the Texas video | Every Short opens on its payoff in the first 2 s: no logo, no premise card, no quiet era. The long videos can borrow this: a 5 s teaser of 1945 or 2026 before "Before the divergence". |
| Retention flat after ~3 min (the audience that stays loves the canon) | Shorts target that audience too: canon detail (Arabic, transliteration, names) on the lower third, not generic history. |
| Static periods feel frozen | Camera drift on every slot, a sound cue on every border change, something moving every 1-2 s. |
| Traffic from X and Discord, 81.6% browse | Post each Short to YouTube Shorts, TikTok and Reels, and to X and Discord the same day; the CTA is the Discord invite. |
| Texas CTR 20.5% (thumbnail works) | Countryballs and the strategy-game look carry to the Shorts' first frame. |

Honest caveat: Shorts reach is very noisy, and the share who click through to a 13-minute video is usually small. They are a funnel for the Discord and the channel's recommendations, not a guaranteed way to lift the long videos' watch time. Judge them by subscribers per Short and Discord joins, over 3 weeks.

## New: war-simulation Shorts with army numbers

- New data: `data/armies.csv` (war, year, side, unit, strength, source). The numbers are mostly invented, so each row is `inferred` until you approve it, in line with the house rules.
- New: `cgvideo/warhud.py`: a HUD skin per era (see table in the master prompt), drawn over `war_layer` in `motion.py`, which already grows arrows along `wars.csv` paths and pulses battles. It adds banners with live strength numbers, a battle popup and a result bar.
- Antiquity, medieval, renaissance, Victorian, world wars, cold war and modern each get an original skin *in the spirit of* the corresponding game genre. I will not reproduce any game's art, icons, fonts or music.
- Wars already in `wars.csv` (42) give the paths. Best first: the Civil War 1861-65, the Masri war, the Siberian War, the Derg Union confrontation.

## New: the reference video

`youtu.be/-B957W7H2v0` is "Equestria at War - BountyMaps (Part 1)". I couldn't watch it: this session can't open YouTube, and I haven't looked at its frames. The war-sim HUD above is built from your description, not from the video's content. To match it, give me a list of what you like in it, or let me grab frames from your PC (Windows-MCP is connected there) and I will list them as keyframes.

## New: Caliphates at full extent

The mesh and plates cover lon 20 to 68, lat 5.5 to 44.5. The real caliphate at its height ran from Iberia (about -9 lon) to Sindh and Transoxiana (about 75 lon), north to the Pyrenees (about 43-46 lat). To avoid cutting it off:

1. Extend `mesh.bbox` to about `[-12, 5.5, 80, 48]` (a bigger mesh; it adds QGIS time and many more cells).
2. Add camera keys in era 3 (610-1257) that pull back to zoom ~0.55 so the whole realm fits.
3. Check `PlateSpec` limits (`max_plate_megapixels` 40) and bump `PLATE_VERSION`, since every plate redraws.
4. Check canon first: confirm in the pages what the alternate caliphate controls.

This touches the long cut too, so it needs your OK before I change `config/project.yaml`.

## New: countryballs, globe, music

- Countryballs: reuse `thumbnail.countryball()`; add `data/countryballs.csv` (personality, lines in English and Arabic) and a speech-bubble drawer. They talk on the bottom third, one line at a time.
- Globe: `globe.py` for the 3D globe; if Blender is connected, a rendered globe move is better. 
- Music: a major-key "heroic" band added to `audio.py`'s `BANDS`; the eerie bands stay off for Shorts.

## What I could and could not do this turn

- Done: this plan, the master prompt, and a read of the pipeline.
- Not done: a rendered Short. The renders need QGIS, Natural Earth data and a render machine, none of which this cloud session has, and no folder on your PC is connected yet. Your PC does have Blender and Windows-MCP connected; I see no QGIS, GIMP or Resolve MCP there, and I have not installed anything.
- Unverified: HyperFrames, which I haven't called yet, and everything about the reference video.

## Suggested next steps

1. You approve the Short list and the caliphate extension.
2. I run the layout change and Short 1 frames in a Remote Control session on your PC (it has your checkout and QGIS), then Short 2 with the war HUD.
