"""The upload kit of a phase: title options, the description with its chapters, tags and the pinned
comment, written into build/solms/phaseN/youtube/ ready to paste.

    python solms.py publish 1
"""

from __future__ import annotations

import json

from . import frame as F

REPO = "https://github.com/Mofferato/controglobe"
SITE = "https://mofferato.github.io/controglobe"


def _mmss(t):
    t = int(round(t))
    return f"{t // 60}:{t % 60:02d}"


def build(n: int, log=print):
    hf = F.build_dir(n) / "hf"
    D = json.loads((hf / "data.js").read_text(encoding="utf8")[len("window.DATA = "):].rstrip().rstrip(";"))
    out = F.build_dir(n) / "youtube"
    out.mkdir(parents=True, exist_ok=True)
    titles = [
        "Alternate History of Texas (in place of Saudi Arabia) – Phase I",
        "What if Texas Had Saudi Arabia's History? | Phase I: The Turquoise Road",
        "Texas as Saudi Arabia: 500 BCE – 603 CE, Every War Simulated",
        "The Kingdom of Solms-America, Phase I: The Turquoise Road",
        "Alternate Texas: Four Ancient Wars on the Turquoise Road",
    ]
    chapters = "\n".join(f"{_mmss(s['t0'])} {s['chapter']}" for s in D["scenes"])
    desc = f"""Texas, the southern plains and the far south-west, carrying the history of Saudi Arabia on their own ground. Phase I of the Kingdom of Solms-America: the Turquoise Road, 500 BCE to 603 CE, with every war simulated on the map.

This is transposition, not transplantation: geography never moves. Paquimé is Makkah, Chukson Madinah, Waimas Jeddah, Dreifurt (on the Trinity) Riyadh; the Gulf of California is the Red Sea and the Gulf of Mexico the Gulf. Before the Path, before the Crossing, before the House of Solms, the turquoise kingdoms taxed a road that ran from the Cerrillos hills to the City of the Gods, and the empires of the south and the east fought over it.

Four wars, with their armies and numbers: the Northern Expedition (26–24 BCE), the Turquoise Queen (268–273), the Eastern Expedition (363) and the Year of the Litter (570), and the battle of the Caprock (554).

Every name is shown in English, in American (the German of the Crossing), in its native form where a real one exists (O'odham, Caddo, Nahuatl), in the setting's Turquoise syllabary, and in Arabic.

Chapters
{chapters}

Help us draw Phase II, The Path and the Commonwealth: join the Controglobe Discord, {D['discord']}

Every name, border and date: {SITE}
Code, data and canon (open source, CC BY-SA 4.0): {REPO}

North America's states descend from "A More Fractured Union: USA and Middle East swap" by Bemon (u/kaselev) and Body25 (u/bodycornflower), 2023, from which Controglobe branched. Relief: ETOPO 2022 (NOAA NCEI). Land cover, rivers and lakes: Natural Earth. Frontiers traced on rivers and watersheds in QGIS with GRASS. Score and effects made in code. The game-inspired interface is our own drawing; no game art is used.

This is alternate-history fiction. The religions, polities and wars after 500 BCE are inventions of the setting and describe no living people or faith.
"""
    tags = ["alternate history", "alternate history of texas", "texas", "saudi arabia", "mapping", "map animation",
            "countryballs", "war simulation", "imperator rome", "ancient history", "native american history",
            "paquime", "controglobe", "the global swap", "what if", "history map", "solms-america"]
    pinned = f"""Phase II, The Path and the Commonwealth (604 – 1399), is drawn on the Discord: {D['discord']}

Which war should get the longest simulation next: the Messenger's wars, the Speakers' conquests, or the fall of Cahokia? Reply here or vote on the Discord.

Transposition, not transplantation: Texas keeps its own rivers, plains and deserts and takes Saudi Arabia's role. Every name and date is in the encyclopedia: {SITE}"""
    (out / "titles.txt").write_text("\n".join(titles) + "\n", encoding="utf8")
    (out / "description.txt").write_text(desc, encoding="utf8")
    (out / "tags.txt").write_text(", ".join(tags) + "\n", encoding="utf8")
    (out / "pinned_comment.txt").write_text(pinned + "\n", encoding="utf8")
    (out / "chapters.txt").write_text(chapters + "\n", encoding="utf8")
    log(f"  upload kit: {out}")
    return out
