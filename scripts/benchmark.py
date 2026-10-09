"""Benchmarks the ingestion API under three client strategies to make the
"why parallelize" argument with numbers instead of assertion:

  sync         - one request at a time, blocking
  asyncio      - N concurrent requests via aiohttp
  multiprocess - N worker processes each firing requests

This measures *client-side* throughput against the ingestion endpoint
(which itself just stores bytes and emits an event) -- it demonstrates
the client-side parallelization patterns referenced in the job
descriptions, not the server's inference throughput, which is a
separate, GPU/CPU-bound concern benchmarked on cv-inference-cpp directly.
"""
import argparse
import asyncio
import multiprocessing
import time
from pathlib import Path

import requests
import aiohttp

SAMPLE_IMAGE = Path(__file__).parent / "sample.jpg"


def _one_sync_request(url: str) -> float:
    t0 = time.monotonic()
    with open(SAMPLE_IMAGE, "rb") as f:
        requests.post(url, files={"file": ("sample.jpg", f, "image/jpeg")}, timeout=30)
    return time.monotonic() - t0


def run_sync(url: str, n: int) -> list[float]:
    return [_one_sync_request(url) for _ in range(n)]


async def _one_async_request(session, url: str) -> float:
    t0 = time.monotonic()
    with open(SAMPLE_IMAGE, "rb") as f:
        data = f.read()
    form = aiohttp.FormData()
    form.add_field("file", data, filename="sample.jpg", content_type="image/jpeg")
    async with session.post(url, data=form) as resp:
        await resp.read()
    return time.monotonic() - t0


async def run_async(url: str, n: int, concurrency: int) -> list[float]:
    sem = asyncio.Semaphore(concurrency)

    async def bounded(session):
        async with sem:
            return await _one_async_request(session, url)

    async with aiohttp.ClientSession() as session:
        return await asyncio.gather(*(bounded(session) for _ in range(n)))


def _worker_batch(url: str, count: int) -> list[float]:
    return [_one_sync_request(url) for _ in range(count)]


def run_multiprocess(url: str, n: int, workers: int) -> list[float]:
    per_worker = n // workers
    with multiprocessing.Pool(workers) as pool:
        batches = pool.starmap(_worker_batch, [(url, per_worker)] * workers)
    return [t for batch in batches for t in batch]


def report(name: str, latencies: list[float], wall_seconds: float):
    latencies = sorted(latencies)
    n = len(latencies)
    p50 = latencies[int(n * 0.50)]
    p95 = latencies[int(n * 0.95)] if n > 1 else latencies[0]
    print(f"{name:>14}: {n} requests in {wall_seconds:.2f}s "
          f"-> {n / wall_seconds:.1f} img/s, p50={p50*1000:.0f}ms, p95={p95*1000:.0f}ms")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000/images")
    parser.add_argument("--images", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=20)
    args = parser.parse_args()

    if not SAMPLE_IMAGE.exists():
        raise SystemExit(f"place a sample.jpg at {SAMPLE_IMAGE} before running")

    t0 = time.monotonic()
    lat = run_sync(args.url, args.images)
    report("sync", lat, time.monotonic() - t0)

    t0 = time.monotonic()
    lat = asyncio.run(run_async(args.url, args.images, args.concurrency))
    report("asyncio", lat, time.monotonic() - t0)

    t0 = time.monotonic()
    lat = run_multiprocess(args.url, args.images, workers=min(args.concurrency, multiprocessing.cpu_count()))
    report("multiprocess", lat, time.monotonic() - t0)


if __name__ == "__main__":
    main()
