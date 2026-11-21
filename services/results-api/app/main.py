"""@file
@brief FastAPI entrypoint and HTTP surface for the read-only results API.

Wires the Postgres result repository and the Redis cache into the
GetImageResult use case and exposes single-image lookup plus a paginated
recent-images listing. This service only ever reads the ``images`` row.
"""
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, HTTPException, Query

from app.adapters.postgres_repository import PostgresResultRepository
from app.adapters.redis_cache import RedisResultCache
from app.use_cases.get_image_result import GetImageResult
from app.infra.config import settings

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await asyncpg.create_pool(settings.postgres_dsn)
    repo = PostgresResultRepository(pool)
    cache = RedisResultCache(settings.redis_url)
    state["pool"] = pool
    state["repo"] = repo
    state["get_result"] = GetImageResult(repo, cache)
    try:
        yield
    finally:
        await pool.close()
        await cache.close()


app = FastAPI(title="results-api", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    """@brief Liveness probe. Returns a static OK without touching backends."""
    return {"status": "ok"}


@app.get("/images/{image_id}")
async def get_image(image_id: str):
    """@brief Cache-aside lookup of one image result; 404 if unknown.

    @param image_id The image identifier to look up.
    @return The full result record (status, timings, detections).
    """
    result = await state["get_result"].execute(image_id)
    if result is None:
        raise HTTPException(status_code=404, detail="not found")
    return {
        "image_id": result.image_id,
        "filename": result.filename,
        "status": result.status,
        "uploaded_at": result.uploaded_at.isoformat(),
        "processed_at": result.processed_at.isoformat() if result.processed_at else None,
        "processing_ms": result.processing_ms,
        "error_message": result.error_message,
        "detections": [d.__dict__ for d in result.detections],
    }


@app.get("/images")
async def list_images(limit: int = Query(20, le=100), offset: int = Query(0, ge=0)):
    """@brief Paginated listing of recent images ordered by upload time.

    @param limit Page size (max 100).
    @param offset Row offset into the recent-images ordering.
    @return A page of lightweight image summaries.
    """
    results = await state["repo"].list_recent(limit, offset)
    return {
        "limit": limit,
        "offset": offset,
        "items": [
            {"image_id": r.image_id, "filename": r.filename, "status": r.status,
             "uploaded_at": r.uploaded_at.isoformat()}
            for r in results
        ],
    }
