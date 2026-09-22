"""``vivino`` — look up wine ratings and reviews on Vivino from the command line."""

from __future__ import annotations

import json
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from .vivino_api import WINE_TYPES, ApiError, Client

app = typer.Typer(
    name="vivino",
    help="Search Vivino for wine ratings and reviews.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()
err_console = Console(stderr=True)


def _fail(message: str) -> None:
    err_console.print(f"[red]Error:[/red] {message}")
    raise typer.Exit(code=1)


def _matches(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return payload.get("matches", [])


@app.command()
def search(
    text: Annotated[str, typer.Argument(help="Free text: name, producer, grape, region.")],
    wine_type: Annotated[list[str] | None, typer.Option("--type", "-t",
        help=f"Repeatable: {', '.join(WINE_TYPES)}.")] = None,
    min_price: Annotated[float | None, typer.Option("--min-price")] = None,
    max_price: Annotated[float | None, typer.Option("--max-price")] = None,
    min_rating: Annotated[float, typer.Option("--min-rating", help="0-5.")] = 0.0,
    country: Annotated[str, typer.Option("--country", help="Market for price, e.g. se.")] = "se",
    currency: Annotated[str, typer.Option("--currency")] = "SEK",
    limit: Annotated[int, typer.Option("--limit", "-n")] = 10,
    fmt: Annotated[str, typer.Option("--format", "-f", help="table or json.")] = "table",
) -> None:
    """Search Vivino by name, producer, grape or region."""
    for t in wine_type or []:
        if t not in WINE_TYPES:
            _fail(f"--type must be one of: {', '.join(WINE_TYPES)}")

    with Client() as client:
        try:
            payload = client.explore(
                text,
                wine_types=wine_type,
                min_price=min_price,
                max_price=max_price,
                min_rating=min_rating,
                country_code=country,
                currency_code=currency,
            )
        except ApiError as exc:
            _fail(str(exc))
            return

    matches = _matches(payload)[:limit]
    if fmt == "json":
        print(json.dumps(matches, ensure_ascii=False, indent=2))
        return
    _print_matches(matches, title=f"{payload.get('records_matched', len(matches))} matches")


def _print_matches(matches: list[dict[str, Any]], *, title: str) -> None:
    if not matches:
        err_console.print("[yellow]No matches.[/yellow]")
        return
    table = Table(title=title, header_style="bold cyan", title_justify="left")
    for column, justify in (
        ("Vintage ID", "left"), ("Wine ID", "left"), ("Name", "left"),
        ("Winery", "left"), ("Region", "left"), ("Rating", "right"),
        ("Ratings", "right"), ("Price", "right"),
    ):
        table.add_column(column, justify=justify, overflow="fold")

    for match in matches:
        vintage = match.get("vintage", {})
        wine = vintage.get("wine", {})
        stats = vintage.get("statistics", {})
        price = (match.get("price") or {}).get("amount")
        table.add_row(
            str(vintage.get("id", "")),
            str(wine.get("id", "")),
            vintage.get("name", ""),
            wine.get("winery", {}).get("name", ""),
            wine.get("region", {}).get("name", ""),
            f"{stats.get('wine_ratings_average', ''):.2f}" if stats.get("wine_ratings_average") else "",
            str(stats.get("wine_ratings_count", "")),
            f"{price:.0f}" if price is not None else "",
        )
    console.print(table)


@app.command()
def show(
    vintage_id: Annotated[int, typer.Argument(help="Vintage id, from 'vivino search'.")],
    fmt: Annotated[str, typer.Option("--format", "-f", help="detail or json.")] = "detail",
) -> None:
    """Show a vintage's full detail record."""
    with Client() as client:
        try:
            vintage = client.vintage(vintage_id)
        except ApiError as exc:
            _fail(str(exc))
            return

    if fmt == "json":
        print(json.dumps(vintage, ensure_ascii=False, indent=2))
        return

    wine = vintage.get("wine", {})
    vintage_stats = vintage.get("statistics", {})
    wine_stats = wine.get("statistics", {})
    console.print(f"[bold cyan]{vintage.get('name', '')}[/bold cyan]")
    console.print(f"[dim]wine id {wine.get('id', '')} · vintage id {vintage_id}[/dim]\n")
    console.print(f"  [green]Winery:[/green] {wine.get('winery', {}).get('name', '')}")
    console.print(f"  [green]Region:[/green] {wine.get('region', {}).get('name', '')}")
    console.print(f"  [green]Wine rating:[/green] {wine_stats.get('ratings_average', '')} "
                   f"({wine_stats.get('ratings_count', 0)} ratings)")
    console.print(f"  [green]Vintage rating:[/green] {vintage_stats.get('ratings_average', '')} "
                   f"({vintage_stats.get('ratings_count', 0)} ratings)")
    taste = wine.get("taste") or {}
    if taste:
        console.print(f"  [green]Taste:[/green] {taste}")


@app.command()
def reviews(
    wine_id: Annotated[int, typer.Argument(help="Wine id (not vintage id) from 'vivino search'.")],
    limit: Annotated[int, typer.Option("--limit", "-n")] = 10,
    fmt: Annotated[str, typer.Option("--format", "-f", help="table or json.")] = "table",
) -> None:
    """List user reviews for a wine."""
    with Client() as client:
        try:
            items = client.reviews(wine_id, per_page=limit)
        except ApiError as exc:
            _fail(str(exc))
            return

    if fmt == "json":
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return

    if not items:
        err_console.print("[yellow]No reviews.[/yellow]")
        return
    for review in items:
        user = review.get("user", {}).get("alias", "")
        console.print(f"[bold cyan]{review.get('rating', '')}/5[/bold cyan] [dim]{user}[/dim]")
        if review.get("note"):
            console.print(f"  {review['note']}")
        console.print()


if __name__ == "__main__":
    app()
