# Project Status

_Last updated: 2026-10-10_

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

Full runtime smoke was verified end-to-end: upload → `pending` seed → worker →
gRPC inference → `done`/`failed` → results-api read; idempotent upsert on the
partition key; `grpc.health.v1.Health/Check` returns `SERVING`; graceful worker
shutdown works. The object-store fix is QA-passed: MinIO reaches healthy and the
full upload → object-write → pending-row path works end-to-end with the real
MinIO image.

## Known follow-ups

None outstanding. The previously tracked design gap (D2) was fixed earlier in
this cycle, and the earlier local image-registry limitation for MinIO is now
resolved by the `docker-compose` object-storage fix (QA-passed).

## Pointers

- Changes shipped this cycle are recorded in [`../CHANGELOG.md`](../CHANGELOG.md):
  the release under the `1.0.0` section, and the two post-release patch changes
  under the `1.0.1` section.
- Design rationale and the enforced / structural / intended retention split:
  [`design-decisions.md`](design-decisions.md).
