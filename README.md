# Controglobe

**An open-source worldbuilding encyclopedia.** From 500 BCE the Global North and the Global South
trade historical trajectories. Geography stays exactly where it is; everything else moves.

**Live site:** https://mofferato.github.io/controglobe/

## Articles

| Page | What it is |
|---|---|
| [`index.html`](index.html) | Project hub, premise, rules of the setting |
| [`united-states-of-arabia.html`](united-states-of-arabia.html) | The featured article: the federal republic of al-Mashriq, modelled on the *United States* article (primary) and *Saudi Arabia* (secondary) |
| [`history-of-the-united-states-of-arabia.html`](history-of-the-united-states-of-arabia.html) | History of Arabia from prehistory to the present, modelled on *History of the United States* (primary) and *History of Saudi Arabia* (secondary), including the Islamic-era and colonial trades in Europeans |
| [`nabataean-unification.html`](nabataean-unification.html) | The Nabataean Kingdom (c. 440 BCE – 36 CE), a custom entity modelled on the *Nabataean Kingdom* article: the Covenant of the Wells, the water administration and the origin of written Arabic |
| [`vehicles.html`](vehicles.html) | Motor vehicles in the Global Swap: the Kongolese invention of the car, Mosul mass production, the Hindustani turn after the oil shocks, Nusantaran electrification, and the regional design traditions, with schematic drawings |
| [`africa.html`](africa.html) | Reference atlas: every African nation, its Global-North counterpart, and a map on non-colonial borders |

## The core swap

| Region | Carries the history of |
|---|---|
| Middle East | North America (Arabia = USA, Zagrosia = Canada, Masr = Mexico) |
| Africa | Europe (Kimfumu kya Kongo = Germany, Jolof = Spain, Derg Union = Russia) |
| Europe | Africa |
| North America | Middle East |
| South Asia | Britain, Japan and China combined |
| Maritime South-East Asia | China |
| South America | Mainland South Asia |
| Caucasus | Caribbean |
| Central Asia | Central America |
| Indian Ocean islands, Macaronesia, South Atlantic | The Pacific |

Exceptions: Iceland = Morocco, Greenland = Cyprus.

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

Every article is laid out the way an encyclopedia lays one out: sections open with a hatnote,
and the maps, diagrams and charts are **captioned figures** drawn as inline SVG &mdash; the maps of
the Mashriq all on one coastline, the world maps all on one projection.

Every article carries Wikipedia-style **preview cards**: hovering, tapping or tabbing to a link,
a section anchor or a marked term opens a summary card, drawn from data held in the same file.
Cards for cross-article links carry a thumbnail; cards for a section of the current page are
built from the page itself. See [CONTRIBUTING.md](CONTRIBUTING.md#preview-cards).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Open an **issue** to argue about canon;
open a **pull request** to add or fix an article.

## Licence

Text and images: [CC BY-SA 4.0](LICENSE). Reuse and modify with attribution, share alike.
