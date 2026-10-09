-- Partitioned by month so old partitions can be detached and archived
-- without touching hot (recent) data. See docs/design-decisions.md.
CREATE TABLE IF NOT EXISTS images (
    image_id       TEXT NOT NULL,
    filename       TEXT NOT NULL,
    content_type   TEXT NOT NULL,
    size_bytes     BIGINT NOT NULL,
    uploaded_at    TIMESTAMPTZ NOT NULL,
    processed_at   TIMESTAMPTZ,
    success        BOOLEAN,
    error_message  TEXT,
    processing_ms  INTEGER,
    detections     JSONB,
    PRIMARY KEY (image_id, uploaded_at)
) PARTITION BY RANGE (uploaded_at);

CREATE TABLE IF NOT EXISTS images_default PARTITION OF images DEFAULT;

CREATE INDEX IF NOT EXISTS idx_images_uploaded_at ON images (uploaded_at DESC);
CREATE INDEX IF NOT EXISTS idx_images_status ON images (success) WHERE processed_at IS NOT NULL;

-- Example of a monthly partition to be created ahead of time by a
-- scheduled job (not included in this scaffold):
-- CREATE TABLE images_2026_09 PARTITION OF images
--   FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
