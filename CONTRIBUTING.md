# Contributing to Controglobe

Controglobe is open source. Competing canon is expected; the project keeps a *main* canon
and welcomes forks.

## Friends first

Controglobe is made by people who enjoy building a world together, and the team is meant to be
friends first. Be kind, welcome newcomers, and remember that an argument about canon is an
argument about a story, never about the person making it. The project will take on more
structure as it grows, but that rule stays. If you would like to help and do not know where to
start, open an issue and say hello: there is always a flag to draw, a date to check or a page
to translate.

## Before you write

Read the rules on the [hub page](index.html). The three that get broken most often:

- **Geography is fixed.** If your idea needs a mountain range to move, it is a different project.
- **Roles, not costumes.** Congo carries Germany's *role*. It is not German. Its language is
  Kikongo, its cities are Kinshasa and Lubumbashi, its empire is the Kimfumu kya Kongo.
- **No conference borders.** If a frontier you draw is a straight line along a meridian,
  redraw it along a river, a watershed or a ceasefire.

## Opening an issue

Good issues:
- *"Tanzania = Bulgaria breaks the 1878 settlement, here is why"*
- *"The Aïr cantons and the Kanem herding rights contradict each other on the Termit frontier"*
- *"Who is the Portugal-analogue's colonial rival in the Indian Ocean?"*

Please label whether you are reporting a **contradiction**, proposing **new canon**, or
raising a **question**.

## Opening a pull request

1. One article per file, self-contained HTML, no external requests, no build step.
2. Artwork as inline SVG. Do not add binary image files.
3. Match the register of the existing articles: encyclopedic, past tense, no winking at
   the reader, no "in our timeline" outside the clearly marked swap-key sections.
4. Add your article to the table in `README.md` and to the cards in `index.html`.
5. Cross-link from at least one existing article.
6. Start from an existing page of the same kind, so the new page carries the design-system
   block, the masthead, the site footer and the chrome script unchanged. See below.

## Design system

Every page of both editions shares one design. It lives in four places, and each of them is
**identical on every page**: change it on all sixteen pages at once, never on one.
`python tools/sitekit.py` does that for you: `check` lists any page missing a shared part,
`chrome` copies the head tags, masthead, footer and chrome script from `africa.html` (and
`ar/africa.html`) to every page of its edition, keeping each page's current link, language
link, skip target and family, and `design` copies the stylesheet block from `index.html` to
every page. Edit the reference page, then run the command.

- **The stylesheet block** between the markers `/* ==== Controglobe design system` and
  `/* ==== end of design system`, at the top of each page's `<style>`. Rules that belong to one
  page only go *after* the end marker. The block holds the colour tokens (`--bg`, `--panel`,
  `--ink`, `--muted`, `--line`, `--accent`, `--link` and the rest) for the light theme, the dark
  theme and a forced theme, and the right-to-left rules for the Arabic edition.
- **The masthead**, `<header class="cg-mast">`, first thing in the `<body>`: the Controglobe globe
  as avatar, the site links, the colour-theme switch and the interlanguage link. The current
  page's link carries `aria-current="page"`. Visible labels in the switch come from its `data-l-*`
  attributes, so the chrome script needs no translation.
- **The site footer**, `<footer class="cg-foot">`, just before `<div id="pvcard">`.
- **The chrome script**, the last `<script>` in the body, beginning `/* Site chrome:`. It applies
  the stored colour theme and, on screens wider than 1320px, turns an article's contents box into a
  sidebar that follows the section being read.

The head of every page carries the Controglobe globe as its favicon (a PNG data URI, the globe
without its wordmark so it reads at tab size; the masthead and footer show the same image) and
its touch icon (the whole emblem on the masthead teal). `python build.py logo --site`, in
`video/`, redraws all of them in every page from the video's emblem. The head also carries
`<meta name="color-scheme" content="light dark">`, the masthead colour as
`theme-color`, and a one-line script that applies a stored theme before the page paints.

`<body>` carries the page's family, which scopes the rules that differ between them:
`cg-hub` for the front page, `cg-atlas` for the reference atlases and `cg-article` for everything
written as an encyclopedia article. An article keeps its content in `<div id="container">`, an
atlas and the hub in `<div class="wrap" id="main">`; the preview-card script reads those, not the
masthead or footer.

In the dark theme the page turns dark but **figures keep a light plate**, the way an encyclopedia
shows a printed map: the SVG artwork is drawn for paper and is not recoloured. Never rely on a
colour that only works on one theme; use the tokens.

A link to an article that does not exist yet (`href="#"`) is shown in the red-link colour, the way
an encyclopedia shows a missing article. It still opens a preview card when the term has an entry.

## Sections and figures

Articles are laid out the way an encyclopedia lays them out. Every substantial section opens
with a hatnote and, where a picture earns its place, carries a captioned figure:

```html
<h2 id="colonial">Foreign colonisation (1497&ndash;1763)</h2>
<p class="hatnote">Main articles: <a href="#">Colonial Arabia</a>, <a href="#">Thirteen Princely Colonies</a></p>
<figure class="mapwrap">
<svg viewBox="0 0 920 620" role="img" aria-label="&hellip;">&hellip;</svg>
<figcaption>The <b>colonial holdings</b> on the Arabian coasts about 1750: &hellip;</figcaption>
</figure>
<p>Body text &hellip;</p>
```

- **Hatnotes** use the usual forms &mdash; *Main article:*, *Main articles:*, *Further
  information:*, *See also:* &mdash; and link to articles that exist or to `#` for ones that do
  not, exactly as a red link would.
- **Captions** say what the picture shows rather than repeating the section. Name the colours
  ("in pink", "in blue") so the reader can read the key from the caption, and give the date.
  Links and `<b>` are welcome; a bold term with a preview entry gets a card.
- **Figures** are `<figure class="mapwrap">` with an inline `<svg>` and a `<figcaption>`. Give
  every `svg` a `role="img"` and an `aria-label` that describes the whole picture, because the
  caption alone is not a description.
- **Maps** of the Mashriq share one canvas, `0 0 920 620`, and one coastline, so that a reader
  who has learnt the shape once can read every later map. It is the video's own frame: an
  azimuthal equal-area projection centred on 46.5°E 25°N at 5.089&nbsp;km a pixel. Their ground
  is drawn from the mesh the video is drawn on, by `python build.py sitemaps` in `video/`: the
  sea by depth, the land, Natural Earth's shaded relief (projected by QGIS), rivers and lakes,
  the map's coloured areas and the frontiers of the map's year, dark around the map's subject
  and lighter between the neighbours beyond it. So every border follows a river, a wadi, an
  escarpment or the mesh's hand-drawn edges, the same line the video draws that year.
  `video/config/sitemaps.yaml` says which regions take which legend colour, and the ground is
  shared by both editions. Everything a map says (towns, arrows, labels, legend, footnote) is
  the page's own and is written by hand on top; cities stand at their true positions with their
  labels beside them. Neighbours and
  seas (*Zagrosia*, *Masr*, *the Derg successor states*, *the Gulf*) are set in faint italic on
  the ground or water they name, never at the frame's edge. In the Arabic edition a label keeps to
  the side of its dot that the English gives it, and reads right to left. World maps share one frame: the
  Natural Earth projection centred on 11°E, 960 wide and cropped to 84°N&ndash;57°S, drawn from
  [Natural Earth](https://www.naturalearthdata.com/) coastlines (public domain) and baked into the
  page as inline SVG, with the key in a white band underneath. They show regions rather than
  countries. Regional maps (the trade in Europeans, the crowns coming to Arabia) use the same
  projection cropped to a box.
- **Africa is never coloured by modern states.** Colouring the countries of the outside timeline
  would draw the conference borders the setting forbids &mdash; the Egypt&ndash;Sudan parallel, the
  Libya&ndash;Chad line. Wherever a map colours part of Africa, it colours the nations of the
  [Africa atlas](africa.html), whose drawing has been fitted to real coordinates so its frontiers can
  be laid on a true coastline. Where the atlas leaves a sliver of coast uncovered, the nearest nation
  takes it.
- Artwork is inline SVG. No binary images, no external requests, no build step.

## Preview cards

Every article carries Wikipedia-style preview cards. Hovering, tapping or tabbing to a link,
a section anchor or a marked term opens a summary card. There is no build step and no request:
each page holds its own data at the bottom of the file, in the `PV` object inside the last
`<script>`.

An entry looks like this:

```js
"covenant-of-the-wells": {"t": "Covenant of the Wells", "s": "262&nbsp;BCE",
  "x": "Sworn at the wells of Hajr by Rabbel&nbsp;III and &hellip;", "img": ""}
```

`t` is the title, `s` the one-line subtitle, `x` the extract of two or three sentences, and
`img` an optional inline SVG thumbnail. A card is reached in one of four ways:

1. **Another article.** Links to a sibling page use the `LINKS` map, so any link to
   `vehicles.html` shows the *Motor vehicles* card. A new article needs one `art-` entry,
   added to `LINKS` on every page that links to it.
2. **A section of the same page.** Links to `#some-heading` build a card from the heading and
   its first paragraph. Nothing to maintain.
3. **A term.** `MATCH` maps the exact text of a link, a bold or italic term or a table cell to
   an entry key, so `<a href="#">Saqaliba</a>` gets a card without any extra attribute. The
   elements scanned are `a, b, i, strong, td, th`, the same list on every page.

   **A `MATCH` key is rendered text, not markup.** The lookup compares it against what the
   browser shows, with every whitespace run folded to a plain space, so a key must be written
   the way the page reads rather than the way the source is typed: `Aïr`, not
   `A&iuml;r`; `Mysore Loom & Motor`, not `Mysore Loom &amp; Motor`; `Aretas I` with a plain
   space, even where the prose prints `Aretas&nbsp;I`. A key that keeps the entity or the
   `&nbsp;` never fires, and the card it points at is simply never seen. A trailing
   parenthetical is forgiving &mdash; the cell `Aïr (custom)` still finds the key
   `Aïr` &mdash; so a qualifier in the table costs nothing.

   A link resolves by its target before `MATCH` is consulted, so `<a href="#section">` shows
   that section's card and `<a href="other.html">` shows that article's card, whatever the
   text says.
4. **An explicit mark.** Where a term appears only in running prose, wrap its *first* mention
   in `<span class="pv-t" data-pv="key">`, and leave the rest of the prose alone.

Keep entries to one card's worth of text, and keep them consistent with the article they
summarise: the same entity reads the same way on every page that mentions it.

## Translations

A language edition lives in its own directory under the **same filenames** as the English
originals &mdash; the Arabic edition is in `ar/`. Because every intra-site link is a bare relative
filename, a translated page links to its translated siblings with no href changes.

Translating a page means:

- `<html lang="…" dir="…">`, a `<link rel="alternate" hreflang>` pair in the head, and an
  interlanguage link in the nav back to English.
- Nothing to add to the stylesheet: the design system already carries the right-to-left rules,
  and uses logical properties (`padding-inline-start`, `border-inline-start`) wherever a side
  matters. System fonts only: no `@import`, no web fonts, no external requests, still no build step.
- The masthead and footer in the edition's language: the site links, the tagline, the theme labels
  in the switch's `data-l-*` attributes, and the interlanguage link pointing back.
- Prose, `<title>`, the meta descriptions, every SVG `<text>` and every `aria-label`. SVG geometry
  &mdash; `viewBox`, coordinates, path data, colours, the shared canvases &mdash; does not move. In an RTL
  edition, `text-anchor="middle"` labels translate in place; a start- or end-anchored label needs
  `direction="rtl"`, and a two-column key is mirrored across the canvas.
- The preview-card data: `t`, `s` and `x` in `PV`, and the *keys* of `MATCH`, which are on-page
  display text. The keys of `PV` and `LINKS`, `data-pv` values, `id` values and `#anchors` stay
  Latin so both editions keep working. User-visible strings inside the script are translated;
  code comments are not.
- A glossary in the edition's directory, binding for every proper noun, updated in the same pass
  whenever a new name is decided. See [`ar/GLOSSARY.md`](ar/GLOSSARY.md).

A link to an article that edition has not translated yet points at `../<file>.html` and carries
`class="pending"`, which prints a "(in English)" marker after it, the way an interlanguage red link
behaves. When that article is translated, drop the `../` and the class.

Two things bite in a right-to-left edition. A numeric range such as `1789&ndash;1797` lays out
backwards, because the en-dash between two numbers is a neutral and takes the paragraph's
direction; wrap the range in U+2066 (LRI) and U+2069 (PDI) and it reads left to right again, with
no markup added. And `margin-inline-start` on the interlanguage link resolves against *the link's*
`dir`, which is the other language's. The masthead avoids this by putting the link inside
`.cg-tools`, a container that carries no `dir` of its own, so its logical margins resolve against
the page. Inside an SVG, set `direction` explicitly on start- or end-anchored Arabic labels: the
page's `dir="rtl"` is inherited into the drawing and would otherwise swing them to the wrong side.

## Article checklist

- [ ] Every date, institution and border is internally consistent with existing canon
- [ ] The swap-key section says which outside-timeline history the subject carries
- [ ] Custom entities are marked as custom
- [ ] Nothing depends on a network request
- [ ] Terms with a preview entry are reachable, and every entry is reached by something
- [ ] Every substantial section has a hatnote, and every figure a caption
- [ ] The design-system block, masthead, footer and chrome script are unchanged from the other pages
- [ ] No map colours Africa by modern states
- [ ] The page is readable on a phone, and in both the light and the dark theme

## Licence

By contributing you agree your work is released under CC BY-SA 4.0.
