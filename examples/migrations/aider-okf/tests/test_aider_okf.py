from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from aider_okf import convert, find_sensitive_data, parse_aider_history  # noqa: E402
from generate_source import sanitize_history  # noqa: E402
from path_scrub import scrub_home_paths  # noqa: E402
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
        assert frontmatter["timestamp"] == "2026-09-01T10:20:30Z"

    assert recovered == [message.content for message in parse_aider_history(SOURCE)]


def test_privacy_preflight_fails_closed_without_echoing_secret(tmp_path: Path) -> None:
    secret = "sk-proj-abcdefghijklmnopqrstuvwxyz012345"
    assert find_sensitive_data(f"token={secret}")
    source = tmp_path / "history.md"
    source.write_text(f"#### use {secret}\n", encoding="utf-8")
    with pytest.raises(ValueError) as error:
        convert(source, tmp_path / "out")
    assert secret not in str(error.value)


def test_privacy_preflight_detects_bearer_authorization_header() -> None:
    secret = "eyJhbGciOiJIUzI1NiJ9.payload.signature"
    assert find_sensitive_data(f"Authorization: Bearer {secret}")


@pytest.mark.parametrize(
    ("raw", "survivor"),
    [
        ('"/home/alice/Very Secret Project/file.py"', "Very Secret"),
        ("path=/Users/alice/Very Secret Project/file.py", "Project"),
        (r"/home/alice/Very\ Secret\ Project/file.py", "alice"),
        (r"C:\Users\alice\Documents\private.txt", "alice"),
        (r"output: C:\Users\alice\Very Secret Project\private.txt", "Project"),
    ],
)
def test_home_path_scrubber_covers_publishable_path_forms(
    raw: str, survivor: str
) -> None:
    scrubbed = scrub_home_paths(raw)
    assert "<USER_HOME>" in scrubbed
    assert survivor not in scrubbed


def test_source_sanitizer_keeps_non_path_text(tmp_path: Path) -> None:
    repository = tmp_path / "memanto"
    text = f"repo={repository}\nmessage=keep this explanation\n"
    scrubbed = sanitize_history(text, repository)
    assert "repo=<MEMANTO_REPOSITORY>" in scrubbed
    assert "message=keep this explanation" in scrubbed


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


def _mutated_bundle(tmp_path: Path, field: str, value: str) -> Path:
    """Copy the fixture and mutate one x_aider frontmatter field."""

    bundle = tmp_path / "sample_okf"
    shutil.copytree(HERE / "sample_okf", bundle)
    memory = bundle / "memories" / "001-tool.md"
    text = memory.read_text(encoding="utf-8")
    frontmatter_text, body = text.split("---", 2)[1:]
    frontmatter = yaml.safe_load(frontmatter_text)
    frontmatter["x_aider"][field] = value
    memory.write_text(
        "---\n"
        + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
        + "\n---"
        + body,
        encoding="utf-8",
    )
    return bundle


def test_validation_rejects_mutated_source_receipt(tmp_path: Path) -> None:
    bundle = _mutated_bundle(tmp_path, "source_sha256", "0" * 64)
    with pytest.raises(ValueError, match="source hash mismatch"):
        validate(
            HERE / "data" / "aider.chat.history.md",
            bundle,
            HERE / "golden_questions.yaml",
        )


def test_validation_rejects_mutated_role_metadata(tmp_path: Path) -> None:
    bundle = _mutated_bundle(tmp_path, "role", "user")
    with pytest.raises(ValueError, match="role metadata mismatch"):
        validate(
            HERE / "data" / "aider.chat.history.md",
            bundle,
            HERE / "golden_questions.yaml",
        )
