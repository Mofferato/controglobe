#!/usr/bin/env python3
"""Keep the encyclopedia's shared parts identical on every page, the way CONTRIBUTING.md asks.

  python tools/sitekit.py check     report every page that is missing a shared part
  python tools/sitekit.py chrome    copy the head tags, masthead, footer and chrome script from the
                                    reference page of each edition to every page of that edition
  python tools/sitekit.py design    copy the design-system stylesheet block from index.html to every
                                    page of both editions

Every page stays a single self-contained file: this is not a build step, only a way to change
the shared parts once instead of sixteen times. Each page keeps its own four differences: the
link marked as the current page, where the language switch points, the skip link's target and
the page family on <body> (cg-hub, cg-atlas or cg-article). Line endings are kept as found.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
REFERENCE = {"en": "africa.html", "ar": "ar/africa.html"}     # complete pages to copy the chrome from
DESIGN_SOURCE = "index.html"                                  # the page whose stylesheet block is the master
FAMILY = {"index.html": "cg-hub", "africa.html": "cg-atlas", "europe.html": "cg-atlas"}   # others: cg-article
HEAD_TAGS = [r'<meta name="color-scheme"[^>]*>', r'<meta name="theme-color"[^>]*>', r'<link rel="icon"[^>]*>',
             r'<link rel="apple-touch-icon"[^>]*>', r"<script>try\{var t=localStorage\.getItem\('cg-theme'\)[^<]*</script>"]
MAST = re.compile(r'<header class="cg-mast"[\s\S]*?</header>')
FOOT = re.compile(r'<footer class="cg-foot">[\s\S]*?</footer>')
CHROME = re.compile(r"<script>\s*/\* Site chrome:[\s\S]*?</script>")
DESIGN = re.compile(r"/\* ==== Controglobe design system[\s\S]*?/\* ==== end of design system[^\n]*")


def pages() -> list[pathlib.Path]:
    return sorted(ROOT.glob("*.html")) + sorted(ROOT.glob("ar/*.html"))


def read(p: pathlib.Path) -> str:
    with open(p, encoding="utf8", newline="") as fh:
        return fh.read()


def write(p: pathlib.Path, text: str) -> None:
    with open(p, "w", encoding="utf8", newline="") as fh:
        fh.write(text)


def edition(p: pathlib.Path) -> str:
    return "ar" if p.parent.name == "ar" else "en"


def like(block: str, page_text: str) -> str:
    """A block copied from another file, given the target page's line endings."""
    block = block.replace("\r\n", "\n")
    return block.replace("\n", "\r\n") if "\r\n" in page_text else block


def family(p: pathlib.Path, text: str) -> str:
    m = re.search(r'<body class="(cg-[a-z]+)"', text)
    return m.group(1) if m else FAMILY.get(p.name, "cg-article")


def lang_href(p: pathlib.Path) -> str:
    if edition(p) == "en":
        return "ar/" if p.name == "index.html" else f"ar/{p.name}"
    return "../" if p.name == "index.html" else f"../{p.name}"


def masthead(ref: str, p: pathlib.Path, fam: str) -> str:
    m = MAST.search(ref).group(0)
    m = m.replace(' aria-current="page"', "")
    m = re.sub(r'(<a href="%s")' % re.escape(p.name), r'\1 aria-current="page"', m, count=1)
    m = re.sub(r'(<a class="cg-skip" href=")[^"]*', r"\1" + ("#container" if fam == "cg-article" else "#main"), m)
    return re.sub(r'(<a class="cg-lang" href=")[^"]*', r"\g<1>" + lang_href(p), m)


def footer(ref: str, p: pathlib.Path) -> str:
    f = FOOT.search(ref).group(0)
    return re.sub(r'(<a href=")[^"]*("[^>]*\bhreflang=)', lambda m: m.group(1) + lang_href(p) + m.group(2), f)


def problems(p: pathlib.Path, s: str) -> list[str]:
    out = []
    for pat in HEAD_TAGS:
        if not re.search(pat, s):
            out.append(f"head tag {pat[:28]}")
    for name, rx in (("masthead", MAST), ("footer", FOOT), ("chrome script", CHROME), ("design system", DESIGN)):
        if not rx.search(s):
            out.append(name)
    if not re.search(r'<body class="cg-', s):
        out.append("page family on <body>")
    fam = family(p, s)
    if fam == "cg-article" and 'id="container"' not in s or fam != "cg-article" and 'id="main"' not in s:
        out.append("skip-link target")
    return out


def chrome() -> list[str]:
    refs = {ed: read(ROOT / name) for ed, name in REFERENCE.items()}
    changed = []
    for p in pages():
        s = read(p)
        ref = refs[edition(p)]
        fam = family(p, s)
        t = s
        # head tags, right after the viewport meta, in the reference's order
        head = [re.search(pat, ref).group(0) for pat in HEAD_TAGS]
        for pat in HEAD_TAGS:
            t = re.sub(r"[ \t]*" + pat + r"\r?\n?", "", t, count=1)
        nl = "\r\n" if "\r\n" in t else "\n"
        t = re.sub(r'(<meta name="viewport"[^>]*>\r?\n)', lambda m: m.group(1) + nl.join(head) + nl, t, count=1)
        # the page family and its skip-link target
        t = re.sub(r"<body[^>]*>", f'<body class="{fam}">', t, count=1)
        if fam == "cg-hub" and 'id="main"' not in t:
            t = t.replace('<div class="wrap">', '<div class="wrap" id="main">', 1)
        # masthead first in the body, footer just before the preview card, chrome script last
        mast = like(masthead(ref, p, fam), t)
        t = MAST.sub(lambda m: mast, t, count=1) if MAST.search(t) else \
            re.sub(r'(<body class="[^"]*">\r?\n)', lambda m: m.group(1) + mast + nl, t, count=1)
        foot = like(footer(ref, p), t)
        t = FOOT.sub(lambda m: foot, t, count=1) if FOOT.search(t) else \
            t.replace('<div id="pvcard"', foot + nl + '<div id="pvcard"', 1)
        script = like(CHROME.search(ref).group(0), t)
        t = CHROME.sub(lambda m: script, t, count=1) if CHROME.search(t) else \
            t.replace("</body>", script + nl + "</body>", 1)
        if t != s:
            write(p, t)
            changed.append(p.relative_to(ROOT).as_posix())
    return changed


def design() -> list[str]:
    block = DESIGN.search(read(ROOT / DESIGN_SOURCE)).group(0)
    changed = []
    for p in pages():
        s = read(p)
        t = DESIGN.sub(lambda m: like(block, s), s, count=1)
        if t != s:
            write(p, t)
            changed.append(p.relative_to(ROOT).as_posix())
    return changed


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "check"
    if cmd == "chrome":
        done = chrome()
        print(f"chrome synced in {len(done)} pages" + ("".join(f"\n  {d}" for d in done)))
    elif cmd == "design":
        done = design()
        print(f"design system synced in {len(done)} pages" + ("".join(f"\n  {d}" for d in done)))
    elif cmd != "check":
        print(__doc__)
        return 2
    bad = 0
    for p in pages():
        issues = problems(p, read(p))
        if issues:
            bad += 1
            print(f"{p.relative_to(ROOT).as_posix()}: missing {', '.join(issues)}")
    if not bad:
        print(f"all {len(pages())} pages carry every shared part")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
