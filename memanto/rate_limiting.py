import time
from typing import Dict, Tuple, Optional

class RateLimiter:
    def __init__(self, limits: Dict[str, Tuple[int, int]]):
        self.limits = limits
        self.counters = {}

    def check_rate_limit(self, operation: str, agent_id: str) -> Tuple[bool, Optional[float]]:
        """
        Check if the operation is within rate limits.

        Args:
            operation: The operation to check.
            agent_id: The ID of the agent performing the operation.

        Returns:
            Tuple of (allowed, retry_after). If allowed is True, retry_after is None.
            If allowed is False, retry_after is the number of seconds to wait before retrying.

        Raises:
            ValueError: If the operation is not registered in the rate limiter.
        """
        if operation not in self.limits:
            raise ValueError(
                f"Unknown rate-limit operation '{operation}'. "
                "Register it in RateLimiter.limits before use."
            )

        limit, window = self.limits[operation]
        key = f"{agent_id}_{operation}"
        current_time = time.time()

        if key not in self.counters:
            self.counters[key] = []

        # Remove old timestamps
        self.counters[key] = [t for t in self.counters[key] if current_time - t < window]

        if len(self.counters[key]) >= limit:
            oldest = self.counters[key][0]
            retry_after = window - (current_time - oldest)
            return False, retry_after

        self.counters[key].append(current_time)
        return True, None

    def enforce_namespace_rate_limit(self, operation: str, agent_id: str) -> Tuple[bool, Optional[float]]:
        """
        Enforce rate limits for namespace operations.

        Args:
            operation: The operation to enforce.
            agent_id: The ID of the agent performing the operation.

        Returns:
            Tuple of (allowed, retry_after). If allowed is True, retry_after is None.
            If allowed is False, retry_after is the number of seconds to wait before retrying.

        Raises:
            ValueError: If the operation is not registered in the rate limiter.
        """
        namespace_operation = f"namespace_{operation}"
        return self.check_rate_limit(namespace_operation, agent_id)