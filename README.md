# CV Inference Platform

A small, honest distributed system for ingesting images, running computer-vision inference on them at scale, and serving the results through a REST API.

It exists as a portfolio project mapping directly to the skills required for senior "Computer Vision Infrastructure" / "Image Processing Pipelines" roles:
Clean Architecture, async/parallel processing, database scaling & retention, Docker/Kubernetes, gRPC, and event-driven service boundaries.

## Why this exists

Most portfolio repos show a single script. This shows a *system*: services that don't trust each other's internals, communicate over well-defined contracts (REST + gRPC), scale independently, and make an explicit choice about what happens to data over time.

## Architecture

```
                 ┌─────────────┐        ┌────────────────────┐
  client ──HTTP──▶  ingestion  │──push──▶  Redis Stream      │
                 │  (FastAPI)  │        │  "images:uploaded" │
                 └─────────────┘        └──────────┬─────────┘
                        │                          │ consume (N workers, scaled by HPA)
                        ▼                          ▼
                 ┌─────────────┐            ┌──────────────┐        ┌─────────────────────┐
                 │  MinIO (S3) │◀───stores──│  worker      │──gRPC──▶  cv-inference-cpp   │
                 │  raw images │            │  (Python)    │        │  (C++, OpenCV)      │
                 └─────────────┘            └───────┬──────┘        └─────────────────────┘
                                                    │ writes metadata + result
                                                    ▼
                                             ┌──────────────┐
                                             │  PostgreSQL  │
                                             └──────┬───────┘
                                                    │ read
                                                    ▼
                                             ┌──────────────┐
                                             │ results-api  │◀── client polls/queries results
                                             │  (FastAPI)   │
                                             └──────────────┘
```

**Services**

| Service | Language | Responsibility |
|---|---|---|
| `ingestion` | Python / FastAPI | Accepts uploads, writes raw bytes to object storage, emits an `image.uploaded` event to a Redis Stream. Never touches CV logic. |
| `worker` | Python | Consumes events, calls the C++ inference service over gRPC, writes results + metadata to Postgres. Runs as a horizontally-scaled pool. |
| `cv-inference-cpp` | C++ / OpenCV / gRPC | Stateless inference microservice. Kept in C++ deliberately — this is the CPU-bound hot path, and it's the one place raw throughput matters more than developer velocity. |
| `results-api` | Python / FastAPI | Read-only query API over Postgres, with Redis-backed response caching and pagination. |

This is an **event-driven pipeline**, not a request/response chain: `ingestion` never blocks on inference, and `worker` count scales independently of `ingestion` traffic. That decoupling is the main architectural point of the project, not an afterthought.

## Clean Architecture

Each Python service follows the same internal layering, so the layering is a convention, not a one-off:

```
app/
├── domain/        # entities & value objects, no framework imports
├── use_cases/      # application logic, depends only on domain
├── adapters/       # FastAPI routers, gRPC clients, event consumers — depend inward
└── infra/          # DB sessions, object storage clients, config
```

Dependencies point inward only: `domain` knows nothing about FastAPI, Postgres, or Redis. This is what makes the worker's inference backend swappable (see `docs/design-decisions.md`) without touching business logic.

## Data retention strategy

Images and metadata are treated differently:

- **Raw images** (MinIO): lifecycle policy moves objects older than 7 days to a cold-storage bucket class, and deletes anything older than 90 days unless flagged `retain=true` in metadata.
- **Metadata + inference results** (Postgres): kept indefinitely, but the `images` table is partitioned by month (`created_at`) so old partitions can   be detached and archived to cold storage/Parquet without touching hot data.
- **Redis Stream**: consumer-group acknowledgement + a max length (`MAXLEN`)   so the stream self-trims once all consumer groups have caught up.

See `docs/design-decisions.md` for the reasoning and trade-offs.

## Prerequisites

- Docker Engine with Docker Compose v2
- Python 3.12+ for local static validation and ad-hoc scripts
- Enough local resources for the stack: PostgreSQL, Redis, MinIO, and the C++ inference container

## Running it locally

```bash
docker compose up --build
```

This brings up: `ingestion` (:8000), `results-api` (:8001), `cv-inference-cpp` (:50051, gRPC), 2x `worker`, `postgres`, `redis`, `minio`.

The Python worker generates its gRPC bindings from the shared `proto/inference.proto` file at image build time, and the C++ service compiles the same contract during its Docker build. The compose file intentionally avoids the obsolete `version:` field used by older Compose releases.

## Validation

```bash
docker compose config
python3 -m compileall services/ingestion/app services/worker/app services/results-api/app
```

These checks verify that the stack definition is valid and that the Python service source compiles cleanly before runtime startup.

Upload an image:

```bash
curl -F "file=@sample.jpg" http://localhost:8000/images
# => {"image_id": "..."}
```

Poll for the result:

```bash
curl http://localhost:8001/images/<image_id>
```

## Running it on Kubernetes

Manifests are in `k8s/`. They assume a local cluster (kind/minikube) with an image registry reachable by the cluster:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/
```

The `worker` deployment ships with a `HorizontalPodAutoscaler` keyed on CPU, so `kubectl apply` alone demonstrates the "scale the worker pool under load" story — see `scripts/benchmark.py` to generate that load.

## Benchmarking

```bash
python scripts/benchmark.py --images 500 --concurrency 50
```

Reports throughput (images/sec) and p50/p95 latency for three modes:
synchronous, `asyncio`-concurrent, and multiprocess — see the script for what's actually being compared and why the numbers differ.

## Repo layout

```
.
├── docker-compose.yml
├── k8s/                        # Deployments, Services, HPA, StatefulSets
├── proto/inference.proto       # shared gRPC contract
├── services/
│   ├── ingestion/
│   ├── worker/
│   ├── cv-inference-cpp/
│   └── results-api/
├── scripts/benchmark.py
└── docs/design-decisions.md
```

## Status

This is a portfolio scaffold: the architecture, contracts, and infra are real and runnable; the inference logic itself is intentionally a simple OpenCV operation (edge/face detection) rather than a production model, since the point is the *plumbing* around inference, not the model itself.
