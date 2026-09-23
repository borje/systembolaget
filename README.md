# systembolaget

Ask Claude Code about drinks, and let it search Systembolaget's whole catalogue
(~27 000 products) and cross-check the answers against Vivino.

The recommended way to use this repo is as an **agent skill**: install the two
CLIs, open Claude Code in this directory, and ask in plain Swedish or English.
The `sb` and `vivino` CLIs exist to make that possible; you can drive them by
hand too, but the point is to let the agent do it.

## Using it as an agent skill

```bash
uv tool install .   # puts `sb` and `vivino` on your PATH
claude              # start Claude Code in this directory
```

`.claude/skills/systembolaget/SKILL.md` and `.claude/skills/vivino/SKILL.md`
are picked up automatically. They teach Claude how to translate Swedish taste
vocabulary (*fylligt*, *strävt*, *friskt*, *rökigt*, ...) into Systembolaget's
twelve-point taste clocks, which filter values the API actually accepts, how to
find drinks that taste like a given one, and how to read Vivino's rating fields
without being fooled by a thin vintage rating.

### Things you can ask that the website can't answer

The site lets you tick a few filters and scroll. An agent with these tools can
combine filters freely, compute over the results, compare across sources and
explain why it picked something.

**Taste, described in words**

- "Ett fylligt, strävt rött till grillat mellan 120 och 180 kr."
- "Ett torrt vitt med hög syra från Frankrike eller Tyskland, gärna under 150 kr."
- "Den rökigaste whiskyn under 700 kr."
- "Ett lätt, friskt rött som går att servera lite kylt."
- "En riktigt besk IPA, sorterad på pris."

**Similarity**

- "Hitta något som smakar som artikel 262708 men kostar under 120 kr."
- "Vilka viner har exakt samma smakprofil som den här Barolon?"
- "Något som liknar det här rödvinet, men det får gärna vara en portvin
  eller något annat helt — bara smaken stämmer."
- "Vi gillade det här vinet, vilka andra passar till samma mat och smakar
  likadant?"

**Cross-checking with Vivino**

- "Ta fram tio Nebbiolo under 250 kr och kolla vilka som har över 4,0 på Vivino."
- "Vilket av de här tre vinerna får bäst betyg på Vivino, och hur många
  har betygsatt dem?"
- "Bästa Vivino-betyg per krona bland Rioja på Systembolaget."
- "Är det här boxvinet något att ha enligt Vivino, eller finns det ett
  bättre i samma prisklass?"

**Counting, comparing and ranking**

- "Hur många rödviner passar till vilt, och hur fördelar de sig per land?"
- "Vilket land har flest ekologiska viner under 100 kr?"
- "Billigaste flaskan per land bland vita viner med hög syra."
- "Vilken druva dominerar bland fylliga röda från Spanien?"
- "Jämför medelpriset på Champagne och Cava i sortimentet."
- "Lista alla ölstilar som finns och hur många öl det finns i varje."

**Constraints the site doesn't expose together**

- "Alkoholfritt som passar till fisk, under 40 kr."
- "Ekologiskt vin i box med lägre klimatpåverkan."
- "Något sött till dessert som inte är portvin och håller under 15 %."
- "Ett rött med under 3 g/l socker och minst 14 % alkohol."

**Full records and exports**

- "Berätta allt om artikel 262708: druvor, producent, klimat, näringsvärden."
- "Exportera alla viner från Portugal till en CSV jag kan öppna i Excel."
- "Ge mig hela sortimentet av whisky som JSON."

Each of these turns into one or a handful of `sb`/`vivino` calls that the
agent composes, runs and summarises. The sections below document the CLIs
themselves for when you want to run them directly.

## The `sb` CLI

A Python CLI for searching Systembolaget's catalogue through the same public
REST API that systembolaget.se uses in the browser. No account and no API key:
the subscription key the site ships publicly is built in, and can be overridden
with `SYSTEMBOLAGET_API_KEY` if it rotates.

Working on the code instead of installing? `uv run sb ...` runs the CLI
straight from the checkout — that's the form the examples below omit.

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

## The `vivino` CLI

`vivino search TEXT` / `vivino show VINTAGE_ID` / `vivino reviews WINE_ID`
look up ratings and reviews on Vivino, e.g. to check whether a Systembolaget
find is any good. No account or API key needed.

```bash
vivino search "Barolo Albe G.D. Vajra"
vivino show 160828241
vivino reviews 1100124 -n 5
```

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
