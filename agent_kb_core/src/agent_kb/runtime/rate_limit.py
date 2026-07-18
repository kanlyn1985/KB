from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: float
    retry_after_seconds: float
    limit: int

    def to_dict(self) -> dict[str, float | int | bool]:
        return asdict(self)


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketRateLimiter:
    """In-process token bucket suitable for one service process.

    Distributed deployments should replace this implementation with a shared
    backend while retaining the `consume` contract.
    """

    def __init__(self, *, capacity: int = 60, refill_per_second: float = 1.0) -> None:
        if capacity < 1 or refill_per_second <= 0:
            raise ValueError("capacity and refill_per_second must be positive")
        self.capacity = int(capacity)
        self.refill_per_second = float(refill_per_second)
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def consume(self, key: str, *, cost: float = 1.0, now: float | None = None) -> RateLimitDecision:
        if cost <= 0:
            raise ValueError("cost must be positive")
        timestamp = time.monotonic() if now is None else float(now)
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=float(self.capacity), updated_at=timestamp)
                self._buckets[key] = bucket
            elapsed = max(0.0, timestamp - bucket.updated_at)
            bucket.tokens = min(float(self.capacity), bucket.tokens + elapsed * self.refill_per_second)
            bucket.updated_at = timestamp
            if bucket.tokens >= cost:
                bucket.tokens -= cost
                return RateLimitDecision(
                    allowed=True,
                    remaining=max(0.0, bucket.tokens),
                    retry_after_seconds=0.0,
                    limit=self.capacity,
                )
            deficit = cost - bucket.tokens
            return RateLimitDecision(
                allowed=False,
                remaining=max(0.0, bucket.tokens),
                retry_after_seconds=deficit / self.refill_per_second,
                limit=self.capacity,
            )

    def reset(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)
