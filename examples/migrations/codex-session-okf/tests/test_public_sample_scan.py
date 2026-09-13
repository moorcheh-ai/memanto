"""Tests for the public-demo safety scanner."""

from pathlib import Path

from scan_public_sample import scan_path


def test_scan_accepts_benign_text(tmp_path: Path) -> None:
    """Allow ordinary public demonstration content."""
    (tmp_path / "sample.md").write_text(
        "Portable memory belongs to you.\n", encoding="utf-8"
    )

    assert scan_path(tmp_path) == []


def test_scan_rejects_new_credential_forms_without_echoing_values(
    tmp_path: Path,
) -> None:
    """Keep the preflight scanner aligned with the adapter redactor."""
    github_token = "github_pat_" + "A" * 32
    aws_access_key = "ASIA" + "B" * 16
    jwt = "eyJ" + "c" * 12 + "." + "d" * 12 + "." + "e" * 12
    (tmp_path / "unsafe.txt").write_text(
        f"{github_token}\n{aws_access_key}\n{jwt}\n", encoding="utf-8"
    )

    findings = scan_path(tmp_path)

    assert findings == ["unsafe.txt: 3 sensitive value(s)"]
    assert github_token not in findings[0]
    assert aws_access_key not in findings[0]
    assert jwt not in findings[0]


def test_scan_fails_closed_on_non_utf8_file(tmp_path: Path) -> None:
    """Do not silently skip binary content in a public sample tree."""
    (tmp_path / "opaque.bin").write_bytes(b"\xff\xfe")

    assert scan_path(tmp_path) == ["opaque.bin: non-UTF-8 file"]
