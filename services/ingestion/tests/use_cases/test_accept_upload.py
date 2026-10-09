"""Unit tests for the AcceptUpload use case using in-memory fake ports.

These tests exercise pure application logic with fakes -- no MinIO, Redis,
or Postgres is required.
"""
import asyncio

import pytest

from app.domain.image import ImageUpload
from app.use_cases.accept_upload import AcceptUpload


class FakeObjectStore:
    def __init__(self) -> None:
        self.puts: list[tuple[str, bytes, str]] = []
        self.calls: list[str] = []

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.calls.append("put")
        self.puts.append((key, data, content_type))


class FakeMetadataRepository:
    def __init__(self) -> None:
        self.rows: list[ImageUpload] = []
        self.calls: list[str] = []

    async def insert_pending(self, upload: ImageUpload) -> None:
        self.calls.append("insert_pending")
        self.rows.append(upload)


class FakeEventPublisher:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self.calls: list[str] = []

    async def publish(self, stream: str, payload: dict) -> None:
        self.calls.append("publish")
        self.events.append((stream, payload))


def _build() -> tuple[AcceptUpload, FakeObjectStore, FakeMetadataRepository, FakeEventPublisher]:
    store = FakeObjectStore()
    metadata = FakeMetadataRepository()
    publisher = FakeEventPublisher()
    return AcceptUpload(store, metadata, publisher), store, metadata, publisher


def test_happy_path_stores_seeds_and_publishes():
    use_case, store, metadata, publisher = _build()

    upload = asyncio.run(use_case.execute("cat.jpg", "image/jpeg", b"abc"))

    assert isinstance(upload, ImageUpload)
    assert upload.filename == "cat.jpg"
    assert upload.content_type == "image/jpeg"
    assert upload.size_bytes == 3

    # Bytes were stored under the image_id key.
    assert store.puts == [(upload.image_id, b"abc", "image/jpeg")]
    # A pending row was seeded with exactly the upload metadata.
    assert metadata.rows == [upload]
    # The published event payload mirrors the stored metadata.
    stream, payload = publisher.events[0]
    assert stream == "images:uploaded"
    assert payload == {
        "image_id": upload.image_id,
        "filename": upload.filename,
        "content_type": upload.content_type,
        "size_bytes": upload.size_bytes,
        "uploaded_at": upload.uploaded_at.isoformat(),
    }


def test_ordering_put_then_insert_pending_then_publish():
    use_case, store, metadata, publisher = _build()

    asyncio.run(use_case.execute("dog.png", "image/png", b"xy"))

    # The design mandates: put bytes -> insert pending row -> publish event.
    order = store.calls + metadata.calls + publisher.calls
    assert order == ["put", "insert_pending", "publish"]


def test_event_is_not_published_when_pending_insert_fails():
    """Edge case: if seeding the pending row raises, the event must not fire
    (ordering guarantees publish happens strictly after the insert)."""
    store = FakeObjectStore()
    publisher = FakeEventPublisher()

    class ExplodingMetadata:
        async def insert_pending(self, upload: ImageUpload) -> None:
            raise RuntimeError("db down")

    use_case = AcceptUpload(store, ExplodingMetadata(), publisher)

    with pytest.raises(RuntimeError, match="db down"):
        asyncio.run(use_case.execute("x.jpg", "image/jpeg", b"z"))

    assert store.puts, "bytes should already be stored before the failure"
    assert publisher.events == [], "no event may be published if seeding failed"
