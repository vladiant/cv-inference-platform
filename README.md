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
                 │  MinIO (S3) │◀──fetch────│  worker      │──gRPC──▶  cv-inference-cpp   │
                 │  raw images │            │  (Python)    │        │  (C++, OpenCV)      │
                 └─────────────┘            └───────┬──────┘        └─────────────────────┘
                                                    │ updates the pending record with the result
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

The image record has a single linear lifecycle with a distinct owner per step:
`ingestion` **creates** a `pending` metadata row in Postgres (and stores the raw
bytes in MinIO) before emitting the event; `worker` later **updates** that row
with the inference result (`done`/`failed`); `results-api` only ever **reads**
it. Writing metadata is not CV work, so ingestion seeding the row does not cross
the "ingestion performs no CV" boundary — see `docs/design-decisions.md`.

**Services**

| Service | Language | Responsibility |
|---|---|---|
| `ingestion` | Python / FastAPI | Accepts uploads, writes raw bytes to object storage, writes an initial `pending` metadata row to Postgres, then emits an `image.uploaded` event to a Redis Stream. Performs no CV work — it never decodes an image or calls the inference service. |
| `worker` | Python | Consumes events, fetches the raw bytes, calls the C++ inference service over gRPC, and updates the `pending` record in Postgres with the inference result (`done`/`failed`). Runs as a horizontally-scaled pool. |
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

Images and metadata are *designed* to be treated differently. Because this is
an honest scaffold, the three retention ideas below are listed with their
**actual implementation status**, not as if all were live:

- **Redis Stream — enforced now.** Consumer-group acknowledgement plus a max
  length (`MAXLEN ~ 100_000`, approximate) applied on every publish, so the
  stream self-trims once consumers have caught up. This is the only retention
  rule the code actually applies.
- **Postgres partitioning — structurally present, not operationalized.** The
  `images` table really is `PARTITION BY RANGE (uploaded_at)` with a `DEFAULT`
  partition, so the structure exists and old partitions *could* be detached and
  archived. But no scheduled job pre-creates monthly partitions and nothing
  archives them, so in practice every row currently lands in `images_default`.
  Metadata is kept indefinitely.
- **MinIO object lifecycle — designed, not implemented.** The intended policy
  (tier objects to cold storage after 7 days, delete after 90 days unless
  flagged `retain=true`) is **not** configured anywhere, and no `retain`
  metadata field exists yet. It is documented future work, not a running
  feature.

See `docs/design-decisions.md` ("What retention is actually enforced today")
for the reasoning and the precise enforced / structural / intended split.

## Prerequisites

- Docker Engine with Docker Compose v2
- Python 3.12+ for local static validation and ad-hoc scripts
- Enough local resources for the stack: PostgreSQL, Redis, MinIO, and the C++ inference container

## Running it locally

```bash
docker compose up --build
```

This brings up: `ingestion` (:8000), `results-api` (:8001), `cv-inference-cpp` (:50051, gRPC), 2x `worker`, `postgres`, `redis`, `minio`.

The `images` schema is applied automatically on first boot: the Postgres
service mounts `services/results-api/migrations/` into the image's
`/docker-entrypoint-initdb.d/`, which the official `postgres` image runs once
against an empty data directory. Because the data lives in a named volume, the
migration is applied only on a fresh volume — use `docker compose down -v` to
re-initialize from scratch.

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
