# Claude Château 🍷

Search Systembolaget's whole catalogue (~27 000 products) and cross-check wines
against Vivino, directly from the command line or with an AI agent. Ask in plain
Swedish or English; the agent can compose the `sb` and `vivino` calls for you.

## Using it as agent skills

From the repository root:

```bash
uv tool install .   # puts `sb` and `vivino` on your PATH
```

If the CLIs are not installed, run `uv run sb ...` or `uv run vivino ...` from
the repository root instead. The canonical agent-neutral skills are
[skills/systembolaget/SKILL.md](skills/systembolaget/SKILL.md) and
[skills/vivino/SKILL.md](skills/vivino/SKILL.md); [AGENTS.md](AGENTS.md) is the
short repository guide. They explain Swedish taste vocabulary, the twelve-point
taste clocks, valid filters, similarity queries, and Vivino's rating fields.

### Claude Code and Pi

Start `claude` in this directory: `.claude/skills/systembolaget` and
`.claude/skills/vivino` are relative symlinks to the canonical skills, preserving
Claude's discovery. Pi's `.pi/settings.json` points to `../skills`.

### Hermes Agent

Hermes does not automatically discover arbitrary repository skills. To install
these manually, run the following from this repository root. This creates links
only when no existing file, directory or symlink has that name:

```bash
repo="$PWD"
skill_dir="${HERMES_HOME:-$HOME/.hermes}/skills"
mkdir -p "$skill_dir"
for name in systembolaget vivino; do
  target="$skill_dir/$name"
  if [ -e "$target" ] || [ -L "$target" ]; then
    printf 'Skipping existing skill: %s\n' "$target"
  else
    ln -s "$repo/skills/$name" "$target"
  fi
done
hermes skills list
hermes -s systembolaget -s vivino
```

For a named profile, set `HERMES_HOME` to that profile's home (for example
`$HOME/.hermes/profiles/wine`) before installing, then launch with
`hermes --profile wine -s systembolaget -s vivino`. In an existing Hermes session,
use `/reload-skills`, then `/skill systembolaget` or `/skill vivino`.
Keep the checkout in place while these symlinks are installed.

### Things you can ask that the website can't answer

The site lets you tick a few filters and scroll. An agent with these tools can
combine filters freely, compute over the results, compare across sources and
explain why it picked something.

**Food pairing, with the wine you actually want**

- "Vilket rödvin från Italien passar till lamm och rostade rotfrukter?"
- "Vilket vitt vin från Portugal passar till skaldjur och fisk, under 130 kr?"
- "Ett spanskt rött till tacos och kryddstark mat, gärna lite fruktigt."
- "Vilken öl passar till både pizza och hamburgare, och kostar under 30 kr?"
- "Ett fylligt, strävt rött från Frankrike till grillat och ost, mellan 120
  och 180 kr."
- "Ett torrt vitt med hög syra från Tyskland till asiatiskt."
- "Den rökigaste whiskyn under 700 kr."

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

- "Alkoholfritt från Sverige som passar till fisk, under 40 kr."
- "Ekologiskt rött i box från Chile eller Argentina till vilt."
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
sb dishes [QUERY]            # dishes with curated drink lists
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

### Searching by dish

Systembolaget's "Vad passar till?" matcher keeps a curated drink list for
716 dishes, each with a short note on why the pairing works. `sb dishes`
searches them, and `--dish` narrows any search to a dish's list:

```bash
sb dishes bourguignon        # id, group and pairing note
sb search --dish "Boeuf bourguignon" --subcategory "Rött vin" --price -200
```

`--dish` takes an id, an exact name, or any fragment that matches one dish.

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

Pick with `--format` / `-f`. Defaults: table, except `show` (detail) and
`sb dump` (ndjson). Unsupported values are rejected before API calls.

Supported formats:
- `sb search`, `like`, `random`: table, json, ndjson, csv.
- `sb show`: detail, json.
- `sb stock`, `dishes`, `facets`: table, json.
- `sb stores`: table, json, ndjson.
- `sb dump`: ndjson, json, csv (choose `-o` yourself; the filename is not changed).
- `vivino search`, `reviews`: table, json; `vivino show`: detail, json.

Interactive table views use Rich. In non-TTY output (pipes, files, agent capture),
table views write only tab-separated headers and rows to stdout (titles and hints go to stderr):
full names, Unicode, literal markup-looking text and IDs are not truncated or
wrapped, and similarity scores remain included. Fields containing tabs/newlines
are CSV-quoted; this remains table-like text, not an automatic switch to JSON.
Prefer `-f json` and bound results with `-n` for agent parsing.

Search results carry ~70 fields; `sb show` and `sb search --full` fetch the complete
~137-field record, adding aroma, raw materials, producer and terroir prose,
nutrition tables and trivia. Product json/ndjson omits null, empty and false
fields (zeros are kept); csv keeps every column.

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
uv run pytest -q
uv run ruff check .
```

Tests mock the HTTP layer with `respx` and make no network calls.

## Notes

The API is undocumented and reverse-engineered from the website. It ignores
unrecognised parameters rather than rejecting them, so filters are validated
client-side before being sent. Please keep request rates polite; the default
is one request per 100 ms.

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).
