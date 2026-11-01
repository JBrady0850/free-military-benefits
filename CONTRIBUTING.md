# Contributing

Corrections and additions are welcome. The site is data as code: a pull request that edits a YAML file is the whole change.

## Add a discount or Veterans Day offer by hand

1. Pick the file: `data/discounts.yaml` (year-round), `data/veterans-day-2026.yaml` (this Veterans Day), `data/hidden.yaml` (a benefit most people miss), `data/free.yaml`, `data/travel.yaml`.
2. Copy an existing entry. Give it a permanent lowercase `id` (Veterans Day ids end in `-vd26`).
3. Give it `sources` with two independent sites, or one site plus the brand's own page. Sites on one registrable domain count once. The first source becomes the headline link.
4. If a source is a long list page, add `anchor:` with the exact wording that page uses for the business so the link scrolls to it.
5. Write `offer` in your own words and only what the sources say. Set `last_verified` to the day you read them.
6. Run the checks:

```
python scripts/build_data.py --selftest
python tests/test_crawl.py
python tests/test_percent.py
python tests/test_sources.py
python scripts/build_data.py --check
```

The build fails on a missing second source, an em dash, an unknown category or an end date before the start date.

## Add a source page for the harvester

Add the URL to `data/crawl_sources.yaml` under `directories` (year-round lists) or `veterans_day_lists` (this year's Veterans Day pages). Pages must be public, allow crawling in robots.txt, and show the brand and the percentage in the same list item, paragraph, table row or heading. A Veterans Day page whose title names another year is skipped automatically. Run `python tests/test_sources.py` and, if you can, `python scripts/crawl.py` (about three minutes, needs network) and look at `data/watch.json` for what it found.

## Do not edit generated files

`data/crawled.yaml`, `data/crawled-veterans-day.yaml`, `data/watch.json`, `site/data.json` and `site/places.json` are rebuilt by scripts. Fix the script instead.

## Style

Plain, direct sentences. No em dashes. No emoji. No marketing adjectives. Say who qualifies and what to bring, not how great the deal is.
