"""
Persisted per-project capture settings for the Langfuse sync.

Lives at ``~/.memanto/migrate/langfuse/config.json``, beside ``state.json``.

Why this exists: Langfuse guarantees almost nothing about the *meaning* of the
data it stores. Score names, their data types, and their numeric ranges are all
user-defined, and the docs state no convention for whether a higher score is
better. Latency and cost budgets differ per project and per operation. So there
is no set of thresholds Memanto could ship that would be correct for everyone —
the settings have to belong to the user, be written down once, and be scoped to
the Langfuse project they describe.

Shape::

    {
      "version": 1,
      "projects": {
        "<project key>": {
          "capture": ["errors"],
          "score_fail_rules": ["correctness<0.7"],
          "score_pass_rules": ["correctness>=0.9"],
          "latency_ms": null,
          "latency_percentile": 95,
          "cost_usd": null,
          "cost_percentile": null,
          "group_by": null
        }
      }
    }

Only ``errors`` works with no configuration at all, which is why it is the
default: ``level`` is the one field every Langfuse project populates the same
way. Every other mode stays inert — and says so — until the user supplies a
rule or a threshold.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "config.json"
CONFIG_VERSION = 1
DEFAULT_PROJECT_KEY = "default"

# Defined here rather than in `langfuse_rules` because that module imports this
# one; keeping the constant at the lower level lets config validate what it
# loads without a circular import. `langfuse_rules` re-exports it.
CAPTURE_MODES = ("errors", "low_score", "slow", "costly", "success")

# `<=` and `>=` must be tried before `<` and `>`.
_RULE_RE = re.compile(
    r"^\s*(?P<name>[^<>=!\s]+)\s*(?P<op><=|>=|!=|==|=|<|>|\bin\b)\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
_NUMERIC_OPS = ("<", "<=", ">", ">=")


class ScoreRuleError(ValueError):
    """A score rule the user wrote could not be understood."""


@dataclass(frozen=True)
class ScoreRule:
    """One user-defined rule over a named Langfuse score.

    Langfuse scores carry no direction convention, so the user states it:
    ``correctness<0.7`` marks failures, ``toxicity>0.3`` also marks failures,
    and which list a rule lives in (fail or pass) is what gives it meaning.
    """

    name: str
    op: str
    value: Any

    def __str__(self) -> str:
        if self.op == "in":
            return f"{self.name} in {','.join(str(v) for v in self.value)}"
        return f"{self.name}{self.op}{self.value}"

    def matches(self, score: dict[str, Any]) -> bool:
        """Does *score* satisfy this rule?

        Returns ``False`` rather than raising when the score's type can't
        support the comparison — a numeric rule aimed at a categorical score
        is a user mistake we surface at config time, not a reason to abort a
        sync mid-run.
        """
        if str(score.get("name") or "") != self.name:
            return False

        actual = score.get("value")
        if actual is None:
            return False

        if self.op == "in":
            return str(actual).strip().lower() in {
                str(v).strip().lower() for v in self.value
            }

        if self.op in ("==", "="):
            return _loose_equal(actual, self.value)
        if self.op == "!=":
            return not _loose_equal(actual, self.value)

        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            return False
        try:
            threshold = float(self.value)
        except (TypeError, ValueError):
            return False

        actual_f = float(actual)
        if self.op == "<":
            return actual_f < threshold
        if self.op == "<=":
            return actual_f <= threshold
        if self.op == ">":
            return actual_f > threshold
        return actual_f >= threshold


def _loose_equal(actual: Any, expected: Any) -> bool:
    """Compare a score value to a rule value across the four Langfuse types."""
    if isinstance(expected, bool) or isinstance(actual, bool):
        return _truthy(actual) == _truthy(expected)
    if isinstance(actual, (int, float)):
        try:
            return float(actual) == float(expected)
        except (TypeError, ValueError):
            return False
    return str(actual).strip().lower() == str(expected).strip().lower()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in ("true", "yes", "1")


def _coerce_rule_value(raw: str) -> Any:
    text = raw.strip().strip("\"'")
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return float(text)
    except ValueError:
        return text


def parse_score_rule(raw: str) -> ScoreRule:
    """Parse ``"correctness<0.7"`` / ``"tone in polite,neutral"`` into a rule."""
    match = _RULE_RE.match(raw or "")
    if not match:
        raise ScoreRuleError(
            f"Could not parse score rule {raw!r}. "
            "Use <score name><op><value>, e.g. 'correctness<0.7', "
            "'toxicity>0.3', 'thumbs_up=false', or 'tone in polite,neutral'."
        )

    name = match.group("name").strip()
    op = match.group("op").strip().lower()
    if op == "=":
        op = "=="
    raw_value = match.group("value")

    if op == "in":
        values = [v.strip() for v in raw_value.split(",") if v.strip()]
        if not values:
            raise ScoreRuleError(f"Rule {raw!r} needs at least one value after 'in'.")
        return ScoreRule(name=name, op=op, value=values)

    value = _coerce_rule_value(raw_value)
    if op in _NUMERIC_OPS and not isinstance(value, float):
        raise ScoreRuleError(
            f"Rule {raw!r} compares with '{op}', which needs a number — "
            f"got {raw_value.strip()!r}. For text scores use "
            f"'{name}==<value>' or '{name} in a,b'."
        )
    return ScoreRule(name=name, op=op, value=value)


@dataclass
class ProjectConfig:
    """Capture settings for one Langfuse project."""

    capture: frozenset[str] = frozenset({"errors"})
    score_fail_rules: list[ScoreRule] = field(default_factory=list)
    score_pass_rules: list[ScoreRule] = field(default_factory=list)
    latency_ms: float | None = None
    latency_percentile: float | None = None
    cost_usd: float | None = None
    cost_percentile: float | None = None
    group_by: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "capture": sorted(self.capture),
            "score_fail_rules": [str(r) for r in self.score_fail_rules],
            "score_pass_rules": [str(r) for r in self.score_pass_rules],
            "latency_ms": self.latency_ms,
            "latency_percentile": self.latency_percentile,
            "cost_usd": self.cost_usd,
            "cost_percentile": self.cost_percentile,
            "group_by": self.group_by,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ProjectConfig:
        def rules(key: str) -> list[ScoreRule]:
            parsed: list[ScoreRule] = []
            for item in raw.get(key) or []:
                try:
                    parsed.append(parse_score_rule(str(item)))
                except ScoreRuleError:
                    # A hand-edited bad rule shouldn't make the whole config
                    # unloadable — drop it and keep the rules that do parse.
                    continue
            return parsed

        # Drop unknown modes rather than letting them through. A typo in a
        # hand-edited config.json ("error" for "errors") would otherwise load
        # cleanly and then raise from CaptureConfig.__post_init__ mid-command.
        # This matches how the rest of this module treats a damaged file:
        # rules that don't parse are skipped, and a corrupt file loads empty.
        capture = {str(m).replace("-", "_") for m in (raw.get("capture") or ["errors"])}
        valid = capture & set(CAPTURE_MODES)

        return cls(
            capture=frozenset(valid or {"errors"}),
            score_fail_rules=rules("score_fail_rules"),
            score_pass_rules=rules("score_pass_rules"),
            latency_ms=_opt_float(raw.get("latency_ms")),
            latency_percentile=_opt_float(raw.get("latency_percentile")),
            cost_usd=_opt_float(raw.get("cost_usd")),
            cost_percentile=_opt_float(raw.get("cost_percentile")),
            group_by=raw.get("group_by") or None,
        )

    def unconfigured_modes(self) -> dict[str, str]:
        """Enabled modes that cannot fire yet, and what each one needs."""
        return unconfigured_modes(
            modes=self.capture,
            score_fail_rules=self.score_fail_rules,
            score_pass_rules=self.score_pass_rules,
            latency_ms=self.latency_ms,
            latency_percentile=self.latency_percentile,
            cost_usd=self.cost_usd,
            cost_percentile=self.cost_percentile,
        )


def unconfigured_modes(
    *,
    modes: Any,
    score_fail_rules: Any,
    score_pass_rules: Any,
    latency_ms: float | None,
    latency_percentile: float | None,
    cost_usd: float | None,
    cost_percentile: float | None,
) -> dict[str, str]:
    """Enabled capture modes that cannot fire yet, and what each one needs.

    Surfacing this is the whole point of the design: a mode that silently
    captures nothing — because the user never wrote a score rule, or never
    set a budget — is far worse than one that says what it is waiting for.
    Shared by ``ProjectConfig`` (file layer) and ``CaptureConfig`` (runtime).
    """
    missing: dict[str, str] = {}
    if "low_score" in modes and not score_fail_rules:
        missing["low_score"] = (
            "no score-fail rule set — run 'memanto migrate langfuse --discover' "
            "to see this project's score names, then add e.g. "
            "--score-fail 'correctness<0.7'"
        )
    if "success" in modes and not score_pass_rules:
        missing["success"] = (
            "no score-pass rule set — add e.g. --score-pass 'correctness>=0.9'"
        )
    if "slow" in modes and latency_ms is None and latency_percentile is None:
        missing["slow"] = (
            "no latency budget set — use --latency-ms <n> for a fixed budget, or "
            "--latency-percentile 95 to flag this project's own slowest tail"
        )
    if "costly" in modes and cost_usd is None and cost_percentile is None:
        missing["costly"] = (
            "no cost budget set — use --cost-usd <n> or --cost-percentile 95"
        )
    return missing


def _opt_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def project_key(*, project_id: str | None = None, api_key: str | None = None) -> str:
    """A stable identity for the Langfuse project being synced.

    Prefers the ``projectId`` carried on observations. Before any data has
    been fetched only the credential is known, and a Langfuse public key is
    project-scoped, so its hash is the fallback. Hashed rather than stored raw
    so the config file never contains a credential.
    """
    if project_id:
        return str(project_id)
    if api_key:
        public_key = api_key.split(":", 1)[0].strip()
        if public_key:
            digest = hashlib.sha256(public_key.encode("utf-8")).hexdigest()[:12]
            return f"pk-{digest}"
    return DEFAULT_PROJECT_KEY


def config_path(base_dir: Path) -> Path:
    return base_dir / CONFIG_FILENAME


def load_all(path: Path) -> dict[str, Any]:
    """Read the whole config file, tolerating absence and corruption."""
    empty: dict[str, Any] = {"version": CONFIG_VERSION, "projects": {}}
    if not path.exists():
        return empty
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty
    if not isinstance(loaded, dict):
        return empty
    projects = loaded.get("projects")
    return {
        "version": loaded.get("version", CONFIG_VERSION),
        "projects": projects if isinstance(projects, dict) else {},
    }


def load_project(path: Path, key: str) -> ProjectConfig:
    """Settings for one project, falling back to the ``default`` entry."""
    projects = load_all(path).get("projects", {})
    raw = projects.get(key)
    if not isinstance(raw, dict):
        raw = projects.get(DEFAULT_PROJECT_KEY)
    if not isinstance(raw, dict):
        return ProjectConfig()
    return ProjectConfig.from_dict(raw)


def save_project(path: Path, key: str, config: ProjectConfig) -> Path:
    """Persist settings for one project, leaving other projects untouched."""
    data = load_all(path)
    data["version"] = CONFIG_VERSION
    data.setdefault("projects", {})[key] = config.as_dict()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return path
