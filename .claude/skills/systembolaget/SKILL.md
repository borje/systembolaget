---
name: systembolaget
description: Search Systembolaget's drink catalogue with the `sb` CLI. Use when someone wants to find, compare or look up a drink (vin, öl, sprit, cider, alkoholfritt) by taste, food pairing, price, country, grape, alcohol content or similarity to another drink — e.g. "något som passar till grillat", "ett fylligt rött under 150 kr", "liknande smak som Barolo", "starkaste ölen", or when they want to export the catalogue.
---

# Systembolaget CLI

`sb` searches the live Systembolaget catalogue (~27 000 products) through the
same public REST API that systembolaget.se uses. No account or API key needed.

Run it with `uv run sb` from the project root, or just `sb` if the environment
is already active.

## Picking a command

| The request | Command |
|---|---|
| Find drinks matching stated wishes | `sb search` |
| Everything known about one product | `sb show NUMBER` |
| "Something like this one" | `sb like NUMBER` |
| "Surprise me" | `sb random` |
| What values can I filter on? | `sb facets [FILTER]` |
| Food pairing options | `sb pairings` |
| Stores and opening addresses | `sb stores` |
| Export the catalogue | `sb dump` |

Always pass `-n` to bound the result count, and prefer `-f json` when you need
to compute over the results rather than show them.

## Translating wishes into filters

This is the main job. Swedish drink vocabulary maps onto Systembolaget's
twelve-point *smakklockor*, each searchable as a `0-12` range.

| They say | Flag | Range | Applies to |
|---|---|---|---|
| fylligt, kraftfullt, mustigt | `--body` | `8-12` | vin, öl |
| lätt, nätt | `--body` | `0-5` | vin, öl |
| strävt, tanninrikt, kärvt | `--roughness` | `8-12` | **vin only** |
| mjukt, rundat | `--roughness` | `0-4` | **vin only** |
| friskt, syrligt, fruktigt | `--fruitacid` | `8-12` | **vin only** |
| sött, halvsött | `--sweetness` | `6-12` | vin, öl, sprit |
| torrt | `--sweetness` | `0-3` | vin, öl |
| beskt, humlebeskt | `--bitterness` | `8-12` | **öl only** |
| rökigt, torvigt | `--smokiness` | `7-12` | **sprit only** |
| fatlagrat, ekigt | `--oaked Fatlagrad` | — | vin |

Each clock is only filled in for the categories Systembolaget uses it for, so
combining one with the wrong category returns nothing: there are no beers with
a `roughness` value and no wines with a `bitterness` value. If a taste filter
gives zero hits, check this column before assuming the catalogue is empty.

Ranges accept `8-12`, `8-` (no upper bound), `-5` (no lower bound) or a bare
`8` (exact). The same syntax works for `--price` (kr), `--volume` (ml),
`--alcohol` (%) and `--sugar` (g/l).

"Passar till ..." maps to `--pairs-with`, which takes only these values:

```
Grönsaker Fisk Fågel Lamm Fläsk Nöt Vilt Skaldjur Ost Pasta Pizza
Grillat Hamburgare Kryddstarkt Asiatiskt Buffémat Snacks Dessert
Aperitif Avec/digestif Drinkingrediens Sällskapsdryck
```

Map the dish to the nearest one — *entrecôte* → `Nöt`, *räkor* → `Skaldjur`,
*curry* → `Kryddstarkt`, *tacos* → `Kryddstarkt`, *fredagsmys* →
`Sällskapsdryck`. If nothing fits, pass free text as the positional argument
instead of guessing: `sb search "Hernö" -c Sprit`.

Every categorical flag repeats, and repeating it means OR:

```bash
sb search --country Italien --country Spanien --grape Tempranillo
```

## Worked examples

```bash
# "Ett fylligt rött till grillat, runt 150 kr"
sb search --category Vin --subcategory "Rött vin" \
  --pairs-with Grillat --body 8-12 --price 120-180 -n 10

# "Något som smakar ungefär som den här" (artikelnummer 262708)
sb like 262708 -n 10

# ... but cheaper, and let it leave the category
sb like 262708 --price -120 --any-category -n 10

# "Ett torrt vitt med hög syra från Frankrike eller Tyskland"
sb search --category Vin --subcategory "Vitt vin" \
  --country Frankrike --country Tyskland --sweetness 0-3 --fruitacid 8-12 -n 10

# "En rökig whisky under 700 kr"
sb search --subcategory Whisky --smokiness 7-12 --price -700 -n 10

# "En IPA" — beer styles live in --style, spelled as Systembolaget spells them
sb search --category Öl --style "India pale ale (IPA)" --sort Price -n 10

# "Alkoholfritt till maten"
sb search --alcohol 0-0.5 --pairs-with Fisk -n 10

# "Ekologiskt vin i box, låg klimatpåverkan"
sb search --category Vin --organic --packaging Box --co2 Lägre -n 10

# How many matches, without listing them
sb search --category Vin --pairs-with Vilt --count
```

## Finding the right filter value

Values must match Systembolaget's own spelling **and capitalisation** exactly.
`--category vin` returns nothing; `--category Vin` returns 15 000 products.
Values are often surprising — beer styles read `India pale ale (IPA)`, not
`IPA`. When unsure, ask the API rather than guessing: `sb facets` lists the
filters, and `sb facets FILTER` lists that filter's values *for the current
selection*, with result counts.

```bash
sb facets                          # every available filter
sb facets country -c Vin           # countries that actually have wine
sb facets grape -c Vin             # all 300 grape varieties
sb facets producer -c Vin          # the 500 largest producers
```

Not every filter is advertised for every selection. `subcategory` and `style`
in particular often return no facet list, and the values then have to be
observed from results instead:

```bash
sb search -c Öl --subcategory Ale -n 200 -f json \
  | python3 -c "import json,sys,collections; print(collections.Counter(
      p['categoryLevel3'] for p in json.load(sys.stdin)).most_common())"
```

Zero hits almost always means a misspelled value. Suspiciously *many* hits
means a misspelled flag — the API ignores parameters it does not recognise
rather than rejecting them, so the filter silently did nothing.

## Similarity search

`sb like NUMBER` reads the reference product's taste clocks and searches for
drinks whose clocks sit within `±tolerance` (default 1), then ranks them by
mean distance. The `Likhet` column is that distance in clock steps, so `0.00`
is an exact profile match.

- `like` takes only `--tolerance`, `--price`, `--any-category`,
  `--match-pairings`, `-n` and `-f`. Other `search` filters such as `--country`
  are not accepted; narrow the result afterwards or fall back to `sb search`.
- `--tolerance 0` demands an identical profile; `3` or more casts wide.
- `--any-category` allows crossing from, say, red wine into port.
- `--match-pairings` additionally requires the same food symbols.
- Products with no taste clock data (many spirits) cannot be matched; the
  command says so, and `sb search` with explicit filters is the fallback.

## Getting full records

Search results carry ~70 fields. `sb show` and `sb search --full` fetch the
complete ~137-field record, which adds aroma, raw materials, producer and
terroir prose, nutrition tables and trivia.

```bash
sb show 262708                 # readable, with taste clock bars
sb show 262708 -f json         # the whole record
sb search --grape Nebbiolo --full -f json -n 20 > nebbiolo.json
```

`--full` costs one extra request per product, so keep `-n` small.

## Exporting the catalogue

```bash
sb dump -o catalogue.ndjson              # everything, ~27 000 products
sb dump -c Vin -o wine.ndjson            # one category
sb dump -c Vin -f csv -o wine.csv        # spreadsheet-friendly subset
sb dump -c Vin -n 100 -o sample.ndjson   # a sample, to see the shape first
```

The search endpoint drops results on deep pages, so `dump` splits the query
into small buckets (category → subcategory → country → price band) that page
reliably, and de-duplicates. Progress goes to stderr, data to the file, so
`-o -` pipes cleanly.

`dump` always writes complete ~137-field records, looking each product up
individually, so a dump is a superset of what `sb search` returns — raw
materials, aroma, producer prose and nutrition included. That costs one request
per product, so a whole-catalogue dump runs for hours; use `--category` or
`--limit` when a slice will do.

## Notes and limits

- Output formats: `table` (default), `json`, `ndjson`, `csv`. Tables are for
  humans; parse `json`/`ndjson`.
- `--sort` accepts `Score`, `Price`, `Vintage`, `Volume`, `Name`,
  `ProductLaunchDate`. Add `--desc` to reverse. Sorting by alcohol is *not*
  supported by the API — filter with `--alcohol` and sort by something else.
- The reported result count runs slightly ahead of what the API will actually
  return, so a complete crawl can come back a few products short. That is the
  API's behaviour, not a bug in the crawl.
- Prices are current catalogue prices in SEK; stock levels are not exposed.
- Be polite: the default 0.1 s gap between requests is there for a reason.
  Lower it with `--rate-limit` only for a one-off bulk export.
