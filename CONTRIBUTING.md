# Contributing to Controglobe

Controglobe is open source. Competing canon is expected; the project keeps a *main* canon
and welcomes forks.

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
  who has learnt the shape once can read every later map. World maps share `0 0 960 500`,
  equirectangular, regions rather than countries. Keep the key inside the frame where there is
  sea to put it, and in a white band underneath where there is not.
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
   an entry key, so `<a href="#">Saqaliba</a>` gets a card without any extra attribute.
4. **An explicit mark.** Where a term appears only in running prose, wrap its *first* mention
   in `<span class="pv-t" data-pv="key">`, and leave the rest of the prose alone.

Keep entries to one card's worth of text, and keep them consistent with the article they
summarise: the same entity reads the same way on every page that mentions it.

## Article checklist

- [ ] Every date, institution and border is internally consistent with existing canon
- [ ] The swap-key section says which outside-timeline history the subject carries
- [ ] Custom entities are marked as custom
- [ ] Nothing depends on a network request
- [ ] Terms with a preview entry are reachable, and every entry is reached by something
- [ ] Every substantial section has a hatnote, and every figure a caption
- [ ] The page is readable on a phone

## Licence

By contributing you agree your work is released under CC BY-SA 4.0.
