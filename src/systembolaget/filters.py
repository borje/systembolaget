"""Registry of every search filter the Systembolaget product API accepts.

The API silently ignores unknown parameters and malformed range values, so a
typo produces a full, unfiltered result set rather than an error.  Everything a
user can pass therefore goes through this registry first.

Two filter shapes exist:

``term``
    Repeatable exact-match parameters.  Repeating one ORs the values together
    (``country=Italien&country=Frankrike`` returns the union).

``range``
    Numeric bounds expressed with ``.min`` / ``.max`` suffixes.  Note that the
    more obvious ``price=100-200`` form is accepted by the server and then
    ignored, which is why ranges are rendered here and nowhere else.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TermFilter:
    """An exact-match, repeatable query parameter."""

    param: str
    help: str
    #: Known values, when the set is small and stable enough to be worth
    #: showing in ``--help``.  Empty means "open ended, discover via facets".
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class RangeFilter:
    """A numeric filter rendered as ``<param>.min`` / ``<param>.max``."""

    param: str
    help: str
    unit: str = ""
    #: Inclusive bounds for validation, when the scale is fixed.
    limits: tuple[float, float] | None = None

    def render(self, low: float | None, high: float | None) -> dict[str, str]:
        out: dict[str, str] = {}
        if low is not None:
            out[f"{self.param}.min"] = _num(low)
        if high is not None:
            out[f"{self.param}.max"] = _num(high)
        return out


def _num(value: float) -> str:
    """Render a bound without a trailing ``.0``, which the API prefers."""
    return str(int(value)) if float(value).is_integer() else str(value)


#: The twelve-segment "smakklocka" scales.  Systembolaget shows these as clocks
#: on the product page; the API exposes each one as an independent 0-12 range.
TASTE_CLOCKS: dict[str, RangeFilter] = {
    "body": RangeFilter("tasteClockBody", "Fyllighet (body)", limits=(0, 12)),
    "roughness": RangeFilter("tasteClockRoughness", "Strävhet (tannin)", limits=(0, 12)),
    "fruitacid": RangeFilter("tasteClockFruitacid", "Fruktsyra", limits=(0, 12)),
    "sweetness": RangeFilter("tasteClockSweetness", "Sötma", limits=(0, 12)),
    "bitterness": RangeFilter("tasteClockBitter", "Beska", limits=(0, 12)),
    "smokiness": RangeFilter("tasteClockSmokiness", "Rökighet", limits=(0, 12)),
    "casque": RangeFilter("tasteClockCasque", "Fatkaraktär", limits=(0, 12)),
}

#: Maps a taste clock to the field name carrying its value on a product record.
TASTE_CLOCK_FIELDS: dict[str, str] = {
    name: rf.param[0].lower() + rf.param[1:] for name, rf in TASTE_CLOCKS.items()
}

RANGE_FILTERS: dict[str, RangeFilter] = {
    "price": RangeFilter("price", "Pris", unit="kr"),
    "volume": RangeFilter("volume", "Volym", unit="ml"),
    "alcohol": RangeFilter("alcoholPercentage", "Alkoholhalt", unit="%", limits=(0, 100)),
    "sugar": RangeFilter("sugarContent", "Sockerhalt", unit="g/l"),
    "sugar-per-100ml": RangeFilter(
        "sugarContentGramPer100ml", "Sockerhalt", unit="g/100ml"
    ),
    **TASTE_CLOCKS,
}

#: "Passar till ..." — the food-pairing symbols printed on the product page.
TASTE_SYMBOLS: tuple[str, ...] = (
    "Grönsaker", "Fisk", "Fågel", "Lamm", "Fläsk", "Nöt", "Vilt", "Skaldjur",
    "Ost", "Pasta", "Pizza", "Grillat", "Hamburgare", "Kryddstarkt", "Asiatiskt",
    "Buffémat", "Snacks", "Dessert", "Aperitif", "Avec/digestif",
    "Drinkingrediens", "Sällskapsdryck",
)

TERM_FILTERS: dict[str, TermFilter] = {
    "category": TermFilter(
        "categoryLevel1", "Huvudkategori", ("Vin", "Öl", "Sprit", "Cider & blanddrycker", "Alkoholfritt")
    ),
    "subcategory": TermFilter("categoryLevel2", "Underkategori, t.ex. 'Rött vin', 'Whisky'"),
    "style": TermFilter("categoryLevel3", "Stil, t.ex. 'Fruktigt & Smakrikt'"),
    "subtype": TermFilter("categoryLevel4", "Ytterligare indelning"),
    "country": TermFilter("country", "Ursprungsland"),
    "region": TermFilter("originLevel1", "Region, t.ex. 'Toscana'"),
    "subregion": TermFilter("originLevel2", "Distrikt, t.ex. 'Chianti Classico'"),
    "producer": TermFilter("producerName", "Producent"),
    "grape": TermFilter("grapes", "Druva, t.ex. 'Nebbiolo'"),
    "pairs-with": TermFilter("tasteSymbols", "Passar till ...", TASTE_SYMBOLS),
    "vintage": TermFilter("vintage", "Årgång, t.ex. '2019'"),
    "assortment": TermFilter(
        "assortmentText",
        "Sortiment",
        ("Fast sortiment", "Tillfälligt sortiment", "Lokalt & Småskaligt",
         "Säsong", "Webblanseringar", "Ordervaror"),
    ),
    "packaging": TermFilter(
        "packagingLevel1",
        "Förpackning",
        ("Glasflaska", "Lättare glasflaska", "Box", "Burk", "PET-flaska",
         "Multipack", "Pappförpackning", "Påse"),
    ),
    "co2": TermFilter(
        "packagingCO2ImpactLevel",
        "Förpackningens klimatavtryck",
        ("Lägre", "Medel", "Högre"),
    ),
    "seal": TermFilter("seal", "Förslutning, t.ex. 'Skruvkapsyl'"),
    "label": TermFilter(
        "label", "Märkning", ("Ekologiskt", "Klimat, miljö, socialt ansvar")
    ),
    "ethical": TermFilter("ethicalLabel", "Etisk certifiering, t.ex. 'Fair for Life'"),
    "trait": TermFilter(
        "otherSelections", "Egenskap", ("Vegansk", "Naturvin", "Koscher")
    ),
    "oaked": TermFilter(
        "hasCasqueTaste", "Fatlagring", ("Fatlagrad", "Inte fatlagrad")
    ),
    "new": TermFilter(
        "newArrivalType",
        "Nyheter",
        ("Nytt senaste veckan", "Nytt senaste månaden", "Nytt senaste 3 månader", "Nyhet"),
    ),
}

#: ``sortBy`` values that demonstrably change the result order.  The API also
#: accepts ``AlcoholPercentage`` but ignores it, so it is deliberately absent.
SORT_FIELDS: tuple[str, ...] = (
    "Score", "Price", "Vintage", "Volume", "Name", "ProductLaunchDate",
)
SORT_DIRECTIONS: tuple[str, ...] = ("Ascending", "Descending", "Random")


class FilterError(ValueError):
    """Raised when a user-supplied filter cannot be rendered safely."""


def parse_range(spec: str, rf: RangeFilter) -> tuple[float | None, float | None]:
    """Parse a ``LOW-HIGH`` range spec, where either side may be omitted.

    Accepts ``100-200``, ``100-`` (no upper bound), ``-200`` (no lower bound)
    and a bare ``150`` (exact value).  Negative numbers are not meaningful for
    any Systembolaget range, so a leading ``-`` always means "up to".
    """
    text = spec.strip()
    if not text:
        raise FilterError(f"--{rf.param}: empty range")

    if "-" in text[1:] or text.startswith("-"):
        head, _, tail = text.partition("-") if not text.startswith("-") else ("", "-", text[1:])
        low = _bound(head, rf)
        high = _bound(tail, rf)
    else:
        low = high = _bound(text, rf)

    if low is not None and high is not None and low > high:
        raise FilterError(f"{rf.param}: lower bound {low} exceeds upper bound {high}")
    for value in (low, high):
        if value is None or rf.limits is None:
            continue
        lo, hi = rf.limits
        if not lo <= value <= hi:
            raise FilterError(f"{rf.param}: {value} outside valid range {lo}-{hi}")
    return low, high


def _bound(text: str, rf: RangeFilter) -> float | None:
    text = text.strip()
    if not text or text == "*":
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise FilterError(f"{rf.param}: {text!r} is not a number") from exc
