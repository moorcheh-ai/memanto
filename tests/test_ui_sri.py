from html.parser import HTMLParser
from pathlib import Path

INDEX_PATH = (
    Path(__file__).parents[1] / "memanto" / "app" / "ui" / "static" / "index.html"
)


EXPECTED_SCRIPTS = {
    "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js": "sha384-9nhczxUqK87bcKHh20fSQcTGD4qq5GhayNYSYWqwBkINBhOfQLg/P5HG5lF1urn4",
    "https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js": "sha384-NNQgBjjuhtXzPmmy4gurS5X7P4uTt1DThyevz4Ua0IVK5+kazYQI1W27JHjbbxQz",
    "https://cdn.jsdelivr.net/npm/dompurify@3.0.11/dist/purify.min.js": "sha384-Ic7KEGROu37YaruU6NyiYeib7UhjFyDZQ5fzBAji965L75T/4LGk5nzwMEjNGexs",
}


class ScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: dict[str, dict[str, str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "script":
            return
        attributes = {name: value or "" for name, value in attrs}
        src = attributes.get("src")
        if src in EXPECTED_SCRIPTS:
            self.scripts[src] = attributes


def test_external_ui_scripts_use_subresource_integrity() -> None:
    parser = ScriptParser()
    parser.feed(INDEX_PATH.read_text(encoding="utf-8"))

    assert set(parser.scripts) == set(EXPECTED_SCRIPTS)
    for src, expected_integrity in EXPECTED_SCRIPTS.items():
        script = parser.scripts[src]
        assert script["integrity"] == expected_integrity
        assert script["crossorigin"] == "anonymous"
