"""Tests for expiry policies: duration parsing, evaluation, sweeps, purge."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from memanto.app.services.memory_policy_service import (
    MemoryPolicy,
    MemoryPolicyService,
    evaluate,
    format_duration,
    memory_age_basis,
    parse_duration,
)
from memanto.app.services.policy_presets import PRESETS, list_presets, load_preset
from memanto.app.utils.errors import SessionError

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


CLIENT_CLASSES = (
    pytest.param(
        "memanto.cli.client.direct_client",
        "DirectClient",
        id="direct-client",
    ),
    pytest.param(
        "memanto.cli.client.sdk_client",
        "SdkClient",
        id="sdk-client",
    ),
)


def memory(
    memory_id="mem-1",
    memory_type="context",
    age_days=0,
    status="active",
    **extra,
):
    """A formatted memory dict as the read service would produce it."""
    stamp = (NOW - timedelta(days=age_days)).isoformat()
    return {
        "id": memory_id,
        "title": f"Memory {memory_id}",
        "type": memory_type,
        "status": status,
        "created_at": stamp,
        "updated_at": stamp,
        "confidence": 0.8,
        "provenance": "explicit_statement",
        "source": "user",
        "tags": [],
        **extra,
    }


@pytest.mark.parametrize(("module_name", "class_name"), CLIENT_CLASSES)
@pytest.mark.parametrize(
    ("method_name", "args"),
    [
        ("get_policy", ("other-agent",)),
        ("set_policy", ("other-agent", {})),
        ("apply_policy_preset", ("other-agent", "balanced")),
    ],
)
def test_policy_access_requires_validated_agent_session(
    module_name: str,
    class_name: str,
    method_name: str,
    args: tuple[object, ...],
) -> None:
    """Policy reads and writes must not bypass the agent session boundary."""
    module = __import__(module_name, fromlist=[class_name])
    client = getattr(module, class_name)(api_key="test-key")
    client._get_validated_session_for_agent = MagicMock(  # type: ignore[method-assign]
        side_effect=SessionError("session scope mismatch")
    )
    client._get_policy_service = MagicMock()  # type: ignore[method-assign]

    with pytest.raises(SessionError, match="session scope mismatch"):
        getattr(client, method_name)(*args)

    client._get_validated_session_for_agent.assert_called_once_with("other-agent")
    client._get_policy_service.assert_not_called()


class TestParseDuration:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("30m", 1800),
            ("12h", 43200),
            ("7d", 604800),
            ("2w", 1209600),
            ("1y", 31536000),
            ("never", None),
            (None, None),
            ("  3D  ", 259200),
            ("1mo", 2592000),
            ("3mo", 7776000),
            ("12mo", 31104000),
            ("  2MO ", 5184000),
        ],
    )
    def test_parses_supported_forms(self, value, expected):
        assert parse_duration(value) == expected

    def test_months_are_not_confused_with_minutes(self):
        """`3m` is three minutes; `3mo` is three months. The regex must not
        read the leading `m` of `mo` as the minute unit."""
        assert parse_duration("3m") == 180
        assert parse_duration("3mo") == 7776000

    @pytest.mark.parametrize(
        "value", ["", "7", "d", "7x", "-3d", "0d", "seven days", "3.5d", True]
    )
    def test_rejects_malformed_durations(self, value):
        if value == "":
            assert parse_duration(value) is None
            return
        with pytest.raises(ValueError):
            parse_duration(value)

    @pytest.mark.parametrize("value", ["30m", "12h", "3d", "2w", "1y", "never"])
    def test_round_trips_through_format(self, value):
        assert format_duration(parse_duration(value)) == value

    def test_format_prefers_the_largest_exact_unit(self):
        """7d and 1w are the same window; the compact form wins."""
        assert format_duration(parse_duration("7d")) == "1w"


class TestAgeBasis:
    def test_prefers_updated_at_over_created_at(self):
        """Editing a memory is evidence it is still live, so it resets the clock."""
        basis = memory_age_basis(
            {
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-05-01T00:00:00Z",
            }
        )
        assert basis == datetime(2026, 5, 1, tzinfo=timezone.utc)

    def test_falls_back_to_created_at(self):
        basis = memory_age_basis({"created_at": "2026-01-01T00:00:00Z"})
        assert basis == datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_returns_none_when_no_usable_timestamp(self):
        assert memory_age_basis({"created_at": "not-a-date"}) is None
        assert memory_age_basis({}) is None


class TestEvaluateRetentionTable:
    def test_expires_once_past_the_type_window(self):
        policy = MemoryPolicy(retention={"context": "7d"})
        should_expire, reason = evaluate(memory(age_days=8), policy, NOW)

        assert should_expire is True
        assert reason == "retention.context"

    def test_keeps_a_memory_inside_the_window(self):
        policy = MemoryPolicy(retention={"context": "7d"})
        should_expire, reason = evaluate(memory(age_days=3), policy, NOW)

        assert should_expire is False
        assert reason is None

    def test_expires_exactly_at_the_boundary(self):
        policy = MemoryPolicy(retention={"context": "7d"})
        assert evaluate(memory(age_days=7), policy, NOW)[0] is True

    def test_never_keeps_a_type_forever(self):
        policy = MemoryPolicy(retention={"fact": "never"})
        assert evaluate(memory(memory_type="fact", age_days=9999), policy, NOW)[0] is (
            False
        )

    def test_type_absent_from_the_table_never_expires(self):
        policy = MemoryPolicy(retention={"context": "1d"})
        assert evaluate(memory(memory_type="fact", age_days=9999), policy, NOW)[0] is (
            False
        )

    def test_memory_without_a_timestamp_is_never_expired(self):
        policy = MemoryPolicy(retention={"context": "1d"})
        stale = memory()
        stale["created_at"] = None
        stale["updated_at"] = None

        assert evaluate(stale, policy, NOW)[0] is False

    def test_already_expired_memory_is_left_alone(self):
        """A sweep never re-stamps an expired memory."""
        policy = MemoryPolicy(retention={"context": "1d"})
        assert evaluate(memory(age_days=99, status="expired"), policy, NOW) == (
            False,
            None,
        )


class TestEvaluateRules:
    def test_rule_wins_over_the_retention_table(self):
        policy = MemoryPolicy(
            retention={"context": "30d"},
            rules=[
                {
                    "name": "scratch-notes",
                    "match": {"tags": ["scratch"]},
                    "expire_after": "1d",
                }
            ],
        )
        should_expire, reason = evaluate(
            memory(age_days=3, tags=["scratch"]), policy, NOW
        )

        assert should_expire is True
        assert reason == "scratch-notes"

    def test_first_matching_rule_short_circuits(self):
        policy = MemoryPolicy(
            rules=[
                {"name": "first", "match": {"tags": ["a"]}, "expire_after": "never"},
                {"name": "second", "match": {"tags": ["a"]}, "expire_after": "1d"},
            ]
        )
        assert evaluate(memory(age_days=99, tags=["a"]), policy, NOW) == (False, None)

    def test_never_rule_pins_a_memory_active(self):
        """An explicit pin beats an otherwise-expiring retention table."""
        policy = MemoryPolicy(
            retention={"context": "1d"},
            rules=[
                {
                    "name": "pinned",
                    "match": {"tags": ["pinned"]},
                    "expire_after": "never",
                }
            ],
        )
        assert evaluate(memory(age_days=99, tags=["pinned"]), policy, NOW)[0] is False

    def test_non_matching_rule_falls_through_to_the_table(self):
        policy = MemoryPolicy(
            retention={"context": "7d"},
            rules=[
                {
                    "name": "pinned",
                    "match": {"tags": ["pinned"]},
                    "expire_after": "never",
                }
            ],
        )
        should_expire, reason = evaluate(memory(age_days=8), policy, NOW)

        assert should_expire is True
        assert reason == "retention.context"

    def test_empty_match_block_matches_everything(self):
        policy = MemoryPolicy(rules=[{"name": "catch-all", "expire_after": "1d"}])
        assert evaluate(memory(age_days=2), policy, NOW) == (True, "catch-all")


class TestPolicyMatchConditions:
    @pytest.mark.parametrize(
        "match,mem,expected",
        [
            ({"type": ["context"]}, {"type": "context"}, True),
            ({"type": ["context"]}, {"type": "fact"}, False),
            ({"source": ["cursor"]}, {"source": "cursor"}, True),
            ({"source": ["cursor"]}, {"source": "user"}, False),
            ({"provenance": ["imported"]}, {"provenance": "imported"}, True),
            ({"provenance": ["imported"]}, {"provenance": "inferred"}, False),
            ({"confidence_below": 0.5}, {"confidence": 0.3}, True),
            ({"confidence_below": 0.5}, {"confidence": 0.7}, False),
            ({"confidence_below": 0.5}, {"confidence": 0.5}, False),
            ({"tags": ["a"]}, {"tags": ["a", "b"]}, True),
            ({"tags": ["a"]}, {"tags": ["b"]}, False),
        ],
    )
    def test_single_condition(self, match, mem, expected):
        from memanto.app.services.memory_policy_service import PolicyMatch

        assert PolicyMatch(**match).matches(mem) is expected

    def test_conditions_are_anded(self):
        from memanto.app.services.memory_policy_service import PolicyMatch

        condition = PolicyMatch(provenance=["imported"], confidence_below=0.5)

        assert condition.matches({"provenance": "imported", "confidence": 0.3}) is True
        assert condition.matches({"provenance": "imported", "confidence": 0.9}) is False
        assert condition.matches({"provenance": "inferred", "confidence": 0.3}) is False

    def test_unknown_confidence_does_not_count_as_low(self):
        from memanto.app.services.memory_policy_service import PolicyMatch

        assert PolicyMatch(confidence_below=0.5).matches({"confidence": None}) is False


class TestPolicyValidation:
    def test_rejects_unknown_memory_type_in_retention(self):
        with pytest.raises(ValueError, match="unknown memory type"):
            MemoryPolicy(retention={"not-a-type": "7d"})

    def test_rejects_malformed_duration_in_retention(self):
        with pytest.raises(ValueError):
            MemoryPolicy(retention={"context": "soon"})

    def test_rejects_duplicate_rule_names(self):
        with pytest.raises(ValueError, match="duplicate rule name"):
            MemoryPolicy(
                rules=[
                    {"name": "dup", "expire_after": "1d"},
                    {"name": "dup", "expire_after": "2d"},
                ]
            )

    def test_rejects_rule_name_that_breaks_filter_syntax(self):
        """The rule name is stamped as expired_by and must stay a filter token."""
        with pytest.raises(ValueError):
            MemoryPolicy(rules=[{"name": "bad name", "expire_after": "1d"}])

    def test_empty_policy_is_reported_as_empty(self):
        assert MemoryPolicy().is_empty() is True
        assert MemoryPolicy(retention={"context": "never"}).is_empty() is True
        assert MemoryPolicy(retention={"context": "1d"}).is_empty() is False


class TestPresets:
    @pytest.mark.parametrize("name", sorted(PRESETS))
    def test_every_preset_builds(self, name):
        policy = load_preset(name)
        assert isinstance(policy, MemoryPolicy)
        assert not policy.is_empty()

    def test_unknown_preset_is_rejected(self):
        with pytest.raises(ValueError, match="Unknown preset"):
            load_preset("nope")

    def test_list_presets_describes_each_one(self):
        listed = list_presets()
        assert {item["name"] for item in listed} == set(PRESETS)
        assert all(item["description"] for item in listed)

    @pytest.mark.parametrize("name", sorted(PRESETS))
    def test_durable_types_never_expire_on_a_timer(self, name):
        """Preferences and instructions are user truths, not transient state."""
        policy = load_preset(name)
        for durable in ("preference", "instruction", "relationship"):
            assert parse_duration(policy.retention.get(durable)) is None

    @pytest.mark.parametrize("name", sorted(PRESETS))
    def test_pinned_memories_are_exempt(self, name):
        policy = load_preset(name)
        pinned = memory(memory_type="context", age_days=9999, tags=["pinned"])
        assert evaluate(pinned, policy, NOW)[0] is False


class _FakeDocuments:
    """Minimal Moorcheh documents API backed by an in-memory dict."""

    def __init__(self, items):
        self.items = {item["id"]: item for item in items}
        self.uploaded = []
        self.deleted = []

    def fetch_text_data(self, **kwargs):
        return {"items": list(self.items.values()), "pagination": {"has_more": False}}

    def get(self, namespace_name, ids):
        return {"items": [self.items[i] for i in ids if i in self.items]}

    def upload(self, namespace_name, documents):
        self.uploaded.extend(documents)
        for doc in documents:
            self.items[doc["id"]] = doc
        return {"status": "success"}

    def delete(self, namespace_name, ids):
        for i in ids:
            self.items.pop(i, None)
            self.deleted.append(i)
        return {"actual_deletions": len(ids)}


class _FakeClient:
    def __init__(self, items):
        self.documents = _FakeDocuments(items)


def stored(memory_id, memory_type="context", age_days=0, status="active", **extra):
    """A raw stored document, in the flat shape Moorcheh returns."""
    stamp = (NOW - timedelta(days=age_days)).isoformat()
    return {
        "id": memory_id,
        "text": f"[{memory_type.upper()}] Title {memory_id}\n\nBody",
        "memory_type": memory_type,
        "agent_id": "alpha",
        "actor_id": "user",
        "source": "user",
        "confidence": 0.8,
        "status": status,
        "provenance": "explicit_statement",
        "created_at": stamp,
        "updated_at": stamp,
        **extra,
    }


class TestApplyPolicies:
    def _service(self, items, tmp_path, policy=None):
        service = MemoryPolicyService(_FakeClient(items), policies_dir=tmp_path)
        if policy is not None:
            service.save_policy("alpha", policy)
        return service

    def test_dry_run_reports_without_writing(self, tmp_path):
        client_items = [stored("old", age_days=30), stored("new", age_days=1)]
        service = self._service(
            client_items, tmp_path, MemoryPolicy(retention={"context": "7d"})
        )

        report = service.apply_policies("alpha", dry_run=True, now=NOW)

        assert report["dry_run"] is True
        assert report["matched"] == 1
        assert report["expired"] == 0
        assert report["memories"][0]["id"] == "old"
        assert service.client.documents.uploaded == []

    def test_apply_stamps_matching_memories(self, tmp_path):
        client_items = [stored("old", age_days=30), stored("new", age_days=1)]
        service = self._service(
            client_items, tmp_path, MemoryPolicy(retention={"context": "7d"})
        )

        report = service.apply_policies("alpha", dry_run=False, now=NOW)

        assert report["matched"] == 1
        assert report["expired"] == 1
        uploaded = {doc["id"]: doc for doc in service.client.documents.uploaded}
        assert uploaded["old"]["status"] == "expired"
        assert uploaded["old"]["expired_by"] == "retention.context"
        assert uploaded["old"]["expired_at"] == NOW.isoformat()
        assert "new" not in uploaded

    def test_per_rule_counts_are_reported(self, tmp_path):
        client_items = [
            stored("a", age_days=30),
            stored("b", age_days=30),
            stored("c", age_days=30, memory_type="event"),
        ]
        service = self._service(
            client_items,
            tmp_path,
            MemoryPolicy(retention={"context": "7d", "event": "7d"}),
        )

        report = service.apply_policies("alpha", dry_run=True, now=NOW)

        assert report["per_rule"] == {"retention.context": 2, "retention.event": 1}

    def test_empty_policy_expires_nothing(self, tmp_path):
        service = self._service([stored("old", age_days=9999)], tmp_path)

        report = service.apply_policies("alpha", dry_run=True, now=NOW)

        assert report["policy_is_empty"] is True
        assert report["matched"] == 0

    def test_sweep_shares_one_timestamp(self, tmp_path):
        client_items = [stored("a", age_days=30), stored("b", age_days=40)]
        service = self._service(
            client_items, tmp_path, MemoryPolicy(retention={"context": "7d"})
        )

        service.apply_policies("alpha", dry_run=False, now=NOW)

        stamps = {doc["expired_at"] for doc in service.client.documents.uploaded}
        assert stamps == {NOW.isoformat()}


class TestPurgeExpired:
    def _service(self, items, tmp_path, policy):
        service = MemoryPolicyService(_FakeClient(items), policies_dir=tmp_path)
        service.save_policy("alpha", policy)
        return service

    def test_disabled_by_default(self, tmp_path):
        old = stored(
            "old",
            status="expired",
            expired_at=(NOW - timedelta(days=9999)).isoformat(),
        )
        service = self._service([old], tmp_path, MemoryPolicy())

        report = service.purge_expired("alpha", now=NOW)

        assert report["enabled"] is False
        assert report["purged"] == 0
        assert service.client.documents.deleted == []

    def test_purges_only_past_the_window(self, tmp_path):
        items = [
            stored(
                "ancient",
                status="expired",
                expired_at=(NOW - timedelta(days=400)).isoformat(),
            ),
            stored(
                "recent",
                status="expired",
                expired_at=(NOW - timedelta(days=10)).isoformat(),
            ),
        ]
        service = self._service(
            items, tmp_path, MemoryPolicy(purge_expired_after="365d")
        )

        report = service.purge_expired("alpha", dry_run=False, now=NOW)

        assert report["matched"] == 1
        assert report["purged"] == 1
        assert service.client.documents.deleted == ["ancient"]

    def test_dry_run_deletes_nothing(self, tmp_path):
        items = [
            stored(
                "ancient",
                status="expired",
                expired_at=(NOW - timedelta(days=400)).isoformat(),
            )
        ]
        service = self._service(
            items, tmp_path, MemoryPolicy(purge_expired_after="365d")
        )

        report = service.purge_expired("alpha", dry_run=True, now=NOW)

        assert report["matched"] == 1
        assert report["purged"] == 0
        assert service.client.documents.deleted == []

    def test_expired_memory_without_a_stamp_is_never_purged(self, tmp_path):
        items = [stored("no-stamp", status="expired")]
        service = self._service(items, tmp_path, MemoryPolicy(purge_expired_after="1d"))

        report = service.purge_expired("alpha", dry_run=False, now=NOW)

        assert report["matched"] == 0
        assert service.client.documents.deleted == []


class TestPolicyPersistence:
    def test_missing_policy_loads_as_empty(self, tmp_path):
        service = MemoryPolicyService(_FakeClient([]), policies_dir=tmp_path)
        assert service.load_policy("alpha").is_empty() is True

    def test_round_trips_through_disk(self, tmp_path):
        service = MemoryPolicyService(_FakeClient([]), policies_dir=tmp_path)
        policy = load_preset("balanced")

        service.save_policy("alpha", policy)
        loaded = service.load_policy("alpha")

        assert loaded.retention == policy.retention
        assert [r.name for r in loaded.rules] == [r.name for r in policy.rules]
        assert loaded.purge_expired_after == policy.purge_expired_after
        # Match conditions must survive the exclude_none round trip.
        by_name = {r.name: r for r in loaded.rules}
        assert by_name["scratch-notes"].match.tags == ["scratch", "temp"]
        assert by_name["low-confidence-guesses"].match.confidence_below == 0.5
        assert by_name["low-confidence-guesses"].match.provenance == ["inferred"]

    def test_saved_file_omits_unset_match_conditions(self, tmp_path):
        """The policy file is hand-edited, so unset conditions must not appear."""
        service = MemoryPolicyService(_FakeClient([]), policies_dir=tmp_path)
        service.save_policy("alpha", load_preset("balanced"))

        text = (tmp_path / "alpha.yaml").read_text(encoding="utf-8")

        assert "null" not in text
        assert "tags:" in text and "expire_after:" in text

    def test_rejects_agent_id_path_traversal(self, tmp_path):
        service = MemoryPolicyService(_FakeClient([]), policies_dir=tmp_path)
        with pytest.raises(ValueError):
            service.load_policy("../escape")

    def test_invalid_policy_file_raises(self, tmp_path):
        service = MemoryPolicyService(_FakeClient([]), policies_dir=tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "alpha.yaml").write_text(
            "retention:\n  not-a-type: 7d\n", encoding="utf-8"
        )

        from memanto.app.utils.errors import MemoryError

        with pytest.raises(MemoryError, match="Invalid policy"):
            service.load_policy("alpha")


class TestPresetPreview:
    """`get_policy_preset` backs the confirm-before-adopting flow, so it must
    return the full policy without writing anything."""

    def test_returns_full_policy_without_saving(self, tmp_path):
        from memanto.app.services.policy_presets import PRESETS, load_preset

        policy = load_preset("balanced")
        detail = {
            "name": "balanced",
            "description": PRESETS["balanced"]["description"],
            "policy": policy.model_dump(mode="json", exclude_none=True),
        }

        assert detail["description"]
        assert detail["policy"]["retention"]["context"] == "7d"
        assert [r["name"] for r in detail["policy"]["rules"]][0] == "pinned"
        # exclude_none keeps unset match conditions out of the preview too.
        assert "null" not in str(detail["policy"])
        # Nothing was persisted.
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.parametrize("name", sorted(PRESETS))
    def test_every_preset_previews(self, name):
        policy = load_preset(name)
        dumped = policy.model_dump(mode="json", exclude_none=True)
        assert dumped["version"] == 1
        assert "purge_expired_after" in dumped
