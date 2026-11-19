"""Tracing for every agent on the platform.

``init_tracing()`` turns on Braintrust's native Strands integration: each ``Agent`` call, model call,
event-loop cycle and tool call becomes a span, nested under whatever span the app has open. Teams
call it once at startup; nothing else in their agent changes.

Where the data goes is set by environment only:
  BRAINTRUST_API_KEY   from AWS Secrets Manager (runtime) or the CI secret
  BRAINTRUST_API_URL   the data plane in our own AWS account (BYOC); unset = Braintrust cloud
  BRAINTRUST_PROJECT   one project per agent team
  BRAINTRUST_TRACE_ENABLED=false   no tracing (local runs, unit tests)
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

import braintrust
from braintrust.integrations.strands import setup_strands

_logger = None


def trace_enabled() -> bool:
    return os.environ.get("BRAINTRUST_TRACE_ENABLED", "true").lower() != "false"


def init_tracing(project: str | None = None):
    """Start the project logger and instrument Strands. Safe to call more than once."""
    global _logger
    if _logger is not None:
        return _logger
    project = project or os.environ["BRAINTRUST_PROJECT"]
    _logger = braintrust.init_logger(project=project, set_current=True)
    setup_strands(project_name=project)
    return _logger


def logger():
    return _logger or init_tracing()


def _active_parent():
    """The Braintrust span for the Strands span that is running now (a tool call), else the current span."""
    try:
        from braintrust.integrations.strands.tracing import _current_parent_span
        parent = _current_parent_span()
    except Exception:  # older SDKs
        parent = None
    return parent or braintrust.current_span()


@contextmanager
def child_span(name: str, type: str = "task", **event: Any) -> Iterator[Any]:
    """A span under the running tool call (so work a tool starts nests under it), current while open."""
    with _active_parent().start_span(name=name, type=type, **event) as span:
        yield span


def instrument_strands() -> None:
    """Instrument Strands without starting a project logger (evals log to their experiment)."""
    from braintrust.integrations.strands import StrandsIntegration
    StrandsIntegration.setup()
