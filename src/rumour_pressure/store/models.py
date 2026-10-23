"""Row schemas. Each model maps to one warehouse table; every row is validated before write.

All timestamps must be timezone-aware and are normalised to UTC.
"""

from datetime import UTC, datetime
from typing import Annotated, ClassVar, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]

Venue = Literal["polymarket", "kalshi", "manifold"]
StanceLabel = Literal["supports_yes", "supports_no", "irrelevant"]


class Row(BaseModel):
    """Base for warehouse rows. Subclasses set the table name and its primary key."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    table: ClassVar[str]
    key: ClassVar[tuple[str, ...]]


class MarketRow(Row):
    table = "markets"
    key = ("market_id",)

    market_id: str
    venue: Venue
    question: str
    resolution_text: str
    url: str
    close_time: UtcDatetime | None = None
    entity_keys: list[str] = Field(default_factory=list)


class PriceRow(Row):
    table = "prices"
    key = ("market_id", "ts_utc")

    market_id: str
    ts_utc: UtcDatetime
    price: Probability
    volume: Annotated[float, Field(ge=0)] | None = None
    n_trades: Annotated[int, Field(ge=0)] | None = None


class AttentionRow(Row):
    table = "attention"
    key = ("source", "entity", "metric", "ts_utc")

    source: str
    entity: str
    ts_utc: UtcDatetime
    metric: str
    value: float


class PostRow(Row):
    table = "posts"
    key = ("post_id",)

    post_id: str  # "<source>:<native id>"
    source: str
    ts_utc: UtcDatetime
    channel: str  # subreddit, feed, outlet domain...
    author_hash: str | None  # salted hash; raw usernames are never stored
    text: str
    url: str
    collected_at: UtcDatetime


class StanceRow(Row):
    table = "stance"
    # prompt_version and model are part of the key, so a new prompt adds labels
    # rather than overwriting older ones.
    key = ("post_id", "market_id", "model", "prompt_version")

    post_id: str
    market_id: str
    label: StanceLabel
    confidence: Probability
    model: str
    prompt_version: str
    classified_at: UtcDatetime


class JumpRow(Row):
    table = "jumps"
    key = ("market_id", "ts_start", "params_hash")

    market_id: str
    ts_start: UtcDatetime
    ts_end: UtcDatetime
    delta: float
    residual: float
    params_hash: str
    volume: float | None = None
    n_trades: int | None = None


class LoggerGapRow(Row):
    table = "logger_gaps"
    key = ("source", "gap_start")

    source: str
    gap_start: UtcDatetime
    gap_end: UtcDatetime | None = None
    reason: str = ""
