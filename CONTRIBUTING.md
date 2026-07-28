# Contributing to MEMANTO

Thank you for your interest in contributing to MEMANTO — the universal memory layer for agentic AI. This guide will help you get set up and understand how we work.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Ways to Contribute](#ways-to-contribute)
- [Reporting Bugs](#reporting-bugs)
- [Requesting Features](#requesting-features)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Code Style](#code-style)
- [Running Tests](#running-tests)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Commit Message Convention](#commit-message-convention)
- [Community](#community)

---

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please read it before contributing.

---

## Ways to Contribute

- **Bug reports** — open a GitHub issue with reproduction steps
- **Feature requests** — open a GitHub issue describing the use case
- **Documentation improvements** — fix typos, improve clarity, add examples
- **Bug fixes and features** — submit a pull request (see below)
- **Memory type integrations** — propose new memory type handlers or agent connectors

---

## Reporting Bugs

Before opening an issue, please check that it hasn't been reported already.

When filing a bug, include:

1. **MEMANTO version** (`pip show memanto`)
2. **Python version** (`python --version`)
3. **Operating system**
4. **Steps to reproduce** — a minimal, self-contained script is ideal
5. **Expected behavior** vs. **actual behavior**
6. **Relevant logs or error output**

Open a bug report at: https://github.com/moorcheh-ai/memanto/issues

> **Security vulnerabilities** must **not** be reported as public issues. See [SECURITY.md](SECURITY.md) for responsible disclosure instructions.

---

## Requesting Features

Open a feature request at https://github.com/moorcheh-ai/memanto/issues and include:

- A clear description of the problem you are trying to solve
- Your proposed solution or API
- Any alternatives you considered
- Whether you are willing to implement it yourself

---

## Development Setup

### Prerequisites

- Python 3.10–3.12
- [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`
- A Moorcheh API key from https://console.moorcheh.ai/api-keys

### 1. Fork and clone

```bash
git clone https://github.com/<your-username>/memanto.git
cd memanto
```

### 2. Create a virtual environment and install dependencies

**With uv (recommended):**

```bash
uv sync --group dev
```

**With pip:**

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[all]"
```

### 3. Configure your environment

```bash
cp .env.example .env
# Edit .env and add your MOORCHEH_API_KEY
```

### 4. Install pre-commit hooks

```bash
pre-commit install
```

The hooks run `uv run ruff check`, `uv run ruff format --check`, and `uv run mypy` on every commit automatically.

---

## Project Structure

```
memanto/
├── memanto/
│   ├── app/          # FastAPI application, routes, models
│   └── cli/          # Typer CLI commands
├── tests/            # pytest test suite
├── docs/             # Additional documentation
├── assets/           # Logos and diagrams
├── pyproject.toml    # Project metadata and tool configuration
└── SECURITY.md       # Security policy
```

---

## Code Style

We use **[Ruff](https://docs.astral.sh/ruff/)** for linting and formatting, and **[mypy](https://mypy.readthedocs.io/)** for static type checking. All tools are run via `uv run` so no global installs are needed.

```bash
# Check for lint errors
uv run ruff check .

# Check formatting (non-destructive — reports issues without modifying files)
uv run ruff format --check .

# Apply lint fixes and format in one go (use before committing)
uv run ruff check . --fix && uv run ruff format .

# Type check
uv run mypy .
```

Key conventions:

- Line length: 88 characters
- Target Python version: 3.10+
- Import order enforced by ruff (`isort` rules)
- Do not suppress type errors with `# type: ignore` without a comment explaining why

Running pre-commit manually:

```bash
uv run pre-commit run --all-files
```

---

## Running Tests

```bash
# Run the full test suite
pytest

# Run a specific test file
pytest tests/test_cli.py

# Run with verbose output
pytest -v

# Run and stop on first failure
pytest -x
```

Tests require a valid `MOORCHEH_API_KEY` in your environment or `.env` file for any integration tests. Unit tests that don't hit the network will run without a key.

---

## Submitting a Pull Request

1. **Create a branch** from `main`:

   ```bash
   git checkout -b fix/describe-your-fix
   # or
   git checkout -b feat/describe-your-feature
   ```

   Branch naming:
   | Prefix | Use for |
   |--------|---------|
   | `feat/` | new features |
   | `fix/` | bug fixes |
   | `docs/` | documentation only |
   | `chore/` | maintenance, dependency updates |
   | `test/` | adding or fixing tests |
   | `refactor/` | code restructuring without behavior change |

2. **Make your changes.** Keep each PR focused on a single concern.

3. **Add tests** for any new behavior. PRs that reduce test coverage will be asked to add tests before merging.

4. **Ensure all checks pass:**

   ```bash
   pre-commit run --all-files
   pytest
   ```

5. **Push your branch** and open a pull request against `main`.

6. **Fill in the PR description:**
   - What problem does this solve?
   - How did you test it?
   - Link any related issues (e.g., `Closes #42`)

7. A maintainer will review your PR. Please respond to feedback within a reasonable time. PRs with no activity for 30 days may be closed.

### PR Checklist

- [ ] Code follows the project style (`ruff`, `mypy` pass)
- [ ] Tests added or updated for changed behavior
- [ ] All existing tests pass
- [ ] Documentation updated if the public API or CLI changed
- [ ] No secrets or credentials in the diff

---

## Commit Message Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary>

[optional body]

[optional footer(s)]
```

**Types:** `feat`, `fix`, `docs`, `chore`, `test`, `refactor`, `perf`, `ci`

**Examples:**

```
feat(cli): add --type flag to recall command
fix(app): handle empty memory list in daily-summary endpoint
docs: update REST API section in README
chore(deps): bump pydantic to 2.7.0
```

Rules:
- Use the imperative mood in the summary ("add", not "added" or "adds")
- Keep the summary under 72 characters
- Reference issues in the footer: `Closes #123`

---

## Community

- **Discord**: [Join our server](https://memanto.ai/discord) — the best place for quick questions and discussions
- **GitHub Issues**: https://github.com/moorcheh-ai/memanto/issues — bugs and feature requests
- **Email**: support@moorcheh.ai — for anything that doesn't fit the above
- **Docs**: https://docs.memanto.ai

We appreciate every contribution, no matter how small. Thank you for helping make MEMANTO better.
