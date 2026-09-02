from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from aider_okf import convert, find_sensitive_data, parse_aider_history  # noqa: E402
from validate import validate  # noqa: E402

SOURCE = (
    "# aider chat started at 2026-09-01 10:20:30\n\n"
    "#### Remember UTC storage.  \n"
    "#### Display New York time.\n"
    "> Aider v1.2.3  \n\n"
    "Updated the profile.\n\n"
    "#### Summarize it.\n"
    "UTC storage and New York display.\n"
)


def test_parser_matches_aider_role_markers() -> None:
    messages = parse_aider_history(SOURCE)
    assert [(message.role, message.content) for message in messages] == [
        ("user", "Remember UTC storage.  \nDisplay New York time."),
        ("tool", "Aider v1.2.3"),
        ("assistant", "Updated the profile."),
        ("user", "Summarize it."),
        ("assistant", "UTC storage and New York display."),
    ]
    assert all(message.session == 1 for message in messages)


def test_conversion_is_lossless_and_valid_okf(tmp_path: Path) -> None:
    source = tmp_path / ".aider.chat.history.md"
    source.write_text(SOURCE, encoding="utf-8")
    output = tmp_path / "okf"
    receipt = convert(source, output)

    assert receipt["source_records"] == receipt["mapped_memories"] == 5
    assert receipt["skipped"] == 0
    documents = sorted((output / "memories").glob("*.md"))
    assert len(documents) == 5
    recovered: list[str] = []
    for document in documents:
        text = document.read_text(encoding="utf-8")
        frontmatter_text, body = text.split("---", 2)[1:]
        frontmatter = yaml.safe_load(frontmatter_text)
        recovered.append(body.split("\n", 4)[-1].strip())
        assert (
            frontmatter["x_aider"]["content_sha256"]
            == hashlib.sha256(recovered[-1].encode()).hexdigest()
        )
        assert frontmatter["x_memanto"]["source"] == "aider"

    assert recovered == [message.content for message in parse_aider_history(SOURCE)]


def test_privacy_preflight_fails_closed_without_echoing_secret(tmp_path: Path) -> None:
    secret = "sk-proj-abcdefghijklmnopqrstuvwxyz012345"
    assert find_sensitive_data(f"token={secret}")
    source = tmp_path / "history.md"
    source.write_text(f"#### use {secret}\n", encoding="utf-8")
    with pytest.raises(ValueError) as error:
        convert(source, tmp_path / "out")
    assert secret not in str(error.value)


def test_existing_output_is_never_overlaid(tmp_path: Path) -> None:
    source = tmp_path / "history.md"
    source.write_text(SOURCE, encoding="utf-8")
    output = tmp_path / "okf"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        convert(source, output)
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_checked_in_genuine_source_receipt() -> None:
    receipt = validate(
        HERE / "data" / "aider.chat.history.md",
        HERE / "sample_okf",
        HERE / "golden_questions.yaml",
    )
    assert receipt["source_records"] == 16
    assert receipt["mapped_memories"] == 16
    assert receipt["exact_content_hashes"] == "16/16"
    assert receipt["golden_recall_parity"] == "4/4"
