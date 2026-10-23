# Implementation Plan: Rumour Pressure MVP

Spec: [SPEC.md](SPEC.md) · Last updated: 2026-10-23

## Overview

Build the MVP in vertical slices: each slice ends with something visible in the local
dashboard. Order follows risk. The live Bluesky logger starts first because live data
cannot be backfilled. Price data and the panel jump count come next, because "are there
enough informative jumps?" is the dealbreaker most likely to stop the project. Attention,
text and stance follow once that question has an answer.

## Architecture decisions

- **One warehouse, one join key.** Every source writes to DuckDB with UTC timestamps; all
  views join on the hourly bucket.
- **Fetch / parse split.** Network code caches raw JSON; parsers are pure functions tested
  against recorded fixtures, so tests never need the network.
- **Idempotent upserts.** Collectors can be re-run freely; natural keys prevent duplicates.
- **Dashboard grows with the data.** It is created in Task 4 with one price line and gains
  a lane in each later slice, rather than being built at the end.
- **Stance model behind an OpenAI-compatible client.** Qwen3.5-9B via Ollama with thinking
  off and JSON-schema output; swapping in another model is a config change.

## Task list

### Phase 0: Foundation

#### Task 1: Project scaffold and warehouse
**Description:** Set up the uv project, ruff, pytest markers (`live`, `slow`), the `rp`
CLI entry point, `config.py`, and the DuckDB schema from the spec with upsert helpers.
**Acceptance criteria:**
- [ ] `uv sync`, `uv run ruff check .` and `uv run pytest` all succeed on a fresh clone.
- [ ] `rp --help` lists the commands from the spec (stubs are fine).
- [ ] Upserting the same rows twice leaves the row count unchanged (unit test).
**Verification:** `uv run pytest tests/unit/test_store.py`
**Dependencies:** None
**Files:** `pyproject.toml`, `src/rumour_pressure/{cli,config}.py`, `src/rumour_pressure/store/`, `tests/unit/test_store.py`
**Scope:** M

#### Task 2: Bluesky live logger
**Description:** Long-running `rp bluesky-log` that subscribes to Jetstream, keeps posts
matching keyword sets, writes them to `posts`, reconnects with backoff, and records any
outage in `logger_gaps`. Keywords come from config until the registry exists.
**Acceptance criteria:**
- [ ] Matching posts land in `posts` with `author_hash`, never a raw handle.
- [ ] A forced disconnect produces one `logger_gaps` row and automatic reconnection.
- [ ] Runs 24 h on the laptop without manual intervention (success criterion 3).
**Verification:** unit tests on the filter and parser with recorded Jetstream messages; `uv run pytest -m live tests/live/test_bluesky.py`; 24 h run.
**Dependencies:** Task 1
**Files:** `src/rumour_pressure/collect/bluesky.py`, `tests/unit/test_bluesky.py`, `tests/fixtures/bluesky/`
**Scope:** M

#### Task 3: Market registry and flagship selection
**Description:** `rp registry find --entity "Taylor Swift"` searches Polymarket, Kalshi and
Manifold for open markets closing 6+ months out and prints candidates with volume and close
date. Sam picks the flagship; the chosen markets go into `registry/markets.yaml` with
resolution text and entity keywords. Pin the exact Ollama model tag here too.
**Acceptance criteria:**
- [ ] The finder returns candidates from all three venues (or reports which returned none).
- [ ] `markets.yaml` holds ≥2 long-horizon Swift markets on ≥2 venues, validated on load
      (success criterion 1).
- [ ] The Bluesky logger reads its keywords from the registry.
**Verification:** `uv run pytest tests/unit/test_registry.py`; `uv run rp registry find --entity "Taylor Swift"`
**Dependencies:** Task 1
**Files:** `src/rumour_pressure/registry/`, `registry/markets.yaml`, `tests/unit/test_registry.py`
**Scope:** M

### Checkpoint A: foundation
- [ ] All unit tests pass.
- [ ] The logger is running on the laptop and writing posts.
- [ ] Sam has approved the flagship markets.

### Phase 1: Price slice and the panel go/no-go

#### Task 4: Manifold prices and the first dashboard view
**Description:** Collect the full bet history for Manifold flagship markets into `prices`,
and create the Streamlit dashboard with a market selector and one hourly price line.
This is the first end-to-end slice.
**Acceptance criteria:**
- [ ] Bet history parses into a price series; re-running writes no duplicates.
- [ ] The dashboard shows the Manifold price line for any registry market.
**Verification:** `uv run pytest tests/unit/test_manifold.py`; open the dashboard and check one market by eye against Manifold's own chart.
**Dependencies:** Tasks 1, 3
**Files:** `collect/manifold.py`, `dashboard/app.py`, `tests/unit/test_manifold.py`, fixtures
**Scope:** M

#### Task 5: Polymarket and Kalshi prices
**Description:** Price-history collectors for both venues, plus volume and trade counts
where available. Record how far back and how fine their history goes — this answers an
open question in the spec.
**Acceptance criteria:**
- [ ] Both venues backfill flagship markets into `prices`; re-runs are idempotent.
- [ ] The dashboard shows one price line per venue on the same axis.
- [ ] History depth and granularity per venue are written into SPEC.md.
**Verification:** `uv run pytest tests/unit/test_polymarket.py tests/unit/test_kalshi.py`; `uv run pytest -m live`
**Dependencies:** Task 4
**Files:** `collect/polymarket.py`, `collect/kalshi.py`, tests + fixtures, `dashboard/app.py`
**Scope:** M

#### Task 6: Detrending and jump detection
**Description:** Constant-hazard detrend and a parameterised jump detector (default:
|Δ| ≥ 5 points within 24 h, minimum trade count), writing to `jumps` and drawn as markers
on the dashboard.
**Acceptance criteria:**
- [ ] Synthetic series with injected jumps: every jump found, none on a flat series
      (success criterion 5).
- [ ] Each flagship market has a jump list; parameters are stored as `params_hash`.
- [ ] Jumps appear as markers on the dashboard price lanes.
**Verification:** `uv run pytest tests/unit/test_signals.py`; `uv run rp signals --market <id>`
**Dependencies:** Task 5
**Files:** `signals/detrend.py`, `signals/jumps.py`, `tests/unit/test_signals.py`, `dashboard/app.py`
**Scope:** M

#### Task 7: Panel feasibility count
**Description:** Build `registry/candidates.yaml` of 30–50 long-horizon culture markets and
run `rp panel-count`, which collects their prices and reports qualifying jumps (raw and
volume-filtered), per venue and in total.
**Acceptance criteria:**
- [ ] Report lists jumps per market, per venue and pooled, with and without the volume filter.
- [ ] Report saved to `reports/panel_count.md` (success criterion 7).
**Verification:** `uv run rp panel-count --candidates registry/candidates.yaml`; Sam reviews the report.
**Dependencies:** Task 6
**Files:** `registry/candidates.yaml`, `src/rumour_pressure/panel.py`, `reports/panel_count.md`
**Scope:** S–M

### Checkpoint B: go/no-go — review with Sam
- [ ] Enough pooled jumps for a panel (dozens to low hundreds)? If not, decide: widen the
      candidate pool, relax thresholds, or narrow the research question.
- [ ] Do most large moves come from single low-volume trades?

### Phase 2: Attention lanes

#### Task 8: Wikipedia pageviews and edit history
**Description:** Daily pageviews and revision history (with reverts flagged) for each
market's entity articles, drawn as attention lanes.
**Acceptance criteria:**
- [ ] Both series land in `attention`; re-runs are idempotent; requests carry a descriptive User-Agent.
- [ ] Two attention lanes appear under the price lanes, sharing the time axis.
**Verification:** `uv run pytest tests/unit/test_wikipedia.py`; dashboard check.
**Dependencies:** Task 4
**Files:** `collect/wikipedia.py`, tests + fixtures, `dashboard/app.py`
**Scope:** M

#### Task 9: GDELT volume and headlines
**Description:** Hourly coverage-volume timeline into `attention`, and headlines with URLs
into `posts` (source `gdelt`), respecting the 1-request-per-5-seconds limit.
**Acceptance criteria:**
- [ ] Volume lane on the dashboard; headlines stored as posts.
- [ ] Rate limiter verified by a unit test with a fake clock.
**Verification:** `uv run pytest tests/unit/test_gdelt.py`; `uv run pytest -m live tests/live/test_gdelt.py`
**Dependencies:** Task 4
**Files:** `collect/gdelt.py`, tests + fixtures, `dashboard/app.py`
**Scope:** M

### Phase 3: Text and stance

#### Task 10: Reddit backfill and Manifold comments
**Description:** Arctic Shift collector for named subreddits (list in the registry) and
Manifold comment collector, both into `posts`. At least 700 ms between Arctic Shift calls.
**Acceptance criteria:**
- [ ] Backfill covers each flagship market's lifetime; re-runs are idempotent.
- [ ] No raw usernames stored.
**Verification:** `uv run pytest tests/unit/test_arctic_shift.py tests/unit/test_manifold.py`
**Dependencies:** Task 3
**Files:** `collect/arctic_shift.py`, `collect/manifold.py`, tests + fixtures, `registry/markets.yaml`
**Scope:** M

#### Task 11: Relevance filter, stance client and benchmark
**Description:** Keyword/entity relevance filter; Ollama client for Qwen3.5-9B with thinking
off and a JSON schema for `{label, confidence}`; versioned prompt v1; `rp classify` and
`rp bench-stance`.
**Acceptance criteria:**
- [ ] Every model response validates against the schema; invalid output is retried once, then logged.
- [ ] Labels are stored with `model` and `prompt_version`; older labels are never overwritten.
- [ ] `bench-stance --n 200` reports posts/minute on the M3 Air.
**Verification:** unit tests with a stubbed model; `uv run rp bench-stance --n 200`
**Dependencies:** Tasks 3, 10
**Files:** `stance/{relevance,prompt,client}.py`, `tests/unit/test_stance.py`
**Scope:** M

#### Task 12: Labelling page
**Description:** A Streamlit page that shows a market's resolution text and one post at a
time for Sam to label; exports `labels/stance_labels.csv` with IDs and labels only. Sam
then labels about 300 posts across ≥3 markets.
**Acceptance criteria:**
- [ ] Labels save as they are made; the CSV contains no post text.
- [ ] Sampling draws across markets and sources, not just the newest posts.
**Verification:** label 10 posts and inspect the CSV.
**Dependencies:** Task 10
**Files:** `dashboard/label.py`, `labels/stance_labels.csv`
**Scope:** S

#### Task 13: Classifier accuracy evaluation
**Description:** Slow test computing macro-F1 and a confusion matrix against Sam's labels;
iterate the prompt (bumping `prompt_version`) until the target is met or the gap is understood.
**Acceptance criteria:**
- [ ] Macro-F1 ≥ 0.70, or a written note on why not and what to try (success criterion 4).
**Verification:** `uv run pytest -m slow`
**Dependencies:** Tasks 11, 12
**Files:** `tests/slow/test_stance_accuracy.py`, `stance/prompt.py`
**Scope:** S

#### Task 14: Stance index and jump drill-down
**Description:** Hourly, source-weighted stance index per market as a dashboard lane;
selecting a jump lists the posts and headlines from the preceding 72 hours, as links.
**Acceptance criteria:**
- [ ] Stance lane shares the time axis with price and attention.
- [ ] Jump drill-down lists the prior 72 h of posts with stance labels and links.
- [ ] One market loads in under 5 s on the M3 Air (success criterion 6).
**Verification:** `uv run pytest tests/unit/test_index.py`; time the dashboard load.
**Dependencies:** Tasks 6, 11
**Files:** `signals/index.py`, `dashboard/app.py`, `tests/unit/test_index.py`
**Scope:** M

### Checkpoint C: MVP complete
- [ ] All seven success criteria in SPEC.md are met.
- [ ] Review with Sam: what the flagship shows, and whether to proceed to the panel event study.

## Parallelization

- After Task 1: Tasks 2 and 3 are independent.
- After Task 4: Tasks 5–7 (prices) and Tasks 8–9 (attention) can run in parallel.
- Task 10 needs only the registry, so text backfill can start early; it runs slowly because
  of rate limits, so starting it in the background early pays off.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Too few informative jumps for a panel | High | Task 7 measures it before any NLP work; Checkpoint B is an explicit go/no-go |
| Polymarket or Kalshi history too shallow or coarse | Medium | Task 5 measures it; Manifold's full bet history is the fallback |
| Laptop sleeps and the Bluesky logger has gaps | Medium | Gaps are recorded, not hidden; cloud server is a tracked open question |
| Arctic Shift slow or down (volunteer-run) | Medium | Raw cache plus resumable backfill; start Task 10 early |
| Qwen3.5-9B too slow for the post volume | Medium | Relevance filter first; `bench-stance` measures it; "System 1" models are the fallback |
| Hand-labelling 300 posts takes longer than expected | Low | Labelling page optimised for speed; 300 is a target, not a gate for earlier tasks |

## Open questions

- Which subreddits count as on-topic for the flagship (needed by Task 10)?
- Single labeller, or a second person to measure agreement (Task 12)?
