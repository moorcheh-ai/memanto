"""
Live Langfuse -> Memanto capture, as an OpenTelemetry span processor.

Langfuse's Python SDK is built on OpenTelemetry and attaches its own span
processor to the global ``TracerProvider``. Adding a second processor is
therefore all it takes to see every span the application produces, with no
extra instrumentation and no dependency on Langfuse's own API:

    from langfuse import Langfuse
    from langfuse_memanto import attach

    Langfuse()                      # your existing setup
    attach(agent_id="my-agent")     # one line

Design notes:

* **Nothing runs on the hot path.** ``on_end`` maps the span and appends it to
  a buffer; all grouping, reconciliation, and network I/O happen on a daemon
  thread. Every entry point swallows its own exceptions — a memory that fails
  to write must never break the traced application.
* **One memory per signature, not per occurrence.** Buffered spans are handed
  to ``run_langfuse_sync``, the same function ``memanto migrate langfuse``
  uses, so a retry storm collapses to a single memory and the two paths write
  byte-identical content.
* **Shared ledger.** Writes are recorded in
  ``~/.memanto/migrate/langfuse/state.json`` under the same
  ``project::agent`` scope the CLI uses, so a later sync sees them as already
  written instead of duplicating them.

Limits worth knowing (see README):

* Score-driven modes (``low-score``/``success``) cannot work live — Langfuse
  scores are attached *after* a trace finishes, so nothing in the span carries
  them. Use the periodic sync for those.
* Percentile budgets need a population to calibrate against and are ignored
  here; give ``slow``/``costly`` an absolute budget if you want them live.
"""

from __future__ import annotations

import atexit
import logging
import os
import threading
from typing import Any

from opentelemetry.sdk.trace import SpanProcessor

from langfuse_memanto.config import HandlerSettings
from langfuse_memanto.span_mapper import span_to_observation

logger = logging.getLogger(__name__)

# A storm can outrun the flush interval; past this the buffer stops growing and
# drops are counted rather than letting an incident exhaust memory.
_HARD_BUFFER_FACTOR = 20

# Consecutive failed flushes before a batch is abandoned. Transient blips
# recover well within this; a permanently bad key or dead backend must not
# hold observations forever.
_MAX_FLUSH_ATTEMPTS = 4

_LIVE_UNSUPPORTED_MODES = ("low_score", "success")


class MemantoLangfuseHandler(SpanProcessor):
    """Writes failing Langfuse spans into Memanto as they happen."""

    def __init__(
        self,
        agent_id: str | None = None,
        *,
        api_key: str | None = None,
        project_key: str | None = None,
        capture: list[str] | None = None,
        latency_ms: float | None = None,
        cost_usd: float | None = None,
        score_fail: list[str] | None = None,
        score_pass: list[str] | None = None,
        group_by: str | None = None,
        auto_create_agent: bool | None = None,
        settings: HandlerSettings | None = None,
        client: Any | None = None,
        host: str = "https://cloud.langfuse.com",
    ) -> None:
        self.settings = settings or HandlerSettings()
        self.agent_id = agent_id or self.settings.agent_id
        if not self.agent_id:
            raise ValueError(
                "No agent to write to. Pass agent_id=... or set "
                "MEMANTO_LANGFUSE_AGENT_ID."
            )

        self._api_key = api_key or self.settings.api_key_value()
        self._client = client
        self._host = host.rstrip("/")
        self._auto_create = (
            self.settings.auto_create_agent
            if auto_create_agent is None
            else auto_create_agent
        )
        self._agent_ready = False
        self._consecutive_failures = 0

        self._buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        # Separate from `_lock`, which only guards the buffer. A flush is a
        # load-modify-save cycle over the shared ledger, and two of them
        # overlapping would each save their own view of the scope — the slower
        # writer erasing the faster one's newly recorded signatures. The worker
        # thread and an application calling flush()/shutdown() really can
        # overlap, so the cycle is serialized.
        self._flush_lock = threading.Lock()
        self._wake = threading.Event()
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

        self.dropped = 0
        self.captured = 0
        self.written = 0

        self._config, self._project_key = self._build_capture_config(
            project_key or self.settings.project_key,
            capture=capture,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            score_fail=score_fail,
            score_pass=score_pass,
            group_by=group_by,
        )
        self._warn_about_live_limits()

    # -- setup ---------------------------------------------------------

    def _build_capture_config(
        self,
        project_key: str | None,
        *,
        capture: list[str] | None,
        latency_ms: float | None,
        cost_usd: float | None,
        score_fail: list[str] | None,
        score_pass: list[str] | None,
        group_by: str | None,
    ) -> tuple[Any, str]:
        """Merge in-code settings over the profile the CLI and UI share.

        Anything passed in code wins, so an app can be entirely
        self-configuring; anything omitted falls back to
        ``~/.memanto/migrate/langfuse/config.json`` so a team that manages
        capture rules centrally does not have to repeat them in every service.
        """
        from memanto.cli.config.manager import ConfigManager
        from memanto.cli.migrate.langfuse_config import (
            config_path,
            load_project,
            parse_score_rule,
        )
        from memanto.cli.migrate.langfuse_config import (
            project_key as derive_project_key,
        )
        from memanto.cli.migrate.langfuse_rules import (
            CaptureConfig,
            parse_capture_modes,
        )

        # Derive the project identity the same way the CLI does, from the
        # Langfuse credential the app already has configured. Without this the
        # handler would file its writes under "default" while `memanto migrate
        # langfuse` used the key-derived scope — and the sync would re-write
        # every memory the app had already stored.
        #
        # Precedence mirrors ConfigManager.get_langfuse_api_key: the combined
        # LANGFUSE_API_KEY first, then the vendor-native public key. Reading
        # only the latter would miss users who set just the combined form.
        # `project_key` splits on ":", so passing either shape is safe.
        key = project_key or derive_project_key(
            api_key=(
                os.environ.get("LANGFUSE_API_KEY")
                or os.environ.get("LANGFUSE_PUBLIC_KEY")
            )
        )
        base_dir = ConfigManager().get_migrate_dir("langfuse")
        stored = load_project(config_path(base_dir), key)

        config = CaptureConfig(
            modes=parse_capture_modes(capture) if capture else stored.capture,
            score_fail_rules=(
                tuple(parse_score_rule(r) for r in score_fail)
                if score_fail
                else tuple(stored.score_fail_rules)
            ),
            score_pass_rules=(
                tuple(parse_score_rule(r) for r in score_pass)
                if score_pass
                else tuple(stored.score_pass_rules)
            ),
            latency_ms=latency_ms if latency_ms is not None else stored.latency_ms,
            latency_percentile=stored.latency_percentile,
            cost_usd=cost_usd if cost_usd is not None else stored.cost_usd,
            cost_percentile=stored.cost_percentile,
            group_by=group_by or stored.group_by,
        )
        return config, key

    def _ensure_agent(self, client: Any) -> None:
        """Make sure the agent exists and has a live session.

        Lets an app work from a bare API key with no CLI setup. Activation is
        tried first because the agent usually already exists, which costs one
        call instead of two.
        """
        if self._agent_ready:
            return
        from memanto.app.utils.errors import (
            AgentAlreadyExistsError,
            AgentNotFoundError,
        )

        agent_id = str(self.agent_id)
        try:
            client.activate_agent(agent_id, duration_hours=self.settings.session_hours)
        except AgentNotFoundError:
            if not self._auto_create:
                raise
            logger.info("langfuse-memanto: creating agent '%s'", agent_id)
            try:
                client.create_agent(agent_id=agent_id, pattern="tool")
            except AgentAlreadyExistsError:
                pass  # another process won the race
            client.activate_agent(agent_id, duration_hours=self.settings.session_hours)
        self._agent_ready = True

    def _warn_about_live_limits(self) -> None:
        """Say plainly which configured modes this path cannot honour."""
        unsupported = [m for m in _LIVE_UNSUPPORTED_MODES if m in self._config.modes]
        if unsupported:
            logger.warning(
                "langfuse-memanto: %s cannot be captured live — Langfuse scores "
                "arrive after a trace ends. Run 'memanto migrate langfuse' "
                "periodically to pick those up.",
                ", ".join(m.replace("_", "-") for m in unsupported),
            )
        if "slow" in self._config.modes and self._config.latency_ms is None:
            logger.warning(
                "langfuse-memanto: 'slow' has no absolute latency budget; "
                "percentile budgets need a population and are ignored live. "
                "Set --latency-ms to capture slow spans from the app."
            )
        if "costly" in self._config.modes:
            logger.warning(
                "langfuse-memanto: 'costly' only fires live if your app sets "
                "cost_details on the observation itself. Langfuse otherwise "
                "computes cost server-side after ingestion, where a span "
                "processor cannot see it — run 'memanto migrate langfuse' to "
                "capture cost anomalies."
            )

    def attach(self, tracer_provider: Any | None = None) -> MemantoLangfuseHandler:
        """Register on the tracer provider Langfuse is already using."""
        if tracer_provider is None:
            from opentelemetry import trace

            tracer_provider = trace.get_tracer_provider()

        adder = getattr(tracer_provider, "add_span_processor", None)
        if adder is None:
            raise RuntimeError(
                "The active OpenTelemetry TracerProvider cannot take another "
                "span processor. Initialise Langfuse (or your own SDK "
                "TracerProvider) before calling attach()."
            )
        adder(self)
        self._start_worker()
        atexit.register(self.shutdown)
        return self

    def _start_worker(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="langfuse-memanto-flush", daemon=True
        )
        self._thread.start()

    # -- SpanProcessor ------------------------------------------------

    def on_start(self, span: Any, parent_context: Any = None) -> None:
        """Nothing to do: only completed spans carry status and timing."""

    def on_end(self, span: Any) -> None:
        """Buffer a capture-worthy span. Must be fast and must never raise."""
        try:
            observation = span_to_observation(span)
            if observation is None:
                return

            from memanto.cli.migrate.langfuse_rules import classify

            if classify(observation, self._config) is None:
                return

            with self._lock:
                if len(self._buffer) >= self.settings.max_buffer * _HARD_BUFFER_FACTOR:
                    self.dropped += 1
                    return
                self._buffer.append(observation)
                self.captured += 1
                should_flush = len(self._buffer) >= self.settings.max_buffer
            if should_flush:
                self._wake.set()
        except Exception:  # pragma: no cover - defensive
            logger.debug("langfuse-memanto: span capture failed", exc_info=True)

    def shutdown(self) -> None:
        """Flush what is buffered and stop the worker."""
        if self._stopped.is_set():
            return
        self._stopped.set()
        self._wake.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=10)
        self.flush()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        """OpenTelemetry's flush hook."""
        self.flush()
        return True

    # -- writing ------------------------------------------------------

    def _run(self) -> None:
        while not self._stopped.is_set():
            self._wake.wait(self.settings.flush_interval_seconds)
            self._wake.clear()
            self.flush()

    def _get_client(self) -> Any:
        if self._client is None:
            from memanto.cli.client.sdk_client import SdkClient

            if not self._api_key:
                raise RuntimeError(
                    "No Memanto API key. Pass api_key=... or set MOORCHEH_API_KEY."
                )
            self._client = SdkClient(self._api_key)
        return self._client

    def _requeue(self, batch: list[dict[str, Any]]) -> None:
        """Put a failed batch back so the next flush retries it.

        Retrying the whole batch is safe because reconciliation is idempotent:
        anything that did get written is already in the ledger and comes back
        as "unchanged". After ``_MAX_FLUSH_ATTEMPTS`` consecutive failures the
        batch is dropped — a permanently bad key or dead backend must not grow
        the buffer without bound.
        """
        self._consecutive_failures += 1
        if self._consecutive_failures >= _MAX_FLUSH_ATTEMPTS:
            with self._lock:
                self.dropped += len(batch)
            logger.warning(
                "langfuse-memanto: giving up on %d observations after %d failed "
                "flushes. Langfuse still has the traces — 'memanto migrate "
                "langfuse' can recover them.",
                len(batch),
                self._consecutive_failures,
            )
            self._consecutive_failures = 0
            return

        hard_cap = self.settings.max_buffer * _HARD_BUFFER_FACTOR
        with self._lock:
            room = max(0, hard_cap - len(self._buffer))
            kept = batch[:room]
            self.dropped += len(batch) - len(kept)
            # Oldest first: newer observations are already behind them.
            self._buffer[:0] = kept

    def flush(self) -> int:
        """Write buffered spans as memories. Returns the number written.

        Reuses ``run_langfuse_sync`` so grouping, reconciliation against the
        ledger, batching, and payload shaping are the same code the CLI runs.
        A batch that fails to write is retained and retried, not discarded.
        """
        with self._flush_lock:
            return self._flush_locked()

    def _flush_locked(self) -> int:
        with self._lock:
            if not self._buffer:
                return 0
            batch, self._buffer = self._buffer, []

        try:
            from memanto.cli.config.manager import ConfigManager
            from memanto.cli.migrate.langfuse_state import (
                load_state,
                save_state,
                scope_key,
                state_path,
            )
            from memanto.cli.migrate.runner import run_langfuse_sync

            base_dir = ConfigManager().get_migrate_dir("langfuse")
            ledger = state_path(base_dir)
            scope = scope_key(self._project_key, str(self.agent_id))
            state = load_state(ledger, scope)

            client = self._get_client()
            self._ensure_agent(client)

            summary, _rows, _plan = run_langfuse_sync(
                export={
                    "api_base": self._host,
                    "observations": batch,
                    "scores": [],
                    "summary": {},
                },
                client=client,
                agent_id=str(self.agent_id),
                state=state,
                dry_run=False,
                config=self._config,
            )
            # A failed write leaves the cursor where it was, so the next sync
            # still covers what was not stored.
            save_state(ledger, state, scope, advance_cursor=summary.failed == 0)

            written = int(summary.imported) + int(summary.updated)
            self.written += written

            if summary.failed:
                logger.warning(
                    "langfuse-memanto: %d memories failed to write, retrying: %s",
                    summary.failed,
                    "; ".join(summary.errors[:3]),
                )
                self._requeue(batch)
                return written

            self._consecutive_failures = 0
            return written
        except Exception:
            # Never take the application down, but do not silently drop the
            # observations either — hold them for the next attempt.
            logger.warning("langfuse-memanto: flush failed, retrying", exc_info=True)
            self._requeue(batch)
            return 0

    def stats(self) -> dict[str, int]:
        """Counters for debugging what the handler has seen and done."""
        with self._lock:
            pending = len(self._buffer)
        return {
            "captured": self.captured,
            "written": self.written,
            "dropped": self.dropped,
            "pending": pending,
        }


def attach(
    agent_id: str | None = None,
    *,
    api_key: str | None = None,
    project_key: str | None = None,
    capture: list[str] | None = None,
    latency_ms: float | None = None,
    cost_usd: float | None = None,
    score_fail: list[str] | None = None,
    score_pass: list[str] | None = None,
    group_by: str | None = None,
    auto_create_agent: bool | None = None,
    host: str = "https://cloud.langfuse.com",
    tracer_provider: Any | None = None,
) -> MemantoLangfuseHandler:
    """Start capturing failing Langfuse spans into Memanto.

    Call once, after Langfuse is initialised. With only an API key set, this
    is all the setup there is — the agent is created and activated on first
    write::

        Langfuse()
        attach(agent_id="my-agent")

    Capture rules can be given here instead of via the CLI::

        attach(
            agent_id="my-agent",
            capture=["errors", "slow"],
            latency_ms=5000,
        )

    Anything omitted falls back to the shared profile in
    ``~/.memanto/migrate/langfuse/config.json``.
    """
    handler = MemantoLangfuseHandler(
        agent_id,
        api_key=api_key,
        project_key=project_key,
        capture=capture,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        score_fail=score_fail,
        score_pass=score_pass,
        group_by=group_by,
        auto_create_agent=auto_create_agent,
        host=host,
    )
    return handler.attach(tracer_provider)
