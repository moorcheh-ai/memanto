"""
Tracing Utilities for MEMANTO Observability
"""

import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

# Context variables
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
span_stack_var: ContextVar[list["Span"] | None] = ContextVar("span_stack", default=None)


@dataclass
class Span:
    """Tracing span"""

    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "OK"
    error: str | None = None

    def finish(self, error: Exception | None = None):
        """Finish the span"""
        self.end_time = time.time()
        if error:
            self.status = "ERROR"
            self.error = str(error)

    def duration_ms(self) -> float:
        """Get span duration in milliseconds"""
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return (time.time() - self.start_time) * 1000

    def to_dict(self) -> dict[str, Any]:
        """Convert span to dictionary"""
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms(),
            "attributes": self.attributes,
            "status": self.status,
            "error": self.error,
        }


class MemantoTracer:
    """Simple tracer for MEMANTO (production should use OpenTelemetry)"""

    def __init__(self) -> None:
        self.spans: list[Span] = []

    def start_trace(self, name: str) -> str:
        """Start a new trace"""
        trace_id = f"trace_{uuid.uuid4().hex[:16]}"
        trace_id_var.set(trace_id)
        span_stack_var.set([])

        # Create root span
        self.start_span(name)
        return trace_id

    def start_span(self, name: str, attributes: dict[str, Any] | None = None) -> Span:
        """Start a new span"""
        trace_id = trace_id_var.get()
        if not trace_id:
            trace_id = self.start_trace(name)

        span_stack = span_stack_var.get()
        if span_stack is None:
            span_stack = []
            span_stack_var.set(span_stack)

        parent_span_id = span_stack[-1].span_id if span_stack else None

        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=f"span_{uuid.uuid4().hex[:12]}",
            parent_span_id=parent_span_id,
            attributes=attributes or {},
        )

        span_stack.append(span)
        span_stack_var.set(span_stack)
        self.spans.append(span)

        return span

    def finish_span(self, span: Span, error: Exception | None = None):
        """Finish a span"""
        span.finish(error)

        span_stack = span_stack_var.get()
        if span_stack is None:
            span_stack = []
            span_stack_var.set(span_stack)

        if span_stack and span_stack[-1] == span:
            span_stack.pop()
            span_stack_var.set(span_stack)

    def get_current_span(self) -> Span | None:
        """Get current active span"""
        span_stack = span_stack_var.get()
        if span_stack is None:
            span_stack = []
            span_stack_var.set(span_stack)

        return span_stack[-1] if span_stack else None

    def add_span_attribute(self, key: str, value: Any):
        """Add attribute to current span"""
        span = self.get_current_span()
        if span:
            span.attributes[key] = value


# Global tracer instance
tracer = MemantoTracer()


@contextmanager
def trace_span(name: str, attributes: dict[str, Any] | None = None):
    """Context manager for tracing spans"""
    span = tracer.start_span(name, attributes)
    try:
        yield span
    except Exception as e:
        tracer.finish_span(span, e)
        raise
    else:
        tracer.finish_span(span)


def trace_memory_operation(operation_type: str):
    """Decorator for tracing memory operations"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            with trace_span(f"memory.{operation_type}") as span:
                # Extract common attributes from request
                if args and hasattr(args[0], "scope"):
                    request = args[0]
                    span.attributes.update(
                        {
                            "scope_type": request.scope.scope_type,
                            "scope_id": request.scope.scope_id,
                        }
                    )

                    if hasattr(request, "memory_type"):
                        span.attributes["memory_type"] = request.memory_type

                    if hasattr(request, "provisional"):
                        span.attributes["provisional"] = request.provisional

                    if hasattr(request, "k"):
                        span.attributes["k"] = request.k

                return func(*args, **kwargs)

        return wrapper

    return decorator


def trace_moorcheh_call(method: str):
    """Decorator for tracing Moorcheh SDK calls"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            with trace_span(f"moorcheh.{method}") as span:
                span.attributes["moorcheh_method"] = method
                return func(*args, **kwargs)

        return wrapper

    return decorator


def get_trace_summary() -> dict[str, Any]:
    """Get summary of all traces"""
    traces: dict[str, list[dict[str, Any]]] = {}

    for span in tracer.spans:
        trace_id = span.trace_id
        if trace_id not in traces:
            traces[trace_id] = []
        traces[trace_id].append(span.to_dict())

    return traces
