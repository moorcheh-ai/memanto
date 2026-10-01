#!/usr/bin/env python3
"""
Regression tests for CLI stream encoding.

Rich emits box-drawing characters, bullets and braille spinner frames. When the
CLI's output is captured on Windows, Python encodes it with the locale code page
(cp1252), which cannot represent any of them, and every affected command dies
with UnicodeEncodeError before printing a result.

See memanto.cli._ensure_utf8_streams.
"""

import io

from memanto.cli import _ensure_utf8_streams

# One frame of Rich's braille spinner, a box-drawing corner, and a bullet: the
# exact characters that crashed `memanto recall` under cp1252.
RICH_GLYPHS = "⠹⠦ ┌─┐ ● —"


class FakeStream:
    """Stand-in for sys.stdout that records reconfigure() calls.

    Deliberately not an io.StringIO subclass: StringIO.encoding is a writable
    attribute, so overriding it with a property is a typing error. The helper
    only needs the three members _ensure_utf8_streams touches.
    """

    def __init__(self, encoding: str, isatty: bool = False):
        self.encoding = encoding
        self._isatty = isatty
        self.reconfigured: list[dict] = []

    def isatty(self) -> bool:
        return self._isatty

    def reconfigure(self, **kwargs) -> None:
        self.reconfigured.append(kwargs)
        if "encoding" in kwargs:
            self.encoding = kwargs["encoding"]


def _run(monkeypatch, stdout, stderr):
    monkeypatch.setattr("sys.stdout", stdout)
    monkeypatch.setattr("sys.stderr", stderr)
    _ensure_utf8_streams()


def test_legacy_codepage_streams_are_switched_to_utf8(monkeypatch):
    out, err = FakeStream("cp1252"), FakeStream("cp1252")
    _run(monkeypatch, out, err)

    for stream in (out, err):
        assert stream.reconfigured == [{"encoding": "utf-8", "errors": "replace"}]


def test_nul_device_is_fixed_even_though_it_claims_to_be_a_tty(monkeypatch):
    """`command > NUL` on Windows reports isatty() True while encoding cp1252.

    isatty() is therefore not a usable signal here; only the encoding is.
    """
    out = FakeStream("cp1252", isatty=True)
    _run(monkeypatch, out, FakeStream("utf-8"))

    assert out.reconfigured == [{"encoding": "utf-8", "errors": "replace"}]


def test_utf8_streams_are_left_alone(monkeypatch):
    out, err = FakeStream("utf-8"), FakeStream("UTF-8")
    _run(monkeypatch, out, err)

    assert out.reconfigured == []
    assert err.reconfigured == []


def test_utf8_alias_spellings_are_left_alone(monkeypatch):
    out, err = FakeStream("utf8"), FakeStream("UTF_8")
    _run(monkeypatch, out, err)

    assert out.reconfigured == []
    assert err.reconfigured == []


def test_streams_without_reconfigure_are_skipped(monkeypatch):
    """Captured stdout under pytest/CI may be a plain object with no reconfigure."""

    class Bare:
        encoding = "cp1252"

        def isatty(self):
            return False

    _run(monkeypatch, Bare(), Bare())  # must not raise


def test_reconfigure_failure_never_stops_the_cli(monkeypatch):
    class Hostile(FakeStream):
        def reconfigure(self, **kwargs):
            raise OSError("stream is closed")

    _run(monkeypatch, Hostile("cp1252"), Hostile("cp1252"))  # must not raise


def test_rich_glyphs_survive_a_cp1252_stream_after_the_fix():
    """End to end: the glyphs that used to crash now encode cleanly."""
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252", errors="strict")

    try:
        stream.write(RICH_GLYPHS)
        stream.flush()
        raise AssertionError("cp1252 unexpectedly encoded Rich's glyphs")
    except UnicodeEncodeError:
        pass  # the bug this module guards against

    stream.reconfigure(encoding="utf-8", errors="replace")
    stream.write(RICH_GLYPHS)
    stream.flush()

    assert RICH_GLYPHS.encode("utf-8") in buffer.getvalue()
