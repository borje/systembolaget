---
name: vivino
description: Look up wine ratings and reviews on Vivino with the `vivino` CLI. Use when someone wants a Vivino rating/score for a specific wine, to check whether a wine (e.g. from Systembolaget) is any good, to read reviews, or to search Vivino by name/grape/region — e.g. "är det här ett bra vin enligt Vivino", "vad har Barolo X för betyg", "kolla recensioner för...".
---

# Vivino CLI

`vivino` searches Vivino's undocumented JSON API — the same one vivino.com's
own frontend calls. No account or API key needed.

Run it with `uv run vivino` from the project root, or just `vivino` if the
environment is already active.

## Picking a command

| The request | Command |
|---|---|
| Search/find a wine by name, grape, region | `vivino search TEXT` |
| One vintage's full detail (rating, region, winery) | `vivino show VINTAGE_ID` |
| User reviews for a wine | `vivino reviews WINE_ID` |

`search` results give you both ids. `vintage_id` (from the `Vintage ID`
column) is what `show` needs; `wine_id` (from the `Wine ID` column) is what
`reviews` needs — they are different things, a wine has many vintages.

## Worked examples

```bash
# "Är det här ett bra vin enligt Vivino?" — search, then read the wine rating
vivino search "Barolo Albe G.D. Vajra"
vivino show 160828241

# Reviews for that wine (needs the wine id, not the vintage id)
vivino reviews 1100124 -n 5

# Narrow by type and price
vivino search "Chianti" --type red --max-price 200 --min-rating 3.8 -n 10
```

## Reading `search` output

The `Rating`/`Ratings` columns are the **wine's** rating across all vintages
(`wine_ratings_average`/`wine_ratings_count`), not the specific vintage's —
use this as the general "is this wine good" answer, since a single vintage's
own rating count is often thin or zero.

`--min-price`/`--max-price` are in `--currency` (default `SEK`) and
`--country` (default `se`) controls which market's price is returned.

## `show` and rating fields

`vivino show` reports two different ratings, and they live under different
keys in `-f json`:

- **Wine rating** — the wine across all vintages: `wine.statistics.ratings_average` / `wine.statistics.ratings_count`. This is the number to trust.
- **Vintage rating** — this specific year only: top-level `statistics.ratings_average` / `statistics.ratings_count`. Often based on very few ratings (sometimes 0-1) even for a well-reviewed wine — don't present it as equivalent to the wine rating.

## Gotchas

- **Search text must roughly match Vivino's own listing, not the seller's
  marketing name.** Systembolaget's "Hermitage Sélection" is Vivino's
  "Crozes-Hermitage" (a different, lower appellation) for the same producer —
  searching the retailer's product name can silently match the wrong wine.
  Cross-check producer + region, not just the string.
- **A no-year-match search does not fail — it returns unrelated vintages of
  the same wine (sometimes decades off, even before the winery's own
  founding), all carrying identical wine-level rating/count.** Confirm the
  target vintage actually appears before trusting a per-vintage claim; fall
  back to the wine-level rating instead.
- Low `Ratings` count (under ~50) means the average is noisy — say so rather
  than presenting it as equivalent to a wine with thousands of ratings.
- Reviews come back empty for obscure/low-volume wines — check the `Ratings`
  count from `search`/`show` first to avoid a pointless lookup.
- `--type` values: `red`, `white`, `sparkling`, `rose`, `dessert`, `fortified`.
- Output formats: `table` (default, for humans) or `json` (`-f json`) —
  parse `json` when computing over results rather than showing them.
