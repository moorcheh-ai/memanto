"""Tests for the Langfuse exporter: credentials, hosts, and cursor pagination."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from memanto.cli.analyze import langfuse_export
from memanto.cli.analyze.langfuse_export import (
    MAX_PAGES,
    normalize_host,
    paginate,
    run_langfuse_export,
    split_api_key,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.content = b"x"
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeClient:
    """Stands in for httpx.Client, recording every request it serves."""

    def __init__(self, pages):
        self._pages = list(pages)
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        if self._pages:
            return FakeResponse(self._pages.pop(0))
        return FakeResponse({"data": [], "meta": {"nextCursor": None}})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# --------------------------------------------------------------------------
# Credentials and host
# --------------------------------------------------------------------------


def test_split_api_key_splits_the_combined_pair():
    assert split_api_key("pk-lf-abc:sk-lf-xyz") == ("pk-lf-abc", "sk-lf-xyz")
    assert split_api_key("  pk-lf-abc : sk-lf-xyz  ") == ("pk-lf-abc", "sk-lf-xyz")


@pytest.mark.parametrize("bad", ["", "pk-lf-only", "pk-lf-abc:", ":sk-lf-xyz"])
def test_split_api_key_rejects_a_half_credential(bad):
    with pytest.raises(ValueError, match="both keys"):
        split_api_key(bad)


def test_normalize_host_handles_cloud_and_self_hosted():
    assert normalize_host(None) == "https://cloud.langfuse.com"
    assert normalize_host("") == "https://cloud.langfuse.com"
    assert normalize_host("https://us.cloud.langfuse.com/") == (
        "https://us.cloud.langfuse.com"
    )
    assert normalize_host("langfuse.internal") == "https://langfuse.internal"
    assert normalize_host("http://localhost:3000") == "http://localhost:3000"


# --------------------------------------------------------------------------
# Pagination
# --------------------------------------------------------------------------


def test_paginate_follows_the_cursor_until_exhausted():
    client = FakeClient(
        [
            {"data": [{"id": "a"}], "meta": {"nextCursor": "cur-1"}},
            {"data": [{"id": "b"}], "meta": {"nextCursor": "cur-2"}},
            {"data": [{"id": "c"}], "meta": {"nextCursor": None}},
        ]
    )

    rows = paginate(client, "/api/public/v2/observations", {}, page_size=500)

    assert [r["id"] for r in rows] == ["a", "b", "c"]
    assert [call[1].get("cursor") for call in client.calls] == [None, "cur-1", "cur-2"]


def test_paginate_accepts_the_items_envelope_too():
    client = FakeClient([{"items": [{"id": "a"}], "nextCursor": None}])

    assert paginate(client, "/x", {}, page_size=10) == [{"id": "a"}]


def test_paginate_stops_at_the_page_cap():
    """A busy project must not spin forever on a server that always returns a cursor."""
    client = FakeClient(
        [{"data": [{"id": str(i)}], "meta": {"nextCursor": "next"}} for i in range(500)]
    )

    rows = paginate(client, "/x", {}, page_size=1)

    assert len(rows) == MAX_PAGES
    assert len(client.calls) == MAX_PAGES


def test_each_endpoint_clamps_limit_to_its_own_ceiling(tmp_path, monkeypatch):
    """v3 scores rejects limit>100 with a 400; v2 observations allows 1000.

    Regression: a single global clamp of 1000 made every score fetch fail.
    """
    from memanto.cli.analyze.langfuse_export import (
        MAX_LIMIT_OBSERVATIONS,
        MAX_LIMIT_SCORES,
    )

    client = FakeClient([{"data": [], "meta": {}}, {"data": [], "meta": {}}])
    monkeypatch.setattr(langfuse_export, "_client", lambda *a, **k: client)

    run_langfuse_export("pk:sk", tmp_path, discover=True, page_size=1000)

    limits = {path: params["limit"] for path, params in client.calls}
    assert limits["/api/public/v2/observations"] == MAX_LIMIT_OBSERVATIONS
    assert limits["/api/public/v3/scores"] == MAX_LIMIT_SCORES
    assert MAX_LIMIT_SCORES <= 100


def test_default_page_size_is_within_every_endpoint_ceiling(tmp_path, monkeypatch):
    client = FakeClient([{"data": [], "meta": {}}, {"data": [], "meta": {}}])
    monkeypatch.setattr(langfuse_export, "_client", lambda *a, **k: client)

    run_langfuse_export("pk:sk", tmp_path, discover=True)

    for path, params in client.calls:
        ceiling = 100 if "scores" in path else 1000
        assert params["limit"] <= ceiling, f"{path} would 400"


def test_paginate_sends_the_page_size_as_limit():
    client = FakeClient([{"data": [], "meta": {}}])
    paginate(client, "/x", {"level": "ERROR"}, page_size=250)

    _, params = client.calls[0]
    assert params["limit"] == 250
    assert params["level"] == "ERROR"


# --------------------------------------------------------------------------
# Export orchestration
# --------------------------------------------------------------------------


def test_errors_only_uses_the_server_side_level_filter(tmp_path, monkeypatch):
    client = FakeClient([{"data": [{"id": "a", "level": "ERROR"}], "meta": {}}])
    monkeypatch.setattr(langfuse_export, "_client", lambda *a, **k: client)

    _, export = run_langfuse_export("pk:sk", tmp_path, capture={"errors"})

    assert client.calls[0][0] == "/api/public/v2/observations"
    assert client.calls[0][1]["level"] == "ERROR"
    assert export["summary"]["observation_count"] == 1


def test_latency_modes_sweep_unfiltered(tmp_path, monkeypatch):
    """Latency and cost are not server-side filterable, so the level filter is dropped."""
    client = FakeClient([{"data": [{"id": "a"}], "meta": {}}])
    monkeypatch.setattr(langfuse_export, "_client", lambda *a, **k: client)

    run_langfuse_export("pk:sk", tmp_path, capture={"errors", "slow"})

    assert "level" not in client.calls[0][1]


def _score_config(rule="correctness<0.7"):
    from memanto.cli.migrate.langfuse_config import parse_score_rule
    from memanto.cli.migrate.langfuse_rules import CaptureConfig

    return CaptureConfig(
        modes=frozenset({"low_score"}), score_fail_rules=(parse_score_rule(rule),)
    )


def test_score_modes_hydrate_only_the_traces_a_rule_matches(tmp_path, monkeypatch):
    client = FakeClient(
        [
            # scores page: one failing, one passing (live `subject` linkage)
            {
                "data": [
                    {
                        "id": "s1",
                        "subject": {"kind": "trace", "id": "trace-7"},
                        "name": "correctness",
                        "value": 0.1,
                    },
                    {
                        "id": "s2",
                        "subject": {"kind": "trace", "id": "trace-8"},
                        "name": "correctness",
                        "value": 0.95,
                    },
                ],
                "meta": {"nextCursor": None},
            },
            {"data": [{"id": "o1", "traceId": "trace-7"}], "meta": {}},
        ]
    )
    monkeypatch.setattr(langfuse_export, "_client", lambda *a, **k: client)

    _, export = run_langfuse_export(
        "pk:sk", tmp_path, capture={"low_score"}, config=_score_config()
    )

    assert client.calls[0][0] == "/api/public/v3/scores"
    # Scores are fetched unfiltered: no server-side value filter is correct in
    # general, because ranges and direction are user-defined.
    assert "valueMax" not in client.calls[0][1]
    # `subject` must be requested or the linkage comes back null.
    assert "subject" in client.calls[0][1]["fields"]
    hydrated = [c[1].get("traceId") for c in client.calls if c[1].get("traceId")]
    assert hydrated == ["trace-7"], "only the rule-matching trace should be fetched"
    assert len(export["scores"]) == 2


def test_score_modes_fetch_nothing_without_rules(tmp_path, monkeypatch):
    """Without a rule there is no way to know which scores mean failure."""
    client = FakeClient(
        [
            {
                "data": [{"id": "s1", "traceId": "trace-7", "value": 0.1}],
                "meta": {"nextCursor": None},
            }
        ]
    )
    monkeypatch.setattr(langfuse_export, "_client", lambda *a, **k: client)

    run_langfuse_export("pk:sk", tmp_path, capture={"low_score"})

    assert not [c for c in client.calls if c[1].get("traceId")]


def test_discover_pulls_unfiltered_observations_and_all_scores(tmp_path, monkeypatch):
    client = FakeClient(
        [
            {"data": [{"id": "o1", "level": "DEFAULT"}], "meta": {}},
            {"data": [{"id": "s1", "name": "correctness", "value": 0.4}], "meta": {}},
        ]
    )
    monkeypatch.setattr(langfuse_export, "_client", lambda *a, **k: client)

    _, export = run_langfuse_export("pk:sk", tmp_path, discover=True)

    assert "level" not in client.calls[0][1]
    assert client.calls[1][0] == "/api/public/v3/scores"
    assert export["summary"]["discover"] is True
    assert len(export["observations"]) == 1 and len(export["scores"]) == 1


def test_export_writes_a_replayable_file(tmp_path, monkeypatch):
    client = FakeClient([{"data": [{"id": "a", "level": "ERROR"}], "meta": {}}])
    monkeypatch.setattr(langfuse_export, "_client", lambda *a, **k: client)
    since = datetime(2026, 7, 1, tzinfo=timezone.utc)

    path, export = run_langfuse_export(
        "pk:sk",
        tmp_path,
        host="https://us.cloud.langfuse.com",
        since=since,
        capture={"errors"},
    )

    assert path.name == "langfuse_export.json"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["api_base"] == "https://us.cloud.langfuse.com"
    assert on_disk["summary"]["capture_modes"] == ["errors"]
    assert export["summary"]["from_time"] == since.isoformat()


def test_duplicate_observations_are_collapsed(tmp_path, monkeypatch):
    """Score hydration can re-fetch rows the error sweep already returned."""
    client = FakeClient(
        [
            {"data": [{"id": "dup"}, {"id": "dup"}, {"id": "other"}], "meta": {}},
        ]
    )
    monkeypatch.setattr(langfuse_export, "_client", lambda *a, **k: client)

    _, export = run_langfuse_export("pk:sk", tmp_path, capture={"errors"})

    assert [o["id"] for o in export["observations"]] == ["dup", "other"]


def test_unknown_capture_mode_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unknown capture mode"):
        run_langfuse_export("pk:sk", tmp_path, capture={"whoops"})
