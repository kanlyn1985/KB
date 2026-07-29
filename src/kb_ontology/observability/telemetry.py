"""Lightweight tracing spans + optional OTLP/HTTP JSON exporter.

Adapted from agent_kb_core observability/telemetry (lean subset).
"""

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
    """Minimal OTLP/HTTP JSON exporter for traces."""

    endpoint: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 10.0
    service_name: str = "kb-ontology"

    @classmethod
    def from_environment(cls) -> OTLPHTTPJSONExporter:
        endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
        ).strip()
        raw_headers = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")
        headers: dict[str, str] = {}
        for item in raw_headers.split(","):
            if "=" in item:
                key, value = item.split("=", 1)
                headers[key.strip()] = value.strip()
        return cls(
            endpoint=endpoint,
            headers=headers,
            timeout_seconds=float(os.environ.get("OTEL_EXPORTER_OTLP_TIMEOUT", "10000"))
            / 1000.0,
            service_name=os.environ.get("OTEL_SERVICE_NAME", "kb-ontology"),
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
                            "scope": {"name": "kb_ontology.observability"},
                            "spans": [_otlp_span(span) for span in spans],
                        }
                    ],
                }
            ]
        }
        self._post("/v1/traces", payload)

    def export_metrics(self, metrics: dict[str, Any]) -> None:
        # Best-effort; many collectors ignore custom JSON metrics.
        self._post(
            "/v1/metrics",
            {"resourceMetrics": [{"metrics": metrics}]},
        )

    def _post(self, path: str, payload: dict[str, Any]) -> None:
        url = self.endpoint.rstrip("/") + path
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            **self.headers,
        }
        req = request.Request(url, data=body, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=self.timeout_seconds):
                return
        except (error.URLError, error.HTTPError, TimeoutError):
            return


class Tracer:
    """Simple nested span tracer with optional exporter."""

    def __init__(
        self,
        *,
        exporter: TelemetryExporter | None = None,
        service_name: str = "kb-ontology",
    ) -> None:
        self.exporter = exporter
        self.service_name = service_name
        self._stack: list[tuple[str, str, float, str, dict[str, Any]]] = []
        # (trace_id, span_id, started_perf, name, attributes)

    @contextmanager
    def span(
        self,
        name: str,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        trace_id = self._stack[-1][0] if self._stack else uuid4().hex
        parent_span_id = self._stack[-1][1] if self._stack else None
        span_id = uuid4().hex[:16]
        started_at = _utc_now_iso()
        started = time.perf_counter()
        attrs = dict(attributes or {})
        self._stack.append((trace_id, span_id, started, name, attrs))
        status = "ok"
        err: str | None = None
        try:
            yield attrs
        except Exception as exc:
            status = "error"
            err = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._stack.pop()
            ended = time.perf_counter()
            span = TraceSpan(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                name=name,
                started_at=started_at,
                ended_at=_utc_now_iso(),
                duration_ms=(ended - started) * 1000.0,
                status=status,
                attributes=attrs,
                error=err,
            )
            if self.exporter is not None:
                try:
                    self.exporter.export_spans([span])
                except Exception:
                    pass


def _otlp_span(span: TraceSpan) -> dict[str, Any]:
    return {
        "traceId": span.trace_id,
        "spanId": span.span_id,
        "parentSpanId": span.parent_span_id or "",
        "name": span.name,
        "startTimeUnixNano": "0",
        "endTimeUnixNano": "0",
        "attributes": [
            {"key": k, "value": {"stringValue": str(v)}}
            for k, v in span.attributes.items()
        ],
        "status": {
            "code": 2 if span.status == "error" else 1,
            "message": span.error or "",
        },
    }
