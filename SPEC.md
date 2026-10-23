# Spec: Rumour Pressure vs. Market Price — MVP

Status: draft for review · Owner: Sam Mitchell · Last updated: 2026-10-23
One-pager: https://claude.ai/artifact/M7J9auN9D9qYZb3isqbJNR

## Objective

Measure whether online rumour about celebrity life events leads, lags or merely mirrors
prediction-market prices on long-horizon culture questions (closing 6–24+ months out).
Research answer first; trading is out of scope unless a solid lead relationship is found.

The MVP is a **Taylor Swift flagship**: collect prices, attention and text for 2–4
long-horizon Swift markets, score every relevant post for stance against each market's
own resolution text, detect price jumps, and show it all in a **local dashboard** on one
hourly timeline. In parallel, count jumps across 30–50 candidate markets to decide whether
the full panel is viable.

User: Sam (sole researcher). Success = the success criteria at the end of this spec.

## Tech stack

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.12 | |
| Env / deps | `uv` | lockfile committed |
| Storage | DuckDB over Parquet | one local warehouse, `data/` gitignored |
| HTTP | `httpx` | retries + per-source rate limits |
| Live stream | `websockets` | Bluesky Jetstream |
| Row schemas | `pydantic` v2 | validate every row before write |
| Stance model | **Qwen3.5-9B, 4-bit, via Ollama** | thinking off; JSON-schema-constrained output; OpenAI-compatible API so the model is swappable (MLX later if speed demands) |
| Dashboard | Streamlit + Plotly | local only |
| Lint / format | `ruff` | |
| Tests | `pytest` | |

Target machine: MacBook Air, M3, 16 GB unified memory.

## Data sources (MVP)

| Source | Role | Collected | Resolution | Limits to respect |
|---|---|---|---|---|
| Wikipedia pageviews | Attention | daily views of named articles | daily (hourly dumps deferred) | descriptive User-Agent |
| Wikipedia edit history | Attention | revisions + reverts on named articles | to the second | — |
| GDELT DOC 2.0 | Attention + text | volume timeline, headlines + URLs | ~15 min–hourly | 1 request / 5 s; last 3 months via DOC API |
| Reddit via Arctic Shift | Text | posts + comments in named subreddits | to the second | ~48 h indexing lag; volunteer service — ≥700 ms between calls |
| Bluesky Jetstream | Text | live posts matching keywords | real time | live only; logger must run continuously |
| Manifold | Price + text | bets (→ price series) + comments | ms | play money |
| Polymarket | Price | price history, trades | hourly or finer (confirm) | |
| Kalshi | Price | price history | hourly or finer (confirm) | |

Excluded: Google Trends (no reliable free API), X/TikTok/Instagram (cost / no research access).

## Data model (DuckDB)

All timestamps are UTC. The shared join key is `hour = date_trunc('hour', ts_utc)`.

```
markets   (market_id, venue, question, resolution_text, close_time, url, entity_keys[])
prices    (market_id, ts_utc, price, volume, n_trades)
attention (source, entity, ts_utc, metric, value)
posts     (post_id, source, ts_utc, channel, author_hash, text, url, collected_at)
stance    (post_id, market_id, label, confidence, model, prompt_version, classified_at)
jumps     (market_id, ts_start, ts_end, delta, residual, volume, n_trades, params_hash)
```

- `post_id` is `<source>:<native id>`; inserts are upserts, so every collector is idempotent.
- `author_hash` is a salted hash; raw usernames are never stored.
- `label` ∈ {`supports_yes`, `supports_no`, `irrelevant`}.

**One writer at a time.** DuckDB allows a single writing process per file, so long-running
processes never hold the warehouse open. The Bluesky logger appends to daily JSONL files in
`data/live/bluesky/`; `rp collect bluesky` loads them (idempotently) and removes completed
days. Batch collectors open the warehouse only while writing; the dashboard opens it
read-only. Author deletions are honoured: the logger records deletions of posts it kept,
and ingest removes those posts and their stance labels.

## Pipeline

1. **Registry** — `registry/markets.yaml` lists markets with venue IDs, resolution text and
   entity keywords. Task 1 finds the flagship markets by searching all three venues.
2. **Collect** — one module per source; each separates `fetch` (network, raw JSON cached to
   `data/raw/`) from `parse` (pure function → pydantic rows).
3. **Relevance filter** — cheap keyword/entity match on posts before the model sees them.
4. **Stance** — Qwen3.5-9B gets the market's resolution text + one post and returns
   `{label, confidence}` under a JSON schema. Prompt is versioned; changing it bumps
   `prompt_version` and never overwrites earlier labels.
5. **Signals** — detrend each price series (constant-hazard baseline, parameterised),
   detect jumps (default: |Δ| ≥ 5 points within 24 h, min trade count; all thresholds are
   parameters), build the hourly stance index = weighted(supports_yes) − weighted(supports_no).
6. **Dashboard** — per market: price lane per venue, attention lanes, stance index lane,
   jump markers; selecting a jump lists posts and headlines from the preceding 72 h
   (linked, not republished).

## Commands

```
uv sync                                           # install
uv run ruff check --fix . && uv run ruff format . # lint + format
uv run pytest                                     # unit tests (no network)
uv run pytest -m live                             # opt-in tests that hit real APIs
uv run pytest -m slow                             # stance accuracy vs. labelled set

uv run rp registry find --entity "Taylor Swift"   # search venues for candidate markets
uv run rp collect <source> --market <id> [--since YYYY-MM-DD]
uv run rp collect all --market <id>
uv run rp bluesky-log --keywords-from-registry    # long-running live logger
uv run rp classify --market <id> [--limit N]
uv run rp bench-stance --n 200                    # posts/minute on this machine
uv run rp signals --market <id>                   # detrend, jumps, stance index
uv run rp panel-count --candidates registry/candidates.yaml
uv run streamlit run src/rumour_pressure/dashboard/app.py

ollama pull <qwen3.5 9b 4-bit tag>                # exact tag pinned in Task 1
```

## Project structure

```
rumour-pressure/
  SPEC.md
  pyproject.toml, uv.lock
  registry/
    markets.yaml          flagship markets + resolution text
    candidates.yaml       panel candidates for the feasibility count
  src/rumour_pressure/
    cli.py
    config.py             rate limits, thresholds, paths
    store/                DuckDB schema + upsert helpers
    collect/              wikipedia.py gdelt.py arctic_shift.py bluesky.py
                          manifold.py polymarket.py kalshi.py
    stance/               prompt.py client.py relevance.py
    signals/              detrend.py jumps.py index.py
    dashboard/app.py
  labels/
    stance_labels.csv     post_id, market_id, label, labeller — NO post text
  tests/
    fixtures/             recorded API responses (trimmed, no usernames)
    unit/  live/  slow/
  data/                   gitignored: raw/, warehouse.duckdb
```

## Code style

Typed functions, pure parsers, network at the edges. Example:

```python
class PriceRow(BaseModel):
    market_id: str
    ts_utc: datetime
    price: float = Field(ge=0, le=1)
    volume: float | None = None
    n_trades: int | None = None


def parse_manifold_bets(market_id: str, bets: list[dict]) -> list[PriceRow]:
    """Turn raw Manifold bets into a price series (one row per bet, probAfter)."""
    return [
        PriceRow(
            market_id=market_id,
            ts_utc=datetime.fromtimestamp(b["createdTime"] / 1000, tz=UTC),
            price=b["probAfter"],
        )
        for b in bets
        if not b.get("isCancelled")
    ]
```

- `snake_case` modules and functions; one source per module.
- No hidden globals: thresholds and limits live in `config.py`.
- Log, don't print; every collector logs rows fetched / written / skipped.

## Testing strategy

- **Unit (default, offline):** every `parse_*` against recorded fixtures; upsert
  idempotency (run twice → same row count); detrend + jump detection on synthetic series
  with injected jumps; stance output schema validation with a stubbed model.
- **Live (`-m live`):** one small real call per source to catch API drift. Run before
  merging collector changes.
- **Slow (`-m slow`):** stance classifier against `labels/stance_labels.csv`; reports
  macro-F1 and per-class confusion.
- No test may require the Bluesky logger or Ollama to be running unless marked.

## Boundaries

**Always**
- Store UTC; bucket by hour.
- Respect each source's rate limit and identify with a descriptive User-Agent.
- Cache raw responses so re-parsing never re-fetches.
- Run `ruff` and unit tests before every commit.
- Version the stance prompt; never overwrite labels made with an older version.

**Ask first**
- Adding a dependency or a data source.
- Changing the warehouse schema.
- Anything that costs money (cloud server, paid API).
- Changing jump or stance thresholds after results have been looked at.

**Never**
- Commit `data/`, raw post text, usernames or credentials.
- Republish individual posts; the dashboard links to them and shows aggregates.
- Work around a source that blocks or rate-limits us.
- Place trades or build trading code in the MVP.

## Success criteria

1. `registry/markets.yaml` holds ≥2 long-horizon Swift markets on ≥2 venues, each with
   resolution text and entity keywords.
2. Every collector backfills its source for the flagship markets (from market creation or
   the source's history limit); a second run writes zero duplicate rows.
3. The Bluesky logger runs ≥24 h unattended on the laptop, reconnects on drop, and records
   any gaps in a `logger_gaps` table.
4. ≥300 hand-labelled posts across ≥3 markets; classifier macro-F1 ≥ 0.70 against them
   (target to revisit after the first look). `bench-stance` reports posts/minute.
5. The jump detector finds every injected jump in the synthetic test and produces a jump
   list for each flagship market.
6. The dashboard shows each flagship market with price-per-venue, attention and stance
   lanes plus jump markers; selecting a jump lists the prior 72 h of posts. One market
   loads in under 5 s on the M3 Air.
7. `panel-count` reports qualifying jumps across 30–50 candidate markets, so the panel
   decision is made with data.

## Open questions

- [ ] **Cloud server for the Bluesky logger** — runs on the laptop for now; move to a small
      server before relying on it for continuous data. (Tracked so it isn't forgotten.)
- [ ] Which exact markets form the flagship (decided in Task 1)?
- [ ] Panel selection rule: venues, minimum volume, minimum horizon, topic.
- [ ] Polymarket and Kalshi price-history depth and granularity for long-dated markets.
- [ ] Are daily Wikipedia views enough, or do we need the hourly dumps?
- [ ] Single labeller (Sam) or a second labeller to measure agreement?
- [ ] Default jump parameters (threshold, window, minimum trades) — confirm after Task 1 data.
- [ ] **"System 1" (non-reasoning) models for stance** — come back to this once the labelled
      set exists. Stance is a fast, single-label judgement, so a non-reasoning instruct
      model, or a small fine-tuned encoder classifier trained on our labels, may match
      Qwen3.5-9B's accuracy at a fraction of the latency. `bench-stance` + the slow
      accuracy test are the harness for comparing them.
