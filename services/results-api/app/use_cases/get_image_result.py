import json
from typing import Optional, Protocol

from app.domain.image_result import ImageResult, Detection


class ResultRepository(Protocol):
    async def find_by_id(self, image_id: str) -> Optional[ImageResult]: ...


class ResultCache(Protocol):
    async def get(self, key: str) -> Optional[str]: ...
    async def set(self, key: str, value: str, ttl_seconds: int) -> None: ...


class GetImageResult:
    """Cache-aside read: check Redis first, fall back to Postgres, then
    populate the cache. A `pending`/`failed` result is cached with a much
    shorter TTL than a `done` one, since it's likely to change soon.
    """

    def __init__(self, repo: ResultRepository, cache: ResultCache):
        self._repo = repo
        self._cache = cache

    async def execute(self, image_id: str) -> Optional[ImageResult]:
        cache_key = f"image_result:{image_id}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return self._deserialize(cached)

        result = await self._repo.find_by_id(image_id)
        if result is None:
            return None

        ttl = 3600 if result.status == "done" else 5
        await self._cache.set(cache_key, self._serialize(result), ttl_seconds=ttl)
        return result

    @staticmethod
    def _serialize(result: ImageResult) -> str:
        return json.dumps({
            "image_id": result.image_id,
            "filename": result.filename,
            "uploaded_at": result.uploaded_at.isoformat(),
            "processed_at": result.processed_at.isoformat() if result.processed_at else None,
            "success": result.success,
            "error_message": result.error_message,
            "processing_ms": result.processing_ms,
            "detections": [d.__dict__ for d in result.detections],
        })

    @staticmethod
    def _deserialize(raw: str) -> ImageResult:
        from datetime import datetime
        data = json.loads(raw)
        return ImageResult(
            image_id=data["image_id"],
            filename=data["filename"],
            uploaded_at=datetime.fromisoformat(data["uploaded_at"]),
            processed_at=datetime.fromisoformat(data["processed_at"]) if data["processed_at"] else None,
            success=data["success"],
            error_message=data["error_message"],
            processing_ms=data["processing_ms"],
            detections=[Detection(**d) for d in data["detections"]],
        )
