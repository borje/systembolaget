"""Search Systembolaget's product catalogue via their public REST API."""

from .api import ApiError, Client, NotFound
from .search import (
    build_query,
    crawl_all,
    rank_by_similarity,
    similar_query,
    taste_profile,
)

__all__ = [
    "ApiError",
    "Client",
    "NotFound",
    "build_query",
    "crawl_all",
    "rank_by_similarity",
    "similar_query",
    "taste_profile",
]
__version__ = "0.1.0"
