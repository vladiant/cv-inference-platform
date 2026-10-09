"""Unit tests for the ingestion domain entity (pure, stdlib-only)."""
from datetime import datetime, timezone

from app.domain.image import ImageUpload


def test_new_populates_fields_and_generates_uuid():
    upload = ImageUpload.new("photo.jpg", "image/jpeg", 123)

    assert upload.filename == "photo.jpg"
    assert upload.content_type == "image/jpeg"
    assert upload.size_bytes == 123
    # image_id is a UUID string.
    assert len(upload.image_id) == 36 and upload.image_id.count("-") == 4
    # uploaded_at is timezone-aware UTC.
    assert upload.uploaded_at.tzinfo is not None
    assert upload.uploaded_at.utcoffset() == timezone.utc.utcoffset(datetime.now())


def test_new_generates_unique_ids():
    a = ImageUpload.new("a.jpg", "image/jpeg", 1)
    b = ImageUpload.new("b.jpg", "image/jpeg", 1)
    assert a.image_id != b.image_id
