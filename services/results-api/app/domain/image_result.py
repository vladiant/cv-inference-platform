from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class ImageResult:
    image_id: str
    filename: str
    uploaded_at: datetime
    processed_at: Optional[datetime]
    success: Optional[bool]
    error_message: Optional[str]
    processing_ms: Optional[int]
    detections: list[Detection]

    @property
    def status(self) -> str:
        if self.processed_at is None:
            return "pending"
        return "done" if self.success else "failed"
