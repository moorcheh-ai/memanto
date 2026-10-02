from memanto.cli.connect.agent_registry import AGENT_REGISTRY, detect_memanto_installed
from memanto.cli.connect.templates import MEMANTO_SENTINEL, MEMANTO_SENTINEL_END


def _write_shared_agents_skill(project_dir):
    skill_dir = project_dir / ".agents" / "skills" / "memanto"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("memanto skill\n", encoding="utf-8")


def _write_agent_skill(project_dir, agent_name):
    skill_dir = AGENT_REGISTRY[agent_name].resolve_skill_local(project_dir)
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("memanto skill\n", encoding="utf-8")


def test_shared_agents_skill_alone_does_not_mark_instruction_agents_installed(
    tmp_path,
):
    """The shared .agents skill path is used by several agents.

    A leftover SKILL.md without the matching agent instruction file is not a
    complete install and must not make every agent that uses that shared skill
    directory appear installed.
    """
    _write_shared_agents_skill(tmp_path)

    installed = {agent.name for agent in detect_memanto_installed(tmp_path)}

    assert installed.isdisjoint({"codex", "cline", "opencode", "github-copilot"})


def test_cline_install_detection_requires_cline_rule_file(tmp_path):
    """Cline should be detected only when its own rule file is present."""
    _write_shared_agents_skill(tmp_path)
    cline_rule = tmp_path / ".clinerules" / "memanto.md"
    cline_rule.parent.mkdir(parents=True)
    cline_rule.write_text(
        f"{MEMANTO_SENTINEL}\n## MEMANTO\n{MEMANTO_SENTINEL_END}\n",
        encoding="utf-8",
    )

    installed = {agent.name for agent in detect_memanto_installed(tmp_path)}

    assert "cline" in installed
    assert installed.isdisjoint({"codex", "opencode", "github-copilot"})


def test_skills_only_agent_detected_from_skill_file_alone(tmp_path):
    """Agents without an instruction file are detected from SKILL.md alone."""
    skills_only_agent = AGENT_REGISTRY["antigravity"]
    assert skills_only_agent.instruction_local_file is None
    _write_agent_skill(tmp_path, skills_only_agent.name)

    installed = {agent.name for agent in detect_memanto_installed(tmp_path)}

    assert skills_only_agent.name in installed


def test_pi_install_detection_requires_pi_skill_dir(tmp_path):
    """Pi shares AGENTS.md with codex/opencode, so its own skill dir decides."""
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text(
        f"{MEMANTO_SENTINEL}\n## MEMANTO\n{MEMANTO_SENTINEL_END}\n",
        encoding="utf-8",
    )
    _write_shared_agents_skill(tmp_path)

    installed = {agent.name for agent in detect_memanto_installed(tmp_path)}

    assert "codex" in installed
    assert "pi" not in installed

    _write_agent_skill(tmp_path, "pi")

    installed = {agent.name for agent in detect_memanto_installed(tmp_path)}

    assert "pi" in installed
