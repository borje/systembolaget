import httpx
import pytest
import respx

from systembolaget.vivino_api import BASE_URL, ApiError, Client, NotFound


def make_client(**kwargs) -> Client:
    return Client(**kwargs)


@respx.mock
def test_explore_sends_wine_type_ids_and_returns_matches():
    route = respx.get(f"{BASE_URL}/explore/explore").mock(
        return_value=httpx.Response(200, json={"explore_vintage": {"matches": [{"vintage": {"id": 1}}]}})
    )
    result = make_client().explore("Barolo", wine_types=["red", "white"])
    assert result["matches"][0]["vintage"]["id"] == 1
    assert route.calls.last.request.url.params.get_list("wine_type_ids[]") == ["1", "2"]


@respx.mock
def test_vintage_unwraps_the_envelope():
    respx.get(f"{BASE_URL}/vintages/123").mock(
        return_value=httpx.Response(200, json={"vintage": {"id": 123}})
    )
    assert make_client().vintage(123) == {"id": 123}


@respx.mock
def test_reviews_unwraps_the_list():
    respx.get(f"{BASE_URL}/wines/9/reviews").mock(
        return_value=httpx.Response(200, json={"reviews": [{"rating": 4}]})
    )
    assert make_client().reviews(9) == [{"rating": 4}]


@respx.mock
def test_missing_vintage_raises_not_found():
    respx.get(f"{BASE_URL}/vintages/0").mock(return_value=httpx.Response(404, json={}))
    with pytest.raises(NotFound):
        make_client().vintage(0)


@respx.mock
def test_transient_errors_are_retried(monkeypatch):
    monkeypatch.setattr("systembolaget.vivino_api.time.sleep", lambda _: None)
    respx.get(f"{BASE_URL}/vintages/1").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"vintage": {"id": 1}})]
    )
    assert make_client().vintage(1) == {"id": 1}


@respx.mock
def test_client_errors_are_not_retried():
    route = respx.get(f"{BASE_URL}/vintages/1").mock(return_value=httpx.Response(400, text="bad"))
    with pytest.raises(ApiError, match="400"):
        make_client().vintage(1)
    assert route.call_count == 1
