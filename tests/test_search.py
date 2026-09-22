import pytest

from systembolaget.filters import FilterError
from systembolaget.search import (
    build_query,
    rank_by_similarity,
    similar_query,
    similarity_score,
    taste_profile,
)


def test_build_query_repeats_term_filters_for_or_semantics():
    params = build_query(terms={"country": ["Italien", "Frankrike"]})
    assert params["country"] == ["Italien", "Frankrike"]


def test_build_query_renders_ranges_with_suffixes():
    params = build_query(ranges={"price": "100-200", "body": "8-"})
    assert params["price.min"] == "100"
    assert params["price.max"] == "200"
    assert params["tasteClockBody.min"] == "8"
    assert "tasteClockBody.max" not in params


def test_build_query_rejects_unknown_filters():
    with pytest.raises(FilterError):
        build_query(terms={"nonsense": ["x"]})


def test_taste_profile_reads_search_result_shape():
    product = {
        "tasteClocks": [
            {"key": "TasteClockBody", "value": 6},
            {"key": "TasteClockFruitacid", "value": 9},
        ]
    }
    assert taste_profile(product) == {"body": 6, "fruitacid": 9}


def test_taste_profile_reads_detail_shape():
    product = {"tasteClockBody": 6, "tasteClockRoughness": 6, "tasteClockSweetness": None}
    assert taste_profile(product) == {"body": 6, "roughness": 6}


def test_taste_profile_treats_zero_as_absent():
    """Search results pad undeclared clocks with 0, which is not a real value."""
    assert taste_profile({"tasteClockBody": 0, "tasteClockBitter": 3}) == {"bitterness": 3}


def test_similar_query_windows_each_clock_and_clamps():
    product = {"tasteClockBody": 1, "tasteClockFruitacid": 12, "categoryLevel2": "Rött vin"}
    params = similar_query(product, tolerance=2)
    assert params["tasteClockBody.min"] == "0"     # clamped at the low end
    assert params["tasteClockBody.max"] == "3"
    assert params["tasteClockFruitacid.min"] == "10"
    assert params["tasteClockFruitacid.max"] == "12"  # clamped at the high end
    assert params["categoryLevel2"] == ["Rött vin"]


def test_similar_query_can_drop_the_category_constraint():
    product = {"tasteClockBody": 5, "categoryLevel2": "Rött vin"}
    params = similar_query(product, match_category=False)
    assert "categoryLevel2" not in params


def test_similar_query_needs_taste_data():
    with pytest.raises(FilterError, match="no taste clock data"):
        similar_query({"productNumber": "1", "categoryLevel2": "Rött vin"})


def test_similar_query_can_require_matching_pairings():
    product = {"tasteClockBody": 5, "tasteSymbols": "Grillat;Nöt"}
    params = similar_query(product, match_pairings=True)
    assert params["tasteSymbols"] == ["Grillat", "Nöt"]


def test_similarity_score_is_zero_for_an_identical_profile():
    assert similarity_score({"body": 6, "roughness": 4}, {"body": 6, "roughness": 4}) == 0


def test_similarity_score_penalises_missing_clocks():
    """A candidate that simply lacks a clock must not beat one that matches."""
    reference = {"body": 6}
    assert similarity_score(reference, {"body": 6}) < similarity_score(reference, {})


def test_rank_by_similarity_orders_closest_first_and_drops_self():
    reference = {"productNumber": "1", "tasteClockBody": 6}
    candidates = [
        {"productNumber": "1", "tasteClockBody": 6},   # the reference itself
        {"productNumber": "2", "tasteClockBody": 9},
        {"productNumber": "3", "tasteClockBody": 7},
    ]
    ranked = rank_by_similarity(reference, candidates)
    assert [p["productNumber"] for _, p in ranked] == ["3", "2"]
