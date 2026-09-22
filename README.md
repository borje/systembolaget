# systembolaget

A Python CLI for searching Systembolaget's drink catalogue (~27 000 products)
through the same public REST API that systembolaget.se uses in the browser.

No account and no API key: the subscription key the site ships publicly is
built in, and can be overridden with `SYSTEMBOLAGET_API_KEY` if it rotates.

## Installation

```bash
uv tool install .   # puts `sb` on your PATH
sb --help
```

Working on the code instead? `uv run sb ...` runs the CLI straight from the
checkout, no install needed — that's the form the rest of this README's
examples omit.

## Usage

```bash
sb search [TEXT] [FILTERS]   # search on any combination of wishes
sb show NUMBER               # everything known about one product
sb like NUMBER               # drinks that taste like this one
sb random                    # suggestions when you can't decide
sb facets [FILTER]           # what values a filter accepts
sb pairings                  # the "passar till ..." vocabulary
sb stores                    # stores and agents
sb dump                      # download the whole catalogue
```

### Searching by taste

Systembolaget scores drinks on twelve-point *smakklockor*, and each one is a
searchable range:

```bash
# A full-bodied, tannic red for the grill, 120-180 kr
sb search --category Vin --subcategory "Rött vin" \
  --pairs-with Grillat --body 8-12 --roughness 8-12 --price 120-180

# A dry, high-acid white from France or Germany
sb search --category Vin --subcategory "Vitt vin" \
  --country Frankrike --country Tyskland --sweetness 0-3 --fruitacid 8-12

# A smoky whisky under 700 kr
sb search --subcategory Whisky --smokiness 7-12 --price -700
```

Ranges accept `8-12`, `8-` (open above), `-5` (open below) or a bare `8`.
Categorical flags repeat, and repeating means OR.

Which clocks exist depends on the category — `roughness` and `fruitacid` are
wine-only, `bitterness` is beer-only and `smokiness` is spirits-only.

### Finding something similar

```bash
sb like 262708              # same taste profile
sb like 262708 --tolerance 3 --any-category --price -150
```

`like` reads the reference drink's taste clocks, searches for drinks whose
clocks sit within ±tolerance, and ranks the results by mean distance. The
`Likhet` column is that distance in clock steps, so `0.00` is an exact match.

### Discovering filter values

Values are case-sensitive and spelled Systembolaget's way, so look them up
rather than guessing:

```bash
sb facets                   # every filter
sb facets country -c Vin    # countries that actually have wine
sb facets grape -c Vin      # all 300 grape varieties
```

### Exporting

```bash
sb dump -o catalogue.ndjson        # everything
sb dump -c Vin -f csv -o wine.csv  # one category, spreadsheet-friendly
sb dump -c Vin -n 100 -o try.ndjson  # a taste of it, for trying things out
```

The search endpoint silently drops results on deep pages, so `dump` splits the
query into small buckets (category → subcategory → country → price band) that
page reliably, then de-duplicates. On a spot check of Swedish beer this lifts
coverage from 95.9 % to 100 %.

Every product is then looked up individually, so the dump always carries the
complete ~137-field record rather than the ~70 fields search returns. That is
one request per product: a full catalogue takes hours, so narrow it with
`--category` or `--limit` unless you really want all of it.

### Output formats

`--format table` (default, for humans), `json`, `ndjson` or `csv`. Search
results carry ~70 fields; `sb show` and `sb search --full` fetch the complete
~137-field record, adding aroma, raw materials, producer and terroir prose,
nutrition tables and trivia.

## Library use

```python
from systembolaget import Client, build_query

with Client() as client:
    params = build_query(
        terms={"category": ["Vin"], "pairs-with": ["Grillat"]},
        ranges={"price": "120-180", "body": "8-12"},
    )
    for product in client.iter_products(params, limit=10):
        print(product["productNumber"], product["productNameBold"])
```

## Agent skill

`.claude/skills/systembolaget/SKILL.md` teaches Claude Code to drive this CLI,
including how to translate Swedish taste vocabulary into filters.

## Development

```bash
uv run pytest
```

Tests mock the HTTP layer with `respx` and make no network calls.

## Notes

The API is undocumented and reverse-engineered from the website. It ignores
unrecognised parameters rather than rejecting them, so filters are validated
client-side before being sent. Please keep request rates polite; the default
is one request per 100 ms.
