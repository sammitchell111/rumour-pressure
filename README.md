# rumour-pressure

Does online rumour about celebrity life events lead, lag or merely mirror
prediction-market prices on long-horizon culture questions?

- [SPEC.md](SPEC.md) — what we're building and how we'll know it's done
- [PLAN.md](PLAN.md) — ordered tasks with acceptance checks

## Setup

```
uv sync
uv run rp init-db
uv run pytest
```

Data lives in `data/` (gitignored); set `RP_DATA_DIR` to put it elsewhere.
