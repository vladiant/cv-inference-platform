"""@file
@brief Environment-driven configuration for the results API service.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    ## @brief Immutable settings resolved from environment variables at import.
    postgres_dsn: str = os.getenv("POSTGRES_DSN", "postgresql://cvplatform:cvplatform@localhost:5432/cvplatform")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")


settings = Settings()
