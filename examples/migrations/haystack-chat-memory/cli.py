"""Run the shipped CLI with filesystem state confined to the demo private root."""

import os
from pathlib import Path
from unittest.mock import patch


def main() -> None:
    root = Path(os.environ["HAYSTACK_MEMANTO_CONFIG"]).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Memanto currently has no global config-directory flag. Its settings and
    # session services also use Path.home(), so changing only ConfigManager is
    # insufficient. Scope that lookup in this child process before any Memanto
    # import; do not change HOME or alter CLI/client/mapper/exporter behavior.
    with patch.object(Path, "home", return_value=root):
        from memanto.cli.main import app

        app()


if __name__ == "__main__":
    main()
