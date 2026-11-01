# Earned Benefits (working name)

Free, open-source military benefits toolkit. Every military and veteran discount, free benefit, and planning tool in one place, at no cost, with no account and no tracking. Others charge up to $59.99 a year to aggregate public data; this project keeps the data open.

**Planned live site:** https://jbrady0850.github.io/earned-benefits/

## What works in this v0 scaffold

- `site/index.html`: a zero-build HTML front end in the navy house theme. Search, category chips, kind and verification filters, provenance badges (verified date, confidence), and source links on every card.
- `data/discounts.yaml` and `data/free.yaml`: the open dataset. Every entry carries `source_url`, `last_verified`, and `confidence`.
- `data/schema/entry.schema.json`: the contract every entry must meet.
- `scripts/build_data.py`: validates the dataset and generates `site/data.json` for the page.
- Assistant panel (optional): bring your own AI key (Anthropic, Gemini, OpenAI, or local Ollama). The key stays in your browser's localStorage and is sent only to the provider you chose. The app is fully usable without it.

## Design principles

1. Free forever. No tier, no trial, no account.
2. Privacy first: location and profile math happen in the browser and never leave the device.
3. Data as code: every entry is reviewable, sourced, and dated; CI validates the schema.
4. One-stop shop: discounts, free items, parks passes, state benefits, and calculators together.

## Roadmap (from the design document)

- v0.1: 200+ sourced discounts, 50+ free benefits, VA disability math calculator, verification helper (GOVX, ID.me, SheerID, WeSalute, ExpertVoice), first ten state pages, PWA offline support, map view (MapLibre + OpenStreetMap).
- v0.2: net pay calculator, TSP modeler, SCRA/MLA card tracker with calendar export, Veterans Day seasonal page.
- Freshness engine: GitHub Actions crawlers refresh and verify the data on schedule; the page re-fetches fresh JSON on every visit.

## Data rules

- Only add an entry with an official `source_url`; never state terms the source does not.
- Set `last_verified` to the date you personally confirmed the page.
- `confidence`: `official` (verified on the brand's own page), `community` (reported by the community, source noted), `unconfirmed`.

## Not affiliated

This project is not affiliated with the Department of Defense, the Department of Veterans Affairs, or any brand listed. Always confirm terms at the linked source before relying on them.

## License

Code: MIT. Data: CC BY-SA 4.0 (attribution, share alike).
