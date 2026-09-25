"""Query construction, taste matching and whole-catalogue crawling."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from .api import Client
from .filters import (
    RANGE_FILTERS,
    TASTE_CLOCK_FIELDS,
    TASTE_CLOCKS,
    TERM_FILTERS,
    FilterError,
    parse_range,
)


@dataclass
class Query:
    """A search request assembled from validated filters."""

    params: dict[str, Any] = field(default_factory=dict)

    def add_term(self, name: str, values: Iterable[str]) -> Query:
        values = [v for v in values if v]
        if not values:
            return self
        try:
            spec = TERM_FILTERS[name]
        except KeyError as exc:
            raise FilterError(f"Unknown filter {name!r}") from exc
        existing = self.params.setdefault(spec.param, [])
        existing.extend(values)
        return self

    def add_range(self, name: str, spec: str) -> Query:
        try:
            rf = RANGE_FILTERS[name]
        except KeyError as exc:
            raise FilterError(f"Unknown range filter {name!r}") from exc
        low, high = parse_range(spec, rf)
        self.params.update(rf.render(low, high))
        return self

    def add_bounds(self, name: str, low: float | None, high: float | None) -> Query:
        rf = RANGE_FILTERS[name]
        self.params.update(rf.render(low, high))
        return self

    def set(self, key: str, value: Any) -> Query:
        if value is not None:
            self.params[key] = value
        return self

    def build(self) -> dict[str, Any]:
        return dict(self.params)


def build_query(
    *,
    text: str | None = None,
    terms: dict[str, Iterable[str]] | None = None,
    ranges: dict[str, str] | None = None,
    sort_by: str | None = None,
    sort_direction: str | None = None,
) -> dict[str, Any]:
    """Assemble a validated query parameter dict."""
    query = Query()
    if text:
        query.set("textQuery", text)
    for name, values in (terms or {}).items():
        query.add_term(name, values)
    for name, spec in (ranges or {}).items():
        if spec:
            query.add_range(name, spec)
    query.set("sortBy", sort_by)
    query.set("sortDirection", sort_direction)
    return query.build()


# -- taste similarity ------------------------------------------------------


def taste_profile(product: dict[str, Any]) -> dict[str, int]:
    """Extract the taste clock values a product actually declares.

    Search results and detail records disagree on shape — the detail endpoint
    uses ``null`` where the search endpoint uses ``0`` — so an absent clock and
    a genuine zero are treated alike: both mean "nothing to match on".
    """
    profile: dict[str, int] = {}

    for clock in product.get("tasteClocks") or []:
        key = clock.get("key", "")
        value = clock.get("value")
        for name, rf in TASTE_CLOCKS.items():
            if key.lower() == rf.param.lower() and value:
                profile[name] = int(value)

    for name, field_name in TASTE_CLOCK_FIELDS.items():
        if name in profile:
            continue
        value = product.get(field_name)
        if value:
            profile[name] = int(value)

    return profile


def similar_query(
    product: dict[str, Any],
    *,
    tolerance: int = 1,
    match_category: bool = True,
    match_pairings: bool = False,
) -> dict[str, Any]:
    """Build a query for drinks that taste like *product*.

    Each declared taste clock becomes a window of ``±tolerance`` around the
    reference value.  Widening the tolerance trades precision for recall; a
    tolerance of 0 demands an exact profile match.
    """
    profile = taste_profile(product)
    if not profile:
        raise FilterError(
            "That product has no taste clock data, so there is nothing to "
            "match against. Try 'sb search' with explicit filters instead."
        )

    query = Query()
    for name, value in profile.items():
        low = max(0, value - tolerance)
        high = min(12, value + tolerance)
        query.add_bounds(name, low, high)

    if match_category:
        # Level 2 ("Rött vin") keeps results recognisable; level 1 alone is too
        # broad to be useful and level 3 usually collapses the result set.
        for key, filter_name in (
            ("categoryLevel2", "subcategory"),
            ("categoryLevel1", "category"),
        ):
            value = product.get(key)
            if value:
                query.add_term(filter_name, [value])
                break

    if match_pairings:
        symbols = _pairings(product)
        if symbols:
            query.add_term("pairs-with", symbols)

    return query.build()


def _pairings(product: dict[str, Any]) -> list[str]:
    """Food-pairing symbols, normalised across both response shapes."""
    symbols = product.get("tasteSymbolsList") or product.get("tasteSymbols") or []
    if isinstance(symbols, str):
        return [s.strip() for s in symbols.split(";") if s.strip()]
    return [str(s) for s in symbols]


def similarity_score(reference: dict[str, int], candidate: dict[str, int]) -> float:
    """Mean absolute distance between two taste profiles, in clock steps.

    Lower is closer.  Clocks the reference declares but the candidate does not
    count as a full 12-step miss, so a sparsely described product cannot beat a
    fully described one by simply having less to disagree about.
    """
    if not reference:
        return float("inf")
    total = sum(
        abs(value - candidate.get(name, value - 12)) for name, value in reference.items()
    )
    return total / len(reference)


def rank_by_similarity(
    reference: dict[str, Any], candidates: Iterable[dict[str, Any]]
) -> list[tuple[float, dict[str, Any]]]:
    """Order *candidates* by taste distance from *reference*, closest first."""
    profile = taste_profile(reference)
    reference_number = reference.get("productNumber")
    ranked = [
        (similarity_score(profile, taste_profile(candidate)), candidate)
        for candidate in candidates
        if candidate.get("productNumber") != reference_number
    ]
    ranked.sort(key=lambda pair: (pair[0], pair[1].get("productNameBold") or ""))
    return ranked


# -- dishes ----------------------------------------------------------------


def flatten_dishes(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn the grouped ``/v1/dishes/`` payload into one list of dishes.

    Each dish gains a ``dishGroupName`` key, and its name is tidied: the API
    serves some names with trailing spaces or soft hyphens.
    """
    dishes: list[dict[str, Any]] = []
    for group in groups:
        group_name = (group.get("dishGroupName") or "").strip()
        for dish in group.get("dishes") or []:
            dishes.append({
                **dish,
                "dishName": _clean(dish.get("dishName") or ""),
                "dishGroupName": group_name,
            })
    return dishes


def _clean(text: str) -> str:
    return text.replace("\xad", "").strip()


def find_dishes(dishes: list[dict[str, Any]], needle: str) -> list[dict[str, Any]]:
    """Dishes whose name or group contains *needle*, ignoring case."""
    key = _clean(needle).casefold()
    return [
        d for d in dishes
        if key in d["dishName"].casefold() or key in d["dishGroupName"].casefold()
    ]


def resolve_dish(dishes: list[dict[str, Any]], spec: str) -> dict[str, Any]:
    """Pick the one dish *spec* names — a ``dishId``, an exact name, or a
    name fragment that matches a single dish.
    """
    text = _clean(spec)
    if text.isdigit():
        for dish in dishes:
            if str(dish.get("dishId")) == text:
                return dish
        raise FilterError(f"Ingen maträtt har id {text}. Se 'sb dishes'.")

    exact = [d for d in dishes if d["dishName"].casefold() == text.casefold()]
    if len(exact) == 1:
        return exact[0]

    matches = exact or [d for d in dishes if text.casefold() in d["dishName"].casefold()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise FilterError(f"Ingen maträtt matchar {spec!r}. Se 'sb dishes'.")
    shown = ", ".join(f"{d['dishName']} ({d['dishId']})" for d in matches[:10])
    more = f" och {len(matches) - 10} till" if len(matches) > 10 else ""
    raise FilterError(f"{spec!r} matchar flera maträtter: {shown}{more}. Ange id.")


# -- whole catalogue crawling ---------------------------------------------

#: Bucket size below which paging stays reliable.  Beyond roughly this many
#: results the API starts dropping items from deep pages, so the crawler splits
#: instead of paging further.
SAFE_BUCKET = 600

#: Price bands (kr) used to split a bucket that is still too large after the
#: categorical splits are exhausted.  Chosen to spread the catalogue roughly
#: evenly rather than to be round numbers.
PRICE_BANDS: tuple[tuple[int | None, int | None], ...] = (
    (None, 80), (80, 110), (110, 140), (140, 180), (180, 230),
    (230, 300), (300, 450), (450, 800), (800, None),
)


def crawl_all(
    client: Client,
    base_params: dict[str, Any] | None = None,
    *,
    progress: Any = None,
) -> Iterator[dict[str, Any]]:
    """Yield every product matching *base_params*, de-duplicated.

    The API cannot simply be paged from start to finish: past roughly 30 pages
    it silently drops results, and past the final page it wraps around.  This
    recursively splits the query — by category, then country, then price band —
    until each bucket is small enough to page through reliably.
    """
    base_params = dict(base_params or {})
    seen: set[str] = set()

    splits = [
        ("categoryLevel1", "category"),
        ("categoryLevel2", "subcategory"),
        ("country", "country"),
    ]

    yield from _crawl_bucket(client, base_params, splits, seen, progress)


def _crawl_bucket(
    client: Client,
    params: dict[str, Any],
    splits: list[tuple[str, str]],
    seen: set[str],
    progress: Any,
) -> Iterator[dict[str, Any]]:
    total = client.count(params)
    if total == 0:
        return

    if total <= SAFE_BUCKET:
        yield from _drain(client, params, seen, progress)
        return

    if splits:
        param_name, _ = splits[0]
        values = _facet_values(client, params, param_name)
        if values:
            before = len(seen)
            for value in values:
                child = dict(params)
                child[param_name] = value
                yield from _crawl_bucket(client, child, splits[1:], seen, progress)
            # A facet cannot reach products whose field is empty, so the split
            # can leave a remainder.  Measure it against what the children
            # actually returned rather than against ``total``, which runs a
            # little ahead of what the API will hand back; re-paging the whole
            # bucket is only worth it when something is genuinely missing.
            if len(seen) - before < total:
                yield from _drain(client, params, seen, progress)
            return
        yield from _crawl_bucket(client, params, splits[1:], seen, progress)
        return

    if "price.min" not in params and "price.max" not in params:
        for low, high in PRICE_BANDS:
            child = dict(params)
            if low is not None:
                child["price.min"] = low
            if high is not None:
                child["price.max"] = high
            yield from _crawl_bucket(client, child, [], seen, progress)
        return

    # Nothing left to split on; page as deep as the API allows.
    yield from _drain(client, params, seen, progress)


def _drain(
    client: Client, params: dict[str, Any], seen: set[str], progress: Any
) -> Iterator[dict[str, Any]]:
    """Page through one bucket under several sort orders.

    Each sort order surfaces a slightly different slice of a large bucket, so
    unioning two of them recovers most of what deep paging drops.
    """
    for sort_by, direction in (("Name", "Ascending"), ("Price", "Descending")):
        query = dict(params, sortBy=sort_by, sortDirection=direction)
        new_in_pass = 0
        for product in client.iter_products(query):
            key = product.get("productNumber")
            if key in seen:
                continue
            seen.add(key)
            new_in_pass += 1
            if progress is not None:
                progress(product)
            yield product
        # A second pass only pays off when the first one hit the paging limit.
        if new_in_pass < 30:
            break


def _facet_values(client: Client, params: dict[str, Any], param_name: str) -> list[str]:
    """Distinct values of *param_name*, read from the API's own facet list."""
    if param_name in params:
        return []
    payload = client.search(params, page=1, size=1, include_filters=True)
    wanted = param_name.lower()
    for filter_spec in payload.get("filters") or []:
        if filter_spec.get("name", "").lower() != wanted:
            continue
        return [
            modifier["value"]
            for modifier in filter_spec.get("searchModifiers") or []
            if modifier.get("value")
        ]
    return _sampled_values(client, params, param_name)


def _sampled_values(client: Client, params: dict[str, Any], param_name: str) -> list[str]:
    """Fall back to sampling products when the API advertises no facet.

    Category levels 2 and up are filterable but are not always returned as
    facets, so their values have to be observed from the products themselves.
    """
    field_name = param_name[0].lower() + param_name[1:]
    values: set[str] = set()
    for sort_by in ("Name", "Price"):
        query = dict(params, sortBy=sort_by, sortDirection="Ascending")
        for product in client.iter_products(query, limit=300):
            value = product.get(field_name)
            if value:
                values.add(str(value))
    return sorted(values)
