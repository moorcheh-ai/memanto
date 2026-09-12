import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.adapters import DataSource, load_source


class _FileLike:
    name = "filelike"

    def load(self, path):
        return f"file:{path}"

    def extract(self, raw, filters=None):
        return []

    def get_conversation_list(self, raw):
        return []

    def get_source_stats(self):
        return {}


class _ApiLike:
    name = "apilike"

    def load_source(self, source):
        return f"api:{source.endpoint}:{source.credentials.get('token')}"

    def extract(self, raw, filters=None):
        return []

    def get_conversation_list(self, raw):
        return []

    def get_source_stats(self):
        return {}


class TestDataSource:
    def test_from_file(self):
        ds = DataSource.from_file("/a/b.json")
        assert ds.kind == "file"
        assert ds.path == "/a/b.json"

    def test_from_api(self):
        ds = DataSource.from_api("https://x", {"token": "abc"})
        assert ds.kind == "api"
        assert ds.endpoint == "https://x"
        assert ds.credentials == {"token": "abc"}


class TestLoadSource:
    def test_file_dispatch(self):
        out = load_source(_FileLike(), DataSource.from_file("/a/b.json"))
        assert out == "file:/a/b.json"

    def test_api_dispatch_injects_credentials(self):
        out = load_source(
            _ApiLike(), DataSource.from_api("https://x", {"token": "abc"})
        )
        assert out == "api:https://x:abc"

    def test_file_adapter_rejects_api_source(self):
        try:
            load_source(_FileLike(), DataSource.from_api("https://x"))
        except TypeError:
            return
        raise AssertionError("expected TypeError")

    def test_api_adapter_rejects_file_source(self):
        try:
            load_source(_ApiLike(), DataSource.from_file("/a/b.json"))
        except TypeError:
            return
        raise AssertionError("expected TypeError")

    def test_unknown_kind_rejected(self):
        try:
            load_source(_FileLike(), DataSource(kind="usb"))
        except ValueError:
            return
        raise AssertionError("expected ValueError")
