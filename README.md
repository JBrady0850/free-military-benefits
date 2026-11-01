# Free Military Benefits

A free military and veteran benefits brief. It leads with what most people do not know, applies it to your own status and ZIP code, and backs every discount with at least two independent sources. No account, no tracking, no fees.

**Live site:** https://jbrady0850.github.io/free-military-benefits/

## What it does

- **Start here.** Five quick questions (status, ZIP, interests, family, what you already have), asked once and saved in your browser. Every tab follows the answers.
- **What you unlock.** The high-value benefits people miss: base commissary and exchange shopping with any VA rating, military resorts, the DoD travel booking site, Space-A, CHAMPVA and Chapter 35, each with why it is missed and a step checklist. Benefits you already have move to their own list.
- **Veterans Day 2026 planner.** Every offer we can source twice, grouped by date, with meal, shopping, services and attractions filters, redeem-later and family filters, a search box, and one-tap calendar export. With a ZIP set it shows national chains plus anything with a location or state match near you, and hides place-bound offers elsewhere.
- **Near me.** The nearest participating restaurants, discount brands with stores, bases, VA facilities and state-only offers. Everything runs on your device from location files the site refreshes weekly; your ZIP never leaves the browser.
- **Travel and cruises.** DoD-only travel, cruise line military programs with the fine print, and free retreats and support programs.
- **Discount directory.** Hand-checked discounts plus every brand that public directories report at **more than 20 percent**, with category counts, an over-20 filter and a "confirmed on the brand's page" filter.
- **Assistant (optional).** Bring your own AI key (Anthropic, Gemini, OpenAI or local Ollama). Answers come only from this site's entries, and the page lists which entries it sent.
- **Sources and data.** Every source page read in the last refresh, how many rows it gave, which ones failed, and which brands are waiting on a second source.

## The two-source rule

Every discount or Veterans Day offer in the dataset has at least two independent sources: two different sites, or one site plus the brand's own page confirming the percentage. Sites on one registrable domain count once. `scripts/build_data.py` fails the build when an entry has fewer, and the self-test proves the check catches a planted single-source entry. Offers reported by one source wait in `data/watch.json` and on the Sources tab until a second confirms them. Wording such as "likely", "expected", "pending" or "2025 terms" is never counted as an offer for this year.

Every source link opens at the offer: the brand's own page, or the list page with a text fragment that scrolls to the line.

## How the data stays fresh

- `scripts/crawl.py` runs weekly in GitHub Actions and daily Nov 1 to 14. It checks robots.txt for every host, reads the 23 directory pages and 20 Veterans Day lists in `data/crawl_sources.yaml`, keeps only facts (brand, percentage, link), fetches each page once with one retry, skips any Veterans Day page whose title names another year, and verifies brand pages in parallel.
- `scripts/snapshot_places.py` rebuilds `site/places.json` from All the Places (CC0) store locators, VA facilities and Wikidata installations.
- `scripts/build_data.py` validates every entry against `data/schema/entry.schema.json`, enforces the two-source rule, derives badge percentages, adds text fragments, flags curated entries not rechecked in 90 days, and writes `site/data.json` with data-health stats. The page re-downloads it on every visit.
- CI proves its own checks: `build_data.py --selftest`, `tests/test_crawl.py` (27 parser checks), `tests/test_percent.py`, `tests/test_sources.py`.

## Files

| Path | Purpose |
|---|---|
| `data/hidden.yaml` | Lesser-known, high-value benefits with steps |
| `data/veterans-day-2026.yaml` | Hand-checked Veterans Day 2026 offers, each with two sources |
| `data/crawled-veterans-day.yaml` | Generated: Veterans Day offers named on two or more upstream lists |
| `data/travel.yaml` | Cruise line military programs |
| `data/free.yaml` | Free passes, facilities, retreats and support |
| `data/discounts.yaml` | Hand-checked year-round discounts |
| `data/crawled.yaml` | Generated weekly: brands over 20 percent with two sources or a confirming brand page |
| `data/crawl_sources.yaml` | The directories and lists the harvester reads |
| `data/watch.json` | Generated: held brands, per-source counts, failures |
| `site/zip.json` | ZIP code centers and states from the U.S. Census Bureau (public domain) |
| `site/places.json` | Generated weekly: store, VA facility and installation locations |

## Data rules

- Every entry needs `source_url`, `sources` (two independent sites for discounts and offers), and a `last_verified` date. Never state terms the source does not.
- `confidence`: `official` (the organization's own page or a government list), `community` (reported by a named third party), `unconfirmed`.
- Auto-found entries are labeled; a hand-curated entry for the same brand replaces the auto one.
- Fix generated files by fixing the generator, never by editing `crawled*.yaml`, `data.json` or `places.json`.
- No em dashes in data or generated text.

See `CONTRIBUTING.md` to add an entry or a source.

## Credits

Veterans Day anchor list: VA News. Store and facility locations: All the Places (CC0) and Wikidata (CC0). Map links: OpenStreetMap. ZIP centers: U.S. Census Bureau. Free-experience entries draw on the [veteran-opportunities](https://github.com/techwithvictoria/veteran-opportunities) directory by Tech with Victoria; descriptions here are our own.

## Not affiliated

Not affiliated with the Department of Defense, the Department of Veterans Affairs or any brand listed. Nothing here is legal or financial advice. Confirm every offer at its source.

## License

Code: MIT. Data: CC BY-SA 4.0 (attribution, share alike).
