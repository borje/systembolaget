"""Thin HTTP client for Systembolaget's public e-commerce API.

The API is the one https://www.systembolaget.se itself calls from the browser.
It needs no account: the subscription key below is the public one shipped in
the site's own JavaScript bundle.  Callers can override it with the
``SYSTEMBOLAGET_API_KEY`` environment variable if it is ever rotated.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from typing import Any, Self

import httpx

BASE_URL = "https://api-extern.systembolaget.se/sb-api-ecommerce"

#: Public key inlined in the site bundle as ``NEXT_PUBLIC_API_KEY_APIM``.
DEFAULT_API_KEY = "8d39a7340ee7439f8b4c1e995c8f3e4a"

#: The server silently caps ``size`` at 30, so asking for more just wastes a
#: round trip's worth of expectation.
MAX_PAGE_SIZE = 30


class ApiError(RuntimeError):
    """A request failed in a way retrying will not fix."""


class NotFound(ApiError):
    """The API returned 404.

    For the search endpoint this is not really an error: asking for a page
    past the last one is how the server signals that a result set is
    exhausted, so paging code treats it as a stop condition.
    """


class Client:
    """Synchronous client with retry and polite rate limiting."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 30.0,
        rate_limit: float = 0.1,
        max_retries: int = 4,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("SYSTEMBOLAGET_API_KEY") or DEFAULT_API_KEY
        self.rate_limit = rate_limit
        self.max_retries = max_retries
        self._last_request = 0.0
        self._client = client or httpx.Client(
            base_url=BASE_URL,
            timeout=timeout,
            headers={
                "Ocp-Apim-Subscription-Key": self.api_key,
                "Accept": "application/json",
                # The API rejects some default client identifiers outright.
                "User-Agent": "systembolaget-cli/0.1 (+https://github.com/)",
            },
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- transport ---------------------------------------------------------

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET *path*, retrying throttling and transient server errors."""
        delay = 1.0
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            self._throttle()
            try:
                response = self._client.get(path, params=params)
            except httpx.RequestError as exc:  # network-level failure
                last_error = exc
            else:
                if response.status_code == 200:
                    return response.json()
                if response.status_code == 404:
                    raise NotFound(f"Not found: {path}")
                if response.status_code in (401, 403):
                    raise ApiError(
                        f"Rejected by the API ({response.status_code}). The public "
                        "key may have rotated; set SYSTEMBOLAGET_API_KEY to override."
                    )
                if response.status_code not in (408, 429, 500, 502, 503, 504):
                    raise ApiError(
                        f"{response.status_code} from {path}: {response.text[:200]}"
                    )
                last_error = ApiError(f"{response.status_code} from {path}")
                # Honour Retry-After when the server sends one.
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = max(delay, float(retry_after))

            if attempt < self.max_retries - 1:
                time.sleep(delay)
                delay *= 2

        raise ApiError(f"Gave up on {path} after {self.max_retries} attempts") from last_error

    def _throttle(self) -> None:
        if self.rate_limit <= 0:
            return
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request = time.monotonic()

    # -- endpoints ---------------------------------------------------------

    def search(
        self,
        params: dict[str, Any],
        *,
        page: int = 1,
        size: int = MAX_PAGE_SIZE,
        include_filters: bool = False,
    ) -> dict[str, Any]:
        """One page of product search results."""
        query = dict(params)
        query["page"] = page
        query["size"] = min(size, MAX_PAGE_SIZE)
        if not include_filters:
            query["excludeFilterMetadata"] = "true"
        return self.get("/v1/productsearch/search", query)

    def product(self, product_number: str) -> dict[str, Any]:
        """The full ~137-field record for one product number.

        This is strictly richer than the search result: it adds producer and
        terroir prose, aroma, raw materials, nutrition tables and trivia.
        """
        return self.get(f"/v1/product/productnumber/{product_number}")

    def stores(self) -> list[dict[str, Any]]:
        """Every store and agent, with address and opening hours."""
        payload = self.get("/v1/sitesearch/site/")
        return payload.get("siteSearchResults", [])

    def store_stock(self, product_id: str) -> list[dict[str, Any]]:
        """Per-store stock for a product, keyed by its internal ``productId``.

        Not the same as ``productNumber`` — callers get it from ``product()``.
        Only stores that currently hold the product appear in the result.
        """
        payload = self.get(f"/v1/site/stores/{product_id}/")
        return payload.get("storeStocks", [])

    def store_stock_at(self, site_id: str, product_id: str) -> dict[str, Any]:
        """Stock for one product at one store — cheaper than ``store_stock``
        when only a specific store is of interest.
        """
        return self.get(f"/v1/stockbalance/store/{site_id}/{product_id}")

    def iter_products(
        self,
        params: dict[str, Any],
        *,
        limit: int | None = None,
        max_pages: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Walk search result pages, yielding unique products.

        Paging past the final page wraps back to earlier results instead of
        returning an empty list, so this stops as soon as a page contributes
        nothing new rather than trusting the reported page count.
        """
        seen: set[str] = set()
        yielded = 0
        page = 1

        while True:
            if max_pages is not None and page > max_pages:
                return
            try:
                payload = self.search(params, page=page)
            except NotFound:
                # Paged past the final page — the result set is complete.
                return
            products = payload.get("products") or []
            if not products:
                return

            fresh = 0
            for product in products:
                key = product.get("productNumber") or product.get("productId")
                if key in seen:
                    continue
                seen.add(key)
                fresh += 1
                yield product
                yielded += 1
                if limit is not None and yielded >= limit:
                    return

            if fresh == 0:  # the result set has started repeating
                return
            page += 1

    def count(self, params: dict[str, Any]) -> int:
        """Number of matching products, as the API reports it.

        Treat this as an estimate: it runs slightly ahead of the number of
        products the search endpoint will actually hand back.
        """
        payload = self.search(params, page=1, size=1)
        return int(payload.get("metadata", {}).get("docCount", 0))
