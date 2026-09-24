# Controglobe

**An open-source worldbuilding encyclopedia.** From 500 BCE the Global North and the Global South
trade historical trajectories. Geography stays exactly where it is; everything else moves.

**Live site:** https://mofferato.github.io/controglobe/

## Articles

| Page | What it is |
|---|---|
| [`index.html`](index.html) | Project hub, premise, rules of the setting |
| [`united-states-of-arabia.html`](united-states-of-arabia.html) | The featured article: the federal republic in al-Mashriq, modelled on the *United States* article (primary) and *Saudi Arabia* (secondary) |
| [`history-of-the-united-states-of-arabia.html`](history-of-the-united-states-of-arabia.html) | History of Arabia from prehistory to the present, modelled on *History of the United States* (primary) and *History of Saudi Arabia* (secondary), including the Islamic-era and colonial trades in Europeans |
| [`nabataean-unification.html`](nabataean-unification.html) | The Nabataean Kingdom (c. 440 BCE – 36 CE), a custom entity modelled on the *Nabataean Kingdom* article: the Covenant of the Wells, the water administration and the origin of written Arabic |
| [`vehicles.html`](vehicles.html) | Motor vehicles in the Global Swap: the Kongolese invention of the car, Mosul mass production, the Hindustani turn after the oil shocks, Nusantaran electrification, and the regional design traditions, with schematic drawings |
| [`africa.html`](africa.html) | Reference atlas: every African nation, its Global-North counterpart, and a map on non-colonial borders |
| [`europe.html`](europe.html) | Reference atlas: every European nation, its Global-South counterpart, the African partition of the continent, and the mirror rule that keeps the two atlases consistent |
| [`timeline-of-the-global-swap.html`](timeline-of-the-global-swap.html) | Chronology of the whole setting in ten eras, from the Achaemenid withdrawal of 460&nbsp;BCE to 2026, with maps of the trade in Europeans, the crowns coming to Arabia and the Cold War. Every entry is drawn from, and links to, the article that treats it |

## Arabic edition &mdash; الطبعة العربية

The Arabic edition lives in [`ar/`](ar/), one file per article under the **same filename** as the
English original, the way Wikipedia keeps a language at its own site. Because every intra-site link
is a bare relative filename, a page inside `ar/` links to its Arabic siblings with no href changes.
Every article has an Arabic edition, and every English article carries an interlanguage link to it.

| Page | Status |
|---|---|
| [`ar/index.html`](ar/index.html) | translated |
| [`ar/united-states-of-arabia.html`](ar/united-states-of-arabia.html) | translated |
| [`ar/history-of-the-united-states-of-arabia.html`](ar/history-of-the-united-states-of-arabia.html) | translated |
| [`ar/nabataean-unification.html`](ar/nabataean-unification.html) | translated |
| [`ar/vehicles.html`](ar/vehicles.html) | translated |
| [`ar/africa.html`](ar/africa.html) | translated |
| [`ar/europe.html`](ar/europe.html) | translated |
| [`ar/timeline-of-the-global-swap.html`](ar/timeline-of-the-global-swap.html) | translated |

[`ar/GLOSSARY.md`](ar/GLOSSARY.md) is the binding authority on every proper noun in Arabic, and on
the conventions of the edition: MSA in the register of ar.wikipedia, Western Arabic numerals,
ق.م / م for the eras, and code identifiers (`id`, anchors, `data-pv` and `PV`/`LINKS` keys) left in
Latin so links keep working across both editions. A link to an article that has no Arabic edition
yet points at `../<file>.html` and carries `class="pending"`, which prints "(بالإنجليزية)" after it,
the way an interlanguage red link behaves; when that article is translated, drop the `../` and the
class. Nothing carries `class="pending"` at the moment &mdash; the rule stays in the stylesheet for
the next article written in English first. Each page carries `<html lang="ar" dir="rtl">` and a
`<link rel="alternate" hreflang>` pair; the right-to-left rules are part of the shared design system,
so an Arabic page needs no stylesheet of its own &mdash; system fonts only, no external requests. A
numeric range is wrapped in U+2066/U+2069 so that 1789&#8211;1797 still reads left to right inside
right-to-left text.

## The core swap

| Region | Carries the history of |
|---|---|
| Middle East | North America. **al-Mashriq** is Arabia = the USA, Zagrosia = Canada (Anatolia is its Quebec, Iran the rest) and Qubrus = Greenland; Masr = Mexico is the neighbour outside it |
| Africa | Europe (Kimfumu kya Kongo = Germany, Jolof = Spain, Derg Union = Russia) |
| Europe | Africa |
| North America | Middle East |
| South Asia | Britain, Japan and China combined |
| Maritime South-East Asia | China |
| South America | Mainland South Asia |
| Caucasus | Caribbean |
| Central Asia | Central America |
| Indian Ocean islands, Macaronesia, South Atlantic | The Pacific |
| Afghanistan | Siberia |
| Siberia | Afghanistan |

Exceptions: Iceland = Morocco, Greenland = Cyprus. Afghanistan and Siberia trade places one for one: Afghanistan is
the Abyssinian Empire's (later the Derg Union's) vast eastern hinterland, and Siberia is the independent, mountain-ringed
kingdom that no empire held for long, the ground of the Siberian War. Anatolia is Zagrosian ground, so Turkey is outside the African swap the way Egypt is outside the European one.

Unassigned: East Asia, the rest of northern Asia, mainland South-East Asia and Australia have no counterpart
yet, and the world maps leave them grey. Proposals are welcome in the issue tracker.

## Rules

1. **Geography is fixed.** Only history moves.
2. **Borders are internal.** No frontier descends from a partition conference.
3. **Roles, not costumes.** A nation carries another's historical role, not its names, language or religion.
4. **Custom entities are allowed** where nothing maps cleanly (A&iuml;r, Kanem, Songhai, Tem).
5. **Contradiction is expected.** Forks and competing canon are the point.

## How this is built

Every page is a single self-contained HTML file. No build step, no framework, no dependencies,
no external requests. All artwork &mdash; flags, seals, maps, presidential portraits &mdash; is
inline SVG. Open any file in a browser and it works.

Every page shares one **design system**: a block of CSS that is identical on all pages of both
editions, one masthead with the Controglobe globe as its avatar (the same globe is every page's
favicon), one site footer, and a small chrome script. The design follows the reader's light or dark
setting, and a switch in the masthead overrides it; on wide screens an article's contents box
becomes a sidebar that tracks the section being read. See
[CONTRIBUTING.md](CONTRIBUTING.md#design-system).

Every article is laid out the way an encyclopedia lays one out: sections open with a hatnote,
and the maps, diagrams and charts are **captioned figures** drawn as inline SVG &mdash; the maps of
the Mashriq all on one coastline, the world maps all on one projection. World and regional maps
are drawn on real coastlines from [Natural Earth](https://www.naturalearthdata.com/) (public domain),
baked into the page; wherever they colour Africa, they colour the nations of the Africa atlas on its
own non-colonial frontiers, never modern states.

Every article carries Wikipedia-style **preview cards**: hovering, tapping or tabbing to a link,
a section anchor or a marked term opens a summary card, drawn from data held in the same file.
Cards for cross-article links carry a thumbnail; cards for a section of the current page are
built from the page itself. See [CONTRIBUTING.md](CONTRIBUTING.md#preview-cards).

## Video

[`video/`](video/) builds the series' mapping videos from this canon, starting with
*Alternate History of Arabia (in place of the United States), every year*: the Global Swap's
borders drawn year by year on real coastlines, rendered with Python and finished in QGIS, GIMP
and DaVinci Resolve, with Claude writing the data and driving the tools. It is separate from the
encyclopedia (the site still has no build step and no dependencies); start at
[`video/README.md`](video/README.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Open an **issue** to argue about canon;
open a **pull request** to add or fix an article.

## Licence

Text and images: [CC BY-SA 4.0](LICENSE). Reuse and modify with attribution, share alike.
