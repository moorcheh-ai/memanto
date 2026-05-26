from pathlib import Path
import subprocess
import sys


EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples" / "claudecode-skills-memanto"
SCRIPT = EXAMPLE_DIR / "scripts" / "memanto_skill_memory.py"
README = EXAMPLE_DIR / "README.md"
SKILL = EXAMPLE_DIR / "skills" / "memanto-project-memory" / "SKILL.md"


def run_script(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_claudecode_skills_memanto_example_files_exist():
    assert README.exists()
    assert SKILL.exists()
    assert SCRIPT.exists()
    assert "dry-run" in README.read_text().lower()
    assert "memanto-project-memory" in SKILL.read_text()


def test_memanto_skill_memory_setup_dry_run_prints_agent_create_command():
    result = run_script("setup", "--agent-id", "demo-project", "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "memanto agent create demo-project --pattern project" in result.stdout


def test_memanto_skill_memory_remember_decision_dry_run_uses_typed_memory():
    result = run_script(
        "remember-decision",
        "--title",
        "Use SQLite",
        "--content",
        "Decision: use SQLite for local cache.",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    assert "memanto remember" in result.stdout
    assert "--type decision" in result.stdout
    assert "--title 'Use SQLite'" in result.stdout


def test_memanto_skill_memory_recall_dry_run_prints_recall_command():
    result = run_script("recall", "--query", "local cache", "--limit", "3", "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "memanto recall 'local cache' --limit 3" in result.stdout
