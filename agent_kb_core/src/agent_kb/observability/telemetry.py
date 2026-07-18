from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Iterator, Protocol, Sequence
from urllib import error, request
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class TraceSpan:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    started_at: str
    ended_at: str
    duration_ms: float
    status: str
    attributes: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TelemetryExporter(Protocol):
    def export_spans(self, spans: Sequence[TraceSpan]) -> None: ...

    def export_metrics(self, metrics: dict[str, Any]) -> None: ...


@dataclass
class InMemoryTelemetryExporter:
    spans: list[TraceSpan] = field(default_factory=list)
    metric_snapshots: list[dict[str, Any]] = field(default_factory=list)

    def export_spans(self, spans: Sequence[TraceSpan]) -> None:
        self.spans.extend(spans)

    def export_metrics(self, metrics: dict[str, Any]) -> None:
        self.metric_snapshots.append(dict(metrics))


@dataclass(frozen=True)
class OTLPHTTPJSONExporter:
    """Minimal OTLP/HTTP JSON exporter for traces and metrics."""

    endpoint: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 10.0
    service_name: str = "agent-kb-core"

    @classmethod
    def from_environment(cls) -> OTLPHTTPJSONExporter:
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318").strip()
        raw_headers = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")
        headers: dict[str, str] = {}
        for item in raw_headers.split(","):
            if "=" in item:
                key, value = item.split("=", 1)
                headers[key.strip()] = value.strip()
        return cls(
            endpoint=endpoint,
            headers=headers,
            timeout_seconds=float(os.environ.get("OTEL_EXPORTER_OTLP_TIMEOUT", "10000")) / 1000.0,
            service_name=os.environ.get("OTEL_SERVICE_NAME", "agent-kb-core"),
        )

    def export_spans(self, spans: Sequence[TraceSpan]) -> None:
        payload = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {
                                "key": "service.name",
                                "value": {"stringValue": self.service_name},
                            }
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "agent_kb.observability"},
                            "spans": [_otlp_span(span) for span in spans],
                        }
                    ],
                }
            ]
        }
        self._post("/v1/traces", payload)

    def export_metrics(self, metrics: dict[str, Any]) -> None:
        now_ns = str(time.time_ns())
        gauge_metrics = []
        for name, value in _flatten_numeric(metrics):
            gauge_metrics.append(
                {
                    "name": name,
                    "gauge": {
                        "dataPoints": [
                            {
                                "timeUnixNano": now_ns,
                                "asDouble": float(value),
                            }
                        ]
                    },
                }
            )
        payload = {
            "resourceMetrics": [
                {
                    "resource": {
                        "attributes": [
                            {
                                "key": "service.name",
                                "value": {"stringValue": self.service_name},
                            }
                        ]
                    },
                    "scopeMetrics": [
                        {
                            "scope": {"name": "agent_kb.observability"},
                            "metrics": gauge_metrics,
                        }
                    ],
                }
            ]
        }
        self._post("/v1/metrics", payload)

    def _post(self, path: str, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **self.headers,
        }
        outbound = request.Request(
            self.endpoint.rstrip("/") + path,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(outbound, timeout=self.timeout_seconds):
                return
        except (error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"OTLP export failed: {type(exc).__name__}") from exc


class Tracer:
    def __init__(self, exporter: TelemetryExporter | None = None) -> None:
        self.exporter = exporter

    @contextmanager
    def span(
        self,
        name: str,
        *,
        attributes: dict[str, Any] | None = None,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> Iterator[dict[str, str]]:
        started_wall = _utc_now_iso()
        started = time.perf_counter()
        current_trace_id = trace_id or uuid4().hex
        span_id = uuid4().hex[:16]
        status = "ok"
        error_text: str | None = None
        try:
            yield {"trace_id": current_trace_id, "span_id": span_id}
        except Exception as exc:
            status = "error"
            error_text = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            ended_wall = _utc_now_iso()
            span = TraceSpan(
                trace_id=current_trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                name=name,
                started_at=started_wall,
                ended_at=ended_wall,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                status=status,
                attributes=dict(attributes or {}),
                error=error_text,
            )
            if self.exporter is not None:
                self.exporter.export_spans([span])


def _otlp_span(span: TraceSpan) -> dict[str, Any]:
    started_ns = str(_iso_to_ns(span.started_at))
    ended_ns = str(_iso_to_ns(span.ended_at))
    attributes = [
        {"key": key, "value": _otlp_value(value)}
        for key, value in span.attributes.items()
    ]
    if span.error:
        attributes.append({"key": "error.message", "value": {"stringValue": span.error}})
    return {
        "traceId": span.trace_id,
        "spanId": span.span_id,
        "parentSpanId": span.parent_span_id or "",
        "name": span.name,
        "kind": 1,
        "startTimeUnixNano": started_ns,
        "endTimeUnixNano": ended_ns,
        "attributes": attributes,
        "status": {"code": 2 if span.status == "error" else 1},
    }


def _otlp_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": str(value)}


def _iso_to_ns(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return int(parsed.timestamp() * 1_000_000_000)


def _flatten_numeric(payload: dict[str, Any], prefix: str = "") -> list[tuple[str, float]]:
    values: list[tuple[str, float]] = []
    for key, value in payload.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, bool):
            values.append((name, 1.0 if value else 0.0))
        elif isinstance(value, (int, float)):
            values.append((name, float(value)))
        elif isinstance(value, dict):
            values.extend(_flatten_numeric(value, name))
    return values
