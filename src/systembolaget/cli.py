"""``sb`` — search Systembolaget's catalogue from the command line."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

from .api import ApiError, Client
from .filters import (
    RANGE_FILTERS,
    SORT_FIELDS,
    TASTE_SYMBOLS,
    TERM_FILTERS,
    FilterError,
)
from .format import (
    console,
    dump_csv,
    dump_json,
    dump_ndjson,
    err_console,
    print_detail,
    print_table,
    product_name,
)
from .search import (
    build_query,
    crawl_all,
    rank_by_similarity,
    similar_query,
    taste_profile,
)

app = typer.Typer(
    name="sb",
    help="Sök och lista drycker från Systembolaget via deras publika API.",
    no_args_is_help=True,
    add_completion=False,
)

Format = str


def _client(ctx: typer.Context) -> Client:
    options = ctx.obj or {}
    return Client(rate_limit=options.get("rate_limit", 0.1))


def _emit(products: list[dict[str, Any]], fmt: str, *, title: str | None = None,
          scores: list[float] | None = None) -> None:
    """Render a result set in the requested format."""
    if fmt == "json":
        dump_json(products)
    elif fmt == "ndjson":
        dump_ndjson(products)
    elif fmt == "csv":
        dump_csv(products)
    else:
        print_table(products, title=title, scores=scores)


def _fail(message: str) -> None:
    err_console.print(f"[red]Fel:[/red] {message}")
    raise typer.Exit(code=1)


@app.callback()
def main(
    ctx: typer.Context,
    rate_limit: Annotated[float, typer.Option(
        "--rate-limit", help="Minsta tid i sekunder mellan anrop.")] = 0.1,
) -> None:
    ctx.obj = {"rate_limit": rate_limit}


@app.command()
def search(
    ctx: typer.Context,
    text: Annotated[Optional[str], typer.Argument(
        help="Fritext, t.ex. namn, producent eller druva.")] = None,
    # Categorical filters
    category: Annotated[Optional[list[str]], typer.Option("--category", "-c",
        help="Vin, Öl, Sprit, Cider & blanddrycker, Alkoholfritt.")] = None,
    subcategory: Annotated[Optional[list[str]], typer.Option("--subcategory",
        help="T.ex. 'Rött vin', 'Whisky', 'IPA'.")] = None,
    style: Annotated[Optional[list[str]], typer.Option("--style",
        help="T.ex. 'Fruktigt & Smakrikt'.")] = None,
    country: Annotated[Optional[list[str]], typer.Option("--country",
        help="Ursprungsland.")] = None,
    region: Annotated[Optional[list[str]], typer.Option("--region",
        help="Region, t.ex. 'Toscana'.")] = None,
    producer: Annotated[Optional[list[str]], typer.Option("--producer", help="Producent.")] = None,
    grape: Annotated[Optional[list[str]], typer.Option("--grape",
        help="Druva, t.ex. 'Nebbiolo'.")] = None,
    pairs_with: Annotated[Optional[list[str]], typer.Option("--pairs-with", "-p",
        help="Passar till, t.ex. 'Grillat'. Se 'sb pairings'.")] = None,
    vintage: Annotated[Optional[list[str]], typer.Option("--vintage", help="Årgång.")] = None,
    assortment: Annotated[Optional[list[str]], typer.Option("--assortment",
        help="T.ex. 'Fast sortiment'.")] = None,
    packaging: Annotated[Optional[list[str]], typer.Option("--packaging",
        help="T.ex. 'Box', 'Burk'.")] = None,
    seal: Annotated[Optional[list[str]], typer.Option("--seal",
        help="Förslutning, t.ex. 'Skruvkapsyl'.")] = None,
    trait: Annotated[Optional[list[str]], typer.Option("--trait",
        help="Vegansk, Naturvin eller Koscher.")] = None,
    oaked: Annotated[Optional[str], typer.Option("--oaked",
        help="'Fatlagrad' eller 'Inte fatlagrad'.")] = None,
    organic: Annotated[bool, typer.Option("--organic", help="Endast ekologiskt.")] = False,
    new: Annotated[Optional[str], typer.Option("--new",
        help="T.ex. 'Nytt senaste månaden'.")] = None,
    co2: Annotated[Optional[str], typer.Option("--co2",
        help="Förpackningens klimatavtryck: Lägre, Medel, Högre.")] = None,
    # Numeric ranges
    price: Annotated[Optional[str], typer.Option("--price",
        help="Prisintervall i kr, t.ex. 100-200, 100- eller -150.")] = None,
    volume: Annotated[Optional[str], typer.Option("--volume", help="Volym i ml.")] = None,
    alcohol: Annotated[Optional[str], typer.Option("--alcohol",
        help="Alkoholhalt i procent, t.ex. 0-0.5.")] = None,
    sugar: Annotated[Optional[str], typer.Option("--sugar", help="Sockerhalt i g/l.")] = None,
    body: Annotated[Optional[str], typer.Option("--body", help="Fyllighet 0-12.")] = None,
    roughness: Annotated[Optional[str], typer.Option("--roughness", help="Strävhet 0-12.")] = None,
    fruitacid: Annotated[Optional[str], typer.Option("--fruitacid", help="Fruktsyra 0-12.")] = None,
    sweetness: Annotated[Optional[str], typer.Option("--sweetness", help="Sötma 0-12.")] = None,
    bitterness: Annotated[Optional[str], typer.Option("--bitterness", help="Beska 0-12.")] = None,
    smokiness: Annotated[Optional[str], typer.Option("--smokiness", help="Rökighet 0-12.")] = None,
    # Output
    limit: Annotated[int, typer.Option("--limit", "-n", help="Antal träffar.")] = 20,
    sort_by: Annotated[str, typer.Option("--sort",
        help=f"Sortera på: {', '.join(SORT_FIELDS)}.")] = "Score",
    desc: Annotated[bool, typer.Option("--desc", help="Fallande sortering.")] = False,
    full: Annotated[bool, typer.Option("--full",
        help="Hämta hela produktposten för varje träff (långsammare).")] = False,
    fmt: Annotated[str, typer.Option("--format", "-f",
        help="table, json, ndjson eller csv.")] = "table",
    count_only: Annotated[bool, typer.Option("--count", help="Skriv bara antalet träffar.")] = False,
) -> None:
    """Sök drycker på valfri kombination av önskemål.

    Alla kategoriska flaggor kan upprepas och kombineras då med ELLER:
    ``--country Italien --country Frankrike`` ger båda länderna.
    """
    if sort_by not in SORT_FIELDS:
        _fail(f"--sort måste vara en av: {', '.join(SORT_FIELDS)}")

    labels = list(trait or [])
    terms: dict[str, list[str]] = {
        "category": category or [],
        "subcategory": subcategory or [],
        "style": style or [],
        "country": country or [],
        "region": region or [],
        "producer": producer or [],
        "grape": grape or [],
        "pairs-with": pairs_with or [],
        "vintage": vintage or [],
        "assortment": assortment or [],
        "packaging": packaging or [],
        "seal": seal or [],
        "trait": labels,
        "oaked": [oaked] if oaked else [],
        "new": [new] if new else [],
        "co2": [co2] if co2 else [],
        "label": ["Ekologiskt"] if organic else [],
    }
    ranges = {
        "price": price, "volume": volume, "alcohol": alcohol, "sugar": sugar,
        "body": body, "roughness": roughness, "fruitacid": fruitacid,
        "sweetness": sweetness, "bitterness": bitterness, "smokiness": smokiness,
    }

    try:
        params = build_query(
            text=text, terms=terms, ranges=ranges, sort_by=sort_by,
            sort_direction="Descending" if desc else "Ascending",
        )
    except FilterError as exc:
        _fail(str(exc))
        return

    with _client(ctx) as client:
        try:
            if count_only:
                console.print(client.count(params))
                return
            products = list(client.iter_products(params, limit=limit))
            if full:
                products = [_enrich(client, p) for p in products]
        except ApiError as exc:
            _fail(str(exc))
            return

    _emit(products, fmt, title=f"{len(products)} träffar")


def _enrich(client: Client, product: dict[str, Any]) -> dict[str, Any]:
    """Merge a search hit with its complete record, if it can be fetched.

    Neither record contains the other.  The full one adds raw materials,
    aroma, producer prose and nutrition, but drops ``price``, ``volumeText``
    and a few flags the search hit carries, and leaves some taste clocks null
    where the search hit has a number.  So the search hit is the base and only
    the full record's non-empty values are laid on top.
    """
    number = product.get("productNumber")
    if not number:
        return product
    try:
        full = client.product(number)
    except ApiError:
        return product
    merged = dict(product)
    merged.update({k: v for k, v in full.items() if v not in (None, "", [], {})})
    return merged


@app.command()
def show(
    ctx: typer.Context,
    product_number: Annotated[str, typer.Argument(help="Artikelnummer, t.ex. 262708.")],
    fmt: Annotated[str, typer.Option("--format", "-f", help="detail eller json.")] = "detail",
) -> None:
    """Visa allt som finns om en produkt."""
    with _client(ctx) as client:
        try:
            product = client.product(product_number)
        except ApiError as exc:
            _fail(str(exc))
            return
    if fmt == "json":
        dump_json([product])
    else:
        print_detail(product)


@app.command("like")
def like(
    ctx: typer.Context,
    product_number: Annotated[str, typer.Argument(help="Artikelnummer att utgå från.")],
    tolerance: Annotated[int, typer.Option("--tolerance", "-t",
        help="Hur mycket smakklockorna får avvika (0-6).")] = 1,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Antal förslag.")] = 20,
    price: Annotated[Optional[str], typer.Option("--price", help="Begränsa priset, t.ex. -200.")] = None,
    any_category: Annotated[bool, typer.Option("--any-category",
        help="Tillåt träffar utanför samma kategori.")] = False,
    match_pairings: Annotated[bool, typer.Option("--match-pairings",
        help="Kräv dessutom samma 'passar till'-symboler.")] = False,
    fmt: Annotated[str, typer.Option("--format", "-f", help="table, json, ndjson, csv.")] = "table",
) -> None:
    """Hitta drycker med liknande smak som en given produkt.

    Utgår från produktens smakklockor och söker andra drycker vars klockor
    ligger inom ±tolerans, sorterade efter hur nära de ligger.
    """
    if not 0 <= tolerance <= 6:
        _fail("--tolerance måste vara mellan 0 och 6")

    with _client(ctx) as client:
        try:
            reference = client.product(product_number)
        except ApiError as exc:
            _fail(str(exc))
            return

        try:
            params = similar_query(
                reference,
                tolerance=tolerance,
                match_category=not any_category,
                match_pairings=match_pairings,
            )
            if price:
                params.update(_price_bounds(price))
        except FilterError as exc:
            _fail(str(exc))
            return

        # Over-fetch so the ranking has candidates to choose between.
        candidates = list(client.iter_products(params, limit=max(limit * 5, 100)))

    ranked = rank_by_similarity(reference, candidates)[:limit]
    profile = ", ".join(f"{k} {v}" for k, v in taste_profile(reference).items())

    if fmt == "table":
        console.print(
            f"Liknar [bold cyan]{product_name(reference)}[/bold cyan] "
            f"[dim]({profile})[/dim]\n"
        )
    _emit(
        [product for _, product in ranked],
        fmt,
        title=f"{len(ranked)} liknande drycker",
        scores=[score for score, _ in ranked] if fmt == "table" else None,
    )


def _price_bounds(spec: str) -> dict[str, str]:
    from .filters import parse_range

    low, high = parse_range(spec, RANGE_FILTERS["price"])
    return RANGE_FILTERS["price"].render(low, high)


@app.command()
def pairings() -> None:
    """Lista alla 'passar till'-alternativ som går att söka på."""
    console.print("[bold cyan]Passar till[/bold cyan]")
    for symbol in sorted(TASTE_SYMBOLS):
        console.print(f"  {symbol}")
    console.print("\n[dim]Använd med: sb search --pairs-with Grillat[/dim]")


@app.command()
def facets(
    ctx: typer.Context,
    field: Annotated[Optional[str], typer.Argument(
        help="Filternamn, t.ex. country, grape, subcategory. Utelämna för lista.")] = None,
    category: Annotated[Optional[list[str]], typer.Option("--category", "-c",
        help="Begränsa till en kategori.")] = None,
    text: Annotated[Optional[str], typer.Option("--text", help="Begränsa till en fritextsökning.")] = None,
) -> None:
    """Visa vilka värden ett filter kan ta, för det aktuella urvalet.

    Utan argument listas alla tillgängliga filter.
    """
    if field is None:
        console.print("[bold cyan]Kategoriska filter[/bold cyan] (kan upprepas)")
        for name, spec in TERM_FILTERS.items():
            values = f" — {', '.join(spec.values)}" if spec.values else ""
            console.print(f"  [green]{name:<14}[/green] {spec.help}{values}")
        console.print("\n[bold cyan]Intervallfilter[/bold cyan] (t.ex. 100-200, 100-, -200)")
        for name, spec in RANGE_FILTERS.items():
            unit = f" [{spec.unit}]" if spec.unit else ""
            console.print(f"  [green]{name:<14}[/green] {spec.help}{unit}")
        return

    spec = TERM_FILTERS.get(field)
    if spec is None:
        _fail(f"Okänt filter {field!r}. Kör 'sb facets' för listan.")
        return

    params = build_query(text=text, terms={"category": category or []})
    with _client(ctx) as client:
        try:
            payload = client.search(params, page=1, size=1, include_filters=True)
        except ApiError as exc:
            _fail(str(exc))
            return

    wanted = spec.param.lower()
    for filter_spec in payload.get("filters") or []:
        if filter_spec.get("name", "").lower() != wanted:
            continue
        modifiers = filter_spec.get("searchModifiers") or []
        console.print(f"[bold cyan]{filter_spec.get('displayName') or field}[/bold cyan]")
        for modifier in modifiers:
            count = modifier.get("count")
            suffix = f" [dim]({count})[/dim]" if count else ""
            console.print(f"  {modifier.get('value')}{suffix}")
        console.print(f"\n[dim]{len(modifiers)} värden[/dim]")
        return

    if spec.values:
        console.print(f"[bold cyan]{field}[/bold cyan] [dim](kända värden)[/dim]")
        for value in spec.values:
            console.print(f"  {value}")
        return
    _fail(
        f"API:et redovisar inga värden för {field!r} i det här urvalet. "
        "Prova att begränsa med --category."
    )


@app.command()
def stores(
    ctx: typer.Context,
    city: Annotated[Optional[str], typer.Option("--city", help="Filtrera på ort.")] = None,
    fmt: Annotated[str, typer.Option("--format", "-f", help="table, json, ndjson.")] = "table",
) -> None:
    """Lista Systembolagets butiker och ombud."""
    with _client(ctx) as client:
        try:
            sites = client.stores()
        except ApiError as exc:
            _fail(str(exc))
            return

    if city:
        needle = city.casefold()
        sites = [s for s in sites if needle in (s.get("city") or "").casefold()]

    if fmt == "json":
        dump_json(sites)
        return
    if fmt == "ndjson":
        dump_ndjson(sites)
        return

    from rich.table import Table

    table = Table(title=f"{len(sites)} butiker", header_style="bold cyan")
    for column in ("Nr", "Namn", "Adress", "Ort", "Län", "Typ"):
        table.add_column(column, overflow="fold")
    for site in sites:
        table.add_row(
            site.get("siteId") or "",
            site.get("displayName") or site.get("alias") or "",
            site.get("streetAddress") or "",
            site.get("city") or "",
            site.get("county") or "",
            "Ombud" if site.get("isAgent") else "Butik",
        )
    console.print(table)


@app.command()
def dump(
    ctx: typer.Context,
    output: Annotated[Path, typer.Option("--output", "-o",
        help="Fil att skriva till. '-' för stdout.")] = Path("systembolaget.ndjson"),
    category: Annotated[Optional[list[str]], typer.Option("--category", "-c",
        help="Begränsa till en kategori.")] = None,
    fmt: Annotated[str, typer.Option("--format", "-f", help="ndjson, json eller csv.")] = "ndjson",
    limit: Annotated[Optional[int], typer.Option("--limit", "-n",
        help="Sluta efter N produkter (för test).")] = None,
) -> None:
    """Ladda ner hela sortimentet med fullständiga produktposter.

    Söktjänsten tappar träffar på djupa sidor, så katalogen hämtas genom att
    dela upp sökningen i mindre delmängder (kategori, land, prisintervall) som
    var för sig går att bläddra igenom tillförlitligt. Dubbletter filtreras
    bort, så resultatet kan innehålla något färre poster än API:ets egen
    räknare anger.

    Varje träff slås sedan upp på produkt-endpointen, eftersom söksvaret bara
    bär ~70 av produktens ~137 fält: råvaror, aroma, producent- och
    terroirtexter, näringsvärden och kuriosa finns bara i den fulla posten.
    Det kostar ett anrop per produkt, så en full katalog tar timmar. Begränsa
    med --category eller --limit när du inte behöver allt.
    """
    params = build_query(terms={"category": category or []})
    written = 0

    def report(_product: dict[str, Any]) -> None:
        nonlocal written
        written += 1
        if written % 250 == 0:
            err_console.print(f"[dim]… {written} produkter[/dim]")

    with _client(ctx) as client:
        try:
            expected = client.count(params)
            err_console.print(f"[cyan]API:et anger {expected} produkter.[/cyan]")

            stream = sys.stdout if str(output) == "-" else output.open("w", encoding="utf-8")
            try:
                products = crawl_all(client, params, progress=report)
                if limit is not None:
                    products = _take(products, limit)
                products = (_enrich(client, p) for p in products)

                if fmt == "ndjson":
                    total = dump_ndjson(products, stream)
                elif fmt == "csv":
                    total = dump_csv(products, stream)
                else:
                    collected = list(products)
                    dump_json(collected, stream)
                    total = len(collected)
            finally:
                if stream is not sys.stdout:
                    stream.close()
        except ApiError as exc:
            _fail(str(exc))
            return

    where = "stdout" if str(output) == "-" else str(output)
    err_console.print(
        f"[green]Klart:[/green] {total} produkter till {where} "
        f"[dim](API:et angav {expected})[/dim]"
    )


def _take(iterable: Any, count: int) -> Any:
    for index, item in enumerate(iterable):
        if index >= count:
            return
        yield item


@app.command()
def random(
    ctx: typer.Context,
    category: Annotated[Optional[list[str]], typer.Option("--category", "-c",
        help="Begränsa till en kategori.")] = None,
    pairs_with: Annotated[Optional[list[str]], typer.Option("--pairs-with", "-p",
        help="Passar till.")] = None,
    price: Annotated[Optional[str], typer.Option("--price", help="Prisintervall.")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Antal förslag.")] = 5,
) -> None:
    """Slumpa fram förslag — för när man inte vet vad man vill ha."""
    try:
        params = build_query(
            terms={"category": category or [], "pairs-with": pairs_with or []},
            ranges={"price": price} if price else None,
            sort_direction="Random",
        )
    except FilterError as exc:
        _fail(str(exc))
        return

    with _client(ctx) as client:
        try:
            products = list(client.iter_products(params, limit=limit))
        except ApiError as exc:
            _fail(str(exc))
            return
    print_table(products, title="Slumpade förslag")


if __name__ == "__main__":
    app()
