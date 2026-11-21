"""@file
@brief Domain entities for the results API (framework-free).
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Detection:
    ## @brief One detected object: a label, a score, and a bounding box.
    label: str
    confidence: float
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class ImageResult:
    ## @brief Read model for one image row, including derived ``status``.
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
        """@brief Derive ``pending`` / ``done`` / ``failed`` from the row state."""
        if self.processed_at is None:
            return "pending"
        return "done" if self.success else "failed"
