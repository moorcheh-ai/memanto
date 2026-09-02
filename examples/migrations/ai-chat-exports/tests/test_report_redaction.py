import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


from generate_report import _HOME, _HOME_RE, _redact_home

HOME_STR = str(_HOME)


class TestHomeRedaction:
    def test_plain_path_separator(self):
        text = f"Run dir: {HOME_STR}/.memanto/x"
        assert HOME_STR not in _redact_home(text)
        assert "~/.memanto/x" in _redact_home(text)

    def test_home_at_end_of_line(self):
        text = f"Path: {HOME_STR}"
        assert HOME_STR not in _redact_home(text)
        assert "~" in _redact_home(text)

    def test_home_in_quotes(self):
        text = f'home = "{HOME_STR}"'
        redacted = _redact_home(text)
        assert HOME_STR not in redacted
        assert 'home = "~"' in redacted

    def test_home_before_colon(self):
        text = f"{HOME_STR}: not found"
        redacted = _redact_home(text)
        assert HOME_STR not in redacted
        assert "~: not found" in redacted

    def test_home_before_period(self):
        text = f"...{HOME_STR}.json"
        redacted = _redact_home(text)
        assert HOME_STR not in redacted
        assert "~.json" in redacted

    def test_longer_prefix_not_clobbered(self):
        sibling = f"{HOME_STR}2-other"
        redacted = _redact_home(sibling)
        assert sibling == redacted

    def test_underscore_sibling_not_redacted(self):
        sibling = f"{HOME_STR}_backup"
        redacted = _redact_home(sibling)
        assert sibling == redacted

    def test_unicode_sibling_not_redacted(self):
        sibling = f"{HOME_STR}П"
        redacted = _redact_home(sibling)
        assert sibling == redacted

    def test_home_before_whitespace(self):
        text = f"from {HOME_STR} "  # trailing space before EOL
        redacted = _redact_home(text)
        assert HOME_STR not in redacted
        assert "~ " in redacted

    def test_regex_is_literal_escaped(self):
        assert re.escape(HOME_STR) in _HOME_RE.pattern