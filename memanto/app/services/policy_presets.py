"""
Predefined expiry policy bundles.

Starting points users can enable in one command and then edit. Each is a
complete :class:`MemoryPolicy`: a per-type retention table plus a couple of
rules for the cases the table cannot express.

The shared shape across all three:

* ``preference``, ``instruction``, ``relationship`` are durable user truths and
  never expire on a timer in any preset.
* ``context`` is current-state scratch and rots fastest.
* Anything explicitly tagged ``pinned`` is exempt, because a user who pins a
  memory is overriding the policy on purpose.
"""

from typing import Any

from memanto.app.services.memory_policy_service import MemoryPolicy

# A rule shared by every preset: an explicit pin always beats the table.
_PINNED_RULE: dict[str, Any] = {
    "name": "pinned",
    "match": {"tags": ["pinned"]},
    "expire_after": "never",
}


PRESETS: dict[str, dict[str, Any]] = {
    "conservative": {
        "description": (
            "Expire only fast-rotting state. Nothing durable ages out, and "
            "nothing is ever purged."
        ),
        "policy": {
            "retention": {
                "context": "30d",
                "event": "90d",
                "error": "90d",
            },
            "rules": [_PINNED_RULE],
            "purge_expired_after": "never",
        },
    },
    "balanced": {
        "description": (
            "Sensible defaults for a working agent: transient state ages out "
            "in weeks, semantic knowledge in months, durable truths never."
        ),
        "policy": {
            "retention": {
                "context": "7d",
                "event": "30d",
                "error": "30d",
                "observation": "60d",
                "commitment": "90d",
                "artifact": "180d",
            },
            "rules": [
                _PINNED_RULE,
                {
                    "name": "scratch-notes",
                    "match": {"tags": ["scratch", "temp"]},
                    "expire_after": "3d",
                },
                {
                    "name": "low-confidence-guesses",
                    "match": {
                        "provenance": ["inferred"],
                        "confidence_below": 0.5,
                    },
                    "expire_after": "14d",
                },
            ],
            "purge_expired_after": "never",
        },
    },
    "aggressive": {
        "description": (
            "Keep the working set tight. Most types age out quickly and "
            "expired memories are purged after a year."
        ),
        "policy": {
            "retention": {
                "context": "3d",
                "event": "14d",
                "error": "14d",
                "observation": "30d",
                "commitment": "30d",
                "artifact": "60d",
                "fact": "180d",
                "decision": "180d",
                "goal": "180d",
                "learning": "180d",
            },
            "rules": [
                _PINNED_RULE,
                {
                    "name": "scratch-notes",
                    "match": {"tags": ["scratch", "temp"]},
                    "expire_after": "1d",
                },
                {
                    "name": "low-confidence-imports",
                    "match": {
                        "provenance": ["imported", "inferred"],
                        "confidence_below": 0.5,
                    },
                    "expire_after": "7d",
                },
            ],
            "purge_expired_after": "365d",
        },
    },
}


def list_presets() -> list[dict[str, Any]]:
    """Return every preset with its description and a short summary."""
    summaries = []
    for name, preset in PRESETS.items():
        policy = load_preset(name)
        summaries.append(
            {
                "name": name,
                "description": preset["description"],
                "retention": policy.retention,
                "rule_count": len(policy.rules),
                "purge_expired_after": policy.purge_expired_after,
            }
        )
    return summaries


def load_preset(name: str) -> MemoryPolicy:
    """Build the :class:`MemoryPolicy` for a named preset.

    Raises:
        ValueError: If *name* is not a known preset.
    """
    preset = PRESETS.get(name)
    if preset is None:
        valid = ", ".join(sorted(PRESETS))
        raise ValueError(f"Unknown preset '{name}'. Must be one of: {valid}.")
    return MemoryPolicy(**preset["policy"])
