"""Prometheus metrics for UCP MCP Server."""

from prometheus_client import Counter, Histogram, Gauge, Info

# HTTP Client Metrics
http_requests_total = Counter(
    "ucp_http_requests_total",
    "Total HTTP requests to merchants",
    ["method", "endpoint", "status_code"],
)

http_request_duration_seconds = Histogram(
    "ucp_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

http_requests_in_progress = Gauge(
    "ucp_http_requests_in_progress",
    "Number of HTTP requests currently in progress",
    ["method"],
)

# Retry Metrics
http_retries_total = Counter(
    "ucp_http_retries_total",
    "Total HTTP request retries",
    ["method", "endpoint", "attempt"],
)

# Cache Metrics
discovery_cache_hits_total = Counter(
    "ucp_discovery_cache_hits_total",
    "Total discovery cache hits",
)

discovery_cache_misses_total = Counter(
    "ucp_discovery_cache_misses_total",
    "Total discovery cache misses",
)

# Tool Metrics
tool_calls_total = Counter(
    "ucp_tool_calls_total",
    "Total MCP tool calls",
    ["tool_name", "status"],
)

tool_call_duration_seconds = Histogram(
    "ucp_tool_call_duration_seconds",
    "MCP tool call duration in seconds",
    ["tool_name"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# Server Info
server_info = Info(
    "ucp_mcp_server",
    "UCP MCP Server information",
)


def init_metrics(version: str = "unknown") -> None:
    """Initialize server metrics with version info."""
    server_info.info({
        "version": version,
        "protocol": "ucp",
        "transport": "mcp",
    })


class MetricsMiddleware:
    """Context manager for tracking HTTP request metrics."""

    def __init__(self, method: str, endpoint: str):
        self.method = method
        self.endpoint = endpoint
        self._timer = None

    def __enter__(self):
        http_requests_in_progress.labels(method=self.method).inc()
        self._timer = http_request_duration_seconds.labels(
            method=self.method,
            endpoint=self.endpoint,
        ).time()
        self._timer.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        http_requests_in_progress.labels(method=self.method).dec()

        status_code = "200"
        if exc_type is not None:
            status_code = "500"

        http_requests_total.labels(
            method=self.method,
            endpoint=self.endpoint,
            status_code=status_code,
        ).inc()

        self._timer.__exit__(exc_type, exc_val, exc_tb)
        return False
