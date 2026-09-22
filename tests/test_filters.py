import pytest

from systembolaget.filters import (
    RANGE_FILTERS,
    TERM_FILTERS,
    FilterError,
    parse_range,
)


@pytest.mark.parametrize(
    "spec,expected",
    [
        ("100-200", (100.0, 200.0)),
        ("100-", (100.0, None)),
        ("-200", (None, 200.0)),
        ("150", (150.0, 150.0)),
        ("*-*", (None, None)),
        ("  80-120 ", (80.0, 120.0)),
        ("12.5-13.5", (12.5, 13.5)),
    ],
)
def test_parse_range_accepts_open_and_closed_bounds(spec, expected):
    assert parse_range(spec, RANGE_FILTERS["price"]) == expected


@pytest.mark.parametrize("spec", ["200-100", "abc", "", "1-abc"])
def test_parse_range_rejects_nonsense(spec):
    with pytest.raises(FilterError):
        parse_range(spec, RANGE_FILTERS["price"])


def test_taste_clock_bounds_are_enforced():
    assert parse_range("8-12", RANGE_FILTERS["body"]) == (8.0, 12.0)
    with pytest.raises(FilterError, match="outside valid range"):
        parse_range("20", RANGE_FILTERS["body"])


def test_range_renders_with_min_max_suffixes():
    """The plain ``price=100-200`` form is accepted but ignored by the API."""
    rendered = RANGE_FILTERS["price"].render(100, 200)
    assert rendered == {"price.min": "100", "price.max": "200"}


def test_range_omits_absent_bounds():
    assert RANGE_FILTERS["price"].render(None, 200) == {"price.max": "200"}
    assert RANGE_FILTERS["price"].render(100, None) == {"price.min": "100"}
    assert RANGE_FILTERS["price"].render(None, None) == {}


def test_range_keeps_fractional_bounds_intact():
    assert RANGE_FILTERS["alcohol"].render(0, 0.5) == {
        "alcoholPercentage.min": "0",
        "alcoholPercentage.max": "0.5",
    }


def test_pairs_with_maps_to_taste_symbols():
    assert TERM_FILTERS["pairs-with"].param == "tasteSymbols"
    assert "Grillat" in TERM_FILTERS["pairs-with"].values
