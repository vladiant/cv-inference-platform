import json
from typing import Optional

import asyncpg

from app.domain.image_result import ImageResult, Detection


class PostgresResultRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def find_by_id(self, image_id: str) -> Optional[ImageResult]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT image_id, filename, uploaded_at, processed_at,
                       success, error_message, processing_ms, detections
                FROM images WHERE image_id = $1
                """,
                image_id,
            )
        if row is None:
            return None
        detections_raw = json.loads(row["detections"]) if row["detections"] else []
        return ImageResult(
            image_id=row["image_id"],
            filename=row["filename"],
            uploaded_at=row["uploaded_at"],
            processed_at=row["processed_at"],
            success=row["success"],
            error_message=row["error_message"],
            processing_ms=row["processing_ms"],
            detections=[Detection(**d) for d in detections_raw],
        )

    async def list_recent(self, limit: int, offset: int) -> list[ImageResult]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT image_id, filename, uploaded_at, processed_at,
                       success, error_message, processing_ms, detections
                FROM images ORDER BY uploaded_at DESC LIMIT $1 OFFSET $2
                """,
                limit, offset,
            )
        results = []
        for row in rows:
            detections_raw = json.loads(row["detections"]) if row["detections"] else []
            results.append(ImageResult(
                image_id=row["image_id"], filename=row["filename"],
                uploaded_at=row["uploaded_at"], processed_at=row["processed_at"],
                success=row["success"], error_message=row["error_message"],
                processing_ms=row["processing_ms"],
                detections=[Detection(**d) for d in detections_raw],
            ))
        return results
