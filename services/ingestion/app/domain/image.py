"""Domain entities for the ingestion service.

No FastAPI, no boto3, no Redis imports here — this module should be
importable in a plain Python REPL with nothing installed but the
standard library.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import uuid


@dataclass(frozen=True)
class ImageUpload:
    image_id: str
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime

    @staticmethod
    def new(filename: str, content_type: str, size_bytes: int) -> "ImageUpload":
        return ImageUpload(
            image_id=str(uuid.uuid4()),
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            uploaded_at=datetime.now(timezone.utc),
        )
