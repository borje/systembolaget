"""Rendering search results as tables, JSON, NDJSON or CSV."""

from __future__ import annotations

import csv
import json
import sys
from collections.abc import Iterable, Sequence
from enum import StrEnum
from typing import Any

from rich.console import Console
from rich.table import Table

from .filters import TASTE_CLOCKS
from .search import taste_profile

console = Console()
err_console = Console(stderr=True)


class ResultFormat(StrEnum):
    table = "table"
    json = "json"
    ndjson = "ndjson"
    csv = "csv"


class TableFormat(StrEnum):
    table = "table"
    json = "json"


class DetailFormat(StrEnum):
    detail = "detail"
    json = "json"


class StoreFormat(StrEnum):
    table = "table"
    json = "json"
    ndjson = "ndjson"


class DumpFormat(StrEnum):
    ndjson = "ndjson"
    json = "json"
    csv = "csv"


def print_rows(output: Console, table: Table, rows: Iterable[Sequence[str]]) -> None:
    """Keep Rich tables on terminals, but write lossless text to pipes/files."""
    if output.is_terminal:
        for row in rows:
            table.add_row(*row)
        output.print(table)
        return
    if table.title:
        print(table.title, file=sys.stderr)
    writer = csv.writer(output.file, delimiter="\t", lineterminator="\n")
    writer.writerow([column.header for column in table.columns])
    writer.writerows(rows)

#: Columns shown by the default table view, as (header, product field).
TABLE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("Nr", "productNumber"),
    ("Namn", "_name"),
    ("Kategori", "_category"),
    ("Ursprung", "_origin"),
    ("Volym", "volumeText"),
    ("Pris", "_price"),
    ("Alk", "_alcohol"),
)

#: Extra columns for piped (agent) output, where width costs nothing.
TSV_COLUMNS: tuple[tuple[str, str], ...] = (
    ("Druvor", "_grapes"),
    ("Smak", "_taste"),
)


def product_name(product: dict[str, Any]) -> str:
    bold = (product.get("productNameBold") or "").strip()
    thin = (product.get("productNameThin") or "").strip()
    return f"{bold} {thin}".strip() or "(namnlös)"


def _category(product: dict[str, Any]) -> str:
    parts = [product.get("categoryLevel2"), product.get("categoryLevel3")]
    return ", ".join(p for p in parts if p) or (product.get("categoryLevel1") or "")


def _origin(product: dict[str, Any]) -> str:
    parts = [product.get("country"), product.get("originLevel1")]
    return ", ".join(p for p in parts if p)


def _price(product: dict[str, Any]) -> str:
    price = product.get("price")
    if price is None:
        price = product.get("priceInclVat")
    return f"{price:.2f}".rstrip("0").rstrip(".") + " kr" if price is not None else ""


def _alcohol(product: dict[str, Any]) -> str:
    value = product.get("alcoholPercentage")
    return f"{value:g}%" if value is not None else ""


def _grapes(product: dict[str, Any]) -> str:
    grapes = product.get("grapes") or []
    # Search results carry a list, detail records a ";"-joined string.
    if isinstance(grapes, str):
        grapes = [g for g in grapes.split(";") if g]
    return ", ".join(grapes)


def _taste(product: dict[str, Any]) -> str:
    return " ".join(f"{name}={value}" for name, value in taste_profile(product).items())


_DERIVED = {
    "_name": product_name,
    "_category": _category,
    "_origin": _origin,
    "_price": _price,
    "_alcohol": _alcohol,
    "_grapes": _grapes,
    "_taste": _taste,
}


def cell(product: dict[str, Any], field: str) -> str:
    if field in _DERIVED:
        return _DERIVED[field](product)
    value = product.get(field)
    return "" if value is None else str(value)


def print_table(
    products: Sequence[dict[str, Any]],
    *,
    title: str | None = None,
    scores: Sequence[float] | None = None,
) -> None:
    """Render products as a terminal table."""
    if not products:
        err_console.print("[yellow]Inga träffar.[/yellow]")
        return

    table = Table(title=title, header_style="bold cyan", title_justify="left")
    if scores is not None:
        table.add_column("Likhet", justify="right", style="magenta", no_wrap=True)
    # Names and categories are the only columns worth spending width on; the
    # rest are short enough that wrapping them just makes rows taller.
    widths = {"Namn": 34, "Kategori": 22, "Ursprung": 20}
    columns = TABLE_COLUMNS if console.is_terminal else TABLE_COLUMNS + TSV_COLUMNS
    for header, _ in columns:
        justify = "right" if header in ("Pris", "Alk", "Volym") else "left"
        table.add_column(
            header,
            justify=justify,
            max_width=widths.get(header),
            no_wrap=header not in widths,
            overflow="ellipsis",
        )

    rows = []
    for index, product in enumerate(products):
        row = [cell(product, field) for _, field in columns]
        if scores is not None:
            row.insert(0, f"{scores[index]:.2f}")
        rows.append(row)

    print_rows(console, table, rows)


def print_detail(product: dict[str, Any]) -> None:
    """Render one product's full record in readable sections."""
    console.print(f"[bold cyan]{product_name(product)}[/bold cyan]")
    number = product.get("productNumber", "")
    console.print(f"[dim]Artikelnummer {number}[/dim]\n")

    sections: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
        ("Grunduppgifter", (
            ("Kategori", "customCategoryTitle"),
            ("Sortiment", "assortmentText"),
            ("Pris", "_price"),
            ("Jämförpris", "comparisonPrice"),
            ("Volym", "volume"),
            ("Förpackning", "packagingLevel1"),
            ("Förslutning", "seal"),
            ("Alkoholhalt", "_alcohol"),
            ("Årgång", "vintage"),
        )),
        ("Ursprung", (
            ("Land", "country"),
            ("Region", "originLevel1"),
            ("Distrikt", "originLevel2"),
            ("Producent", "producerName"),
            ("Leverantör", "supplierName"),
        )),
        ("Smak", (
            ("Färg", "color"),
            ("Doft", "aroma"),
            ("Smak", "taste"),
            ("Användning", "usage"),
            ("Råvaror", "rawMaterial"),
            ("Passar till", "_pairings"),
        )),
        ("Bakgrund", (
            ("Producent", "producerDescription"),
            ("Odlingsområde", "cultivationArea"),
            ("Produktion", "production"),
            ("Skörd", "harvest"),
            ("Jordmån", "soil"),
            ("Visste du att", "didYouKnowInformation"),
        )),
    )

    for heading, fields in sections:
        rows = [(label, _detail_value(product, key)) for label, key in fields]
        rows = [(label, value) for label, value in rows if value]
        if not rows:
            continue
        console.print(f"[bold]{heading}[/bold]")
        for label, value in rows:
            console.print(f"  [green]{label}:[/green] {value}")
        console.print()

    profile = taste_profile(product)
    if profile:
        console.print("[bold]Smakklockor[/bold]")
        for name, value in profile.items():
            label = TASTE_CLOCKS[name].help
            bar = "█" * value + "░" * (12 - value)
            console.print(f"  [green]{label:<22}[/green] [cyan]{bar}[/cyan] {value}/12")
        console.print()

    flags = [
        label
        for label, key in (
            ("Ekologiskt", "isOrganic"),
            ("Veganskt", "isVeganFriendly"),
            ("Naturvin", "isNaturalWine"),
            ("Koscher", "isKosher"),
            ("Glutenfritt", "isGlutenFree"),
            ("Hållbart val", "isSustainableChoice"),
            ("Klimatsmart förpackning", "isClimateSmartPackaging"),
            ("Nyhet", "isNewInAssortment"),
            ("Slutsåld", "isCompletelyOutOfStock"),
            ("Utgående", "isDiscontinued"),
        )
        if product.get(key)
    ]
    if flags:
        console.print("[bold]Egenskaper[/bold]\n  " + ", ".join(flags) + "\n")

    stores = product.get("availableNumberOfStores")
    if stores:
        console.print(f"[dim]Finns i {stores} butiker[/dim]")
    console.print(
        f"[dim]https://www.systembolaget.se/produkt/{_slug(product)}/{number}/[/dim]"
    )


def _slug(product: dict[str, Any]) -> str:
    category = (product.get("categoryLevel1") or "").lower()
    return {"vin": "vin", "öl": "ol", "sprit": "sprit"}.get(category, "produkt")


def _detail_value(product: dict[str, Any], key: str) -> str:
    if key == "_pairings":
        symbols = product.get("tasteSymbolsList") or product.get("tasteSymbols") or []
        if isinstance(symbols, str):
            symbols = [s for s in symbols.split(";") if s]
        return ", ".join(symbols)
    if key == "comparisonPrice":
        value = product.get(key)
        return f"{value:g} kr/l" if value else ""
    if key == "volume":
        value = product.get(key)
        return f"{value:g} ml" if value else product.get("volumeText") or ""
    return cell(product, key)


# -- machine-readable output ----------------------------------------------


def strip_empty(product: dict[str, Any]) -> dict[str, Any]:
    """Drop null, empty and False fields; a missing key reads the same.  Keeps 0."""
    return {k: v for k, v in product.items() if v is not False and v not in (None, "", [], {})}


def dump_json(products: Iterable[dict[str, Any]], stream: Any = None) -> None:
    stream = stream or sys.stdout
    json.dump(list(products), stream, ensure_ascii=False, indent=2)
    stream.write("\n")


def dump_ndjson(products: Iterable[dict[str, Any]], stream: Any = None) -> int:
    """Write one JSON object per line.  Returns the number written."""
    stream = stream or sys.stdout
    count = 0
    for product in products:
        stream.write(json.dumps(product, ensure_ascii=False) + "\n")
        count += 1
    return count


#: Flat columns for CSV export, chosen to stay useful in a spreadsheet.
CSV_FIELDS: tuple[str, ...] = (
    "productNumber", "productNameBold", "productNameThin", "categoryLevel1",
    "categoryLevel2", "categoryLevel3", "country", "originLevel1", "originLevel2",
    "producerName", "vintage", "price", "volume", "alcoholPercentage",
    "assortmentText", "packagingLevel1", "seal", "isOrganic", "taste", "usage",
    "tasteClockBody", "tasteClockRoughness", "tasteClockFruitacid",
    "tasteClockSweetness", "tasteClockBitter", "tasteClockSmokiness",
)


def dump_csv(products: Iterable[dict[str, Any]], stream: Any = None) -> int:
    stream = stream or sys.stdout
    writer = csv.DictWriter(
        stream, fieldnames=list(CSV_FIELDS) + ["tasteSymbols"], extrasaction="ignore"
    )
    writer.writeheader()
    count = 0
    for product in products:
        row = {key: product.get(key) for key in CSV_FIELDS}
        symbols = product.get("tasteSymbolsList") or product.get("tasteSymbols") or []
        if isinstance(symbols, str):
            symbols = [s for s in symbols.split(";") if s]
        row["tasteSymbols"] = ";".join(symbols)
        writer.writerow(row)
        count += 1
    return count
