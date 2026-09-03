"""
Export Langfuse observability signal to JSON (observations and scores).

Used by ``memanto migrate langfuse``. Pure ``httpx`` — no Langfuse SDK
dependency, so users don't have to install ``langfuse`` and we don't break
when the SDK ships a new major version.

Endpoints (Langfuse public API — https://langfuse.com/docs/api-and-data-platform):
    GET  /api/public/v2/observations?fromStartTime=&toStartTime=&cursor=&level=
    GET  /api/public/v3/scores?fromTimestamp=&cursor=&valueMin=&valueMax=

Both ``GET /api/public/traces`` and the v1 ``/api/public/observations`` are
deprecated: traces are reconstructed by grouping v2 observation rows on
``traceId``. v2 uses opaque ``cursor`` pagination (not ``page``) and
``fromStartTime``/``toStartTime`` (not ``fromTimestamp``).

Auth: HTTP Basic with the public key as username and the secret key as
password. Memanto's migrate plumbing carries a single API-key string per
provider, so both keys travel as ``"pk-lf-...:sk-lf-..."`` and are split here.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from memanto.cli.migrate.langfuse_rules import CAPTURE_MODES

DEFAULT_HOST = "https://cloud.langfuse.com"
DEFAULT_PAGE_SIZE = 500
DEFAULT_WINDOW_DAYS = 7
REQUEST_TIMEOUT_S = 60.0

# Page-size ceilings differ per endpoint and are enforced server-side with a
# 400, so each fetch clamps to its own. v2 observations allows up to 1000;
# v3 scores rejects anything over 100.
MAX_LIMIT_OBSERVATIONS = 1000
MAX_LIMIT_SCORES = 100

# Guard against an unbounded sweep on a busy project. Each page is up to
# DEFAULT_PAGE_SIZE rows, so this caps one run at ~100k observations.
MAX_PAGES = 200

# Traces hydrated from score hits. Scores point at traces, so low-score and
# success capture need a second fetch per trace; cap it so a noisy eval run
# can't fan out into thousands of requests.
MAX_SCORED_TRACES = 200

# Field groups the mapper needs. `metrics`/`usage`/`model` carry latency and
# cost; `io` carries the input/output that error text is extracted from.
OBSERVATION_FIELDS = "core,basic,time,io,metadata,model,usage,metrics,trace_context"

# v3 scores omit their trace linkage unless `subject` is requested — without
# it every score comes back unattached and no score rule can ever match.
# (`core` carries name/value/dataType; valid groups are core, details,
# subject, annotation.)
SCORE_FIELDS = "core,subject"

# Modes that need every observation in the window, not just the errored ones:
# latency and cost are not server-side filterable, so they are classified
# client-side in langfuse_rules.
_UNFILTERED_MODES = frozenset({"slow", "costly"})
_SCORE_MODES = frozenset({"low_score", "success"})


def split_api_key(api_key: str) -> tuple[str, str]:
    """Split a combined ``"<public_key>:<secret_key>"`` credential.

    Langfuse needs two keys but the migrate CLI, the stored ``.env`` entry,
    and the UI all carry one string per provider, so the pair travels joined.
    """
    raw = (api_key or "").strip()
    public_key, _, secret_key = raw.partition(":")
    public_key = public_key.strip()
    secret_key = secret_key.strip()
    if not public_key or not secret_key:
        raise ValueError(
            "Langfuse needs both keys as 'pk-lf-...:sk-lf-...' "
            "(public key, colon, secret key). Get them from your Langfuse "
            "project settings."
        )
    return public_key, secret_key


import ipaddress
import socket

# Official Langfuse Cloud regions (allowed as-is).
_ALLOWED_LANGFUSE_HOSTS = {
    "https://cloud.langfuse.com",
    "https://us.cloud.langfuse.com",
    "https://eu.cloud.langfuse.com",
}


def _resolve_public_ip(host: str) -> str | None:
    """Resolve *host* and return a single public IP, or None if unsafe.

    Used to pin the connection target so a DNS rebind between validation and
    connect time cannot redirect the request at an internal address.
    """
    hostname = host.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].strip()
    if hostname in ("localhost", "0.0.0.0", "::1", "127.0.0.1"):
        return None
    try:
        infos = socket.getaddrinfo(hostname, None)
        for info in infos:
            addr = info[4][0].split("%", 1)[0]
            ip = ipaddress.ip_address(addr)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            ):
                continue  # skip internal addresses, but keep looking for a public one
            return addr
    except (socket.gaierror, ValueError):
        return None
    return None


def normalize_host(host: str | None) -> str:
    """Normalize a Langfuse base URL (cloud EU/US or self-hosted).

    SECURITY (#1852): the Langfuse secret key is transmitted as HTTP Basic auth,
    so a host value must never point at internal infrastructure or travel in
    cleartext. Rules:
      * empty -> official cloud default
      * explicit http:// -> rejected (cleartext + Langfuse is HTTPS-only)
      * official cloud regions -> allowed as-is
      * any other host -> must resolve to a PUBLIC IP (DNS-rebind guard);
        private/loopback/link-local/metadata hosts fall back to the default
    """
    text = (host or "").strip().rstrip("/")
    if not text:
        return DEFAULT_HOST
    if text.startswith("http://"):
        # Reject cleartext custom hosts: the secret key must not go over HTTP.
        return DEFAULT_HOST
    if not text.startswith("https://"):
        text = f"https://{text}"
    if text in _ALLOWED_LANGFUSE_HOSTS:
        return text
    ip = _resolve_public_ip(text)
    if ip is None:
        return DEFAULT_HOST
    return text


import contextlib
import socket as _socket_module


@contextlib.contextmanager
def _pinned_getaddrinfo(pin_host: str, pin_ip: str, pin_family: int):
    """Temporarily shadow socket.getaddrinfo so *pin_host* always resolves to *pin_ip*.

    This is the DNS-rebinding defense: we resolved and validated *pin_host* as a
    public address once (see normalize_host/_pinned_transport), then force every
    connect-time lookup of that name to return the same validated IP — even if the
    real name server would now answer with an internal address. Restores the
    original resolver on exit.
    """
    orig = _socket_module.getaddrinfo

    def _pinned(*args: Any, **kwargs: Any) -> Any:
        if args and args[0] == pin_host:
            return [(pin_family, _socket_module.SOCK_STREAM, 6, "", (pin_ip, 0))]
        return orig(*args, **kwargs)

    _socket_module.getaddrinfo = _pinned  # type: ignore[misc]
    try:
        yield
    finally:
        _socket_module.getaddrinfo = orig  # type: ignore[misc]


class _PinnedIPTransport(httpx.HTTPTransport):
    """Transport that pins a hostname to a pre-validated public IP at connect time.

    httpx/httpcore resolve DNS when the connection opens, not when the URL is
    built. Without a pin, a hostile name server could return a public address at
    validation time and an internal (metadata/loopback/RFC1918) address at connect
    time, bypassing the SSRF guard. We shadow ``socket.getaddrinfo`` for the target
    hostname during the connect so the TCP connection always lands on the IP we
    already validated as public. The original hostname stays in the Host header and
    TLS SNI (``base_url`` is unchanged).
    """

    def __init__(self, pin_host: str, pin_ip: str, pin_family: int, **kwargs: Any):
        super().__init__(**kwargs)
        self._pin_host = pin_host
        self._pin_ip = pin_ip
        self._pin_family = pin_family

    def handle_request(self, request: Any) -> Any:  # type: ignore[override]
        with _pinned_getaddrinfo(self._pin_host, self._pin_ip, self._pin_family):
            return super().handle_request(request)


def _pinned_transport(host: str) -> httpx.HTTPTransport:
    """Build a connection-time IP-pinned transport for *host* (or a plain one).

    The IP is resolved once here (after normalize_host already guaranteed it is
    public) and forced at connect time. If the host cannot be resolved to a public
    IP, a default transport is returned.
    """
    hostname = host.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].strip()
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return httpx.HTTPTransport()
    try:
        infos = _socket_module.getaddrinfo(hostname, None)
    except (_socket_module.gaierror, ValueError):
        return httpx.HTTPTransport()
    for info in infos:
        addr = info[4][0].split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            continue
        return _PinnedIPTransport(pin_host=hostname, pin_ip=addr, pin_family=info[0])
    return httpx.HTTPTransport()


def _client(api_key: str, host: str) -> httpx.Client:
    public_key, secret_key = split_api_key(api_key)
    return httpx.Client(
        base_url=host,
        timeout=REQUEST_TIMEOUT_S,
        auth=httpx.BasicAuth(public_key, secret_key),
        headers={"Content-Type": "application/json"},
        transport=_pinned_transport(host),
    )


US_HOST = "https://us.cloud.langfuse.com"


def _get_json(
    client: httpx.Client, path: str, params: dict[str, Any] | None = None
) -> Any:
    resp = client.get(path, params=params or {})
    if resp.status_code >= 400:
        message = f"GET {path} -> {resp.status_code}: {resp.text[:500]}"
        # Langfuse Cloud is regional and keys are not valid across regions, so
        # a US-region project hit against the EU default fails as "invalid
        # credentials" — which sends people hunting for a key problem instead.
        if resp.status_code == 401 and str(client.base_url).rstrip("/") == DEFAULT_HOST:
            message += (
                f"\n\nIf your project is on Langfuse Cloud US, the keys are only "
                f"valid there — retry with --host {US_HOST} "
                f"(or set LANGFUSE_HOST)."
            )
        raise RuntimeError(message)
    return resp.json() if resp.content else {}


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    """Pull the row list out of a Langfuse list response.

    The v2/v3 list envelopes key their rows as ``data``; older and
    self-hosted builds have shipped ``items``. Accept both rather than
    silently returning nothing against a slightly different deployment.
    """
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "items"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _extract_cursor(payload: Any) -> str | None:
    """Pull the next-page cursor out of a Langfuse list response."""
    if not isinstance(payload, dict):
        return None
    meta = payload.get("meta")
    if isinstance(meta, dict):
        cursor = meta.get("nextCursor")
        if isinstance(cursor, str) and cursor:
            return cursor
    cursor = payload.get("nextCursor")
    if isinstance(cursor, str) and cursor:
        return cursor
    return None


def paginate(
    client: httpx.Client,
    path: str,
    params: dict[str, Any],
    *,
    page_size: int,
    on_progress: Callable[[str], None] | None = None,
    label: str = "rows",
) -> list[dict[str, Any]]:
    """Walk every cursor page of a Langfuse list endpoint."""
    rows: list[dict[str, Any]] = []
    cursor: str | None = None

    for page in range(MAX_PAGES):
        page_params = {**params, "limit": page_size}
        if cursor:
            page_params["cursor"] = cursor
        payload = _get_json(client, path, params=page_params)

        batch = _extract_items(payload)
        rows.extend(batch)
        if on_progress and batch:
            on_progress(f"  fetched {len(rows)} {label} (page {page + 1})")

        cursor = _extract_cursor(payload)
        if not cursor or not batch:
            break
    else:
        if on_progress:
            on_progress(
                f"  stopped at the {MAX_PAGES}-page cap — narrow --since to "
                f"capture the rest"
            )

    return rows


def fetch_observations(
    client: httpx.Client,
    *,
    from_time: datetime,
    to_time: datetime,
    level: str | None = None,
    trace_id: str | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    on_progress: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Fetch observation rows in a time window, optionally filtered by level."""
    params: dict[str, Any] = {
        "fields": OBSERVATION_FIELDS,
        "fromStartTime": from_time.isoformat(),
        "toStartTime": to_time.isoformat(),
    }
    if level:
        params["level"] = level
    if trace_id:
        params["traceId"] = trace_id

    return paginate(
        client,
        "/api/public/v2/observations",
        params,
        page_size=min(page_size, MAX_LIMIT_OBSERVATIONS),
        on_progress=on_progress,
        label="observations",
    )


def fetch_scores(
    client: httpx.Client,
    *,
    from_time: datetime,
    page_size: int = DEFAULT_PAGE_SIZE,
    on_progress: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Fetch every score row in the window.

    Deliberately unfiltered. Langfuse scores may be numeric, categorical,
    boolean, or text, with user-defined names and ranges and no convention for
    whether higher is better, so there is no server-side value filter that
    would be correct in general. Which scores mean "failure" is decided
    client-side by the user's rules, and discovery needs the full set anyway.
    """
    return paginate(
        client,
        "/api/public/v3/scores",
        {"fromTimestamp": from_time.isoformat(), "fields": SCORE_FIELDS},
        page_size=min(page_size, MAX_LIMIT_SCORES),
        on_progress=on_progress,
        label="scores",
    )


def _traces_matching_rules(
    scores: list[dict[str, Any]], config: Any | None
) -> list[str]:
    """Trace ids whose scores the user's rules flag, in first-seen order.

    Returns nothing when no rules are configured — which is correct: without a
    rule there is no way to know which scores mean failure, and guessing would
    write wrong memories.
    """
    if config is None:
        return []

    from memanto.cli.migrate.langfuse_rules import (
        score_modes_by_trace,
        score_trace_id,
    )

    matched = score_modes_by_trace(scores, config)
    if not matched:
        return []

    seen: set[str] = set()
    ordered: list[str] = []
    for score in scores:
        trace_id = score_trace_id(score)
        if trace_id in matched and trace_id not in seen:
            seen.add(trace_id)
            ordered.append(trace_id)
    return ordered


def _dedupe_observations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per observation id — score hydration can re-fetch known rows."""
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        row_id = row.get("id")
        if isinstance(row_id, str) and row_id:
            if row_id in seen:
                continue
            seen.add(row_id)
        unique.append(row)
    return unique


def run_langfuse_export(
    api_key: str,
    dest_dir: Path,
    *,
    host: str = DEFAULT_HOST,
    since: datetime | None = None,
    capture: set[str] | None = None,
    config: Any | None = None,
    discover: bool = False,
    page_size: int = DEFAULT_PAGE_SIZE,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """
    Export Langfuse observations and scores and write JSON into *dest_dir*.

    Which rows get pulled depends on *capture*:

    ``errors``
        ``level=ERROR`` observations — filtered server-side, so this is the
        cheap path and the default.
    ``slow`` / ``costly``
        Every observation in the window (latency and cost are not
        server-side filterable); ``langfuse_rules`` classifies them.
    ``low_score`` / ``success``
        Every score in the window, then the observations of whichever traces
        the user's score rules match.

    Latency and cost budgets are not fetch filters — Langfuse cannot filter on
    them server-side, so ``langfuse_rules`` applies them client-side.

    Set *discover* to pull an unfiltered sample of observations and every
    score, for ``langfuse_discover.discover`` to summarize.

    Returns the written file path and the full export dict.
    """
    modes = set(capture or (config.modes if config is not None else {"errors"}))
    unknown = modes - set(CAPTURE_MODES)
    if unknown:
        raise ValueError(
            f"Unknown capture mode(s): {sorted(unknown)}. "
            f"Valid: {', '.join(CAPTURE_MODES)}"
        )
    if not modes:
        raise ValueError("At least one capture mode is required.")

    page_size = max(1, page_size)
    host = normalize_host(host)
    to_time = datetime.now(timezone.utc)
    from_time = since or (to_time - timedelta(days=DEFAULT_WINDOW_DAYS))

    observations: list[dict[str, Any]] = []
    scores: list[dict[str, Any]] = []

    with _client(api_key, host) as client:
        window = f"{from_time.date()} → {to_time.date()}"

        if discover:
            # Discovery inspects the shape of the data, so it must not
            # pre-filter: an unfiltered sweep plus every score.
            if on_progress:
                on_progress(f"Sampling observations and scores ({window})...")
            observations.extend(
                fetch_observations(
                    client,
                    from_time=from_time,
                    to_time=to_time,
                    page_size=page_size,
                    on_progress=on_progress,
                )
            )
            scores.extend(
                fetch_scores(
                    client,
                    from_time=from_time,
                    page_size=page_size,
                    on_progress=on_progress,
                )
            )
        elif modes & _UNFILTERED_MODES:
            # One unfiltered sweep also covers `errors`, so don't re-fetch.
            if on_progress:
                on_progress(f"Fetching all observations ({window})...")
            observations.extend(
                fetch_observations(
                    client,
                    from_time=from_time,
                    to_time=to_time,
                    page_size=page_size,
                    on_progress=on_progress,
                )
            )
        elif "errors" in modes:
            if on_progress:
                on_progress(f"Fetching errored observations ({window})...")
            observations.extend(
                fetch_observations(
                    client,
                    from_time=from_time,
                    to_time=to_time,
                    level="ERROR",
                    page_size=page_size,
                    on_progress=on_progress,
                )
            )

        if not discover and modes & _SCORE_MODES:
            if on_progress:
                on_progress("Fetching scores...")
            scores.extend(
                fetch_scores(
                    client,
                    from_time=from_time,
                    page_size=page_size,
                    on_progress=on_progress,
                )
            )

            # Only hydrate traces the user's rules actually flag. Without
            # rules nothing can match, so nothing is fetched — and the caller
            # reports the mode as unconfigured rather than silently empty.
            matched = _traces_matching_rules(scores, config)
            trace_ids = matched[:MAX_SCORED_TRACES]
            if trace_ids and on_progress:
                on_progress(f"Hydrating {len(trace_ids)} scored traces...")
            for trace_id in trace_ids:
                observations.extend(
                    fetch_observations(
                        client,
                        from_time=from_time,
                        to_time=to_time,
                        trace_id=trace_id,
                        page_size=page_size,
                    )
                )

    observations = _dedupe_observations(observations)

    export = {
        "exported_at": to_time.isoformat(),
        "api_base": host,
        "summary": {
            "observation_count": len(observations),
            "score_count": len(scores),
            "capture_modes": sorted(modes),
            "from_time": from_time.isoformat(),
            "to_time": to_time.isoformat(),
            "discover": discover,
            "page_size": page_size,
        },
        "observations": observations,
        "scores": scores,
        "notes": {
            "endpoints": "v2 observations + v3 scores; /traces and v1 "
            "/observations are deprecated and unused.",
            "grouping": "Rows are raw. `memanto migrate langfuse` groups them "
            "into one memory per error signature — see cli/migrate/langfuse_rules.py.",
            "caps": f"At most {MAX_PAGES} pages per query and "
            f"{MAX_SCORED_TRACES} hydrated traces per score mode.",
        },
    }

    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / "langfuse_export.json"

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False, default=str)

    return out_path, export
