from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class LoadTestReport:
    request_count: int
    success_count: int
    error_count: int
    duration_seconds: float
    requests_per_second: float
    latency_ms_min: float
    latency_ms_mean: float
    latency_ms_p95: float
    latency_ms_max: float
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_load_test(
    operation: Callable[[int], Any],
    *,
    request_count: int = 100,
    concurrency: int = 8,
) -> LoadTestReport:
    if request_count < 1 or concurrency < 1:
        raise ValueError("request_count and concurrency must be positive")
    started = time.perf_counter()
    latencies: list[float] = []
    errors: list[str] = []

    def invoke(index: int) -> float:
        request_started = time.perf_counter()
        operation(index)
        return (time.perf_counter() - request_started) * 1000.0

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(invoke, index) for index in range(request_count)]
        for future in as_completed(futures):
            try:
                latencies.append(future.result())
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
    duration = max(0.000001, time.perf_counter() - started)
    ordered = sorted(latencies)
    return LoadTestReport(
        request_count=request_count,
        success_count=len(latencies),
        error_count=len(errors),
        duration_seconds=duration,
        requests_per_second=request_count / duration,
        latency_ms_min=ordered[0] if ordered else 0.0,
        latency_ms_mean=sum(ordered) / len(ordered) if ordered else 0.0,
        latency_ms_p95=_percentile(ordered, 0.95),
        latency_ms_max=ordered[-1] if ordered else 0.0,
        errors=errors[:100],
    )


@dataclass(frozen=True)
class ChaosPolicy:
    failure_rate: float = 0.0
    min_delay_ms: float = 0.0
    max_delay_ms: float = 0.0
    seed: int = 0

    def __post_init__(self) -> None:
        if not 0.0 <= self.failure_rate <= 1.0:
            raise ValueError("failure_rate must be between 0 and 1")
        if self.min_delay_ms < 0 or self.max_delay_ms < self.min_delay_ms:
            raise ValueError("invalid delay range")


class ChaosInjector:
    def __init__(self, operation: Callable[..., Any], policy: ChaosPolicy) -> None:
        self.operation = operation
        self.policy = policy
        self._random = random.Random(policy.seed)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if self.policy.max_delay_ms > 0:
            delay = self._random.uniform(self.policy.min_delay_ms, self.policy.max_delay_ms)
            time.sleep(delay / 1000.0)
        if self._random.random() < self.policy.failure_rate:
            raise RuntimeError("injected chaos failure")
        return self.operation(*args, **kwargs)


@dataclass(frozen=True)
class SecurityProbeResult:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, str | bool]:
        return asdict(self)


def run_security_probes(probes: Iterable[tuple[str, Callable[[], bool]]]) -> list[SecurityProbeResult]:
    results: list[SecurityProbeResult] = []
    for name, probe in probes:
        try:
            passed = bool(probe())
            detail = "passed" if passed else "returned false"
        except Exception as exc:
            passed = False
            detail = f"{type(exc).__name__}: {exc}"
        results.append(SecurityProbeResult(name=name, passed=passed, detail=detail))
    return results


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * quantile))))
    return values[index]
