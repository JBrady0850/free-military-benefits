# Free Military Benefits (working name)

A free military and veteran benefits brief. It leads with what most people do not know, applies it to your own status and ZIP code, and keeps every entry sourced and dated. No account, no tracking, no fees.

**Live site:** https://jbrady0850.github.io/free-military-benefits/

## What it does

- **What you unlock.** Pick your status (any VA rating including 0 percent, 100 percent P&T, Purple Heart, caregiver, retiree, spouse and more) and see the high-value benefits people miss: base commissary and exchange shopping, military resorts, the DoD travel booking site, Space-A, CHAMPVA and Chapter 35, each with why it is missed and a step checklist saved on your device.
- **Veterans Day 2026 planner.** Every sourced offer grouped by date, filtered by meal, shopping, services or attractions, with redeem-later and family-included filters and one-tap calendar export (.ics).
- **Near me.** Enter a ZIP code to find participating Veterans Day locations, discount brands with stores nearby, the closest commissaries and exchanges, VA facilities and offers only in your state. The ZIP is converted on your device; only its center point goes to OpenStreetMap's Overpass service when you press Find.
- **Travel and cruises.** DoD-only travel options plus cruise line military programs with the fine print, and free retreats and support programs.
- **Discount directory.** Hand-checked discounts plus every brand that public military-discount directories report at **20 percent or more**, harvested automatically each week.
- **Assistant (optional).** Bring your own AI key (Anthropic, Gemini, OpenAI or local Ollama). The key stays in your browser and goes only to the provider you choose. Answers come only from this site's entries.

## How the data stays fresh

- `scripts/crawl.py` runs weekly in GitHub Actions (daily in early November). It checks robots.txt, reads the directory pages in `data/crawl_sources.yaml`, keeps only facts (brand, percentage, source link) at or above the threshold, skips brands curated by hand, and watches the VA News Veterans Day list for newly announced names.
- `scripts/build_data.py` validates every entry against `data/schema/entry.schema.json` and writes `site/data.json`. The page re-downloads it on every visit.
- CI proves its own checks: `build_data.py --selftest` must reject `tests/fixtures/bad.yaml`, and `tests/test_crawl.py` covers the parser.

## Files

| Path | Purpose |
|---|---|
| `data/hidden.yaml` | Lesser-known, high-value benefits with steps |
| `data/veterans-day-2026.yaml` | Veterans Day 2026 offers (VA News list plus named community sources) |
| `data/travel.yaml` | Cruise line military programs |
| `data/free.yaml` | Free passes, facilities, retreats and support |
| `data/discounts.yaml` | Hand-checked year-round discounts |
| `data/crawled.yaml` | Generated weekly; auto-listed 20 percent plus brands |
| `site/zip.json` | ZIP code centers from the U.S. Census Bureau Gazetteer (public domain), built by `scripts/build_zip.py` |

## Data rules

- Every entry needs a `source_url` and a `last_verified` date. Never state terms the source does not.
- `confidence`: `official` (the organization's own page or a government list), `community` (reported by a named third party), `unconfirmed`.
- Auto-found entries are always labeled community-reported; a hand-curated entry for the same brand replaces the auto one.
- No em dashes in data or generated text.

## Credits

Veterans Day list: VA News. Map data: OpenStreetMap contributors (ODbL). ZIP centers: U.S. Census Bureau. Free-experience entries draw on the [veteran-opportunities](https://github.com/techwithvictoria/veteran-opportunities) directory by Tech with Victoria; descriptions here are our own.

## Not affiliated

Not affiliated with the Department of Defense, the Department of Veterans Affairs or any brand listed. Nothing here is legal or financial advice. Confirm every offer at its source.

## License

Code: MIT. Data: CC BY-SA 4.0 (attribution, share alike).
