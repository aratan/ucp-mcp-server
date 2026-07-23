"""Configuration via environment variables."""

import os


class UCPConfig:
    """UCP client configuration from environment variables."""

    # HTTP Client
    TIMEOUT: float = float(os.environ.get("UCP_TIMEOUT", "30.0"))
    CONNECT_TIMEOUT: float = float(os.environ.get("UCP_CONNECT_TIMEOUT", "10.0"))

    # Rate Limiting
    MAX_CONCURRENT_REQUESTS: int = int(os.environ.get("UCP_MAX_CONCURRENT", "10"))
    RATE_LIMIT_PER_SECOND: float = float(os.environ.get("UCP_RATE_LIMIT", "100"))

    # Retry
    MAX_RETRIES: int = int(os.environ.get("UCP_MAX_RETRIES", "3"))
    RETRY_BACKOFF_BASE: float = float(os.environ.get("UCP_RETRY_BACKOFF_BASE", "0.5"))
    RETRY_BACKOFF_MAX: float = float(os.environ.get("UCP_RETRY_BACKOFF_MAX", "10.0"))

    # Caching
    DISCOVERY_CACHE_TTL: int = int(os.environ.get("UCP_DISCOVERY_CACHE_TTL", "300"))

    # Logging
    LOG_LEVEL: str = os.environ.get("UCP_LOG_LEVEL", "INFO")


config = UCPConfig()
