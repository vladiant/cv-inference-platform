# Project Status

_Last updated: 2026-11-22_

## Current stage

The first functional release has been stamped as **`1.0.0`** (annotated tag
`v1.0.0`); the tag is released and pushed.

Since `1.0.0`, two **patch-level** changes shipped to `main` and are now stamped
as **`1.0.1`** (annotated tag `v1.0.1`). Both are recorded under the CHANGELOG
**`1.0.1`** section:

1. **GitHub Actions CI workflow** (`.github/workflows/ci.yml`) plus a README CI
   status badge.
2. **`docker-compose` object-storage fix**: the object store now runs the
   freely-pullable Bitnami-repackaged real MinIO binary (the old
   `minio/minio:latest` was gated and no longer pullable), with a MinIO
   healthcheck, `service_healthy` gating for `ingestion`/`worker`, the missing
   `worker → minio` dependency, and `restart: unless-stopped` across services.

Since `1.0.1`, one **documentation-only, PATCH-level** change is staged under
the CHANGELOG **`[Unreleased]`** section (not yet stamped/tagged):

3. **Doxygen API docs + System Component Diagram.** A root `Doxyfile` plus a
   Doxygen `@mainpage` (`docs/mainpage.dox`) carrying a hand-authored Graphviz
   Component Diagram of the four services and their contracts (HTTP/REST, Redis
   Stream event, Redis cache, gRPC, S3, SQL). Doxygen-format doc comments were
   added across the service source trees, `main.cpp`, `inference.proto`, and
   `benchmark.py`; the README gained a "Documentation (Doxygen)" subsection; and
   `.gitignore` now excludes the generated `docs/doxygen/` output. No runtime
   behavior, API, event contract, schema, credentials, ports, or bucket names
   changed — the doc comments are inert.

Full runtime smoke was verified end-to-end: upload → `pending` seed → worker →
gRPC inference → `done`/`failed` → results-api read; idempotent upsert on the
partition key; `grpc.health.v1.Health/Check` returns `SERVING`; graceful worker
shutdown works. The object-store fix is QA-passed: MinIO reaches healthy and the
full upload → object-write → pending-row path works end-to-end with the real
MinIO image.

## Known follow-ups

- The Doxygen documentation change is staged under `[Unreleased]` and has not
  yet been stamped as a patch release / tagged. Generating the docs requires
  `doxygen` and `graphviz` (`dot`) on `PATH`; run `doxygen Doxyfile` from the
  repo root (output: `docs/doxygen/html/`, gitignored).

## Pointers

- Changes shipped this cycle are recorded in [`../CHANGELOG.md`](../CHANGELOG.md):
  the release under the `1.0.0` section, the two post-release patch changes
  under the `1.0.1` section, and the Doxygen documentation change under
  `[Unreleased]`.
- Design rationale and the enforced / structural / intended retention split:
  [`design-decisions.md`](design-decisions.md).
- Doxygen config: root [`../Doxyfile`](../Doxyfile); Component Diagram source:
  [`mainpage.dox`](mainpage.dox).

