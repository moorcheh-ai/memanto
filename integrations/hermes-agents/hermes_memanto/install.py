"""Install the Memanto plugin into a Hermes plugins directory.

Hermes discovers memory providers as *directories* under
``$HERMES_HOME/plugins/<name>/`` (default ``~/.hermes/plugins``), each holding
an ``__init__.py`` that exposes ``register(ctx)`` plus a ``plugin.yaml``
manifest. This script writes a self-contained ``memanto/`` plugin folder there
by copying :mod:`hermes_memanto.provider` verbatim as the plugin's
``__init__.py`` — so once installed it only needs the ``memanto`` SDK (declared
in ``plugin.yaml``), not this package.

Usage::

    hermes-memanto-install                 # install into $HERMES_HOME (or ~/.hermes)
    hermes-memanto-install --hermes-home /path/to/.hermes
    hermes-memanto-install --force         # overwrite an existing install
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent
_PROVIDER_SRC = _PKG_DIR / "provider.py"
_PLUGIN_YAML = _PKG_DIR / "plugin.yaml"
_PLUGIN_README = _PKG_DIR / "PLUGIN_README.md"

_PLUGIN_NAME = "memanto"


def _default_hermes_home() -> Path:
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".hermes"


def install(hermes_home: Path, *, force: bool = False) -> Path:
    """Write the ``memanto`` plugin into ``hermes_home/plugins`` and return its path."""
    target = hermes_home / "plugins" / _PLUGIN_NAME
    if target.exists() and not force:
        raise FileExistsError(
            f"{target} already exists. Re-run with --force to overwrite it."
        )
    target.mkdir(parents=True, exist_ok=True)
    # The provider module doubles as the plugin's __init__.py (it exposes
    # register(ctx) and a MemantoMemoryProvider subclass).
    shutil.copyfile(_PROVIDER_SRC, target / "__init__.py")
    shutil.copyfile(_PLUGIN_YAML, target / "plugin.yaml")
    if _PLUGIN_README.exists():
        shutil.copyfile(_PLUGIN_README, target / "README.md")
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="hermes-memanto-install",
        description="Install the Memanto memory-agent plugin into Hermes.",
    )
    parser.add_argument(
        "--hermes-home",
        default=None,
        help="Hermes home directory (default: $HERMES_HOME or ~/.hermes).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing memanto plugin.",
    )
    args = parser.parse_args(argv)

    hermes_home = (
        Path(args.hermes_home).expanduser()
        if args.hermes_home
        else _default_hermes_home()
    )
    try:
        target = install(hermes_home, force=args.force)
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Installed the Memanto memory plugin at {target}")
    print("Next steps:")
    print("  1. pip install memanto")
    print("  2. export MOORCHEH_API_KEY=...   (https://console.moorcheh.ai/api-keys)")
    print("  3. hermes config set memory.provider memanto")
    print("     (or run: hermes memory setup  →  select 'memanto')")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
