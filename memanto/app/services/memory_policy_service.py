"""
Memory Policy Service

Expiry policies decide when a memory stops being ``active`` and becomes
``expired``. Nothing expires on its own: a policy only takes effect when a
sweep runs (``apply_policies``), which stamps ``status`` / ``expired_at`` /
``expired_by`` onto each matching record. That makes expiry a durable,
auditable fact rather than something recomputed on every read — a recalled
memory can say *when* it expired and *which rule* did it.

A policy has two complementary halves:

``retention``
    A per-type table for broad strokes: ``context: 3d``, ``fact: never``.

``rules``
    Named, sharper match blocks evaluated in order. The first matching rule
    wins and short-circuits the table, so a rule can also *pin* a memory
    active by expiring after ``never``.
"""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from memanto.app.config import get_data_dir
from memanto.app.constants import VALID_MEMORY_TYPES, MemoryType, ProvenanceType
from memanto.app.core import BoundedExpiredBy, agent_namespace
from memanto.app.utils.atomic_write import atomic_write_text
from memanto.app.utils.errors import MemoryError
from memanto.app.utils.validation import validate_safe_id

POLICY_VERSION = 1

# "never" means "no expiry", represented as None once parsed.
NEVER = "never"

# ``mo`` must precede the single-letter class so "3mo" is not read as "3m".
# A month is the conventional 30 days: calendar months have no fixed length,
# and an expiry window does not need one.
_DURATION_RE = re.compile(r"^(\d+)\s*(mo|[mhdwy])$", re.IGNORECASE)
_DURATION_UNITS = {
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "mo": 2592000,
    "y": 31536000,
}


def parse_duration(value: Any) -> int | None:
    """Parse ``"7d"`` / ``"12h"`` / ``"never"`` into seconds.

    Returns None for ``never`` (and for None), meaning "does not expire".
    """
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        if value <= 0:
            raise ValueError("duration must be a positive number of seconds")
        return value
    if not isinstance(value, str):
        raise ValueError(f"invalid duration: {value!r}")

    token = value.strip().lower()
    if token in (NEVER, ""):
        return None

    match = _DURATION_RE.fullmatch(token)
    if not match:
        raise ValueError(
            f"invalid duration '{value}': use a number followed by "
            "m/h/d/w/mo/y (e.g. '30d', '3mo'), or 'never'"
        )
    amount = int(match.group(1))
    if amount <= 0:
        raise ValueError(f"invalid duration '{value}': must be greater than zero")
    return amount * _DURATION_UNITS[match.group(2).lower()]


def format_duration(seconds: int | None) -> str:
    """Render parsed seconds back into the compact form users wrote."""
    if seconds is None:
        return NEVER
    for unit in ("y", "w", "d", "h", "m"):
        size = _DURATION_UNITS[unit]
        if seconds % size == 0:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"


class PolicyMatch(BaseModel):
    """Conditions a memory must satisfy for a rule to fire.

    Every field that is set must match (AND). An empty match block matches
    every memory, which is how a catch-all rule is written.
    """

    type: list[MemoryType] | None = None
    tags: list[str] | None = None
    source: list[str] | None = None
    provenance: list[ProvenanceType] | None = None
    confidence_below: float | None = Field(default=None, ge=0.0, le=1.0)

    def matches(self, memory: dict[str, Any]) -> bool:
        """Return True when *memory* satisfies every condition set here."""
        if self.type is not None and memory.get("type") not in self.type:
            return False

        if self.tags is not None:
            memory_tags = memory.get("tags") or []
            if not any(tag in memory_tags for tag in self.tags):
                return False

        if self.source is not None and memory.get("source") not in self.source:
            return False

        if (
            self.provenance is not None
            and memory.get("provenance") not in self.provenance
        ):
            return False

        if self.confidence_below is not None:
            try:
                confidence = float(memory.get("confidence"))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                # Unknown confidence is not evidence of low confidence.
                return False
            if confidence >= self.confidence_below:
                return False

        return True


class PolicyRule(BaseModel):
    """A named expiry rule. ``name`` is stamped onto the memory as
    ``expired_by``, so it is bounded to the Moorcheh filter-token charset."""

    name: BoundedExpiredBy
    match: PolicyMatch = Field(default_factory=PolicyMatch)
    expire_after: str = NEVER

    @field_validator("expire_after", mode="before")
    @classmethod
    def _validate_expire_after(cls, value: Any) -> Any:
        """Reject an unparseable duration at load time, not at sweep time."""
        parse_duration(value)
        return value

    @property
    def expire_after_seconds(self) -> int | None:
        """This rule's expiry window in seconds, or None for ``never``."""
        return parse_duration(self.expire_after)


class MemoryPolicy(BaseModel):
    """The full expiry policy for one agent."""

    version: int = POLICY_VERSION
    retention: dict[str, str] = Field(default_factory=dict)
    rules: list[PolicyRule] = Field(default_factory=list)
    purge_expired_after: str = NEVER

    @field_validator("retention")
    @classmethod
    def _validate_retention(cls, value: dict[str, str]) -> dict[str, str]:
        """Every key must be a real memory type and every value a duration."""
        for memory_type, duration in value.items():
            if memory_type not in VALID_MEMORY_TYPES:
                valid = ", ".join(sorted(VALID_MEMORY_TYPES))
                raise ValueError(
                    f"unknown memory type '{memory_type}' in retention table. "
                    f"Must be one of: {valid}."
                )
            parse_duration(duration)
        return value

    @field_validator("purge_expired_after", mode="before")
    @classmethod
    def _validate_purge(cls, value: Any) -> Any:
        """Reject an unparseable purge window at load time."""
        parse_duration(value)
        return value

    @field_validator("rules")
    @classmethod
    def _validate_unique_rule_names(cls, value: list[PolicyRule]) -> list[PolicyRule]:
        """Rule names identify an expiry in the audit trail, so keep them unique."""
        seen: set[str] = set()
        for rule in value:
            if rule.name in seen:
                raise ValueError(f"duplicate rule name '{rule.name}'")
            seen.add(rule.name)
        return value

    @property
    def purge_expired_after_seconds(self) -> int | None:
        """The purge window in seconds, or None when purging is disabled."""
        return parse_duration(self.purge_expired_after)

    def is_empty(self) -> bool:
        """True when this policy would never expire anything."""
        return not self.rules and not any(
            parse_duration(duration) is not None for duration in self.retention.values()
        )


def _parse_timestamp(value: Any) -> datetime | None:
    """Best-effort parse of a stored timestamp into an aware datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def memory_age_basis(memory: dict[str, Any]) -> datetime | None:
    """The timestamp a memory's age is measured from.

    ``updated_at`` wins over ``created_at``: editing a memory is evidence it is
    still live, so an edit resets its expiry clock.
    """
    return _parse_timestamp(memory.get("updated_at")) or _parse_timestamp(
        memory.get("created_at")
    )


def evaluate(
    memory: dict[str, Any], policy: MemoryPolicy, now: datetime
) -> tuple[bool, str | None]:
    """Decide whether *memory* should be expired under *policy*.

    Pure function — no I/O. Returns ``(should_expire, reason)`` where reason is
    the rule name (or ``retention.<type>``) to stamp as ``expired_by``.

    The first matching rule wins and short-circuits the retention table, so a
    rule with ``expire_after: never`` pins a memory active.
    """
    # Already expired memories are left alone; a sweep never re-stamps them and
    # never revives them (restoring is always an explicit act).
    if (memory.get("status") or "active") != "active":
        return False, None

    basis = memory_age_basis(memory)
    if basis is None:
        # No usable timestamp means no defensible age, so never expire it.
        return False, None
    age = now - basis

    for rule in policy.rules:
        if rule.match.matches(memory):
            window = rule.expire_after_seconds
            if window is None or age < timedelta(seconds=window):
                return False, None
            return True, rule.name

    memory_type = memory.get("type")
    if not memory_type or memory_type not in policy.retention:
        return False, None

    window = parse_duration(policy.retention[memory_type])
    if window is None or age < timedelta(seconds=window):
        return False, None
    return True, f"retention.{memory_type}"


class MemoryPolicyService:
    """Load, save, and apply per-agent expiry policies."""

    def __init__(self, moorcheh_client, policies_dir: Path | None = None):
        """Initialize the service.

        Args:
            moorcheh_client: Active Moorcheh client, used by sweeps.
            policies_dir: Policy storage dir (defaults to ~/.memanto/policies/).
        """
        self.client = moorcheh_client
        self.policies_dir = policies_dir or get_data_dir() / "policies"

    def _policy_file(self, agent_id: str) -> Path:
        """Path to one agent's policy file, rejecting traversal in agent_id."""
        validate_safe_id(agent_id, "agent_id")
        return self.policies_dir / f"{agent_id}.yaml"

    def load_policy(self, agent_id: str) -> MemoryPolicy:
        """Return the agent's policy, or an empty one when none is set."""
        import importlib

        yaml = importlib.import_module("yaml")

        path = self._policy_file(agent_id)
        if not path.exists():
            return MemoryPolicy()

        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            raise MemoryError(f"Failed to read policy for '{agent_id}': {e}")

        if not isinstance(raw, dict):
            raise MemoryError(
                f"Policy file for '{agent_id}' must be a mapping, got {type(raw).__name__}"
            )

        try:
            return MemoryPolicy(**raw)
        except Exception as e:
            raise MemoryError(f"Invalid policy for '{agent_id}': {e}")

    def save_policy(self, agent_id: str, policy: MemoryPolicy) -> Path:
        """Persist *policy* for *agent_id* and return the file path."""
        import importlib

        yaml = importlib.import_module("yaml")

        path = self._policy_file(agent_id)
        self.policies_dir.mkdir(parents=True, exist_ok=True)
        # exclude_none keeps unset match conditions out of the file. Without it
        # every rule carries `type: null`, `source: null`, ... which buries the
        # two lines that actually matter in a file users hand-edit.
        atomic_write_text(
            path,
            yaml.safe_dump(
                policy.model_dump(mode="json", exclude_none=True),
                sort_keys=False,
                default_flow_style=False,
            ),
        )
        return path

    def _read_service(self):
        """Build a read service bound to this service's client."""
        from memanto.app.services.memory_read_service import MemoryReadService

        return MemoryReadService(self.client)

    def _write_service(self):
        """Build a write service bound to this service's client."""
        from memanto.app.services.memory_write_service import MemoryWriteService

        return MemoryWriteService(self.client)

    def apply_policies(
        self,
        agent_id: str,
        dry_run: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Evaluate the agent's policy over every memory and expire matches.

        Args:
            agent_id: Agent whose memories to sweep.
            dry_run: When True, report what would change without writing.
            now: Evaluation time; defaults to the current UTC time. The whole
                sweep shares one timestamp so a batch stamps consistently.

        Returns:
            A report with the matched memories, per-rule counts, and whether
            the changes were actually written.
        """
        policy = self.load_policy(agent_id)
        stamped_at = now or datetime.now(timezone.utc)
        namespace = agent_namespace(agent_id)

        read_service = self._read_service()
        memories = read_service._fetch_all_memories([namespace], status="active")
        # Counted only so callers can explain the two populations apart: a sweep
        # acts on active memories, while `purge_expired_after` acts on the
        # already-expired ones. Reporting one without the other reads as a bug.
        already_expired = len(
            read_service._fetch_all_memories([namespace], status="expired")
        )

        matched: list[dict[str, Any]] = []
        for memory in memories:
            should_expire, reason = evaluate(memory, policy, stamped_at)
            if should_expire and reason:
                matched.append(
                    {
                        "id": memory.get("id"),
                        "title": memory.get("title"),
                        "type": memory.get("type"),
                        "created_at": memory.get("created_at"),
                        "updated_at": memory.get("updated_at"),
                        "expired_by": reason,
                    }
                )

        per_rule: dict[str, int] = {}
        for item in matched:
            reason = str(item["expired_by"])
            per_rule[reason] = per_rule.get(reason, 0) + 1

        expired_count = 0
        errors: list[dict[str, str]] = []
        if not dry_run:
            write_service = self._write_service()
            for item in matched:
                memory_id = item.get("id")
                if not memory_id:
                    continue
                try:
                    write_service.set_lifecycle(
                        str(memory_id),
                        namespace,
                        expired=True,
                        reason=str(item["expired_by"]),
                        when=stamped_at,
                    )
                    expired_count += 1
                except Exception as e:
                    errors.append({"id": str(memory_id), "error": str(e)})

        return {
            "agent_id": agent_id,
            "dry_run": dry_run,
            "policy_is_empty": policy.is_empty(),
            "scanned": len(memories),
            "already_expired": already_expired,
            "matched": len(matched),
            "expired": expired_count,
            "per_rule": per_rule,
            "memories": matched,
            "errors": errors,
            "evaluated_at": stamped_at.isoformat(),
        }

    def purge_expired(
        self,
        agent_id: str,
        dry_run: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Permanently delete memories expired longer than the purge window.

        This is the only destructive step in the lifecycle and is disabled
        unless the policy sets ``purge_expired_after``. Deleted memories cannot
        be restored.
        """
        policy = self.load_policy(agent_id)
        window = policy.purge_expired_after_seconds
        evaluated_at = now or datetime.now(timezone.utc)

        if window is None:
            return {
                "agent_id": agent_id,
                "dry_run": dry_run,
                "enabled": False,
                "matched": 0,
                "purged": 0,
                "memories": [],
                "errors": [],
                "evaluated_at": evaluated_at.isoformat(),
            }

        namespace = agent_namespace(agent_id)
        read_service = self._read_service()
        memories = read_service._fetch_all_memories([namespace], status="expired")

        cutoff = evaluated_at - timedelta(seconds=window)
        matched = []
        for memory in memories:
            expired_at = _parse_timestamp(memory.get("expired_at"))
            # No stamp means no defensible purge date, so leave it alone.
            if expired_at is not None and expired_at <= cutoff:
                matched.append(
                    {
                        "id": memory.get("id"),
                        "title": memory.get("title"),
                        "expired_at": memory.get("expired_at"),
                        "expired_by": memory.get("expired_by"),
                    }
                )

        purged = 0
        errors: list[dict[str, str]] = []
        if not dry_run:
            write_service = self._write_service()
            for item in matched:
                memory_id = item.get("id")
                if not memory_id:
                    continue
                try:
                    write_service.delete_memory(str(memory_id), namespace)
                    purged += 1
                except Exception as e:
                    errors.append({"id": str(memory_id), "error": str(e)})

        return {
            "agent_id": agent_id,
            "dry_run": dry_run,
            "enabled": True,
            "purge_expired_after": policy.purge_expired_after,
            "matched": len(matched),
            "purged": purged,
            "memories": matched,
            "errors": errors,
            "evaluated_at": evaluated_at.isoformat(),
        }
