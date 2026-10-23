"""The market registry: which markets we study, their rules text and entity keywords.

Lives in `registry/markets.yaml` (committed). Build it with `rp registry find` to see
candidates and `rp registry add` to fetch a market's full details and record it.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from rumour_pressure.store.models import MarketRow, UtcDatetime, Venue

DEFAULT_PATH = Path("registry/markets.yaml")


class RegistryMarket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_id: str  # "<venue>:<venue's own id>"
    venue: Venue
    venue_ref: dict[str, Any]  # whatever the venue's APIs need (ids, tickers, token ids)
    group: str  # e.g. "pregnancy", "wedding"
    question: str
    resolution_text: str
    url: str
    close_time: UtcDatetime | None = None
    closed: bool = False
    entity_keys: list[str] = Field(default_factory=list)

    def to_row(self) -> MarketRow:
        return MarketRow(
            market_id=self.market_id,
            venue=self.venue,
            question=self.question,
            resolution_text=self.resolution_text,
            url=self.url,
            close_time=self.close_time,
            entity_keys=self.entity_keys,
        )


class Registry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    markets: list[RegistryMarket] = Field(default_factory=list)
    extra_live_keywords: list[str] = Field(default_factory=list)
    subreddits: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> "Registry":
        ids = [m.market_id for m in self.markets]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate market_id(s): {sorted(dupes)}")
        return self

    def upsert(self, market: RegistryMarket) -> "Registry":
        kept = [m for m in self.markets if m.market_id != market.market_id]
        return self.model_copy(update={"markets": [*kept, market]})

    def get(self, market_id: str) -> RegistryMarket:
        for m in self.markets:
            if m.market_id == market_id:
                return m
        raise KeyError(market_id)

    def live_keywords(self) -> list[str]:
        keys = {k for m in self.markets for k in m.entity_keys} | set(self.extra_live_keywords)
        return sorted(keys)


def load_registry(path: Path = DEFAULT_PATH) -> Registry:
    if not Path(path).exists():
        return Registry()
    return Registry.model_validate(yaml.safe_load(Path(path).read_text()) or {})


def save_registry(registry: Registry, path: Path = DEFAULT_PATH) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = registry.model_dump(mode="json")
    data["markets"] = sorted(data["markets"], key=lambda m: (m["group"], m["market_id"]))
    Path(path).write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100))
