"""
Offline tests for the ChatGPT/Claude to OKF migration adapter.

The adapter lives in ``examples/migrations/chatgpt-claude-okf/``. These tests
sit here rather than beside it so the repository test suite actually runs them.

They cover the only parts of the pipeline the example owns: parsing two vendor
export formats, the OKF v0.2 upgrade layer, the privacy filter, and the one
destructive operation. Everything else is a shipped Memanto service with its
own tests upstream.

No API key, no network, no credits:

    pytest tests/test_chatgpt_claude_okf.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ADAPTER = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "migrations"
    / "chatgpt-claude-okf"
)
sys.path.insert(0, str(_ADAPTER))

import okf_v02  # noqa: E402
from liberate import (  # noqa: E402
    _clear_stale_bundle,
    _parse_dt,
    _require_paths,
    classify_saved,
    exclude_matching,
    inspect_export,
    read_chatgpt,
    read_claude,
    verify_links,
    write_bundle,
)


def _node(node_id, parent, role, text, content_type="text", recipient=None):
    """Build one node of a ChatGPT conversation graph."""
    message = {
        "author": {"role": role},
        "content": {"content_type": content_type, "parts": [text]},
    }
    if recipient:
        message["recipient"] = recipient
    return {"id": node_id, "parent": parent, "message": message}


def _chatgpt_file(tmp_path: Path, mapping: dict, current: str) -> Path:
    """Write a single-conversation ChatGPT export to a temporary file."""
    path = tmp_path / "conversations.json"
    path.write_text(
        json.dumps(
            [
                {
                    "conversation_id": "c1",
                    "title": "Test thread",
                    "create_time": 1750000000.0,
                    "current_node": current,
                    "mapping": mapping,
                }
            ]
        )
    )
    return path


class TestReadChatgpt:
    def test_returns_messages_in_chronological_order(self, tmp_path):
        """ChatGPT stores a parent chain, so the walk runs newest to oldest and the result has to be reversed."""
        mapping = {
            "a": _node("a", None, "user", "first"),
            "b": _node("b", "a", "assistant", "second"),
            "c": _node("c", "b", "user", "third"),
        }
        conv = next(read_chatgpt(_chatgpt_file(tmp_path, mapping, "c")))
        assert [m["content"] for m in conv.messages] == ["first", "second", "third"]

    def test_keeps_assistant_turns_for_context(self, tmp_path):
        """The extractor needs both sides. A user-only transcript loses what was actually decided."""
        mapping = {
            "a": _node("a", None, "user", "q"),
            "b": _node("b", "a", "assistant", "answer text"),
        }
        conv = next(read_chatgpt(_chatgpt_file(tmp_path, mapping, "b")))
        assert [m["role"] for m in conv.messages] == ["user", "assistant"]

    def test_skips_custom_instruction_nodes(self, tmp_path):
        """Custom instructions repeat verbatim in every conversation, so importing them would create one duplicate per thread."""
        mapping = {
            "a": _node("a", None, "user", "sys blob", "user_editable_context"),
            "b": _node("b", "a", "user", "real question"),
        }
        conv = next(read_chatgpt(_chatgpt_file(tmp_path, mapping, "b")))
        assert [m["content"] for m in conv.messages] == ["real question"]

    def test_survives_a_parent_cycle(self, tmp_path):
        """A malformed export can point two nodes at each other; the walk must
        terminate rather than hang."""
        mapping = {
            "a": _node("a", "b", "user", "one"),
            "b": _node("b", "a", "user", "two"),
        }
        conv = next(read_chatgpt(_chatgpt_file(tmp_path, mapping, "a")))
        assert len(conv.messages) == 2

    def test_parses_epoch_timestamp(self, tmp_path):
        """ChatGPT writes create_time as epoch seconds, where Claude writes ISO 8601."""
        mapping = {"a": _node("a", None, "user", "hi")}
        conv = next(read_chatgpt(_chatgpt_file(tmp_path, mapping, "a")))
        assert conv.created_at is not None
        assert conv.created_at.tzinfo is not None

    def test_ignores_conversations_with_no_usable_text(self, tmp_path):
        """An image-only or empty thread has nothing to distill and should not reach the extractor."""
        mapping = {"a": _node("a", None, "user", "   ")}
        assert list(read_chatgpt(_chatgpt_file(tmp_path, mapping, "a"))) == []


class TestReadClaude:
    def _write(self, tmp_path: Path, messages: list) -> Path:
        """Write a Claude-shaped export to a temporary file."""
        path = tmp_path / "conversations.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "uuid": "cc1",
                        "name": "Claude thread",
                        "created_at": "2026-02-11T09:15:00Z",
                        "chat_messages": messages,
                    }
                ]
            )
        )
        return path

    def test_reads_legacy_text_field(self, tmp_path):
        """Older Claude exports carry the message text directly on `text`."""
        path = self._write(tmp_path, [{"sender": "human", "text": "hello"}])
        conv = next(read_claude(path))
        assert conv.messages == [{"role": "user", "content": "hello"}]

    def test_falls_back_to_content_blocks(self, tmp_path):
        """Newer exports leave ``text`` empty and split the body into blocks."""
        path = self._write(
            tmp_path,
            [
                {
                    "sender": "human",
                    "text": "",
                    "content": [{"type": "text", "text": "from blocks"}],
                }
            ],
        )
        conv = next(read_claude(path))
        assert conv.messages[0]["content"] == "from blocks"

    def test_maps_human_sender_to_user_role(self, tmp_path):
        """Claude labels the sender `human`; the extraction service expects `user`."""
        path = self._write(
            tmp_path,
            [
                {"sender": "human", "text": "q"},
                {"sender": "assistant", "text": "a"},
            ],
        )
        conv = next(read_claude(path))
        assert [m["role"] for m in conv.messages] == ["user", "assistant"]

    def test_parses_iso_timestamp(self, tmp_path):
        """Claude writes created_at as an ISO 8601 string, not an epoch number."""
        path = self._write(tmp_path, [{"sender": "human", "text": "hi"}])
        conv = next(read_claude(path))
        assert conv.created_at.year == 2026


class TestClassifySaved:
    def test_assigns_a_valid_type_to_every_line(self, tmp_path):
        """An unrecognised type would be dropped at import, so every line must land on a real Memanto type."""
        path = tmp_path / "saved.txt"
        path.write_text(
            "# a comment that should be ignored\n"
            "\n"
            "Prefers Python and FastAPI over heavy ORMs.\n"
            "- Decided to standardise on Prometheus for metrics.\n"
        )
        records = classify_saved(path, "chatgpt")
        assert len(records) == 2
        assert all(r["type"] for r in records)
        assert all(r["provenance"] == "imported" for r in records)
        assert all(r["source"] == "chatgpt" for r in records)

    def test_strips_list_bullets(self, tmp_path):
        """People paste their saved memory list with the bullets still attached."""
        path = tmp_path / "saved.txt"
        path.write_text("- Uses Kubernetes on bare metal.\n")
        assert not classify_saved(path, "chatgpt")[0]["content"].startswith("-")


class TestInspectExport:
    def test_counts_bio_writes(self, tmp_path):
        """A `bio` recipient is the moment ChatGPT commits a memory, which is exactly what --inspect exists to count."""
        mapping = {
            "a": _node("a", None, "user", "hi"),
            "b": _node("b", "a", "assistant", "saving", recipient="bio"),
        }
        counts = inspect_export(_chatgpt_file(tmp_path, mapping, "b"), "chatgpt")
        assert counts["bio_writes"] == 1
        assert counts["conversations"] == 1

    def test_reports_claude_counts_without_chatgpt_only_fields(self, tmp_path):
        """Claude has no bio writes, so those keys must be absent rather than reported as zero."""
        path = tmp_path / "conversations.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "uuid": "c",
                        "name": "n",
                        "created_at": "2026-02-11T09:15:00Z",
                        "chat_messages": [{"sender": "human", "text": "hi"}],
                    }
                ]
            )
        )
        counts = inspect_export(path, "claude")
        assert counts["conversations"] == 1
        assert "bio_writes" not in counts


class TestClearStaleBundle:
    def test_removes_a_previous_bundle(self, tmp_path):
        """Extraction is non-deterministic, so slugs differ between runs and stale documents would otherwise survive into the new bundle."""
        bundle = tmp_path / "okf"
        (bundle / "memories").mkdir(parents=True)
        (bundle / "index.md").write_text("---\ntype: index\n---\n")
        _clear_stale_bundle(bundle)
        assert not bundle.exists()

    def test_refuses_to_delete_an_unrelated_directory(self, tmp_path):
        """Guard against pointing --out at a folder holding real work."""
        target = tmp_path / "not-a-bundle"
        target.mkdir()
        (target / "important.txt").write_text("do not delete me")
        with pytest.raises(SystemExit):
            _clear_stale_bundle(target)
        assert (target / "important.txt").exists()

    def test_is_a_no_op_when_nothing_exists(self, tmp_path):
        """A first run has nothing to clear and must not fail."""
        _clear_stale_bundle(tmp_path / "missing")


class TestRequirePaths:
    def test_accepts_existing_and_absent_optional_paths(self, tmp_path):
        """An omitted optional source is not an error."""
        real = tmp_path / "there.json"
        real.write_text("[]")
        _require_paths((real, "--chatgpt"), (None, "--claude"))

    def test_rejects_a_missing_path(self, tmp_path):
        """A typo must stop the run rather than silently migrating other data."""
        with pytest.raises(SystemExit) as exc:
            _require_paths((tmp_path / "typo.zip", "--chatgpt"))
        assert "--chatgpt" in str(exc.value)

    def test_names_every_missing_path(self, tmp_path):
        """Reporting one missing path at a time forces the user to re-run to discover the next."""
        with pytest.raises(SystemExit) as exc:
            _require_paths(
                (tmp_path / "a.zip", "--chatgpt"),
                (tmp_path / "b.zip", "--claude"),
            )
        message = str(exc.value)
        assert "--chatgpt" in message and "--claude" in message


class TestVerifyLinks:
    def _bundle(self, tmp_path: Path, body: str) -> Path:
        """Build a small bundle on disk from the given documents."""
        bundle = tmp_path / "okf"
        (bundle / "memories").mkdir(parents=True)
        (bundle / "memories" / "real.md").write_text("---\ntype: fact\n---\n\nbody\n")
        (bundle / "index.md").write_text(body)
        return bundle

    def test_clean_bundle_reports_nothing(self, tmp_path):
        """A bundle whose links all resolve reports an empty list, not None."""
        bundle = self._bundle(tmp_path, "# Index\n\n- [real](memories/real.md)\n")
        assert verify_links(bundle) == []

    def test_detects_a_dangling_link(self, tmp_path):
        """A generated index can point at a document the privacy filter removed."""
        bundle = self._bundle(tmp_path, "# Index\n\n- [gone](memories/gone.md)\n")
        broken = verify_links(bundle)
        assert len(broken) == 1
        assert "memories/gone.md" in broken[0]

    def test_ignores_external_links_and_anchors(self, tmp_path):
        """Only relative paths are ours to resolve; URLs and bare anchors are not."""
        bundle = self._bundle(
            tmp_path,
            "[web](https://example.com/x.md)\n[mail](mailto:a@b.c)\n[anchor](#section)\n",
        )
        assert verify_links(bundle) == []

    def test_resolves_bundle_absolute_links(self, tmp_path):
        """Spec 6.1 allows a leading slash meaning bundle-root relative."""
        bundle = self._bundle(tmp_path, "[root-rel](/memories/real.md)\n")
        assert verify_links(bundle) == []


class TestOkfV02:
    """Spec v0.2 upgrade layered over memanto's v0.1 exporter."""

    def _bundle(self, tmp_path: Path, timestamp: str | None) -> tuple[Path, list]:
        """Build a small bundle on disk from the given documents."""
        record = {
            "id": "abc-123",
            "title": "A preference",
            "content": "Prefers Python.",
            "type": "preference",
            "confidence": 0.9,
            "tags": ["chatgpt"],
            "created_at": timestamp,
            "source": "chatgpt",
            "source_ref": "conv-9",
            "source_title": "A conversation",
            "provenance": "imported",
            "status": "active",
        }
        bundle = tmp_path / "okf"
        write_bundle([record], bundle, "test-agent")
        return bundle, [record]

    def _doc(self, bundle: Path) -> dict[str, Any]:
        """Frontmatter of the one concept document, parsed the way the module
        itself parses it, since a body may legally contain `---` rules."""
        path = next(
            p for p in (bundle / "memories").rglob("*.md") if p.name != "index.md"
        )
        # okf_v02 lives under examples/, which mypy does not analyse, so the
        # return is Any here and needs an explicit annotation.
        frontmatter: dict[str, Any] = okf_v02._split(path.read_text(encoding="utf-8"))[
            0
        ]
        return frontmatter

    def test_adds_generated_by_actor(self, tmp_path):
        """Spec 5.2 requires `generated.by`, written in the actor convention of section 7."""
        bundle, records = self._bundle(tmp_path, "2026-02-01T00:00:00+00:00")
        okf_v02.upgrade(bundle, records, "memanto-liberate/1.0")
        assert self._doc(bundle)["generated"]["by"] == "memanto-liberate/1.0"

    def test_generated_at_mirrors_timestamp_for_determinism(self, tmp_path):
        """Reusing the source date keeps v0.1 and v0.2 consumers in agreement and
        stops re-runs churning committed bundles."""
        bundle, records = self._bundle(tmp_path, "2026-02-01T00:00:00+00:00")
        okf_v02.upgrade(bundle, records, "p/1")
        doc = self._doc(bundle)
        assert doc["generated"]["at"] == doc["timestamp"]

    def test_generated_at_omitted_when_source_has_no_date(self, tmp_path):
        """The spec requires only `by`; inventing a date would be worse."""
        bundle, records = self._bundle(tmp_path, None)
        okf_v02.upgrade(bundle, records, "p/1")
        assert "at" not in self._doc(bundle)["generated"]

    def test_sources_points_back_at_the_conversation(self, tmp_path):
        """Spec 5.1 provenance, so a reader can tell which conversation a memory came from."""
        bundle, records = self._bundle(tmp_path, None)
        okf_v02.upgrade(bundle, records, "p/1")
        source = self._doc(bundle)["sources"][0]
        assert source["id"] == "chatgpt:conv-9"
        assert source["title"] == "A conversation"

    def test_root_index_declares_okf_version(self, tmp_path):
        """Spec 12 requires the declaration, and section 8 permits frontmatter only at the bundle root."""
        bundle, records = self._bundle(tmp_path, None)
        okf_v02.upgrade(bundle, records, "p/1")
        front, _ = okf_v02._split((bundle / "index.md").read_text(encoding="utf-8"))
        assert front == {"okf_version": "0.2"}

    def test_non_root_index_carries_no_frontmatter(self, tmp_path):
        """Spec section 8 permits frontmatter in an index only at the bundle root."""
        bundle, records = self._bundle(tmp_path, None)
        okf_v02.upgrade(bundle, records, "p/1")
        for index in bundle.rglob("index.md"):
            if index.parent != bundle:
                assert not index.read_text().startswith("---")

    def test_every_non_reserved_doc_has_a_type(self, tmp_path):
        """Conformance rule 1. Memanto emits metrics/overview.md with no
        frontmatter at all, which fails it until this layer runs."""
        bundle, records = self._bundle(tmp_path, None)
        okf_v02.upgrade(bundle, records, "p/1")
        for doc in bundle.rglob("*.md"):
            if doc.name in okf_v02.RESERVED:
                continue
            frontmatter, _ = okf_v02._split(doc.read_text(encoding="utf-8"))
            assert frontmatter.get("type"), f"{doc} has no type"

    def test_upgraded_bundle_still_imports_through_memanto(self, tmp_path):
        """The whole point: v0.2 output must stay readable by the shipped v0.1 loader."""
        from memanto.cli.migrate.okf_loader import load_okf_bundle

        bundle, records = self._bundle(tmp_path, "2026-02-01T00:00:00+00:00")
        okf_v02.upgrade(bundle, records, "memanto-liberate/1.0")
        loaded = load_okf_bundle(bundle)["memories"]
        assert len(loaded) == 1
        # Unknown v0.2 keys must be preserved, not dropped (spec section 4.1).
        assert "generated" in loaded[0]["extra"]
        assert "sources" in loaded[0]["extra"]


class TestExcludeMatching:
    """Privacy filter. Runs before the bundle is written, because index files
    repeat titles and a post-hoc file delete would leave the text in listings."""

    def _records(self):
        """Two records, one carrying the sensitive text in the title and one in the body."""
        return [
            {
                "title": "Prefers FastAPI",
                "content": "Likes Python.",
                "type": "preference",
            },
            {
                "title": "Uses service account SVC_X",
                "content": "Internal id.",
                "type": "context",
            },
            {
                "title": "Alerting philosophy",
                "content": "Page on SVC_X errors.",
                "type": "learning",
            },
        ]

    def test_drops_matches_in_title(self):
        """A pattern matching the title alone is enough to exclude the memory."""
        kept, dropped = exclude_matching(self._records(), "SVC_X")
        assert "context" in dropped

    def test_never_reports_the_excluded_title(self):
        """The report must not echo text the caller asked to suppress."""
        _, dropped = exclude_matching(self._records(), "SVC_X")
        assert not any("SVC_X" in d for d in dropped)

    def test_drops_matches_in_content_too(self):
        """A private identifier buried in the body is just as exposed."""
        kept, dropped = exclude_matching(self._records(), "SVC_X")
        assert len(dropped) == 2
        assert [r["title"] for r in kept] == ["Prefers FastAPI"]

    def test_is_case_insensitive(self):
        """Identifiers get typed in whatever case the user happens to remember."""
        kept, _ = exclude_matching(self._records(), "svc_x")
        assert len(kept) == 1

    def test_supports_alternation(self):
        """Patterns from --exclude-file are joined with a pipe, so alternation has to work."""
        kept, dropped = exclude_matching(self._records(), "FastAPI|SVC_X")
        assert kept == [] and len(dropped) == 3

    def test_no_match_keeps_everything(self):
        """A pattern that matches nothing must not silently drop records."""
        kept, dropped = exclude_matching(self._records(), "nothing-here")
        assert len(kept) == 3 and dropped == []


class TestHostileInput:
    """Real exports are sometimes truncated, corrupt, or hand-edited. None of
    that should produce a traceback."""

    def test_corrupt_json_exits_with_an_explanation(self, tmp_path):
        """A truncated download is the usual cause, and the message says so rather than showing a raw traceback."""
        bad = tmp_path / "conversations.json"
        bad.write_text("{not json")
        with pytest.raises(SystemExit) as exc:
            list(read_chatgpt(bad))
        assert "not valid JSON" in str(exc.value)

    def test_file_named_zip_that_is_not_a_zip(self, tmp_path):
        """The extension is not proof of the format."""
        fake = tmp_path / "export.zip"
        fake.write_text("plain text")
        with pytest.raises(SystemExit) as exc:
            list(read_chatgpt(fake))
        assert "zip archive" in str(exc.value)

    def test_out_of_range_epoch_is_treated_as_no_date(self):
        """A corrupt timestamp must not abort a whole migration."""
        assert _parse_dt(99999999999999) is None

    def test_invalid_exclusion_regex_reports_itself(self):
        """A bad pattern must name itself rather than surfacing a raw re.error."""
        with pytest.raises(SystemExit) as exc:
            exclude_matching([{"title": "a", "content": "b", "type": "fact"}], "([un")
        assert "Invalid exclusion pattern" in str(exc.value)

    def test_malformed_yaml_in_a_document_is_tolerated(self, tmp_path):
        """OKF section 11: a consumer must not reject a bundle for one bad doc."""
        bundle = tmp_path / "okf"
        (bundle / "memories").mkdir(parents=True)
        (bundle / "memories" / "broken.md").write_text(
            "---\n: : bad yaml :\n---\nbody\n"
        )
        counts = okf_v02.upgrade(bundle, [], "p/1")
        assert counts["documents"] >= 1

    def test_conversation_with_null_mapping_is_skipped(self, tmp_path):
        """A null mapping is skipped rather than dereferenced."""
        path = tmp_path / "conversations.json"
        path.write_text(json.dumps([{"mapping": None, "current_node": None}]))
        assert list(read_chatgpt(path)) == []


class TestShardedExport:
    """Large ChatGPT exports split history across numbered shards.

    Both cases here were found by running --inspect on a real 360-conversation
    export: it reported 4 conversations and 0 messages, because the archive had
    no conversations.json at all and the loader matched the wrong file.
    """

    @staticmethod
    def _conversation(conv_id: str, text: str) -> dict[str, Any]:
        """One minimal ChatGPT conversation carrying a single user message."""
        return {
            "conversation_id": conv_id,
            "title": f"Thread {conv_id}",
            "create_time": 1750000000.0,
            "current_node": "a",
            "mapping": {"a": _node("a", None, "user", text)},
        }

    def _zip(self, tmp_path: Path, members: dict[str, Any]) -> Path:
        """Build a zip archive from a mapping of member name to JSON payload."""
        import zipfile

        path = tmp_path / "export.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for name, payload in members.items():
                archive.writestr(name, json.dumps(payload))
        return path

    def test_reads_every_numbered_shard(self, tmp_path):
        """Reading only the first shard would silently drop most of a large export."""
        archive = self._zip(
            tmp_path,
            {
                "conversations-000.json": [self._conversation("c0", "zero")],
                "conversations-001.json": [self._conversation("c1", "one")],
                "conversations-002.json": [self._conversation("c2", "two")],
            },
        )
        found = list(read_chatgpt(archive))
        assert [c.id for c in found] == ["c0", "c1", "c2"]

    def test_shards_are_read_in_numeric_order(self, tmp_path):
        """Archive member order is not guaranteed, so the reader has to impose one."""
        archive = self._zip(
            tmp_path,
            {
                "conversations-002.json": [self._conversation("c2", "two")],
                "conversations-000.json": [self._conversation("c0", "zero")],
                "conversations-001.json": [self._conversation("c1", "one")],
            },
        )
        assert [c.id for c in read_chatgpt(archive)] == ["c0", "c1", "c2"]

    def test_shard_order_is_numeric_not_lexicographic(self, tmp_path):
        """A string sort puts conversations-1000 before conversations-999.

        Only reachable on a very large export, but --limit slices this order,
        so getting it wrong silently changes which conversations migrate.
        """
        archive = self._zip(
            tmp_path,
            {
                "conversations-1000.json": [self._conversation("c1000", "later")],
                "conversations-999.json": [self._conversation("c999", "earlier")],
            },
        )
        assert [c.id for c in read_chatgpt(archive)] == ["c999", "c1000"]

    def test_unsharded_file_sorts_before_shards(self, tmp_path):
        """OpenAI does not currently ship both, but the ordering still has to be defined rather than incidental."""
        archive = self._zip(
            tmp_path,
            {
                "conversations-000.json": [self._conversation("shard", "s")],
                "conversations.json": [self._conversation("plain", "p")],
            },
        )
        assert [c.id for c in read_chatgpt(archive)] == ["plain", "shard"]

    def test_shared_conversations_is_not_mistaken_for_history(self, tmp_path):
        """The stub file ends with the same text but holds no ``mapping``.

        Matching on a suffix picks it up and silently yields a handful of empty
        conversations instead of the whole export.
        """
        archive = self._zip(
            tmp_path,
            {
                "shared_conversations.json": [
                    {"conversation_id": "shared", "title": "Shared", "id": "s1"}
                ],
                "conversations-000.json": [self._conversation("real", "kept")],
            },
        )
        found = list(read_chatgpt(archive))
        assert [c.id for c in found] == ["real"]

    def test_unsharded_export_still_works(self, tmp_path):
        """Small exports continue to ship a single conversations.json."""
        archive = self._zip(
            tmp_path, {"conversations.json": [self._conversation("solo", "text")]}
        )
        assert [c.id for c in read_chatgpt(archive)] == ["solo"]

    def test_inspect_counts_across_shards(self, tmp_path):
        """The counts have to span every shard, and exclude the shared-conversation stubs."""
        archive = self._zip(
            tmp_path,
            {
                "conversations-000.json": [self._conversation("c0", "zero")],
                "conversations-001.json": [self._conversation("c1", "one")],
                "shared_conversations.json": [{"conversation_id": "s", "title": "S"}],
            },
        )
        counts = inspect_export(archive, "chatgpt")
        assert counts["conversations"] == 2
        assert counts["messages"] == 2

    def test_archive_with_only_the_stub_file_is_reported_missing(self, tmp_path):
        """Finding only stubs means the history is genuinely absent, which is an error rather than an empty result."""
        archive = self._zip(
            tmp_path, {"shared_conversations.json": [{"conversation_id": "s"}]}
        )
        with pytest.raises(SystemExit, match="No conversations.json"):
            list(read_chatgpt(archive))

    def test_folder_export_reads_shards_too(self, tmp_path):
        """Some users unzip the archive before running the adapter."""
        folder = tmp_path / "export"
        folder.mkdir()
        for index, conv_id in enumerate(["c0", "c1"]):
            (folder / f"conversations-00{index}.json").write_text(
                json.dumps([self._conversation(conv_id, "text")])
            )
        assert [c.id for c in read_chatgpt(folder)] == ["c0", "c1"]


class TestReviewFixes:
    """Cases for the defects CodeRabbit found on the review of PR #1893."""

    def test_offset_timestamp_is_converted_to_utc(self):
        """An offset-aware source value must be converted, not just accepted."""
        parsed = _parse_dt("2026-02-11T09:15:00+05:30")
        assert parsed is not None
        assert parsed.utcoffset().total_seconds() == 0
        assert parsed.hour == 3 and parsed.minute == 45

    def test_naive_timestamp_is_assumed_utc(self):
        """A value with no offset keeps its clock time and gains UTC."""
        parsed = _parse_dt("2026-02-11T09:15:00")
        assert parsed is not None
        assert parsed.utcoffset().total_seconds() == 0
        assert parsed.hour == 9

    def test_list_mapping_is_skipped_not_crashed(self, tmp_path):
        """Valid JSON can still carry the wrong shape for mapping."""
        path = tmp_path / "conversations.json"
        path.write_text(
            json.dumps([{"conversation_id": "c1", "current_node": "a", "mapping": [1]}])
        )
        assert list(read_chatgpt(path)) == []

    def test_scalar_node_stops_the_walk(self, tmp_path):
        """A non-object node cannot be walked, and must not raise."""
        path = tmp_path / "conversations.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "conversation_id": "c1",
                        "current_node": "a",
                        "mapping": {"a": 5},
                    }
                ]
            )
        )
        assert list(read_chatgpt(path)) == []

    def test_scalar_author_does_not_crash(self, tmp_path):
        """A non-object author would raise on .get() during the walk."""
        path = tmp_path / "conversations.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "conversation_id": "c1",
                        "current_node": "a",
                        "mapping": {
                            "a": {
                                "id": "a",
                                "parent": None,
                                "message": {
                                    "author": "user",
                                    "content": {
                                        "content_type": "text",
                                        "parts": ["hi"],
                                    },
                                },
                            }
                        },
                    }
                ]
            )
        )
        assert list(read_chatgpt(path)) == []

    def test_inspect_tolerates_a_list_mapping(self, tmp_path):
        """--inspect must survive the same malformed shapes the reader does."""
        path = tmp_path / "conversations.json"
        path.write_text(json.dumps([{"conversation_id": "c1", "mapping": [1, 2]}]))
        counts = inspect_export(path, "chatgpt")
        assert counts["conversations"] == 1
        assert counts["messages"] == 0

    def test_claude_non_string_text_is_ignored(self, tmp_path):
        """A numeric text field would raise on .strip()."""
        path = tmp_path / "conversations.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "uuid": "c1",
                        "name": "T",
                        "chat_messages": [{"sender": "human", "text": 42}],
                    }
                ]
            )
        )
        assert list(read_claude(path)) == []

    def test_source_entry_carries_a_required_resource(self):
        """OKF v0.2 section 5.1 makes resource REQUIRED on every entry."""
        entry = okf_v02._source_entry(
            {"source_ref": "abc123", "source": "chatgpt", "source_title": "T"}
        )
        assert entry is not None
        assert entry["resource"] == "conversation abc123 in a chatgpt data export"

    def test_saved_memory_source_entry_describes_its_scope(self):
        """Pasted memories have no conversation, so the resource is a scope descriptor instead."""
        entry = okf_v02._source_entry(
            {"source_ref": "claude:saved-memories", "source": "claude"}
        )
        assert entry is not None
        assert entry["resource"] == "saved memory list pasted from claude"
