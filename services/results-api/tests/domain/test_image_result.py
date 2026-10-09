"""Unit tests for the ImageResult domain status machine (pure, stdlib-only)."""
from datetime import datetime, timezone

from app.domain.image_result import Detection, ImageResult


def _result(processed_at=None, success=None) -> ImageResult:
    return ImageResult(
        image_id="id-1",
        filename="x.jpg",
        uploaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        processed_at=processed_at,
        success=success,
        error_message=None,
        processing_ms=None,
        detections=[],
    )


def test_status_pending_when_not_processed():
    assert _result().status == "pending"


def test_status_done_when_success_true():
    r = _result(processed_at=datetime(2026, 1, 2, tzinfo=timezone.utc), success=True)
    assert r.status == "done"


def test_status_failed_when_success_false():
    r = _result(processed_at=datetime(2026, 1, 2, tzinfo=timezone.utc), success=False)
    assert r.status == "failed"


def test_detection_is_a_value_object():
    d = Detection(label="face", confidence=1.0, x=1, y=2, width=3, height=4)
    assert (d.label, d.x, d.y, d.width, d.height) == ("face", 1, 2, 3, 4)
