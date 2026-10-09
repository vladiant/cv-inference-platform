# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-10

First functional, QA-verified cut of the pipeline and the initial stamped
release. The headline change is a **breaking gRPC health-contract change**
(see Removed / Changed).

### Added

- **Pipeline metadata lifecycle.** `ingestion` now seeds a `pending` row in the
  `images` table after storing the raw bytes and before publishing the event
  (per request: put bytes → insert `pending` row → publish event). This is
  backed by a new `MetadataRepository` port with an `asyncpg` adapter.
- **Applied Postgres schema.** The `images` migrations are now actually applied
  at startup: mounted into the Postgres image's init directory in
  `docker-compose`, and shipped as a ConfigMap in `k8s/`.
- **Graceful worker shutdown.** `worker` handles `SIGTERM`/`SIGINT` and releases
  its Redis, Postgres, and gRPC resources on shutdown.
- **Standard gRPC health service.** `cv-inference-cpp` now serves the standard
  `grpc.health.v1.Health` service; the k8s `cv-inference-cpp` readiness check
  uses a native `grpc` probe against it.
- **Root `.dockerignore`** to harden and shrink the Docker build context.
- **Infra-free unit tests** for `ingestion` and `results-api` (no
  Postgres/Redis/MinIO required to run them).

### Changed

- **BREAKING (gRPC):** the inference health contract moved from a bespoke
  `HealthCheck` RPC to the standard `grpc.health.v1.Health` service. Any client
  probing health must call `grpc.health.v1.Health/Check` instead of the removed
  bespoke RPC.
- `ingestion` now **requires** `POSTGRES_DSN` and depends on Postgres, since it
  writes the initial `pending` metadata row.
- `worker` upsert now targets the full partition key
  `ON CONFLICT (image_id, uploaded_at)`, with `uploaded_at` taken from the event
  payload, keeping the write idempotent against the partitioned table.
- `worker` now runs via `python -m app.main`.
- `worker` Redis consumer name now derives from `HOSTNAME`, so each replica gets
  a unique consumer id within the consumer group.
- `scripts/benchmark.py` async path now performs a real multipart upload
  (matching the sync path), so the sync / async / multiprocess comparison is
  valid.
- `docs/design-decisions.md` and the README design-intent sections were
  corrected and reconciled (image-record lifecycle; honest retention
  enforced / structural / intended split).

### Removed

- **BREAKING (gRPC):** the bespoke `HealthCheck` RPC and its `Health*` messages
  were removed from `proto/inference.proto` in favor of the standard
  `grpc.health.v1.Health` service (see Changed).
