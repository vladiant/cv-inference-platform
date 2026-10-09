"""Concrete MetadataRepository adapter backed by asyncpg (Postgres).

This is the only file in the ingestion service allowed to import asyncpg.
It writes the ``pending`` metadata row that ingestion owns -- bookkeeping
only, never any computer-vision work.
"""
import asyncpg

from app.domain.image import ImageUpload


class PostgresMetadataRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def insert_pending(self, upload: ImageUpload) -> None:
        """Seed a ``pending`` row (processed_at/success/... left NULL).

        ``ON CONFLICT (image_id, uploaded_at) DO NOTHING`` keeps a
        redelivered/retried upload idempotent: the conflict target is the
        full primary key because ``images`` is partitioned by
        ``uploaded_at`` and has no unique constraint on ``image_id`` alone.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO images (image_id, filename, content_type,
                                    size_bytes, uploaded_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (image_id, uploaded_at) DO NOTHING
                """,
                upload.image_id,
                upload.filename,
                upload.content_type,
                upload.size_bytes,
                upload.uploaded_at,
            )
