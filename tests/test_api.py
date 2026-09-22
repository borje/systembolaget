import httpx
import pytest
import respx

from systembolaget.api import BASE_URL, ApiError, Client, NotFound

SEARCH = f"{BASE_URL}/v1/productsearch/search"


def make_client(**kwargs) -> Client:
    # No sleeping between calls, and no real backoff, so tests stay fast.
    return Client(rate_limit=0, **kwargs)


def page(*numbers: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "metadata": {"docCount": len(numbers)},
            "products": [{"productNumber": n} for n in numbers],
        },
    )


@respx.mock
def test_search_caps_page_size_at_the_server_limit():
    route = respx.get(SEARCH).mock(return_value=page("1"))
    make_client().search({}, size=500)
    assert route.calls.last.request.url.params["size"] == "30"


@respx.mock
def test_search_excludes_filter_metadata_unless_asked():
    route = respx.get(SEARCH).mock(return_value=page("1"))
    client = make_client()
    client.search({})
    assert route.calls.last.request.url.params["excludeFilterMetadata"] == "true"
    client.search({}, include_filters=True)
    assert "excludeFilterMetadata" not in route.calls.last.request.url.params


@respx.mock
def test_iter_products_walks_pages_until_they_run_out():
    respx.get(SEARCH).mock(side_effect=[page("1", "2"), page("3"), page()])
    assert [p["productNumber"] for p in make_client().iter_products({})] == ["1", "2", "3"]


@respx.mock
def test_iter_products_stops_on_404_from_paging_past_the_end():
    """The API signals 'no more pages' with a 404 rather than an empty list."""
    respx.get(SEARCH).mock(
        side_effect=[page("1"), httpx.Response(404, json={"statusCode": 404})]
    )
    assert [p["productNumber"] for p in make_client().iter_products({})] == ["1"]


@respx.mock
def test_iter_products_stops_when_results_start_repeating():
    """Some queries wrap around to earlier pages instead of ending."""
    respx.get(SEARCH).mock(side_effect=[page("1", "2"), page("1", "2"), page("9")])
    assert [p["productNumber"] for p in make_client().iter_products({})] == ["1", "2"]


@respx.mock
def test_iter_products_deduplicates_across_pages():
    respx.get(SEARCH).mock(side_effect=[page("1", "2"), page("2", "3"), page()])
    assert [p["productNumber"] for p in make_client().iter_products({})] == ["1", "2", "3"]


@respx.mock
def test_iter_products_honours_limit():
    respx.get(SEARCH).mock(return_value=page("1", "2", "3"))
    assert len(list(make_client().iter_products({}, limit=2))) == 2


@respx.mock
def test_transient_server_errors_are_retried(monkeypatch):
    monkeypatch.setattr("systembolaget.api.time.sleep", lambda _: None)
    respx.get(SEARCH).mock(side_effect=[httpx.Response(503), page("1")])
    assert make_client().search({})["products"][0]["productNumber"] == "1"


@respx.mock
def test_client_errors_are_not_retried():
    route = respx.get(SEARCH).mock(return_value=httpx.Response(400, text="bad filter"))
    with pytest.raises(ApiError, match="400"):
        make_client().search({})
    assert route.call_count == 1


@respx.mock
def test_missing_product_raises_not_found():
    respx.get(f"{BASE_URL}/v1/product/productnumber/000").mock(
        return_value=httpx.Response(404, json={})
    )
    with pytest.raises(NotFound):
        make_client().product("000")


@respx.mock
def test_rejected_key_explains_the_override(monkeypatch):
    monkeypatch.setattr("systembolaget.api.time.sleep", lambda _: None)
    respx.get(SEARCH).mock(return_value=httpx.Response(401))
    with pytest.raises(ApiError, match="SYSTEMBOLAGET_API_KEY"):
        make_client().search({})


@respx.mock
def test_stores_unwraps_the_result_envelope():
    respx.get(f"{BASE_URL}/v1/sitesearch/site/").mock(
        return_value=httpx.Response(200, json={"siteSearchResults": [{"siteId": "0102"}]})
    )
    assert make_client().stores() == [{"siteId": "0102"}]


def test_api_key_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("SYSTEMBOLAGET_API_KEY", "override")
    assert make_client().api_key == "override"
