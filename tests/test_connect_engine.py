from memanto.cli.connect.agent_registry import AGENT_REGISTRY
from memanto.cli.connect.engine import _remove_instructions
from memanto.cli.connect.templates import get_instruction_content


def test_remove_dedicated_instruction_preserves_unmanaged_file(tmp_path):
    agent = AGENT_REGISTRY["cursor"]
    rules_path = tmp_path / ".cursor" / "rules" / "memanto.mdc"
    rules_path.parent.mkdir(parents=True)
    rules_path.write_text("User-owned Cursor rules\n", encoding="utf-8")

    result = _remove_instructions(agent, tmp_path, is_global=False)

    assert result is None
    assert rules_path.read_text(encoding="utf-8") == "User-owned Cursor rules\n"


def test_remove_dedicated_instruction_preserves_non_utf8_unmanaged_file(tmp_path):
    agent = AGENT_REGISTRY["cursor"]
    rules_path = tmp_path / ".cursor" / "rules" / "memanto.mdc"
    rules_path.parent.mkdir(parents=True)
    rules_path.write_bytes(b"\xff\xfeuser-owned rules")

    result = _remove_instructions(agent, tmp_path, is_global=False)

    assert result is None
    assert rules_path.read_bytes() == b"\xff\xfeuser-owned rules"


def test_remove_dedicated_instruction_deletes_memanto_managed_file(tmp_path):
    agent = AGENT_REGISTRY["cursor"]
    rules_path = tmp_path / ".cursor" / "rules" / "memanto.mdc"
    rules_path.parent.mkdir(parents=True)
    rules_path.write_text(get_instruction_content("cursor"), encoding="utf-8")

    result = _remove_instructions(agent, tmp_path, is_global=False)

    assert result == "Removed memanto.mdc"
    assert not rules_path.exists()
