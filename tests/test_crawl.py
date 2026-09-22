"""Tests for the whole-catalogue crawler.

The crawler exists to work around two quirks of the search endpoint: it drops
results on deep pages, and a facet split cannot reach products whose split
field is empty.  These tests pin down both behaviours with a fake API.
"""

from typing import Any

from systembolaget.api import MAX_PAGE_SIZE, Client
from systembolaget.search import SAFE_BUCKET, crawl_all

#: The crawler only pages a bucket once it is down to ``SAFE_BUCKET`` items, so
#: a fake that truncates earlier than that would fail by construction.  Tests
#: give the fake exactly the page budget the crawler assumes it has.
PAGE_LIMIT = SAFE_BUCKET // MAX_PAGE_SIZE


class FakeApi:
    """An in-memory stand-in for the search endpoint.

    Products are plain dicts.  ``page_limit`` mimics the real service dropping
    everything past a certain page, so a bucket that is too large to page
    through loses its tail unless the crawler splits it first.
    """

    def __init__(self, products: list[dict[str, Any]], *, page_limit: int | None = None):
        self.products = products
        self.page_limit = page_limit
        self.requests: list[dict[str, Any]] = []

    def matching(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        results = []
        for product in self.products:
            for key, value in params.items():
                if key in ("page", "size", "sortBy", "sortDirection",
                           "excludeFilterMetadata"):
                    continue
                if key == "price.min" and product.get("price", 0) < value:
                    break
                if key == "price.max" and product.get("price", 0) >= value:
                    break
                if key in ("price.min", "price.max"):
                    continue
                wanted = value if isinstance(value, list) else [value]
                if product.get(key) not in wanted:
                    break
            else:
                results.append(product)
        return results

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        params = dict(params or {})
        self.requests.append(params)
        page = params.pop("page", 1)
        size = params.pop("size", 30)
        include_filters = not params.pop("excludeFilterMetadata", None)
        params.pop("sortBy", None)
        params.pop("sortDirection", None)

        results = self.matching(params)
        if self.page_limit is not None and page > self.page_limit:
            window: list[dict[str, Any]] = []
        else:
            window = results[(page - 1) * size: page * size]

        payload: dict[str, Any] = {
            "metadata": {"docCount": len(results)},
            "products": window,
        }
        if include_filters:
            # Facets are named in PascalCase but the matching product field is
            # camelCase, exactly as the real API does it.
            payload["filters"] = [
                {
                    "name": name,
                    "searchModifiers": [
                        {"value": v} for v in sorted(
                            {p[field] for p in results if p.get(field)}
                        )
                    ],
                }
                for name, field in (
                    ("CategoryLevel1", "categoryLevel1"),
                    ("CategoryLevel2", "categoryLevel2"),
                    ("Country", "country"),
                )
            ]
        return payload


def make_client(api: FakeApi) -> Client:
    client = Client(rate_limit=0)
    client.get = api.get  # type: ignore[method-assign]
    return client


def product(number: int, **fields: Any) -> dict[str, Any]:
    base = {
        "productNumber": str(number),
        "categoryLevel1": "Vin",
        "categoryLevel2": "Rött vin",
        "country": "Italien",
        "price": 100,
    }
    base.update(fields)
    return base


def test_small_catalogue_is_returned_whole():
    api = FakeApi([product(i) for i in range(10)])
    got = list(crawl_all(make_client(api)))
    assert len(got) == 10


def test_results_are_deduplicated():
    """The same product reachable from two buckets is yielded once."""
    api = FakeApi([product(i) for i in range(10)])
    numbers = [p["productNumber"] for p in crawl_all(make_client(api))]
    assert len(numbers) == len(set(numbers))


def test_large_bucket_is_split_so_nothing_is_lost():
    """Without splitting, the page limit would truncate this catalogue."""
    products = [
        product(i, categoryLevel1=("Vin" if i % 2 else "Öl"),
                categoryLevel2=f"Sub{i % 4}", country=f"Land{i % 5}")
        for i in range(SAFE_BUCKET * 2)
    ]
    # The catalogue is twice what a single bucket may page through, so a naive
    # crawl would stop halfway.
    api = FakeApi(products, page_limit=PAGE_LIMIT)
    got = {p["productNumber"] for p in crawl_all(make_client(api))}
    assert len(got) == len(products)


def test_products_missing_the_split_field_are_still_found():
    """A facet split cannot see products whose split field is empty."""
    products = [product(i, categoryLevel2=f"Sub{i % 3}") for i in range(SAFE_BUCKET + 50)]
    orphan = product(99999, categoryLevel2=None)
    api = FakeApi(products + [orphan])
    got = {p["productNumber"] for p in crawl_all(make_client(api))}
    assert "99999" in got
    assert len(got) == len(products) + 1


def test_base_params_constrain_the_crawl():
    products = [product(i, categoryLevel1="Vin") for i in range(5)]
    products += [product(100 + i, categoryLevel1="Öl") for i in range(5)]
    api = FakeApi(products)
    got = list(crawl_all(make_client(api), {"categoryLevel1": "Öl"}))
    assert {p["categoryLevel1"] for p in got} == {"Öl"}


def test_price_banding_splits_a_bucket_with_no_categories_left():
    """When every categorical split is exhausted, price bands take over."""
    products = [
        product(i, categoryLevel2="Rött vin", country="Italien", price=50 + i)
        for i in range(SAFE_BUCKET + 200)
    ]
    api = FakeApi(products, page_limit=PAGE_LIMIT)
    got = {p["productNumber"] for p in crawl_all(make_client(api))}
    # Price bands cover the full spread, so everything priced within them is
    # reachable even though no categorical split remains.
    assert len(got) == len(products)


def test_empty_catalogue_yields_nothing():
    assert list(crawl_all(make_client(FakeApi([])))) == []
