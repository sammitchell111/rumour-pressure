"""Opt-in: run with `uv run pytest -m live`. Connects to the real Jetstream for ~20 s."""

import asyncio
from datetime import UTC, datetime

import pytest

from rumour_pressure.collect import bluesky as bs

pytestmark = pytest.mark.live


class CountingMatcher(bs.Matcher):
    """Matches everything, so a short run is guaranteed to stage something."""

    def __init__(self):
        super().__init__(["the"])

    def matches(self, text: str) -> bool:
        return True


def test_jetstream_streams_posts(tmp_path):
    logger = bs.BlueskyLogger(CountingMatcher(), "live-test", tmp_path)

    async def run_briefly():
        stop = asyncio.Event()
        task = asyncio.create_task(logger.run(stop=stop))
        await asyncio.sleep(20)
        stop.set()
        await asyncio.wait_for(task, timeout=30)

    asyncio.run(run_briefly())
    staged = bs.read_staged(tmp_path, "posts")
    assert logger.posts_staged > 0
    newest = max(s["ts_utc"] for s in staged if s["type"] == "post")
    age = datetime.now(UTC) - datetime.fromisoformat(newest)
    assert age.total_seconds() < 120
