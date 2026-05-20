import importlib.util
import sys
from pathlib import Path

EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "claudecode-skills-memanto"
    / "skill_memory_hook.py"
)


def load_example_module():
    spec = importlib.util.spec_from_file_location(
        "skill_memory_hook_example", EXAMPLE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_format_memory_block_wraps_recalled_constraints():
    module = load_example_module()

    block = module.format_memory_block("- Use queue workers for retries.")

    assert block.startswith("<memanto-engineering-memory>")
    assert "Use queue workers for retries." in block
    assert block.endswith("</memanto-engineering-memory>")


def test_extract_memory_candidates_redacts_api_keys():
    module = load_example_module()

    payloads = module.extract_memory_candidates(
        skill_name="grill-with-docs",
        task="Design importer",
        path="services/importer.py",
        transcript=(
            "Decision: retries should happen in workers.\n"
            "Preference: keep handoffs concise.\n"
            "Decision: never persist MOORCHEH_API_KEY=mch_supersecrettoken123456789"
        ),
    )

    assert len(payloads) == 2
    all_content = "\n".join(payload.content for payload in payloads)
    assert "mch_supersecrettoken" not in all_content
    assert "[REDACTED_SECRET]" in all_content
    assert "retries should happen in workers" in all_content
    assert "services/importer.py" in all_content


def test_dry_run_before_never_requires_memanto_credentials(capsys):
    module = load_example_module()

    exit_code = module.main(
        [
            "before",
            "--skill-name",
            "tdd",
            "--task",
            "Add importer tests",
            "--dry-run",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "<memanto-engineering-memory>" in output
    assert "small vertical slices" in output
