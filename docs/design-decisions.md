# Design Decisions

Written as if explaining trade-offs to a non-engineering stakeholder — the
"why", not just the "what".

## Why split ingestion from inference?

If the API that accepts uploads also runs inference synchronously, a slow
model or a burst of uploads makes the *upload* feel slow, even though
uploading and inferring are unrelated concerns from the customer's point of
view. Splitting them means: uploads always feel instant, and we can scale the
inference workers up or down independently of how many people are uploading
right now, without redeploying the upload service.

## Why gRPC between worker and cv-inference-cpp, but REST everywhere else?

REST/JSON is the right default for anything a human or a third party might
call directly — it's debuggable with `curl`, self-describing, and nobody
needs a code generator to use it. The worker-to-inference call is different:
it's a high-frequency, internal, binary-payload (image bytes) call where
serialization overhead is not free. gRPC's binary protobuf framing and HTTP/2
multiplexing measurably reduce overhead at that call rate. Using REST there
"for consistency" would be optimizing for a value (uniformity) at the expense
of the value that actually matters on that path (throughput).

## Why C++ for the inference service specifically?

Everything else in the system is I/O-bound: it's waiting on the network, the
database, or object storage, and Python's `asyncio` handles that well. The
inference step is CPU-bound — it's the one place where per-request Python
interpreter overhead actually shows up in the bill. Isolating it as its own
service means the CPU-bound hot path can be optimized (or the model swapped,
or GPU support added) without touching the rest of the system, and it can be
scaled and resourced separately in Kubernetes (different CPU/memory requests
than the I/O-bound services).

## Why an event stream instead of the worker polling the database?

Polling means either wasted queries when nothing's new, or added latency
between "image uploaded" and "worker notices it," depending on the poll
interval. A stream gives near-immediate delivery without a polling loop, and
consumer groups mean adding a second worker doesn't require any code change —
it just means the same events get load-balanced across more consumers.

## Why keep raw images and metadata in different stores with different retention?

Raw image bytes are large and mostly write-once/read-rarely after processing.
Metadata and results are small, queried constantly, and need to support
filtering ("show me all failed inferences from last week"). Forcing both into
one system means picking a storage engine that's mediocre at both jobs
instead of good at one. Splitting them lets each store use a retention policy
that matches how the data is actually used: image bytes are the natural
candidate for tiering/expiry, while metadata and results stay queryable
indefinitely, with old partitions detached and archived rather than deleted,
since audit and analytics needs on structured data tend to outlast the raw
files they describe.

Which of these policies is actually *enforced in this scaffold* versus merely
*designed for* is spelled out explicitly in "What retention is actually
enforced today" below. The distinction matters: this is an "honest" scaffold,
and a design document that claims lifecycle rules the code does not implement
is worse than one that says plainly what is and isn't wired.

## The image record lifecycle: who owns the row, and why `pending` exists

The whole system is built around the promise that *uploading feels instant and
inference happens afterwards*. For a client to observe that promise, there has
to be a queryable state that means "we have your image, we haven't finished
looking at it yet." That state is `pending`.

The row in the `images` table therefore has a single, linear lifecycle with a
**different owner for each transition** — which is cleaner than the alternative
where one service owns the whole row:

1. **`ingestion` creates the row** (`status = pending`): it writes the
   *metadata* it already has — `image_id`, `filename`, `content_type`,
   `size_bytes`, `uploaded_at` — leaving `processed_at`, `success`,
   `detections`, etc. `NULL`. This happens *after* the bytes are in object
   storage and *before* the event is published.
2. **`worker` enriches the row** (`status → done | failed`): it fills in
   `processed_at`, `success`, `error_message`, `processing_ms`, `detections`.
3. **`results-api` only ever reads the row.**

### Reconciling this with "ingestion never touches CV logic"

The boundary that matters — and the one the README asserts — is that ingestion
performs **no computer-vision work**: it never decodes an image, never calls
the inference service, never imports OpenCV. Writing a *metadata* row is not CV
logic; it is the same category of bookkeeping as emitting the event. So
ingestion gaining a Postgres write does **not** cross the CV boundary. It does,
however, add a new dependency (ingestion now needs a Postgres connection), and
that trade-off is deliberate:

- **Chosen: ingestion seeds a `pending` row.** Pros: `pending` becomes a real,
  observable state that *demonstrates the async pipeline* instead of a 404 gap;
  the short-TTL cache branch in `results-api` is no longer dead code; and
  ownership of each row-phase is crisp. It also resolves the upsert bug below
  cleanly. Con: ingestion depends on Postgres.
- **Rejected: delete the `pending` concept, keep the worker as the only
  writer.** This keeps ingestion free of Postgres, but a freshly-uploaded image
  returns `404` until the worker finishes — ambiguous (never existed vs. not
  done yet) — and it throws away the clearest demonstration of the
  event-driven design, which is the entire point of the project. The coupling
  it avoids (one small, fast, local metadata INSERT) is cheap; the demonstration
  it loses is the headline feature.

### The upsert conflict target (the bug this also fixes)

`images` is `PARTITION BY RANGE (uploaded_at)` with `PRIMARY KEY (image_id,
uploaded_at)`. On a partitioned table, an `ON CONFLICT` target **must include
the partition key** — there is no unique constraint on `image_id` alone, so the
worker's `ON CONFLICT (image_id)` fails at runtime.

The worker's write is therefore an upsert whose **conflict target is the full
primary key**:

```sql
INSERT INTO images (image_id, filename, content_type, size_bytes, uploaded_at,
                    processed_at, success, error_message, processing_ms, detections)
VALUES ($1, $2, $3, $4, $5, now(), $6, $7, $8, $9)
ON CONFLICT (image_id, uploaded_at) DO UPDATE SET
    processed_at  = now(),
    success       = EXCLUDED.success,
    error_message = EXCLUDED.error_message,
    processing_ms = EXCLUDED.processing_ms,
    detections    = EXCLUDED.detections;
```

Because ingestion has already inserted the `(image_id, uploaded_at)` row, the
worker normally takes the `DO UPDATE` branch (pending → done/failed). If the
pending row is somehow missing (e.g. ingestion's insert was lost), the `INSERT`
branch recreates it, so the write is robust and **idempotent under Redis
redelivery**. The `uploaded_at` value the worker binds comes from the event
payload (the exact ISO-8601 string ingestion emitted), so it matches the stored
timestamp to microsecond precision and the conflict fires reliably. This single
change fixes both the partition-incompatible conflict target and the
unreachable-`pending` problem at once.

## How the schema gets created

The migration in `services/results-api/migrations/001_init.sql` was never
applied — nothing mounted or ran it — so every service that touches `images`
would fail at runtime. The authoritative mechanism:

- **Compose:** mount the migrations directory into the Postgres image's
  first-boot hook:
  `./services/results-api/migrations:/docker-entrypoint-initdb.d:ro`. The
  official `postgres` image executes `*.sql` there **once, on an empty data
  directory**. Because `pgdata` is a named volume, re-running `docker compose
  up` does not re-apply it; `docker compose down -v` (or a fresh volume) does.
  All DDL is already `IF NOT EXISTS`, so re-application is harmless.
- **Kubernetes:** ship the same SQL as a `ConfigMap` and mount it into the
  postgres container's `/docker-entrypoint-initdb.d/` (same first-boot
  semantics, parallel to Compose). A standalone migration `Job` running a real
  migration tool is the production-grade path and is noted as future work, not
  built here — consistent with the scaffold's honesty about what's wired.

Ownership note: the migration file lives under `results-api/` for historical
reasons but describes a table written by `ingestion` and `worker` and read by
`results-api`. It is a **shared contract**; treat it as owned by the data
model, not by any one service.

## Worker packaging, imports, and shutdown

Two defects in how the worker is packaged and run:

1. **Import path.** The Dockerfile generates `inference_pb2` /
   `inference_pb2_grpc` into `/srv` (the workdir) but runs `python
   app/main.py`, which puts `/srv/app` — not `/srv` — on `sys.path[0]`, so
   `import inference_pb2` is unresolvable. The convention: **run the worker as
   a module** (`python -u -m app.main`) with workdir `/srv`. Running `-m` puts
   the workdir (`/srv`) on `sys.path`, so both the `app` package *and* the
   top-level generated stubs resolve. This also mirrors how `ingestion` and
   `results-api` are invoked (`app.main:app`). Generated stubs stay at the
   service root as top-level modules — deliberately, so the single source of
   truth remains `proto/inference.proto` regenerated at build time.
2. **Lifecycle / graceful shutdown.** `main()` opens Redis, an asyncpg pool, an
   aioboto3 session, and a gRPC channel and never closes any of them; the
   `while True` loop has no signal handling. On `SIGTERM` — which is exactly
   what happens on every HPA scale-down and rolling update, i.e. the project's
   headline "scale the worker pool" story — the process is killed mid-loop. The
   expectation for the developer: install `SIGTERM`/`SIGINT` handlers that set
   an asyncio stop event, let the current message finish (or leave it un-acked
   for redelivery), break the loop, and `await` close of the Redis client,
   asyncpg pool, and gRPC channel before exit. Un-acked in-flight messages are
   safe — they are redelivered — but open resources should be released cleanly.

(The same lifecycle rigor applies to the Redis clients in `ingestion`'s
publisher and `results-api`'s cache, which are also never closed on shutdown;
closing them in each service's lifespan is a smaller, lower-priority
consistency fix.)

## Health checking the inference service

The proto defines a bespoke `HealthCheck` RPC that the C++ service implements,
but nothing calls it — k8s uses a `tcpSocket` readiness probe, which only
proves the port is open, not that the server (and its Haar cascade) actually
loaded and can serve.

**Decision: adopt the standard gRPC health-checking protocol
(`grpc.health.v1.Health`) and drop the custom RPC.** Rationale: inventing a
one-off health RPC when gRPC has a well-known standard that the whole ecosystem
(including Kubernetes' native `grpc` probe) understands is reinventing a wheel.
Concretely:

- Remove `HealthCheck` / `HealthRequest` / `HealthResponse` from
  `inference.proto`.
- Enable the gRPC C++ default health service
  (`grpc::EnableDefaultHealthCheckService(true)` before building the server),
  which serves `grpc.health.v1.Health` reporting `SERVING` once the service is
  registered.
- Replace the `tcpSocket` readiness probe in `k8s/cv-inference-cpp.yaml` with a
  native gRPC probe (`readinessProbe.grpc.port: 50051`).

Rejected alternative: keep the custom RPC and wire an `exec` probe that shells
out to a bundled client binary. It works, but it's more moving parts and less
idiomatic than the standard health service for no benefit.

## Keeping the benchmark honest

`scripts/benchmark.py`'s async path builds an unused `form` and posts
`data={"file": data}` — raw bytes as a urlencoded form field, not a multipart
file upload. FastAPI's `File(...)` endpoint rejects that with `422`, so the
async and multiprocess numbers are measuring rejected requests and the whole
sync-vs-async-vs-multiprocess comparison is invalid. The benchmark must
exercise the **same multipart contract as the real client** (an
`aiohttp.FormData` field named `file` with `filename` and `content_type`, i.e.
the async equivalent of the sync path's `files={"file": (...)}`). This is a
contract-consistency fix for the developer; the design point is simply that a
benchmark that doesn't speak the real endpoint's contract proves nothing.

## What retention is actually enforced today

To keep this document trustworthy, here is the honest split between what the
scaffold *enforces*, what is *structurally present but not operationalized*,
and what is *documented intent only*:

- **Enforced now:** the Redis Stream's `MAXLEN ~ 100_000` (approximate),
  applied on every `XADD` in `ingestion`'s publisher. The stream self-trims;
  this is the only retention rule the code actually applies.
- **Structurally present, not operationalized:** Postgres partitioning. The
  `images` table really is declared `PARTITION BY RANGE (uploaded_at)` with a
  `DEFAULT` partition, so the *structure* exists — but **no scheduled job
  pre-creates monthly partitions, and no detach/archive runs**. In practice
  every row lands in `images_default`. The monthly-partition `CREATE TABLE` is a
  commented-out example in the migration, nothing more.
- **Documented intent only (not implemented):** the MinIO lifecycle policy.
  There is **no** bucket lifecycle configuration anywhere — no 7-day cold-tier
  transition, no 90-day expiry — and **no `retain=true` metadata field exists**
  in the schema or the code to exempt objects from it. This is a future-work
  design, not a running feature.

README and this document must agree on exactly this split. Any text that
implies the MinIO lifecycle or monthly partition rotation is live is wrong and
should be corrected to match the three-way breakdown above.

## What would change with real production scale?

- Redis Streams → Kafka, once cross-service replay/ordering guarantees or
  multi-datacenter delivery matter more than operational simplicity.
- A single Postgres instance → read replicas for `results-api`, since it's
  read-heavy and can tolerate slightly stale data.
- The C++ inference service would get a proper batching layer (accumulate N
  requests or T milliseconds, run one batched inference call) if a real model
  benefits from batch throughput — not implemented here since the scaffold
  uses a single-image OpenCV operation.
