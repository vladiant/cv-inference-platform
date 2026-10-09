"""FastAPI entrypoint. This is the only file that knows both the web
framework and the concrete adapters — it exists purely to wire them
together and expose HTTP endpoints over the use case.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException

from app.adapters.s3_object_store import S3ObjectStore
from app.adapters.redis_event_publisher import RedisEventPublisher
from app.use_cases.accept_upload import AcceptUpload
from app.infra.config import settings

store = S3ObjectStore(
    settings.minio_endpoint, settings.minio_access_key, settings.minio_secret_key, settings.bucket_name
)
publisher = RedisEventPublisher(settings.redis_url)
accept_upload = AcceptUpload(store, publisher)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.ensure_bucket()
    yield


app = FastAPI(title="ingestion", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/images")
async def upload_image(file: UploadFile = File(...)):
    if file.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(status_code=415, detail="only jpeg/png supported")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    upload = await accept_upload.execute(file.filename, file.content_type, data)
    return {"image_id": upload.image_id, "status": "queued"}
