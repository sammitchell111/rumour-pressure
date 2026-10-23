import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import websockets

from rumour_pressure.collect import bluesky as bs
from rumour_pressure.store import Warehouse

FIXTURE = Path(__file__).parents[1] / "fixtures" / "bluesky" / "messages.jsonl"
MESSAGES = [json.loads(line) for line in FIXTURE.read_text().splitlines()]
NOW = datetime(2026, 10, 23, 9, 5, tzinfo=UTC)
SALT = "test-salt"
MATCHER = bs.Matcher(["Taylor Swift", "Swifties", "Travis Kelce"])


def parse(msg):
    return bs.parse_message(msg, MATCHER, SALT, NOW)


# --- matching -----------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Taylor Swift is touring", True),
        ("taylor swift!", True),
        ("the SWIFTIES are loud", True),
        ("#TaylorSwift trending", False),  # hashtag form needs its own keyword
        ("she moved swiftly", False),
        ("Travis Kelce interview", True),
    ],
)
def test_matcher(text, expected):
    assert MATCHER.matches(text) is expected


# --- parsing ------------------------------------------------------------------


def test_matching_create_becomes_a_post_without_the_raw_did():
    post = parse(MESSAGES[0])
    assert isinstance(post, bs.PostRow)
    assert post.source == "bluesky"
    assert "alice" not in post.post_id
    assert post.author_hash == bs.author_hash("did:plc:alice000000000000000000", SALT)
    assert post.text.startswith("Is Taylor Swift")
    assert post.url.endswith("/post/3myjaaaaaaa2f")


def test_timestamp_is_server_receipt_time_not_client_claim():
    post = parse(MESSAGES[0])
    assert post.ts_utc == datetime.fromtimestamp(1792746015266964 / 1e6, tz=UTC)


def test_non_matching_posts_and_other_events_are_ignored():
    assert parse(MESSAGES[1]) is None  # pasta
    assert parse(MESSAGES[4]) is None  # account event
    assert parse(MESSAGES[5]) is None  # "swiftly"


def test_delete_maps_to_the_same_post_id_as_its_create():
    created = parse(MESSAGES[0])
    deleted = parse(MESSAGES[3])
    assert isinstance(deleted, bs.Deletion)
    assert deleted.post_id == created.post_id


def test_author_hash_is_stable_and_salted():
    did = "did:plc:alice000000000000000000"
    assert bs.author_hash(did, SALT) == bs.author_hash(did, SALT)
    assert bs.author_hash(did, SALT) != bs.author_hash(did, "other-salt")


# --- logger: reconnects and gaps ---------------------------------------------


class FakeConnection:
    """Async-iterable socket that yields messages then optionally drops."""

    def __init__(self, messages, drop: bool):
        self.messages = messages
        self.drop = drop

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for m in self.messages:
            yield json.dumps(m)
        if self.drop:
            raise websockets.ConnectionClosedError(None, None)


def run_logger(tmp_path, connections):
    urls = []
    conns = iter(connections)

    def connect(url):
        urls.append(url)
        return next(conns)

    async def no_sleep(_):
        return None

    logger = bs.BlueskyLogger(
        matcher=MATCHER,
        salt=SALT,
        stage_dir=tmp_path,
        connect=connect,
        sleep=no_sleep,
        clock=lambda: NOW,
    )
    asyncio.run(logger.run(max_connections=len(connections)))
    return urls


def test_a_dropped_connection_reconnects_and_records_one_gap(tmp_path):
    run_logger(
        tmp_path,
        [FakeConnection(MESSAGES[:2], drop=True), FakeConnection(MESSAGES[2:], drop=False)],
    )
    gaps = bs.read_staged(tmp_path, "gaps")
    assert len(gaps) == 1
    assert gaps[0]["gap_end"] is not None
    assert "ConnectionClosed" in gaps[0]["reason"]


def test_reconnect_rewinds_the_cursor_so_nothing_is_missed(tmp_path):
    urls = run_logger(
        tmp_path,
        [FakeConnection(MESSAGES[:2], drop=True), FakeConnection([], drop=False)],
    )
    assert "cursor" not in urls[0]
    expected = MESSAGES[1]["time_us"] - bs.CURSOR_REWIND_US
    assert f"cursor={expected}" in urls[1]


def test_only_matching_posts_and_deletions_are_staged(tmp_path):
    run_logger(tmp_path, [FakeConnection(MESSAGES, drop=False)])
    staged = bs.read_staged(tmp_path, "posts")
    kinds = sorted(s["type"] for s in staged)
    assert kinds == ["deletion", "post", "post"]


def test_deletions_of_posts_we_never_kept_are_not_staged(tmp_path):
    stranger_delete = {**MESSAGES[3], "did": "did:plc:stranger0000000000000000"}
    run_logger(tmp_path, [FakeConnection([stranger_delete], drop=False)])
    assert bs.read_staged(tmp_path, "posts") == []


def test_known_posts_survive_a_restart_so_later_deletions_still_apply(tmp_path):
    run_logger(tmp_path, [FakeConnection(MESSAGES[:1], drop=False)])  # Alice posts
    run_logger(tmp_path, [FakeConnection(MESSAGES[3:4], drop=False)])  # new process; she deletes
    kinds = [s["type"] for s in bs.read_staged(tmp_path, "posts")]
    assert kinds == ["post", "deletion"]


# --- ingest into the warehouse -----------------------------------------------


def test_ingest_loads_posts_applies_deletions_and_is_idempotent(tmp_path):
    stage = tmp_path / "stage"
    run_logger(
        stage,
        [FakeConnection(MESSAGES[:2], drop=True), FakeConnection(MESSAGES[2:], drop=False)],
    )
    with Warehouse(tmp_path / "wh.duckdb") as wh:
        first = bs.ingest_staged(stage, wh, today=NOW.date())
        second = bs.ingest_staged(stage, wh, today=NOW.date())
        texts = [t for (t,) in wh.query("select text from posts")]
        assert texts == ["the SWIFTIES have decoded another easter egg"]  # Alice deleted hers
        assert wh.count("logger_gaps") == 1
    assert first == second
