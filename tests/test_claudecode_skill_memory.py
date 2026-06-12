import importlib.util
import json
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "claudecode-skills-memanto"
    / "skill_memory.py"
)


def load_module():
    """Load the example module from its documentation directory."""
    spec = importlib.util.spec_from_file_location("skill_memory", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeRunner:
    """Capture Memanto CLI commands while returning configured output."""

    def __init__(self, stdout="", returncode=0):
        """Configure fake process output for command calls."""
        self.stdout = stdout
        self.returncode = returncode
        self.commands = []

    def __call__(self, command):
        """Record a command and return a process-like result object."""
        self.commands.append(command)

        class Result:
            pass

        result = Result()
        result.stdout = self.stdout
        result.stderr = ""
        result.returncode = self.returncode
        return result


def missing_runner(command):
    """Simulate the Memanto CLI being absent from PATH."""
    raise FileNotFoundError(command[0])


def test_inject_context_formats_recalled_engineering_decisions():
    """Inject mode formats recalled Memanto memories into context."""
    skill_memory = load_module()
    recall_payload = {
        "memories": [
            {
                "content": "Use repository-local helpers before introducing new abstractions.",
                "type": "preference",
                "score": 0.91,
            },
            {
                "content": "Payment code must keep provider-specific retries isolated.",
                "type": "decision",
                "score": 0.84,
            },
        ]
    }
    runner = FakeRunner(stdout=json.dumps(recall_payload))
    bridge = skill_memory.SkillMemoryBridge(runner=runner)

    output = bridge.inject_context(
        {
            "skill": "tdd",
            "task": "add retry tests",
            "project_path": "/workspace/billing",
            "files": ["billing/retry.py"],
        }
    )

    assert "Relevant engineering memory" in output["additionalContext"]
    assert "repository-local helpers" in output["additionalContext"]
    assert "provider-specific retries" in output["additionalContext"]
    assert runner.commands == [
        [
            "memanto",
            "recall",
            "Skill tdd for task add retry tests in /workspace/billing touching billing/retry.py",
            "--limit",
            "5",
            "--json",
        ]
    ]


def test_record_completion_stores_decisions_and_skips_empty_summaries():
    """Record mode stores non-empty summaries and skips empty events."""
    skill_memory = load_module()
    runner = FakeRunner(stdout='{"memory_id": "mem-1"}')
    bridge = skill_memory.SkillMemoryBridge(runner=runner)

    stored = bridge.record_completion(
        {
            "skill": "tdd",
            "task": "add retry tests",
            "project_path": "/workspace/billing",
            "summary": "Captured that retries stop after the third failed provider attempt.",
            "decisions": ["Keep retry policy per provider adapter."],
        }
    )

    skipped = bridge.record_completion(
        {
            "skill": "tdd",
            "task": "empty",
            "project_path": "/workspace/billing",
            "summary": "   ",
            "decisions": [],
        }
    )

    assert stored["stored"] is True
    assert skipped == {"stored": False, "reason": "empty summary"}
    assert len(runner.commands) == 1
    command = runner.commands[0]
    assert command[:3] == ["memanto", "remember", "Skill tdd completed: add retry tests"]
    assert "--type" in command
    assert "decision" in command
    assert "Captured that retries stop after the third failed provider attempt." in command[3]
    assert "Keep retry policy per provider adapter." in command[3]


def test_missing_memanto_cli_fails_open_without_crashing():
    """Missing Memanto binaries return empty outputs instead of raising."""
    skill_memory = load_module()
    bridge = skill_memory.SkillMemoryBridge(runner=missing_runner)

    assert bridge.inject_context({"skill": "tdd", "task": "demo"}) == {
        "additionalContext": ""
    }
    assert bridge.record_completion(
        {"skill": "tdd", "task": "demo", "summary": "Useful decision."}
    ) == {
        "stored": False,
        "reason": "memanto CLI unavailable",
    }


def test_main_reports_invalid_event_input(capsys):
    """Invalid event JSON is reported as a CLI error."""
    skill_memory = load_module()

    exit_code = skill_memory.main(["inject", "--event", "[]"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Invalid event input" in captured.err
    assert "event JSON must be an object" in captured.err
