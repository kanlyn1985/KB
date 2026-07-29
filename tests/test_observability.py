"""Metrics and tracer unit tests."""

from __future__ import annotations

from kb_ontology.observability import (
    InMemoryTelemetryExporter,
    MetricsRegistry,
    Tracer,
)


def test_metrics_counter_and_timer() -> None:
    reg = MetricsRegistry()
    reg.increment("requests")
    reg.increment("requests", 2)
    with reg.timer("work"):
        pass
    snap = reg.snapshot()
    assert snap.counters["requests"] == 3
    assert snap.durations_ms["work"]["count"] == 1.0
    assert "p95" in snap.durations_ms["work"]
    assert "counters" in snap.to_dict()


def test_tracer_exports_spans() -> None:
    exporter = InMemoryTelemetryExporter()
    tracer = Tracer(exporter=exporter)
    with tracer.span("outer", attributes={"k": "v"}):
        with tracer.span("inner"):
            pass
    assert len(exporter.spans) == 2
    names = {s.name for s in exporter.spans}
    assert names == {"outer", "inner"}
    outer = next(s for s in exporter.spans if s.name == "outer")
    assert outer.attributes["k"] == "v"
    assert outer.status == "ok"
