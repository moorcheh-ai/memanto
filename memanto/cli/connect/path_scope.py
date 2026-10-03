"""Project-local path scope checks for connect and sync writers."""

from __future__ import annotations

from pathlib import Path


def assert_project_local_path(
    project_path: Path,
    target: Path,
    *,
    is_global: bool = False,
    action: str = "local write",
) -> Path:
    """Resolve *target* and require project-local destinations when not global.

    Global destinations are intentional (user home / shared agent config) and
    are returned after resolve without a project-root check. Local destinations
    must resolve to a path beneath the project root; symlink aliases that escape
    the project are rejected before any mutation.
    """
    try:
        resolved = target.resolve(strict=False)
        if not is_global:
            root = project_path.resolve()
            resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f"Refusing {action} outside project: {target}") from exc
    return resolved
