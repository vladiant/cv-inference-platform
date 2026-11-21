"""@file
@brief Domain entities for the ingestion service (framework-free).

No FastAPI, no boto3, no Redis imports here — this module should be
importable in a plain Python REPL with nothing installed but the
standard library.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import uuid


@dataclass(frozen=True)
class ImageUpload:
    """@brief Immutable value object describing one accepted upload.

    Carries only the metadata ingestion owns at acceptance time; the CV
    result fields live on the Postgres row filled in later by the worker.
    """
    image_id: str
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime

    @staticmethod
    def new(filename: str, content_type: str, size_bytes: int) -> "ImageUpload":
        """@brief Build a fresh upload with a random UUID and a UTC timestamp.

        @param filename Original client-supplied filename.
        @param content_type MIME type of the upload (image/jpeg or image/png).
        @param size_bytes Size of the raw bytes in bytes.
        @return A new frozen ImageUpload instance.
        """
        return ImageUpload(
            image_id=str(uuid.uuid4()),
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            uploaded_at=datetime.now(timezone.utc),
        )
