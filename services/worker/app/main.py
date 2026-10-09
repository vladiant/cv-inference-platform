"""Worker: consumes 'images:uploaded' events from Redis, fetches the raw
image from object storage, calls the C++ inference service over gRPC,
and persists the result to Postgres.

Run as N replicas in the same Redis consumer group ("workers") so that
scaling the pool is a deployment-count change, not a code change.
"""
import asyncio
import json
import os
import signal
import time
from datetime import datetime

import asyncpg
import grpc
import redis.asyncio as redis
import aioboto3

import inference_pb2
import inference_pb2_grpc

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql://cvplatform:cvplatform@localhost:5432/cvplatform")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "cvplatform")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "cvplatform123")
INFERENCE_GRPC_ADDR = os.getenv("INFERENCE_GRPC_ADDR", "localhost:50051")
BUCKET_NAME = os.getenv("IMAGE_BUCKET", "images-raw")

STREAM = "images:uploaded"
GROUP = "workers"
CONSUMER = f"worker-{os.getenv('HOSTNAME') or os.getpid()}"


async def ensure_group(r: redis.Redis):
    try:
        await r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


async def fetch_image(s3_session: aioboto3.Session, image_id: str) -> bytes:
    async with s3_session.client(
        "s3", endpoint_url=f"http://{MINIO_ENDPOINT}",
        aws_access_key_id=MINIO_ACCESS_KEY, aws_secret_access_key=MINIO_SECRET_KEY,
    ) as s3:
        obj = await s3.get_object(Bucket=BUCKET_NAME, Key=image_id)
        return await obj["Body"].read()


async def run_inference(stub, image_id: str, image_data: bytes) -> inference_pb2.InferResponse:
    request = inference_pb2.InferRequest(
        image_id=image_id, image_data=image_data, operation="face_detect"
    )
    return await stub.InferImage(request, timeout=10.0)


async def persist_result(pool: asyncpg.Pool, image_id: str, payload: dict, response) -> None:
    # Bind uploaded_at from the event payload (the exact ISO-8601 string
    # ingestion emitted) so the conflict target matches the seeded pending
    # row to microsecond precision rather than inventing a new now().
    uploaded_at = datetime.fromisoformat(payload["uploaded_at"])
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO images (image_id, filename, content_type, size_bytes, uploaded_at,
                                 processed_at, success, error_message, processing_ms, detections)
            VALUES ($1, $2, $3, $4, $5, now(), $6, $7, $8, $9)
            ON CONFLICT (image_id, uploaded_at) DO UPDATE SET
                processed_at = now(),
                success = EXCLUDED.success,
                error_message = EXCLUDED.error_message,
                processing_ms = EXCLUDED.processing_ms,
                detections = EXCLUDED.detections
            """,
            image_id,
            payload["filename"],
            payload["content_type"],
            payload["size_bytes"],
            uploaded_at,
            response.success,
            response.error_message,
            response.processing_ms,
            json.dumps([
                {"label": d.label, "confidence": d.confidence, "x": d.x, "y": d.y,
                 "width": d.width, "height": d.height}
                for d in response.detections
            ]),
        )


async def main():
    r = redis.from_url(REDIS_URL, decode_responses=True)
    await ensure_group(r)
    pool = await asyncpg.create_pool(POSTGRES_DSN)
    s3_session = aioboto3.Session()
    channel = grpc.aio.insecure_channel(INFERENCE_GRPC_ADDR)
    stub = inference_pb2_grpc.InferenceStub(channel)

    # Graceful shutdown: SIGTERM (HPA scale-down / rolling update) and SIGINT
    # set this event. The consume loop breaks between messages, leaving any
    # in-flight message un-acked so Redis redelivers it, then we release the
    # Redis client, asyncpg pool, and gRPC channel cleanly before exit.
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:  # pragma: no cover - non-Unix fallback
            signal.signal(sig, lambda *_: stop_event.set())

    print(f"[{CONSUMER}] started, consuming {STREAM}/{GROUP}", flush=True)

    try:
        while not stop_event.is_set():
            entries = await r.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=1, block=5000)
            if not entries:
                continue
            for _stream, messages in entries:
                for message_id, fields in messages:
                    if stop_event.is_set():
                        break
                    payload = json.loads(fields["data"])
                    image_id = payload["image_id"]
                    t0 = time.monotonic()
                    try:
                        image_data = await fetch_image(s3_session, image_id)
                        response = await run_inference(stub, image_id, image_data)
                        await persist_result(pool, image_id, payload, response)
                        await r.xack(STREAM, GROUP, message_id)
                        print(f"[{CONSUMER}] processed {image_id} in {time.monotonic()-t0:.3f}s", flush=True)
                    except Exception as exc:  # noqa: BLE001 - worker must never die on one bad message
                        print(f"[{CONSUMER}] failed on {image_id}: {exc}", flush=True)
                        # left un-acked; will be reclaimed via XCLAIM by a monitoring
                        # process in a full implementation (not included in this scaffold)
    finally:
        print(f"[{CONSUMER}] shutting down, releasing resources", flush=True)
        await r.aclose()
        await pool.close()
        await channel.close()


if __name__ == "__main__":
    asyncio.run(main())
