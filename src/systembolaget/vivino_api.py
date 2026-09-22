"""Thin HTTP client for Vivino's undocumented JSON API.

No API key or account needed — a plain GET with a browser ``User-Agent``
works. AWS WAF sits in front of it but does not block ordinary GETs.
"""

from __future__ import annotations

import time
from typing import Any, Self

import httpx

BASE_URL = "https://www.vivino.com/api"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

#: wine_type_ids[] values, as spelled out on vivino.com's own filter UI.
WINE_TYPES: dict[str, int] = {
    "red": 1,
    "white": 2,
    "sparkling": 3,
    "rose": 4,
    "dessert": 7,
    "fortified": 24,
}


class ApiError(RuntimeError):
    """A request failed in a way retrying will not fix."""


class NotFound(ApiError):
    """The API returned 404."""


class Client:
    """Synchronous client with retry for throttling and transient errors."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        max_retries: int = 4,
        client: httpx.Client | None = None,
    ) -> None:
        self.max_retries = max_retries
        self._client = client or httpx.Client(
            base_url=BASE_URL,
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- transport ---------------------------------------------------------

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        delay = 1.0
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                response = self._client.get(path, params=params)
            except httpx.RequestError as exc:
                last_error = exc
            else:
                if response.status_code == 200:
                    return response.json()
                if response.status_code == 404:
                    raise NotFound(f"Not found: {path}")
                if response.status_code not in (408, 429, 500, 502, 503, 504):
                    raise ApiError(f"{response.status_code} from {path}: {response.text[:200]}")
                last_error = ApiError(f"{response.status_code} from {path}")
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = max(delay, float(retry_after))

            if attempt < self.max_retries - 1:
                time.sleep(delay)
                delay *= 2

        raise ApiError(f"Gave up on {path} after {self.max_retries} attempts") from last_error

    # -- endpoints -----------------------------------------------------

    def explore(
        self,
        search_term: str,
        *,
        wine_types: list[str] | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        min_rating: float = 0.0,
        order_by: str = "relevance",
        order: str = "desc",
        page: int = 1,
        country_code: str = "se",
        currency_code: str = "SEK",
        language: str = "en",
    ) -> dict[str, Any]:
        """Search for wines. Returns the ``explore_vintage`` payload."""
        params: dict[str, Any] = {
            "search_term": search_term,
            "country_code": country_code,
            "currency_code": currency_code,
            "order_by": order_by,
            "order": order,
            "min_rating": min_rating,
            "page": page,
            "language": language,
        }
        if wine_types:
            params["wine_type_ids[]"] = [WINE_TYPES[t] for t in wine_types]
        if min_price is not None:
            params["price_range_min"] = min_price
        if max_price is not None:
            params["price_range_max"] = max_price
        payload = self.get("/explore/explore", params)
        return payload.get("explore_vintage", {})

    def vintage(self, vintage_id: int | str) -> dict[str, Any]:
        """One vintage's full detail record."""
        payload = self.get(f"/vintages/{vintage_id}")
        return payload.get("vintage", payload)

    def highlights(self, vintage_id: int | str) -> dict[str, Any]:
        """A vintage's editorial highlights (often empty)."""
        return self.get(f"/vintages/{vintage_id}/highlights")

    def reviews(
        self,
        wine_id: int | str,
        *,
        page: int = 1,
        per_page: int = 10,
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """User reviews for a wine (needs the wine id, not the vintage id)."""
        payload = self.get(
            f"/wines/{wine_id}/reviews",
            {"per_page": per_page, "page": page, "language": language},
        )
        return payload.get("reviews", [])
