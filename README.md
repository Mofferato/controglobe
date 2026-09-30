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
| [`kingdom-of-solms-america.html`](kingdom-of-solms-america.html) | North America carries the Middle East: the oil monarchy of the southern plains, modelled on the *Saudi Arabia* article (primary) and *Texas* and *United States* (secondary). The House of Solms and the Plain Rule, the Two Sanctuaries of Paquim&eacute; and Chukson, the thirteen marches, and the continent's states, militias and unrecognised authorities on maps traced on the ground |
| [`nabataean-unification.html`](nabataean-unification.html) | The Nabataean Kingdom (c. 440 BCE – 36 CE), a custom entity modelled on the *Nabataean Kingdom* article: the Covenant of the Wells, the water administration and the origin of written Arabic |
| [`vehicles.html`](vehicles.html) | Motor vehicles in the Global Swap: the Kongolese invention of the car, Mosul mass production, the Hindustani turn after the oil shocks, Nusantaran electrification, and the regional design traditions, with schematic drawings |
| [`africa.html`](africa.html) | Reference atlas: every African nation, its Global-North counterpart, and a map whose frontiers are traced on rivers, watersheds and escarpments, never on a partition line |
| [`europe.html`](europe.html) | Reference atlas: every European nation, its Global-South counterpart, the African partition of the continent, and the mirror rule that keeps the two atlases consistent |
| [`timeline-of-the-global-swap.html`](timeline-of-the-global-swap.html) | Chronology of the whole setting in ten eras, from the Achaemenid withdrawal of 460&nbsp;BCE to 2026, with maps of the trade in Europeans, the crowns coming to Arabia and the Cold War. Every entry is drawn from, and links to, the article that treats it. Its last section is the setting's **master swap key**: the regions, the events, the states of al-Mashriq and North America, and North America's militias and unrecognised authorities, with their map |

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
| [`ar/kingdom-of-solms-america.html`](ar/kingdom-of-solms-america.html) | translated |
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
| Middle East | North America. **al-Mashriq** is Arabia = the USA, Zagrosia = Canada (Anatolia is its Quebec, Iran the rest) and Qubrus = Greenland, a self-governing dependency of Ifriqiya (independent until Ifriqiya colonised it in 1721; home rule 1979, self-rule 2009); Masr = Mexico is the neighbour outside it |
| Africa | Europe (Kimfumu kya Kongo = Germany, Jolof = Spain, Manden = Italy, Ifriqiya = Denmark, Derg Union = Russia) |
| Europe | Africa |
| North America | Middle East (**Solms-America** = Saudi Arabia on the ground of Texas, Mississippi = Iraq, Atlantica = Iran, Aztlan = Israel, California = Palestine, Cascadia = Syria, Oregon = Lebanon, Colorado = Jordan, Mexico = Egypt, Nuevo Le&oacute;n = Yemen, the Gulf states of Ludwigsland, Karankawa, the Counties, R&iacute;o Grande and Puerto Rico = Kuwait, Qatar, the Emirates, Oman and Bahrain, Canada = Turkey) |
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
Within Africa the swap follows civilisation before geography: Italy's role is carried by Manden, on the ground of Mali,
heir to Wagadu (the Ghana Empire) as Italy is heir to Rome, in the Latin west rather than the far south; Angola (Ndongo)
carries Montenegro instead.

North America was peopled from the 1400s by Europe's tribal Christian confederations (the Crossing), so its
nations are Germanic, French, Castilian, Slavic and English by speech. The Abrahamic religions' part is carried
by the prophetic monotheisms of native America: the Path, preached at Paquim&eacute;, whose holy places the
conquerors adopted as their own, and the older faith of the Nahua, who carry the Jews' part in Aztlan. The
nations of the plains and the lakes carry the Kurds'. The
[Timeline's swap key](timeline-of-the-global-swap.html#north-america) has the whole continent, with its
militias and unrecognised authorities.

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
over relief and sea depths from [ETOPO 2022](https://www.ncei.noaa.gov/products/etopo-global-relief-model)
(NOAA NCEI, public domain) that QGIS projects and shades and GIMP finishes, all baked into the
page; wherever they colour Africa, they colour the nations of the Africa atlas on its
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

## Community

Come and say hello on the Discord: **https://discord.gg/XYZXVFjQUj**

[`community/`](community/) holds the Controglobe Discord: its channels, roles, rules and
onboarding as data, and a script that builds the server from them. Start at
[`community/README.md`](community/README.md).

## Credits

Controglobe branched off from
[*A More Fractured Union: USA and Middle East swap*](https://www.reddit.com/r/imaginarymaps/comments/1hk5ngv/a_more_fractured_union_usa_and_middle_east_swap/)
(r/imaginarymaps, December 2023), a map by **Bemon** (u/kaselev: scenario writer, chief cartographer, flag
designer, editor) and **Body25** (u/bodycornflower: co-writer, flag designer, editor). The states of North
America, the Middle Eastern country each one stands for, the non-state actors and *The Damascus Times* are
theirs; Controglobe keeps them, moves their frontiers from state lines onto rivers and watersheds, and adds
the peoples, the religions and the histories. Both of them also helped with the timeline in its first
months, before contact with them was lost. The project is grateful to them, and the door stays open.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Open an **issue** to argue about canon;
open a **pull request** to add or fix an article.

## Licence

Text and images: [CC BY-SA 4.0](LICENSE). Reuse and modify with attribution, share alike.
