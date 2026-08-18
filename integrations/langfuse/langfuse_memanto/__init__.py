"""
langfuse-memanto — turn Langfuse observability signal into Memanto memories,
live from your application.

Langfuse's Python SDK is built on OpenTelemetry, so this package attaches a
second span processor to the tracer provider Langfuse already set up. Failing
spans are grouped into one memory per error *signature* and written to Memanto
on a background thread::

    from langfuse import Langfuse
    from langfuse_memanto import attach

    Langfuse()
    attach(agent_id="my-agent")

Capture settings are shared with ``memanto migrate langfuse`` — configure them
once with ``memanto migrate langfuse --discover`` and ``--save``.
"""

from langfuse_memanto.config import HandlerSettings
from langfuse_memanto.handler import MemantoLangfuseHandler, attach
from langfuse_memanto.span_mapper import span_to_observation

# The core imports inside the handler are lazy, so a too-old `memanto` would
# otherwise import cleanly and only fail at attach() with a ModuleNotFoundError
# pointing at Memanto internals. The dependency pin normally prevents that;
# this catches the cases it cannot (--no-deps, a constraints file, a vendored
# checkout) and says what to do about it.
try:  # pragma: no cover - exercised by the packaging check, not unit tests
    import memanto.cli.migrate.langfuse_rules as _rules  # noqa: F401
except ModuleNotFoundError as _exc:  # pragma: no cover
    raise ImportError(
        "langfuse-memanto requires memanto>=0.2.14, which carries the Langfuse "
        "capture rules this package builds on. The installed memanto is older. "
        "Upgrade with:  pip install -U 'memanto>=0.2.14'"
    ) from _exc

__version__ = "0.1.0"

__all__ = [
    "HandlerSettings",
    "MemantoLangfuseHandler",
    "attach",
    "span_to_observation",
    "__version__",
]
