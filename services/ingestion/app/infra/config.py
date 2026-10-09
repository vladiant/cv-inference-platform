import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "cvplatform")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "cvplatform123")
    bucket_name: str = os.getenv("IMAGE_BUCKET", "images-raw")


settings = Settings()
