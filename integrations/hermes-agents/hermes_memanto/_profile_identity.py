"""Persist the Hermes identity associated with each local profile directory."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

_METADATA_FILE = ".memanto_identity.json"
_CLAIM_ENV = "MEMANTO_HERMES_PROFILE_CLAIM"
_SCHEMA = 1


def _present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _error(profile: Path, detail: str) -> RuntimeError:
    return RuntimeError(
        f"Cannot select Hermes profile {profile.name!r}: {detail}. "
        f"After checking the directory, set {_CLAIM_ENV}={profile.name!r} "
        "for one startup to adopt an older profile without metadata."
    )


def _ensure_directory(profile: Path) -> bool:
    if profile.is_symlink():
        raise _error(profile, "the profile path is a symbolic link")
    if profile.exists():
        if not profile.is_dir():
            raise _error(profile, "the profile path is not a directory")
        return False
    profile.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    try:
        profile.mkdir(mode=0o700)
        return True
    except FileExistsError:
        if profile.is_symlink() or not profile.is_dir():
            raise _error(profile, "the profile path changed while it was created")
        return False


def _read_metadata(profile: Path) -> dict[str, object] | None:
    path = profile / _METADATA_FILE
    if not _present(path):
        return None
    if path.is_symlink() or not path.is_file():
        raise _error(profile, "the metadata path is not a regular file")
    try:
        raw = path.read_text(encoding="utf-8")
        if len(raw.encode("utf-8")) > 4096:
            raise ValueError("metadata is too large")
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise _error(profile, "the metadata file is invalid") from exc
    if not isinstance(value, dict):
        raise _error(profile, "the metadata file is not an object")
    return value


def _record(
    profile: Path,
    identity: str,
    raw_agent_id: str,
    agent_namespace: str,
) -> dict[str, object]:
    return {
        "schema": _SCHEMA,
        "identity": identity,
        "raw_agent_id": raw_agent_id,
        "profile": profile.name,
        "agent_namespace": agent_namespace,
    }


def _write_once(profile: Path, value: dict[str, object]) -> bool:
    path = profile / _METADATA_FILE
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return True
    except FileExistsError:
        return False
    except OSError as exc:
        raise _error(profile, "the metadata file could not be created") from exc


def _validated_namespace(
    profile: Path,
    value: dict[str, object],
    *,
    identity: str,
    raw_agent_id: str,
    allowed_namespaces: set[str],
) -> str:
    expected = {
        "schema": _SCHEMA,
        "identity": identity,
        "raw_agent_id": raw_agent_id,
        "profile": profile.name,
    }
    for key, expected_value in expected.items():
        if value.get(key) != expected_value:
            raise _error(profile, f"the metadata does not match {key!r}")
    namespace = value.get("agent_namespace")
    if not isinstance(namespace, str) or namespace not in allowed_namespaces:
        raise _error(profile, "the metadata contains an unknown agent namespace")
    return namespace


def _select(
    profile: Path,
    *,
    identity: str,
    raw_agent_id: str,
    default_namespace: str,
    allowed_namespaces: set[str],
    created: bool,
) -> str:
    value = _read_metadata(profile)
    if value is None:
        claimed = os.environ.get(_CLAIM_ENV) == profile.name
        if not created and not claimed:
            raise _error(profile, "the existing directory has no metadata")
        proposed = _record(profile, identity, raw_agent_id, default_namespace)
        if _write_once(profile, proposed):
            return default_namespace
        value = _read_metadata(profile)
        if value is None:
            raise _error(profile, "the metadata disappeared during creation")
    return _validated_namespace(
        profile,
        value,
        identity=identity,
        raw_agent_id=raw_agent_id,
        allowed_namespaces=allowed_namespaces,
    )


def resolve_compatible_profile_mapping(
    hermes_home: str,
    identity: str,
    raw_agent_id: str,
    *,
    sanitize_agent_id: Callable[[str], str],
    legacy_sanitize_agent_id: Callable[[str], str],
) -> tuple[str, Path]:
    """Return a profile and namespace only when their metadata matches."""
    new_identity = sanitize_agent_id(identity)
    old_identity = legacy_sanitize_agent_id(identity)
    new_agent = sanitize_agent_id(raw_agent_id)
    old_agent = legacy_sanitize_agent_id(raw_agent_id)
    allowed = {new_agent, old_agent}

    root = Path(hermes_home).expanduser() / "profiles"
    new_profile = root / new_identity
    old_profile = root / old_identity

    if new_identity != old_identity:
        has_new = _present(new_profile)
        has_old = _present(old_profile)
        if has_new and has_old:
            raise _error(
                new_profile,
                f"both {new_identity!r} and older alias {old_identity!r} exist",
            )
        if has_old:
            created = _ensure_directory(old_profile)
            namespace = _select(
                old_profile,
                identity=identity,
                raw_agent_id=raw_agent_id,
                default_namespace=old_agent,
                allowed_namespaces=allowed,
                created=created,
            )
            return namespace, old_profile
        if has_new:
            created = _ensure_directory(new_profile)
            namespace = _select(
                new_profile,
                identity=identity,
                raw_agent_id=raw_agent_id,
                default_namespace=new_agent,
                allowed_namespaces=allowed,
                created=created,
            )
            return namespace, new_profile

    existed = _present(new_profile)
    created = _ensure_directory(new_profile)
    default_namespace = old_agent if existed and new_agent != old_agent else new_agent
    namespace = _select(
        new_profile,
        identity=identity,
        raw_agent_id=raw_agent_id,
        default_namespace=default_namespace,
        allowed_namespaces=allowed,
        created=created,
    )
    return namespace, new_profile
