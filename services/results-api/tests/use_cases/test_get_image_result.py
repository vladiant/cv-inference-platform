"""Unit tests for the GetImageResult cache-aside use case with fake ports.

No Postgres or Redis is required -- the repository and cache are in-memory
fakes.
"""
import asyncio
from datetime import datetime, timezone

from app.domain.image_result import ImageResult
from app.use_cases.get_image_result import GetImageResult


class FakeRepository:
    def __init__(self, result: ImageResult | None) -> None:
        self._result = result
        self.find_calls = 0

    async def find_by_id(self, image_id: str) -> ImageResult | None:
        self.find_calls += 1
        return self._result


class FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.sets: list[tuple[str, str, int]] = []

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self.store[key] = value
        self.sets.append((key, value, ttl_seconds))


def _done_result() -> ImageResult:
    return ImageResult(
        image_id="id-1",
        filename="x.jpg",
        uploaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        processed_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        success=True,
        error_message=None,
        processing_ms=42,
        detections=[],
    )


def _pending_result() -> ImageResult:
    return ImageResult(
        image_id="id-2",
        filename="y.jpg",
        uploaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        processed_at=None,
        success=None,
        error_message=None,
        processing_ms=None,
        detections=[],
    )


def test_miss_then_db_then_cache_populated_with_long_ttl_for_done():
    repo = FakeRepository(_done_result())
    cache = FakeCache()
    use_case = GetImageResult(repo, cache)

    result = asyncio.run(use_case.execute("id-1"))

    assert result is not None and result.status == "done"
    assert repo.find_calls == 1
    # 'done' results cache for an hour.
    assert cache.sets[0][2] == 3600


def test_pending_result_cached_with_short_ttl():
    repo = FakeRepository(_pending_result())
    cache = FakeCache()
    use_case = GetImageResult(repo, cache)

    result = asyncio.run(use_case.execute("id-2"))

    assert result is not None and result.status == "pending"
    # Non-done results use a short TTL because they change soon.
    assert cache.sets[0][2] == 5


def test_cache_hit_skips_the_repository():
    repo = FakeRepository(_done_result())
    cache = FakeCache()
    use_case = GetImageResult(repo, cache)

    # Prime the cache via a first (miss) call.
    first = asyncio.run(use_case.execute("id-1"))
    assert repo.find_calls == 1

    # Second call is served from cache -- repo is not consulted again.
    second = asyncio.run(use_case.execute("id-1"))
    assert repo.find_calls == 1
    assert second is not None
    assert second.image_id == first.image_id
    assert second.processing_ms == first.processing_ms


def test_missing_image_returns_none_and_is_not_cached():
    repo = FakeRepository(None)
    cache = FakeCache()
    use_case = GetImageResult(repo, cache)

    result = asyncio.run(use_case.execute("missing"))

    assert result is None
    assert cache.sets == []
