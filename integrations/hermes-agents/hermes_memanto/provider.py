"""Memanto Hermes provider with identity-bound profile selection.

The implementation remains in ``_provider_core`` so existing provider behavior
stays unchanged.  Profile resolution is replaced before any provider instance
can initialize, and all public and test-facing names are re-exported here.
"""

from __future__ import annotations

from pathlib import Path

from . import _provider_core as _core
from ._profile_identity import (
    resolve_compatible_profile_mapping as _resolve_identity_bound_profile,
)


# Preserve the module surface used by Hermes and by downstream integrations.
for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)


def _resolve_compatible_profile_mapping(
    hermes_home: str,
    identity: str,
    raw_agent_id: str,
) -> tuple[str, Path]:
    return _resolve_identity_bound_profile(
        hermes_home,
        identity,
        raw_agent_id,
        sanitize_agent_id=_core._sanitize_agent_id,
        legacy_sanitize_agent_id=_core._legacy_sanitize_agent_id,
    )


# Methods defined in _provider_core resolve globals in that module at runtime.
# Installing the resolver there therefore covers normal provider startup as
# well as direct calls through this compatibility module.
_core._resolve_compatible_profile_mapping = _resolve_compatible_profile_mapping
globals()["_resolve_compatible_profile_mapping"] = _resolve_compatible_profile_mapping

__all__ = ["MemantoMemoryProvider", "register"]
