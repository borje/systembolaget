import csv
import io
import json
from pathlib import Path

import pytest
import respx
from rich.console import Console
from typer.testing import CliRunner

from systembolaget import cli, vivino_cli
from systembolaget import format as rendering
from systembolaget.api import BASE_URL
from systembolaget.vivino_api import BASE_URL as VIVINO_URL

runner = CliRunner()
NAME = ("Å Château [bold]庄园[/bold] " + "Extraordinary vineyard name " * 8).strip()
ID = "12345678901234567890"
PRODUCT = {"productNumber": ID, "productId": "p", "productNameBold": NAME,
           "categoryLevel1": "Vin", "tasteClockBody": 8}
MATCH = {"vintage": {"id": int(ID), "name": NAME, "wine": {"id": 98765432109876543210}}}
SB_COMMANDS = [
    (["search", "-n", "1"], {"table", "json", "ndjson", "csv"}),
    (["show", "1"], {"detail", "json"}),
    (["stock", "1"], {"table", "json"}),
    (["like", "1", "-n", "1"], {"table", "json", "ndjson", "csv"}),
    (["dishes"], {"table", "json"}),
    (["facets", "country"], {"table", "json"}),
    (["facets"], {"table", "json"}),
    (["stores"], {"table", "json", "ndjson"}),
    (["dump", "-o", "-", "-n", "1"], {"json", "ndjson", "csv"}),
    (["random", "-n", "1"], {"table", "json", "ndjson", "csv"}),
]
VIVINO_COMMANDS = [(["search", "wine"], {"table", "json"}),
                   (["show", "1"], {"detail", "json"}),
                   (["reviews", "1"], {"table", "json"})]
CASES = [(cli.app, args, formats) for args, formats in SB_COMMANDS] + [
    (vivino_cli.app, args, formats) for args, formats in VIVINO_COMMANDS]


@pytest.fixture(autouse=True)
def no_rate_limit_sleep(monkeypatch):
    monkeypatch.setattr("systembolaget.api.time.sleep", lambda _: None)


@pytest.fixture
def api():
    with respx.mock as router:
        router.get(f"{BASE_URL}/v1/productsearch/search").respond(200, json={
            "metadata": {"docCount": 1}, "products": [PRODUCT],
            "filters": [{"name": "country", "searchModifiers": [{"value": "Sverige", "count": 1}]}],
        })
        router.get(f"{BASE_URL}/v1/product/productnumber/1").respond(
            200, json={**PRODUCT, "productNumber": "1"})
        router.get(f"{BASE_URL}/v1/product/productnumber/{ID}").respond(200, json=PRODUCT)
        router.get(f"{BASE_URL}/v1/site/stores/p/").respond(200, json={"storeStocks": [
            {"store": {"alias": NAME}, "stockBalance": {"stock": 1}}]})
        router.get(f"{BASE_URL}/v1/sitesearch/site/").respond(200, json={"siteSearchResults": [
            {"siteId": ID, "displayName": NAME}]})
        router.get(f"{BASE_URL}/v1/dishes/").respond(200, json=[{
            "dishGroupName": "Grupp", "dishes": [{"dishId": ID, "dishName": NAME}]}])
        router.get(f"{VIVINO_URL}/explore/explore").respond(200, json={
            "explore_vintage": {"matches": [MATCH]}})
        router.get(f"{VIVINO_URL}/vintages/1").respond(200, json={"vintage": MATCH["vintage"]})
        router.get(f"{VIVINO_URL}/wines/1/reviews").respond(200, json={"reviews": [{"note": NAME}]})
        yield router


@pytest.mark.parametrize("app,args,formats", CASES)
def test_json_format(app, args, formats, api):
    result = runner.invoke(app, args + ["-f", "json"])
    assert result.exit_code == 0, result.output
    assert isinstance(json.loads(result.stdout), (list, dict))


@pytest.mark.parametrize("app,args,formats", CASES)
def test_unsupported_formats_fail_before_network(app, args, formats):
    unsupported = next(value for value in ["csv", "ndjson", "table", "detail", "bogus"]
                       if value not in formats)
    with respx.mock as router:
        result = runner.invoke(app, args + ["-f", unsupported])
        assert result.exit_code == 2, result.output
        assert "Invalid value" in result.output
        assert not router.calls


def assert_tsv(stdout):
    """Header plus rows, all the same width: nothing else on stdout."""
    rows = list(csv.reader(io.StringIO(stdout), delimiter="\t"))
    assert len(rows) >= 2 and len({len(row) for row in rows}) == 1, rows


@pytest.mark.parametrize("args", [["search", "-n", "1"], ["random", "-n", "1"],
                                  ["search", "--dish", ID, "-n", "1"],
                                  ["like", "1", "-n", "1"], ["stores"], ["dishes"],
                                  ["stock", "1"]])
def test_sb_non_tty_tables_preserve_names(args, api):
    result = runner.invoke(cli.app, args, env={"COLUMNS": "30"})
    assert result.exit_code == 0, result.output
    assert NAME in result.stdout
    if args[0] != "stock":
        assert ID in result.stdout
    assert_tsv(result.stdout)
    if args[0] == "like":
        assert "Likhet" in result.stdout
        assert "0.00" in result.stdout


def test_vivino_non_tty_table_preserves_names_and_ids(api):
    result = runner.invoke(vivino_cli.app, ["search", "wine"], env={"COLUMNS": "30"})
    assert result.exit_code == 0, result.output
    assert NAME in result.stdout
    assert ID in result.stdout
    assert "98765432109876543210" in result.stdout
    assert_tsv(result.stdout)


def test_dishes_no_match_fails_in_every_format(api):
    for fmt in ("table", "json"):
        assert runner.invoke(cli.app, ["dishes", "nomatch", "-f", fmt]).exit_code == 1


# country comes from the API response, category from the static fallback.
@pytest.mark.parametrize("field", ["country", "category"])
def test_facet_values_share_one_json_shape(field, api):
    result = runner.invoke(cli.app, ["facets", field, "-f", "json"])
    assert result.exit_code == 0, result.output
    values = json.loads(result.stdout)
    assert values and all(set(item) == {"value", "count"} for item in values)


def test_vivino_non_tty_reviews_preserve_literal_text(api):
    result = runner.invoke(vivino_cli.app, ["reviews", "1"])
    assert result.exit_code == 0
    assert NAME in result.stdout


def test_interactive_product_table_still_uses_rich(monkeypatch):
    stream = io.StringIO()
    monkeypatch.setattr(rendering, "console", Console(file=stream, force_terminal=True, width=100))
    rendering.print_table([PRODUCT])
    assert "┏" in stream.getvalue()
    assert "\t" not in stream.getvalue()


def test_dump_default_remains_ndjson(api):
    result = runner.invoke(cli.app, ["dump", "-o", "-", "-n", "1"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == PRODUCT


def test_repository_agent_skill_layout():
    root = Path(__file__).resolve().parents[1]
    agents = (root / "AGENTS.md").read_text()
    for name in ("systembolaget", "vivino"):
        canonical = root / "skills" / name
        compatibility = root / ".claude" / "skills" / name
        assert compatibility.is_symlink()
        assert compatibility.readlink() == Path(f"../../skills/{name}")
        assert compatibility.resolve() == canonical
        skill = (canonical / "SKILL.md").read_text()
        assert skill.startswith(f"---\nname: {name}\n")
        assert f"skills/{name}/SKILL.md" in agents
        assert "on PATH" in skill
    assert json.loads((root / ".pi/settings.json").read_text())["skills"] == ["../skills"]
    assert "uv tool install ." in agents
    assert "uv run" in agents
    assert "-f json" in agents
    assert "--limit" in agents
    assert "uv run pytest -q" in agents
    assert "uv run ruff check ." in agents
    readme = (root / "README.md").read_text()
    assert "${HERMES_HOME:-$HOME/.hermes}" in readme
    assert "does not automatically discover" in readme
    assert "non-TTY" in readme
