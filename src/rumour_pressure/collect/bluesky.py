"""Bluesky live logger (Jetstream) and the ingest step that loads its output.

The logger runs continuously and never opens the warehouse: DuckDB allows one writer per
file, and the logger must not block the dashboard or the other collectors. It appends
matching posts, deletions and connection gaps to small daily JSONL files; `ingest_staged`
(run by `rp collect bluesky`) loads them into the warehouse.

Privacy: author DIDs are replaced by a salted hash in post IDs and `author_hash`. The post
URL still carries the DID so the dashboard can link to it; the warehouse is local-only.
Deletions are honoured: if an author deletes a post we stored, ingest removes it.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import ssl
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import websockets

from rumour_pressure.store import Warehouse
from rumour_pressure.store.models import LoggerGapRow, PostRow

log = logging.getLogger(__name__)

JETSTREAM_URL = "wss://jetstream2.us-east.bsky.network/subscribe"
POST_COLLECTION = "app.bsky.feed.post"
# On reconnect, replay from slightly before the last event seen; duplicates are harmless
# because ingest upserts on post_id.
CURSOR_REWIND_US = 5_000_000
MAX_BACKOFF_S = 60.0
KNOWN_IDS_FILE = "known_ids.txt"

__all__ = [
    "BlueskyLogger",
    "Deletion",
    "Matcher",
    "PostRow",
    "author_hash",
    "ingest_staged",
    "parse_message",
    "read_staged",
]


# --- matching and parsing -----------------------------------------------------


class Matcher:
    """Case-insensitive whole-phrase matcher: 'Swifties' does not match 'swiftly'."""

    def __init__(self, keywords: Iterable[str]):
        self.keywords = sorted({k.strip() for k in keywords if k.strip()}, key=len, reverse=True)
        if not self.keywords:
            raise ValueError("Matcher needs at least one keyword")
        alternatives = "|".join(re.escape(k) for k in self.keywords)
        self._pattern = re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)

    def matches(self, text: str) -> bool:
        return bool(self._pattern.search(text))


@dataclass(frozen=True)
class Deletion:
    post_id: str


def author_hash(did: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{did}".encode()).hexdigest()[:16]


def _post_id(did: str, rkey: str, salt: str) -> str:
    return f"bluesky:{author_hash(did, salt)}/{rkey}"


def parse_message(
    msg: dict[str, Any], matcher: Matcher, salt: str, collected_at: datetime
) -> PostRow | Deletion | None:
    """Turn one Jetstream event into a post, a deletion, or nothing.

    Timestamps use the relay's receipt time (`time_us`), not the client-supplied
    `createdAt`, which can be backdated.
    """
    commit = msg.get("commit")
    if msg.get("kind") != "commit" or not commit or commit.get("collection") != POST_COLLECTION:
        return None

    did, rkey = msg["did"], commit["rkey"]
    operation = commit.get("operation")

    if operation == "delete":
        return Deletion(post_id=_post_id(did, rkey, salt))
    if operation != "create":
        return None

    text = (commit.get("record") or {}).get("text") or ""
    if not matcher.matches(text):
        return None

    return PostRow(
        post_id=_post_id(did, rkey, salt),
        source="bluesky",
        ts_utc=datetime.fromtimestamp(msg["time_us"] / 1e6, tz=UTC),
        channel="jetstream",
        author_hash=author_hash(did, salt),
        text=text,
        url=f"https://bsky.app/profile/{did}/post/{rkey}",
        collected_at=collected_at,
    )


# --- staging files ------------------------------------------------------------


def _append(stage_dir: Path, kind: str, day: date, record: dict[str, Any]) -> None:
    stage_dir.mkdir(parents=True, exist_ok=True)
    path = stage_dir / f"{kind}-{day.isoformat()}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _staged_files(stage_dir: Path, kind: str) -> list[Path]:
    return sorted(stage_dir.glob(f"{kind}-*.jsonl"))


def _read_file(path: Path) -> list[dict[str, Any]]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            # The logger may be mid-write on today's file; a partial last line is expected.
            log.debug("skipping partial line in %s", path)
    return records


def read_staged(stage_dir: Path, kind: str) -> list[dict[str, Any]]:
    """All staged records of one kind ('posts' or 'gaps'), oldest file first."""
    return [r for path in _staged_files(stage_dir, kind) for r in _read_file(path)]


# --- the logger -----------------------------------------------------------------


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE"))


def _default_connect(url: str):
    return websockets.connect(
        url, ssl=_ssl_context(), open_timeout=20, ping_interval=20, max_size=None
    )


class BlueskyLogger:
    def __init__(
        self,
        matcher: Matcher,
        salt: str,
        stage_dir: Path,
        connect: Callable[[str], Any] = _default_connect,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        url: str = JETSTREAM_URL,
    ):
        self.matcher = matcher
        self.salt = salt
        self.stage_dir = Path(stage_dir)
        self.connect = connect
        self.sleep = sleep
        self.clock = clock
        self.url = url
        self.cursor: int | None = None
        self.posts_staged = 0
        # IDs of every post ever kept, persisted across restarts and ingests, so that only
        # deletions of *our* posts are staged (the network deletes ~2 posts per second).
        self._known_ids_path = self.stage_dir / KNOWN_IDS_FILE
        self.known_ids: set[str] = (
            set(self._known_ids_path.read_text().split())
            if self._known_ids_path.exists()
            else set()
        )

    def _remember(self, post_id: str) -> None:
        if post_id in self.known_ids:
            return
        self.known_ids.add(post_id)
        self.stage_dir.mkdir(parents=True, exist_ok=True)
        with self._known_ids_path.open("a", encoding="utf-8") as f:
            f.write(post_id + "\n")

    def _url(self) -> str:
        url = f"{self.url}?wantedCollections={POST_COLLECTION}"
        if self.cursor is not None:
            url += f"&cursor={self.cursor - CURSOR_REWIND_US}"
        return url

    def _handle(self, raw: str | bytes) -> None:
        msg = json.loads(raw)
        self.cursor = msg.get("time_us", self.cursor)
        now = self.clock()
        item = parse_message(msg, self.matcher, self.salt, now)
        if isinstance(item, PostRow):
            record = {"type": "post", **item.model_dump(mode="json")}
            _append(self.stage_dir, "posts", now.date(), record)
            self._remember(item.post_id)
            self.posts_staged += 1
        elif isinstance(item, Deletion) and item.post_id in self.known_ids:
            _append(self.stage_dir, "posts", now.date(), {"type": "deletion", **vars(item)})

    def _record_gap(self, start: datetime, end: datetime | None, reason: str) -> None:
        gap = LoggerGapRow(source="bluesky", gap_start=start, gap_end=end, reason=reason)
        _append(self.stage_dir, "gaps", start.date(), gap.model_dump(mode="json"))
        log.warning("bluesky gap %s -> %s: %s", start, end, reason)

    async def run(
        self, stop: asyncio.Event | None = None, max_connections: int | None = None
    ) -> None:
        """Stream until `stop` is set (or `max_connections` sessions end, for tests)."""
        connections = 0
        attempt = 0
        gap_start: datetime | None = None
        gap_reason = ""

        while not (stop and stop.is_set()):
            try:
                async with self.connect(self._url()) as ws:
                    if gap_start is not None:
                        self._record_gap(gap_start, self.clock(), gap_reason)
                        gap_start = None
                    attempt = 0
                    log.info("connected to jetstream")
                    async for raw in ws:
                        self._handle(raw)
                        if stop and stop.is_set():
                            return
                reason = "closed by server"
            except (OSError, TimeoutError, websockets.ConnectionClosed) as exc:
                reason = f"{type(exc).__name__}: {exc}"

            connections += 1
            if max_connections is not None and connections >= max_connections:
                return

            if gap_start is None:
                gap_start, gap_reason = self.clock(), reason
            delay = min(MAX_BACKOFF_S, 2.0**attempt)
            attempt += 1
            log.warning("jetstream disconnected (%s); retrying in %.0fs", reason, delay)
            await self.sleep(delay)


# --- ingest -----------------------------------------------------------------------


@dataclass(frozen=True)
class IngestSummary:
    posts: int
    deletions: int
    gaps: int


def ingest_staged(stage_dir: Path, wh: Warehouse, today: date | None = None) -> IngestSummary:
    """Load staged posts, deletions and gaps into the warehouse.

    Idempotent. Files from days before `today` are complete, so they are removed after a
    successful load; today's file is still being written and is kept.
    """
    today = today or datetime.now(UTC).date()
    stage_dir = Path(stage_dir)
    post_files = _staged_files(stage_dir, "posts")
    gap_files = _staged_files(stage_dir, "gaps")

    records = [r for path in post_files for r in _read_file(path)]
    posts = [
        PostRow(**{k: v for k, v in r.items() if k != "type"})
        for r in records
        if r.get("type") == "post"
    ]
    deleted = {r["post_id"] for r in records if r.get("type") == "deletion"}
    gaps = [LoggerGapRow(**r) for path in gap_files for r in _read_file(path)]

    wh.upsert(posts)
    wh.upsert(gaps)
    wh.delete_posts(deleted)

    for path in post_files + gap_files:
        file_day = date.fromisoformat(path.stem.split("-", 1)[1])
        if file_day < today:
            path.unlink()

    return IngestSummary(posts=len(posts), deletions=len(deleted), gaps=len(gaps))
