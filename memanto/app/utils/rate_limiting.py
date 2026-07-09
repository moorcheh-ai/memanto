"""
Rate Limiting for MEMANTO
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException


@dataclass
class RateLimit:
    """Rate limit configuration"""

    requests: int  # Number of requests
    window: int  # Time window in seconds


class RateLimiter:
    """Token bucket rate limiter"""

    def __init__(self):
        # Storage: key -> deque of timestamps
        self.requests = defaultdict(deque)

        # Rate limit configurations
        self.limits = {
            # Memory operations
            "memory_write": RateLimit(60, 60),  # 60/min per scope
            "memory_read": RateLimit(120, 60),  # 120/min per agent
            "memory_answer": RateLimit(30, 60),  # 30/min per agent (strictest)
            "memory_delete": RateLimit(30, 60),  # 30/min per scope
            # Namespace operations
            "namespace_create": RateLimit(10, 60),  # 10/min per agent
            "namespace_delete": RateLimit(5, 60),  # 5/min per agent
            # Health endpoints (more lenient)
            "health": RateLimit(300, 60),  # 300/min
        }

    def _get_key(self, operation: str, agent_id: str) -> str:
        """Generate rate limit key"""
        return f"{operation}:{agent_id}"

    def check_rate_limit(
        self, operation: str, agent_id: str
    ) -> tuple[bool, int | None]:
        """
        Check if request is within rate limit
        Returns: (allowed, retry_after_seconds)
        """
        if operation not in self.limits:
            return True, None

        limit = self.limits[operation]
        key = self._get_key(operation, agent_id)
        now = time.time()

        # Clean old requests outside window
        request_times = self.requests[key]
        while request_times and request_times[0] <= now - limit.window:
            request_times.popleft()

        # Check if under limit
        if len(request_times) < limit.requests:
            request_times.append(now)
            return True, None

        # Rate limited - calculate retry after
        oldest_request = request_times[0]
        retry_after = int(oldest_request + limit.window - now) + 1

        return False, retry_after

    def enforce_rate_limit(self, operation: str, agent_id: str):
        """Enforce rate limit, raise HTTPException if exceeded"""
        allowed, retry_after = self.check_rate_limit(operation, agent_id)

        if not allowed:
            # Log rate limit event
            from memanto.app.utils.logging import MemantoLogger

            MemantoLogger.log_request(
                request_id="rate_limit",
                route=f"/{operation}",
                method="POST",
                status_code=429,
                latency_ms=0,
                agent_id=agent_id,
                errors=["rate_limit_triggered"],
            )

            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded for {operation}",
                    "retry_after": retry_after,
                    "limit": f"{self.limits[operation].requests}/{self.limits[operation].window}s",
                },
                headers={"Retry-After": str(retry_after)},
            )


# Global rate limiter
rate_limiter = RateLimiter()


def enforce_write_rate_limit(agent_id: str):
    """Enforce rate limit for memory write operations"""
    rate_limiter.enforce_rate_limit("memory_write", agent_id)


def enforce_read_rate_limit(agent_id: str):
    """Enforce rate limit for memory read operations"""
    rate_limiter.enforce_rate_limit("memory_read", agent_id)


def enforce_answer_rate_limit(agent_id: str):
    """Enforce rate limit for memory answer operations"""
    rate_limiter.enforce_rate_limit("memory_answer", agent_id)


def enforce_delete_rate_limit(agent_id: str):
    """Enforce rate limit for memory delete operations"""
    rate_limiter.enforce_rate_limit("memory_delete", agent_id)


def enforce_namespace_rate_limit(operation: str, agent_id: str):
    """Enforce rate limit for namespace operations"""
    rate_limiter.enforce_rate_limit(f"namespace_{operation}", agent_id)
