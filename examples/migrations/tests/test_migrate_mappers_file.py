import pytest

from mappers import map_langgraph, map_notion, map_obsidian


def _lg_item(key, value, namespace=None):
    item = {"key": key, "value": value}
    if namespace is not None:
        item["namespace"] = namespace
    return item


def _md_entry(body="", title="", stem="", tags=None, created_at=None):
    e = {"body": body, "filename_stem": stem, "tags": tags or []}
    if title:
        e["title"] = title
    if created_at:
        e["created_at"] = created_at
    return e


class TestMapLanggraph:
    def test_value_dict_extracts_content(self):
        export = {"items": [_lg_item("k1", {"content": "hello world"}, ["user", "abc"])]}
        rows = map_langgraph(export)
        assert len(rows) == 1
        assert rows[0]["content"].startswith("hello world")

    def test_value_str_used_directly(self):
        export = {"items": [_lg_item("k2", "plain string value", ["ns"])]}
        rows = map_langgraph(export)
        assert rows[0]["content"].startswith("plain string value")

    def test_value_dict_no_content_key_serialized(self):
        export = {"items": [_lg_item("k3", {"note": "some note", "priority": "high"}, [])]}
        rows = map_langgraph(export)
        assert len(rows) == 1
        assert "note" in rows[0]["content"] or "some note" in rows[0]["content"]

    def test_value_other_type_str_converted(self):
        export = {"items": [_lg_item("k3", 42, [])]}
        rows = map_langgraph(export)
        assert rows[0]["content"].startswith("42")

    def test_namespace_list_becomes_tag(self):
        export = {"items": [_lg_item("k4", "content", ["user", "thread", "123"])]}
        rows = map_langgraph(export)
        assert "user/thread/123" in rows[0]["tags"]

    def test_key_becomes_source_ref(self):
        export = {"items": [_lg_item("my-key", "some content", [])]}
        assert map_langgraph(export)[0]["source_ref"] == "my-key"

    def test_source_and_provenance(self):
        r = map_langgraph({"items": [_lg_item("k5", "content", [])]})[0]
        assert r["source"] == "langgraph"
        assert r["provenance"] == "imported"

    def test_type_is_none(self):
        assert map_langgraph({"items": [_lg_item("k6", "content", [])]})[0]["type"] is None

    def test_empty_export(self):
        assert map_langgraph({}) == []
        assert map_langgraph({"items": []}) == []

    def test_empty_content_skipped(self):
        export = {"items": [_lg_item("k7", {"content": "   "}, [])]}
        assert map_langgraph(export) == []

    def test_empty_namespace_no_tag(self):
        assert map_langgraph({"items": [_lg_item("k8", "content", [])]})[0]["tags"] == []

    def test_missing_namespace_key(self):
        export = {"items": [{"key": "k9", "value": "content"}]}
        rows = map_langgraph(export)
        assert len(rows) == 1
        assert rows[0]["tags"] == []

    @pytest.mark.parametrize("namespace,expected_tag", [
        (["a", "b"],  "a/b"),
        (["single"],  "single"),
        ("string-ns", "string-ns"),
    ])
    def test_namespace_formats(self, namespace, expected_tag):
        export = {"items": [_lg_item("k", "content", namespace)]}
        assert map_langgraph(export)[0]["tags"] == [expected_tag]


class TestMapNotion:
    def test_basic_entry(self):
        export = {"memories": [_md_entry(body="My note body", stem="my-note")]}
        rows = map_notion(export)
        assert len(rows) == 1
        assert rows[0]["content"].startswith("My note body")

    def test_source_and_provenance(self):
        r = map_notion({"memories": [_md_entry(body="body", stem="stem")]})[0]
        assert r["source"] == "notion"
        assert r["provenance"] == "imported"
        assert r["type"] == "artifact"

    def test_title_from_frontmatter(self):
        export = {"memories": [_md_entry(body="body", title="Explicit Title", stem="stem")]}
        assert map_notion(export)[0]["title"] == "Explicit Title"

    def test_title_fallback_to_stem(self):
        export = {"memories": [_md_entry(body="body", stem="my-page")]}
        assert map_notion(export)[0]["title"] == "my-page"

    def test_title_fallback_to_body_excerpt(self):
        body = "This is a long note without explicit title"
        rows = map_notion({"memories": [_md_entry(body=body, stem="")]})
        assert rows[0]["title"] in body or rows[0]["title"].endswith("...")

    def test_empty_body_with_title_uses_title_as_content(self):
        export = {"memories": [_md_entry(body="", title="Page Title", stem="page-title")]}
        rows = map_notion(export)
        assert len(rows) == 1
        assert rows[0]["content"].startswith("Page Title")

    def test_empty_body_and_no_title_skipped(self):
        assert map_notion({"memories": [_md_entry(body="", title="", stem="page")]}) == []

    def test_whitespace_only_body_skipped(self):
        assert map_notion({"memories": [_md_entry(body="   \n\t  ", title="", stem="page")]}) == []

    def test_tags_from_frontmatter(self):
        export = {"memories": [_md_entry(body="body", tags=["python", "notes"], stem="s")]}
        tags = map_notion(export)[0]["tags"]
        assert "python" in tags
        assert "notes" in tags

    def test_source_ref_is_stem(self):
        assert map_notion({"memories": [_md_entry(body="body", stem="my-note")]})[0]["source_ref"] == "my-note"

    def test_empty_export(self):
        assert map_notion({}) == []
        assert map_notion({"memories": []}) == []

    def test_missing_optional_fields(self):
        rows = map_notion({"memories": [{"body": "just a body"}]})
        assert len(rows) == 1
        assert rows[0]["tags"] == []

    def test_created_at_parsed(self):
        export = {"memories": [_md_entry(body="body", stem="s", created_at="2024-01-15T10:00:00Z")]}
        assert map_notion(export)[0]["created_at"] is not None


class TestMapObsidian:
    def test_basic_entry(self):
        export = {"memories": [_md_entry(body="Vault note content", stem="vault-note")]}
        rows = map_obsidian(export)
        assert len(rows) == 1
        assert rows[0]["content"].startswith("Vault note content")

    def test_source_and_provenance(self):
        r = map_obsidian({"memories": [_md_entry(body="body", stem="stem")]})[0]
        assert r["source"] == "obsidian"
        assert r["provenance"] == "imported"
        assert r["type"] == "artifact"

    def test_title_from_frontmatter(self):
        export = {"memories": [_md_entry(body="body", title="Note Title", stem="stem")]}
        assert map_obsidian(export)[0]["title"] == "Note Title"

    def test_title_fallback_to_stem(self):
        export = {"memories": [_md_entry(body="body", stem="my-vault-note")]}
        assert map_obsidian(export)[0]["title"] == "my-vault-note"

    def test_empty_body_with_title_not_skipped(self):
        export = {"memories": [_md_entry(body="", title="Has Title", stem="s")]}
        assert len(map_obsidian(export)) == 1

    def test_empty_body_and_no_title_skipped(self):
        assert map_obsidian({"memories": [_md_entry(body="", title="", stem="note")]}) == []

    def test_whitespace_only_body_skipped(self):
        assert map_obsidian({"memories": [_md_entry(body="  \n  ", title="", stem="note")]}) == []

    def test_tags_extracted(self):
        export = {"memories": [_md_entry(body="body", tags=["tag1", "tag2"], stem="s")]}
        assert map_obsidian(export)[0]["tags"] == ["tag1", "tag2"]

    def test_no_tags(self):
        assert map_obsidian({"memories": [_md_entry(body="body", stem="s")]})[0]["tags"] == []

    def test_source_ref_is_stem(self):
        assert map_obsidian({"memories": [_md_entry(body="body", stem="vault-file")]})[0]["source_ref"] == "vault-file"

    def test_empty_export(self):
        assert map_obsidian({}) == []
        assert map_obsidian({"memories": []}) == []

    def test_missing_optional_fields(self):
        rows = map_obsidian({"memories": [{"body": "just a body"}]})
        assert len(rows) == 1
        assert rows[0]["tags"] == []

    def test_created_at_parsed(self):
        export = {"memories": [_md_entry(body="body", stem="s", created_at="2023-06-01T08:30:00+00:00")]}
        assert map_obsidian(export)[0]["created_at"] is not None

    @pytest.mark.parametrize("body,title,stem,expected_title", [
        ("body text", "FM Title", "stem",      "FM Title"),
        ("body text", "",         "my-stem",   "my-stem"),
        ("short body", "",        "",          "short body"),
    ])
    def test_title_resolution(self, body, title, stem, expected_title):
        rows = map_obsidian({"memories": [_md_entry(body=body, title=title, stem=stem)]})
        assert rows[0]["title"] == expected_title
