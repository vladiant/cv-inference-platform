"""Application logic for accepting an image upload.

Depends only on domain types and on abstract ports (ObjectStore,
EventPublisher) — never on a concrete library. The adapters/ layer
supplies the concrete implementations at wiring time.
"""
from typing import Protocol

from app.domain.image import ImageUpload


class ObjectStore(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...


class MetadataRepository(Protocol):
    async def insert_pending(self, upload: ImageUpload) -> None: ...


class EventPublisher(Protocol):
    async def publish(self, stream: str, payload: dict) -> None: ...


class AcceptUpload:
    """Use case: store the raw bytes, seed a ``pending`` metadata row,
    then announce that they exist.

    Deliberately does nothing CV-related. If this method ever imports
    OpenCV, that's a sign the layering has been violated. Writing the
    metadata row is bookkeeping (the same category as emitting the
    event), not computer-vision work, so it stays inside the boundary.
    """

    def __init__(
        self,
        store: ObjectStore,
        metadata: MetadataRepository,
        publisher: EventPublisher,
    ):
        self._store = store
        self._metadata = metadata
        self._publisher = publisher

    async def execute(self, filename: str, content_type: str, data: bytes) -> ImageUpload:
        upload = ImageUpload.new(filename, content_type, len(data))
        # Per-request ordering: put bytes -> insert pending row -> publish event.
        await self._store.put(upload.image_id, data, content_type)
        await self._metadata.insert_pending(upload)
        await self._publisher.publish(
            "images:uploaded",
            {
                "image_id": upload.image_id,
                "filename": upload.filename,
                "content_type": upload.content_type,
                "size_bytes": upload.size_bytes,
                "uploaded_at": upload.uploaded_at.isoformat(),
            },
        )
        return upload
