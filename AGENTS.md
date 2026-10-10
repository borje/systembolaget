# Agent guide

Canonical skills: [Systembolaget](skills/systembolaget/SKILL.md) and
[Vivino](skills/vivino/SKILL.md). Read the relevant skill before querying.

- Install both CLIs from this root with `uv tool install .`.
- Use installed `sb` / `vivino` if available on PATH; otherwise run
  `uv run sb ...` / `uv run vivino ...` from the repository root.
- Prefer `-f json` for agent parsing; supported formats vary by command.
- Bound searches, similarity suggestions and reviews with `--limit` / `-n`.
  Narrow exports and use `sb search --count` before large requests. Commands
  without a limit option should be narrowed with their available filters.
- Non-TTY table output is lossless tab-separated text; interactive tables use Rich.
- Verify changes: `uv run pytest -q` and `uv run ruff check .`.
  Tests mock HTTP with respx; do not use live APIs in tests.
