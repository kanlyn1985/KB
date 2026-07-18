from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class MetricSnapshot:
    counters: dict[str, int]
    durations_ms: dict[str, dict[str, float]]

    def to_dict(self) -> dict[str, object]:
        return {
            "counters": dict(self.counters),
            "durations_ms": {name: dict(values) for name, values in self.durations_ms.items()},
        }


class MetricsRegistry:
    """Thread-safe counters and duration summaries without external dependencies."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._durations: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + int(amount)

    def observe_ms(self, name: str, duration_ms: float) -> None:
        with self._lock:
            self._durations.setdefault(name, []).append(max(0.0, float(duration_ms)))

    @contextmanager
    def timer(self, name: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.observe_ms(name, (time.perf_counter() - started) * 1000.0)

    def snapshot(self) -> MetricSnapshot:
        with self._lock:
            counters = dict(self._counters)
            durations = {
                name: _summarize(values)
                for name, values in self._durations.items()
            }
        return MetricSnapshot(counters=counters, durations_ms=durations)


def _summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0.0, "min": 0.0, "max": 0.0, "mean": 0.0, "p95": 0.0}
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * 0.95))))
    return {
        "count": float(len(ordered)),
        "min": ordered[0],
        "max": ordered[-1],
        "mean": sum(ordered) / len(ordered),
        "p95": ordered[p95_index],
    }
