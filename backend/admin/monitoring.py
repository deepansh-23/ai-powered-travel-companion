"""In-memory API Monitoring and Diagnostics for Admin Dashboard.

Collects real request metrics and sanitized diagnostics events using FastAPI middleware.
- Bounded memory storage (deque of up to 10,000 requests, up to 300 diagnostics events).
- Safe: never logs request bodies, passwords, cookies, authorization headers, or secrets.
- Redacts query parameters to prevent leaking tokens or user identifiers.
- Excludes static files, health check endpoints, and admin monitoring/settings calls to avoid recursion.
- Instrumentation failures never break normal application requests.
"""

import logging
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Excluded path prefixes and exact paths
EXCLUDED_PREFIXES = (
    "/admin",
    "/css",
    "/js",
    "/images",
    "/fonts",
    "/favicon.ico",
    "/static",
)

EXCLUDED_EXACT = {
    "/api/health",
    "/api/admin/monitoring",
    "/api/admin/system-health",
    "/api/admin/diagnostics",
    "/api/admin/settings",
    "/api/settings/public",
    "/docs",
    "/redoc",
    "/openapi.json",
}


def _mask_ip(ip: Optional[str]) -> str:
    if not ip or ip == "unknown":
        return "unknown"
    if ":" in ip:  # IPv6
        parts = ip.split(":")
        return f"{parts[0]}:{parts[1]}::xxxx" if len(parts) >= 2 else "ipv6:xxxx"
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"
    return "xxx.xxx.xxx.xxx"


def _sanitize_error_summary(status_code: int, path: str, exc_type: Optional[str] = None) -> str:
    summaries = {
        400: "Bad Request: Invalid or missing parameters",
        401: "Unauthorized: Authentication or step-up required",
        403: "Forbidden: Permission denied or human verification required",
        404: "Not Found: Resource or route does not exist",
        409: "Conflict: Resource state conflict",
        422: "Unprocessable Entity: Schema validation failed",
        429: "Too Many Requests: Rate limit exceeded",
        500: "Internal Server Error: Application exception handled safely",
        502: "Bad Gateway: Downstream service unavailable",
        503: "Service Unavailable: Maintenance or temporary outage",
        504: "Gateway Timeout: Upstream response timed out",
    }
    base = summaries.get(status_code, f"HTTP {status_code}: Request completed with failure status")
    if exc_type and status_code >= 500:
        base += f" ({exc_type})"
    return base


class RequestRecord:
    __slots__ = ("timestamp", "method", "path", "status_code", "duration_ms")

    def __init__(self, timestamp: float, method: str, path: str, status_code: int, duration_ms: float):
        self.timestamp = timestamp
        self.method = method
        self.path = path
        self.status_code = status_code
        self.duration_ms = duration_ms


class DiagnosticRecord:
    __slots__ = ("id", "timestamp", "method", "endpoint", "status_code", "error_summary", "duration_ms", "client_ip_masked")

    def __init__(self, id: str, timestamp: str, method: str, endpoint: str, status_code: int, error_summary: str, duration_ms: float, client_ip_masked: str):
        self.id = id
        self.timestamp = timestamp
        self.method = method
        self.endpoint = endpoint
        self.status_code = status_code
        self.error_summary = error_summary
        self.duration_ms = duration_ms
        self.client_ip_masked = client_ip_masked

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "method": self.method,
            "endpoint": self.endpoint,
            "status_code": self.status_code,
            "error_summary": self.error_summary,
            "duration_ms": round(self.duration_ms, 2),
            "client_ip_masked": self.client_ip_masked,
        }


class ApiMetricsTracker:
    def __init__(self, max_records: int = 10000, max_diagnostics: int = 300):
        self.records: deque = deque(maxlen=max_records)
        self.diagnostics: deque = deque(maxlen=max_diagnostics)
        self.start_time: float = time.time()
        self.start_datetime_iso: str = datetime.now(timezone.utc).isoformat()
        self.total_requests_recorded: int = 0

    def record(self, method: str, path: str, status_code: int, duration_ms: float, client_ip: Optional[str] = None, exc_type: Optional[str] = None) -> None:
        try:
            now = time.time()
            self.records.append(RequestRecord(now, method, path, status_code, duration_ms))
            self.total_requests_recorded += 1

            # If request resulted in an error (4xx or 5xx), record a sanitized diagnostic event
            if status_code >= 400:
                diag_id = f"diag_{int(now * 1000)}_{secrets.token_hex(3)}"
                timestamp_iso = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
                summary = _sanitize_error_summary(status_code, path, exc_type)
                masked_ip = _mask_ip(client_ip)

                self.diagnostics.append(
                    DiagnosticRecord(
                        id=diag_id,
                        timestamp=timestamp_iso,
                        method=method,
                        endpoint=path,
                        status_code=status_code,
                        error_summary=summary,
                        duration_ms=duration_ms,
                        client_ip_masked=masked_ip,
                    )
                )
        except Exception:
            pass

    def get_metrics(self, window_minutes: int = 15) -> Dict[str, Any]:
        """Aggregate metrics for the requested time window (e.g. 15 or 1440)."""
        now = time.time()
        cutoff = now - (window_minutes * 60)

        # Snapshot records safely
        recent = [r for r in list(self.records) if r.timestamp >= cutoff]

        total = len(recent)
        successful = 0
        failed = 0
        c4xx = 0
        c5xx = 0
        total_duration = 0.0

        endpoints_latency = defaultdict(list)
        endpoints_errors = defaultdict(int)
        endpoints_last_error = {}
        recent_failures: List[Dict[str, Any]] = []

        for r in recent:
            total_duration += r.duration_ms
            endpoint_key = f"{r.method} {r.path}"
            endpoints_latency[endpoint_key].append(r.duration_ms)

            if 200 <= r.status_code < 400:
                successful += 1
            else:
                failed += 1
                if 400 <= r.status_code < 500:
                    c4xx += 1
                elif r.status_code >= 500:
                    c5xx += 1
                endpoints_errors[endpoint_key] += 1
                endpoints_last_error[endpoint_key] = r.status_code

                # Collect recent failures
                recent_failures.append({
                    "timestamp": datetime.fromtimestamp(r.timestamp, tz=timezone.utc).isoformat(),
                    "method": r.method,
                    "path": r.path,
                    "status_code": r.status_code,
                    "duration_ms": round(r.duration_ms, 2),
                })

        avg_response_time = round(total_duration / total, 2) if total > 0 else 0.0
        error_rate = round((failed / total) * 100, 2) if total > 0 else 0.0

        # Slowest endpoints
        slowest_list = []
        for ep, durations in endpoints_latency.items():
            if durations:
                ep_avg = sum(durations) / len(durations)
                ep_max = max(durations)
                slowest_list.append({
                    "endpoint": ep,
                    "avg_duration_ms": round(ep_avg, 2),
                    "max_duration_ms": round(ep_max, 2),
                    "count": len(durations),
                })
        slowest_list.sort(key=lambda x: x["avg_duration_ms"], reverse=True)
        slowest_endpoints = slowest_list[:10]

        # Endpoints with most errors
        error_list = []
        for ep, err_count in endpoints_errors.items():
            error_list.append({
                "endpoint": ep,
                "error_count": err_count,
                "last_status_code": endpoints_last_error.get(ep, 500),
            })
        error_list.sort(key=lambda x: x["error_count"], reverse=True)
        most_errors = error_list[:10]

        # Reverse recent failures to show newest first, limit to 30
        recent_failures.reverse()
        recent_failures = recent_failures[:30]

        return {
            "window_minutes": window_minutes,
            "window_label": "Last 15 Minutes" if window_minutes <= 15 else "Last 24 Hours",
            "total_requests": total,
            "successful_requests": successful,
            "failed_requests": failed,
            "c4xx_count": c4xx,
            "c5xx_count": c5xx,
            "error_rate_percent": error_rate,
            "avg_response_time_ms": avg_response_time,
            "slowest_endpoints": slowest_endpoints,
            "endpoints_with_most_errors": most_errors,
            "recent_failures": recent_failures,
            "process_started_at": self.start_datetime_iso,
            "uptime_seconds": int(now - self.start_time),
            "total_lifetime_requests": self.total_requests_recorded,
            "is_in_memory": True,
        }

    def get_diagnostics(
        self,
        level: str = "all",
        search: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Return real, sanitized diagnostic error events."""
        events = list(self.diagnostics)
        events.reverse()  # Newest first

        filtered = []
        c4xx = 0
        c5xx = 0

        search_term = (search or "").strip().lower()

        for ev in events:
            if 400 <= ev.status_code < 500:
                c4xx += 1
            elif ev.status_code >= 500:
                c5xx += 1

            if level == "4xx" and not (400 <= ev.status_code < 500):
                continue
            if level == "5xx" and not (ev.status_code >= 500):
                continue

            if search_term:
                match = (
                    search_term in ev.endpoint.lower()
                    or search_term in ev.method.lower()
                    or search_term in str(ev.status_code)
                    or search_term in ev.error_summary.lower()
                )
                if not match:
                    continue

            filtered.append(ev.to_dict())

        return {
            "items": filtered[:limit],
            "total_recorded": len(self.diagnostics),
            "c4xx_count": c4xx,
            "c5xx_count": c5xx,
            "app_uptime_seconds": int(time.time() - self.start_time),
            "server_time": datetime.now(timezone.utc).isoformat(),
        }


# Global instance
metrics_tracker = ApiMetricsTracker()


class ApiMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Fast path check for excluded routes
        if path in EXCLUDED_EXACT or any(path.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
            return await call_next(request)

        # Only track /api routes
        if not path.startswith("/api"):
            return await call_next(request)

        start_time = time.perf_counter()
        status_code = 500
        exc_type = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as exc:
            status_code = 500
            exc_type = type(exc).__name__  # class name only: no message, no traceback
            raise
        finally:
            try:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                client_ip = request.client.host if request.client else "unknown"
                # Redact query parameters — record path only
                metrics_tracker.record(
                    method=request.method,
                    path=path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    client_ip=client_ip,
                    exc_type=exc_type,
                )
            except Exception:
                # Instrumentation failure must never break application request
                pass
